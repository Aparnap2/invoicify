#!/bin/bash
# Stop all invoicify containers

echo "🛑 Stopping all invoicify containers..."

containers=(
    "invoicify-minio"
    "invoicify-ollama"
    "invoicify-qbo-mock"
    "invoicify-postgres"
    "invoicify-kafka"
)

for container in "${containers[@]}"; do
    if docker ps | grep -q $container; then
        echo "  Stopping $container..."
        docker stop $container
    fi
done

echo "✅ All containers stopped"
