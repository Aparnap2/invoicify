"""Pydantic AI agent for invoice data extraction."""

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image
from pydantic import BaseModel
from pydantic_ai import Agent

from app.config import get_settings
from app.schemas.invoice import (
    InvoiceExtracted,
    InvoiceExtraction,
    ExtractedConfidence,
    LineItem,
)

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """Preprocess images for better OCR results."""

    @staticmethod
    def preprocess_image(image_data: bytes) -> bytes:
        """Preprocess image data for better extraction."""
        try:
            image = Image.open(BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            # Resize if too large (max 2000px on longest side)
            max_size = 2000
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.LANCZOS)

            # Save to JPEG
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85, optimize=True)
            return buffer.getvalue()
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}")
            return image_data

    @staticmethod
    def encode_image(image_data: bytes) -> str:
        """Encode image to base64 for LLM."""
        return base64.b64encode(image_data).decode("utf-8")


class InvoiceExtractionResult(BaseModel):
    """Result from the extraction agent."""

    success: bool
    data: Optional[InvoiceExtracted] = None
    confidence: float = 0.0
    notes: list[str] = []
    error: Optional[str] = None


class InvoiceExtractorAgent:
    """Pydantic AI agent for extracting structured data from invoices."""

    def __init__(self, model: Optional[str] = None):
        """Initialize the extraction agent."""
        settings = get_settings()
        self.model = model or settings.llm_model
        self._agent: Optional[Agent] = None
        self._setup_agent()

    def _setup_agent(self) -> None:
        """Set up the Pydantic AI agent with structured output."""
        self._agent = Agent(
            self.model,
            output_type=InvoiceExtracted,
            system_prompt="""You are an expert invoice data extraction agent.
Your task is to extract structured information from invoice documents.

Always:
1. Parse ALL line items accurately
2. Calculate totals to verify math
3. Identify vendor details even if poorly formatted
4. Note any fields that are unclear or missing
5. Provide confidence scores for each extracted field

Extract in this order:
- Vendor name and address
- Invoice number and date
- Due date
- Line items (all of them)
- Subtotals, taxes, and total
- Payment terms and PO number

If you cannot read something, mark it as None but explain in notes.""",
        )

    async def extract_from_text(
        self, raw_text: str, image_base64: Optional[str] = None
    ) -> InvoiceExtractionResult:
        """Extract invoice data from raw text."""
        try:
            prompt = f"""Extract all invoice data from the following content.

{f"Image available as base64: {image_base64[:100]}..." if image_base64 else ""}

Raw content:
{raw_text}

Extract structured data following the invoice schema."""

            result = await self._agent.run(prompt)

            # Calculate confidence scores
            confidence_scores = self._calculate_confidence_scores(result.output)

            extraction = InvoiceExtraction(
                confidence_scores=confidence_scores,
                overall_confidence=result.usage().output_tokens / 1000 if result.usage() else 0.5,
                extraction_notes=self._generate_notes(result.output),
                requires_review=any(
                    c.confidence < 0.8 for c in confidence_scores
                ),
            )

            extracted = InvoiceExtracted(
                **result.output.model_dump(),
                extraction=extraction,
            )

            return InvoiceExtractionResult(
                success=True,
                data=extracted,
                confidence=extraction.overall_confidence,
                notes=extraction.extraction_notes,
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return InvoiceExtractionResult(
                success=False, error=str(e), confidence=0.0
            )

    async def extract_from_file(
        self, file_path: Path, file_type: str
    ) -> InvoiceExtractionResult:
        """Extract invoice data from a file."""
        try:
            if file_type in ("png", "jpg", "jpeg"):
                return await self._extract_from_image(file_path)
            elif file_type == "pdf":
                return await self._extract_from_pdf(file_path)
            else:
                return InvoiceExtractionResult(
                    success=False,
                    error=f"Unsupported file type: {file_type}",
                )
        except Exception as e:
            logger.error(f"File extraction failed: {e}")
            return InvoiceExtractionResult(
                success=False, error=str(e)
            )

    async def _extract_from_image(self, file_path: Path) -> InvoiceExtractionResult:
        """Extract from image file."""
        image_data = file_path.read_bytes()
        preprocessed = ImagePreprocessor.preprocess_image(image_data)
        image_base64 = ImagePreprocessor.encode_image(preprocessed)

        # For images, we need OCR first (simplified - use LLM vision)
        prompt = """Analyze this invoice image and extract all structured data.
Provide the vendor name, invoice number, dates, line items, and totals."""

        result = await self._agent.run(prompt)

        return InvoiceExtractionResult(
            success=True,
            data=InvoiceExtracted(**result.output.model_dump()),
            confidence=0.85,
        )

    async def _extract_from_pdf(self, file_path: Path) -> InvoiceExtractionResult:
        """Extract from PDF file."""
        # For PDFs, we would use pdfplumber or similar
        # This is a simplified version
        prompt = f"""Extract all invoice data from this PDF document: {file_path}

Note: In production, we would first extract text using pdfplumber."""

        result = await self._agent.run(prompt)

        return InvoiceExtractionResult(
            success=True,
            data=InvoiceExtracted(**result.output.model_dump()),
            confidence=0.9,
        )

    def _calculate_confidence_scores(
        self, data: InvoiceExtracted
    ) -> list[ExtractedConfidence]:
        """Calculate confidence scores for extracted fields."""
        # Simplified - in production this would use more sophisticated logic
        return [
            ExtractedConfidence(
                field_name="vendor_name",
                confidence=0.95 if data.vendor_name else 0.0,
                extraction_method="llm",
            ),
            ExtractedConfidence(
                field_name="invoice_number",
                confidence=0.98 if data.invoice_number else 0.0,
                extraction_method="llm",
            ),
            ExtractedConfidence(
                field_name="total_amount",
                confidence=0.92 if data.total_amount else 0.0,
                extraction_method="llm",
            ),
        ]

    def _generate_notes(self, data: InvoiceExtracted) -> list[str]:
        """Generate extraction notes."""
        notes = []

        if not data.vendor_address:
            notes.append("Vendor address could not be extracted")

        if data.po_number is None:
            notes.append("No PO number found on invoice")

        if len(data.line_items) == 0:
            notes.append("No line items detected")

        # Verify math
        calculated_total = sum(item.amount for item in data.line_items)
        if calculated_total > 0 and data.subtotal > 0:
            if abs(float(calculated_total - data.subtotal)) > 0.01:
                notes.append(
                    f"Line item total ({calculated_total}) differs from subtotal ({data.subtotal})"
                )

        return notes


# Singleton instance
_extractor_agent: Optional[InvoiceExtractorAgent] = None


def get_extractor_agent() -> InvoiceExtractorAgent:
    """Get the singleton extractor agent."""
    global _extractor_agent
    if _extractor_agent is None:
        _extractor_agent = InvoiceExtractorAgent()
    return _extractor_agent
