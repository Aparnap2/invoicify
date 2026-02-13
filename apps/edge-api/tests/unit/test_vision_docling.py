"""
TDD Tests for Docling Vision Adapter
Tests the IBM Docling integration for document extraction.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import tempfile

from src.infrastructure.vision_docling import DoclingAdapter, VisionExtractionError


class TestDoclingAdapter:
    """Test suite for Docling vision adapter."""

    @pytest.fixture
    def adapter(self):
        """Create Docling adapter instance."""
        return DoclingAdapter()

    @pytest.mark.asyncio
    async def test_adapter_initializes_docling_converter(self, adapter):
        """Test that adapter initializes Docling converter on first use."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            tmp_path = tmp.name

        try:
            with patch.object(
                adapter, "_ensure_initialized", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = None
                adapter._initialized = True

                # Create mock document with all needed attributes
                mock_doc = Mock()
                mock_doc.export_to_markdown.return_value = "# Test Invoice"
                mock_doc.tables = []
                mock_doc.pages = [Mock(), Mock()]  # List for len()

                mock_result = Mock()
                mock_result.document = mock_doc

                adapter.converter = Mock()
                adapter.converter.convert.return_value = mock_result

                await adapter.extract_invoice_data(tmp_path)

                mock_init.assert_called_once()
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_extract_invoice_data_returns_markdown_format(self, adapter):
        """Test that extraction returns Markdown format."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            tmp_path = tmp.name

        try:
            mock_document = Mock()
            mock_document.export_to_markdown.return_value = """
# Invoice

**Vendor:** Acme Corp
**Amount:** $1,500.00

| Item | Qty | Price | Total |
|------|-----|-------|-------|
| Consulting | 10 | $150 | $1,500 |
"""
            mock_document.tables = [Mock(), Mock()]  # 2 tables detected
            mock_document.pages = [Mock()]

            mock_result = Mock()
            mock_result.document = mock_document

            adapter.converter = Mock()
            adapter.converter.convert = Mock(return_value=mock_result)
            adapter._initialized = True

            result = await adapter.extract_invoice_data(tmp_path)

            assert result["format"] == "markdown"
            assert "raw_text" in result
            assert "| Item | Qty |" in result["raw_text"]  # Table preserved
            assert result["tables_detected"] == 2
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_extract_handles_local_file(self, adapter):
        """Test extraction from local file path."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake pdf content")
            tmp_path = tmp.name

        try:
            mock_document = Mock()
            mock_document.export_to_markdown.return_value = "# Test"
            mock_document.tables = []
            mock_document.pages = [Mock()]  # List for len()

            mock_result = Mock()
            mock_result.document = mock_document

            adapter.converter = Mock()
            adapter.converter.convert = Mock(return_value=mock_result)
            adapter._initialized = True

            result = await adapter.extract_invoice_data(tmp_path)

            assert result is not None
            adapter.converter.convert.assert_called_once()
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_extract_downloads_url_to_temp_file(self, adapter):
        """Test that URLs are downloaded to temp files."""
        mock_response = Mock()
        mock_response.content = b"fake pdf content"
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        mock_document = Mock()
        mock_document.export_to_markdown.return_value = "# Downloaded Invoice"
        mock_document.tables = []
        mock_document.pages = [Mock()]  # List for len()

        mock_result = Mock()
        mock_result.document = mock_document

        adapter.converter = Mock()
        adapter.converter.convert = Mock(return_value=mock_result)
        adapter._initialized = True

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client.return_value
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            result = await adapter.extract_invoice_data(
                "https://example.com/invoice.pdf"
            )

            assert result["raw_text"] == "# Downloaded Invoice"
            mock_client.return_value.get.assert_called_once_with(
                "https://example.com/invoice.pdf", follow_redirects=True
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            result = await adapter.extract_invoice_data(
                "https://example.com/invoice.pdf"
            )

            assert result["raw_text"] == "# Downloaded Invoice"
            mock_client.return_value.get.assert_called_once_with(
                "https://example.com/invoice.pdf", follow_redirects=True
            )

    @pytest.mark.asyncio
    async def test_extract_rejects_non_http_urls(self, adapter):
        """Test that non-HTTP(S) URLs are rejected for security."""
        adapter._initialized = True

        with pytest.raises(ValueError, match="Invalid URL scheme"):
            await adapter.extract_invoice_data("file:///etc/passwd")

        with pytest.raises(ValueError, match="Invalid URL scheme"):
            await adapter.extract_invoice_data("ftp://example.com/file.pdf")

    @pytest.mark.asyncio
    async def test_extract_raises_error_on_failure(self, adapter):
        """Test that extraction failures raise VisionExtractionError."""
        adapter.converter = Mock()
        adapter.converter.convert = Mock(side_effect=Exception("Docling failed"))
        adapter._initialized = True

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"fake content")
            tmp_path = tmp.name

        try:
            with pytest.raises(VisionExtractionError, match="Failed to extract"):
                await adapter.extract_invoice_data(tmp_path)
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_calculate_confidence_returns_normalized_score(self, adapter):
        """Test confidence calculation based on text length."""
        mock_document = Mock()
        mock_document.export_to_markdown.return_value = "x" * 2000  # Long text

        confidence = adapter._calculate_confidence(mock_document)

        assert 0.0 <= confidence <= 1.0
        assert confidence >= 0.9  # Long text = high confidence

    @pytest.mark.asyncio
    async def test_calculate_confidence_returns_default_on_error(self, adapter):
        """Test that confidence defaults to 0.5 on calculation error."""
        mock_document = Mock()
        mock_document.export_to_markdown = Mock(side_effect=Exception("Export failed"))

        confidence = adapter._calculate_confidence(mock_document)

        assert confidence == 0.5

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_initialized(self, adapter):
        """Test health check passes when Docling is initialized."""
        adapter._initialized = True
        adapter.converter = Mock()

        result = await adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self, adapter):
        """Test health check fails when Docling can't initialize."""
        with patch.object(
            adapter, "_ensure_initialized", side_effect=Exception("Import failed")
        ):
            result = await adapter.health_check()

            assert result is False


class TestDoclingAdapterFactory:
    """Test factory integration for Docling adapter."""

    def test_factory_returns_docling_by_default(self):
        """Test that factory returns DoclingAdapter when VISION_MODE not set."""
        with patch.dict("os.environ", {}, clear=True):
            from src.config.factory import get_vision_adapter

            # Should not raise - Docling is default
            adapter = get_vision_adapter()

            assert adapter is not None

    def test_factory_returns_docling_when_explicitly_set(self):
        """Test that factory returns DoclingAdapter when VISION_MODE=docling."""
        with patch.dict("os.environ", {"VISION_MODE": "docling"}, clear=True):
            from src.config.factory import get_vision_adapter

            adapter = get_vision_adapter()

            assert adapter is not None

    def test_factory_raises_for_unimplemented_watson(self):
        """Test that factory raises NotImplementedError for Watson."""
        with patch.dict("os.environ", {"VISION_MODE": "watson"}, clear=True):
            from src.config.factory import get_vision_adapter

            with pytest.raises(NotImplementedError, match="Watson"):
                get_vision_adapter()

    def test_factory_raises_for_unimplemented_groq(self):
        """Test that factory raises NotImplementedError for Groq."""
        with patch.dict("os.environ", {"VISION_MODE": "groq"}, clear=True):
            from src.config.factory import get_vision_adapter

            with pytest.raises(NotImplementedError, match="Groq"):
                get_vision_adapter()
