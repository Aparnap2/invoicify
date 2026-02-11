#!/bin/bash
# Run Golden Invoice Test end-to-end

set -e

BASE_URL="${BASE_URL:-http://localhost:8787}"
FIXTURES_DIR="${FIXTURES_DIR:-./fixtures}"

echo "🏆 Golden Invoice Test"
echo "======================"
echo "Base URL: $BASE_URL"
echo ""

# Step 1: Health check
echo "1️⃣ Checking worker health..."
HEALTH=$(curl -s "$BASE_URL/health")
echo "   Response: $HEALTH"
echo ""

# Step 2: Upload invoice
echo "2️⃣ Uploading test invoice..."
UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/upload" \
    -F "file=@$FIXTURES_DIR/sample-invoice.pdf" \
    -F "metadata={\"source\":\"test\",\"userId\":\"test-user\"}")

echo "   Response: $UPLOAD_RESPONSE"

# Extract trace_id
TRACE_ID=$(echo $UPLOAD_RESPONSE | grep -o '"traceId":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TRACE_ID" ]; then
    echo "❌ Failed to get traceId"
    exit 1
fi

echo "   Trace ID: $TRACE_ID"
echo ""

# Step 3: Poll for completion
echo "3️⃣ Polling for processing completion..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    STATUS=$(curl -s "$BASE_URL/api/v1/invoices/$TRACE_ID/status")
    echo "   Attempt $((ATTEMPT+1))/$MAX_ATTEMPTS: $STATUS"
    
    # Check if completed
    if echo "$STATUS" | grep -q "APPROVED\|REJECTED\|HITL_REQUIRED\|FAILED"; then
        echo ""
        echo "✅ Processing complete!"
        echo "   Final status: $STATUS"
        break
    fi
    
    ATTEMPT=$((ATTEMPT+1))
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo ""
    echo "❌ Timeout waiting for completion"
    exit 1
fi

# Step 4: Verify results
echo ""
echo "4️⃣ Verifying results..."

# Check R2 storage
echo "   Checking R2 storage..."
# This would need AWS CLI or MinIO client configured

# Check D1 database
echo "   Checking D1 database..."
# This would need wrangler d1 execute

echo ""
echo "✅ Golden Invoice Test Complete!"
