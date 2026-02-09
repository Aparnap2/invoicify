# Nivi Development Plan (Phased Execution)

# # Overview

This development plan leverages **existing codebase** and migrates it to the IBM + Temporal + WarpStream architecture. **Total Timeline: 10 days** with 70% code reuse from current implementation.

---

# # Phase 1: Foundation & Infrastructure (Days 1-2)

## # Goal
Set up IBM Cloud, Temporal Cloud, and WarpStream. Verify connectivity.

## # Day 1: IBM Cloud Setup

**Morning (4 hours):**
- [ ] Create IBM Cloud account (if not exists)
- [ ] Create IBM Cloud Object Storage bucket `nivi-lake-prod`
- [ ] Create IBM Code Engine project `nivi-prod`
- [ ] Create API key with COS and CE permissions
- [ ] Test COS connectivity from local Python

```bash
# Verify COS connectivity
pip install ibm-cos-sdk
python -c "
import ibm_boto3
from ibm_botocore.config import Config
client = ibm_boto3.client(
    service_name='s3',
    ibm_api_key_id='YOUR_API_KEY',
    endpoint_url='https://s3.us-south.cloud-object-storage.appdomain.cloud'
)
print(client.list_buckets())
"
```text
**Afternoon (4 hours):**
- [ ] Create IBM Secrets Manager instance
- [ ] Store secrets: API keys, Neo4j credentials, Qdrant key
- [ ] Create service-to-service IAM policies
- [ ] Document secret names and structure

**Deliverables:**
- IBM Cloud dashboard screenshot showing all services
- COS bucket created and accessible
- Secrets stored in Secrets Manager
- API keys documented (in secure location)

## # Day 2: Temporal & WarpStream Setup

**Morning (4 hours):**
- [ ] Register for Temporal Cloud (free tier)
- [ ] Create namespace `nivi-prod`
- [ ] Generate mTLS certificates
- [ ] Store certificates in IBM Secrets Manager
- [ ] Install Temporal CLI (`temporal`)
- [ ] Test connection to Temporal Cloud

```bash
# Install Temporal CLI

|  |


# Verify connection
temporal operator namespace list --address your-namespace.tmprl.cloud:7233 \
  --tls-cert-path certs/client.pem \
  --tls-key-path certs/client.key
```text
**Afternoon (4 hours):**
- [ ] Deploy WarpStream Agent to IBM Code Engine
- [ ] Create WarpStream configuration
- [ ] Create Kafka topics:
  - `invoice.ingested`
  - `invoice.risk_scored`
  - `invoice.processed`
  - `invoice.approval_needed`
  - `trust.updated`
- [ ] Test produce/consume from local laptop

```bash
# Deploy WarpStream Agent
ibmcloud ce application create --name warpstream-agent \
  --image warpstreamlabs/warpstream:latest \
  --env BUCKET=nivi-warpstream \
  --env IBM_API_KEY="${IBM_CLOUD_API_KEY}"

# Test connectivity
kcat -b localhost:9092 -L
kcat -b localhost:9092 -t invoice.ingested -P <<< '{"test": true}'
```text
**Deliverables:**
- Temporal namespace created and accessible
- mTLS certificates generated and stored
- WarpStream Agent running in Code Engine
- Kafka topics created and tested
- Local connectivity verified

---

# # Phase 2: Temporal Worker Migration (Days 3-4)

## # Goal
Migrate existing LangGraph workflow to Temporal with 90% code reuse.

## # Day 3: Core Worker Setup

**Morning (4 hours):**
- [ ] Create new directory structure: `temporal/`
- [ ] Set up Python virtual environment
- [ ] Install dependencies:
  ```
  temporalio==1.6.0
  river==0.21.0
  ibm-cos-sdk==2.13.0
  neo4j==5.15.0
  qdrant-client==1.7.0
  groq==0.4.0
  ```
- [ ] Create `temporal/workflows/invoice.py` (migrate from `ai/app/graphs/invoice_workflow.py`)
- [ ] Create `temporal/activities/` directory

**Afternoon (4 hours):**
- [ ] Migrate Analyst agent to Activity:
  ```python
  # temporal/activities/agents.py
  from temporalio import activity
  from app.agents.analyst import get_analyst_agent  # Reuse existing

  @activity.defn
  async def analyst_evaluate(invoice_data: dict) -> AnalystProposal:
      agent = get_analyst_agent()
      return await agent.analyze(InvoiceExtracted(**invoice_data))
  ```
- [ ] Migrate Critic agent to Activity (same pattern)
- [ ] Create `temporal/worker.py` (entry point)
- [ ] Test locally with Temporal dev server

