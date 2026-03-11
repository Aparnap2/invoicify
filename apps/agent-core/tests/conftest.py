"""Pytest configuration and fixtures for agent-core tests.

Sets up Python path and common fixtures for unit, integration, and E2E tests.
"""

import os
import sys
import uuid
import asyncio
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, AsyncGenerator

import pytest
import httpx
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Add src to Python path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Test configuration
TEST_TENANT_ID = f"test-tenant-{uuid.uuid4().hex[:8]}"
TEST_USER_ID = f"test-user-{uuid.uuid4().hex[:8]}"
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8001")
WORKER_URL = os.getenv("TEST_WORKER_URL", "http://localhost:8787")
REQUEST_TIMEOUT = 30.0


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async HTTP client for API calls."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        yield client


@pytest.fixture
def test_vendor_data() -> Dict[str, Any]:
    """Generate test vendor data."""
    vendor_id = str(uuid.uuid4())
    return {
        "id": vendor_id,
        "name": f"Test Vendor {vendor_id[:8]}",
        "normalized_name": f"test-vendor-{vendor_id[:8]}",
        "email": f"vendor-{vendor_id[:8]}@test.com",
        "phone": "+1-555-0123",
        "address": "123 Test Street, Test City, TC 12345",
        "tax_id": f"TAX-{vendor_id[:8]}",
        "trust_level": 50,
    }


@pytest.fixture
def test_invoice_data(test_vendor_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate test invoice data."""
    return {
        "trace_id": str(uuid.uuid4()),
        "vendor_id": test_vendor_data["id"],
        "vendor_name": test_vendor_data["name"],
        "invoice_number": f"INV-{uuid.uuid4().hex[:8].upper()}",
        "total": 3540.00,
        "currency": "USD",
        "invoice_date": (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d"),
        "due_date": (datetime.utcnow() + timedelta(days=23)).strftime("%Y-%m-%d"),
        "line_items": [
            {
                "description": "Office Chairs (Ergonomic)",
                "quantity": 10,
                "unit_price": 150.00,
                "amount": 1500.00,
            },
            {
                "description": "Executive Desks (Wooden)",
                "quantity": 5,
                "unit_price": 300.00,
                "amount": 1500.00,
            },
        ],
        "subtotal": 3000.00,
        "tax_amount": 540.00,
    }


@pytest.fixture
def test_pdf_invoice(test_invoice_data: Dict[str, Any]) -> bytes:
    """Generate a test PDF invoice."""
    buffer = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    buffer_path = buffer.name
    buffer.close()

    c = canvas.Canvas(buffer_path, pagesize=letter)
    width, height = letter

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, height - 100, "TAX INVOICE")

    # Vendor info
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 130, f"Vendor: {test_invoice_data['vendor_name']}")
    c.drawString(100, height - 150, f"Invoice #: {test_invoice_data['invoice_number']}")
    c.drawString(100, height - 170, f"Date: {test_invoice_data['invoice_date']}")
    c.drawString(100, height - 190, f"Due Date: {test_invoice_data['due_date']}")

    # Line items
    y = height - 230
    c.setFont("Helvetica-Bold", 10)
    c.drawString(100, y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(350, y, "Unit Price")
    c.drawString(450, y, "Amount")

    c.setFont("Helvetica", 10)
    y -= 20
    for item in test_invoice_data["line_items"]:
        c.drawString(100, y, item["description"])
        c.drawString(300, y, str(item["quantity"]))
        c.drawString(350, y, f"${item['unit_price']:.2f}")
        c.drawString(450, y, f"${item['amount']:.2f}")
        y -= 20

    # Totals
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(350, y, "Subtotal:")
    c.drawString(450, y, f"${test_invoice_data['subtotal']:.2f}")
    y -= 20
    c.drawString(350, y, "Tax:")
    c.drawString(450, y, f"${test_invoice_data['tax_amount']:.2f}")
    y -= 20
    c.drawString(350, y, "Total:")
    c.drawString(450, y, f"${test_invoice_data['total']:.2f}")

    c.save()

    with open(buffer_path, "rb") as f:
        pdf_bytes = f.read()

    os.unlink(buffer_path)
    return pdf_bytes


def calculate_content_hash(pdf_bytes: bytes) -> str:
    """Calculate SHA256 hash of PDF content for duplicate detection."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def generate_idempotency_key(trace_id: str, vendor_id: str) -> str:
    """Generate idempotency key for invoice processing."""
    return hashlib.sha256(f"{trace_id}:{vendor_id}".encode()).hexdigest()
