# Nivi Enterprise Architecture (IBM + Temporal + WarpStream)

# # 1. High-Level Design (HLD)

## # Executive Summary
Nivi is a **Serverless Enterprise Finance Agent** designed for high throughput, durable execution, and zero idle cost. It leverages the **IBM Cloud Free Tier** for compute/storage, **Temporal Cloud** for orchestration, and **WarpStream** for stateless event streaming.

**Current State Integration:**
- Existing LangGraph workflow with Analyst-Critic pattern → **Migrate to Temporal Workflows**
- Neo4j knowledge graph → **Keep as-is**, integrate via Temporal Activities
- Cloudflare Workers edge layer → **Keep for ingestion**, publish to WarpStream
- Qdrant vector search → **Keep as-is**, access via Temporal Activities

## # Core Principles
1. **Stateless Compute:** All workers run on IBM Code Engine (Scale-to-Zero)
2. **Durable State:** All business logic wrapped in Temporal Workflows
3. **Separation of Storage:** Data Lake (IBM COS) decoupled from Compute
4. **Online Learning:** ML models update incrementally via River

## # Architecture Diagram

```mermaid
graph TD

| Upload Invoice |
| Push Event |


    subgraph IBM Cloud Free Tier

| Store Segments |


        subgraph Code Engine Serverless Containers
            Worker[Python Temporal Worker]
            ML[River ML Model]
        end
    end

    subgraph Control Plane

| Trigger |
| Heartbeat |

    end

| Read/Write |
| Vector Search |
| Inference |

| Update |


    style CF fill:#f9f,stroke:#333,stroke-width:2px
    style Temp fill:#bbf,stroke:#333,stroke-width:2px
    style WS fill:#bfb,stroke:#333,stroke-width:2px
```text
---

# # 2. Low-Level Design (LLD)

## # 2.1 The Event Spinal Cord (WarpStream)

**Protocol:** Kafka v3.0+ compatible
**Deployment:** Docker container running `warpstream agent` on IBM Code Engine
**Backend:** IBM COS `s3.us-south.cloud-object-storage.appdomain.cloud`

**Topic Topology:**

| Topic | Purpose | Retention | Partition |
| ------- | --------- | ----------- | ----------- |
| `invoice.ingested` | Raw payload JSON + Image URL | 7 days | 3 |
| `invoice.risk_scored` | River ML anomaly scores | 30 days | 3 |
| `invoice.processed` | Final structured data for ERP | 90 days | 3 |
| `invoice.approval_needed` | Human-in-the-loop trigger | 1 day | 1 |
| `trust.updated` | Vendor trust battery changes | Forever | 1 |


**WarpStream Agent Config:**
```yaml
# warpstream-config.yaml
agent:
  region: "us-south"
  bucket: "nivi-warpstream-prod"
  credentials:
    type: "iam"
    api_key: "${IBM_CLOUD_API_KEY}"

storage:
  type: "s3"
  endpoint: "s3.us-south.cloud-object-storage.appdomain.cloud"

logging:
  level: "info"
  format: "json"
```text
## # 2.2 The Brain (Temporal Worker)

**Language:** Python 3.11
**Base:** Existing LangGraph workflow migrated to Temporal

**Workflow Definition:** `InvoiceProcessingWorkflow`

```python
# temporal/workflows/invoice_workflow.py
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta

@workflow.defn
class InvoiceProcessingWorkflow:
    @workflow.run
    async def run(self, invoice_data: InvoiceInput) -> ProcessingResult:
        # Activity 1: Extract data using Groq/Llama Vision
        extracted = await workflow.execute_activity(
            extract_invoice_data,
            invoice_data.image_url,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
                non_retryable_error_types=["InvalidImageError"]
            )
        )

        # Activity 2: Detect anomaly using River ML
        risk_score = await workflow.execute_activity(
            detect_anomaly,
            {
                "amount": extracted.total_amount,
                "vendor_id": extracted.vendor_name
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Activity 3: Check runway impact via Neo4j
        runway_impact = await workflow.execute_activity(
            check_runway_impact,
            extracted.total_amount,
            start_to_close_timeout=timedelta(seconds=5),
        )

        # Activity 4: Analyst-Critic evaluation
        decision = await workflow.execute_activity(
            evaluate_with_agents,
            {
                "extracted": extracted,
                "risk_score": risk_score,
                "runway_impact": runway_impact
            },
            start_to_close_timeout=timedelta(seconds=15),
        )

        # Human-in-the-loop if needed
        if decision.requires_approval:
            approval = await workflow.execute_activity(
                request_human_approval,
                decision,
                start_to_close_timeout=timedelta(hours=24),
            )

            # Wait for signal from human
            approval_signal = await workflow.wait_for_external_signal(
                "approval_response",
                timeout=timedelta(hours=48)
            )

        # Finalize
        return await workflow.execute_activity(
            finalize_invoice,
            FinalizeInput(
                extracted=extracted,
                decision=decision,
                approval=approval_signal if decision.requires_approval else None
            )
        )
```text
**Activity Implementations:**

