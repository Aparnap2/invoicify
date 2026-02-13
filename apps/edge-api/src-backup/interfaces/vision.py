"""
Vision Adapter Interface
Defines the contract for document extraction adapters.
Following Hexagonal Architecture - Domain logic depends on this interface,
not on specific implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class VisionAdapter(ABC):
    """
    Abstract base class for vision/document extraction adapters.

    Implementations:
    - DoclingAdapter: Local extraction with structured Markdown output (default)
    - WatsonAdapter: IBM Watson Discovery for enterprise
    - GroqAdapter: Groq Cloud Vision API
    """

    @abstractmethod
    async def extract_invoice_data(self, file_path_or_url: str) -> Dict[str, Any]:
        """
        Extract structured data from an invoice document.

        Args:
            file_path_or_url: Path to local file or URL to remote document

        Returns:
            Dict containing:
            - raw_text: Structured content (Markdown for Docling)
            - format: Content format (markdown, json, text)
            - tables_detected: Number of tables found
            - confidence: Extraction confidence score
            - metadata: Additional document metadata
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the vision service is healthy and available."""
        pass
