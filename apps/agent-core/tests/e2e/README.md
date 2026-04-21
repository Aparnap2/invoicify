# Fullstack E2E Tests for Invoicify

Comprehensive end-to-end tests for the Invoicify application stack.

## Overview

This test suite validates the entire Invoicify application end-to-end:

- ✅ **Authentication** (Better Auth)
- ✅ **Database CRUD** (PostgreSQL)
- ✅ **API Routes** (FastAPI + Hono)
- ✅ **MCP Integrations** (QuickBooks, HubSpot, Telegram)
- ✅ **Complete vendor-to-payment workflow**

## Test Structure

```
tests/e2e/test_fullstack_e2e.py
├── TestAuthentication
│   ├── test_user_registration
│   ├── test_organization_creation
│   └── test_api_key_auth
├── TestDatabaseCRUD
│   ├── test_vendor_crud
│   ├── test_invoice_crud
│   └── test_content_hash_dedup
├── TestAPIRoutes
│   ├── test_invoice_upload_endpoint
│   ├── test_invoice_status_endpoint
│   └── test_vendor_search_endpoint
├── TestMCPIntegrations
│   ├── test_quickbooks_mcp_flow
│   ├── test_hubspot_mcp_flow
│   └── test_telegram_webhook_flow
├── TestCompleteWorkflow
│   └── test_complete_vendor_to_payment_flow
└── TestEdgeCases
    ├── test_invalid_invoice_format
    ├── test_missing_auth_header
    └── test_rate_limiting
```

## Prerequisites

### 1. Install Dependencies

```bash
cd apps/agent-core
uv sync
```

### 2. Set Up Environment Variables

Create a `.env` file in `apps/agent-core/`:

```bash
# Copy from example
cp .env.example .env

# Edit with your values
vim .env
```

Required environment variables:

```bash
# Service URLs
TEST_BASE_URL=http://localhost:8001
TEST_WORKER_URL=http://localhost:8787
DATABASE_URL=postgresql://invoicify:password@localhost:5432/invoicify

# QuickBooks (optional - for MCP tests)
QB_CLIENT_ID=your_client_id
QB_CLIENT_SECRET=your_client_secret
QB_REALM_ID=your_realm_id
QB_REFRESH_TOKEN=your_refresh_token

# HubSpot (optional - for MCP tests)
HUBSPOT_API_KEY=pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Telegram (optional - for webhook tests)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

### 3. Start Required Services

The E2E tests require all services to be running:

```bash
# Start PostgreSQL
docker run -d \
  --name invoicify-db \
  -e POSTGRES_USER=invoicify \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=invoicify \
  -p 5432:5432 \
  postgres:15-alpine

# Wait for DB to be ready
sleep 5

# Start agent-core (FastAPI)
cd apps/agent-core
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 &

# Start worker (Hono/Cloudflare Workers)
cd invoicify-worker
pnpm run dev &

# Wait for services to start
sleep 10

# Verify services are running
curl http://localhost:8001/health
curl http://localhost:8787/health
```

## Running Tests

### Run All Tests

```bash
cd apps/agent-core
uv run pytest tests/e2e/test_fullstack_e2e.py -v
```

### Run Specific Test Class

```bash
# Authentication tests
uv run pytest tests/e2e/test_fullstack_e2e.py::TestAuthentication -v

# Database CRUD tests
uv run pytest tests/e2e/test_fullstack_e2e.py::TestDatabaseCRUD -v

# API route tests
uv run pytest tests/e2e/test_fullstack_e2e.py::TestAPIRoutes -v

# MCP integration tests
uv run pytest tests/e2e/test_fullstack_e2e.py::TestMCPIntegrations -v

# Complete workflow test
uv run pytest tests/e2e/test_fullstack_e2e.py::TestCompleteWorkflow -v

# Edge case tests
uv run pytest tests/e2e/test_fullstack_e2e.py::TestEdgeCases -v
```

### Run Specific Test

```bash
# Single test
uv run pytest tests/e2e/test_fullstack_e2e.py::TestAuthentication::test_user_registration -v

# Multiple specific tests
uv run pytest tests/e2e/test_fullstack_e2e.py::TestDatabaseCRUD::test_vendor_crud tests/e2e/test_fullstack_e2e.py::TestDatabaseCRUD::test_invoice_crud -v
```

### Run with Coverage

```bash
uv run pytest tests/e2e/test_fullstack_e2e.py --cov=src --cov-report=html --cov-report=term
```

### Run in CI Mode (No Real API Calls)

```bash
# Skip integration tests that require real services
uv run pytest tests/e2e/test_fullstack_e2e.py -m "not integration" -v
```

### Run with Output Capture

```bash
# Show print statements during test execution
uv run pytest tests/e2e/test_fullstack_e2e.py -v -s

