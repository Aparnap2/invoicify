# Invoicify: Hybrid Edge-Native Architecture

# # Executive Summary

**"The Decoupled Brain"** - Event-driven hybrid system combining Edge performance with Python AI engineering excellence.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INVOICIFY HYBRID STACK                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌──────────────────────────────────────────────────┐  │
│  │  CLOUDFLARE │     │              IBM CODE ENGINE                      │  │
│  │   PAGES     │────▶│              (Python AI Worker)                   │  │
│  │   (Vite)    │     │                                                      │  │
│  └─────────────┘     │  ┌──────────────────────────────────────────────┐  │  │
│         │            │  │  LangGraph Workflows                         │  │  │
│         │            │  │  • Analyst-Critic Pattern                    │  │  │
│         ▼            │  │  • DSPy Prompt Optimization                  │  │  │
│  ┌─────────────┐     │  │  • Instructor Structured Outputs             │  │  │
│  │  WORKERS    │     │  │  • Fastembed Local Embeddings               │  │  │
│  │  (Hono +    │     │  └──────────────────────────────────────────────┘  │  │
│  │   tRPC)     │     │                        │                           │  │
│  └─────────────┘     │                        ▼                           │  │
│         │            │              ┌─────────────────┐                    │  │
│         │            │              │  GROQ (Free)    │                    │  │
│         ▼            │              │  or Qwen API    │                    │  │
│  ┌─────────────┐     │              └─────────────────┘                    │  │
│  │     D1      │     └────────────────────────────────────────────────────┘  │
│  │  (SQLite)   │                            │                                 │
│  └─────────────┘                            ▼                                 │
│         │                      ┌─────────────────────────┐                   │
│         │                      │   KNOWLEDGE LAYER       │                   │
│         ▼                      ├─────────────────────────┤                   │
│  ┌─────────────┐               │  Qdrant (Vectors)      │                   │
│  │  UPSTASH    │               │  Neo4j Aura (Graph)    │                   │
│  │   KAFKA     │               └─────────────────────────┘                   │
│  │   QUEUE     │                                                          │
│  └─────────────┘                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```text
---

# # Architecture Principles

1. **Edge Performance** - Frontend and ingestion on Cloudflare Workers
2. **Python AI Excellence** - Keep `instructor`, `dspy`, `fastembed`, `langgraph`
3. **Event-Driven** - Kafka/Queues decouple frontend from AI processing
4. **Serverless AI** - IBM Code Engine for scale-to-zero Python containers
5. **$0 Cost** - All free tiers with no infrastructure costs

---

# # Component Breakdown

## # 1. Edge Layer (Cloudflare Workers)

**Role:** Fast ingestion, API gateway, user interaction

| Component | Technology | Purpose |
| ----------- | ----------- | --------- |
| Frontend | Vite + React | User interface |
| API Gateway | Hono + tRPC | Type-safe API |
| Database | D1 (SQLite) | User/Org/Invoice metadata |
| Vision | Workers AI | Quick first-pass OCR |
| Queues | Upstash Kafka | Async message passing |


**Key Files:**
- `worker/src/index.ts` - Main Hono app
- `worker/src/routes/extract.ts` - OCR extraction endpoint
- `worker/src/db/schema.ts` - D1 schema
- `worker/src/lib/redpanda.ts` - Kafka producer

**Environment Variables:**
```bash
# Cloudflare Wrangler
CLOUDFLARE_DATABASE_ID=xxx
CLOUDFLARE_KV_CACHE_ID=xxx

# Upstash Kafka
UPSTASH_KAFKA_REST_URL=https://xxx.upstash.io
UPSTASH_KAFKA_REST_USERNAME=xxx
UPSTASH_KAFKA_REST_PASSWORD=xxx

