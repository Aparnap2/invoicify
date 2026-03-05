# Invoicify End-to-End Test Suite

Comprehensive E2E testing for the Invoicify invoice processing pipeline.

## Overview

This test suite validates the complete invoice processing workflow:

1. **Email Ingestion** - Mocked via Azure Event Grid emulator
2. **PDF Upload** - Mocked Azure Blob Storage
3. **OCR Extraction** - Mocked Azure Document Intelligence
4. **LLM Parsing** - OpenRouter free tier (or mocked)
5. **Trust Battery** - Vendor risk decision engine
6. **QuickBooks Sync** - Mocked via Mockoon
7. **Salesforce Logging** - Mocked via Mockoon
8. **Audit Ledger** - Complete audit trail verification

## Files Created

```
invoicify/
├── mocks/
│   ├── quickbooks-mock.json      # QuickBooks API mock (port 3010)
│   ├── salesforce-mock.json      # Salesforce API mock (port 3020)
│   ├── azure-eventgrid-mock.json # Azure Event Grid & Storage mock (port 3030)
│   └── audit-ledger-mock.json    # Audit ledger mock (port 3050)
├── scripts/
│   └── test-e2e-full.sh          # Main test runner script
└── tests/
    └── e2e/
        ├── __init__.py
        ├── generate_invoice.py   # Test invoice PDF generator
        └── test_full_workflow.py # Complete E2E test
```

## Quick Start

### Prerequisites

```bash
# Node.js 18+ (for Mockoon CLI)
node --version  # v18 or higher

# Python 3.11+
python3 --version  # 3.11 or higher

# Install Mockoon CLI
npm install -g @mockoon/cli

# Install Python test dependencies
pip install pytest pytest-asyncio httpx reportlab
# Or with uv:
uv pip install pytest pytest-asyncio httpx reportlab
```

### Run Full Test Suite

```bash
# Make script executable (first time only)
chmod +x scripts/test-e2e-full.sh

# Run complete E2E tests
./scripts/test-e2e-full.sh

# Run without cleanup (keep mocks running for debugging)
./scripts/test-e2e-full.sh --no-cleanup

# Run with verbose output
./scripts/test-e2e-full.sh --verbose
```

### Run Individual Tests

```bash
# Run pytest directly (mocks must be running)
pytest tests/e2e/test_full_workflow.py -v

# Run specific test
pytest tests/e2e/test_full_workflow.py::test_full_workflow -v -s

# Run with coverage
pytest tests/e2e/ -v --cov=apps/agent-core/src
```

### Generate Test Invoices

```bash
# Generate single test invoice
python tests/e2e/generate_invoice.py --output test_invoice.pdf

# Generate with custom vendor and amount
python tests/e2e/generate_invoice.py --vendor "TechCorp" --amount 2500.00

# Generate batch of invoices
python tests/e2e/generate_invoice.py --batch 10 --output-dir ./test_invoices
```

## Mock Services

### Port Configuration

| Service | Port | Description |
|---------|------|-------------|
| QuickBooks Mock | 3010 | QuickBooks Online API |
| Salesforce Mock | 3020 | Salesforce REST API |
| Azure Blob/Event Grid | 3030 | Blob storage + Event Grid |
| Azure Document Intelligence | 3040 | OCR extraction |
| Audit Ledger | 3050 | Audit trail service |

### Start Mocks Manually

```bash
# Start QuickBooks mock
mockoon-cli start --data mocks/quickbooks-mock.json --port 3010

# Start Salesforce mock
mockoon-cli start --data mocks/salesforce-mock.json --port 3020

# Start Azure Event Grid mock
mockoon-cli start --data mocks/azure-eventgrid-mock.json --port 3030

# Start Audit Ledger mock
mockoon-cli start --data mocks/audit-ledger-mock.json --port 3050
```

### Health Check

```bash
# Check all mock services
curl http://localhost:3010/health  # QuickBooks
curl http://localhost:3020/health  # Salesforce
curl http://localhost:3030/health  # Azure Event Grid
curl http://localhost:3050/health  # Audit Ledger
```

## Test Workflow

### Step-by-Step Execution

