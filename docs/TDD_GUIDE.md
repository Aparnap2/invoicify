# Nivi TDD Development Environment

# # Overview

Test-Driven Development (TDD) environment using Docker, Mockoon CLI, and existing infrastructure (Ollama, Neo4j, Qdrant, Redpanda, Temporal).

# # Quick Start

```bash
# 1. Start infrastructure
docker-compose -f docker-compose.test.yml up -d

# 2. Run all tests
./scripts/test-all.sh

# 3. Run specific test suite
./scripts/test-unit.sh
./scripts/test-integration.sh
./scripts/test-e2e.sh
```text
# # Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     TEST ENVIRONMENT                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Mockoon    │  │   Temporal   │  │     Redpanda     │  │
│  │   (Mocks)    │  │   (Dev)      │  │    (Kafka)       │  │
│  │   :3000      │  │   :7233      │  │    :9092         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────┴─────────────────┴────────────────────┴─────────┐  │
│  │              TEMPORAL WORKER (Test)                    │  │
│  │  ┌──────────────┐  ┌──────────────┐                   │  │
│  │  │   Analyst    │  │    Critic    │                   │  │
│  │  │   Activity   │  │   Activity   │                   │  │
│  │  └──────────────┘  └──────────────┘                   │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────┼───────────────────────────────┐  │
│  │                   SHARED RESOURCES                      │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │  │
│  │  │  Ollama  │  │  Neo4j   │  │  Qdrant  │             │  │
│  │  │ :11434   │  │ :7687    │  │ :6333    │             │  │
│  │  └──────────┘  └──────────┘  └──────────┘             │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```text
# # Test-Driven Development Workflow

## # 1. Red: Write Failing Test

```python
# temporal/tests/activities/test_anomaly.py
async def test_anomaly_detector_identifies_outlier():
    """Test that amounts 5x above average are flagged as anomalies."""
    # Arrange: Train on normal amounts
    for amount in [100, 105, 98, 110, 102]:
        await detect_anomaly(amount, "test-vendor")

    # Act: Test anomalous amount
    result = await detect_anomaly(500, "test-vendor")

    # Assert: Should be flagged as anomaly
    assert result['is_anomaly'] is True
    assert result['score'] > 0.7
```text
Run the test (should fail):
```bash
pytest temporal/tests/activities/test_anomaly.py::test_anomaly_detector_identifies_outlier -v
```text
## # 2. Green: Write Minimum Code

```python
# temporal/activities/anomaly.py
async def detect_anomaly(amount: float, vendor_id: str) -> dict:
    """Detect if amount is anomalous for vendor."""
    # Load or initialize model
    model = await load_model(vendor_id)

    # Score and learn
    features = {'amount': amount}
    score = model.score_one(features)
    model.learn_one(features)

    # Persist model
    await save_model(vendor_id, model)

    return {
        'score': score,
        'is_anomaly': score > 0.7,
        'vendor_id': vendor_id
    }
```text
Run the test (should pass):
```bash
pytest temporal/tests/activities/test_anomaly.py -v
```text
## # 3. Refactor: Improve Code Quality

- Add error handling
- Improve logging
- Optimize performance
- Re-run tests

# # Docker Test Services

## # docker-compose.test.yml

```yaml
version: '3.8'

