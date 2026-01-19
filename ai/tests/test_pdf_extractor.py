"""
Test suite for PDF Extraction Service (TDD) using Docling

Run with: pytest tests/test_pdf_extractor.py -v
"""

import pytest
from pathlib import Path


class TestPDFExtractorImports:
    """Test that required dependencies are available."""

    def test_docling_available(self):
        """Docling should be available for PDF extraction."""
        from docling.document_converter import DocumentConverter
        assert DocumentConverter is not None

    def test_pydantic_available(self):
        """Pydantic should be available for data modeling."""
        from pydantic import BaseModel
        assert BaseModel is not None


class TestPDFExtractorBasic:
    """Basic tests for PDFExtractor class."""

    def test_extractor_initialization(self):
        """Test that extractor can be initialized with default settings."""
        from app.services.pdf_extractor import PDFExtractor
        extractor = PDFExtractor()
        assert extractor is not None
        assert extractor.ocr_enabled is True
        assert extractor.table_extraction is True

    def test_extractor_with_custom_settings(self):
        """Test that extractor can be initialized with custom settings."""
        from app.services.pdf_extractor import PDFExtractor, ExtractionMode
        extractor = PDFExtractor(
            ocr_enabled=False,
            table_extraction=False,
            extraction_mode=ExtractionMode.TEXT
        )
        assert extractor is not None
        assert extractor.ocr_enabled is False
        assert extractor.table_extraction is False

    def test_extract_text_from_pdf_function_exists(self):
        """Test that the standalone function exists."""
        from app.services.pdf_extractor import extract_text_from_pdf
        assert callable(extract_text_from_pdf)

    def test_extract_invoice_function_exists(self):
        """Test that the invoice extraction function exists."""
        from app.services.pdf_extractor import extract_invoice
        assert callable(extract_invoice)


class TestExtractedInvoiceModel:
    """Tests for the ExtractedInvoice Pydantic model."""

    def test_create_empty_invoice(self):
        """Test creating an empty extracted invoice."""
        from app.services.pdf_extractor import ExtractedInvoice

        invoice = ExtractedInvoice()
        assert invoice.invoice_number is None
        assert invoice.total_amount is None
        assert invoice.line_items == []

    def test_create_invoice_with_data(self):
        """Test creating an invoice with data."""
        from app.services.pdf_extractor import ExtractedInvoice, LineItem, ContactInfo

        invoice = ExtractedInvoice(
            invoice_number="INV-001",
            invoice_date="2024-01-15",
            total_amount=1500.00,
            currency="USD",
            sender=ContactInfo(name="Acme Corp"),
            line_items=[
                LineItem(description="Widget", quantity=10, unit_price=150.00, amount=1500.00)
            ]
        )

        assert invoice.invoice_number == "INV-001"
        assert invoice.total_amount == 1500.00
        assert len(invoice.line_items) == 1
        assert invoice.sender.name == "Acme Corp"

    def test_invoice_to_dict(self):
        """Test invoice serialization to dict."""
        from app.services.pdf_extractor import ExtractedInvoice

        invoice = ExtractedInvoice(invoice_number="INV-001", total_amount=100.00)
        data = invoice.model_dump()

        assert data["invoice_number"] == "INV-001"
        assert data["total_amount"] == 100.00


class TestExtractedItemModel:
    """Tests for the ExtractedItem dataclass."""

    def test_create_item(self):
        """Test creating an extracted item."""
        from app.services.pdf_extractor import ExtractedItem

        item = ExtractedItem(
            label="TEXT",
            text="Invoice #12345",
            page=1
        )

        assert item.label == "TEXT"
        assert item.text == "Invoice #12345"
        assert item.page == 1

    def test_item_to_dict(self):
        """Test item serialization to dict."""
        from app.services.pdf_extractor import ExtractedItem

        item = ExtractedItem(label="TABLE", text=None, page=2)
        data = item.to_dict()

        assert data["label"] == "TABLE"
        assert data["page"] == 2


