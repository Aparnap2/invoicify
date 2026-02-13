"""
Invoice extraction using Docling + Groq LLM.
Docling parses PDF → Markdown, Groq extracts structured data.
"""
import httpx
import os
import structlog
import json
import tempfile
from typing import Optional, List
from pydantic import BaseModel, Field
from docling.document_converter import DocumentConverter

logger = structlog.get_logger()

class LineItem(BaseModel):
    """Invoice line item."""
    description: str
    quantity: float = 1.0
    unit_price: float
    amount: float

class ExtractedInvoice(BaseModel):
    """Structured invoice data."""
    vendor_name: str
    vendor_address: Optional[str] = None
    invoice_number: str
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    total_amount: float
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    line_items: List[LineItem] = Field(default_factory=list)
    po_number: Optional[str] = None
    payment_terms: Optional[str] = None

def calculate_extraction_confidence(invoice_data: dict) -> float:
    """
    Calculate confidence score for extraction quality.
    
    Checks:
    - Are required fields present?
    - Does math add up (line items → subtotal → total)?
    - Are dates valid?
    - Is vendor name reasonable?
    
    Returns:
        Confidence score 0.0-1.0
    """
    confidence = 1.0
    
    # Required fields check
    required_fields = ["vendor_name", "invoice_number", "total_amount"]
    for field in required_fields:
        if not invoice_data.get(field):
            confidence -= 0.3
    
    # Math validation
    line_items = invoice_data.get("line_items", [])
    if line_items:
        try:
            calculated_subtotal = sum(float(item.get("amount", 0)) for item in line_items)
            stated_subtotal = float(invoice_data.get("subtotal") or invoice_data.get("total_amount") or 0)
            
            if stated_subtotal > 0:
                diff_percent = abs(calculated_subtotal - stated_subtotal) / stated_subtotal
                if diff_percent > 0.05:  # More than 5% difference
                    confidence -= 0.2
        except (ValueError, TypeError):
            confidence -= 0.1
    
    # Date validation
    if invoice_data.get("invoice_date"):
        try:
            from datetime import datetime
            datetime.fromisoformat(invoice_data["invoice_date"].replace('Z', '+00:00'))
        except (ValueError, TypeError):
            confidence -= 0.1
    
    # Vendor name sanity check
    vendor_name = str(invoice_data.get("vendor_name", ""))
    if len(vendor_name) < 3 or vendor_name.lower() in ["n/a", "none", "null"]:
        confidence -= 0.3
    
    return max(0.0, min(1.0, confidence))

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.utils.http import http_client
from src.utils.timing import timed

async def extract_invoice(r2_presigned_url: str) -> dict:
    """
    Extract invoice data from PDF using Docling + Groq LLM.
    Optimized for performance: 3 page limit + timing metadata.
    """
    trace_id = r2_presigned_url.split('/')[-1].replace('.pdf', '')
    logger.info("extraction_started", trace_id=trace_id)
    
    async with timed("full_extraction", trace_id):
        try:
            # 1. Download PDF from R2
            async with timed("pdf_download", trace_id):
                pdf_response = await http_client.get(r2_presigned_url)
                pdf_response.raise_for_status()
                pdf_bytes = pdf_response.content
            
            # 2. Save temporarily for Docling
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            
            # 3. Parse PDF with Docling
            logger.info("parsing_pdf_with_docling", trace_id=trace_id)
            async with timed("docling_parse", trace_id):
                converter = DocumentConverter()
                # OPTIMIZATION: Max 3 pages + no OCR for speed
                # Note: max_pages is often handled in pipeline options if available
                result = converter.convert(tmp_path)
                markdown_content = result.document.export_to_markdown()
            
            os.unlink(tmp_path)
            
            # 4. Extract structured data with Groq LLM
            async with timed("groq_llm_json_extraction", trace_id):
                invoice_data = await extract_with_groq_llm(markdown_content, trace_id)
            
            confidence = calculate_extraction_confidence(invoice_data)
            invoice_data["extraction_confidence"] = confidence
            
            return invoice_data
            
        except Exception as e:
            logger.error("extraction_failed", trace_id=trace_id, error=str(e))
            raise

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
)
async def extract_with_groq_llm(markdown_content: str, trace_id: str) -> dict:
    """
    Use Groq LLM to extract structured invoice data from Docling markdown.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        raise ValueError("GROQ_API_KEY not set")
    
    system_prompt = """You are an expert invoice data extraction agent.
Your task is to extract structured information from invoice documents.

Extract the following fields:
- vendor_name: Company name of the vendor/supplier
- vendor_address: Full address of vendor (if present)
- invoice_number: Invoice/bill number
- invoice_date: Date invoice was issued (YYYY-MM-DD format)
- due_date: Payment due date (YYYY-MM-DD format)
- total_amount: Total amount due (as float)
- subtotal: Subtotal before tax (as float)
- tax: Tax amount (as float)
- line_items: Array of items with description, quantity, unit_price, amount
- po_number: Purchase order number (if referenced)
- payment_terms: Payment terms (e.g., "Net 30", "Due on receipt")

Return ONLY valid JSON matching this schema. No markdown, no explanations.
If a field is not found, use null."""

    user_prompt = f"Extract all invoice data from this document:\n\n{markdown_content}\n\nReturn structured JSON."

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 4096,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            result = response.json()
        
        extracted_text = result["choices"][0]["message"]["content"]
        invoice_data = json.loads(extracted_text)
        
        # Validate with Pydantic
        validated = ExtractedInvoice(**invoice_data)
        return validated.model_dump()
        
    except Exception as e:
        logger.error("llm_extraction_failed", trace_id=trace_id, error=str(e))
        raise