| Activity | Purpose | Timeout | Retry |
| ---------- | --------- | --------- | ------- |
| `extract_invoice_data` | Vision LLM extraction | 30s | 3x |
| `detect_anomaly` | River ML scoring | 10s | 2x |
| `check_runway_impact` | Neo4j graph query | 5s | 3x |
| `evaluate_with_agents` | Analyst-Critic logic | 15s | 2x |
| `request_human_approval` | Send notification | 5s | 5x |
| `finalize_invoice` | Update Neo4j, Qdrant | 10s | 3x |


## # 2.3 The ML Layer (River + IBM Watson)

**Library:** `river` (Online Machine Learning)
**Model:** `river.anomaly.HalfSpaceTrees`
**State Storage:** IBM COS

**Training Loop:**
```python
# temporal/activities/anomaly_detection.py
import pickle
import ibm_boto3
from river import anomaly

async def detect_anomaly(amount: float, vendor_id: str) -> float:
    """Detect anomaly using incremental learning."""

    # Load model state from IBM COS
    cos_client = ibm_boto3.client(
        service_name='s3',
        ibm_api_key_id=os.getenv('IBM_CLOUD_API_KEY'),
        ibm_service_instance_id=os.getenv('IBM_COS_INSTANCE_ID'),
        config=Config(signature_version='oauth'),
        endpoint_url='https://s3.us-south.cloud-object-storage.appdomain.cloud'
    )

    model_key = f"ml-models/{vendor_id}.pkl"

    try:
        response = cos_client.get_object(
            Bucket='nivi-lake-prod',
            Key=model_key
        )
        model = pickle.loads(response['Body'].read())
    except:
        # Initialize new model
        model = anomaly.HalfSpaceTrees(
            n_trees=10,
            height=8,
            window_size=100
        )

    # Predict anomaly score
    features = {'amount': amount}
    score = model.score_one(features)

    # Learn from this observation
    model.learn_one(features)

    # Save updated model asynchronously
    model_bytes = pickle.dumps(model)
    cos_client.put_object(
        Bucket='nivi-lake-prod',
        Key=model_key,
        Body=model_bytes
    )

    return score
```text
---

# # 3. Data Schema

## # 3.1 IBM COS (Data Lake)

**Bucket:** `nivi-lake-prod`

```text
nivi-lake-prod/
├── raw/
│   ├── {date}/
│   │   ├── {invoice_id}.pdf
│   │   └── {invoice_id}.json      # Metadata
├── processed/
│   ├── {date}/
│   │   ├── {invoice_id}.json      # Structured extraction
│   │   └── {invoice_id}_audit.log # Decision trail
├── ml-models/
│   ├── {vendor_id}.pkl            # River model state
│   └── global.pkl                 # Global anomaly model
└── temp/
    └── {workflow_id}/             # Temporary processing files
```text
## # 3.2 Neo4j (Graph)

**Nodes:**
```cypher
// Vendor node
(:Vendor {
  id: string,
  name: string,
  trust_level: int,        // 1=Probation, 2=Standard, 3=Core
  created_at: datetime,
  total_invoices: int,
  total_amount: float
})

// Invoice node
(:Invoice {
  id: string,
  amount: float,
  currency: string,
  status: string,          // APPROVED, REJECTED, PENDING
  created_at: datetime,
  processed_at: datetime,
  risk_score: float
})

// Episode node (for temporal trust tracking)
(:Episode {
  id: string,
  type: string,            // PAYMENT, DISPUTE, REVIEW
  description: string,
  outcome: string,         // SUCCESS, FAILURE
  timestamp: datetime
})
```text
**Edges:**
```cypher
// Vendor sends invoice
(:Vendor)-[:SENT {timestamp: datetime}]->(:Invoice)

// Invoice has risk assessment
(:Invoice)-[:HAS_RISK {score: float, model: string}]->(:RiskScore)

// Vendor has trust episodes
(:Vendor)-[:HAS_EPISODE]->(:Episode)

// Invoice processed by workflow
(:Invoice)-[:PROCESSED_BY {workflow_id: string, duration_ms: int}]->(:Workflow)
```text
## # 3.3 Qdrant (Vector Search)

