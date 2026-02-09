# Nivi Test Strategy

**Project:** Nivi Enterprise Finance Agent
**Architecture:** IBM + Temporal + WarpStream
**Version:** 1.0
**Last Updated:** 2025-02-08

---

# # Overview

This test strategy ensures **production-grade reliability** for the Nivi invoice processing system. We maintain **90%+ test coverage** across all components with a focus on **durable execution**, **ML accuracy**, and **end-to-end correctness**.

## # Test Pyramid

```text
        /\
       /  \     E2E Tests (9 tests)
      /----\    Full pipeline validation
     /      \
    /--------\  Integration Tests (50+ tests)
   /          \ Component interactions
  /------------\
 /              \ Unit Tests (184+ tests)
/----------------\ Logic correctness
```text
---

# # 1. Unit Tests (Pytest)

## # Target: Logic correctness for ML, agents, and utilities

### # 1.1 Python AI Service Tests (79 tests)

**PDF Extractor Service**
*File:* `ai/tests/test_pdf_extractor.py`

| Test Class | Tests | Purpose |
| ------------ | ------- | --------- |
| `TestPDFExtractorImports` | 2 | Verify imports work |
| `TestPDFExtractorBasic` | 4 | Basic extraction scenarios |
| `TestExtractedInvoiceModel` | 3 | Pydantic model validation |
| `TestExtractedItemModel` | 2 | Line item extraction |
| `TestPDFExtractResult` | 2 | Result structure validation |
| `TestExtractionModes` | 3 | Different extraction modes |
| `TestPDFExtractorEdgeCases` | 2 | Error handling |
| `TestInvoiceExtraction` | 2 | End-to-end extraction |


**Total: 20 tests**

```python
# Example test
async def test_extract_invoice_from_pdf():
    extractor = PDFExtractor()
    result = await extractor.extract("test_invoice.pdf")

    assert result.success is True
    assert result.data.vendor_name is not None
    assert result.data.total_amount > 0
    assert result.data.overall_confidence > 0.8
```text
**PII Redactor Service**
*File:* `ai/tests/test_pii_redactor.py`

| Test Class | Tests | Purpose |
| ------------ | ------- | --------- |
| `TestPIIRedactorImports` | 2 | Import verification |
| `TestPIIRedactorBasic` | 2 | Basic redaction |
| `TestPIIRedactionPatterns` | 6 | Pattern matching |
| `TestPIIRedactionModes` | 2 | Different modes |
| `TestPIIRedactionInvoice` | 2 | Invoice-specific |
| `TestPIIRedactionResults` | 2 | Result validation |
| `TestPIIRedactionEdgeCases` | 3 | Edge cases |
| `TestPIISpecificPatterns` | 3 | Specific patterns |


**Total: 24 tests**

**LLM Evaluations Service**
*File:* `ai/tests/test_llm_evals.py`

| Test Class | Tests | Purpose |
| ------------ | ------- | --------- |
| `TestEvalsImports` | 2 | Import verification |
| `TestMetricResult` | 2 | Metric structure |
| `TestEvaluationResult` | 2 | Evaluation structure |
| `TestHallucinationMetric` | 4 | Hallucination detection |
| `TestFaithfulnessMetric` | 3 | Faithfulness check |
| `TestAnswerCorrectnessMetric` | 4 | Correctness validation |
| `TestContextualRelevanceMetric` | 4 | Relevance scoring |
| `TestEvaluationPipeline` | 4 | Full pipeline |
| `TestEvaluationThresholds` | 2 | Threshold validation |
| `TestEvaluationReporting` | 2 | Report generation |
| `TestEvaluationEdgeCases` | 4 | Edge cases |
| `TestExtractionTestCase` | 1 | Test case structure |


**Total: 35 tests**

### # 1.2 Temporal Activities Tests (50+ tests)

**Analyst Agent Activity**
*File:* `temporal/tests/activities/test_analyst.py`

