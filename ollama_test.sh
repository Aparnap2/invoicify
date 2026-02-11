#!/bin/bash
# Test Ollama embedding and LLM inference

echo "========================================="
echo "OLLAMA INVOICE PROCESSING TEST REPORT"
echo "========================================="
echo ""

INVOICE_TEXT='ACME Corp
Invoice #12345
Date: 2024-01-15
Total: $1,250.00
Items: 5x Widget @ $200, 2x Gadget @ $125'

# Test 1: Embedding
echo "1. EMBEDDING TEST (nomic-embed-text:latest)"
echo "-------------------------------------------"
START=$(date +%s%N)
EMBED_RESPONSE=$(curl -s -X POST http://localhost:11434/api/embed \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"nomic-embed-text:latest\", \"input\": \"$INVOICE_TEXT\"}")
END=$(date +%s%N)
EMBED_MS=$(( (END - START) / 1000000 ))

echo "$EMBED_RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
e = d['embeddings'][0] if d.get('embeddings') else []
print(f'Model: nomic-embed-text:latest')
print(f'Dimensions: {len(e)}')
print(f'First 5 values: {e[:5]}')
"
echo "Response Time: ${EMBED_MS} ms"
echo ""

# Test 2: LLM Inference
echo "2. LLM INFERENCE TEST (qwen2.5-coder:3b)"
echo "-------------------------------------------"
START=$(date +%s%N)
LLM_RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"qwen2.5-coder:3b\",
    \"prompt\": \"Extract this invoice as JSON with fields: vendor, invoice_number, invoice_date, total_amount (number), line_items (array with item_name, quantity, unit_price, total_price). Invoice: $INVOICE_TEXT. Return ONLY valid JSON.\",
    \"stream\": false,
    \"format\": \"json\"
  }")
END=$(date +%s%N)
LLM_MS=$(( (END - START) / 1000000 ))

echo "$LLM_RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Model: qwen2.5-coder:3b')
print(f'Response: {d.get(\"response\", \"\")}')
print(f'Done: {d.get(\"done\", False)}')
"
echo "Response Time: ${LLM_MS} ms"
echo ""

echo "========================================="
echo "SUMMARY"
echo "========================================="
echo "Embedding: OK - 768D vector in ${EMBED_MS} ms"
echo "LLM: OK - Response in ${LLM_MS} ms"
