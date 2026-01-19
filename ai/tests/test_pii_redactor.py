"""
Test suite for PII Redaction Service (TDD)

Run with: pytest tests/test_pii_redactor.py -v

Tests for the Microsoft Presidio-based PII detection and redaction.
"""

import pytest
from typing import Optional


class TestPIIRedactorImports:
    """Test that required dependencies are available."""

    def test_pydantic_available(self):
        """Pydantic should be available for data modeling."""
        from pydantic import BaseModel
        assert BaseModel is not None

    def test_re_module_available(self):
        """Regular expression module for pattern-based detection."""
        import re
        assert re is not None


class TestPIIRedactorBasic:
    """Basic tests for PIIRedactor class."""

    def test_redactor_initialization(self):
        """Test that redactor can be initialized."""
        from app.services.pii_redactor import PIIRedactor
        redactor = PIIRedactor()
        assert redactor is not None

    def test_redactor_with_custom_patterns(self):
        """Test initialization with custom PII patterns."""
        from app.services.pii_redactor import PIIRedactor

        custom_patterns = [
            {
                "name": "CUSTOM_ID",
                "pattern": r"CUSTOM-\d{4}",
                "score": 0.9
            }
        ]
        redactor = PIIRedactor(custom_patterns=custom_patterns)
        assert redactor is not None


class TestPIIRedactionPatterns:
    """Tests for specific PII pattern detection and redaction."""

    def test_detect_ssn(self):
        """Test SSN detection and redaction."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Employee SSN: 123-45-6789"
        result = redactor.redact(text)

        assert result is not None
        # SSN should be redacted
        assert "123-45-6789" not in result.redacted_text
        assert result.findings  # Should have detected something

    def test_detect_credit_card(self):
        """Test credit card detection and redaction."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Card number: 4532-1234-5678-9012"
        result = redactor.redact(text)

        assert result is not None
        assert "4532-1234-5678-9012" not in result.redacted_text

    def test_detect_email(self):
        """Test email address detection and redaction."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Contact: john.doe@example.com"
        result = redactor.redact(text)

        assert result is not None
        assert "john.doe@example.com" not in result.redacted_text

    def test_detect_phone(self):
        """Test phone number detection and redaction."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Phone: (555) 123-4567"
        result = redactor.redact(text)

        assert result is not None
        assert "(555) 123-4567" not in result.redacted_text

    def test_detect_multiple_pii_types(self):
        """Test detection of multiple PII types in same text."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = """
        Name: John Doe
        Email: john@example.com
        Phone: 555-123-4567
        SSN: 123-45-6789
        Credit Card: 4532-1234-5678-9012
        """
        result = redactor.redact(text)

        assert result is not None
        # All PII should be redacted
        assert "john@example.com" not in result.redacted_text
        assert "555-123-4567" not in result.redacted_text
        assert "123-45-6789" not in result.redacted_text
        assert "4532-1234-5678-9012" not in result.redacted_text

    def test_preserve_non_pii_text(self):
        """Test that non-PII text is preserved."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Invoice #12345 from Acme Corp for $500.00"
        result = redactor.redact(text)

        assert result is not None
        # Non-PII should be preserved
        assert "Invoice #12345" in result.redacted_text
        assert "Acme Corp" in result.redacted_text
        assert "$500.00" in result.redacted_text


class TestPIIRedactionModes:
    """Tests for different redaction modes."""

    def test_mask_mode(self):
        """Test masking redaction mode."""
        from app.services.pii_redactor import PIIRedactor, RedactionMode

        redactor = PIIRedactor(mode=RedactionMode.MASK)
        text = "Email: test@example.com"
        result = redactor.redact(text)

        assert result is not None
        # Should have masked the email
        assert "*" in result.redacted_text or result.redacted_text != text

    def test_replace_mode(self):
        """Test replacement redaction mode."""
        from app.services.pii_redactor import PIIRedactor, RedactionMode

        redactor = PIIRedactor(mode=RedactionMode.REPLACE)
        text = "Phone: 555-123-4567"
        result = redactor.redact(text)

        assert result is not None
        assert "[REDACTED]" in result.redacted_text or "555-123-4567" not in result.redacted_text

    def test_hash_mode(self):
        """Test hashing redaction mode."""
        from app.services.pii_redactor import PIIRedactor, RedactionMode

        redactor = PIIRedactor(mode=RedactionMode.HASH)
        text = "SSN: 123-45-6789"
        result = redactor.redact(text)

        assert result is not None
        assert "123-45-6789" not in result.redacted_text


