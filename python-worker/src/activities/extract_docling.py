"""
Extract Invoice Activity using Docling
Extracts structured invoice data from documents using IBM Docling.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

from temporalio import activity

from src.config.factory import get_vision
from src.domain.models import InvoiceData, LineItem

logger = logging.getLogger(__name__)


@activity.defn
async def extract_invoice_with_docling(file_url: str) -> Dict[str, Any]:
    """
    Activity: Extract invoice data using Docling.

    Args:
        file_url: URL to invoice file (PDF, image, etc.)

    Returns:
        InvoiceData as dictionary
    """
    # Sanitize URL for logging (remove query params)
    from urllib.parse import urlparse

    parsed = urlparse(file_url)
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    logger.info(f"🔍 Extracting invoice from: {safe_url}")

    try:
        # Get Docling adapter from factory
        vision_adapter = get_vision()

        # Extract document
        extraction = await vision_adapter.extract_invoice_data(file_url)

        # Parse Markdown to extract structured data
        markdown = extraction["raw_text"]

        # Extract fields from Markdown
        invoice_data = _parse_markdown_invoice(markdown)

        # Add confidence and format info
        invoice_data["confidence"] = extraction["confidence"]
        invoice_data["tables_detected"] = extraction["tables_detected"]

        logger.info(
            f"✅ Extracted invoice: {invoice_data['invoice_number']} "
            f"from {invoice_data['vendor_name']}"
        )

        return invoice_data

    except Exception as e:
        logger.error(f"❌ Failed to extract invoice from {safe_url}: {e}")
        raise activity.ApplicationError(
            f"Invoice extraction failed: {str(e)}",
            non_retryable=False,
        ) from e


def _parse_markdown_invoice(markdown: str) -> Dict[str, Any]:
    """
    Parse Markdown invoice content to structured data.

    In production, this would use an LLM (Llama 3.2) to parse.
    For now, extract basic info using heuristics.
    """
    lines = markdown.split("\n")

    # Extract vendor name (usually first heading)
    vendor_name = "Unknown Vendor"
    for line in lines:
        if line.startswith("# "):
            vendor_name = line.replace("# ", "").strip()
            break

    # Generate IDs
    invoice_id = str(uuid.uuid4())
    vendor_id = f"vendor_{vendor_name.lower().replace(' ', '_')}"

    # Extract invoice number (common patterns)
    invoice_number = "INV-UNKNOWN"
    for line in lines:
        if "invoice" in line.lower() and "#" not in line:
            # Try to find number pattern
            match = re.search(r"[A-Z]*-?\d+", line)
            if match:
                invoice_number = match.group()
                break

    # Extract amount (look for $ followed by number)
    total_amount = Decimal("0.00")
    for line in lines:
        if "total" in line.lower() or "$" in line:
            match = re.search(r"\$?([\d,]+\.\d{2})", line)
            if match:
                amount_str = match.group(1).replace(",", "")
                total_amount = Decimal(amount_str)
                break

    # Parse line items from tables
    line_items = _parse_line_items(markdown)

    # Default dates (timezone-aware)
    now = datetime.now(timezone.utc)

    return {
        "invoice_id": invoice_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "issue_date": now.isoformat(),
        "due_date": now.isoformat(),
        "total_amount": str(total_amount),
        "currency": "USD",
        "line_items": [item.__dict__ for item in line_items],
        "raw_markdown": markdown,
    }


def _parse_line_items(markdown: str) -> list:
    """Parse line items from Markdown tables."""
    items = []
    lines = markdown.split("\n")

    for line in lines:
        # Detect Markdown table rows (lines containing |)
        if "|" in line:
            # Skip header separator lines
            if "---" in line and line.strip().startswith("|"):
                continue

            # Parse table row
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]

            if len(cells) >= 3:
                try:
                    # Try to parse as line item
                    description = cells[0]
                    quantity = int(cells[1]) if cells[1].isdigit() else 1

                    # Parse price (remove $ and ,)
                    price_str = cells[2].replace("$", "").replace(",", "")
                    unit_price = Decimal(price_str) if price_str else Decimal("0.00")

                    total = unit_price * quantity

                    items.append(
                        LineItem(
                            description=description,
                            quantity=quantity,
                            unit_price=unit_price,
                            total=total,
                        )
                    )
                except (ValueError, IndexError):
                    continue

    return items
