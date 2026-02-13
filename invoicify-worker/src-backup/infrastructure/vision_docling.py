"""
Docling Vision Adapter
IBM Research's document understanding library for structured extraction.
Converts invoices to Markdown with preserved table structures.
"""

import logging
from typing import Any, Dict
from pathlib import Path
import tempfile
import httpx

from src.interfaces import VisionAdapter

logger = logging.getLogger(__name__)


class DoclingAdapter(VisionAdapter):
    """
    IBM Docling adapter for document extraction.

    Features:
    - Converts PDFs, images, Word docs to structured Markdown
    - Preserves table structures (line items, totals)
    - Local processing (no cloud dependency)
    - Perfect for invoices with tabular data

    Example output format:
    ```markdown
    # Invoice

    | Item | Qty | Price | Total |
    |------|-----|-------|-------|
    | Consulting | 10 | $150 | $1,500 |
    ```
    """

    def __init__(self):
        self.converter = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazy initialization of Docling converter."""
        if not self._initialized:
            try:
                from docling.document_converter import DocumentConverter

                self.converter = DocumentConverter()
                self._initialized = True
                logger.info("✅ Docling converter initialized")
            except ImportError as e:
                logger.error(f"Failed to import Docling: {e}")
                raise RuntimeError(
                    "Docling not installed. Run: uv pip install docling"
                ) from e

    async def extract_invoice_data(self, file_path_or_url: str) -> Dict[str, Any]:
        """
        Extract invoice data using Docling.

        Args:
            file_path_or_url: Local file path or URL to document

        Returns:
            Dict with structured extraction results
        """
        await self._ensure_initialized()

        # Handle URLs by downloading to temp file
        local_path = await self._get_local_path(file_path_or_url)

        try:
            # Convert document to structured format
            result = self.converter.convert(local_path)

            # Export to Markdown (perfect for LLM consumption)
            markdown_content = result.document.export_to_markdown()

            # Count tables (line items are usually tables)
            tables_detected = (
                len(result.document.tables) if hasattr(result.document, "tables") else 0
            )

            # Calculate confidence based on text extraction quality
            confidence = self._calculate_confidence(result.document)

            logger.info(
                f"📄 Docling extracted {tables_detected} tables from {local_path}"
            )

            return {
                "raw_text": markdown_content,
                "format": "markdown",
                "tables_detected": tables_detected,
                "confidence": confidence,
                "metadata": {
                    "source": file_path_or_url,
                    "pages": len(result.document.pages)
                    if hasattr(result.document, "pages")
                    else 1,
                    "docling_version": "2.x",
                },
            }

        except Exception as e:
            logger.error(f"Docling extraction failed: {e}")
            raise VisionExtractionError(f"Failed to extract document: {e}") from e

        finally:
            # Cleanup temp files if downloaded from URL
            if local_path != file_path_or_url and Path(local_path).exists():
                try:
                    Path(local_path).unlink()
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")

    async def _get_local_path(self, file_path_or_url: str) -> str:
        """
        Get local file path, downloading if URL provided.

        Args:
            file_path_or_url: Path or URL

        Returns:
            Local file path
        """
        # Security: Reject dangerous URL schemes (file://, ftp://, etc.)
        if "://" in file_path_or_url and not file_path_or_url.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                f"Invalid URL scheme. Only HTTP/HTTPS allowed: {file_path_or_url}"
            )

        # Check if it's a URL
        if file_path_or_url.startswith(("http://", "https://")):
            return await self._download_file(file_path_or_url)

        # Local file - verify exists
        if not Path(file_path_or_url).exists():
            raise FileNotFoundError(f"File not found: {file_path_or_url}")

        return file_path_or_url

    async def _download_file(self, url: str) -> str:
        """
        Download file from URL to temporary location.

        Args:
            url: File URL

        Returns:
            Path to downloaded file
        """
        # Validate URL scheme (prevent SSRF)
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme. Only HTTP/HTTPS allowed: {url}")

        timeout = float(__import__("os").getenv("VISION_DOWNLOAD_TIMEOUT", "30.0"))

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()

                # Create temp file with appropriate extension
                content_type = response.headers.get("content-type", "")
                ext = self._get_extension_from_content_type(content_type)

                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                    tmp_file.write(response.content)
                    return tmp_file.name

            except httpx.HTTPError as e:
                logger.error(f"Failed to download file from {url}: {e}")
                raise VisionExtractionError(f"Download failed: {e}") from e

    def _get_extension_from_content_type(self, content_type: str) -> str:
        """Map content type to file extension."""
        content_type = content_type.lower()
        if "pdf" in content_type:
            return ".pdf"
        elif "png" in content_type:
            return ".png"
        elif "jpeg" in content_type or "jpg" in content_type:
            return ".jpg"
        elif "tiff" in content_type:
            return ".tiff"
        elif "word" in content_type or "docx" in content_type:
            return ".docx"
        return ".bin"

    def _calculate_confidence(self, document) -> float:
        """
        Calculate extraction confidence score.

        Args:
            document: Docling document object

        Returns:
            Confidence score (0.0 to 1.0)
        """
        # Simple heuristic: more text = higher confidence
        # In production, could use more sophisticated metrics
        try:
            text_length = len(document.export_to_markdown())
            # Normalize: 1000+ chars = high confidence
            confidence = min(1.0, text_length / 1000.0)
            return round(confidence, 2)
        except Exception:
            return 0.5  # Default medium confidence

    async def health_check(self) -> bool:
        """Check if Docling is available."""
        try:
            await self._ensure_initialized()
            return self._initialized
        except Exception as e:
            logger.error(f"Docling health check failed: {e}")
            return False


class VisionExtractionError(Exception):
    """Custom exception for vision extraction failures."""

    pass