# Workers AI
AI_BINDING=AI
```text
## # 2. Async Bridge (Upstash Kafka)

**Role:** Decouple frontend from AI processing

**Topics:**

| Topic | Purpose | Payload |
| ------- | --------- | --------- |
| `invoice.uploaded` | New invoice uploaded | `{invoice_id, user_id, image_url, trace_id}` |
| `invoice.extracted` | OCR completed | `{invoice_id, raw_text, confidence}` |
| `invoice.processed` | AI processing done | `{invoice_id, extracted_data, risk_score}` |


**Producer Code:**
```typescript
// worker/src/lib/kafka-producer.ts
import { Kafka } from "@upstash/kafka";

const kafka = new Kafka({
  url: process.env.UPSTASH_KAFKA_REST_URL,
  username: process.env.UPSTASH_KAFKA_REST_USERNAME,
  password: process.env.UPSTASH_KAFKA_REST_PASSWORD,
});

export async function publishInvoiceUploaded(invoice: {
  id: string;
  userId: string;
  imageUrl: string;
  traceId: string;
}) {
  const p = kafka.producer();
  await p.produce("invoice.uploaded", {
    key: invoice.id,
    value: {
      ...invoice,
      timestamp: new Date().toISOString(),
    },
  });
}
```text
## # 3. AI Core (IBM Code Engine + Python)

**Role:** Deep thinking, structured extraction, risk analysis

**Why IBM Code Engine?**
- Scale-to-zero (no cold start cost)
- Docker native
- Consistent with "IBM Hero" narrative
- No timeout limits (unlike Workers)

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

EXPOSE 8000

# Start Kafka consumer
CMD ["python", "-m", "app.consumer"]
```text
**requirements.txt:**
```txt
# Web Framework
fastapi==0.115.0
uvicorn[standard]==0.32.0
python-multipart==0.0.20

# Kafka
aiokafka==0.10.0

# AI / LLM
openai==1.55.0  # Compatible with Groq, Qwen, Ollama
langgraph==1.0.0
langchain-core==0.3.0
instructor==1.0.0  # Structured outputs
dspy==2.5.0  # Prompt optimization

# Vector Search
fastembed==0.5.0  # Local embeddings
qdrant-client==1.12.0

# Graph Database
neo4j==5.20.0

# OCR
Pillow==10.0.0
pytesseract==0.3.13

# Utilities
pydantic==2.10.0
pydantic-settings==2.0.0
httpx==0.28.0
python-dotenv==1.0.0
loguru==0.7.2

# Observability
langfuse==3.0.0
```text
**Consumer Code:**
```python
# app/consumer.py
import asyncio
from app.services.kafka import KafkaConsumer
from app.services.extraction import InvoiceExtractor
from app.services.langgraph import InvoiceWorkflow
from app.config import get_settings

async def main():
    settings = get_settings()
    consumer = KafkaConsumer("invoice.uploaded")
    workflow = InvoiceWorkflow()
    extractor = InvoiceExtractor()

    async for message in consumer:
        invoice_id = message["key"]
        trace_id = message["value"]["traceId"]

        # 1. Extract using Workers AI results or fallback
        raw_text = message["value"].get("raw_text")
        if not raw_text:
            raw_text = await extractor.extract_from_url(
                message["value"]["imageUrl"]
            )

        # 2. Process through LangGraph workflow
        result = await workflow.process_invoice(
            invoice_data={
                "vendor_name": extracted.vendorName,
                "total_amount": extracted.totalAmount,
            },
            raw_content=raw_text,
            thread_id=trace_id,
        )

        # 3. Publish result
        await publish_to_kafka("invoice.processed", {
            "invoice_id": invoice_id,
            "result": result.model_dump(),
        })

if __name__ == "__main__":
    asyncio.run(main())
```text
## # 4. Knowledge Layer

