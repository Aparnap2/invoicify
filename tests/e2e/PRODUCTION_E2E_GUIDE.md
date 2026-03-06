# 🧪 PRODUCTION E2E TEST GUIDE

## OVERVIEW

This test validates the **complete Invoicify workflow** with **REAL Azure services** and **REAL Docker containers**.

```
PDF Upload → Azure Blob → Sarvam OCR → Azure LLM → Trust Battery → 
QuickBooks (Mock) → Salesforce (Mock) → Audit Trail → Qdrant Vector
```

---

## PREREQUISITES

### 1. Azure Credentials

Create `.env.azure` in the root directory:

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-oss-120b
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Sarvam OCR
SARVAM_AI_API_KEY=sk_your-key-here

# Azure Storage
AZURE_STORAGE_ACCOUNT=invoicifystore
AZURE_STORAGE_KEY=your-storage-key

# Redis (Docker)
REDIS_URL=redis://localhost:6379

# Qdrant (Docker)
QDRANT_URL=http://localhost:6333
```

### 2. Docker Containers

```bash
# Start required containers
./scripts/start_redis.sh
./scripts/start_qdrant.sh

# Verify
docker ps | grep -E "redis|qdrant"
```

### 3. Mockoon CLI

```bash
# Install (if not already installed)
npm install -g @mockoon/cli
```

---

## RUNNING THE TEST

### Quick Start

```bash
# Run full production E2E test
./scripts/test-production-e2e.sh
```

### Manual Run

```bash
cd apps/agent-core
PYTHONPATH=. uv run pytest tests/e2e/test_production_e2e.py -v --tb=short
```

---

## TEST WORKFLOW (10 STEPS)

| Step | Service | Real/Mock | Description |
|------|---------|-----------|-------------|
| 1 | Local FS | Local | Generate test invoice PDF |
| 2 | Azure Blob | **REAL** | Upload PDF to blob storage |
| 3 | Sarvam OCR | **REAL** | Extract text with Azure Document Intelligence |
| 4 | Azure LLM | **REAL** | Parse JSON with GPT-OSS-120B |
| 5 | Redis | **REAL** | Check Trust Battery level |
| 6 | Local Logic | Local | Make approval decision |
| 7 | QuickBooks | Mock (port 3010) | Create bill (if approved) |
| 8 | Salesforce | Mock (port 3020) | Log activity |
| 9 | PostgreSQL | Local | Store audit trail |
| 10 | Qdrant + Azure | **REAL** | Embed + store vector |

---

## EXPECTED OUTPUT

```
╔═══════════════════════════════════════════════════════════╗
║     Invoicify Production E2E Test                        ║
║     Real Azure + Real Docker + Real Data                 ║
╚═══════════════════════════════════════════════════════════╝

✓ Azure credentials validated
✓ invoicify-redis running on port 6379
✓ invoicify-qdrant running on port 6333

Starting QuickBooks mock on port 3010...
✓ QuickBooks mock started (PID: 12345)
Starting Salesforce mock on port 3020...
✓ Salesforce mock started (PID: 12346)

✓ Generate Test Invoice PDF: PASS
    path: /path/to/invoice.pdf
    size_kb: 45.2

✓ Upload to Azure Blob Storage: PASS
    container: invoices
    blob: test/invoice.pdf
    url: https://...

✓ Extract with Sarvam OCR: PASS
    job_id: 20260305_xxx
    pages: 1
    markdown_length: 1234

✓ Parse JSON with Azure LLM: PASS
    model: gpt-oss-120b
    vendor: Acme Supplies
    total: 11800.0
    tokens_used: 512

✓ Check Trust Battery (Redis): PASS
    vendor_id: acme-supplies
    trust_level: STANDARD
    auto_approve_limit: $5,000.00

✓ Make Approval Decision: PASS
    decision: AUTO_APPROVE
    amount: $11,800.00
    limit: $5,000.00
    reason: Trusted vendor...

✓ Sync to Mock QuickBooks: PASS
    bill_id: 5678
    total: 11800.0
    status: created

✓ Log to Mock Salesforce: PASS
    record_id: a00XXXXXXXXXXXXXXX
    decision: AUTO_APPROVE
    status: logged

