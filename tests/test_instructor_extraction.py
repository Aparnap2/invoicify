"""
Comprehensive tests for instructor-based invoice extraction.

This test suite follows TDD principles and tests the structured extraction
schemas and instructor integration for invoice processing.
"""

import pytest
from decimal import Decimal
from datetime import date, datetime
from uuid import uuid4
from typing import Dict, Any

from app.schemas.invoice_extraction import (
    Address, Vendor, LineItem, InvoiceHeader, ConfidenceScores,
    InvoiceExtraction, FieldPatch, ExtractionPatchResponse,
    InvoiceContext, ExtractionQuality,
    create_extraction_from_dict, calculate_extraction_quality
)


class TestAddress:
    """Test cases for Address model."""

    def test_complete_address_validation(self):
        """Test validation of complete address."""
        address = Address(
            street="123 Business St",
            city="New York",
            state="NY",
            postal_code="10001",
            country="US"
        )
        assert address.country == "US"  # Should be uppercase
        assert address.postal_code == "10001"  # Should be uppercase

    def test_partial_address(self):
        """Test validation of partial address."""
        address = Address(city="Boston")
        assert address.city == "Boston"
        assert address.street is None

    def test_invalid_country_code(self):
        """Test validation of invalid country code."""
        with pytest.raises(ValueError, match="String should have at most 2 characters"):
            Address(country="USA")  # Should be 2 letters

    def test_invalid_postal_code(self):
        """Test validation of invalid postal code."""
        with pytest.raises(ValueError, match="Invalid postal code format"):
            Address(postal_code="abc@#$")

    def test_postal_code_formatting(self):
        """Test postal code formatting."""
        address = Address(postal_code="10001-1234")
        assert address.postal_code == "10001-1234"

        address = Address(postal_code="sw1a 0aa")
        assert address.postal_code == "SW1A 0AA"


class TestVendor:
    """Test cases for Vendor model."""

    def test_complete_vendor(self):
        """Test validation of complete vendor."""
        address = Address(
            street="456 Commerce Ave",
            city="San Francisco",
            state="CA",
            postal_code="94102",
            country="US"
        )

        vendor = Vendor(
            vendor_name="Acme Corporation Inc.",
            vendor_address=address,
            vendor_tax_id="12-3456789",
            vendor_email="billing@acme.com",
            vendor_phone="(415) 555-0123",
            vendor_website="https://acme.com"
        )

        assert vendor.vendor_name == "Acme Corporation Inc."
        assert vendor.vendor_tax_id == "123456789"  # Cleaned
        assert vendor.vendor_email == "billing@acme.com"  # Lowercase

    def test_invalid_email(self):
        """Test validation of invalid email."""
        with pytest.raises(ValueError, match="Invalid email format"):
            Vendor(vendor_email="not-an-email")

    def test_invalid_tax_id(self):
        """Test validation of invalid tax ID."""
        with pytest.raises(ValueError, match="Tax ID length should be between 5 and 20"):
            Vendor(vendor_tax_id="123")

    def test_invalid_phone(self):
        """Test validation of invalid phone number."""
        with pytest.raises(ValueError, match="Phone number too short"):
            Vendor(vendor_phone="123")

    def test_phone_formatting(self):
        """Test phone number formatting preserved."""
        vendor = Vendor(vendor_phone="(415) 555-0123 ext. 123")
        assert vendor.vendor_phone == "(415) 555-0123 ext. 123"


