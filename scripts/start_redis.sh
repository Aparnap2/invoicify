#!/bin/bash
# Start Redis (Upstash Redis local alternative)
# Used for: Rate limiting, deduplication, caching

set -e

echo "🚀 Starting Redis container..."

# Check if already running
if docker ps --format '{{.Names}}' | grep -q "^invoicify-redis$"; then
    echo "✅ Redis is already running"
    exit 0
fi

# Check if container exists but stopped
if docker ps -a --format '{{.Names}}' | grep -q "^invoicify-redis$"; then
    echo "📦 Starting existing Redis container..."
    docker start invoicify-redis
else
    echo "📦 Creating new Redis container..."
    docker run -d \
        --name invoicify-redis \
        -p 6379:6379 \
        -v redis_data:/data \
        redis:7-alpine \
        redis-server --appendonly yes
fi

# Wait for Redis to be ready
echo "⏳ Waiting for Redis to be ready..."
sleep 2

# Test connection
echo "📋 Testing Redis connection..."
docker exec invoicify-redis redis-cli ping

echo ""
echo "✅ Redis is running on port 6379!"
echo ""
echo "Test connection:"
echo "  docker exec invoicify-redis redis-cli ping"
echo "  docker exec invoicify-redis redis-cli INFO"
echo ""