# Show output only for failed tests
uv run pytest tests/e2e/test_fullstack_e2e.py -v
```

### Run with Markers

```bash
# Run only E2E tests
uv run pytest tests/e2e/test_fullstack_e2e.py -m e2e -v

# Run only integration tests
uv run pytest tests/e2e/test_fullstack_e2e.py -m integration -v

# Run only async tests
uv run pytest tests/e2e/test_fullstack_e2e.py -m asyncio -v
```

## Test Output

### Successful Test Run

```
tests/e2e/test_fullstack_e2e.py::TestAuthentication::test_user_registration PASSED [  6%]
tests/e2e/test_fullstack_e2e.py::TestAuthentication::test_organization_creation PASSED [ 12%]
tests/e2e/test_fullstack_e2e.py::TestDatabaseCRUD::test_vendor_crud PASSED [ 25%]
tests/e2e/test_fullstack_e2e.py::TestCompleteWorkflow::test_complete_vendor_to_payment_flow PASSED [ 81%]

======================== 16 passed in 45.23s =========================
```

### Skipped Tests (Services Not Available)

```
tests/e2e/test_fullstack_e2e.py::TestAuthentication::test_user_registration SKIPPED [  6%]
tests/e2e/test_fullstack_e2e.py::TestDatabaseCRUD::test_vendor_crud SKIPPED [ 25%]

======================== 16 skipped in 0.30s =========================
```

### Failed Test

```
tests/e2e/test_fullstack_e2e.py::TestAuthentication::test_user_registration FAILED [  6%]

=================================== FAILURES ===================================
__________________ TestAuthentication.test_user_registration ___________________
tests/e2e/test_fullstack_e2e.py:256: in test_user_registration
    assert register_response.status_code in [200, 201]
E   AssertionError: Vendor creation failed: 500
===================== 1 failed, 15 passed in 12.34s ======================
```

## Test Markers

The test suite uses pytest markers for categorization:

| Marker | Description | Usage |
|--------|-------------|-------|
| `e2e` | End-to-end tests | `-m e2e` |
| `integration` | Tests requiring real DB/services | `-m integration` |
| `asyncio` | Async tests | `-m asyncio` |
| `slow` | Slow running tests (>10s) | `-m slow` |

## Fixtures

The test suite provides several fixtures:

### `http_client`

Async HTTP client for API calls:

```python
async def test_example(self, http_client: httpx.AsyncClient):
    response = await http_client.get(f"{WORKER_URL}/health")
    assert response.status_code == 200
```

### `test_vendor_data`

Generates test vendor data:

```python
async def test_example(self, test_vendor_data: Dict[str, Any]):
    # test_vendor_data contains:
    # {
    #     "id": "uuid",
    #     "name": "Test Vendor xxx",
    #     "normalized_name": "test-vendor-xxx",
    #     ...
    # }
```

### `test_invoice_data`

Generates test invoice data:

```python
async def test_example(self, test_invoice_data: Dict[str, Any]):
    # test_invoice_data contains:
    # {
    #     "trace_id": "uuid",
    #     "vendor_id": "uuid",
    #     "invoice_number": "INV-XXX",
    #     "total": 3540.00,
    #     ...
    # }
```

### `test_pdf_invoice`

Generates a test PDF invoice:

```python
async def test_example(self, test_pdf_invoice: bytes):
    # test_pdf_invoice contains raw PDF bytes
```

### `check_services_available`

Checks if services are running before tests:

```python
async def test_example(self, check_services_available: Dict[str, bool]):
    # check_services_available contains:
    # {
    #     "agent_core": True/False,
    #     "worker": True/False,
    # }
```

## Troubleshooting

### All Tests Skipped

**Problem:** All tests are skipped even though services are running.

**Solution:** Check that service URLs are correct:

```bash
# Verify services are accessible
curl http://localhost:8001/health
curl http://localhost:8787/health

# Update environment variables if needed
export TEST_BASE_URL=http://localhost:8001
export TEST_WORKER_URL=http://localhost:8787
```

### Connection Errors

**Problem:** Tests fail with `httpx.ConnectError`.

**Solution:** Ensure services are running and accessible:

```bash
# Check if services are listening
netstat -tlnp | grep -E '8001|8787'

# Restart services if needed
pkill -f "uvicorn src.main:app"
pkill -f "wrangler dev"