```python
# Test: Pattern detection
async def test_analyst_detects_amount_spike():
    """Analyst should flag invoices 2x above vendor average."""
    from temporal.activities.agents import analyst_evaluate

    # Arrange: Vendor history with average $100
    invoice_data = {
        "vendor_name": "Acme Corp",
        "total_amount": 250.00,
        "invoice_number": "INV-001"
    }

    # Act
    proposal = await analyst_evaluate(invoice_data)

    # Assert
    assert proposal.proposed_action == "HITL_REQUIRED"
    assert len(proposal.anomalies) > 0
    assert any(a.type == "AMOUNT_SPIKE" for a in proposal.anomalies)
```text

| Test Case | Input | Expected Output |
| ----------- | ------- | ----------------- |
| Normal amount | $100 (avg $100) | AUTO_APPROVE |
| Medium spike | $200 (avg $100) | HITL_REQUIRED |
| High spike | $500 (avg $100) | HITL_REQUIRED |
| New vendor | No history | HITL_REQUIRED |
| High value | $15,000 | HITL_REQUIRED |
| Low confidence | confidence < 0.8 | HITL_REQUIRED |


**Critic Agent Activity**
*File:* `temporal/tests/activities/test_critic.py`

```python
# Test: Priority matrix
async def test_critic_blocks_on_runway():
    """Critic should block if payment endangers runway."""
    from temporal.activities.agents import critic_review

    # Arrange: Cash $50k, burn $15k/mo, safety $10k
    invoice_data = {
        "total_amount": 45_000,
        "due_date": "2025-02-15"
    }
    financial_context = {
        "current_cash": 50_000,
        "monthly_burn_rate": 15_000,
        "safety_buffer": 10_000
    }

    # Act
    review = await critic_review(invoice_data, financial_context, trust_level=2)

    # Assert
    assert review.blocked is True
    assert any(s.type == "RUNWAY" and s.severity == "CRITICAL" for s in review.signals)
```text

| Priority | Test Case | Input | Expected |
| ---------- | ----------- | ------- | ---------- |
| RUNWAY | Safety buffer | Cash $15k, payment $10k, buffer $10k | BLOCKED |
| RUNWAY | Post-payroll | Payroll in 2 days | WARNING |
| STRATEGY | Survival mode | SURVIVAL mode, >10% cash | CRITICAL |
| CONTRACT | Past due | Due date -5 days | CRITICAL |
| TRUST | Level 1 | Trust level 1 | Manual review |
| BUDGET | Over limit | Category 120% used | CRITICAL |


**Anomaly Detection Activity**
*File:* `temporal/tests/activities/test_anomaly.py`

```python
# Test: Incremental learning
async def test_anomaly_detector_learns():
    """Model should improve with more data."""
    from temporal.activities.anomaly import detect_anomaly

    # Learn normal pattern: $100-$150
    for amount in [100, 110, 105, 120, 115, 130, 125]:
        await detect_anomaly(amount, "vendor-123")

    # Normal amount should have low score
    normal_score = await detect_anomaly(115, "vendor-123")
    assert normal_score['score'] < 0.3

    # Anomalous amount should have high score
    anomaly_score = await detect_anomaly(5000, "vendor-123")
    assert anomaly_score['score'] > 0.7
    assert anomaly_score['is_anomaly'] is True
```text

| Test Case | Data Stream | Anomaly Score |
| ----------- | ------------- | --------------- |
| Normal pattern | [100, 105, 102, 108] | < 0.3 for $105 |
| Anomaly | [100, 105, 102, 5000] | > 0.7 for $5000 |
| Gradual drift | [100, 120, 140, 160] | < 0.5 for $160 |
| New vendor | [] | Medium uncertainty |
| Model persistence | Load from COS | Same scores |


### # 1.3 Worker Tests (TypeScript) (65+ tests)

**Math Critic**
*File:* `worker/src/tests/math.test.ts`

| Test Suite | Tests | Coverage |
| ------------ | ------- | ---------- |
| Math Validation | 34 | 97.65% |


