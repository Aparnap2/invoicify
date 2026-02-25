"""
Universal Invoice Extractor with AI Adapter Pattern.

Supports 3 modes based on ENVIRONMENT and EXTRACTOR_MODE:

1. FIXTURE MODE (EXTRACTOR_MODE=fixture)
   - Hardcoded test data
   - 0.01ms execution
   - Use for: Testing queues, databases, idempotency

2. LOCAL AI MODE (ENVIRONMENT=local, EXTRACTOR_MODE=ollama)
   - Ollama LightOnOCR-1B-1025 for OCR
   - Ollama qwen2.5-coder:3b for JSON extraction
   - nomic-embed-text for embeddings
   - Use for: Full local dev with real AI

3. PRODUCTION MODE (ENVIRONMENT=prod, EXTRACTOR_MODE=sarvam)
   - Sarvam Vision API for OCR
   - Groq Llama-3.3-70b for JSON extraction
   - Use for: Production deployment

Why this pattern?
- Agent Core only cares about contract: PDF In → Pydantic JSON Out
- Local dev not bottlenecked by internet/API limits
- Production gets best-in-class (Sarvam crushed Gemini on olmOCR-Bench)
"""

import os
import json
import re
import httpx
import base64
import structlog
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger()

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "local")
EXTRACTOR_MODE = os.getenv("EXTRACTOR_MODE", "ollama")  # 'ollama', 'sarvam', 'fixture'


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schema for Invoice Extraction
# ─────────────────────────────────────────────────────────────────────────────