# Start services again
cd apps/agent-core && uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 &
cd invoicify-worker && pnpm run dev &
```

### Timeout Errors

**Problem:** Tests fail with `httpx.ReadTimeout`.

**Solution:** Increase timeout in test configuration:

```python
# In test_fullstack_e2e.py, update:
REQUEST_TIMEOUT = 60.0  # Default is 30.0
```

### MCP Integration Tests Skipped

**Problem:** MCP integration tests are skipped.

**Solution:** Set required environment variables:

```bash
# For QuickBooks tests
export QB_CLIENT_ID=your_client_id
export QB_CLIENT_SECRET=your_client_secret
export QB_REALM_ID=your_realm_id

# For HubSpot tests
export HUBSPOT_API_KEY=pat-na1-xxxxxxxx

# For Telegram tests
export TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

## Best Practices

### 1. Clean Test Data

Tests should clean up after themselves:

```python
@pytest.mark.asyncio
async def test_example(self, http_client: httpx.AsyncClient):
    # Create
    create_response = await http_client.post(...)
    resource_id = create_response.json()["id"]
    
    try:
        # Test
        ...
    finally:
        # Cleanup
        await http_client.delete(f"/api/v1/resources/{resource_id}")
```

### 2. Use Unique IDs

Generate unique IDs for each test to avoid conflicts:

```python
import uuid

trace_id = str(uuid.uuid4())
vendor_id = f"test-vendor-{uuid.uuid4().hex[:8]}"
```

### 3. Handle Async Properly

Use `await` for all async operations:

```python
@pytest.mark.asyncio
async def test_example(self, http_client: httpx.AsyncClient):
    response = await http_client.get(...)  # Correct
    # response = http_client.get(...)  # Wrong!
```

### 4. Use Fixtures

Leverage provided fixtures for consistency:

```python
async def test_example(self, test_vendor_data: Dict[str, Any]):
    # Use fixture instead of hardcoding
    response = await http_client.post(
        f"{WORKER_URL}/api/v1/vendors",
        json=test_vendor_data,
    )
```

### 5. Assert with Messages

Provide clear assertion messages:

```python
assert response.status_code == 200, \
    f"Expected 200, got {response.status_code}: {response.text}"
```

## Performance

### Test Execution Time

| Test Class | Avg. Time |
|------------|-----------|
| TestAuthentication | ~3s |
| TestDatabaseCRUD | ~5s |
| TestAPIRoutes | ~4s |
| TestMCPIntegrations | ~10s |
| TestCompleteWorkflow | ~15s |
| TestEdgeCases | ~2s |
| **Total** | **~40s** |

### Optimization Tips

1. **Run specific tests:** Don't run all tests during development
2. **Use markers:** Skip slow tests when not needed
3. **Parallel execution:** Use `pytest-xdist` for parallel test runs
4. **Mock external APIs:** Use `pytest-httpx` to mock HTTP calls

```bash
# Run tests in parallel (requires pytest-xdist)
uv run pytest tests/e2e/test_fullstack_e2e.py -n auto -v
```

## CI/CD Integration

### GitHub Actions

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: invoicify
          POSTGRES_PASSWORD: password
          POSTGRES_DB: invoicify
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install dependencies
        run: |
          cd apps/agent-core
          uv sync
      
      - name: Start services
        run: |
          # Start agent-core
          cd apps/agent-core
          uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 &
          
          # Start worker
          cd invoicify-worker
          pnpm install
          pnpm run dev &
          
          # Wait for services
          sleep 10
      
      - name: Run E2E tests
        run: |
          cd apps/agent-core
          uv run pytest tests/e2e/test_fullstack_e2e.py -v --tb=short
      
      - name: Upload test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results
          path: apps/agent-core/test-results/
```

## Contributing

### Adding New Tests

1. Follow the existing test structure
2. Use appropriate markers (`@pytest.mark.e2e`, `@pytest.mark.integration`)
3. Use fixtures for test data
4. Clean up test data after execution
5. Add docstrings explaining what the test does

### Test Naming Convention

```python
async def test_<feature>_<action>_<expected_result>(self):
    """<Description of what the test does>."""
    # Example:
    async def test_invoice_upload_valid_data_returns_202(self):
        """Test that valid invoice upload returns 202 Accepted."""
```

## Support

For issues or questions:

1. Check the [troubleshooting section](#troubleshooting)
2. Review existing test implementations for examples
3. Check pytest documentation: https://docs.pytest.org/
4. Open an issue in the repository

## License

Same as the main Invoicify project.