**Qdrant (Vector Search):**
```python
# app/services/qdrant.py
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import numpy as np

class InvoiceVectorStore:
    def __init__(self):
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )
        self.collection = "invoice_embeddings"

    async def search_similar(self, query: str, limit: int = 5):
        # Generate embedding using Fastembed
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        query_embedding = list(model.embed_documents([query]))[0]

        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_embedding,
            limit=limit,
        )
        return results
```text
**Neo4j Aura (Graph Knowledge):**
```python
# app/services/neo4j.py
from neo4j import GraphDatabase

class VendorGraph:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
        )

    async def add_trust_episode(self, vendor_id: str, episode: dict):
        """Add a trust/reliability episode for a vendor."""
        async with self.driver.session() as session:
            await session.run("""
                MERGE (v:Vendor {id: $vendor_id})
                CREATE (v)-[:HAS_EPISODE {
                    type: $type,
                    description: $description,
                    timestamp: datetime(),
                    outcome: $outcome
                }]->(:Episode)
            """, vendor_id=vendor_id, **episode)

    async def get_vendor_history(self, vendor_id: str) -> list[dict]:
        """Get all episodes for a vendor."""
        async with self.driver.session() as session:
            result = await session.run("""
                MATCH (v:Vendor {id: $vendor_id})-[:HAS_EPISODE]->(e:Episode)
                RETURN e ORDER BY e.timestamp DESC
            """, vendor_id=vendor_id)
            return [dict(record["e"]) async for record in result]
```text
---

# # Data Flow

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                              REQUEST FLOW                                     │
└──────────────────────────────────────────────────────────────────────────────┘

1. UPLOAD
   User ──▶ Cloudflare Pages ──▶ Workers (Hono) ──▶ D1 (save metadata)
                                                      │
                                                      ▼
                                              Upstash Kafka: invoice.uploaded
                                                      │
                                                      ▼
2. PROCESS (Async - IBM Code Engine)
   Kafka Consumer ──▶ Groq/Qwen API ──▶ LangGraph Workflow
           │
           ├──▶ Instructor (Structured Extraction)
           ├──▶ DSPy (Prompt Optimization)
           ├──▶ Fastembed (Embeddings)
           ├──▶ Qdrant (Semantic Search)
           └──▶ Neo4j (Trust History)
                                                      │
                                                      ▼
                                              Upstash Kafka: invoice.processed
                                                      │
                                                      ▼
3. NOTIFY
   WebSocket ──▶ Frontend (Real-time update)
   or
   Poll ──▶ Workers API (Get status)

```text
---

# # Environment Variables

## # Cloudflare Workers
```bash
# .env for wrangler
CLOUDFLARE_DATABASE_ID=xxx
CLOUDFLARE_KV_CACHE_ID=xxx
UPSTASH_KAFKA_REST_URL=https://xxx.upstash.io
UPSTASH_KAFKA_REST_USERNAME=xxx
UPSTASH_KAFKA_REST_PASSWORD=xxx
ENVIRONMENT=production
```text
## # IBM Code Engine (Python Worker)
```bash
# Dockerfile or IBM CE Config
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/invoicify

# Kafka
UPSTASH_KAFKA_REST_URL=https://xxx.upstash.io
UPSTASH_KAFKA_REST_USERNAME=xxx
UPSTASH_KAFKA_REST_PASSWORD=xxx

# LLM - Choose One
# GROQ (Recommended - Fastest)
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=gsk_xxx
LLM_MODEL=llama-3.2-90b-vision

# OR Qwen (Cheapest)
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxx
LLM_MODEL=qwen-max

# OR Local Ollama (Development)
OPENAI_BASE_URL=http://localhost:11434/v1/
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2-vision

# Knowledge Layer
QDRANT_URL=https://xxx.cloud.qdrant.io
QDRANT_API_KEY=xxx
NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=xxx