✓ Store Audit Trail: PASS
    invoice_id: INV-TEST-2026-001
    event_type: INVOICE_PROCESSED
    decision: AUTO_APPROVE

✓ Embed & Store in Qdrant: PASS
    model: text-embedding-3-small
    vector_size: 1536
    collection: invoices
    point_id: abc123...

============================================================
PRODUCTION E2E TEST SUMMARY
============================================================
Steps Passed: 10/10 (100.0%)
Duration: 45.3s
Decision: AUTO_APPROVE
QuickBooks ID: 5678
Salesforce ID: a00XXXXXXXXXXXXXXX
Report: reports/e2e/production-e2e-summary.json
============================================================

╔═══════════════════════════════════════════════════════════╗
║           PRODUCTION E2E TEST PASSED ✓                    ║
╚═══════════════════════════════════════════════════════════╝
```

---

## REPORTS GENERATED

| File | Format | Purpose |
|------|--------|---------|
| `reports/e2e/production-e2e-summary.json` | JSON | Test summary with all results |
| `reports/e2e/production-e2e-results.xml` | JUnit XML | CI/CD integration |
| `reports/e2e/production-e2e-output.log` | Text | Full console output |

---

## TROUBLESHOOTING

### Azure Credentials Error

```
[ERROR] Missing required environment variables:
  - AZURE_OPENAI_ENDPOINT
  - AZURE_OPENAI_API_KEY
```

**Fix:** Create `.env.azure` with all required variables.

### Docker Container Not Running

```
[!] invoicify-redis not running (optional for this test)
```

**Fix:** Run `./scripts/start_redis.sh`

### Mockoon Port Conflict

```
[ERROR] QuickBooks mock failed to start
```

**Fix:** Kill existing process on port 3010:
```bash
lsof -ti:3010 | xargs kill -9
```

### Sarvam OCR Timeout

```
Step 3 failed: OCR failed: Timeout
```

**Fix:** Increase timeout in `test_production_e2e.py`:
```python
status = job.wait_until_complete(timeout=300)  # 5 minutes
```

---

## CUSTOMIZATION

### Add New Test Steps

Edit `tests/e2e/test_production_e2e.py`:

```python
def test_11_your_new_step(self):
    """Step 11: Your custom step."""
    try:
        # Your logic here
        self.log_step("Your Step", "PASS", {"detail": "value"})
    except Exception as e:
        self.log_step("Your Step", "FAIL", {"error": str(e)})
        pytest.fail(f"Step 11 failed: {e}")
```

### Change Mock Ports

Edit mock JSON files:
- `mocks/quickbooks-prod-mock.json`: Change `"port": 3010`
- `mocks/salesforce-prod-mock.json`: Change `"port": 3020`

Update `Config` class in test file accordingly.

---

## CI/CD INTEGRATION

### GitHub Actions

```yaml
- name: Run Production E2E Test
  run: ./scripts/test-production-e2e.sh
  env:
    AZURE_OPENAI_ENDPOINT: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    AZURE_OPENAI_API_KEY: ${{ secrets.AZURE_OPENAI_API_KEY }}
    SARVAM_AI_API_KEY: ${{ secrets.SARVAM_AI_API_KEY }}
    AZURE_STORAGE_ACCOUNT: ${{ secrets.AZURE_STORAGE_ACCOUNT }}
    AZURE_STORAGE_KEY: ${{ secrets.AZURE_STORAGE_KEY }}
```

### Parse JUnit Results

```bash
# View XML results
cat reports/e2e/production-e2e-results.xml
```

---

## PERFORMANCE BENCHMARKS

| Metric | Target | Actual |
|--------|--------|--------|
| Total Duration | < 3 min | ~45s |
| Azure OCR | < 30s | ~15s |
| Azure LLM | < 10s | ~3s |
| QuickBooks Mock | < 1s | ~150ms |
| Salesforce Mock | < 1s | ~150ms |

---

## NEXT STEPS

After passing this test:

1. ✅ Review reports in `reports/e2e/`
2. ✅ Verify all 10 steps passed
3. ✅ Check QuickBooks mock received bill
4. ✅ Check Salesforce mock received log
5. ✅ Verify Qdrant has vector (use Qdrant dashboard)
6. ✅ Ready for production deployment!

---

**Last Updated:** March 5, 2026  
**Version:** 1.0
