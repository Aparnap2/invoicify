# Invoicify AI Service

**Proactive Finance Ops AI Intern for Seed–Series A Startups**

AI-powered invoice extraction and processing service built with:
- **FastAPI** - Web framework
- **Pydantic v2** - Data validation
- **LangGraph** - Workflow orchestration with Analyst-Critic pattern
- **Langfuse** - Observability for LLM workflows
- **Graphiti + Neo4j** - Temporal Knowledge Graph for episodic memory
- **Postgres + pgvector** - Semantic memory for similarity search
- **Qdrant** - Vector database for semantic search
- **Ollama** - Local LLM support (OpenAI-compatible API)

## Core Philosophy

The Founder has "episodic memory" (what happened when). Invoicify has it too.

The agent stores "Episodes" of business interactions, allowing it to reason about changes over time:

* "We tolerated late payments from Agency X last year because they were new, but now we're strict."
* "This vendor is owned by my investor's brother, so we always pay early."

## Core Architecture

### Analyst-Critic Pattern
The system uses a dual-node safety architecture:

1. **Analyst Agent** - Proposes actions based on historical patterns
   - Pattern detection and anomaly detection
   - Anomaly types: NEW_VENDOR, AMOUNT_SPIKE, AMOUNT_DEVIATION, UNUSUAL_HIGH
   - Proposes: AUTO_APPROVE, HITL_REQUIRED, DELAY_PAYMENT, REJECT

2. **Critic Agent** - Safety checks using Priority Matrix
   - RUNWAY: Cash runway protection (CRITICAL > WARNING > INFO)
   - STRATEGY: Alignment with SURVIVAL/GROWTH/OPTIMIZE modes
   - CONTRACT: Payment terms compliance
   - TRUST: Vendor trust battery level (1=Probation, 2=Standard, 3=Core)
   - BUDGET: Category spending limits

### Trust Battery System
Gradual agent autonomy based on demonstrated accuracy:
| Level | Consecutive Accurate | Auto-Approve Threshold |
|-------|---------------------|------------------------|
| 1 (Probation) | 0-50 | $0 (review all) |
| 2 (Standard) | 50-100 | $500 |
| 3 (Core) | 100+ | $5,000 |

### Temporal Knowledge Graph (Graphiti + Neo4j)
The "Hippocampus" of the agent. Stores evolving relationships over time:

```typescript
// Time-aware edges via Graphiti
(:Vendor)-[:TRUST_STATUS {level: 'PROBATION', valid_from: '2025-01-01', valid_to: '2025-02-01'}]->(:Company)
(:Vendor)-[:TRUST_STATUS {level: 'TRUSTED', valid_from: '2025-02-02'}]->(:Company)
(:Vendor)-[:VIOLATED_TERM {severity: 'HIGH'}]->(:Contract)
```

**Episodic Memory:**
* "Jan 1st: Founder put vendor 'Acme' on probation due to bad service"
* "Jan 12th: Founder overrode probation to pay Acme"
* "Last month you rejected this vendor due to quality - has this been resolved?"

### Cash Reconciliation
Fuzzy matching between bank transactions and scheduled payments:
- Amount similarity scoring (50% weight)
- Vendor similarity matching (30% weight)
- Date proximity scoring (20% weight)
- Confidence threshold: 0.8

### Observability (Langfuse)
Full tracing for invoice processing workflows:

```python
from app.services.langfuse import get_langfuse_client, InvoiceWorkflowTracer

# Tracing is automatic in workflow nodes
# Manual tracing for custom operations:
await InvoiceWorkflowTracer.trace_extraction(
    invoice_id="inv_123",
    raw_content="...",
    extracted_data={"vendor": "Acme", "amount": 500},
    duration_ms=1450.5,
)

await InvoiceWorkflowTracer.trace_workflow_completion(
    invoice_id="inv_123",
    workflow_id="thread_abc",
    final_status="approved",
    duration_ms=2500.0,
)
```

