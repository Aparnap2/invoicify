#!/bin/bash
# Start R2-compatible storage (MinIO for local testing)
# Alternative: Use wrangler R2 local binding

set -e

CONTAINER_NAME="invoicify-minio"

echo "🪣 Starting MinIO (R2-compatible storage)..."

# Check if container already exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Container exists, starting..."
    docker start $CONTAINER_NAME
else
    echo "Creating new MinIO container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p 9000:9000 \
        -p 9001:9001 \
        -e MINIO_ROOT_USER=minioadmin \
        -e MINIO_ROOT_PASSWORD=minioadmin \
        -v minio-data:/data \
        minio/minio:latest \
        server /data --console-address ":9001"
fi

echo "✅ MinIO started!"
echo "📊 Console: http://localhost:9001 (minioadmin/minioadmin)"
echo "🔌 API: http://localhost:9000"

# Create bucket if it doesn't exist
sleep 2
docker run --rm --network host \
    minio/mc:latest \
    alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true

docker run --rm --network host \
    minio/mc:latest \
    mb local/invoicify-storage 2>/dev/null || echo "Bucket exists"
