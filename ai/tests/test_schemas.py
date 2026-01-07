"""Tests for invoice schemas."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.invoice import (
    LineItem,
    InvoiceBase,
    InvoiceCreate,
    InvoiceExtracted,
    InvoiceExtraction,
    ExtractedConfidence,
    POValidationResult,
    ApprovalRequest,
    ApprovalAction,
    ApprovalStatus,
    InvoiceStatus,
    RiskLevel,
    ProcessingResult,
)


class TestLineItem:
    """Tests for LineItem model."""

    def test_create_line_item(self):
        """Test basic line item creation."""
        item = LineItem(
            line_number=1,
            description="Consulting Services",
            quantity=Decimal("10"),
            unit_price=Decimal("150.00"),
            amount=Decimal("1500.00"),
        )
        assert item.line_number == 1
        assert item.description == "Consulting Services"
        assert item.amount == Decimal("1500.00")

    def test_line_item_with_optional_fields(self):
        """Test line item with optional fields."""
        item = LineItem(
            line_number=2,
            description="Software License",
            quantity=Decimal("5"),
            unit_price=Decimal("100.00"),
            amount=Decimal("500.00"),
            tax_code="TX-001",
            gl_code="6100-100",
        )
        assert item.tax_code == "TX-001"
        assert item.gl_code == "6100-100"

    def test_line_item_invalid_quantity(self):
        """Test that negative quantity raises error."""
        with pytest.raises(ValidationError):
            LineItem(
                line_number=1,
                description="Test",
                quantity=Decimal("-1"),
                unit_price=Decimal("10.00"),
                amount=Decimal("10.00"),
            )

    def test_line_item_amount_from_int(self):
        """Test amount conversion from int."""
        item = LineItem(
            line_number=1,
            description="Test",
            quantity=2,
            unit_price=50,
            amount=100,
        )
        assert item.amount == Decimal("100")


class TestInvoiceBase:
    """Tests for InvoiceBase model."""

    def test_create_invoice_base(self):
        """Test basic invoice creation."""
        invoice = InvoiceBase(
            vendor_name="Acme Corp",
            vendor_address="123 Main St",
            invoice_number="INV-001",
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1100.00"),
            line_items=[
                LineItem(
                    line_number=1,
                    description="Item 1",
                    quantity=Decimal("1"),
                    unit_price=Decimal("1000.00"),
                    amount=Decimal("1000.00"),
                )
            ],
        )
        assert invoice.vendor_name == "Acme Corp"
        assert invoice.invoice_number == "INV-001"
        assert invoice.total_amount == Decimal("1100.00")

    def test_invoice_default_currency(self):
        """Test default USD currency."""
        invoice = InvoiceBase(
            vendor_name="Test Vendor",
            invoice_number="INV-002",
            invoice_date=date.today(),
            due_date=date.today(),
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
        )
        assert invoice.currency == "USD"

    def test_invoice_missing_required_fields(self):
        """Test that missing required fields raise error."""
        with pytest.raises(ValidationError):
            InvoiceBase(
                vendor_name="Test",
                # Missing invoice_number, invoice_date, due_date, etc.
            )


class TestInvoiceCreate:
    """Tests for InvoiceCreate model."""

    def test_create_invoice_create(self):
        """Test InvoiceCreate creation."""
        invoice = InvoiceCreate(
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1100.00"),
            source_file_name="invoice.pdf",
            source_file_type="pdf",
        )
        assert invoice.source_file_name == "invoice.pdf"
        assert invoice.source_file_type == "pdf"


class TestInvoiceExtraction:
    """Tests for InvoiceExtraction model."""

    def test_create_extraction_confidence(self):
        """Test ExtractedConfidence creation."""
        confidence = ExtractedConfidence(
            field_name="vendor_name",
            confidence=0.95,
            extraction_method="llm",
        )
        assert confidence.confidence == 0.95
        assert confidence.field_name == "vendor_name"

    def test_confidence_bounds(self):
        """Test confidence score bounds."""
        # Valid confidence
        confidence = ExtractedConfidence(
            field_name="test",
            confidence=0.0,
            extraction_method="llm",
        )
        assert confidence.confidence == 0.0

        confidence = ExtractedConfidence(
            field_name="test",
            confidence=1.0,
            extraction_method="llm",
        )
        assert confidence.confidence == 1.0

    def test_invalid_confidence(self):
        """Test invalid confidence raises error."""
        with pytest.raises(ValidationError):
            ExtractedConfidence(
                field_name="test",
                confidence=1.5,  # Invalid: > 1.0
                extraction_method="llm",
            )


class TestPOValidationResult:
    """Tests for POValidationResult model."""

    def test_valid_po(self):
        """Test valid PO validation."""
        result = POValidationResult(
            is_valid=True,
            po_number="PO-001",
            po_amount=Decimal("1000.00"),
            invoice_amount=Decimal("1000.00"),
            variance=Decimal("0"),
            variance_percentage=0.0,
        )
        assert result.is_valid is True
        assert result.is_within_tolerance is True

    def test_po_within_tolerance(self):
        """Test PO within tolerance."""
        result = POValidationResult(
            is_valid=True,
            po_number="PO-001",
            po_amount=Decimal("1000.00"),
            invoice_amount=Decimal("1050.00"),
            variance=Decimal("50.00"),
            variance_percentage=5.0,
            tolerance_percentage=5.0,
        )
        assert result.is_within_tolerance is True

    def test_po_outside_tolerance(self):
        """Test PO outside tolerance."""
        result = POValidationResult(
            is_valid=False,
            po_number="PO-001",
            po_amount=Decimal("1000.00"),
            invoice_amount=Decimal("1200.00"),
            variance=Decimal("200.00"),
            variance_percentage=20.0,
            tolerance_percentage=5.0,
        )
        assert result.is_within_tolerance is False

    def test_validation_with_errors(self):
        """Test validation with errors."""
        result = POValidationResult(
            is_valid=False,
            po_number=None,
            invoice_amount=Decimal("100.00"),
            errors=["PO number not found"],
        )
        assert result.is_valid is False
        assert "PO number not found" in result.errors


class TestApprovalAction:
    """Tests for ApprovalAction model."""

    def test_approve_action(self):
        """Test approval action."""
        action = ApprovalAction(
            invoice_id=uuid4(),
            decision=ApprovalStatus.APPROVED,
            comments="Looks good",
            approver_id="user-123",
            approver_email="user@example.com",
        )
        assert action.decision == ApprovalStatus.APPROVED

    def test_reject_action(self):
        """Test rejection action."""
        action = ApprovalAction(
            invoice_id=uuid4(),
            decision=ApprovalStatus.REJECTED,
            comments="Incorrect amount",
            approver_id="user-456",
            approver_email="manager@example.com",
        )
        assert action.decision == ApprovalStatus.REJECTED


class TestInvoiceStatus:
    """Tests for InvoiceStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert InvoiceStatus.NEW.value == "new"
        assert InvoiceStatus.EXTRACTED.value == "extracted"
        assert InvoiceStatus.APPROVED.value == "approved"
        assert InvoiceStatus.EXCEPTION.value == "exception"


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_levels(self):
        """Test all risk levels exist."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"
