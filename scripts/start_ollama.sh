#!/bin/bash
# Start Ollama for local AI inference

set -e

CONTAINER_NAME="invoicify-ollama"

echo "🦙 Starting Ollama container..."

# Check if container already exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Container exists, starting..."
    docker start $CONTAINER_NAME
else
    echo "Creating new Ollama container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p 11434:11434 \
        -v ollama-data:/root/.ollama \
        ollama/ollama:latest
fi

echo "✅ Ollama started!"
echo "🔌 API: http://localhost:11434"
echo ""
echo "📥 Pull vision models (optional):"
echo "  docker exec invoicify-ollama ollama pull llava"
echo "  docker exec invoicify-ollama ollama pull bakllava"
