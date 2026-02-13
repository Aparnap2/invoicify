"""
Vision Extraction Activity Implementation (TDD - Step 4)
Fixed: CodeRabbit review issues - Pydantic v2, validation, error handling
"""

import os
import logging
from typing import Dict, Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator
from temporalio import activity

logger = logging.getLogger(__name__)


class VisionAPIError(Exception):
    """Custom exception for Vision API errors."""

    pass


class InvoiceExtractionResult(BaseModel):
    """Pydantic schema for invoice extraction results."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "vendor_name": "Acme Corp",
                "total_amount": 500.00,
                "invoice_number": "INV-2025-001",
                "due_date": "2025-01-01",
                "currency": "USD",
                "confidence": 0.95,
            }
        }
    }

    vendor_name: str = Field(..., description="Vendor name")
    total_amount: float = Field(..., gt=0, description="Invoice total amount")
    invoice_number: str = Field(..., description="Invoice number")
    due_date: str = Field(..., description="Due date (ISO format)")
    currency: str = Field(default="USD", description="Currency code")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Extraction confidence"
    )

    @field_validator("total_amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        """Validate amount is positive."""
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v


def _is_valid_url(url: str) -> bool:
    """Check if string is a valid URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


@activity.defn
async def extract_invoice_data(file_url: str) -> Dict[str, Any]:
    """
    Extract invoice data from file URL using Vision API.

    In TEST mode, calls Mockoon at localhost:3000/extract.
    In PROD mode, calls Groq Vision API.

    Args:
        file_url: URL to invoice file (PDF, image)

    Returns:
        Dictionary with extracted invoice data

    Raises:
        ValueError: If file_url is not a valid URL
        VisionAPIError: If API call fails or returns error
    """
    # Validate URL format
    if not _is_valid_url(file_url):
        raise ValueError(f"Invalid URL format: {file_url}")

    # Get API URL from environment or use default (Mockoon)
    api_url = os.getenv("VISION_API_URL", "http://localhost:3000/extract")

    # Validate API URL
    if not _is_valid_url(api_url):
        raise ValueError(f"Invalid VISION_API_URL: {api_url}")

    logger.info(f"Extracting invoice from: {file_url} using API: {api_url}")

    timeout = float(os.getenv("VISION_API_TIMEOUT", "30.0"))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                api_url,
                json={"url": file_url},
                headers={"Content-Type": "application/json"},
            )

            # Check for HTTP errors
            if response.status_code >= 500:
                error_msg = (
                    f"Vision API server error: {response.status_code} - "
                    f"{response.text[:200]}"
                )
                logger.error(error_msg)
                raise VisionAPIError(error_msg)

            if response.status_code >= 400:
                error_msg = (
                    f"Vision API client error: {response.status_code} - "
                    f"{response.text[:200]}"
                )
                logger.error(error_msg)
                raise VisionAPIError(error_msg)

            # Parse response
            try:
                data = response.json()
            except Exception as e:
                error_msg = f"Failed to parse JSON response: {e}"
                logger.error(error_msg)
                raise VisionAPIError(error_msg)

            # Validate with Pydantic schema
            try:
                validated = InvoiceExtractionResult.model_validate(data)
                logger.info(
                    f"Successfully extracted invoice: {validated.invoice_number} "
                    f"from {validated.vendor_name} for ${validated.total_amount}"
                )
                return validated.model_dump()
            except Exception as validation_error:
                error_msg = f"Invalid response schema: {validation_error}"
                logger.error(error_msg)
                raise VisionAPIError(error_msg)

    except httpx.NetworkError as e:
        error_msg = f"Network error calling Vision API: {e}"
        logger.error(error_msg)
        raise VisionAPIError(error_msg)
    except httpx.TimeoutException as e:
        error_msg = f"Timeout calling Vision API after {timeout}s: {e}"
        logger.error(error_msg)
        raise VisionAPIError(error_msg)
    except VisionAPIError:
        raise
    except Exception as e:
        error_msg = f"Unexpected error calling Vision API: {type(e).__name__}: {e}"
        logger.error(error_msg)
        raise VisionAPIError(error_msg)