services:
  # Mockoon for external API mocking
  mockoon:
    image: mockoon/cli:latest
    command: ["--data", "/data/mocks.json", "--port", "3000"]
    volumes:
      - ./mocks:/data:ro
    ports:
      - "3000:3000"
    networks:
      - nivi-test

  # Temporal development server
  temporal:
    image: temporalio/auto-setup:latest
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgres
      - DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development-sql.yaml
    ports:
      - "7233:7233"
      - "8233:8233"
    networks:
      - nivi-test
    depends_on:
      - postgres

  # PostgreSQL for Temporal
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal
      POSTGRES_DB: temporal
    networks:
      - nivi-test

  # Redpanda (Kafka-compatible)
  redpanda:
    image: docker.redpanda.com/redpandadata/redpanda:v24.2.1
    command:
      - redpanda start
      - --smp 1
      - --overprovisioned
      - --node-id 0
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
      - --advertise-kafka-addr internal://redpanda:9092,external://localhost:19092
      - --pandaproxy-addr internal://0.0.0.0:8082,external://0.0.0.0:18082
      - --advertise-pandaproxy-addr internal://redpanda:8082,external://localhost:18082
      - --schema-registry-addr internal://0.0.0.0:8081,external://0.0.0.0:18081
      - --rpc-addr redpanda:33145
      - --advertise-rpc-addr redpanda:33145
    ports:
      - "19092:19092"
      - "18082:18082"
      - "18081:18081"
    networks:
      - nivi-test

  # Test runner service
  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.test
    volumes:
      - .:/app
      - /app/temporal/__pycache__
      - /app/ai/__pycache__
    environment:
      - TEMPORAL_HOST=temporal:7233
      - REDPANDA_HOST=redpanda:9092
      - MOCKOON_HOST=mockoon:3000
      - OLLAMA_HOST=host.docker.internal:11434
      - NEO4J_HOST=host.docker.internal:7687
      - QDRANT_HOST=host.docker.internal:6333
    networks:
      - nivi-test
    depends_on:
      - temporal
      - redpanda
      - mockoon
    command: ["pytest", "-v", "--tb=short"]

networks:
  nivi-test:
    driver: bridge
```text
## # Dockerfile.test

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

# Copy source code
COPY temporal/ ./temporal/
COPY ai/ ./ai/
COPY tests/ ./tests/
COPY mocks/ ./mocks/

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["pytest", "-v"]
```text
## # requirements-test.txt

```text
# Core dependencies
pydantic==2.10.0
pydantic-settings==2.0.0
httpx==0.28.0
python-dotenv==1.0.0

# Temporal
temporalio==1.6.0

# ML
river==0.21.0
numpy==1.26.0

# Databases
neo4j==5.20.0
qdrant-client==1.12.0
redis==5.0.0
aiokafka==0.10.0

# LLM
openai==1.55.0

# Testing
pytest==8.0.0
pytest-asyncio==0.23.0
pytest-cov==4.1.0
pytest-xdist==3.5.0
pytest-mock==3.12.0
pytest-timeout==2.2.0
factory-boy==3.3.0
faker==22.0.0

# HTTP mocking
responses==0.24.0
aioresponses==0.7.0

# Code quality
black==24.0.0
ruff==0.1.0
mypy==1.8.0
```text
# # Mockoon Configuration

## # mocks/groq-api.json

```json
{
  "uuid": "groq-mock",
  "name": "Groq API Mock",
  "endpointPrefix": "",
  "port": 3000,
  "routes": [
    {
      "uuid": "chat-completions",
      "method": "post",
      "endpoint": "openai/v1/chat/completions",
      "responses": [
        {
          "uuid": "extract-invoice",
          "body": "{\n  \"id\": \"chatcmpl-mock\",\n  \"object\": \"chat.completion\",\n  \"created\": 1700000000,\n  \"model\": \"llama-3.2-90b-vision-preview\",\n  \"choices\": [{\n    \"index\": 0,\n    \"message\": {\n      \"role\": \"assistant\",\n      \"content\": \"{\\\"vendor_name\\\": \\\"Acme Corporation\\\", \\\"total_amount\\\": 1500.00, \\\"invoice_number\\\": \\\"INV-2024-001\\\", \\\"due_date\\\": \\\"2025-03-15\\\", \\\"line_items\\\": [{\\\"description\\\": \\\"Consulting Services\\\", \\\"amount\\\": 1500.00}]}\"\n    },\n    \"finish_reason\": \"stop\"\n  }]\n}",
          "latency": 500,
          "statusCode": 200,
          "label": "Extract Invoice",
          "rules": [
            {
              "target": "body",
              "modifier": "",
              "value": "extract",
              "operator": "contains",
              "invert": false
            }
          ]
        },
        {
          "uuid": "default-response",
          "body": "{\"id\": \"chatcmpl-mock\", \"choices\": [{\"message\": {\"content\": \"Mock response\"}}]}",
          "latency": 100,
          "statusCode": 200
        }
      ]
    }
  ]
}
```text
# # Test Scripts

