"""
Integration test for Vision Extraction (Step 2)
Tests extract.py against running mock server
"""

import sys
import os
import pytest
import subprocess
import time
import signal

# Add src to path
sys.path.insert(0, "/home/aparna/Desktop/invoicify/python-worker/src")

from activities.extract import extract_invoice_data, VisionAPIError


@pytest.fixture(scope="module")
def mock_server():
    """Start mock server for testing."""
    # Start mock server
    proc = subprocess.Popen(
        [
            sys.executable,
            "/home/aparna/Desktop/invoicify/python-worker/tests/mock_server.py",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(2)

    yield proc

    # Cleanup
    proc.send_signal(signal.SIGTERM)
    proc.wait()


@pytest.mark.asyncio
async def test_vision_api_integration(mock_server):
    """Test extraction against running mock server."""
    # Set environment to use mock server
    os.environ["VISION_API_URL"] = "http://localhost:3000/extract"

    # Call extraction
    result = await extract_invoice_data("http://test.com/invoice.pdf")

    # Verify response structure
    assert result["vendor_name"] == "Acme Corporation"
    assert result["total_amount"] == 1500.00
    assert result["invoice_number"] == "INV-2025-001"
    assert result["due_date"] == "2025-02-08"
    assert result["currency"] == "USD"
    assert result["confidence"] == 0.98


@pytest.mark.asyncio
async def test_vision_api_error_handling(mock_server):
    """Test error handling with invalid URL."""
    # Test with invalid URL - should raise ValueError for validation
    with pytest.raises(ValueError):
        await extract_invoice_data("not-a-valid-url")


@pytest.mark.asyncio
async def test_vision_api_validation(mock_server):
    """Test response validation."""
    os.environ["VISION_API_URL"] = "http://localhost:3000/extract"

    result = await extract_invoice_data("http://test.com/invoice.pdf")

    # Verify all required fields
    required_fields = [
        "vendor_name",
        "total_amount",
        "invoice_number",
        "due_date",
        "currency",
        "confidence",
    ]
    for field in required_fields:
        assert field in result, f"Missing field: {field}"

    # Verify types
    assert isinstance(result["total_amount"], (int, float))
    assert isinstance(result["confidence"], (int, float))
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["total_amount"] > 0