class TestLineItem:
    """Test cases for LineItem model."""

    def test_complete_line_item(self):
        """Test validation of complete line item."""
        line = LineItem(
            line_number=1,
            description="Office Supplies",
            quantity=Decimal("10.00"),
            unit_price=Decimal("15.50"),
            total_amount=Decimal("155.00"),
            item_code="OFF-001",
            gl_account="6500",
            tax_rate=Decimal("0.08"),
            tax_amount=Decimal("12.40")
        )

        assert line.line_number == 1
        assert line.quantity == Decimal("10.00")
        assert line.unit_price == Decimal("15.50")
        assert line.total_amount == Decimal("155.00")

    def test_line_item_math_validation(self):
        """Test mathematical consistency validation."""
        # This should pass
        line = LineItem(
            description="Test Item",
            quantity=Decimal("5.00"),
            unit_price=Decimal("10.00"),
            total_amount=Decimal("50.00")  # 5 * 10 = 50
        )

        # This should fail due to math inconsistency
        with pytest.raises(ValueError, match="Line item total inconsistency"):
            LineItem(
                description="Wrong Math Item",
                quantity=Decimal("5.00"),
                unit_price=Decimal("10.00"),
                total_amount=Decimal("75.00")  # Wrong total
            )

    def test_line_item_with_discount(self):
        """Test line item with discount calculation."""
        line = LineItem(
            description="Discounted Item",
            quantity=Decimal("2.00"),
            unit_price=Decimal("100.00"),
            total_amount=Decimal("180.00"),  # 2 * 100 * 0.9 = 180
            discount_rate=Decimal("0.10")
        )

        assert line.discount_rate == Decimal("0.10")

    def test_required_fields(self):
        """Test required fields validation."""
        # Missing required fields should fail
        with pytest.raises(ValueError):
            LineItem()  # All required fields missing

    def test_negative_values(self):
        """Test validation of negative values."""
        with pytest.raises(ValueError):
            LineItem(
                description="Test",
                quantity=Decimal("-1.00"),
                unit_price=Decimal("10.00"),
                total_amount=Decimal("10.00")
            )

    def test_decimal_places(self):
        """Test decimal places validation."""
        line = LineItem(
            description="Precise Item",
            quantity=Decimal("1.23"),  # Valid 2 decimal places
            unit_price=Decimal("10.00"),
            total_amount=Decimal("12.34")
        )

        # Should keep 2 decimal places
        assert line.quantity == Decimal("1.23")


class TestInvoiceHeader:
    """Test cases for InvoiceHeader model."""

    def test_complete_header(self):
        """Test validation of complete header."""
        header = InvoiceHeader(
            invoice_number="INV-2024-001",
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 14),
            subtotal_amount=Decimal("1000.00"),
            tax_amount=Decimal("80.00"),
            total_amount=Decimal("1080.00"),
            currency="USD",
            purchase_order="PO-2024-001",
            invoice_type="standard"
        )

        assert header.invoice_number == "INV-2024-001"
        assert header.currency == "USD"
        assert header.invoice_type == "standard"

    def test_currency_validation(self):
        """Test currency code validation."""
        # Valid currencies
        valid_currencies = ["USD", "EUR", "GBP", "CAD", "JPY"]
        for currency in valid_currencies:
            header = InvoiceHeader(
                invoice_date=date.today(),
                total_amount=Decimal("100.00"),
                currency=currency
            )
            assert header.currency == currency

        # Invalid currency
        with pytest.raises(ValueError, match="Unsupported currency code"):
            InvoiceHeader(
                invoice_date=date.today(),
                total_amount=Decimal("100.00"),
                currency="XYZ"
            )

    def test_date_consistency(self):
        """Test date consistency validation."""
        # Due date before invoice date should fail
        with pytest.raises(ValueError, match="Due date cannot be before invoice date"):
            InvoiceHeader(
                invoice_date=date(2024, 2, 1),
                due_date=date(2024, 1, 15),  # Before invoice date
                total_amount=Decimal("100.00")
            )

    def test_required_fields(self):
        """Test required fields validation."""
        # Only total_amount and currency are required with defaults
        header = InvoiceHeader(total_amount=Decimal("100.00"))
        assert header.total_amount == Decimal("100.00")
        assert header.currency == "USD"  # Default value


class TestConfidenceScores:
    """Test cases for ConfidenceScores model."""

    def test_complete_confidence(self):
        """Test validation of complete confidence scores."""
        confidence = ConfidenceScores(
            overall=Decimal("0.95"),
            header_fields={
                "invoice_number": Decimal("0.98"),
                "vendor_name": Decimal("0.92")
            },
            line_items=[Decimal("0.90"), Decimal("0.88"), Decimal("0.95")]
        )

        assert confidence.overall == Decimal("0.95")
        assert len(confidence.header_fields) == 2
        assert len(confidence.line_items) == 3

    def test_invalid_confidence_range(self):
        """Test confidence score range validation."""
        with pytest.raises(ValueError):
            ConfidenceScores(overall=Decimal("1.5"))  # Above 1.0

        with pytest.raises(ValueError):
            ConfidenceScores(overall=Decimal("-0.1"))  # Below 0.0

    def test_field_score_validation(self):
        """Test header field score validation."""
        # Invalid scores should be filtered out
        confidence = ConfidenceScores(
            overall=Decimal("0.8"),
            header_fields={
                "valid_field": "0.9",  # String that converts to Decimal
                "invalid_field": "not_a_number",  # Will be filtered out
                "another_valid": 0.85  # Float that converts
            }
        )

        assert len(confidence.header_fields) == 2  # One filtered out