## # scripts/test-all.sh

```bash
# !/bin/bash
set -e

echo "🧪 Nivi Test Suite"
echo "=================="

# Start infrastructure
echo "📦 Starting test infrastructure..."
docker-compose -f docker-compose.test.yml up -d

# Wait for services
echo "⏳ Waiting for services..."
sleep 10

# Run tests
echo "🧪 Running tests..."
docker-compose -f docker-compose.test.yml exec -T test-runner pytest \
  --cov=temporal \
  --cov=ai \
  --cov-report=html \
  --cov-report=term-missing \
  -v

# Cleanup
echo "🧹 Cleaning up..."
docker-compose -f docker-compose.test.yml down

echo "✅ Tests complete!"
```text
## # scripts/test-watch.sh

```bash
# !/bin/bash
# Watch mode for TDD

echo "👀 Watch mode - tests will re-run on file changes"

docker-compose -f docker-compose.test.yml exec test-runner \
  ptw --runner "pytest -v"
```text
# # Test Categories

## # Unit Tests (Fast, Isolated)

```python
# temporal/tests/activities/test_analyst_unit.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_analyst_proposes_auto_approve_for_trusted_vendor():
    """Unit test with mocked Neo4j."""
    # Arrange
    with patch('temporal.activities.agents.get_neo4j_client') as mock_neo4j:
        mock_neo4j.return_value.get_vendor_history = AsyncMock(return_value=[
            {'amount': 100, 'status': 'APPROVED'},
            {'amount': 105, 'status': 'APPROVED'},
        ])

        invoice_data = {
            'vendor_name': 'Trusted Vendor',
            'total_amount': 100,
            'invoice_number': 'INV-001'
        }

        # Act
        result = await analyst_evaluate(invoice_data)

        # Assert
        assert result.proposed_action == 'AUTO_APPROVE'
```text
## # Integration Tests (Real Services)

```python
# temporal/tests/integration/test_neo4j_integration.py
import pytest
from neo4j import GraphDatabase

@pytest.fixture(scope='module')
def neo4j_driver():
    driver = GraphDatabase.driver(
        'bolt://host.docker.internal:7687',
        auth=('neo4j', 'password')
    )
    yield driver
    driver.close()

@pytest.mark.asyncio
async def test_vendor_trust_persists_in_neo4j(neo4j_driver):
    """Integration test with real Neo4j."""
    # Act
    await update_vendor_trust('Test Vendor', 'APPROVED', True)

    # Assert
    with neo4j_driver.session() as session:
        result = session.run(
            "MATCH (v:Vendor {name: 'Test Vendor'}) RETURN v.trust_level"
        )
        record = result.single()
        assert record is not None
```text
## # E2E Tests (Full Flow)

```python
# tests/e2e/test_full_pipeline.py
@pytest.mark.asyncio
async def test_complete_invoice_workflow():
    """E2E test through entire pipeline."""
    # 1. Produce to Kafka
    await produce_invoice({
        'invoice_id': 'e2e-test-001',
        'image_url': 'https://example.com/test.pdf'
    })

    # 2. Wait for Temporal workflow
    handle = await temporal_client.start_workflow(
        InvoiceProcessingWorkflow.run,
        invoice_data,
        id='e2e-test-001'
    )

    # 3. Wait for completion
    result = await asyncio.wait_for(handle.result(), timeout=60)

    # 4. Verify Neo4j
    # 5. Verify Qdrant
    # 6. Verify response
```text
# # Running Tests

## # Individual Test Files

```bash
# Unit tests only
pytest temporal/tests/activities/test_analyst_unit.py -v

# Integration tests only
pytest temporal/tests/integration/ -v --tb=short

# E2E tests only
pytest tests/e2e/ -v --timeout=120

# Specific test
pytest temporal/tests/activities/test_anomaly.py::test_anomaly_detector_identifies_outlier -v
```text
## # With Coverage

```bash
# Generate coverage report
pytest --cov=temporal --cov=ai --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html
```text
## # Parallel Execution

```bash
# Run tests in parallel (faster)
pytest -n auto

# With 4 workers
pytest -n 4
```text
# # Debugging Tests