class TestPIIRedactionInvoice:
    """Tests for invoice-specific PII redaction."""

    def test_redact_invoice_with_pii(self):
        """Test redacting PII from invoice text."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        invoice_text = """
        INVOICE

        Bill To:
        John Doe
        123 Main Street
        Anytown, USA 12345
        Email: john.doe@personal.com
        Phone: 555-123-4567

        Account: 987654321
        Routing: 021000021

        Total: $1,234.56
        """

        result = redactor.redact(invoice_text)

        assert result is not None
        # Personal info should be redacted
        assert "john.doe@personal.com" not in result.redacted_text
        assert "555-123-4567" not in result.redacted_text
        # Business content should be preserved
        assert "INVOICE" in result.redacted_text
        assert "$1,234.56" in result.redacted_text

    def test_redact_bank_account_info(self):
        """Test redacting bank account and routing numbers."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Bank Account: 1234567890, Routing: 021000089"
        result = redactor.redact(text)

        assert result is not None
        # Financial info should be redacted
        assert "1234567890" not in result.redacted_text or "021000089" not in result.redacted_text


class TestPIIRedactionResults:
    """Tests for the PII redaction result object."""

    def test_result_contains_findings(self):
        """Test that results include detected PII locations."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Email: test@example.com"
        result = redactor.redact(text)

        assert result is not None
        assert isinstance(result.findings, list)
        assert len(result.findings) >= 1

        finding = result.findings[0]
        assert finding.entity_type  # Should have entity type
        assert finding.start >= 0  # Should have start position
        assert finding.end > finding.start  # Should have end position

    def test_result_metadata(self):
        """Test that results include metadata."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Phone: 555-123-4567"
        result = redactor.redact(text)

        assert result is not None
        assert hasattr(result, 'original_text')
        assert hasattr(result, 'redacted_text')
        assert result.original_text == text


class TestPIIRedactionEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_text(self):
        """Test handling of empty text."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        result = redactor.redact("")

        assert result is not None
        assert result.redacted_text == ""

    def test_no_pii_text(self):
        """Test handling of text with no PII."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        text = "Invoice #12345 for services rendered"
        result = redactor.redact(text)

        assert result is not None
        assert result.findings == []
        assert result.redacted_text == text

    def test_none_input(self):
        """Test handling of None input - returns empty result gracefully."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        # None is handled gracefully, returning empty result
        result = redactor.redact(None)  # type: ignore

        # Should return empty result, not raise
        assert result.redacted_text == "" or result.redacted_text is None
        assert result.findings == []


class TestPIISpecificPatterns:
    """Tests for specific PII pattern configurations."""

    def test_us_ssn_pattern(self):
        """Test US Social Security Number pattern."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        test_cases = [
            "123-45-6789",
            "123 45 6789",
            "123456789",
        ]

        for ssn in test_cases:
            result = redactor.redact(f"SSN: {ssn}")
            assert ssn not in result.redacted_text, f"Failed to redact {ssn}"

    def test_email_patterns(self):
        """Test various email patterns."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        test_cases = [
            "user@domain.com",
            "user.name@domain.co.uk",
            "user+tag@domain.org",
        ]

        for email in test_cases:
            result = redactor.redact(f"Email: {email}")
            assert email not in result.redacted_text, f"Failed to redact {email}"

    def test_phone_patterns(self):
        """Test various phone number patterns."""
        from app.services.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        test_cases = [
            "(555) 123-4567",
            "555-123-4567",
            "555.123.4567",
            "+1 555 123 4567",
        ]

        for phone in test_cases:
            result = redactor.redact(f"Phone: {phone}")
            assert phone not in result.redacted_text, f"Failed to redact {phone}"
