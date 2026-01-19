"""
PDF Extraction Service using Docling

Docling provides advanced PDF understanding with:
- OCR for scanned documents
- TableFormer for table extraction
- Structured extraction using templates
- Document layout awareness

Usage:
    from app.services.pdf_extractor import PDFExtractor, extract_invoice

    # Simple extraction
    result = extract_invoice("invoice.pdf")

    # Advanced with custom options
    extractor = PDFExtractor(ocr_enabled=True)
    result = extractor.extract("invoice.pdf")
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
from enum import Enum
from pydantic import BaseModel, Field


class ExtractionMode(Enum):
    """Extraction mode options."""
    TEXT = "text"
    TABLES = "tables"
    FULL = "full"
    STRUCTURED = "structured"


@dataclass
class ExtractedTable:
    """Represents an extracted table from PDF."""
    table_id: str
    page_number: int
    dataframe: List[List[str]]  # 2D representation
    row_count: int
    col_count: int
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "page_number": self.page_number,
            "data": self.dataframe,
            "rows": self.row_count,
            "cols": self.col_count,
            "confidence": self.confidence,
        }


@dataclass
class ExtractedItem:
    """Represents a document element (text, table, figure, etc.)."""
    label: str  # TEXT, SECTION_HEADER, TABLE, PICTURE, etc.
    text: Optional[str]
    page: int
    bbox: Optional[List[float]] = None  # [x1, y1, x2, y2]
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "page": self.page,
            "bbox": self.bbox,
            "confidence": self.confidence,
        }


@dataclass
class PDFExtractResult:
    """Result of PDF extraction operation."""
    success: bool
    pages: int
    full_text: str
    items: List[ExtractedItem]
    tables: List[ExtractedTable]
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "pages": self.pages,
            "full_text": self.full_text,
            "items": [i.to_dict() for i in self.items],
            "tables": [t.to_dict() for t in self.tables],
            "metadata": self.metadata,
            "error": self.error,
        }


# Pydantic models for structured invoice extraction
class ContactInfo(BaseModel):
    """Sender or receiver contact information."""
    name: Optional[str] = Field(None, description="Company or person name")
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tax_id: Optional[str] = None


class LineItem(BaseModel):
    """Invoice line item."""
    item_number: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    unit: Optional[str] = None  # kg, hours, etc.
    sku: Optional[str] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None


class ExtractedInvoice(BaseModel):
    """Structured invoice extraction result."""
    invoice_number: Optional[str] = Field(None, description="Invoice number")
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    order_number: Optional[str] = None
    order_date: Optional[str] = None

    sender: Optional[ContactInfo] = None
    receiver: Optional[ContactInfo] = None
    bill_to: Optional[ContactInfo] = None
    ship_to: Optional[ContactInfo] = None

    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    shipping_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: Optional[float] = None
    amount_paid: Optional[float] = None
    amount_due: Optional[float] = None
    currency: Optional[str] = "USD"

    payment_terms: Optional[str] = None
    payment_method: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    routing_number: Optional[str] = None

    line_items: List[LineItem] = Field(default_factory=list)
    notes: Optional[str] = None

    raw_text: Optional[str] = None
    confidence_score: float = 0.0
    pages: int = 0


class PDFExtractor:
    """
    PDF extraction service using Docling.

    Features:
    - Multi-page PDF text extraction
    - Table detection with TableFormer
    - OCR for scanned documents
    - Structured invoice extraction with templates

    Args:
        ocr_enabled: Enable OCR for scanned PDFs
        table_extraction: Enable table extraction
        extraction_mode: Text, tables, full, or structured
    """

    def __init__(
        self,
        ocr_enabled: bool = True,
        table_extraction: bool = True,
        extraction_mode: ExtractionMode = ExtractionMode.FULL,
    ):
        self.ocr_enabled = ocr_enabled
        self.table_extraction = table_extraction
        self.extraction_mode = extraction_mode

        # Import docling (lazy to allow optional dependency)
        self._docling_available = False
        self._try_import_docling()

    def _try_import_docling(self) -> bool:
        """Try importing docling, return True if available."""
        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            self.DocumentConverter = DocumentConverter
            self.InputFormat = InputFormat
            self.PdfPipelineOptions = PdfPipelineOptions
            self._docling_available = True
            return True
        except ImportError:
            self._docling_available = False
            return False

    def _ensure_docling(self):
        """Ensure docling is installed, raise if not."""
        if not self._docling_available:
            raise ImportError(
                "Docling is not installed. Install with: pip install docling"
            )

    def extract(self, pdf_path: str) -> PDFExtractResult:
        """
        Extract content from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            PDFExtractResult with extracted content
        """
        self._ensure_docling()
        path = Path(pdf_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            # Configure pipeline options
            pipeline_options = self.PdfPipelineOptions()
            pipeline_options.do_ocr = self.ocr_enabled
            pipeline_options.do_table_structure = self.table_extraction

            # Create converter with options
            converter = self.DocumentConverter(
                format_options={self.InputFormat.PDF: pipeline_options}
            )

            # Convert PDF
            result = converter.convert(path)

            # Extract items
            items: List[ExtractedItem] = []
            tables: List[ExtractedTable] = []

            for item in result.document.iterate_items():
                # Determine page number from provenance
                page_num = 1
                if hasattr(item, 'prov') and item.prov:
                    if isinstance(item.prov, list) and len(item.prov) > 0:
                        page_num = item.prov[0].page_no + 1
                    elif hasattr(item.prov, 'page_no'):
                        page_num = item.prov.page_no + 1

                items.append(ExtractedItem(
                    label=str(item.label),
                    text=item.text if hasattr(item, 'text') else None,
                    page=page_num,
                ))

            # Extract tables
            for idx, table in enumerate(result.document.tables):
                df = table.export_to_dataframe()
                page_num = 1
                if hasattr(table, 'prov') and table.prov:
                    if isinstance(table.prov, list) and len(table.prov) > 0:
                        page_num = table.prov[0].page_no + 1
                    elif hasattr(table.prov, 'page_no'):
                        page_num = table.prov.page_no + 1

                tables.append(ExtractedTable(
                    table_id=f"table_{idx}",
                    page_number=page_num,
                    dataframe=df.values.tolist(),
                    row_count=len(df),
                    col_count=len(df.columns),
                ))

            # Build full text
            text_parts = []
            for item in items:
                if item.text:
                    text_parts.append(item.text)
            full_text = "\n\n".join(text_parts)

            return PDFExtractResult(
                success=True,
                pages=result.input.page_count,
                full_text=full_text,
                items=items,
                tables=tables,
                metadata={
                    "pdf_path": str(path.absolute()),
                    "file_size": result.input.filesize,
                    "format": str(result.input.format),
                },
            )

        except Exception as e:
            return PDFExtractResult(
                success=False,
                pages=0,
                full_text="",
                items=[],
                tables=[],
                error=str(e),
            )

    def extract_invoice(self, pdf_path: str) -> ExtractedInvoice:
        """
        Extract structured invoice data using Docling's template system.

        Args:
            pdf_path: Path to the invoice PDF

        Returns:
            ExtractedInvoice with structured data
        """
        self._ensure_docling()

        try:
            from docling.document_extractor import DocumentExtractor
            from docling.datamodel.base_models import InputFormat
            from docling_core.types.doc import ExtendedInvoice

            extractor = DocumentExtractor(
                allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
            )

            result = extractor.extract(
                source=pdf_path,
                template=ExtendedInvoice,
            )

            # Parse result into our Pydantic model
            invoice = ExtractedInvoice()

            if result and hasattr(result, 'pages') and result.pages:
                first_page = result.pages[0]
                if hasattr(first_page, 'extracted_data'):
                    data = first_page.extracted_data

                    # Map docling format to our format
                    invoice.invoice_number = data.get('invoice_no') or data.get('invoice_number')
                    invoice.invoice_date = data.get('date') or data.get('invoice_date')
                    invoice.due_date = data.get('due_date')
                    invoice.total_amount = data.get('total') or data.get('total_amount')

                    # Line items
                    if 'line_items' in data:
                        for item_data in data['line_items']:
                            invoice.line_items.append(LineItem(
                                description=item_data.get('description'),
                                quantity=item_data.get('quantity'),
                                unit_price=item_data.get('unit_price'),
                                amount=item_data.get('amount'),
                            ))

                    invoice.raw_text = first_page.get('text', '')
                    invoice.pages = len(result.pages) if hasattr(result, 'pages') else 1

            # If docling template extraction didn't work, try basic extraction
            if not invoice.invoice_number:
                basic_result = self.extract(pdf_path)
                invoice.raw_text = basic_result.full_text
                invoice.pages = basic_result.pages

            invoice.confidence_score = 0.85  # Default confidence
            return invoice

        except ImportError:
            # Fallback to basic extraction
            result = self.extract(pdf_path)
            invoice = ExtractedInvoice(
                raw_text=result.full_text,
                pages=result.pages,
                confidence_score=0.7,
            )
            return invoice

        except Exception as e:
            # Return empty invoice with error
            return ExtractedInvoice(
                raw_text=str(e),
                confidence_score=0.0,
            )


def extract_invoice(pdf_path: str) -> ExtractedInvoice:
    """
    Convenience function to extract invoice data.

    Args:
        pdf_path: Path to the invoice PDF

    Returns:
        ExtractedInvoice with structured data
    """
    extractor = PDFExtractor(ocr_enabled=True, table_extraction=True)
    return extractor.extract_invoice(pdf_path)


def extract_text_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from all pages of a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of page dictionaries with text and tables
    """
    extractor = PDFExtractor(extraction_mode=ExtractionMode.FULL)
    result = extractor.extract(pdf_path)

    if not result.success:
        raise ValueError(f"Failed to extract PDF: {result.error}")

    pages_data = []
    for page_num in range(1, result.pages + 1):
        page_items = [i for i in result.items if i.page == page_num]
        page_tables = [t for t in result.tables if t.page_number == page_num]

        pages_data.append({
            "page": page_num,
            "text": "\n".join(i.text for i in page_items if i.text),
            "tables": [t.to_dict() for t in page_tables],
        })

    return pages_data