class TestInvoiceExtraction:
    """Test cases for InvoiceExtraction model."""

    def test_complete_extraction(self):
        """Test validation of complete extraction."""
        vendor = Vendor(vendor_name="Test Vendor")
        header = InvoiceHeader(
            invoice_date=date(2024, 1, 15),
            total_amount=Decimal("100.00"),
            currency="USD"
        )
        line_items = [
            LineItem(
                description="Item 1",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                total_amount=Decimal("50.00")
            ),
            LineItem(
                description="Item 2",
                quantity=Decimal("2.00"),
                unit_price=Decimal("25.00"),
                total_amount=Decimal("50.00")
            )
        ]
        confidence = ConfidenceScores(overall=Decimal("0.9"))

        extraction = InvoiceExtraction(
            vendor=vendor,
            header=header,
            line_items=line_items,
            confidence=confidence
        )

        assert extraction.vendor.vendor_name == "Test Vendor"
        assert len(extraction.line_items) == 2
        assert extraction.confidence.overall == Decimal("0.9")

    def test_line_items_total_validation(self):
        """Test line items total against header subtotal."""
        vendor = Vendor(vendor_name="Test Vendor")
        header = InvoiceHeader(
            subtotal_amount=Decimal("90.00"),  # Different from line items total
            total_amount=Decimal("100.00"),
            currency="USD"
        )
        line_items = [
            LineItem(
                description="Item 1",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                total_amount=Decimal("50.00")
            )
        ]

        with pytest.raises(ValueError, match="Line items total.*doesn't match.*header subtotal"):
            InvoiceExtraction(
                vendor=vendor,
                header=header,
                line_items=line_items,
                confidence=ConfidenceScores(overall=Decimal("0.9"))
            )

    def test_line_number_sequence(self):
        """Test line number sequence validation."""
        vendor = Vendor(vendor_name="Test Vendor")
        header = InvoiceHeader(
            total_amount=Decimal("100.00"),
            currency="USD"
        )

        # Duplicate line numbers should fail
        line_items = [
            LineItem(
                line_number=1,
                description="Item 1",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                total_amount=Decimal("50.00")
            ),
            LineItem(
                line_number=1,  # Duplicate
                description="Item 2",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                total_amount=Decimal("50.00")
            )
        ]

        with pytest.raises(ValueError, match="Duplicate line numbers found"):
            InvoiceExtraction(
                vendor=vendor,
                header=header,
                line_items=line_items,
                confidence=ConfidenceScores(overall=Decimal("0.9"))
            )

    def test_empty_line_items(self):
        """Test validation for empty line items."""
        vendor = Vendor(vendor_name="Test Vendor")
        header = InvoiceHeader(
            total_amount=Decimal("100.00"),
            currency="USD"
        )

        with pytest.raises(ValueError, match="List should have at least 1 item"):
            InvoiceExtraction(
                vendor=vendor,
                header=header,
                line_items=[],  # Empty list
                confidence=ConfidenceScores(overall=Decimal("0.9"))
            )


class TestFieldPatch:
    """Test cases for FieldPatch model."""

    def test_complete_patch(self):
        """Test validation of complete field patch."""
        patch = FieldPatch(
            field_path="header.invoice_number",
            original_value="INV-123",
            corrected_value="INV-2024-123",
            confidence_boost=Decimal("0.15"),
            reason="Standardized format"
        )

        assert patch.field_path == "header.invoice_number"
        assert patch.confidence_boost == Decimal("0.15")

    def test_invalid_field_path(self):
        """Test field path validation."""
        # Empty field path should be fine since it's just a string
        patch = FieldPatch(
            field_path="",
            original_value="old",
            corrected_value="new"
        )
        assert patch.field_path == ""


class TestExtractionPatchResponse:
    """Test cases for ExtractionPatchResponse model."""

    def test_complete_patch_response(self):
        """Test validation of complete patch response."""
        patch1 = FieldPatch(
            field_path="vendor.vendor_name",
            original_value="ACME",
            corrected_value="Acme Corporation Inc."
        )

        response = ExtractionPatchResponse(
            patches=[patch1],
            patch_summary="Corrected vendor name format",
            overall_confidence_improvement=Decimal("0.05"),
            requires_manual_review=False
        )

        assert len(response.patches) == 1
        assert response.requires_manual_review is False

    def test_required_fields(self):
        """Test required fields validation."""
        with pytest.raises(ValueError):
            ExtractionPatchResponse()  # Missing required fields