**RLS Policies**
*File:* `worker/src/lib/rls/policies.test.ts`

| Category | Tests |
| ---------- | ------- |
| Permission Checks | 6 |
| Invoice Access Policies | 10 |
| Vendor Access Policies | 3 |
| Data Masking | 6 |
| Query Filtering | 6 |


**Total: 31+ tests**

---

# # 2. Integration Tests

## # Target: Component interactions and external services

### # 2.1 Temporal Workflow Tests

**Workflow Replay**
*File:* `temporal/tests/integration/test_replay.py`

```python
# Test: Durable execution
async def test_workflow_resumes_on_failure():
    """Workflow should resume after worker crash."""
    from temporalio.testing import WorkflowEnvironment

    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Start workflow
        handle = await env.client.start_workflow(
            InvoiceProcessingWorkflow.run,
            InvoiceInput(invoice_id="test-123"),
            id="test-workflow-1",
            task_queue="test-queue"
        )

        # Simulate activity failure (will retry)
        await env.sleep(timedelta(seconds=5))

        # Workflow should still be running
        description = await handle.describe()
        assert description.status == WorkflowExecutionStatus.RUNNING

        # Complete workflow
        result = await handle.result()
        assert result.status == "COMPLETED"
```text

| Test Case | Scenario | Expected Behavior |
| ----------- | ---------- | ------------------- |
| Activity retry | Network failure in extraction | Retry 3x, then succeed |
| Signal handling | Human approval signal | Workflow resumes correctly |
| Timeout | Activity timeout | Workflow handles gracefully |
| Concurrent | Multiple invoices | Processed in parallel |
| Child workflow | Complex invoice spawns child | Parent waits correctly |


### # 2.2 Kafka Integration Tests

**Producer/Consumer**
*File:* `temporal/tests/integration/test_kafka.py`

```python
async def test_invoice_ingestion_flow():
    """Full flow: Produce → Consume → Process."""
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

    # Produce message
    producer = AIOKafkaProducer(bootstrap_servers='localhost:9092')
    await producer.start()
    await producer.send('invoice.ingested', {
        'invoice_id': 'test-123',
        'image_url': 'https://example.com/inv.pdf'
    })
    await producer.stop()

    # Consume and verify
    consumer = AIOKafkaConsumer(
        'invoice.ingested',
        bootstrap_servers='localhost:9092',
        group_id='test-group'
    )
    await consumer.start()
    msg = await consumer.getone()
    data = json.loads(msg.value)
    assert data['invoice_id'] == 'test-123'
    await consumer.stop()
```text

| Test Case | Action | Verification |
| ----------- | -------- | -------------- |
| Produce | Send to `invoice.ingested` | Message received |
| Consume | Read from topic | Data integrity |
| Partitioning | Send 100 messages | Distributed across partitions |
| Error handling | Invalid message | Dead letter queue |


### # 2.3 IBM COS Integration Tests

**Storage Operations**
*File:* `temporal/tests/integration/test_cos.py`

```python
async def test_model_save_and_load():
    """ML model persistence."""
    from temporal.infrastructure.ibm_cos import save_model, load_model
    from river import anomaly

    # Create and save model
    model = anomaly.HalfSpaceTrees()
    model.learn_one({'amount': 100})

    await save_model("test-vendor", model)

    # Load and verify
    loaded = await load_model("test-vendor")
    assert loaded is not None

    # Scores should be consistent
    score1 = model.score_one({'amount': 200})
    score2 = loaded.score_one({'amount': 200})
    assert abs(score1 - score2) < 0.01
```text

| Test Case | Operation | Verification |
| ----------- | ----------- | -------------- |
| Upload | Put model to COS | Object exists |
| Download | Get model from COS | Bytes match |
| List | List objects | Pagination works |
| Delete | Remove object | 404 on get |
| Versioning | Upload same key | Multiple versions |


### # 2.4 Neo4j Integration Tests

**Graph Operations**
*File:* `temporal/tests/integration/test_neo4j.py`

