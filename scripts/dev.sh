#!/bin/bash

echo "🚀 Starting Invoicify Development Environment"

# Start infrastructure
echo "📦 Starting Docker services (Temporal, Neo4j, Qdrant)..."
docker-compose up -d temporal postgres neo4j qdrant

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check Temporal UI
echo "🌐 Temporal UI: http://localhost:8233"
echo "🌐 Neo4j Browser: http://localhost:7474 (neo4j/invoicify123)"
echo "🌐 Qdrant UI: http://localhost:6333/dashboard"

# Start Mockoon if CLI is available
if command -v mockoon-cli &> /dev/null; then
    echo "🎭 Starting Mockoon..."
    mockoon-cli start --data mockoon/invoicify-mocks.json --port 3001 &
    MOCKOON_PID=$!
else
    echo "⚠️ Mockoon CLI not found. Install it or run Mockoon GUI manually."
fi

# Start Agent Worker
echo "🤖 Starting Agent Worker..."
cd apps/agent-core
# Ensure dependencies are sync'd
uv sync
uv run python -m src.worker &
AGENT_PID=$!
cd ../..

# Start Edge API
echo "⚡ Starting Edge API..."
cd apps/edge-api
# Using npm run dev or pnpm dev
pnpm dev &
EDGE_PID=$!
cd ../..

echo ""
echo "✅ All services started!"
echo ""
echo "📝 Services:"
echo "   - Edge API: http://localhost:8787"
echo "   - Temporal UI: http://localhost:8233"
echo "   - Neo4j: http://localhost:7474"
echo "   - Qdrant: http://localhost:6333/dashboard"
echo ""
echo "🛑 To stop: docker-compose down && kill $AGENT_PID $EDGE_PID $MOCKOON_PID"
