#!/bin/bash
# Start Azurite (Azure Blob Storage Emulator)
# Used for: PDF invoice storage (local dev)

set -e

echo "🚀 Starting Azurite container..."

# Check if already running
if docker ps --format '{{.Names}}' | grep -q "^invoicify-azurite$"; then
    echo "✅ Azurite is already running"
    exit 0
fi

# Check if container exists but stopped
if docker ps -a --format '{{.Names}}' | grep -q "^invoicify-azurite$"; then
    echo "📦 Starting existing Azurite container..."
    docker start invoicify-azurite
else
    echo "📦 Creating new Azurite container..."
    docker run -d \
        --name invoicify-azurite \
        -p 10000:10000 \
        -p 10001:10001 \
        -p 10002:10002 \
        -v azurite_data:/data \
        mcr.microsoft.com/azure-storage/azurite \
        azurite --blobHost 0.0.0.0 --queueHost 0.0.0.0 --tableHost 0.0.0.0 --loose
fi

# Wait for Azurite to be ready
echo "⏳ Waiting for Azurite to be ready..."
sleep 3

# Test connection
echo "📋 Testing Azurite connection..."
curl -s http://localhost:10000/devstoreaccount1/?comp=properties 2>&1 | head -3 || echo "Azurite responding..."

echo ""
echo "✅ Azurite is running!"
echo ""
echo "Ports:"
echo "  Blob:  http://localhost:10000/devstoreaccount1"
echo "  Queue: http://localhost:10001/devstoreaccount1"
echo "  Table: http://localhost:10002/devstoreaccount1"
echo ""
echo "Connection String (for local dev):"
echo "  DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OugDPfYIDSZRfj63d3;BlobEndpoint=http://localhost:10000/devstoreaccount1;"
echo ""