```python
async def test_vendor_trust_evolution():
    """Trust battery updates in graph."""
    from temporal.activities.neo4j import update_vendor_trust

    # Initial state
    await update_vendor_trust("Acme Corp", decision="APPROVED", was_auto_approved=True)

    # Verify in Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run(
            "MATCH (v:Vendor {name: $name}) RETURN v.trust_level",
            name="Acme Corp"
        )
        trust_level = result.single()[0]
        assert trust_level >= 1
```text

| Test Case | Query | Latency |
| ----------- | ------- | --------- |
| Create vendor | MERGE | < 50ms |
| Update trust | SET | < 50ms |
| Get history | MATCH | < 100ms |
| Complex pattern | Multi-hop | < 200ms |


---

# # 3. End-to-End Tests (Playwright)

## # Target: Full system flow from user perspective

### # 3.1 Dashboard Tests
*File:* `fullstack/e2e/dashboard.spec.ts`

```typescript
// Test: Upload and process invoice
test('complete invoice flow', async ({ page }) => {
  // 1. Login
  await page.goto('/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password');
  await page.click('button[type="submit"]');

  // 2. Upload invoice
  await page.goto('/dashboard/upload');
  await page.setInputFiles('input[type="file"]', 'test-invoice.pdf');
  await page.click('button:has-text("Upload")');

  // 3. Wait for processing
  await page.waitForSelector('[data-testid="status-badge"]', {
    state: 'visible',
    timeout: 30_000
  });

  // 4. Verify extraction
  const vendor = await page.textContent('[data-testid="vendor-name"]');
  expect(vendor).toBeTruthy();

  const amount = await page.textContent('[data-testid="total-amount"]');
  expect(amount).toMatch(/\$[\d,]+\.\d{2}/);

  // 5. Check approval status
  const status = await page.textContent('[data-testid="status-badge"]');
  expect(['APPROVED', 'PENDING_REVIEW', 'REJECTED']).toContain(status);
});
```text

| Test Suite | Tests | Status |
| ------------ | ------- | -------- |
| Invoicify Dashboard | 5 | Required |
| Invoicify Invoices Page | 1 | Required |
| Invoicify HITL Page | 1 | Required |
| Invoicify Audit Page | 1 | Required |
| Navigation | 1 | Required |


**Total: 9 tests**

### # 3.2 Full Pipeline Test

**File:** `tests/e2e/test_full_pipeline.py`

```python
async def test_end_to_end_invoice_processing():
    """Full pipeline: Upload → Kafka → Temporal → Approval → Neo4j."""

    # 1. Upload invoice via API
    response = requests.post(
        'https://api.invoicify.com/api/v1/invoices',
        files={'file': open('test-invoice.pdf', 'rb')},
        headers={'Authorization': f'Bearer {token}'}
    )
    invoice_id = response.json()['id']

    # 2. Wait for Kafka message
    consumer = AIOKafkaConsumer('invoice.ingested')
    await consumer.start()
    msg = await asyncio.wait_for(consumer.getone(), timeout=10)
    assert json.loads(msg.value)['invoice_id'] == invoice_id
    await consumer.stop()

    # 3. Wait for Temporal workflow
    handle = temporal_client.get_workflow_handle(f"invoice-{invoice_id}")
    await asyncio.wait_for(handle.result(), timeout=60)

    # 4. Verify Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run(
            "MATCH (i:Invoice {id: $id}) RETURN i.status",
            id=invoice_id
        )
        status = result.single()[0]
        assert status in ['APPROVED', 'PENDING_REVIEW']
```text
---

# # 4. LLM Evaluations (DeepEval)

## # Target: Extraction accuracy and hallucination detection

### # 4.1 Hallucination Metric

**Definition:** Does extracted text exist in source document?

