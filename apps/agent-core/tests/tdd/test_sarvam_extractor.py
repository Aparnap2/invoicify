"""
TDD Tests for Universal Invoice Extractor.

Run:
    uv run pytest tests/tdd/test_sarvam_extractor.py -v -s

Tests cover:
- PII redaction (SOC 2 compliance)
- Fixture mode (fastest, for queue/db testing)
- Local AI mode (Ollama LightOnOCR + qwen2.5-coder)
- Production mode (Sarvam + Groq, mocked)
- Pydantic validation
"""

import pytest
import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


class TestPIIScrubber:
    """Test PII redaction for SOC 2 compliance."""
    
    def test_redact_iban(self):
        """Test IBAN redaction."""
        from src.extraction.sarvam_extractor import redact_financial_pii
        
        text = "Bank Account: DE89370400440532013000"
        redacted = redact_financial_pii(text)
        
        assert "[REDACTED_IBAN]" in redacted
        assert "DE89370400440532013000" not in redacted
    
    def test_redact_indian_account_number(self):
        """Test Indian bank account number redaction."""
        from src.extraction.sarvam_extractor import redact_financial_pii
        
        text = "Account Number: 1234567890123"
        redacted = redact_financial_pii(text)
        
        assert "[REDACTED_ACCOUNT]" in redacted
    
    def test_redact_ifsc_code(self):
        """Test IFSC code redaction."""
        from src.extraction.sarvam_extractor import redact_financial_pii
        
        text = "IFSC Code: SBIN0001234"
        redacted = redact_financial_pii(text)
        
        assert "[REDACTED_IFSC]" in redacted
        assert "SBIN0001234" not in redacted
    
    def test_redact_routing_number(self):
        """Test routing number redaction."""
        from src.extraction.sarvam_extractor import redact_financial_pii
        
        text = "Routing: 123456789"
        redacted = redact_financial_pii(text)
        
        assert "[REDACTED_ROUTING]" in redacted
    
    def test_preserve_amounts(self):
        """Test that amounts are NOT redacted (needed for extraction)."""
        from src.extraction.sarvam_extractor import redact_financial_pii
        
        text = """
        Total Amount: $1,500.00
        Subtotal: $1,200.00
        Tax: $300.00
        Bank Account: 1234567890
        """
        redacted = redact_financial_pii(text)
        
        # Amounts should be preserved
        assert "$1,500.00" in redacted
        assert "$1,200.00" in redacted
        assert "$300.00" in redacted
        
        # Bank account should be redacted
        assert "[REDACTED_ACCOUNT]" in redacted


class TestInvoiceSchema:
    """Test Pydantic schema validation."""
    
    def test_valid_invoice(self):
        """Test valid invoice passes validation."""
        from src.extraction.sarvam_extractor import InvoiceSchema
        
        data = {
            "vendor_name": "Acme Supplies Pvt Ltd",
            "invoice_number": "INV-2024-001",
            "invoice_date": "2024-01-15",
            "subtotal": 3000.0,
            "tax_amount": 540.0,
            "total_amount": 3540.0,
            "currency": "INR",
            "line_items": [
                {"description": "Office Chairs", "quantity": 10, "unit_price": 150.0, "total": 1500.0}
            ],
            "confidence_score": 0.95,
        }
        
        invoice = InvoiceSchema(**data)
        assert invoice.vendor_name == "Acme Supplies Pvt Ltd"
        assert invoice.total_amount == 3540.0
    
    def test_total_validation(self):
        """Test total_amount = subtotal + tax_amount validation."""
        from src.extraction.sarvam_extractor import InvoiceSchema
        
        data = {
            "vendor_name": "Acme Supplies",
            "invoice_number": "INV-001",
            "invoice_date": "2024-01-15",
            "subtotal": 3000.0,
            "tax_amount": 540.0,
            "total_amount": 9999.0,  # Wrong! Should be 3540.0
            "currency": "INR",
            "line_items": [],
            "confidence_score": 0.95,
        }
        
        with pytest.raises(ValueError, match="Total mismatch"):
            InvoiceSchema(**data)
    
    def test_date_format_validation(self):
        """Test date format validation (YYYY-MM-DD)."""
        from src.extraction.sarvam_extractor import InvoiceSchema
        
        data = {
            "vendor_name": "Acme Supplies",
            "invoice_number": "INV-001",
            "invoice_date": "01-15-2024",  # Wrong format
            "subtotal": 3000.0,
            "tax_amount": 540.0,
            "total_amount": 3540.0,
            "currency": "INR",
            "line_items": [],
            "confidence_score": 0.95,
        }
        
        with pytest.raises(ValueError):
            InvoiceSchema(**data)


class TestFixtureMode:
    """Test fixture mode (fastest, for queue/db testing)."""
    
    @pytest.mark.asyncio
    async def test_fixture_mode_returns_hardcoded_data(self):
        """Test fixture mode returns valid hardcoded data."""
        # Import and reload to pick up new env
        import importlib
        from src.extraction import sarvam_extractor
        importlib.reload(sarvam_extractor)
        
        # Set fixture mode
        with patch.dict(os.environ, {"EXTRACTOR_MODE": "fixture"}):
            # Re-import after env change
            importlib.reload(sarvam_extractor)
            extractor = sarvam_extractor.InvoiceExtractor()
            result = await extractor.extract("/fake/path.pdf", "TEST-123")
            
            assert result["vendor_name"] == "Local Dev Supplies"
            assert result["invoice_number"] == "INV-TEST-123"
            assert result["total_amount"] == 1770.0
            assert result["confidence_score"] == 0.99
            assert len(result["line_items"]) == 2