```bash
# Start Temporal dev server
temporal server start-dev

# Run worker locally
python temporal/worker.py

# Test workflow execution
temporal workflow start --type InvoiceProcessingWorkflow \
  --task-queue invoice-queue \
  --input '{"invoice_id": "test-123", "amount": 1000}'
```text
**Deliverables:**
- Temporal Worker running locally
- Analyst and Critic activities working
- Workflow executes end-to-end in dev mode

## # Day 4: Activities Migration

**Morning (4 hours):**
- [ ] Migrate Neo4j client to Activity:
  - Create `temporal/activities/neo4j.py`
  - Wrap existing `ai/app/clients/neo4j_client.py`
  - Add retry logic and error handling
- [ ] Migrate Qdrant client to Activity:
  - Create `temporal/activities/qdrant.py`
  - Wrap existing `ai/app/services/qdrant.py`
- [ ] Create trust battery Activity
- [ ] Test all activities individually

**Afternoon (4 hours):**
- [ ] Create extraction Activity:
  ```python
  @activity.defn
  async def extract_invoice_data(image_url: str) -> InvoiceExtracted:
      """Extract invoice using Groq Vision API."""
      from groq import Groq
      client = Groq(api_key=os.getenv('GROQ_API_KEY'))

      # Download image from URL
      # Call Groq Llama Vision
      # Parse response into InvoiceExtracted
  ```
- [ ] Create anomaly detection Activity (River ML)
- [ ] Create runway impact Activity
- [ ] Wire all activities into workflow
- [ ] Full workflow test with sample invoice

**Deliverables:**
- All 8 activities implemented and tested
- Workflow executes complete pipeline
- Sample invoice processed successfully

---

# # Phase 3: ML & Intelligence Layer (Day 5)

## # Goal
Integrate River ML for anomaly detection and implement online learning.

## # Day 5: River ML Integration

**Morning (4 hours):**
- [ ] Create `temporal/activities/anomaly.py`:
  ```python
  import pickle
  import ibm_boto3
  from river import anomaly, compose, preprocessing

  @activity.defn
  async def detect_anomaly(amount: float, vendor_id: str) -> dict:
      # Load model from IBM COS
      model = await load_model_from_cos(vendor_id)

      # Predict
      features = {'amount': amount}
      score = model.score_one(features)

      # Learn
      model.learn_one(features)

      # Save back to COS
      await save_model_to_cos(vendor_id, model)

      return {
          'score': score,
          'is_anomaly': score > 0.7,
          'vendor_id': vendor_id
      }
  ```
- [ ] Create IBM COS helper functions
- [ ] Initialize global model (across all vendors)
- [ ] Test anomaly detection with synthetic data

**Afternoon (4 hours):**
- [ ] Integrate anomaly detection into workflow
- [ ] Create decision routing based on anomaly score:
  - Score < 0.3: Auto-approve eligible
  - Score 0.3-0.7: Standard review
  - Score > 0.7: Flag for HITL
- [ ] Update Analyst-Critic logic to include anomaly score
- [ ] Test with 10 sample invoices:
  - Normal amounts: $100, $200, $150
  - Anomalous amounts: $10,000, $50,000
- [ ] Verify models are being saved to COS

```bash
# Verify models in COS
ibmcloud cos objects --bucket nivi-lake-prod --prefix ml-models/
```text
**Deliverables:**
- River ML anomaly detection working
- Models persist to IBM COS
- Anomaly scores influence workflow routing
- 10 sample invoices processed with correct routing

---

# # Phase 4: Human-in-the-Loop & Integration (Day 6)

## # Goal
Implement HITL approval flow and integrate with existing Cloudflare Workers.

## # Day 6: HITL & Edge Integration

**Morning (4 hours):**
- [ ] Create HITL Activity:
  ```python
  @activity.defn
  async def request_human_approval(decision: DecisionResult) -> None:
      # Publish to Kafka topic
      producer.send('invoice.approval_needed', {
          'invoice_id': decision.invoice_id,
          'reason': decision.reason,
          'risk_score': decision.risk_score
      })
  ```
- [ ] Add signal handler to workflow:
  ```python
  @workflow.signal
  async def approval_response(self, approved: bool, comments: str) -> None:
      self.approval_result = {
          'approved': approved,
          'comments': comments
      }
  ```
- [ ] Update workflow to wait for signal
- [ ] Create approval timeout (48 hours)

**Afternoon (4 hours):**
- [ ] Update Cloudflare Worker to publish to WarpStream:
  ```typescript
  // Update worker/src/lib/kafka-producer.ts
  import { Kafka } from "kafkajs";

  const kafka = new Kafka({
    brokers: [process.env.WARPSTREAM_BROKER],
    ssl: true,
    sasl: {
      mechanism: 'plain',
      username: process.env.WARPSTREAM_USERNAME,
      password: process.env.WARPSTREAM_PASSWORD
    }
  });
  ```