```
┌─────────────────────────────────────────────────────────────────┐
│                    E2E TEST WORKFLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Generate Test Invoice PDF                                   │
│     └─→ Creates realistic PDF with test data                    │
│                                                                 │
│  2. Email Ingestion (Event Grid)                                │
│     └─→ Simulates email with attachment                         │
│     └─→ Triggers Event Grid event                               │
│                                                                 │
│  3. PDF Upload to Blob Storage                                  │
│     └─→ Uploads PDF to mocked Azure Blob                        │
│     └─→ Returns blob URL                                        │
│                                                                 │
│  4. Azure Document Intelligence OCR                             │
│     └─→ Extracts text and fields from PDF                       │
│     └─→ Returns structured data with confidence                 │
│                                                                 │
│  5. LLM JSON Parsing                                            │
│     └─→ Parses OCR output to standardized JSON                  │
│     └─→ Validates and normalizes fields                         │
│                                                                 │
│  6. Trust Battery Decision                                      │
│     └─→ Checks vendor trust level                               │
│     └─→ Makes AUTO_APPROVE / HITL / BLOCK decision              │
│                                                                 │
│  7. QuickBooks Sync                                             │
│     └─→ Creates bill in QuickBooks (if AUTO_APPROVE)            │
│     └─→ Returns QuickBooks bill ID                              │
│                                                                 │
│  8. Salesforce Logging                                          │
│     └─→ Creates ActivityLog__c record                           │
│     └─→ Returns Salesforce activity ID                          │
│                                                                 │
│  9. Audit Ledger Finalization                                   │
│     └─→ Records complete audit trail                            │
│     └─→ Verifies all entries present                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Test Report

### Output Format

After running tests, you'll see a summary:

```
================================================================================
E2E TEST REPORT: test_full_workflow
================================================================================
Test ID:        550e8400-e29b-41d4-a716-446655440000
Status:         ✅ PASSED
Duration:       45230ms
Start Time:     2025-03-05T19:30:00.000000+00:00
End Time:       2025-03-05T19:30:45.230000+00:00
--------------------------------------------------------------------------------
STEPS:
  1. [✓] 1. Generate Test Invoice PDF (1250ms)
  2. [✓] 2. Email Ingestion (Event Grid) (45ms)
  3. [✓] 3. PDF Upload to Blob Storage (32ms)
  4. [✓] 4. Azure Document Intelligence OCR (520ms)
  5. [✓] 5. LLM JSON Parsing (380ms)
  6. [✓] 6. Trust Battery Decision (15ms)
  7. [✓] 7. QuickBooks Sync (250ms)
  8. [✓] 8. Salesforce Logging (200ms)
  9. [✓] 9. Audit Ledger Finalization (18ms)
--------------------------------------------------------------------------------
INVOICE DATA:
  Number:       INV-E2E-1709668200
  Vendor:       Acme Corporation
  Amount:       $1,620.00
QuickBooks ID:  5678
Salesforce ID:  a00xxABC123
Audit Entries:  10
================================================================================
```

### Report Files

- **JSON Report**: `reports/e2e/test_report_<test_id>.json`
- **JUnit XML**: `reports/e2e/junit-e2e.xml`

## Environment Variables

```bash
# Mock service URLs
export MOCKOON_QUICKBOOKS_URL=http://localhost:3010
export MOCKOON_SALESFORCE_URL=http://localhost:3020
export MOCKOON_AUDIT_URL=http://localhost:3050
export AZURE_BLOB_MOCK_URL=http://localhost:3030
export AZURE_DI_MOCK_URL=http://localhost:3040

# Test configuration
export E2E_TIMEOUT_SECONDS=120    # Max test duration
export E2E_REQUEST_TIMEOUT=30.0   # HTTP request timeout
```

## CI/CD Integration

### GitHub Actions

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-test:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Mockoon CLI
        run: npm install -g @mockoon/cli

      - name: Install Python dependencies
        run: |
          pip install pytest pytest-asyncio httpx reportlab

      - name: Run E2E Tests
        run: ./scripts/test-e2e-full.sh
```

## Troubleshooting

### Mock Services Won't Start

```bash
# Check if ports are in use
lsof -i :3010
lsof -i :3020
lsof -i :3030

# Kill existing processes
kill -9 $(lsof -t -i :3010)
kill -9 $(lsof -t -i :3020)
kill -9 $(lsof -t -i :3030)

# Restart Mockoon
mockoon-cli start --data mocks/quickbooks-mock.json --port 3010
```

### Test Timeout

If tests exceed 2 minutes:

```bash
# Increase timeout
export E2E_TIMEOUT_SECONDS=180
./scripts/test-e2e-full.sh
```

### PDF Generation Fails

```bash
# Install reportlab dependencies
pip install reportlab pillow

# Verify installation
python -c "from reportlab.lib.pagesizes import letter; print('OK')"
```

### Mockoon CLI Issues

```bash
# Reinstall Mockoon CLI
npm uninstall -g @mockoon/cli
npm install -g @mockoon/cli

# Verify installation
mockoon-cli --version
```

## Customization

### Add New Test Scenarios

Edit `tests/e2e/test_full_workflow.py`:

```python
@pytest.mark.asyncio
async def test_high_value_invoice(self, ...):
    """Test auto-approval limit enforcement."""
    invoice_data = TestInvoiceData(
        vendor_name="Big Vendor",
        total_amount=10000.00,  # Exceeds STANDARD limit
        trust_level="STANDARD",
    )
    # ... test implementation
```

### Modify Mock Responses

Edit Mockoon JSON files in `mocks/`:

```json
{
  "endpoint": "/v3/company/:realmId/bill",
  "responses": [{
    "statusCode": 200,
    "body": "{\"Bill\": {\"Id\": \"custom-id\"}}"
  }]
}
```

### Add Custom Invoice Templates

Extend `TestInvoiceGenerator`:

```python
def generate_international_invoice(self, ...):
    """Generate invoice with multiple currencies."""
    # ... custom implementation
```

## Performance Benchmarks

Expected test durations:

| Component | Expected Time |
|-----------|---------------|
| PDF Generation | < 2s |
| Email Ingestion | < 1s |
| Blob Upload | < 1s |
| OCR Extraction | < 3s |
| LLM Parsing | < 2s |
| Trust Decision | < 1s |
| QuickBooks Sync | < 2s |
| Salesforce Log | < 2s |
| Audit Finalization | < 1s |
| **Total** | **< 15s** |

## Security Notes

- Mock services run on localhost only
- No real credentials are used
- Test invoices are clearly marked
- Audit logs are stored locally

## Contributing

1. Add test cases for new features
2. Update mock configurations as needed
3. Ensure tests complete in < 2 minutes
4. Document new test scenarios

## License

Same as Invoicify project license.