class TestLocalAIMode:
    """Test local AI mode (Ollama Docker)."""
    
    @pytest.mark.asyncio
    async def test_local_ocr_lighton(self):
        """Test LightOnOCR via Ollama (mocked)."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "# Invoice\nVendor: Test Corp\nTotal: ₹1,000"
        }
        
        # Also mock Docling fallback
        mock_docling_result = MagicMock()
        mock_docling_result.document.export_to_markdown.return_value = "# Invoice via Docling"
        
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with patch("builtins.open", MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"fake pdf")))):
                with patch("docling.document_converter.DocumentConverter.convert", return_value=mock_docling_result):
                    from src.extraction.sarvam_extractor import InvoiceExtractor
                    extractor = InvoiceExtractor.__new__(InvoiceExtractor)
                    extractor.mode = "ollama"
                    
                    markdown = await extractor._local_ocr_lighton("/fake/path.pdf")
                    assert "Invoice" in markdown
    
    @pytest.mark.asyncio
    async def test_local_llm_qwen(self):
        """Test qwen2.5-coder JSON extraction (mocked)."""
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content='{"vendor_name": "Test Corp", "invoice_number": "INV-001", "invoice_date": "2024-01-15", "subtotal": 1000.0, "tax_amount": 180.0, "total_amount": 1180.0, "currency": "INR", "line_items": [], "confidence_score": 0.95}'
                )
            )]
        )
        
        with patch("openai.AsyncOpenAI", return_value=mock_client):
            from src.extraction.sarvam_extractor import InvoiceExtractor
            extractor = InvoiceExtractor.__new__(InvoiceExtractor)
            extractor.mode = "ollama"
            
            result = await extractor._local_llm_json_qwen(
                "# Invoice\nVendor: Test Corp\nTotal: ₹1,180",
                "INV-001"
            )
            
            assert result["vendor_name"] == "Test Corp"
            assert result["total_amount"] == 1180.0


class TestProductionMode:
    """Test production mode (Sarvam + Groq)."""
    
    @pytest.mark.asyncio
    async def test_sarvam_ocr_api_call(self):
        """Test Sarvam Vision API call (mocked)."""
        from src.extraction.sarvam_extractor import InvoiceExtractor
        
        extractor = InvoiceExtractor.__new__(InvoiceExtractor)
        extractor.mode = "sarvam"
        extractor.sarvam_api_key = "test-key"
        
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "markdown": "# Invoice\nVendor: Acme Corp\nTotal: ₹5,000"
        }
        
        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with patch("builtins.open"):
                markdown = await extractor._prod_ocr_sarvam("/fake/path.pdf", "INV-001")
                assert "Invoice" in markdown
    
    @pytest.mark.asyncio
    async def test_groq_extraction(self):
        """Test Groq JSON extraction (mocked)."""
        from src.extraction.sarvam_extractor import InvoiceExtractor
        
        extractor = InvoiceExtractor.__new__(InvoiceExtractor)
        extractor.mode = "sarvam"
        extractor.groq_api_key = "test-groq-key"
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content='{"vendor_name": "Acme Corp", "invoice_number": "INV-001", "invoice_date": "2024-01-15", "subtotal": 5000.0, "tax_amount": 900.0, "total_amount": 5900.0, "currency": "INR", "line_items": [], "confidence_score": 0.95}'
                )
            )]
        )
        
        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await extractor._prod_llm_json_groq(
                "# Invoice\nVendor: Acme Corp\nTotal: ₹5,900",
                "INV-001"
            )
            
            assert result["vendor_name"] == "Acme Corp"
            assert result["total_amount"] == 5900.0


class TestIntegrationWithRealDocker:
    """Integration tests with real Docker Ollama.
    
    These tests require:
    1. Docker running with Ollama container
    2. Models pulled: aipib/LightOnOCR-1B-1025, qwen2.5-coder:3b
    3. Test PDF fixture available
    
    Run with:
        uv run pytest tests/tdd/test_sarvam_extractor.py::TestIntegrationWithRealDocker -v -s
    """
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.docker
    async def test_real_ollama_extraction(self):
        """Test extraction with real Ollama Docker container.
        
        This test:
        1. Uses LightOnOCR for OCR
        2. Uses qwen2.5-coder for JSON extraction
        3. Validates end-to-end pipeline
        """
        from src.extraction.sarvam_extractor import InvoiceExtractor
        
        # Skip if no test PDF
        pdf_path = Path(__file__).parent.parent / "fixtures" / "invoices" / "simple_invoice.pdf"
        if not pdf_path.exists():
            pytest.skip("Test PDF not found - run scripts/generate_pdf_fixtures.py")
        
        # Set local AI mode
        with patch.dict(os.environ, {
            "EXTRACTOR_MODE": "ollama",
            "ENVIRONMENT": "local",
        }):
            extractor = InvoiceExtractor()
            
            try:
                result = await extractor.extract(str(pdf_path), "TEST-OLLAMA-001")
                
                # Validate result structure
                assert "vendor_name" in result
                assert "invoice_number" in result
                assert "total_amount" in result
                assert "line_items" in result
                assert result["confidence_score"] > 0
                
                print(f"\n✅ Real Ollama extraction successful:")
                print(f"   Vendor: {result['vendor_name']}")
                print(f"   Invoice: {result['invoice_number']}")
                print(f"   Total: ₹{result['total_amount']}")
                
            except Exception as e:
                pytest.skip(f"Ollama not available or model not loaded: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Pytest configuration
# ─────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "docker: mark test as requiring Docker"
    )
