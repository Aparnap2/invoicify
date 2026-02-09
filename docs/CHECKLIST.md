# Production Readiness Checklist

**Project:** Nivi Enterprise Finance Agent
**Architecture:** IBM + Temporal + WarpStream
**Version:** 1.0
**Last Updated:** 2025-02-08

---

# # Infrastructure (IBM Free Tier)

## # IBM Cloud Object Storage (COS)
- [ ] Bucket created: `nivi-lake-prod`
- [ ] Bucket created: `nivi-warpstream`
- [ ] Cross-region replication enabled (optional)
- [ ] Versioning enabled
- [ ] Lifecycle policy configured (30-day temp cleanup)
- [ ] IAM policies configured (least privilege)
- [ ] CORS configured (if needed)
- [ ] Encryption at rest enabled (default)
- [ ] Public access blocked

**Verification Command:**
```bash
ibmcloud cos buckets --ibm-api-key "$IBM_CLOUD_API_KEY"
ibmcloud cos bucket-cors --bucket nivi-lake-prod
```text
## # IBM Code Engine
- [ ] Project created: `nivi-prod`
- [ ] Temporal Worker application created
- [ ] WarpStream Agent application created
- [ ] Memory limit: 0.5 vCPU / 1GB RAM (within free tier)
- [ ] Auto-scaling configured (1-5 instances)
- [ ] Health checks configured (HTTP or TCP)
- [ ] Environment variables from Secrets Manager
- [ ] Log forwarding to IBM Log Analysis
- [ ] Application URL accessible

**Verification Command:**
```bash
ibmcloud ce application list
ibmcloud ce application get --name temporal-worker
ibmcloud ce application logs --name temporal-worker --follow
```text
## # IBM Secrets Manager
- [ ] Instance created
- [ ] Secrets created:
  - [ ] `temporal-mtls-cert` (certificate)
  - [ ] `temporal-mtls-key` (private key)
  - [ ] `ibm-cloud-api-key` (IBM API key)
  - [ ] `neo4j-password` (Neo4j Aura password)
  - [ ] `qdrant-api-key` (Qdrant API key)
  - [ ] `groq-api-key` (Groq API key)
- [ ] Secret rotation policy (90 days)
- [ ] Access logging enabled
- [ ] Service-to-service authentication configured

**Verification Command:**
```bash
ibmcloud secrets-manager secrets --sort-by name
```text
---

# # Orchestration (Temporal)

## # Temporal Cloud
- [ ] Namespace created: `nivi-prod`
- [ ] mTLS certificates generated
- [ ] Certificates stored in Secrets Manager
- [ ] Workflow retention: 30 days (configurable)
- [ ] Task queues created:
  - [ ] `invoice-processing-queue`
  - [ ] `approval-queue`
- [ ] Search attributes configured
- [ ] Service account created
- [ ] Audit logging enabled

**Verification Command:**
```bash
temporal operator namespace describe --namespace nivi-prod
temporal task-queue describe --task-queue invoice-processing-queue
```text
## # Worker Configuration
- [ ] Worker connects to Temporal Cloud
- [ ] TLS certificates loaded correctly
- [ ] Worker heartbeats configured (10s default)
- [ ] Max concurrent activities: 10
- [ ] Max concurrent workflows: 5
- [ ] Activity poll timeout: 30s
- [ ] Workflow poll timeout: 30s

**Verification:**
```bash
temporal workflow count --namespace nivi-prod
temporal workflow list --namespace nivi-prod --limit 10
```text
## # Workflow Features
- [ ] Signal handlers implemented (`approval_response`)
- [ ] Query handlers implemented (for status checks)
- [ ] Retry policies configured for all activities
- [ ] Timeouts configured:
  - [ ] Execution timeout: 24 hours
  - [ ] Run timeout: 24 hours
  - [ ] Task timeout: 60 seconds
- [ ] Continue-as-new configured (for long-running workflows)

---

# # Event Streaming (WarpStream)

## # WarpStream Agent
- [ ] Agent deployed to Code Engine
- [ ] Agent healthy and running
- [ ] Connected to IBM COS backend
- [ ] Auto-scaling configured (1-3 instances)
- [ ] Logs forwarded to IBM Log Analysis

**Verification Command:**
```bash
ibmcloud ce application get --name warpstream-agent
kcat -b localhost:9092 -L  # List topics
```text
## # Kafka Topics
- [ ] Topic created: `invoice.ingested` (3 partitions, 7-day retention)
- [ ] Topic created: `invoice.risk_scored` (3 partitions, 30-day retention)
- [ ] Topic created: `invoice.processed` (3 partitions, 90-day retention)
- [ ] Topic created: `invoice.approval_needed` (1 partition, 1-day retention)
- [ ] Topic created: `trust.updated` (1 partition, forever retention)
- [ ] ACLs configured (read/write permissions)
- [ ] Compaction enabled (where appropriate)