class TestInvoiceContext:
    """Test cases for InvoiceContext model."""

    def test_complete_context(self):
        """Test validation of complete context."""
        context = InvoiceContext(
            document_type="invoice",
            business_domain="retail",
            key_entities={
                "vendor": "Acme Corp",
                "total": "$1,000.00"
            },
            document_structure=["header", "line_items", "footer"],
            confidence_context="High confidence in vendor and amounts"
        )

        assert context.document_type == "invoice"
        assert len(context.key_entities) == 2
        assert len(context.document_structure) == 3

    def test_document_type_validation(self):
        """Test document type validation."""
        valid_types = ["invoice", "receipt", "quote", "purchase_order", "credit_note"]
        for doc_type in valid_types:
            context = InvoiceContext(
                document_type=doc_type,
                confidence_context="Test"
            )
            assert context.document_type == doc_type

        # Invalid document type
        with pytest.raises(ValueError):
            InvoiceContext(
                document_type="invalid_type",
                confidence_context="Test"
            )


class TestExtractionQuality:
    """Test cases for ExtractionQuality model."""

    def test_complete_quality(self):
        """Test validation of complete quality assessment."""
        quality = ExtractionQuality(
            completeness_score=Decimal("0.85"),
            accuracy_score=Decimal("0.92"),
            confidence_score=Decimal("0.88"),
            quality_issues=["Missing tax information"],
            recommendations=["Add tax rate validation"]
        )

        assert quality.completeness_score == Decimal("0.85")
        assert len(quality.quality_issues) == 1
        assert len(quality.recommendations) == 1

    def test_score_range_validation(self):
        """Test score range validation."""
        with pytest.raises(ValueError):
            ExtractionQuality(
                completeness_score=Decimal("1.5"),  # Above 1.0
                accuracy_score=Decimal("0.8"),
                confidence_score=Decimal("0.9")
            )


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_create_extraction_from_dict_valid_data(self):
        """Test creating extraction from valid dictionary."""
        data = {
            "vendor": {"vendor_name": "Test Vendor"},
            "header": {
                "invoice_date": "2024-01-15",
                "total_amount": 100.50,
                "currency": "USD"
            },
            "line_items": [
                {
                    "description": "Test Item",
                    "quantity": 1.0,
                    "unit_price": 100.50,
                    "total_amount": 100.50
                }
            ],
            "confidence": {"overall": 0.95}
        }

        extraction = create_extraction_from_dict(data)
        assert extraction.vendor.vendor_name == "Test Vendor"
        assert extraction.header.total_amount == Decimal("100.50")
        assert len(extraction.line_items) == 1

    def test_create_extraction_from_dict_invalid_data(self):
        """Test creating extraction from invalid dictionary."""
        data = {
            "vendor": {"vendor_name": "Test Vendor"},
            "header": {
                # Missing required total_amount
                "currency": "USD"
            },
            "line_items": [],  # Empty line items
            "confidence": {"overall": 0.95}
        }

        with pytest.raises(ValueError, match="Failed to create extraction from data"):
            create_extraction_from_dict(data)

    def test_calculate_extraction_quality(self):
        """Test quality calculation for extraction."""
        vendor = Vendor(vendor_name="Test Vendor")
        header = InvoiceHeader(
            invoice_date=date(2024, 1, 15),
            total_amount=Decimal("100.00"),
            currency="USD"
        )
        line_items = [
            LineItem(
                description="Test Item",
                quantity=Decimal("1.00"),
                unit_price=Decimal("100.00"),
                total_amount=Decimal("100.00")
            )
        ]
        confidence = ConfidenceScores(overall=Decimal("0.9"))

        extraction = InvoiceExtraction(
            vendor=vendor,
            header=header,
            line_items=line_items,
            confidence=confidence
        )

        quality = calculate_extraction_quality(extraction)
        assert quality.completeness_score >= 0
        assert quality.completeness_score <= 1
        assert quality.accuracy_score == Decimal("0.9")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_maximum_values(self):
        """Test maximum allowed values."""
        # Maximum line number
        line = LineItem(
            line_number=999,
            description="Max Line Item",
            quantity=Decimal("99999999.99"),
            unit_price=Decimal("99999999.99"),
            total_amount=Decimal("999999999999.99")  # Max digits
        )
        assert line.line_number == 999

    def test_minimum_values(self):
        """Test minimum allowed values."""
        # Minimum positive values
        line = LineItem(
            line_number=1,
            description="Min Line Item",
            quantity=Decimal("0.01"),
            unit_price=Decimal("0.01"),
            total_amount=Decimal("0.01")
        )
        assert line.quantity == Decimal("0.01")

    def test_string_length_limits(self):
        """Test string length limits."""
        # Maximum description length
        long_desc = "x" * 500  # Exactly 500 characters
        line = LineItem(
            description=long_desc,
            quantity=Decimal("1.00"),
            unit_price=Decimal("10.00"),
            total_amount=Decimal("10.00")
        )
        assert len(line.description) == 500

        # Description too long should fail
        with pytest.raises(ValueError):
            LineItem(
                description="x" * 501,  # Over limit
                quantity=Decimal("1.00"),
                unit_price=Decimal("10.00"),
                total_amount=Decimal("10.00")
            )

    def test_unicode_handling(self):
        """Test Unicode character handling."""
        vendor = Vendor(
            vendor_name="Café München 国际公司",
            vendor_address=Address(
                street="北京市朝阳区",
                city="Beijing",
                country="CN"
            )
        )
        assert "国际" in vendor.vendor_name
        assert vendor.vendor_address.country == "CN"


