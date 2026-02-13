"""Test Docling + Groq extraction pipeline."""
import asyncio
import os
import sys

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from src.activities.extraction import extract_invoice

@pytest.mark.asyncio
async def test_extraction():
    # Example URL from R2 proxy (requires edge-api to be running)
    test_url = os.getenv("TEST_PDF_URL", "http://localhost:8787/internal/r2/raw/test-invoice.pdf")
    
    print(f"🚀 Starting extraction test for: {test_url}")
    
    try:
        result = await extract_invoice(test_url)
        
        print("\n=== EXTRACTION RESULT ===")
        print(f"Vendor: {result.get('vendor_name')}")
        print(f"Invoice #: {result.get('invoice_number')}")
        print(f"Amount: ${result.get('total_amount')}")
        print(f"Confidence: {result.get('extraction_confidence', 0):.2%}")
        print(f"\nLine Items ({len(result.get('line_items', []))}):")
        for item in result.get('line_items', []):
            print(f"  - {item.get('description')}: ${item.get('amount')}")
            
    except Exception as e:
        print(f"❌ Extraction failed: {e}")

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("⚠️  Warning: GROQ_API_KEY not set. Test will fail if calling LLM.")
    asyncio.run(test_extraction())
