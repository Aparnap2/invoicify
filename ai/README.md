# Invoicify AI Service

**Proactive Finance Ops AI Agent for Seed–Series A Startups**

AI-powered invoice extraction and processing service built with:
- **FastAPI** - Web framework
- **Pydantic v2** - Data validation
- **LangGraph** - Workflow orchestration with Analyst-Critic pattern
- **Ollama** - Local LLM support (OpenAI-compatible API)
- **Neo4j** - Knowledge graph for vendor relationships

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

### Cash Reconciliation
Fuzzy matching between bank transactions and scheduled payments:
- Amount similarity scoring (50% weight)
- Vendor similarity matching (30% weight)
- Date proximity scoring (20% weight)
- Confidence threshold: 0.8

## Components

```
app/
├── agents/
│   ├── analyst.py      # Pattern detection & proposal generation
│   └── critic.py       # Safety checks with Priority Matrix
├── clients/
│   ├── ollama_client.py # LLM & embeddings via OpenAI SDK
│   └── neo4j_client.py  # Knowledge graph operations
├── services/
│   ├── trust_battery.py    # Vendor trust tracking
│   └── reconciliation.py   # Cash reconciliation
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
| `NEO4J_URI` | Neo4j connection | `neo4j://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `password` |
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

# Ollama
docker run -d --name ollama -p 11434:11434 ollama/ollama
docker exec ollama ollama pull llama3.2-vision
docker exec ollama ollama pull nomic-embed-text
```