## # With pdb

```bash
# Drop into debugger on failure
pytest --pdb

# Debug specific test
pytest temporal/tests/activities/test_anomaly.py --pdb -k test_anomaly
```text
## # With Logging

```bash
# Show debug logs
pytest -v --log-cli-level=DEBUG

# Show only errors
pytest -v --log-cli-level=ERROR
```text
## # Docker Exec

```bash
# Enter test container
 docker-compose -f docker-compose.test.yml exec test-runner bash

# Run tests inside container
pytest temporal/tests/activities/test_anomaly.py -v
```text
# # Test Data Factories

## # temporal/tests/factories.py

```python
import factory
from faker import Faker
from temporal.schemas import InvoiceExtracted, LineItem

fake = Faker()

class LineItemFactory(factory.Factory):
    class Meta:
        model = LineItem

    description = factory.LazyAttribute(lambda _: fake.sentence())
    quantity = factory.LazyAttribute(lambda _: fake.random_int(1, 10))
    unit_price = factory.LazyAttribute(lambda _: round(fake.pyfloat(min_value=10, max_value=1000), 2))
    amount = factory.LazyAttribute(lambda obj: round(obj.quantity * obj.unit_price, 2))

class InvoiceExtractedFactory(factory.Factory):
    class Meta:
        model = InvoiceExtracted

    vendor_name = factory.LazyAttribute(lambda _: fake.company())
    invoice_number = factory.LazyAttribute(lambda _: f"INV-{fake.uuid4()[:8]}")
    total_amount = factory.LazyAttribute(lambda _: round(fake.pyfloat(min_value=100, max_value=50000), 2))
    currency = 'USD'
    due_date = factory.LazyAttribute(lambda _: fake.future_date())
    line_items = factory.List([factory.SubFactory(LineItemFactory) for _ in range(3)])
    overall_confidence = factory.LazyAttribute(lambda _: round(fake.pyfloat(min_value=0.8, max_value=1.0), 2))
```text
# # Performance Tests

## # Load Testing with Locust

```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between

class InvoiceUser(HttpUser):
    wait_time = between(1, 5)

    @task(3)
    def upload_invoice(self):
        self.client.post('/api/v1/invoices', json={
            'vendor_name': 'Test Vendor',
            'total_amount': 1000,
            'invoice_number': f'INV-{self.user_id}'
        })

    @task(1)
    def get_invoice(self):
        self.client.get('/api/v1/invoices/test-id')
```text
Run:
```bash
locust -f tests/performance/locustfile.py --host=http://localhost:8000
```text
# # Continuous Integration

## # .github/workflows/tdd.yml

```yaml
name: TDD

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Start infrastructure
      run: docker-compose -f docker-compose.test.yml up -d

    - name: Wait for services
      run: sleep 15

    - name: Run tests

|  |

        docker-compose -f docker-compose.test.yml exec -T test-runner \
          pytest --cov=temporal --cov=ai --cov-report=xml -v

    - name: Upload coverage
      uses: codecov/codecov-action@v3

    - name: Cleanup
      run: docker-compose -f docker-compose.test.yml down
```text
# # Best Practices

1. **Test Naming**: `test_<what>_<condition>_<expected_result>`
2. **Arrange-Act-Assert**: Clear structure in every test
3. **One Assert per Test**: Focus on single behavior
4. **Fast Tests**: Unit tests < 100ms, integration < 1s
5. **Deterministic**: Same input → same output
6. **Isolated**: Tests don't depend on each other
7. **Readable**: Clear intent, minimal setup

# # Troubleshooting

## # Common Issues

1. **Services not starting**: Check ports are available
2. **Neo4j connection refused**: Ensure Neo4j container is running
3. **Kafka timeouts**: Increase sleep time in scripts
4. **Test failures**: Run with `--tb=long` for full trace

## # Reset Environment

```bash
# Complete reset
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d

# Clear Neo4j data
docker exec neo4j cypher-shell -u neo4j -p password "MATCH (n) DETACH DELETE n"

# Clear Kafka topics
docker exec redpanda rpk topic delete invoice.ingested
```text
---

*Happy TDD! 🧪*
