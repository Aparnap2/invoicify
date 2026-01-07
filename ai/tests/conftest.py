"""Pytest configuration and fixtures."""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from pydantic import BaseModel

from app.main import app
from app.config import Settings
from app.schemas.invoice import InvoiceCreate, InvoiceExtracted


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        host="0.0.0.0",
        port=8001,
        debug=True,
        llm_model="openai:gpt-4o",
        log_level="DEBUG",
    )


@pytest.fixture
def sample_invoice_create() -> InvoiceCreate:
    """Create sample invoice for testing."""
    from datetime import date
    from decimal import Decimal

    return InvoiceCreate(
        vendor_name="Test Vendor",
        vendor_address="123 Test St",
        vendor_tax_id="TAX-123",
        invoice_number="INV-TEST-001",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        currency="USD",
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("100.00"),
        total_amount=Decimal("1100.00"),
        source_file_name="test_invoice.pdf",
        source_file_type="pdf",
    )


@pytest.fixture
def sample_raw_content() -> str:
    """Create sample raw invoice content."""
    return """
    INVOICE

    Vendor: Test Vendor LLC
    Address: 123 Test Street, Test City, TC 12345
    Tax ID: TAX-123456

    Invoice Number: INV-2024-001
    Invoice Date: January 15, 2024
    Due Date: February 15, 2024

    Bill To:
    Test Company
    456 Business Ave
    Business City, BC 67890

    Description          Qty   Unit Price   Amount
    ----------------------------------------------------
    Consulting Services    10     $100.00   $1,000.00
    Software License        5     $50.00     $250.00

    Subtotal: $1,250.00
    Tax (10%): $125.00
    TOTAL: $1,375.00

    Payment Terms: Net 30
    PO Number: PO-2024-001
    """


@pytest.fixture
def async_client() -> Generator[AsyncClient, None, None]:
    """Create async test client."""
    transport = ASGITransport(app=app)
    with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