Traced events:
- Workflow execution start/completion
- Field extraction with duration and confidence
- Analyst-Critic reasoning chains
- LLM generation prompts and responses

## The "Money Shot" Demo Flow

1. **Context Setup:** Add episode to Graphiti: "Jan 1st: Founder put vendor 'Acme' on probation due to bad service."

2. **Trigger:** Send an invoice from 'Acme'.

3. **Agent Action:** Agent pauses (HITL). Reason: "Vendor is on probation (Episode Jan 1st)."

4. **Resolution:** Founder approves with override.

5. **Execution:** Stripe Payout succeeded & QBO Bill created.

6. **Update:** Agent writes new episode: "Jan 12th: Founder overrode probation to pay Acme."

## Components

```
app/
├── agents/
│   ├── analyst.py      # Pattern detection & proposal generation
│   └── critic.py       # Safety checks with Priority Matrix
├── clients/
│   ├── ollama_client.py # LLM & embeddings via OpenAI SDK
│   ├── neo4j_client.py  # Knowledge graph operations
│   └── graphiti_client.py # Temporal Knowledge Graph (planned)
├── services/
│   ├── langfuse.py        # Observability tracing
│   ├── trust_battery.py   # Vendor trust tracking
│   ├── reconciliation.py  # Cash reconciliation
│   └── qdrant.py          # Vector search for semantic search
├── graphs/
│   └── invoice_workflow.py # LangGraph StateGraph
└── schemas/
    └── invoice.py       # Pydantic models
```

## Tests

### Integration Tests (Real Services)
```bash
pytest tests/test_integration.py -v
```

### Comprehensive Unit Tests
```bash
pytest tests/test_comprehensive.py -v
```

Test coverage includes:
- Trust Battery: 10 test scenarios
- Analyst Agent: 6 test scenarios
- Critic Agent: 19 test scenarios
- Reconciliation: 12 test scenarios
- End-to-end workflow
- Error handling & graceful degradation
- Debug logging verification

## Setup

```bash
# Create virtual environment with uv
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Run tests
uv run pytest

# Start development server
uv run fastapi dev
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `LLM_MODEL` | Ollama model name | `ollama/llama3.2-vision` |
| `EMBEDDING_MODEL` | Embedding model | `ollama/nomic-embed-text` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | `None` |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | `None` |
| `LANGFUSE_HOST` | Langfuse server URL | `https://cloud.langfuse.com` |
| `NEO4J_URI` | Neo4j connection | `neo4j://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `password` |
| `POSTGRES_URI` | Postgres connection | `postgresql://localhost:5432` |
| `QDRANT_URL` | Qdrant server URL | `http://localhost:6333` |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8001` |
| `DEBUG` | Debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |

## API Endpoints

- `GET /api/v1/health` - Health check
- `POST /api/v1/extract` - Extract invoice data
- `POST /api/v1/process` - Process invoice through workflow
- `POST /api/v1/upload` - Upload invoice file
- `POST /api/v1/approve` - Submit approval decision
- `GET /api/v1/status/{thread_id}` - Get processing status

## Docker Services

Required services (run individually):
```bash
# Neo4j
docker run -d --name neo4j -p 7687:7687 -p 7474:7474 neo4j:latest

# PostgreSQL (for pgvector)
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:15
# Enable pgvector: docker exec -it postgres psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Qdrant (Vector Database)
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant

# Langfuse (Observability - optional, cloud hosted or self-hosted)
# Cloud: Sign up at https://cloud.langfuse.com
# Self-hosted: docker run -d --name langfuse -p 3000:3000 langfuse/langfuse

# Ollama
docker run -d --name ollama -p 11434:11434 ollama/ollama
docker exec ollama ollama pull llama3.2-vision
docker exec ollama ollama pull nomic-embed-text
```

Or use the MDS docker-compose for all services:
```bash
docker-compose -f docker-compose.mds.yml up -d
```
