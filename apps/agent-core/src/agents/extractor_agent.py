"""
Extractor Agent for Invoice Processing.

Uses Docling for PDF → Markdown conversion, then any OpenAI-compatible LLM
for structured extraction to ExtractedInvoice schema.

Provider Configuration:
-----------------------
All providers use the same OpenAI SDK - just change the config:

# Local (Ollama with granite-docling)
ExtractorAgent(config={
    "llm_provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "ibm/granite-docling",
})

# Production (Groq)
ExtractorAgent(config={
    "llm_provider": "groq",
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": os.getenv("GROQ_API_KEY"),
    "model": "llama-3.2-90b-vision-preview",
})

# Azure Foundry
ExtractorAgent(config={
    "llm_provider": "azure",
    "base_url": os.getenv("AZURE_OPENAI_ENDPOINT"),
    "api_key": os.getenv("AZURE_OPENAI_KEY"),
    "model": "gpt-4o",
})
"""

import time
from typing import Any, Dict, Optional
from openai import AsyncOpenAI
import structlog

from src.schemas.invoice_v2 import ExtractedInvoice, VendorInfo, LineItem

logger = structlog.get_logger()


class ExtractorAgent:
    """
    Extracts structured invoice data from PDF documents.
    
    Uses Docling for PDF→Markdown and any OpenAI-compatible LLM for extraction.
    """

    # Provider configurations
    PROVIDERS = {
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "model": "ibm/granite-docling",
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "model": "llama-3.2-90b-vision-preview",
        },
        "azure": {
            "api_key_env": "AZURE_OPENAI_KEY",
            "base_url_env": "AZURE_OPENAI_ENDPOINT",
            "model": "gpt-4o",
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize extractor.

        Args:
            config: Configuration dict with:
                - llm_provider: "ollama" | "groq" | "azure"
                - base_url: API base URL (optional, uses default if not provided)
                - api_key: API key (optional, uses env var if not provided)
                - model: Model name (optional, uses default if not provided)
        """
        self.config = config or {}
        self.provider = config.get("llm_provider", "ollama")
        
        # Get provider defaults
        defaults = self.PROVIDERS.get(self.provider, {})
        
        # Configure with overrides
        self.base_url = config.get("base_url", defaults.get("base_url"))
        self.api_key = config.get("api_key")
        self.model = config.get("model", defaults.get("model", "gpt-4o"))
        
        # Handle env var lookups
        if not self.api_key and defaults.get("api_key_env"):
            import os
            self.api_key = os.getenv(defaults["api_key_env"])
        
        if not self.base_url and defaults.get("base_url_env"):
            import os
            self.base_url = os.getenv(defaults["base_url_env"])
        
        # Initialize OpenAI client
        self.client = self._create_client()
    
    def _create_client(self) -> AsyncOpenAI:
        """Create OpenAI client for configured provider."""
        if self.provider == "azure":
            from openai import AsyncAzureOpenAI
            return AsyncAzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.base_url,
                api_version="2024-08-01-preview",
            )
        else:
            return AsyncOpenAI(
                api_key=self.api_key or "ollama",
                base_url=self.base_url,
            )

    async def extract_from_url(self, r2_url: str) -> ExtractedInvoice:
        """
        Extract invoice from PDF URL.

        Pipeline:
        1. Download PDF
        2. Docling: PDF → Markdown
        3. LLM: Markdown → JSON
        4. Pydantic validation

        Args:
            r2_url: Presigned R2 URL for PDF

        Returns:
            ExtractedInvoice: Structured invoice data
        """
        start_time = time.perf_counter()

        try:
            # Step 1: Download PDF
            pdf_content = await self._download_pdf(r2_url)

            # Step 2: Convert to Markdown with Docling
            markdown = await self._pdf_to_markdown(pdf_content)

            # Step 3: Extract structured data with LLM
            extracted_json = await self._extract_with_llm(markdown)

            # Step 4: Validate with Pydantic
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            extracted_json["extraction_latency_ms"] = latency_ms
            extracted_json["extraction_model"] = f"{self.provider}/{self.model}"

            invoice = ExtractedInvoice(**extracted_json)

            logger.info(
                "invoice_extracted",
                invoice_id=invoice.invoice_id,
                confidence=invoice.extraction_confidence,
                latency_ms=latency_ms,
                provider=self.provider,
                model=self.model,
            )

            return invoice

        except Exception as e:
            logger.error("extraction_failed", error=str(e), url=r2_url)
            raise

    async def _download_pdf(self, url: str) -> bytes:
        """Download PDF from URL."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def _pdf_to_markdown(self, pdf_content: bytes) -> str:
        """Convert PDF to Markdown using Docling."""
        from io import BytesIO
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(BytesIO(pdf_content))
        return result.document.export_to_markdown()

    async def _extract_with_llm(self, markdown: str) -> Dict[str, Any]:
        """
        Extract structured data from Markdown using LLM.
        
        Uses the unified OpenAI SDK - works with any OpenAI-compatible provider.
        """
        prompt = self._build_extraction_prompt(markdown)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an invoice extraction expert. Extract invoice data as structured JSON. Focus on accuracy for financial data."
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        import json
        result = json.loads(response.choices[0].message.content)

        return self._normalize_extraction(result)

    def _build_extraction_prompt(self, markdown: str) -> str:
        """Build prompt for LLM extraction."""
        return f"""
Extract the following fields from this invoice:

REQUIRED FIELDS:
- invoice_number: string (e.g., "INV-2024-001")
- vendor: object with:
  - name: string (vendor legal name)
  - address: string|null
  - tax_id: string|null (GST/VAT number)
  - phone: string|null
  - email: string|null
- line_items: array of objects with:
  - description: string
  - quantity: number
  - unit_price: number
  - total: number
  - tax_rate: number|null (0.0-1.0)
- subtotal: number (sum of line items before tax)
- tax_amount: number
- total_amount: number (subtotal + tax)
- currency: string (default "USD")
- invoice_date: string (YYYY-MM-DD format)
- due_date: string|null (YYYY-MM-DD format)
- po_number: string|null (purchase order number)
- payment_terms: string|null (e.g., "Net 30")

METADATA:
- extraction_confidence: number (0.0-1.0) - your confidence in the extraction
- missing_fields: array of strings - list any fields you couldn't find

INVOICE MARKDOWN:
{markdown}

Return ONLY valid JSON. Do not include any other text or explanation.
"""

    def _normalize_extraction(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize LLM output to ExtractedInvoice schema.
        
        Handles:
        - Default confidence
        - Vendor structuring
        - Line item calculations
        - Total calculations
        """
        # Set default confidence if not provided
        if "extraction_confidence" not in result:
            result["extraction_confidence"] = 0.85

        # Ensure vendor is properly structured
        if "vendor" in result:
            vendor = result["vendor"]
            if isinstance(vendor, str):
                result["vendor"] = {"name": vendor}

        # Ensure line items have required fields
        if "line_items" in result:
            for i, item in enumerate(result["line_items"]):
                # Calculate total if missing
                if "total" not in item and "quantity" in item and "unit_price" in item:
                    item["total"] = item["quantity"] * item["unit_price"]

        # Calculate totals if not provided
        if "line_items" in result:
            line_totals = [item.get("total", 0) for item in result["line_items"]]
            
            if "subtotal" not in result:
                result["subtotal"] = sum(line_totals)
            
            if "tax_amount" not in result:
                result["tax_amount"] = 0.0
            
            if "total_amount" not in result:
                result["total_amount"] = result["subtotal"] + result["tax_amount"]

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Convenience factory functions
# ─────────────────────────────────────────────────────────────────────────────

def create_local_extractor() -> ExtractorAgent:
    """Create extractor with local Ollama (granite-docling)."""
    return ExtractorAgent(config={
        "llm_provider": "ollama",
        "model": "ibm/granite-docling",
    })


def create_groq_extractor() -> ExtractorAgent:
    """Create extractor with Groq (llama-3.2-90b-vision)."""
    return ExtractorAgent(config={
        "llm_provider": "groq",
        "model": "llama-3.2-90b-vision-preview",
    })


def create_azure_extractor() -> ExtractorAgent:
    """Create extractor with Azure Foundry (GPT-4o)."""
    return ExtractorAgent(config={
        "llm_provider": "azure",
        "model": "gpt-4o",
    })