# Integration-style tests
class TestIntegration:
    """Integration tests for complete workflows."""

    def test_realistic_invoice_extraction(self):
        """Test extraction of realistic invoice data."""
        vendor = Vendor(
            vendor_name="Global Technology Solutions Inc.",
            vendor_address=Address(
                street="1234 Innovation Drive",
                city="San Jose",
                state="CA",
                postal_code="95131",
                country="US"
            ),
            vendor_tax_id="12-3456789",
            vendor_email="accounts@globaltech.com"
        )

        header = InvoiceHeader(
            invoice_number="GT-2024-001234",
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 14),
            subtotal_amount=Decimal("5420.00"),
            tax_amount=Decimal("433.60"),
            total_amount=Decimal("5853.60"),
            currency="USD",
            purchase_order="PO-9876"
        )

        line_items = [
            LineItem(
                line_number=1,
                description="Enterprise Software License (Annual)",
                quantity=Decimal("1.00"),
                unit_price=Decimal("4800.00"),
                total_amount=Decimal("4800.00"),
                item_code="SW-ENT-001",
                gl_account="5200"
            ),
            LineItem(
                line_number=2,
                description="Technical Support Services",
                quantity=Decimal("12.00"),
                unit_price=Decimal("100.00"),
                total_amount=Decimal("1200.00"),
                item_code="SV-TS-001",
                gl_account="5400"
            ),
            LineItem(
                line_number=3,
                description="Cloud Infrastructure Credits",
                quantity=Decimal("1.00"),
                unit_price=Decimal("-200.00"),
                total_amount=Decimal("-200.00"),
                item_code="CR-CLOUD-001",
                gl_account="5600"
            ),
            LineItem(
                line_number=4,
                description="Implementation Fee (One-time)",
                quantity=Decimal("1.00"),
                unit_price=Decimal("380.00"),
                total_amount=Decimal("380.00"),
                item_code="SV-IMP-001",
                gl_account="5700"
            )
        ]

        # The line items total should match the header subtotal
        # 4800 + 1200 - 200 + 380 = 6180, but header shows 5420
        # This is a realistic scenario where there might be discrepancies
        # Let's adjust to make it consistent
        header.subtotal_amount = Decimal("6180.00")
        header.total_amount = Decimal("6180.00") + Decimal("433.60")  # 6613.60

        confidence = ConfidenceScores(
            overall=Decimal("0.89"),
            header_fields={
                "invoice_number": Decimal("0.95"),
                "vendor_name": Decimal("0.92"),
                "amounts": Decimal("0.85")
            },
            line_items=[
                Decimal("0.90"),
                Decimal("0.88"),
                Decimal("0.85"),
                Decimal("0.87")
            ]
        )

        extraction = InvoiceExtraction(
            vendor=vendor,
            header=header,
            line_items=line_items,
            confidence=confidence,
            extraction_notes=[
                "Vendor information confidently extracted",
                "Line items appear consistent with description"
            ]
        )

        # Verify the extraction is valid
        assert extraction.vendor.vendor_name == "Global Technology Solutions Inc."
        assert len(extraction.line_items) == 4
        assert extraction.confidence.overall == Decimal("0.89")

        # Calculate and check quality
        quality = calculate_extraction_quality(extraction)
        assert quality.completeness_score > Decimal("0.8")  # Should be quite complete
        assert len(quality.quality_issues) == 0  # No major issues for this data


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v", "--tb=short"])