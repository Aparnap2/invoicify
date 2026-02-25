#!/bin/bash
# Stop All Invoicify Services

set -e

echo "🛑 Stopping Invoicify Services..."
echo ""

# Stop services in reverse order
echo "Stopping Event Grid Emulator..."
docker stop invoicify-event-grid 2>/dev/null || echo "  (not running)"

echo "Stopping Azurite..."
docker stop invoicify-azurite 2>/dev/null || echo "  (not running)"

echo "Stopping Qdrant..."
docker stop invoicify-qdrant 2>/dev/null || echo "  (not running)"

echo "Stopping Redis..."
docker stop invoicify-redis 2>/dev/null || echo "  (not running)"

echo "Stopping Ollama..."
docker stop ollama 2>/dev/null || echo "  (not running)"

echo ""
echo "✅ All services stopped!"
echo ""
echo "Remaining containers:"
docker ps --filter "name=invoicify" --filter "name=ollama" --format "table {{.Names}}\t{{.Status}}" || echo "  (none)"
echo ""