**Collection:** `invoice_embeddings`

```python
{
  "name": "invoice_embeddings",
  "vectors": {
    "size": 384,              # BAAI/bge-small-en-v1.5
    "distance": "Cosine"
  },
  "payload_schema": {
    "invoice_id": "keyword",
    "vendor_name": "keyword",
    "amount": "float",
    "status": "keyword",
    "created_at": "datetime"
  }
}
```text
---

# # 4. Migration from Existing Code

## # 4.1 Current → Target Mapping

| Current Component | Target Component | Migration Strategy |
| ------------------ | ------------------ | ------------------- |
| LangGraph `InvoiceWorkflow` | Temporal `InvoiceProcessingWorkflow` | Wrap nodes as Temporal Activities |
| `analyst.py` | `evaluate_with_agents` Activity | Keep logic, wrap in Activity |
| `critic.py` | `evaluate_with_agents` Activity | Keep logic, wrap in Activity |
| Neo4j client | Neo4j Activity | Keep as-is, add retry logic |
| Upstash Kafka | WarpStream | Update producer/consumer configs |
| Ollama LLM | Groq API | Update client configuration |
| FastAPI service | Temporal Worker | Remove HTTP layer, add Worker |


## # 4.2 Code Reuse Strategy

**Reusable Components (90% reuse):**
```text
ai/app/agents/analyst.py      → temporal/activities/agents.py
ai/app/agents/critic.py       → temporal/activities/agents.py
ai/app/services/neo4j_client  → temporal/activities/neo4j.py
ai/app/services/qdrant.py     → temporal/activities/qdrant.py
ai/app/services/trust_battery → temporal/activities/trust.py
ai/app/schemas/invoice.py     → temporal/schemas.py (keep)
```text
**Modified Components (50% reuse):**
```text
ai/app/graphs/invoice_workflow.py → temporal/workflows/invoice.py
ai/app/main.py                    → temporal/worker.py (remove FastAPI)
```text
**New Components:**
```text
temporal/activities/anomaly.py    # River ML integration
temporal/activities/extraction.py # Groq API integration
temporal/infrastructure/ibm_cos.py # IBM COS client
temporal/infrastructure/warpstream.py # Kafka consumer
```text
---

# # 5. Security Architecture

## # 5.1 Authentication & Authorization

**Temporal Cloud:**
- mTLS certificates for Worker authentication
- Namespace-level access control
- API keys stored in IBM Secrets Manager

**IBM Cloud:**
- IAM roles for Code Engine
- Service-to-service authentication
- Secrets in IBM Secrets Manager

**WarpStream:**
- SASL/SSL encryption
- Topic-level ACLs
- No credentials in code

## # 5.2 Data Protection

**PII Handling:**
- Redaction before leaving extraction activity
- Encryption at rest in IBM COS
- Field-level encryption in Neo4j

**Network Security:**
- All services use TLS 1.3
- VPC for IBM Code Engine
- Private endpoints where possible

---

# # 6. Monitoring & Observability

## # 6.1 Metrics

**Temporal Metrics:**
- Workflow success/failure rate
- Activity execution duration
- Signal latency

**Application Metrics:**
- Invoice processing volume
- Anomaly detection accuracy
- Trust battery updates

**Infrastructure Metrics:**
- IBM Code Engine container scaling
- IBM COS request rates
- WarpStream lag

## # 6.2 Logging

**Structured JSON Logs:**
```json
{
  "timestamp": "2025-02-08T10:30:00Z",
  "level": "INFO",
  "service": "temporal-worker",
  "workflow_id": "invoice-123",
  "activity": "extract_invoice_data",
  "duration_ms": 1250,
  "invoice_id": "inv-456",
  "vendor": "Acme Corp",
  "amount": 5000.00
}
```text
## # 6.3 Tracing

**OpenTelemetry Integration:**
- Workflow execution traces
- Activity spans
- External service calls (Groq, Neo4j)

---

# # 7. Disaster Recovery

## # 7.1 Backup Strategy

**IBM COS:**
- Cross-region replication
- Versioning enabled
- 30-day retention

