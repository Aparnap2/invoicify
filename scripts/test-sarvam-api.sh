#!/bin/bash
# Test REAL Sarvam AI API with curl
# Usage: ./scripts/test-sarvam-api.sh YOUR_API_KEY

set -e

API_KEY="${1:-$SARVAM_AI_API_KEY}"

if [ -z "$API_KEY" ]; then
    echo "❌ Error: No API key provided"
    echo "Usage: ./scripts/test-sarvam-api.sh YOUR_API_KEY"
    echo "   or: export SARVAM_AI_API_KEY=your_key && ./scripts/test-sarvam-api.sh"
    exit 1
fi

echo "🔍 Testing Sarvam AI API..."
echo "=========================================="
echo ""

# Test 1: Translate API (simple test)
echo "1️⃣ Testing Translate API..."
echo ""

TRANSLATE_RESPONSE=$(curl -s -X POST "https://api.sarvam.ai/translate" \
    -H "api-subscription-key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "input": "Hello, how are you?",
        "source_language_code": "en-IN",
        "target_language_code": "hi-IN"
    }' || echo "ERROR")

if [[ "$TRANSLATE_RESPONSE" == *"ERROR"* ]]; then
    echo "❌ Translate API failed"
    echo "Response: $TRANSLATE_RESPONSE"
else
    echo "✅ Translate API response:"
    echo "$TRANSLATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$TRANSLATE_RESPONSE"
fi

echo ""
echo "=========================================="
echo ""

# Test 2: Document Intelligence API
echo "2️⃣ Testing Document Intelligence API..."
echo ""

# Create a test PDF first
TEST_PDF="/tmp/test_invoice.pdf"
cat > /tmp/create_test_pdf.py << 'PYTHON'
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

c = canvas.Canvas("/tmp/test_invoice.pdf", pagesize=letter)
c.drawString(100, 750, "TAX INVOICE")
c.drawString(100, 730, "Invoice No: INV-TEST-001")
c.drawString(100, 710, "Vendor: Test Vendor Pvt Ltd")
c.drawString(100, 690, "GST: 27AABCU9603R1ZM")
c.drawString(100, 670, "Total: Rs. 3540.00")
c.save()
print("PDF created")
PYTHON

python3 /tmp/create_test_pdf.py

if [ ! -f "$TEST_PDF" ]; then
    echo "❌ Failed to create test PDF"
    exit 1
fi

# Test Document Intelligence
echo ""
echo "📄 Uploading test PDF to Sarvam Document Intelligence..."
echo ""

# Note: Sarvam Document Intelligence uses job-based API
# This is a simplified test - full implementation needs async job polling
DOC_RESPONSE=$(curl -s -X POST "https://api.sarvam.ai/document-intelligence/analyze" \
    -H "api-subscription-key: $API_KEY" \
    -H "Content-Type: multipart/form-data" \
    -F "file=@$TEST_PDF" \
    -F "language=en-IN" \
    -F "output_format=html" \
    || echo "ERROR")

if [[ "$DOC_RESPONSE" == *"ERROR"* ]]; then
    echo "⚠️  Document Intelligence API may be async (job-based)"
    echo "Response: $DOC_RESPONSE"
else
    echo "✅ Document Intelligence response:"
    echo "$DOC_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$DOC_RESPONSE"
fi

echo ""
echo "=========================================="
echo ""
echo "✅ Sarvam AI API tests complete!"
echo ""
echo "NEXT STEPS:"
echo "1. If tests passed, update .env.local with your API key"
echo "2. Run: export SARVAM_AI_API_KEY=your_key"
echo "3. Run E2E tests: uv run pytest tests/e2e/test_real_sarvam_e2e.py -v -s"
echo ""