# Observability
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```text
---

# # Deployment Steps

## # Phase 1: Cloudflare Setup
1. Create Cloudflare Pages project (Vite build output)
2. Deploy Workers with Wrangler
3. Create D1 database and apply migrations
4. Set up Upstash Kafka topics

## # Phase 2: IBM Code Engine Setup
1. Build Docker image locally
2. Push to IBM Container Registry
3. Create Code Engine application
4. Configure environment variables
5. Set up scaling (0 to N replicas)

## # Phase 3: Knowledge Layer Setup
1. Create Qdrant Cloud cluster
2. Create Neo4j Aura database
3. Verify connection from Python worker

## # Phase 4: Integration Testing
1. Upload invoice → Check Kafka message
2. Verify Python worker processes message
3. Check LangGraph workflow completion
4. Verify data in Qdrant + Neo4j

---

# # Cost Analysis ($0)

| Service | Free Tier | Monthly Cost |
| --------- | ----------- | -------------- |
| Cloudflare Pages | Unlimited bandwidth | $0 |
| Cloudflare Workers | 100K requests/day | $0 |
| Cloudflare D1 | 5GB storage | $0 |
| Upstash Kafka | 10K messages/day | $0 |
| IBM Code Engine | Scale-to-zero | $0 |
| Qdrant Cloud | 1 cluster, 1GB | $0 |
| Neo4j Aura Free | 1 instance | $0 |
| Groq API | 2M tokens/day | $0 |
| **TOTAL** |  | **$0/mo** |


---

# # Portfolio Narrative

> "**Invoicify** demonstrates my ability to architect **event-driven hybrid systems** that combine edge performance with AI engineering excellence.
>
> **Architecture Decisions:**
> - **Edge Layer:** Cloudflare Workers for low-latency ingestion and API routing
> - **Async Bridge:** Kafka decouples frontend from compute-heavy AI processing
> - **AI Core:** Python worker with LangGraph, Instructor, and DSPy for sophisticated reasoning
> - **Knowledge Layer:** Qdrant for semantic search, Neo4j for graph-based vendor trust tracking
>
> **Why This Stack?**
> - Kept **Python AI tooling** (Instructor, DSPy) instead of migrating to JS
> - Used **IBM Code Engine** for serverless Python containers (no cold start timeouts)
> - **Decoupled architecture** enables independent scaling of edge and AI layers
>
> **Key Technologies:**
> - LangGraph (Python) for complex workflow orchestration
> - Instructor for robust structured LLM outputs
> - DSPy for self-optimizing prompts
> - Fastembed for local embedding generation
> - Upstash Kafka for event streaming
>
> This project showcases both **Edge Computing** (Cloudflare mastery) and **AI Engineering** (advanced Python patterns) - the complete Senior Engineer skillset."

---

# # Files to Modify/Create

## # Cloudflare Worker
- `worker/src/index.ts` - Hono + tRPC setup
- `worker/src/lib/kafka-producer.ts` - Upstash producer
- `worker/src/routes/extract.ts` - OCR + Kafka publish
- `worker/wrangler.toml` - Environment config

## # Python Worker
- `ai/Dockerfile` - Container definition
- `ai/consumer.py` - Kafka consumer entrypoint
- `ai/app/main.py` - FastAPI (optional, for health checks)
- `ai/app/services/kafka.py` - Consumer implementation
- `ai/app/services/extraction.py` - Invoice extraction
- `ai/app/services/langgraph.py` - Workflow orchestration
- `ai/app/services/qdrant.py` - Vector search
- `ai/app/services/neo4j.py` - Graph operations

## # Shared
- `IMPLEMENTATION_PLAN.md` - This architecture document
- `.env.example` - Environment variable template

---

# # Success Metrics

1. **Latency:** Edge responses < 100ms
2. **Throughput:** Handle 100 concurrent uploads
3. **Reliability:** 99% successful extractions
4. **Cost:** $0 monthly infrastructure cost

---

# # Timeline

| Phase | Duration | Deliverable |
| ------- | ---------- | ------------- |
| Phase 1 | 1 day | Cloudflare Workers + D1 + Upstash |
| Phase 2 | 2 days | Python Worker on IBM Code Engine |
| Phase 3 | 1 day | LangGraph + Instructor + DSPy |
| Phase 4 | 1 day | Qdrant + Neo4j integration |
| Phase 5 | 1 day | Testing + Documentation |
| **TOTAL** | **6 days** | Production-ready system |
