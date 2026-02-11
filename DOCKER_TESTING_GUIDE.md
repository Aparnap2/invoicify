# Docker Testing Guide (Individual Containers)

This guide explains how to test each component separately using individual Docker containers (no docker-compose).

## Quick Start

```bash
# Start all services
./scripts/start_ollama.sh
./scripts/start_storage.sh

# Run tests
./scripts/test_components.sh

# Stop all
./scripts/stop_all.sh
```

## Individual Component Testing

### 1. Ollama (Local AI)

**Start:**
```bash
./scripts/start_ollama.sh
```

**Test:**
```bash
# Check if running
curl http://localhost:11434/api/tags

# Pull a vision model
docker exec invoicify-ollama ollama pull llava

# Test extraction
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llava",
    "prompt": "Extract invoice data",
    "images": ["base64encoded..."]
  }'
```

**Stop:**
```bash
docker stop invoicify-ollama
```

### 2. MinIO (R2 Storage)

**Start:**
```bash
./scripts/start_storage.sh
```

**Test:**
```bash
# Check health
curl http://localhost:9000/minio/health/live

# Access console: http://localhost:9001
# Login: minioadmin / minioadmin

# Upload test file
docker run --rm --network host -v $(pwd)/test.pdf:/test.pdf minio/mc:latest \
  cp /test.pdf local/invoicify-storage/
```

**Stop:**
```bash
docker stop invoicify-minio
```

### 3. PostgreSQL (Optional Analytics)

**Start:**
```bash
./scripts/start_postgres.sh
```

**Test:**
```bash
# Connect
psql postgres://invoicify:invoicify@localhost:5432/invoicify

# Or with Docker
docker exec -it invoicify-postgres psql -U invoicify
```

**Stop:**
```bash
docker stop invoicify-postgres
```

### 4. QuickBooks Mock

**Start:**
```bash
./scripts/start_qbo_mock.sh
```

**Test:**
```bash
# Test mock API
curl http://localhost:3001/v3/company/123/bill
```

**Stop:**
```bash
docker stop invoicify-qbo-mock
```

### 5. Kafka (Optional Events)

**Start:**
```bash
./scripts/start_kafka.sh
```

**Test:**
```bash
# Check broker
docker exec invoicify-kafka rpk cluster info

# Create topic
docker exec invoicify-kafka rpk topic create invoices

# Produce message
echo '{"test": "data"}' | docker exec -i invoicify-kafka rpk topic produce invoices
```

**Stop:**
```bash
docker stop invoicify-kafka
```

## Integration Testing Workflow

### Test 1: Risk Calculation (No Docker)
```bash
cd invoicify-worker
npm test
```

### Test 2: Ollama + Storage
```bash
# Start both
./scripts/start_ollama.sh
./scripts/start_storage.sh

# Wait for Ollama to be ready
sleep 5

# Pull model
docker exec invoicify-ollama ollama pull llava

# Test component health
./scripts/test_components.sh
```

### Test 3: Full Pipeline (Local)
```bash
# 1. Start dependencies
./scripts/start_ollama.sh
./scripts/start_storage.sh

# 2. Install worker dependencies
cd invoicify-worker
npm install

# 3. Start worker
npm run dev

# 4. In another terminal, run golden test
./scripts/golden_test.sh
```

## Container Management

### List running containers
```bash
docker ps | grep invoicify
```

### View logs
```bash
# Ollama
docker logs invoicify-ollama -f

# MinIO
docker logs invoicify-minio -f

# PostgreSQL
docker logs invoicify-postgres -f
```

### Restart a container
```bash
docker restart invoicify-ollama
```

### Remove a container (and data)
```bash
# Stop first
docker stop invoicify-ollama

# Remove container
docker rm invoicify-ollama

# Remove volume (WARNING: deletes all data!)
docker volume rm ollama-data
```

## Resource Usage

Monitor container resource usage:
```bash
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | grep invoicify
```

## Testing Checklist

- [ ] Ollama responds to API calls
- [ ] Can pull vision models
- [ ] MinIO is accessible
- [ ] Can create buckets and upload files
- [ ] Worker health endpoint returns 200
- [ ] Risk calculation tests pass
- [ ] Golden invoice test completes

## Troubleshooting

### Port conflicts
```bash
# Check what's using port 11434 (Ollama)
lsof -i :11434

# Or use different port
docker run -d --name invoicify-ollama -p 11435:11434 ollama/ollama
```

### Container won't start
```bash
# Check logs
docker logs invoicify-ollama

# Check if port is in use
netstat -tulpn | grep 11434
```

### Data persistence
Containers use named volumes for persistence:
- `ollama-data` - AI models
- `minio-data` - S3 objects
- `postgres-data` - Database

To reset data:
```bash
docker volume rm ollama-data minio-data postgres-data
```

## Cleanup

Remove all invoicify containers and volumes:
```bash
./scripts/stop_all.sh

# Remove containers
docker rm invoicify-ollama invoicify-minio invoicify-postgres invoicify-qbo-mock invoicify-kafka 2>/dev/null || true

# Remove volumes (WARNING: deletes all data!)
docker volume rm ollama-data minio-data postgres-data redpanda-data 2>/dev/null || true
```