**Neo4j Aura:**
- Daily automated backups
- Point-in-time recovery
- 7-day retention

**Temporal:**
- Workflow history retention: 30 days
- Automatic replay on recovery

## # 7.2 Failover

**Worker Failover:**
- Temporal automatically reschedules activities
- Stateless workers can scale horizontally
- Dead letter queue for failed messages

**Service Degradation:**
- Graceful degradation if Groq unavailable
- Fallback to rule-based extraction
- Queue messages for later processing

---

# # 8. Cost Optimization

## # 8.1 IBM Cloud Free Tier Limits

| Service | Free Tier | Current Usage |
| --------- | ----------- | --------------- |
| Code Engine | 100K vCPU-seconds/month | ~50K |
| COS | 25GB storage | ~5GB |
| Watson (optional) | 1000 API calls/month | 0 |


## # 8.2 Cost Reduction Strategies

1. **Scale-to-Zero:** Workers idle when no workflows
2. **Batch Processing:** Group small invoices
3. **Cache Hit:** Cache vendor models in memory
4. **Smart Scheduling:** Process during off-peak hours

## # 8.3 Estimated Monthly Cost

| Component | Cost |
| ----------- | ------ |
| IBM Code Engine | $0 (free tier) |
| IBM COS | $0 (free tier) |
| Temporal Cloud | $0 (free tier - 1 namespace) |
| Neo4j Aura | $0 (free tier) |
| Qdrant Cloud | $0 (free tier) |
| Groq API | $0 (2M tokens/day free) |
| **Total** | **$0/month** |


---

# # 9. Performance Benchmarks

## # 9.1 Target SLIs

| Metric | Target | Measurement |
| -------- | -------- | ------------- |
| End-to-end latency | < 5s | Workflow start to completion |
| Extraction accuracy | > 95% | Ground truth comparison |
| Anomaly detection precision | > 90% | True positive rate |
| Workflow availability | 99.9% | Uptime over 30 days |
| Throughput | 100 invoices/min | Concurrent processing |


## # 9.2 Optimization Strategies

1. **Parallel Activities:** Run extraction and anomaly check concurrently
2. **Caching:** Cache vendor trust levels for 1 hour
3. **Connection Pooling:** Reuse Neo4j and Qdrant connections
4. **Async I/O:** All activities use async/await
5. **Batch Inserts:** Batch Neo4j writes

---

# # 10. Future Enhancements

## # 10.1 Roadmap

**Phase 2 (Month 2):**
- Multi-currency support
- Advanced anomaly models (ensemble)
- Real-time dashboard

**Phase 3 (Month 3):**
- Slack bot integration
- Automatic payment scheduling
- Vendor onboarding workflow

**Phase 4 (Month 4):**
- ML model versioning
- A/B testing for extraction models
- Custom model training

## # 10.2 Scalability Limits

**Current Architecture Limits:**
- 1000 invoices/day (Temporal free tier)
- 10 concurrent workflows (Code Engine)
- 25GB data lake (COS free tier)

**Upgrade Path:**
- Temporal Cloud paid tier: $50/month
- Code Engine: $0.0001/vCPU-second
- COS: $0.02/GB/month

---

# # Appendix A: Technology Stack Summary

| Layer | Technology | Version | Purpose |
| ------- | ----------- | --------- | --------- |
| Orchestration | Temporal Cloud | Latest | Durable workflows |
| Compute | IBM Code Engine | Latest | Serverless containers |
| Storage | IBM COS | Latest | Data lake |
| Streaming | WarpStream | Latest | Kafka-compatible events |
| Graph DB | Neo4j Aura | 5.x | Knowledge graph |
| Vector DB | Qdrant Cloud | Latest | Similarity search |
| ML | River | 0.21+ | Online learning |
| LLM | Groq API | Latest | Vision + text |
| Language | Python | 3.11 | Worker implementation |
| Edge | Cloudflare Workers | Latest | Ingestion layer |


---

# # Appendix B: Glossary

- **Activity:** Temporal unit of work (function execution)
- **Workflow:** Temporal durable execution unit
- **Signal:** Async message to running workflow
- **WarpStream:** Stateless Kafka-compatible streaming
- **River:** Online machine learning library
- **HITL:** Human-in-the-loop
- **SLI:** Service Level Indicator

---

*Document Version: 1.0*
*Last Updated: 2025-02-08*
*Author: AI Architecture Team*