**Verification Command:**
```bash

|  |

```text
## # Producer/Consumer
- [ ] Cloudflare Worker publishes to `invoice.ingested`
- [ ] Temporal Worker consumes from `invoice.ingested`
- [ ] Temporal Worker publishes to `invoice.processed`
- [ ] Dead letter queue configured
- [ ] Message serialization (JSON) validated
- [ ] Schema registry (optional) configured

---

# # ML & Data

## # River ML Models
- [ ] HalfSpaceTrees model implemented
- [ ] Model state serializes to IBM COS
- [ ] Model state deserializes correctly
- [ ] Anomaly scores normalized (0.0 to 1.0)
- [ ] Online learning loop working
- [ ] Global model + per-vendor models
- [ ] Model versioning (timestamp in key)
- [ ] Model backup (daily snapshot)

**Verification:**
```bash
ibmcloud cos objects --bucket nivi-lake-prod --prefix ml-models/
python -c "from temporal.activities.anomaly import detect_anomaly; import asyncio; print(asyncio.run(detect_anomaly(1000, 'test-vendor')))"
```text
## # Neo4j Aura
- [ ] Aura instance created
- [ ] Connection encrypted (bolt+s://)
- [ ] Indexes created:
  - [ ] `CREATE INDEX vendor_id FOR (v:Vendor) ON (v.id)`
  - [ ] `CREATE INDEX invoice_id FOR (i:Invoice) ON (i.id)`
- [ ] Constraints created:
  - [ ] `CREATE CONSTRAINT vendor_unique FOR (v:Vendor) REQUIRE v.id IS UNIQUE`
- [ ] Data model documented
- [ ] Backup policy: Daily automated
- [ ] Query performance acceptable (< 100ms)

**Verification:**
```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
with driver.session() as session:
    result = session.run("MATCH (v:Vendor) RETURN count(v) as count")
    print(result.single()["count"])
```text
## # Qdrant Cloud
- [ ] Cluster created
- [ ] Collection created: `invoice_embeddings`
- [ ] Vector size: 384 (BAAI/bge-small-en-v1.5)
- [ ] Distance metric: Cosine
- [ ] Payload indexes created
- [ ] API key secured in Secrets Manager

**Verification:**
```python
from qdrant_client import QdrantClient
client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
print(client.get_collections())
```text
---

# # Security

## # Authentication
- [ ] mTLS for Temporal (certificates valid)
- [ ] API keys stored in Secrets Manager
- [ ] No hardcoded credentials in code
- [ ] Service-to-service authentication configured
- [ ] IBM IAM roles configured (least privilege)

**Verification:**
```bash

| password\ | secret" --include="*.py" | grep -v "\.pyc" | grep -v "getenv\ |

```text
## # Authorization
- [ ] Topic-level ACLs in WarpStream
- [ ] Namespace-level access in Temporal
- [ ] Database-level access (Neo4j, Qdrant)
- [ ] No public access to internal services

## # Data Protection
- [ ] PII redaction before storage
- [ ] Encryption at rest (COS, Neo4j)
- [ ] Encryption in transit (TLS 1.3)
- [ ] Field-level encryption for sensitive data
- [ ] Audit logging enabled
- [ ] GDPR compliance checklist completed

**PII Redaction Verification:**
```python
from temporal.activities.extraction import extract_invoice_data
result = extract_invoice_data("https://example.com/invoice.pdf")
assert "ssn" not in str(result).lower()
assert "credit_card" not in str(result).lower()
```text
## # Network Security
- [ ] VPC configured for Code Engine
- [ ] Private endpoints where available
- [ ] Firewall rules configured
- [ ] DDoS protection enabled (Cloudflare)
- [ ] Rate limiting configured

---

# # Testing

## # Unit Tests (184+ required)
- [ ] Python AI service: 79 tests passing
- [ ] Temporal activities: 50+ tests passing
- [ ] Worker (TypeScript): 65+ tests passing
- [ ] Coverage > 80% for all services

**Verification:**
```bash
cd ai && pytest tests/ -v --cov
cd temporal && pytest tests/ -v --cov
cd worker && pnpm test --coverage
```text
## # Integration Tests
- [ ] Temporal workflow replay tests
- [ ] Kafka produce/consume tests
- [ ] IBM COS connectivity tests
- [ ] Neo4j query tests
- [ ] Qdrant vector search tests
- [ ] Groq API integration tests

**Verification:**
```bash
pytest tests/integration/ -v
```text
## # E2E Tests
- [ ] Frontend tests (9 tests)
- [ ] Full pipeline test
- [ ] HITL flow test
- [ ] Anomaly detection test
- [ ] Approval workflow test

**Verification:**
```bash
cd fullstack && pnpm exec playwright test
cd tests/e2e && python test_full_pipeline.py
```text
## # Load Tests
- [ ] 100 invoices/minute sustained
- [ ] 1000 invoices burst
- [ ] p95 latency < 5s
- [ ] p99 latency < 10s
- [ ] No errors during load test

**Verification:**
```bash
k6 run --vus 10 --duration 5m load-test.js
```text
---

# # Monitoring & Observability

## # Logging
- [ ] Structured JSON logs enabled
- [ ] Log levels configured (INFO in prod)
- [ ] Sensitive data redacted from logs
- [ ] Log forwarding to IBM Log Analysis
- [ ] Log retention: 30 days

**Verification:**
```bash
ibmcloud ce application logs --name temporal-worker --tail 100
```text
## # Metrics
- [ ] Temporal metrics exported
- [ ] Custom application metrics defined
- [ ] IBM Cloud Monitoring configured
- [ ] Dashboards created:
  - [ ] Workflow success/failure rate
  - [ ] Activity execution duration
  - [ ] Invoice processing volume
  - [ ] Anomaly detection rate
  - [ ] System resource usage

## # Alerting
- [ ] Alerts configured for:
  - [ ] Error rate > 5%
  - [ ] Latency > 30s p95
  - [ ] Worker down
  - [ ] Queue lag > 100 messages
  - [ ] COS storage > 20GB
- [ ] Alert destinations:
  - [ ] Slack
  - [ ] Email
  - [ ] PagerDuty (optional)

## # Tracing
- [ ] OpenTelemetry integration
- [ ] Workflow execution traces
- [ ] Activity spans
- [ ] External service calls traced

---

# # Documentation

## # Technical Documentation
- [ ] Architecture document (ENTERPRISE_ARCHITECTURE.md)
- [ ] Development plan (DEV_PLAN.md)
- [ ] API documentation
- [ ] Environment variable reference
- [ ] Database schema documentation
- [ ] Sequence diagrams

## # Operational Documentation
- [ ] Runbook (OPERATIONS.md)
- [ ] Troubleshooting guide (TROUBLESHOOTING.md)
- [ ] Deployment procedures
- [ ] Rollback procedures
- [ ] Incident response plan

## # User Documentation
- [ ] User guide
- [ ] FAQ
- [ ] Training materials (optional)

---

# # Performance

## # Benchmarks
- [ ] End-to-end latency < 5s (p95)
- [ ] Activity execution < 30s each
- [ ] Workflow completion < 60s (typical)
- [ ] Anomaly detection < 1s
- [ ] Extraction < 5s
- [ ] Throughput: 100 invoices/min

## # Resource Usage
- [ ] Memory usage < 1GB per worker
- [ ] CPU usage < 0.5 vCPU per worker
- [ ] COS requests < 1000/day (free tier)
- [ ] Network egress < 1GB/day (free tier)

---

# # Compliance

## # Data Governance
- [ ] Data retention policy defined
- [ ] Data deletion procedures
- [ ] Right to be forgotten implemented
- [ ] Data export capability

## # Audit
- [ ] Audit logging enabled
- [ ] Audit logs retained for 1 year
- [ ] Audit log access controls
- [ ] Regular audit reviews scheduled

---

# # Launch Readiness

## # Pre-Launch
- [ ] Security audit completed
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Monitoring dashboards ready
- [ ] Alerts configured
- [ ] Runbook reviewed
- [ ] Rollback plan tested
- [ ] Team trained on operations

## # Launch Day
- [ ] Smoke tests passing
- [ ] First invoice processed successfully
- [ ] End-to-end flow verified
- [ ] Monitoring active
- [ ] On-call engineer assigned
- [ ] Communication plan ready

## # Post-Launch
- [ ] Monitor for 24 hours
- [ ] Collect feedback
- [ ] Document issues
- [ ] Schedule retrospective

---

# # Sign-Off

| Role | Name | Date | Signature |
| ------ | ------ | ------ | ----------- |
| Tech Lead |  |  |  |
| Security |  |  |  |
| QA Lead |  |  |  |
| Product Manager |  |  |  |
| DevOps |  |  |  |


---

# # Appendix: Quick Verification Commands

```bash
# IBM COS
ibmcloud cos buckets
ibmcloud cos objects --bucket nivi-lake-prod

# Code Engine
ibmcloud ce application list
ibmcloud ce application logs --name temporal-worker

# Temporal
temporal operator namespace list
temporal workflow list --namespace nivi-prod

# Kafka
kcat -b localhost:9092 -L
kcat -b localhost:9092 -t invoice.ingested -P <<< '{"test": true}'

# Tests
cd ai && pytest tests/ -v
cd temporal && pytest tests/ -v
cd worker && pnpm test
cd fullstack && pnpm exec playwright test
```text
---

*This checklist must be completed before production launch.*
*All items must be checked and verified.*
*Any exceptions require documented approval.*
