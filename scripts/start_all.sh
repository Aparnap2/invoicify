#!/bin/bash
# Start All Invoicify Services (Individual Containers)
# Starts: Ollama, Redis, Qdrant, Azurite, Event Grid Emulator

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Invoicify Local Development Stack"
echo "=============================================="
echo ""

# Start services in order (dependencies first)
echo "1/5 Starting Ollama (LLM + OCR)..."
bash "$SCRIPT_DIR/start_ollama.sh"
echo ""

echo "2/5 Starting Redis (Rate Limiting + Cache)..."
bash "$SCRIPT_DIR/start_redis.sh"
echo ""

echo "3/5 Starting Qdrant (Vector DB for RAG)..."
bash "$SCRIPT_DIR/start_qdrant.sh"
echo ""

echo "4/5 Starting Azurite (Blob Storage)..."
bash "$SCRIPT_DIR/start_azurite.sh"
echo ""

echo "5/5 Starting Event Grid Emulator..."
bash "$SCRIPT_DIR/start_event_grid.sh"
echo ""

echo "=============================================="
echo "✅ All services started successfully!"
echo "=============================================="
echo ""
echo "Service Status:"
docker ps --filter "name=invoicify" --filter "name=ollama" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Next Steps:"
echo "  1. cd apps/agent-core"
echo "  2. export EXTRACTOR_MODE=ollama  # or 'fixture' or 'sarvam'"
echo "  3. uv run uvicorn src.main:app --reload"
echo ""
echo "Test Extraction:"
echo "  export EXTRACTOR_MODE=fixture"
echo "  python -c \"from src.extraction import extract_invoice; import asyncio; print(asyncio.run(extract_invoice('fake.pdf', '123')))\""
echo ""