```python
from deepeval.metrics import HallucinationMetric
from deepeval.test_case import LLMTestCase

metric = HallucinationMetric(threshold=0.8)

test_case = LLMTestCase(
    input="Extract invoice data",
    actual_output='{"vendor": "Acme Corp", "amount": 5000}',
    context=["Invoice from Acme Corporation for $5000"]
)

metric.measure(test_case)
assert metric.score > 0.8
assert metric.is_successful()
```text
### # 4.2 JSON Schema Metric

**Definition:** Does output match expected schema?

```python
from deepeval.metrics import JsonCorrectnessMetric

schema = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "total_amount": {"type": "number"},
        "invoice_number": {"type": "string"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"}
                }
            }
        }
    },
    "required": ["vendor_name", "total_amount"]
}

metric = JsonCorrectnessMetric(schema=schema)
```text
### # 4.3 Golden Set

**10 Diverse Invoices (Hand-Labeled):**

| Invoice | Type | Complexity | Expected Fields |
| --------- | ------ | ------------ | ----------------- |
| inv_001 | Simple | Low | Vendor, amount, date |
| inv_002 | Complex | Medium | Multi-page, line items |
| inv_003 | Handwritten | High | OCR challenge |
| inv_004 | Scanned | Medium | Image quality issues |
| inv_005 | Multi-currency | Medium | EUR, GBP handling |
| inv_006 | Poor quality | High | Low resolution |
| inv_007 | Tables | Medium | Table extraction |
| inv_008 | Signature | Low | Signature region |
| inv_009 | Stamp overlay | Medium | Stamped invoice |
| inv_010 | Watermark | Medium | Watermarked |


**Evaluation Schedule:**
- Daily: Automated golden set evaluation
- Weekly: Add new challenging invoices
- Monthly: Retrain/fine-tune if accuracy < 95%

---

# # 5. Load Tests

## # Target: Performance under stress

### # 5.1 Sustained Load

**File:** `tests/load/sustained-load.js`

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up
    { duration: '5m', target: 10 },   // Sustained
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'], // 95% under 5s
    http_req_failed: ['rate<0.05'],    // < 5% errors
  },
};

