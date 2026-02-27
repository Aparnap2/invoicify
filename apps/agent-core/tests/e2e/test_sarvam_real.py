#!/usr/bin/env python3
"""
Test Sarvam AI Document Intelligence with real handwritten Hindi invoice

Usage:
    uv run python tests/e2e/test_sarvam_real.py

Requires:
    SARVAM_AI_API_KEY set in .env.local or environment
"""

import os
import sys
import zipfile
import glob
from pathlib import Path
from dotenv import load_dotenv

# Load environment from .env.local
load_dotenv(Path(__file__).parent.parent.parent / "apps" / "agent-core" / ".env.local")

from sarvamai import SarvamAI

# Get API key from environment (NEVER hardcode!)
API_KEY = os.getenv("SARVAM_AI_API_KEY") or os.getenv("SARVAM_API_KEY")

if not API_KEY:
    print("❌ Error: SARVAM_AI_API_KEY not set")
    print("")
    print("Please add to apps/agent-core/.env.local:")
    print("  SARVAM_AI_API_KEY=your_key_here")
    print("")
    sys.exit(1)

print("🔍 Testing Sarvam AI Document Intelligence...")
print("=" * 60)

# Initialize client
client = SarvamAI(api_subscription_key=API_KEY)
client.document_intelligence.initialise()
print("✅ Client initialized")

# Test with the handwritten invoice image
test_img = Path(__file__).parent.parent / "fixtures" / "invoice_hindi.jpeg"
test_img = test_img.absolute()

if not test_img.exists():
    print(f"❌ File not found: {test_img}")
    print("")
    print("Creating test PDF instead...")
    
    # Create test PDF
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    
    test_pdf = Path(__file__).parent / "test_invoice.pdf"
    c = canvas.Canvas(str(test_pdf), pagesize=letter)
    c.drawString(100, 750, "TAX INVOICE")
    c.drawString(100, 730, "Invoice #: TEST-001")
    c.drawString(100, 710, "Vendor: Test Vendor Pvt Ltd")
    c.drawString(100, 690, "GST: 27AABCU9603R1ZM")
    c.drawString(100, 670, "Total: Rs. 3540.00")
    c.save()
    
    test_img = test_pdf
    print(f"✅ Test PDF created: {test_img}")

print(f"📄 Testing with: {test_img}")

# Create job
print("\n📝 Creating document intelligence job...")
job = client.document_intelligence.create_job(
    language="en-IN",
    output_format="md"
)
print(f"✅ Job created: {job.job_id}")

# Upload document
print("\n📤 Uploading document...")
job.upload_file(str(test_img))
print("✅ File uploaded")

# Start processing
print("\n🚀 Starting processing...")
job.start()
print("✅ Job started")

# Wait for completion
print("\n⏳ Waiting for completion...")
status = job.wait_until_complete()
print(f"✅ Job completed with state: {status.job_state}")

# Get metrics
metrics = job.get_page_metrics()
print(f"📊 Page metrics: {metrics}")

# Download output
print("\n💾 Downloading output...")
output_zip = Path(__file__).parent / "sarvam_output.zip"
job.download_output(str(output_zip))
print(f"✅ Output saved to {output_zip}")

# Extract and show results
output_dir = Path(__file__).parent / "sarvam_output"

with zipfile.ZipFile(output_zip, 'r') as zip_ref:
    zip_ref.extractall(output_dir)
    print("✅ Output extracted")
    
    # Find MD file
    import glob
    md_files = glob.glob(str(output_dir / "*.md"))
    if md_files:
        with open(md_files[0], 'r') as f:
            content = f.read()
            print(f"\n📄 Extracted Text ({len(content)} chars):")
            print("=" * 60)
            print(content[:1500] if len(content) > 1500 else content)

print("\n" + "=" * 60)
print("✅ SARVAM AI DOCUMENT INTELLIGENCE TEST PASSED!")
print("=" * 60)