class InvoiceSchema(BaseModel):
    """
    Strict AP schema for invoice extraction.
    All fields validated before state machine transition.
    """
    vendor_name: str = Field(..., min_length=1, max_length=255)
    vendor_address: Optional[str] = Field(default=None, max_length=500)
    vendor_tax_id: Optional[str] = Field(default=None, max_length=50)
    vendor_phone: Optional[str] = Field(default=None, max_length=50)
    vendor_email: Optional[str] = Field(default=None, max_length=255)
    
    invoice_number: str = Field(..., min_length=1, max_length=100)
    invoice_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    due_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    
    subtotal: float = Field(..., ge=0.0)
    tax_amount: float = Field(default=0.0, ge=0.0)
    total_amount: float = Field(..., ge=0.0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    
    po_number: Optional[str] = Field(default=None, max_length=100)
    payment_terms: Optional[str] = Field(default=None, max_length=255)
    
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    
    @field_validator("total_amount")
    @classmethod
    def validate_total(cls, v: float, info) -> float:
        """Ensure total_amount ≈ subtotal + tax_amount (5 paise tolerance)."""
        if hasattr(info, 'data'):
            subtotal = info.data.get("subtotal", 0)
            tax = info.data.get("tax_amount", 0)
            expected = subtotal + tax
            if abs(v - expected) > 0.05:
                raise ValueError(f"Total mismatch: {v:.2f} != {subtotal:.2f} + {tax:.2f}")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# PII Scrubber (SOC 2 Compliance)
# ─────────────────────────────────────────────────────────────────────────────

def redact_financial_pii(markdown_text: str) -> str:
    """
    Strips bank details and sensitive PII before sending to LLM.
    
    Groq/Ollama only needs amounts and line items to structure JSON.
    Bank account numbers, IBANs, and routing numbers are redacted.
    
    SOC 2 Compliance: Prevents PII leakage to third-party LLM providers.
    """
    # Mask IBAN / Swift codes (European/International bank accounts)
    iban_regex = r"\b[A-Z]{2}[0-9]{2}(?:[ ]?[0-9a-zA-Z]{4}){4}(?:[ ]?[0-9a-zA-Z]{1,2})?\b"
    
    # Mask Indian bank account numbers (8-18 digits)
    acct_regex = r"(?i)(account|acct|acc|a\/c)\s*(number|no|#)?\s*[:.-]?\s*\d{8,18}"
    
    # Mask IFSC codes (Indian bank branch codes)
    ifsc_regex = r"\b[A-Z]{4}0[A-Z0-9]{6}\b"
    
    # Mask routing numbers (9 digits)
    routing_regex = r"\b\d{9}\b"
    
    redacted = markdown_text
    
    # Apply redactions
    redacted = re.sub(iban_regex, "[REDACTED_IBAN]", redacted)
    redacted = re.sub(acct_regex, r"\1 \2: [REDACTED_ACCOUNT]", redacted)
    redacted = re.sub(ifsc_regex, "[REDACTED_IFSC]", redacted)
    redacted = re.sub(routing_regex, "[REDACTED_ROUTING]", redacted)
    
    logger.debug("pii_redaction_completed", original_len=len(markdown_text), redacted_len=len(redacted))
    
    return redacted


# ─────────────────────────────────────────────────────────────────────────────
# Universal Invoice Extractor
# ─────────────────────────────────────────────────────────────────────────────

class InvoiceExtractor:
    """
    Universal invoice extractor with AI adapter pattern.
    
    Routes to appropriate AI backend based on environment:
    - Fixture: Hardcoded data (fastest, for queue/db testing)
    - Ollama: Local Docker AI (LightOnOCR + qwen2.5-coder)
    - Sarvam: Production API (Sarvam Vision + Groq)
    
    Usage:
        extractor = InvoiceExtractor()
        result = await extractor.extract("/path/to/invoice.pdf", "INV-123")
    """
    
    # Sarvam Vision API endpoint (Akshar OCR)
    SARVAM_VISION_URL = "https://api.sarvam.ai/v1/document/extract"
    
    def __init__(self):
        """Initialize extractor with API keys from environment."""
        self.mode = EXTRACTOR_MODE
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.sarvam_api_key = os.getenv("SARVAM_API_KEY")
        
        logger.info("extractor_initialized", mode=self.mode, environment=ENV)
    
    async def extract(self, file_path: str, invoice_id: str) -> Dict[str, Any]:
        """
        End-to-end extraction: PDF → Markdown → JSON → Pydantic.
        
        Args:
            file_path: Path to PDF file
            invoice_id: Invoice ID for logging
        
        Returns:
            Validated invoice data as dict
        """
        logger.info("starting_extraction", mode=self.mode, invoice_id=invoice_id, file_path=file_path)
        
        # 1. FIXTURE MODE (Ultra-fast local dev for downstream testing)
        if self.mode == "fixture":
            return self._get_fixture_data(invoice_id)
        
        # 2. LOCAL AI MODE (Using your Docker Ollama setup)
        if self.mode == "ollama":
            markdown = await self._local_ocr_lighton(file_path)
            return await self._local_llm_json_qwen(markdown, invoice_id)
        
        # 3. PRODUCTION MODE (Sarvam + Groq)
        if self.mode == "sarvam":
            markdown = await self._prod_ocr_sarvam(file_path, invoice_id)
            redacted_markdown = redact_financial_pii(markdown)
            return await self._prod_llm_json_groq(redacted_markdown, invoice_id)
        
        raise ValueError(f"Unknown extractor mode: {self.mode}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # FIXTURE MODE
    # ─────────────────────────────────────────────────────────────────────────
    
    def _get_fixture_data(self, invoice_id: str) -> Dict[str, Any]:
        """Returns hardcoded dict to test queues and databases instantly."""
        logger.info("using_fixture_data", invoice_id=invoice_id)
        
        data = {
            "vendor_name": "Local Dev Supplies",
            "vendor_address": "123 Test Street, Bangalore 560001",
            "vendor_tax_id": "29AABCL1234C1Z5",
            "invoice_number": f"INV-{invoice_id}",
            "invoice_date": "2024-01-15",
            "due_date": "2024-02-15",
            "subtotal": 1500.0,
            "tax_amount": 270.0,
            "total_amount": 1770.0,
            "currency": "INR",
            "line_items": [
                {"description": "Test Item A", "quantity": 10, "unit_price": 100.0, "total": 1000.0},
                {"description": "Test Item B", "quantity": 5, "unit_price": 100.0, "total": 500.0}
            ],
            "po_number": "PO-TEST-001",
            "payment_terms": "Net 30",
            "confidence_score": 0.99,
        }
        
        return InvoiceSchema(**data).model_dump()
    
    # ─────────────────────────────────────────────────────────────────────────
    # LOCAL AI MODE (Ollama Docker)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _local_ocr_lighton(self, file_path: str) -> str:
        """
        Uses aipib/LightOnOCR-1B-1025 via local Docker Ollama.
        
        LightOnOCR is a 1B parameter model optimized for document OCR.
        It won't match Sarvam's accuracy on complex tables, but it's
        sufficient for testing system logic (queues, rate limits, state machines).
        """
        logger.info("local_ocr_started", model="aipib/LightOnOCR-1B-1025", file_path=file_path)
        
        try:
            with open(file_path, "rb") as f:
                encoded_image = base64.b64encode(f.read()).decode('utf-8')
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "aipib/LightOnOCR-1B-1025:latest",
                        "prompt": "Extract the text and tables from this invoice into Markdown format. Preserve the structure.",
                        "images": [encoded_image],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                result = response.json()
                markdown = result.get("response", "")
                
                logger.info("local_ocr_complete", markdown_len=len(markdown))
                return markdown
                
        except Exception as e:
            logger.error("local_ocr_failed", error=str(e))
            # Fallback to Docling if LightOn fails
            return await self._local_ocr_docling(file_path)
    
    async def _local_ocr_docling(self, file_path: str) -> str:
        """Fallback: Use Docling for PDF → Markdown conversion."""
        from io import BytesIO
        from docling.document_converter import DocumentConverter
        
        logger.info("using_docling_fallback", file_path=file_path)
        
        try:
            converter = DocumentConverter()
            with open(file_path, "rb") as f:
                result = converter.convert(BytesIO(f.read()))
            
            markdown = result.document.export_to_markdown()
            logger.info("docling_success", markdown_len=len(markdown))
            return markdown
            
        except Exception as e:
            logger.error("docling_failed", error=str(e))
            raise
    
    async def _local_llm_json_qwen(self, markdown: str, invoice_id: str) -> Dict[str, Any]:
        """
        Uses qwen2.5-coder:3b via local Ollama for JSON extraction.
        
        qwen2.5-coder is trained heavily on code/structure, making it
        superior to standard 3B models at outputting strict Pydantic JSON.
        """
        logger.info("local_llm_extraction_started", model="qwen2.5-coder:3b")
        
        from openai import AsyncOpenAI
        
        # Ollama natively exposes an OpenAI-compatible endpoint
        client = AsyncOpenAI(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
        )
        
        prompt = f"""
You are a strict Accounts Payable data extraction agent.
Parse the OCR markdown into the exact JSON schema below.

RULES:
1. If a field is missing or unclear, output null (do not hallucinate)
2. Dates must be YYYY-MM-DD format
3. Amounts must be numeric (no currency symbols)
4. Line items must include: description, quantity, unit_price, total
5. Validate: total_amount = subtotal + tax_amount (±0.05 tolerance)
6. Set confidence_score: 0.0-1.0 based on OCR quality and data completeness

OUTPUT ONLY VALID JSON. No explanations.

OCR MARKDOWN:
{markdown}
"""
        
        try:
            response = await client.chat.completions.create(
                model="qwen2.5-coder:3b",
                messages=[
                    {"role": "system", "content": "You are a strict AP extraction agent. Output JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,  # Deterministic output
                max_tokens=2000,
            )
            
            raw_json = json.loads(response.choices[0].message.content)
            validated_data = InvoiceSchema(**raw_json)
            
            logger.info("local_llm_extraction_success", invoice_id=invoice_id)
            return validated_data.model_dump()
            
        except Exception as e:
            logger.error("local_llm_extraction_failed", error=str(e))
            raise
    
    # ─────────────────────────────────────────────────────────────────────────
    # PRODUCTION MODE (Sarvam + Groq)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _prod_ocr_sarvam(self, file_path: str, invoice_id: str) -> str:
        """
        Call Sarvam Vision API for document intelligence.
        
        Returns high-fidelity Markdown preserving tables, reading order,
        and complex layouts (critical for Indian GST invoices).
        """
        logger.info("sarvam_ocr_started", invoice_id=invoice_id)
        
        if not self.sarvam_api_key:
            logger.warning("sarvam_key_missing_falling_back_to_local")
            return await self._local_ocr_lighton(file_path)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        self.SARVAM_VISION_URL,
                        headers={
                            "api-subscription-key": self.sarvam_api_key,
                            "Content-Type": "multipart/form-data",
                        },
                        files={
                            "file": (os.path.basename(file_path), f, "application/pdf")
                        },
                        data={"output_format": "markdown"},
                    )
                
                response.raise_for_status()
                data = response.json()
                
                markdown = data.get("markdown", "")
                if not markdown:
                    raise ValueError("Sarvam API returned empty markdown")
                
                logger.info(
                    "sarvam_ocr_success",
                    invoice_id=invoice_id,
                    markdown_len=len(markdown),
                )
                
                return markdown
                
            except httpx.HTTPStatusError as e:
                logger.error(
                    "sarvam_api_error",
                    invoice_id=invoice_id,
                    status=e.response.status_code,
                    error=str(e),
                )
                # Fallback to local OCR
                return await self._local_ocr_lighton(file_path)
            
            except Exception as e:
                logger.error(
                    "sarvam_unexpected_error",
                    invoice_id=invoice_id,
                    error=str(e),
                )
                raise
    
    async def _prod_llm_json_groq(self, markdown: str, invoice_id: str) -> Dict[str, Any]:
        """
        Use Groq Llama-3.3 to parse markdown into strict AP JSON schema.
        
        Groq is chosen for:
        - Sub-second latency (critical for phone conversations)
        - Free tier: 30 RPM (sufficient for demo scale)
        - JSON mode guarantee (no hallucinated fields)
        """
        logger.info("groq_extraction_started", invoice_id=invoice_id)
        
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(
            api_key=self.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        
        # System prompt with strict schema enforcement
        system_prompt = """
You are a strict Accounts Payable data extraction agent.
Parse the OCR markdown into the exact JSON schema below.

RULES:
1. If a field is missing or unclear, output null (do not hallucinate)
2. Dates must be YYYY-MM-DD format
3. Amounts must be numeric (no currency symbols)
4. Line items must include: description, quantity, unit_price, total
5. Validate: total_amount = subtotal + tax_amount (±0.05 tolerance)
6. Set confidence_score: 0.0-1.0 based on OCR quality and data completeness

OUTPUT ONLY VALID JSON. No explanations.
"""
        
        prompt = f"""
OCR MARKDOWN:
{markdown}

Extract the following fields as JSON:
{{
  "vendor_name": "string",
  "vendor_address": "string|null",
  "vendor_tax_id": "string|null",
  "vendor_phone": "string|null",
  "vendor_email": "string|null",
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD|null",
  "subtotal": number,
  "tax_amount": number,
  "total_amount": number,
  "currency": "INR|USD|EUR|etc",
  "line_items": [{{"description": "string", "quantity": number, "unit_price": number, "total": number}}],
  "po_number": "string|null",
  "payment_terms": "string|null",
  "confidence_score": 0.0-1.0
}}
"""
        
        try:
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,  # Deterministic output required
                max_tokens=2000,
            )
            
            raw_json = json.loads(response.choices[0].message.content)
            
            # Pydantic validation guarantees system safety
            validated_data = InvoiceSchema(**raw_json)
            
            logger.info("groq_extraction_success", invoice_id=invoice_id)
            return validated_data.model_dump()
            
        except Exception as e:
            logger.error("groq_extraction_failed", invoice_id=invoice_id, error=str(e))
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

async def extract_invoice(file_path: str, invoice_id: str) -> Dict[str, Any]:
    """
    Extract invoice data using configured AI backend.
    
    Usage:
        data = await extract_invoice("/path/to/invoice.pdf", "INV-123")
    """
    extractor = InvoiceExtractor()
    return await extractor.extract(file_path, invoice_id)
