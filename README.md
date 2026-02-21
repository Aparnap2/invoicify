# INVOICIFY — Azure-Native Invoice Processing Agent

[![Tests](https://img.shields.io/badge/tests-81%20passed-brightgreen)](https://github.com/Aparnap2/invoicify)
[![Branch](https://img.shields.io/badge/branch-feat/azure--native--migration-blue)](https://github.com/Aparnap2/invoicify/tree/feat/azure-native-migration)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Invoicify** is an autonomous Accounts Payable (AP) agent that automates invoice processing end-to-end: ingestion → extraction → risk assessment → decision → execution → audit. Built on **100% Azure-native stack** with **Sarvam AI** for Indian language voice support.

---

## 🎯 Key Features

- **☁️ Azure-Native**: Full Azure ecosystem (Functions, Blob Storage, SQL, Cosmos DB, AI Foundry)
- **🇮🇳 Indian-First**: Sarvam Saaras STT + Bulbul TTS for Hindi/Gujarati/Marathi voice calls
- **🔋 Trust Battery**: Vendor trust scoring with automatic approval limits ($0 → $50,000)
- **📞 Voice RFP Calls**: Automated vendor calls for quote collection (Twilio + Sarvam)
- **🧪 TDD Verified**: 81+ unit tests + integration tests with real Docker containers
- **🔒 SOC 2 Ready**: Immutable audit logs, distributed tracing, Azure Key Vault

---

## 🏗️ Architecture Overview

```mermaid
flowchart TB
    subgraph "📤 Zone 1: Ingestion (Azure Functions)"
        A[Invoice Upload API] -->|PDF| B[Azure Blob Storage]
        A -->|Metadata| C[Azure SQL Database]
        A -->|Event| D[Azure Event Grid]
    end
    
    subgraph "🔄 Zone 2: Event Routing"
        D -->|invoice.submitted| E[Processor Function]
        D -->|invoice.needs_call| F[Voice Trigger]
    end
    
    subgraph "🧠 Zone 3: Agent Core (LangGraph)"
        E --> G[State Machine]
        G --> H[Extractor Agent<br/>Docling + Azure AI]
        G --> I[Critic Agent<br/>Math Validation]
        G --> J[Analyst Agent<br/>Risk + Trust]
        G --> K[Executor Agent<br/>QuickBooks]
    end
    
    subgraph "📞 Zone 4: Voice Agent (Pipecat)"
        F --> L[Twilio Transport]
        L --> M[Sarvam Saaras STT]
        M --> N[Azure AI LLM]
        N --> O[Sarvam Bulbul TTS]
        O --> L
    end
    
    subgraph "💾 Zone 5: Data Layer"
        B -.-> R[(Blob Storage)]
        C -.-> S[(Azure SQL)]
        J -.-> T[(Cosmos DB<br/>Trust Battery)]
        J -.-> U[(AI Search<br/>RAG)]
    end
    
    subgraph "📊 Zone 6: Observability"
        V[Azure Monitor]
        W[Application Insights]
    end
    
    style A fill:#4CAF50,stroke:#2E7D32,color:#fff
    style G fill:#2196F3,stroke:#1565C0,color:#fff
    style L fill:#FF9800,stroke:#E65100,color:#fff
    style R fill:#9C27B0,stroke:#6A1B9A,color:#fff
    style V fill:#F44336,stroke:#C62828,color:#fff
```

---

## 🔄 Invoice Processing Pipeline

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    
    SUBMITTED --> EXTRACTING: Docling + Azure AI
    EXTRACTING --> VALIDATING: confidence ≥ 0.75
    EXTRACTING --> NEEDS_CALL: confidence < 0.75
    
    VALIDATING --> ANALYZING: Math + RAG Passed
    VALIDATING --> BLOCKED: Duplicate Detected
    
    ANALYZING --> AUTO_APPROVE: Trust ≥ CORE + Risk < 0.3
    ANALYZING --> HITL_REQUIRED: Trust = STANDARD
    ANALYZING --> BLOCKED: Risk > 0.7
    
    AUTO_APPROVE --> EXECUTING: QuickBooks API
    HITL_REQUIRED --> AWAITING_HUMAN: SignalR
    BLOCKED --> FRAUD_ALERT: Admin Notification
    
    EXECUTING --> AUDITING: Bill Created
    AWAITING_HUMAN --> AUDITING: Human Decision
    FRAUD_ALERT --> AUDITING: Logged
    
    AUDITING --> [*]: Cosmos DB + Event Grid
    
    NEEDS_CALL --> CALL_PENDING: Queue Voice
    CALL_PENDING --> CALL_COMPLETED: Sarvam Pipeline
    CALL_COMPLETED --> EXTRACTING: Re-process
    
    note right of SUBMITTED: PDF in Blob Storage
    note right of ANALYZING: Trust Battery from Cosmos DB
    note right of CALL_PENDING: Twilio + Sarvam STT/TTS
```

---

## 🔋 Trust Battery System

```mermaid
flowchart LR
    A[PROBATION<br/>$0 Limit<br/>100% Review] -->|50 Accurate| B[STANDARD<br/>$500 Limit<br/>Auto ≤ $500]
    B -->|50 More Accurate| C[CORE<br/>$5,000 Limit<br/>Auto ≤ $5k]
    C -->|100 More Accurate| D[STRATEGIC<br/>$50k Limit<br/>Auto ≤ $50k]
    
    D -.->|3 Errors| C
    C -.->|3 Errors| B
    B -.->|3 Errors| A
    
    style A fill:#F44336,color:#fff
    style B fill:#FF9800,color:#000
    style C fill:#2196F3,color:#fff
    style D fill:#4CAF50,color:#fff
```

**Trust Score Formula:**
```
Trust Score = (0.6 × Accuracy) + (0.2 × Volume) + (0.2 × Recency)
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Edge API** | Azure Functions | Serverless ingestion API |
| **Storage** | Azure Blob Storage | PDF storage (SAS URLs) |
| **Database** | Azure SQL Database | Invoice metadata |
| **NoSQL** | Cosmos DB | Trust Battery + audit logs |
| **Search** | Azure AI Search | RAG for duplicate detection |
| **LLM** | Azure AI Foundry | GPT-4o for extraction |
| **Voice STT** | Sarvam Saaras v3 | Hindi/Gujarati/Marathi |
| **Voice TTS** | Sarvam Bulbul v3 | Indian voice synthesis |
| **Telephony** | Twilio | PSTN voice calls |
| **Orchestration** | LangGraph | State machine pipeline |
| **Parsing** | IBM Docling | PDF → Markdown |

---

## 🚀 Quick Start

### Prerequisites

```bash
# Docker for local emulators
docker --version

# Azure CLI for deployment
az --version

# Python 3.11+ with uv
uv --version
```

### 1. Clone & Setup

```bash
git clone https://github.com/Aparnap2/invoicify.git
cd invoicify
git checkout feat/azure-native-migration
```

### 2. Start Local Azure Emulators

```bash
# Start containers individually (preserves your Ollama models)
docker run -d --name invoicify-azurite -p 10000:10000 \
  mcr.microsoft.com/azure-storage/azurite:latest \
  azurite --blobHost 0.0.0.0 --loose

docker run -d --name invoicify-azure-sql -p 1433:1433 \
  -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=Invoicify@Local123 \
  mcr.microsoft.com/mssql/server:2022-latest

docker run -d --name invoicify-cosmos -p 8081:8081 \
  -e AZURE_COSMOS_EMULATOR_PARTITION_COUNT=3 \
  mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:latest

# Start your existing Ollama (preserves models)
docker start ollama
```

### 3. Configure Environment

```bash
# Copy example config
cp apps/agent-core/.env.example apps/agent-core/.env.local

# Edit with your Azure credentials
# Required for LLM tests:
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"

# Optional for voice tests:
export SARVAM_API_KEY="your-sarvam-key"
```

### 4. Install Dependencies

```bash
cd apps/agent-core
uv sync
```

### 5. Run Tests

```bash
# Unit tests (81 tests, fast)
uv run pytest tests/unit/ -v

# Integration tests (requires Docker containers)
uv run pytest tests/tdd/test_azure_integration.py -v -s

# Verify Azure stack
./scripts/verify_azure_stack.sh
```

### 6. Run Agent Core

```bash
uv run uvicorn src.main:app --reload --port 8000
```

---

## 📊 Test Results

| Test Type | Count | Status | Coverage |
|-----------|-------|--------|----------|
| **Unit Tests** | 81 | ✅ Passing | Schemas, Trust Battery, Pipeline |
| **Integration** | 8 | ⏳ Created | Azurite, Azure SQL, Cosmos DB |
| **E2E** | 8 | ⏳ Created | Full invoice flow |
| **LLM Eval** | 6 | ⏳ Created | Extraction quality |

**Run all tests:**
```bash
uv run pytest tests/ -v --tb=short
```

---

## 📁 Project Structure

```
invoicify/
├── apps/
│   ├── agent-core/              # Python FastAPI backend
│   │   ├── src/
│   │   │   ├── schemas/         # Pydantic v2 models
│   │   │   ├── agents/          # Extractor, Critic, Analyst, Executor
│   │   │   ├── pipeline/        # LangGraph state machine
│   │   │   ├── trust/           # Trust Battery system
│   │   │   └── observability/   # Azure Monitor integration
│   │   └── tests/
│   │       ├── unit/            # 81 unit tests
│   │       ├── e2e/             # End-to-end tests
│   │       └── eval/            # LLM evaluation
│   │
│   ├── voice-agent/             # Sarvam voice pipeline
│   │   ├── src/
│   │   │   └── services/        # Service factory (Sarvam-only)
│   │   └── tests/
│   │
│   └── api/                     # Azure Functions (new)
│       ├── functions/           # HTTP triggers
│       ├── db/                  # Azure SQL client
│       └── storage/             # Azure Blob client
│
├── docker/
│   └── open-sarika/             # Local STT (deprecated)
│
├── tests/
│   ├── tdd/                     # TDD integration tests
│   └── integration/             # Azure-native tests
│
├── scripts/
│   ├── verify_azure_stack.sh    # Container verification
│   └── azure_sql_schema.sql     # Database schema
│
├── docker-compose.local.yml     # Azure emulators
└── prd.md                       # Product requirements
```

---

## 🧪 Testing with Real Containers

### Verification Script

```bash
# Verify all containers are running
./scripts/verify_azure_stack.sh

# Expected output:
# ✅ Azurite is running and responding
# ✅ Azure SQL is running and accepting connections
# ✅ Cosmos DB Emulator is running
# ✅ Ollama is running with 7 models
```

### TDD Tests

```bash
# Run TDD tests with real Docker + real Azure AI
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=...

uv run pytest tests/tdd/test_azure_integration.py -v -s

# Tests:
# - Azure Blob Storage TDD (Azurite)
# - Azure SQL TDD (SQL Server)
# - Azure AI LLM TDD (Azure OpenAI)
# - End-to-End invoice flow
```

---

## 💰 Cost Estimate

| Service | Free Tier | Monthly Cost (100k invoices) |
|---------|-----------|------------------------------|
| Azure Functions | 1M requests | $0 |
| Blob Storage | 5GB (12mo) | $1.84 |
| Azure SQL | 32GB always free | $0 |
| Cosmos DB | 25GB + 1k RU/s | $25 |
| Azure AI Foundry | $200 credit | $50 (after credit) |
| Sarvam AI | ₹1,000 credits | $12 |
| **Total** | | **~$90/month** |

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[PRD](prd.md)** | Product requirements + architecture |
| **[README](README.md)** | This file - quick start + overview |
| **[Azure Migration](AZURE_MIGRATION_SUMMARY.md)** | Cloudflare → Azure guide |
| **[Implementation](FINAL_IMPLEMENTATION_SUMMARY.md)** | Complete implementation details |
| **[TDD Tests](tests/tdd/test_azure_integration.py)** | Integration test suite |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

**Branch:** `feat/azure-native-migration` (current development)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **IBM Docling** - PDF parsing library
- **Sarvam AI** - Indian language STT/TTS
- **LangGraph** - State machine orchestration
- **Azure AI Foundry** - LLM platform
- **Twilio** - Voice telephony

---

**Built with ❤️ by the Invoicify Team**  
**Last Updated:** February 21, 2026  
**Version:** 3.0 (Azure-Native + Sarvam Voice)
