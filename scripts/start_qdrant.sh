#!/bin/bash
# Start Qdrant (Vector Database for RAG)
# Used for: Vendor knowledge, duplicate detection, policy search

set -e

echo "🚀 Starting Qdrant container..."

# Check if already running
if docker ps --format '{{.Names}}' | grep -q "^invoicify-qdrant$"; then
    echo "✅ Qdrant is already running"
    exit 0
fi

# Check if container exists but stopped
if docker ps -a --format '{{.Names}}' | grep -q "^invoicify-qdrant$"; then
    echo "📦 Starting existing Qdrant container..."
    docker start invoicify-qdrant
else
    echo "📦 Creating new Qdrant container..."
    docker run -d \
        --name invoicify-qdrant \
        -p 6333:6333 \
        -p 6334:6334 \
        -v qdrant_data:/qdrant/storage \
        qdrant/qdrant:latest
fi

# Wait for Qdrant to be ready
echo "⏳ Waiting for Qdrant to be ready..."
sleep 3

# Test connection
echo "📋 Testing Qdrant connection..."
curl -s http://localhost:6333/ | head -1

echo ""
echo "✅ Qdrant is running on port 6333!"
echo ""
echo "Web UI: http://localhost:6333/dashboard"
echo "Test connection:"
echo "  curl http://localhost:6333/"
echo "  curl http://localhost:6333/collections"
echo ""
