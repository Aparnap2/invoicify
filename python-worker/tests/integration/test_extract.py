"""
Integration tests for Vision Extraction Activity (TDD - Step 4)
RED phase: Tests will fail until implementation is written
"""

import pytest
from unittest.mock import patch, Mock
import httpx

from python_worker.src.activities.extract import (
    extract_invoice_data,
    VisionAPIError,
    InvoiceExtractionResult,
)


class TestExtractInvoiceData:
    """Integration tests for invoice extraction activity."""

    @pytest.fixture
    def mockoon_url(self):
        """Mockoon endpoint URL."""
        return "http://localhost:3000/extract"

    @pytest.mark.asyncio
    async def test_extract_returns_mocked_data(self, mockoon_url):
        """RED: Test extraction returns mocked Acme Corp data from Mockoon."""
        # Arrange
        file_url = "https://example.com/invoice.pdf"

        # Act
        with patch.dict("os.environ", {"VISION_API_URL": mockoon_url}):
            result = await extract_invoice_data(file_url)

        # Assert
        assert isinstance(result, dict)
        assert result["vendor_name"] == "Acme Corporation"
        assert result["total_amount"] == 500.00
        assert result["invoice_number"] == "INV-2025-001"
        assert "due_date" in result
        assert result["currency"] == "USD"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_extract_validates_required_fields(self, mockoon_url):
        """RED: Test that extraction validates required fields."""
        # Arrange
        file_url = "https://example.com/invoice.pdf"

        # Act & Assert
        with patch.dict("os.environ", {"VISION_API_URL": mockoon_url}):
            result = await extract_invoice_data(file_url)

            # Verify all required fields exist
            assert "vendor_name" in result
            assert "total_amount" in result
            assert "invoice_number" in result
            assert isinstance(result["total_amount"], (int, float))
            assert result["total_amount"] > 0

    @pytest.mark.asyncio
    async def test_extract_raises_vision_api_error_on_500(self, mockoon_url):
        """RED: Test that 500 error raises VisionAPIError."""
        # Arrange
        file_url = "https://example.com/invoice.pdf"

        # Mock a 500 response
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            with patch.dict("os.environ", {"VISION_API_URL": mockoon_url}):
                # Act & Assert
                with pytest.raises(VisionAPIError) as exc_info:
                    await extract_invoice_data(file_url)

                assert "500" in str(exc_info.value) or "Vision API" in str(
                    exc_info.value
                )

    @pytest.mark.asyncio
    async def test_extract_raises_vision_api_error_on_network_fail(self):
        """RED: Test that network failure raises VisionAPIError."""
        # Arrange
        file_url = "https://example.com/invoice.pdf"
        bad_url = "http://invalid-host:9999/extract"

        # Act & Assert
        with patch.dict("os.environ", {"VISION_API_URL": bad_url}):
            with pytest.raises(VisionAPIError):
                await extract_invoice_data(file_url)

    @pytest.mark.asyncio
    async def test_extract_uses_default_url_when_env_not_set(self):
        """RED: Test default URL is used when VISION_API_URL not set."""
        # Arrange
        file_url = "https://example.com/invoice.pdf"

        with patch.dict("os.environ", {}, clear=True):
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "vendor_name": "Test",
                    "total_amount": 100.0,
                    "invoice_number": "INV-001",
                    "due_date": "2025-01-01",
                    "currency": "USD",
                    "confidence": 0.9,
                }
                mock_post.return_value = mock_response

                # Act
                await extract_invoice_data(file_url)

                # Assert - Check it used default URL
                call_args = mock_post.call_args
                assert "localhost:3000" in str(call_args)

    def test_invoice_extraction_result_schema(self):
        """RED: Test Pydantic schema validation."""
        # Arrange & Act
        result = InvoiceExtractionResult(
            vendor_name="Test Corp",
            total_amount=1000.00,
            invoice_number="INV-001",
            due_date="2025-01-01",
            currency="USD",
            confidence=0.95,
        )

        # Assert
        assert result.vendor_name == "Test Corp"
        assert result.total_amount == 1000.00
        assert result.confidence >= 0.0 and result.confidence <= 1.0
