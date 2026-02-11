#!/bin/bash
# Start Kafka for event streaming (optional - if not using Cloudflare Queues locally)

set -e

CONTAINER_NAME="invoicify-kafka"

echo "📨 Starting Kafka (Redpanda)..."

# Check if container already exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Container exists, starting..."
    docker start $CONTAINER_NAME
else
    echo "Creating new Kafka container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p 9092:9092 \
        -p 9644:9644 \
        -v redpanda-data:/var/lib/redpanda/data \
        docker.redpanda.com/redpandadata/redpanda:latest \
        redpanda start --overprovisioned --smp 1 --memory 1G --reserve-memory 0M --node-id 0 --check=false
fi

echo "✅ Kafka started!"
echo "🔌 Broker: localhost:9092"
echo "📊 Console: http://localhost:9644"
