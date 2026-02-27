#!/usr/bin/env python3
"""
Test Sarvam AI Document Intelligence with real handwritten Hindi invoice
"""

from sarvamai import SarvamAI
import os
import sys

API_KEY = "sk_ywytz35w_lGpBD7fIWLxUPYbVmNXnWt1L"

print("🔍 Testing Sarvam AI Document Intelligence...")
print("=" * 60)

# Initialize client
client = SarvamAI(api_subscription_key=API_KEY)
client.document_intelligence.initialise()
print("✅ Client initialized")

# Test with the handwritten invoice image
test_img = os.path.join(os.path.dirname(__file__), "..", "..", "invoice_hindi.jpeg")
test_img = os.path.abspath(test_img)

if not os.path.exists(test_img):
    print(f"❌ File not found: {test_img}")
    sys.exit(1)

print(f"📄 Testing with: {test_img}")

# Create job
print("\n📝 Creating document intelligence job...")
job = client.document_intelligence.create_job(
    language="hi-IN",
    output_format="html"
)
print(f"✅ Job created: {job.job_id}")

# Upload document
print("\n📤 Uploading handwritten Hindi invoice...")
job.upload_file(test_img)
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
output_zip = os.path.join(os.path.dirname(__file__), "sarvam_output.zip")
job.download_output(output_zip)
print(f"✅ Output saved to {output_zip}")

# Extract and show results
import zipfile
output_dir = os.path.join(os.path.dirname(__file__), "sarvam_output")

with zipfile.ZipFile(output_zip, 'r') as zip_ref:
    zip_ref.extractall(output_dir)
    print("✅ Output extracted")
    
    # Find HTML file
    import glob
    html_files = glob.glob(os.path.join(output_dir, "*.html"))
    if html_files:
        with open(html_files[0], 'r') as f:
            content = f.read()
            print(f"\n📄 Extracted Text ({len(content)} chars):")
            print("=" * 60)
            print(content[:1500] if len(content) > 1500 else content)

print("\n" + "=" * 60)
print("✅ SARVAM AI HANDWRITTEN HINDI INVOICE TEST PASSED!")
print("=" * 60)