export default function () {
  const payload = {
    invoice_id: `load-${__VU}-${__ITER}`,
    image_url: 'https://example.com/test-invoice.pdf',
  };

  const res = http.post('https://api.invoicify.com/api/v1/invoices', JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(res, {
    'status is 202': (r) => r.status === 202,
    'response time < 5s': (r) => r.timings.duration < 5000,
  });

  sleep(1);
}
```text
**Target Metrics:**

| Metric | Target | Measurement |
| -------- | -------- | ------------- |
| Throughput | 100 invoices/min | Sustained for 10 min |
| Latency p95 | < 5s | End-to-end |
| Latency p99 | < 10s | End-to-end |
| Error rate | < 5% | HTTP 5xx |
| CPU usage | < 80% | IBM Code Engine |
| Memory usage | < 1GB | Per worker |


### # 5.2 Burst Load

```javascript
export const options = {
  stages: [
    { duration: '30s', target: 100 },   // Burst
    { duration: '1m', target: 100 },    // Sustain burst
    { duration: '30s', target: 0 },     // Recovery
  ],
};
```text
**Target:** Handle 1000 invoices in 2 minutes without errors.

### # 5.3 Chaos Test

**File:** `tests/load/chaos-test.py`

```python
async def test_worker_failure_recovery():
    """Kill worker mid-processing, verify Temporal recovers."""

    # Start workflow
    handle = await client.start_workflow(
        InvoiceProcessingWorkflow.run,
        invoice_input,
        id="chaos-test-1"
    )

    # Wait for activity to start
    await asyncio.sleep(2)

    # Kill worker (simulate crash)
    subprocess.run(['ibmcloud', 'ce', 'application', 'update',
                   '--name', 'temporal-worker', '--min-scale', '0'])

    # Wait
    await asyncio.sleep(5)

    # Restart worker
    subprocess.run(['ibmcloud', 'ce', 'application', 'update',
                   '--name', 'temporal-worker', '--min-scale', '1'])

    # Verify workflow completes
    result = await asyncio.wait_for(handle.result(), timeout=120)
    assert result.status == "COMPLETED"
```text
---

# # 6. Test Environments

## # Environment Matrix

| Environment | Purpose | Data | Scale |
| ------------- | --------- | ------ | ------- |
| Local | Development | Mock | 1 invoice |
| CI/CD | Automated testing | Mock + Synthetic | 10 invoices |
| Staging | Pre-production | Anonymized prod | 100 invoices |
| Production | Live | Real | Production load |


## # Test Data

**Mock Invoices:**
- 50 synthetic PDFs (various layouts)
- 10 handwritten samples
- 5 multi-page documents
- 5 poor quality scans

**Anonymized Production Data:**
- Real invoice structure
- Vendor names hashed
- Amounts perturbed (±10%)
- PII redacted

---

# # 7. Test Automation

## # CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Python Tests

|  |

          cd ai && pytest tests/ -v --cov --cov-report=xml
          cd ../temporal && pytest tests/ -v --cov --cov-report=xml

      - name: TypeScript Tests

|  |

          cd worker && pnpm test --coverage
          cd ../fullstack && pnpm exec playwright test

      - name: Upload Coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    services:
      neo4j:
        image: neo4j:5-community
        env:
          NEO4J_AUTH: neo4j/password
        ports:
          - 7687:7687
      kafka:
        image: confluentinc/cp-kafka:latest
        ports:
          - 9092:9092
    steps:
      - name: Run Integration Tests
        run: pytest tests/integration/ -v

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run E2E Tests

|  |

          cd fullstack
          pnpm exec playwright test

  load-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Run Load Tests
        run: k6 run tests/load/sustained-load.js
```text
## # Coverage Requirements

| Component | Minimum Coverage |
| ----------- | ------------------ |
| Python AI Service | 85% |
| Temporal Activities | 90% |
| TypeScript Worker | 80% |
| Frontend | 70% |
| **Overall** | **85%** |


---

# # 8. Test Maintenance

## # Regular Tasks

**Daily:**
- [ ] Run golden set evaluation
- [ ] Check test pass rate in CI/CD
- [ ] Review flaky tests

**Weekly:**
- [ ] Add tests for new features
- [ ] Update test data
- [ ] Review coverage reports

**Monthly:**
- [ ] Performance benchmark comparison
- [ ] Load test execution
- [ ] Test debt review

## # Flaky Test Protocol

1. **Identify:** Mark test as flaky in CI
2. **Quarantine:** Move to separate suite
3. **Investigate:** Root cause analysis
4. **Fix:** Stabilize test
5. **Reintegrate:** Move back to main suite

---

# # 9. Success Criteria

## # Definition of Done

For any feature to be considered complete:

- [ ] Unit tests written and passing (coverage > 80%)
- [ ] Integration tests for external dependencies
- [ ] E2E test for critical user flow
- [ ] Load test if performance-critical
- [ ] Documentation updated
- [ ] Code review approved
- [ ] CI/CD pipeline green

## # Quality Gates

| Gate | Criteria |
| ------ | ---------- |
| Commit | All unit tests pass |
| PR | Unit + Integration tests pass |
| Merge | All tests pass, coverage > 85% |
| Deploy | E2E tests pass, load test acceptable |


---

# # Appendix: Test Command Reference

```bash
# Unit Tests
cd ai && pytest tests/ -v --cov
cd temporal && pytest tests/ -v --cov
cd worker && pnpm test --coverage

# Integration Tests
pytest tests/integration/ -v

# E2E Tests
cd fullstack && pnpm exec playwright test

# Load Tests
k6 run tests/load/sustained-load.js

# LLM Evals
cd ai && python -m deepeval test run

# All Tests
./scripts/run-all-tests.sh

# Coverage Report
pytest --cov=temporal --cov=ai --cov-report=html
```text
---

*This test strategy ensures Nivi is production-ready with 90%+ coverage and comprehensive validation.*
