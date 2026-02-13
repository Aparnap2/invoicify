#!/bin/bash

echo "🧪 Testing Golden Invoice Flow"

# Ensure services are running
if ! curl -s http://localhost:8787/health > /dev/null; then
  echo "⚠️ Edge API might not be running at http://localhost:8787/health"
  # Continue anyway as health endpoint might not be exposed on root
fi

# Create test fixture (if not exists)
mkdir -p fixtures
if [ ! -f "fixtures/test-invoice.pdf" ]; then
  echo "⚠️  No test fixture found at fixtures/test-invoice.pdf"
  echo "Creating a dummy PDF for testing..."
  echo "Dummy PDF Content" > fixtures/test-invoice.pdf
fi

# Upload invoice
echo "📤 Uploading test invoice..."
RESPONSE=$(curl -s -X POST http://localhost:8787/api/v1/invoices \
  -F "file=@fixtures/test-invoice.pdf")

TRACE_ID=$(echo $RESPONSE | jq -r '.trace_id')

if [ "$TRACE_ID" == "null" ] || [ -z "$TRACE_ID" ]; then
  echo "❌ Upload failed: $RESPONSE"
  exit 1
fi

echo "✅ Upload successful. Trace ID: $TRACE_ID"

# Poll status
echo "⏳ Polling status (max 30 seconds)..."
for i in {1..30}; do
  STATUS_RESPONSE=$(curl -s http://localhost:8787/api/v1/invoices/$TRACE_ID)
  STATUS=$(echo $STATUS_RESPONSE | jq -r '.invoice.status')
  WORKFLOW_STATUS=$(echo $STATUS_RESPONSE | jq -r '.workflow.status')
  
  echo "   [$i/30] DB Status: $STATUS | Workflow: $WORKFLOW_STATUS"
  
  if [ "$STATUS" == "APPROVED" ] || [ "$STATUS" == "REJECTED" ]; then
    echo ""
    echo "✅ Workflow completed!"
    echo ""
    echo "Final Result:"
    echo $STATUS_RESPONSE | jq
    exit 0
  fi
  
  if [ "$WORKFLOW_STATUS" == "COMPLETED" ] || [ "$WORKFLOW_STATUS" == "FAILED" ] || [ "$WORKFLOW_STATUS" == "TERMINATED" ]; then
      # If workflow is done but DB isn't updated, give it a tiny bit more time or exit
      if [ "$STATUS" != "APPROVED" ] && [ "$STATUS" != "REJECTED" ]; then
         echo "⚠️ Workflow completed but DB status matches: $STATUS"
      fi
  fi

  sleep 1
done

echo "⏱️ Timeout waiting for completion"
echo "Current status: $STATUS_RESPONSE" | jq
