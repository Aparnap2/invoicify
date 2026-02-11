#!/bin/bash
# Start QuickBooks Mock Server for testing

set -e

CONTAINER_NAME="invoicify-qbo-mock"

echo "📚 Starting QuickBooks Mock Server..."

# Check if container already exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Container exists, starting..."
    docker start $CONTAINER_NAME
else
    echo "Creating mock server container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p 3001:3000 \
        -v $(pwd)/mocks:/data \
        mockoon/cli:latest \
        start --data /data/qbo-mock.json
fi

echo "✅ QBO Mock started!"
echo "🔌 API: http://localhost:3001"
