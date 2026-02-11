#!/bin/bash
# Start PostgreSQL for analytics/logging (optional)

set -e

CONTAINER_NAME="invoicify-postgres"

echo "🐘 Starting PostgreSQL..."

# Check if container already exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo "Container exists, starting..."
    docker start $CONTAINER_NAME
else
    echo "Creating new PostgreSQL container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p 5432:5432 \
        -e POSTGRES_USER=invoicify \
        -e POSTGRES_PASSWORD=invoicify \
        -e POSTGRES_DB=invoicify \
        -v postgres-data:/var/lib/postgresql/data \
        postgres:15-alpine
fi

echo "✅ PostgreSQL started!"
echo "🔌 Connection: postgres://invoicify:invoicify@localhost:5432/invoicify"