- [ ] Create approval endpoint in Worker:
  ```typescript
  app.post('/api/invoices/:id/approve', async (c) => {
    const { id } = c.req.param();
    const { approved, comments } = await c.req.json();

    // Send signal to Temporal workflow
    await temporalClient.workflow.signal(
      'InvoiceProcessingWorkflow',
      'approval_response',
      { approved, comments }
    );

    return c.json({ success: true });
  });
  ```
- [ ] Test end-to-end: Upload → Kafka → Temporal → HITL → Approval

**Deliverables:**
- HITL flow working with signals
- Cloudflare Worker publishes to WarpStream
- Approval API endpoint working
- Full integration test passing

---

# # Phase 5: Deployment & Testing (Days 7-8)

## # Goal
Deploy to IBM Code Engine, run comprehensive tests, and verify production readiness.

## # Day 7: Deployment

**Morning (4 hours):**
- [ ] Create Dockerfile for Temporal Worker:
  ```dockerfile
  FROM python:3.11-slim

  WORKDIR /app

  # Install system dependencies
  RUN apt-get update && apt-get install -y \
      gcc \
      libpq-dev \
      && rm -rf /var/lib/apt/lists/*

  # Copy requirements
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  # Copy code
  COPY temporal/ ./temporal/
  COPY ai/app/ ./ai/app/  # For reused components

  # Environment variables
  ENV PYTHONPATH=/app
  ENV TEMPORAL_HOST=your-namespace.tmprl.cloud:7233
  ENV TEMPORAL_NAMESPACE=nivi-prod

  CMD ["python", "-m", "temporal.worker"]
  ```
- [ ] Build Docker image locally
- [ ] Push to IBM Container Registry
- [ ] Create Code Engine application

```bash
# Build and push
ibmcloud cr login
docker build -t us.icr.io/nivi-prod/temporal-worker:v1 .
docker push us.icr.io/nivi-prod/temporal-worker:v1

# Deploy to Code Engine
ibmcloud ce application create \
  --name temporal-worker \
  --image us.icr.io/nivi-prod/temporal-worker:v1 \
  --cpu 0.5 \
  --memory 1G \
  --min-scale 1 \
  --max-scale 5 \
  --env-from-secret TEMPORAL_CERT \
  --env-from-secret TEMPORAL_KEY \
  --env-from-secret IBM_CLOUD_API_KEY \
  --env-from-secret NEO4J_PASSWORD \
  --env-from-secret QDRANT_API_KEY \
  --env-from-secret GROQ_API_KEY
```text
**Afternoon (4 hours):**
- [ ] Deploy WarpStream Agent (if not done)
- [ ] Verify all services running
- [ ] Configure health checks
- [ ] Set up log aggregation (IBM Log Analysis)
- [ ] Create monitoring dashboards

**Deliverables:**
- Temporal Worker deployed to Code Engine
- WarpStream Agent running
- All secrets configured
- Health checks passing
- Logs flowing to Log Analysis

## # Day 8: Testing

**Morning (4 hours):**
- [ ] Run unit tests:
  ```bash
  cd temporal && pytest tests/ -v --cov
  ```
- [ ] Run integration tests:
  ```bash
  pytest tests/integration/ -v
  ```
- [ ] Run Temporal replay tests:
  ```bash
  pytest tests/temporal/ -v
  ```
- [ ] Verify 184+ existing tests still pass

**Afternoon (4 hours):**
- [ ] Run E2E tests:
  ```bash
  cd fullstack && pnpm exec playwright test
  ```
- [ ] Load test with 100 concurrent invoices:
  ```bash
  # Use k6 or artillery
  k6 run load-test.js
  ```
- [ ] Chaos test: Kill worker mid-processing, verify Temporal resumes
- [ ] Verify all tests pass

**Deliverables:**
- All 184+ tests passing
- E2E tests passing
- Load test results (target: 100 invoices/min)
- Chaos test passed

---

# # Phase 6: Documentation & Launch (Days 9-10)

## # Goal
Complete documentation, runbook, and production launch.

## # Day 9: Documentation

**Morning (4 hours):**
- [ ] Update README.md with new architecture
- [ ] Create OPERATIONS.md:
  - How to scale workers
  - How to debug failed workflows
  - How to update ML models
  - How to handle alerts
- [ ] Create TROUBLESHOOTING.md:
  - Common errors and solutions
  - How to replay workflows
  - How to handle stuck workflows
- [ ] Document all environment variables

**Afternoon (4 hours):**
- [ ] Create architecture diagrams (update existing)
- [ ] Create sequence diagrams for key flows
- [ ] Document API endpoints
- [ ] Create onboarding guide for new developers

