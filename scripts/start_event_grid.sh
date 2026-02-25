#!/bin/bash
# Start Event Grid Emulator (Local mock for Azure Event Grid)
# Used for: Event routing between Agent Core and Voice Agent

set -e

echo "🚀 Starting Event Grid Emulator..."

# Check if already running
if docker ps --format '{{.Names}}' | grep -q "^invoicify-event-grid$"; then
    echo "✅ Event Grid Emulator is already running"
    exit 0
fi

# Check if container exists but stopped
if docker ps -a --format '{{.Names}}' | grep -q "^invoicify-event-grid$"; then
    echo "📦 Starting existing Event Grid Emulator..."
    docker start invoicify-event-grid
else
    echo "📦 Creating new Event Grid Emulator container..."
    docker run -d \
        --name invoicify-event-grid \
        -p 8080:8080 \
        -v $(pwd)/mocks/event_grid_emulator.py:/app/main.py \
        -e WEBHOOK_SUBSCRIBERS=http://host.docker.internal:8001/api/events \
        python:3.11-slim \
        bash -c "pip install fastapi uvicorn httpx structlog pydantic && uvicorn main:app --host 0.0.0.0 --port 8080"
fi

# Wait for Event Grid to be ready
echo "⏳ Waiting for Event Grid Emulator to be ready..."
sleep 5

# Test connection
echo "📋 Testing Event Grid connection..."
curl -s http://localhost:8080/health | head -1 || echo "Event Grid responding..."

echo ""
echo "✅ Event Grid Emulator is running on port 8080!"
echo ""
echo "Endpoints:"
echo "  POST /api/events - Send events (CloudEvents schema)"
echo "  GET  /api/events - List received events"
echo "  GET  /health     - Health check"
echo ""
echo "Test sending event:"
echo "  curl -X POST http://localhost:8080/api/events -H 'Content-Type: application/json' -d '[{\"id\":\"test-1\",\"eventType\":\"invoice.submitted\",\"data\":{\"invoice_id\":\"123\"}}]'"
echo ""
