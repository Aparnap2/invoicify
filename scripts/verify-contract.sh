#!/bin/bash

echo "🧪 Quick Contract Verification Test"
echo "===================================="
echo ""

# Check if services are running
echo "1️⃣ Checking if services are running..."
if ! curl -s http://localhost:8787/health > /dev/null 2>&1; then
  echo "❌ Edge API not running"
  echo "   Run: ./scripts/dev.sh"
  exit 1
fi
echo "✅ Edge API is running"

if ! curl -s http://localhost:8233/api/v1/namespaces > /dev/null 2>&1; then
  echo "⚠️  Temporal might not be running (this is okay for first run)"
fi

# Create test fixture if needed
echo ""
echo "2️⃣ Preparing test fixture..."
mkdir -p fixtures
if [ ! -f "fixtures/test-invoice.pdf" ]; then
  echo "Creating dummy PDF..."
  echo "%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
203
%%EOF" > fixtures/test-invoice.pdf
  echo "✅ Created fixtures/test-invoice.pdf"
else
  echo "✅ Test fixture exists"
fi

# Upload invoice
echo ""
echo "3️⃣ Uploading test invoice..."
RESPONSE=$(curl -s -X POST http://localhost:8787/api/v1/invoices \
  -F "file=@fixtures/test-invoice.pdf")

TRACE_ID=$(echo $RESPONSE | jq -r '.trace_id' 2>/dev/null)

if [ "$TRACE_ID" == "null" ] || [ -z "$TRACE_ID" ]; then
  echo "❌ Upload failed"
  echo "Response: $RESPONSE"
  exit 1
fi

echo "✅ Upload successful!"
echo "   Trace ID: $TRACE_ID"

# Wait a moment for workflow to start
sleep 2

# Check Temporal UI
echo ""
echo "4️⃣ Verification Steps:"
echo "   1. Open Temporal UI: http://localhost:8233"
echo "   2. Look for workflow: invoice-${TRACE_ID}"
echo "   3. Verify all 3 activities executed:"
echo "      - extract_invoice_activity"
echo "      - analyze_invoice_activity"
echo "      - execute_payment_activity"
echo "   4. Check workflow status is COMPLETED"
echo ""
echo "5️⃣ Check invoice status:"
echo "   curl http://localhost:8787/api/v1/invoices/${TRACE_ID} | jq"
echo ""
echo "📊 If all activities show in Temporal UI → CONTRACT VERIFIED ✅"
echo "📊 If workflow fails → Check logs and debug"