## # Day 10: Launch

**Morning (4 hours):**
- [ ] Final security audit
- [ ] Verify all secrets rotated
- [ ] Enable production monitoring
- [ ] Set up alerting (PagerDuty/Slack)
- [ ] Create runbook for on-call

**Afternoon (4 hours):**
- [ ] Production smoke test
- [ ] Process first real invoice
- [ ] Verify end-to-end flow
- [ ] Monitor for 2 hours
- [ ] Document any issues
- [ ] Celebrate! 🎉

---

# # Test Strategy

## # Unit Tests (184+ existing)
```bash
# Python AI service
cd ai && pytest tests/ -v

# Temporal activities
cd temporal && pytest tests/ -v

# Worker (TypeScript)
cd worker && pnpm test
```text
## # Integration Tests
```bash
# Test Temporal workflow replay
pytest tests/temporal/test_replay.py -v

# Test Kafka produce/consume
pytest tests/integration/test_kafka.py -v

# Test IBM COS connectivity
pytest tests/integration/test_cos.py -v
```text
## # E2E Tests
```bash
# Frontend tests
cd fullstack && pnpm exec playwright test

# Full pipeline test
python tests/e2e/test_full_pipeline.py
```text
## # Load Tests
```bash
# 100 invoices/minute
k6 run --vus 10 --duration 5m load-test.js
```text
---

# # Rollback Plan

## # If Issues Detected
1. **Immediate:** Scale Code Engine workers to 0
   ```bash
   ibmcloud ce application update --name temporal-worker --min-scale 0
   ```
2. **Short-term:** Switch Cloudflare Worker to queue mode (store for later)
3. **Long-term:** Revert to previous version
   ```bash
   ibmcloud ce application update --name temporal-worker --image us.icr.io/nivi-prod/temporal-worker:v0
   ```

## # Rollback Criteria
- Error rate > 5%
- Latency > 30s p95
- Data loss detected
- Security incident

---

# # Success Metrics

| Metric | Target | Measurement |
| -------- | -------- | ------------- |
| End-to-end latency | < 5s | Temporal workflow duration |
| Extraction accuracy | > 95% | Manual review of sample |
| Anomaly precision | > 90% | True positive rate |
| System availability | 99.9% | Uptime monitoring |
| Throughput | 100/min | Load test |
| Cost | $0 | Monthly bill |
| Test pass rate | 100% | All 184+ tests |


---

# # Risk Mitigation

| Risk | Mitigation |
| ------ | ----------- |
| IBM Cloud service limits | Monitor usage, have upgrade path ready |
| Temporal Cloud limits | Use free tier wisely, upgrade if needed |
| Groq API rate limits | Implement backoff, fallback to rule-based |
| Data loss | COS versioning, Neo4j backups |
| Security breach | mTLS, field-level encryption, audit logs |


---

# # Appendix: Existing Code Reuse

## # High Reuse (90%+)
- `ai/app/agents/analyst.py` → `temporal/activities/agents.py`
- `ai/app/agents/critic.py` → `temporal/activities/agents.py`
- `ai/app/services/neo4j_client.py` → `temporal/activities/neo4j.py`
- `ai/app/services/qdrant.py` → `temporal/activities/qdrant.py`
- `ai/app/services/trust_battery.py` → `temporal/activities/trust.py`
- `ai/app/schemas/invoice.py` → `temporal/schemas.py`

## # Medium Reuse (50-70%)
- `ai/app/graphs/invoice_workflow.py` → `temporal/workflows/invoice.py`
- `ai/app/main.py` → `temporal/worker.py`

## # New Code (0% reuse)
- `temporal/activities/anomaly.py` (River ML)
- `temporal/activities/extraction.py` (Groq integration)
- `temporal/infrastructure/ibm_cos.py`
- `temporal/infrastructure/warpstream.py`
- Dockerfile and deployment configs

---

# # Daily Standup Template

```text
**Yesterday:**
- Completed: [What was done]
- Blockers: [Any blockers]

**Today:**
- Plan: [What will be done]
- Need help with: [Any assistance needed]

**Metrics:**
- Tests passing: X/Y
- Invoices processed: X
- Issues found: X
```text
---

# # Resources

## # Documentation
- [Temporal Python SDK](https://docs.temporal.io/dev-guide/python)
- [IBM Code Engine](https://cloud.ibm.com/docs/codeengine)
- [WarpStream Docs](https://docs.warpstream.com/)
- [River ML](https://riverml.xyz/)

## # Support Channels
- Temporal Community Slack: #python-sdk
- IBM Cloud Support
- WarpStream Discord

---

*Plan Version: 1.0*
*Timeline: 10 Days*
*Start Date: [TBD]*
*Target Launch: [TBD]*