class TestExtractedTableModel:
    """Tests for the ExtractedTable dataclass."""

    def test_create_table(self):
        """Test creating an extracted table."""
        from app.services.pdf_extractor import ExtractedTable

        table = ExtractedTable(
            table_id="table_0",
            page_number=1,
            dataframe=[["A", "B"], ["C", "D"]],
            row_count=2,
            col_count=2
        )

        assert table.table_id == "table_0"
        assert table.row_count == 2
        assert table.col_count == 2


class TestPDFExtractResult:
    """Tests for the PDFExtractResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful extraction result."""
        from app.services.pdf_extractor import PDFExtractResult, ExtractedItem

        result = PDFExtractResult(
            success=True,
            pages=2,
            full_text="Extracted text",
            items=[ExtractedItem(label="TEXT", text="Test", page=1)],
            tables=[]
        )

        assert result.success is True
        assert result.pages == 2
        assert result.error is None

    def test_failed_result(self):
        """Test creating a failed extraction result."""
        from app.services.pdf_extractor import PDFExtractResult

        result = PDFExtractResult(
            success=False,
            pages=0,
            full_text="",
            items=[],
            tables=[],
            error="File not found"
        )

        assert result.success is False
        assert result.error == "File not found"


class TestExtractionModes:
    """Tests for extraction mode configuration."""

    def test_text_mode(self):
        """Test text-only extraction mode."""
        from app.services.pdf_extractor import PDFExtractor, ExtractionMode

        extractor = PDFExtractor(
            extraction_mode=ExtractionMode.TEXT,
            table_extraction=False
        )
        assert extractor.extraction_mode == ExtractionMode.TEXT

    def test_tables_mode(self):
        """Test tables-only extraction mode."""
        from app.services.pdf_extractor import PDFExtractor, ExtractionMode

        extractor = PDFExtractor(
            extraction_mode=ExtractionMode.TABLES
        )
        assert extractor.extraction_mode == ExtractionMode.TABLES

    def test_full_mode(self):
        """Test full extraction mode."""
        from app.services.pdf_extractor import PDFExtractor, ExtractionMode

        extractor = PDFExtractor(
            extraction_mode=ExtractionMode.FULL
        )
        assert extractor.extraction_mode == ExtractionMode.FULL


class TestPDFExtractorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_nonexistent_file(self):
        """Test handling of non-existent files."""
        from app.services.pdf_extractor import PDFExtractor

        extractor = PDFExtractor()

        with pytest.raises(FileNotFoundError):
            extractor.extract("/nonexistent/path/file.pdf")

    def test_non_pdf_file(self):
        """Test handling of non-PDF files - Docling handles gracefully."""
        import tempfile
        from app.services.pdf_extractor import PDFExtractor

        extractor = PDFExtractor()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"This is not a PDF")
            f.flush()

            try:
                # Docling returns a failed result instead of raising
                result = extractor.extract(f.name)
                assert result.success is False
                assert "does not match any allowed format" in result.error or "format" in result.error.lower()
            finally:
                Path(f.name).unlink()


class TestInvoiceExtraction:
    """Tests for invoice-specific extraction."""

    def test_line_item_model(self):
        """Test the LineItem Pydantic model."""
        from app.services.pdf_extractor import LineItem

        item = LineItem(
            description="Widget A",
            quantity=10,
            unit_price=25.00,
            amount=250.00
        )

        assert item.description == "Widget A"
        assert item.quantity == 10
        assert item.unit_price == 25.00
        assert item.amount == 250.00

    def test_contact_info_model(self):
        """Test the ContactInfo Pydantic model."""
        from app.services.pdf_extractor import ContactInfo

        contact = ContactInfo(
            name="Acme Corp",
            address="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            email="billing@acme.com"
        )

        assert contact.name == "Acme Corp"
        assert contact.email == "billing@acme.com"
        assert contact.zip_code == "12345"


# Fixtures
@pytest.fixture
def sample_pdf_path(tmp_path):
    """Provide a sample PDF path for testing."""
    pytest.skip("PDF fixtures require actual PDF files")


@pytest.fixture
def invoice_pdf_path(tmp_path):
    """Provide an invoice PDF path for testing."""
    pytest.skip("Invoice PDF fixtures require actual files")
