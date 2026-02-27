#!/bin/bash
# Start Ollama (Local LLM + OCR + Embeddings)
# Your existing models: LightOnOCR, qwen2.5-coder, nomic-embed-text, granite-docling

set -e

echo "🚀 Starting Ollama container..."

# Check if already running
if docker ps --format '{{.Names}}' | grep -q "^ollama$"; then
    echo "✅ Ollama is already running"
    docker exec ollama ollama list
    exit 0
fi

# Check if container exists but stopped
if docker ps -a --format '{{.Names}}' | grep -q "^ollama$"; then
    echo "📦 Starting existing Ollama container..."
    docker start ollama
else
    echo "📦 Creating new Ollama container..."
    docker run -d \
        --name ollama \
        -p 11434:11434 \
        -v ollama_data:/root/.ollama \
        ollama/ollama:latest
fi

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
sleep 3

# Verify models are available
echo "📋 Checking available models..."
docker exec ollama ollama list

echo ""
echo "✅ Ollama is running!"
echo ""
echo "Available models:"
docker exec ollama ollama list
echo ""
echo "Test OCR:"
echo "  curl http://localhost:11434/api/generate -d '{\"model\":\"aipib/LightOnOCR-1B-1025\",\"prompt\":\"test\",\"images\":[\"base64...\"]}'"
echo ""
echo "Test LLM:"
echo "  curl http://localhost:11434/api/generate -d '{\"model\":\"qwen2.5-coder:3b\",\"prompt\":\"Hello\"}'"
echo ""
