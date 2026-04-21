# INVOICIFY — Compliance Document Intelligence Agent

[![Tests](https://img.shields.io/badge/tests-83%20passing-brightgreen)](https://github.com/Aparnap2/invoicify)
[![Branch](https://img.shields.io/badge/branch-feat/azure-native-migration-blue)](https://github.com/Aparnap2/invoicify/tree/feat/azure-native-migration)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-QuickBooks%20%7C%20HubSpot-purple)](https://modelcontextprotocol.io)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║            INVOICIFY — COMPLIANCE DOCUMENT INTELLIGENCE AGENT                ║
║                                                                              ║
║  PDF Documents → Azure Doc Intelligence (OCR) → LangGraph → Trust Battery  ║
║                → Hybrid Search (BM25 + Vector) → MCP → Audit Ledger      ║
║                                                                              ║
║  Processes: Invoices · Contracts · SEBI Circulars · GST Notices         ║
║  99% OCR | Full Citation Trail | 83 Tests | $0/month (12 months free)         ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 🏗️ SYSTEM ARCHITECTURE

### Data Flow Sequence

```mermaid
sequenceDiagram
    participant User
    participant Web as Next.js Frontend
    participant API as FastAPI Agent Core
    participant OCR as Azure Document Intelligence
    participant LLM as OpenRouter LLM
    participant QB as QuickBooks MCP
    participant HS as HubSpot MCP
    participant DB as PostgreSQL
    participant Blob as Azure Blob Storage

    User->>Web: Upload Invoice PDF
    Web->>API: POST /api/v1/invoices
    API->>Blob: Store PDF
    API->>OCR: Extract text (Azure DI)
    OCR-->>API: Markdown output
    API->>LLM: Parse JSON (OpenRouter)
    LLM-->>API: Structured invoice data
    API->>DB: Store invoice
    API->>QB: Create bill (if approved)
    QB-->>API: Bill ID
    API->>HS: Create deal (if approved)
    HS-->>API: Deal ID
    API-->>Web: Success response
    Web-->>User: Invoice processed ✓
```

### MCP Integration Architecture

```mermaid
classDiagram
    class LangGraphAgent {
        +extract_node()
        +fraud_gate_node()
        +citation_node()
        +execute_node()
    }
    
    class MCPServerRegistry {
        +get_erp_tools()
        +_load_quickbooks_tools()
        +_load_hubspot_tools()
    }
    
    class QuickBooksMCP {
        +qb_create_bill()
        +qb_get_vendor()
        +qb_list_accounts()
    }
    
    class HubSpotMCP {
        +hs_create_deal()
        +hs_get_company()
        +hs_update_deal()
    }
    
    LangGraphAgent --> MCPServerRegistry
    MCPServerRegistry --> QuickBooksMCP
    MCPServerRegistry --> HubSpotMCP
```

### Trust Battery State Machine

```mermaid
stateDiagram-v2
    [*] --> PROBATION: New vendor
    PROBATION --> STANDARD: 10 accurate invoices
    STANDARD --> CORE: 50 accurate invoices
    CORE --> STRATEGIC: 100 accurate invoices
    
    state PROBATION {
        [*] --> ManualReview
        ManualReview --> [*]
    }
    
    state STANDARD {
        [*] --> AutoApprove500
        AutoApprove500 --> [*]
    }
    
    state CORE {
        [*] --> AutoApprove5000
        AutoApprove5000 --> [*]
    }
    
    state STRATEGIC {
        [*] --> AutoApprove50000
        AutoApprove50000 --> [*]
    }
```

---

## 📖 TABLE OF CONTENTS

```
├── 1. QUICK START
│   ├── 1.1 Prerequisites
│   ├── 1.2 Local Development
│   └── 1.3 Azure Deployment
├── 2. ARCHITECTURE
│   ├── 2.1 Monorepo Structure
│   ├── 2.2 Azure Services
│   └── 2.3 Data Flow
├── 3. TESTING
│   ├── 3.1 Unit Tests
│   ├── 3.2 E2E Tests
│   └── 3.3 Smoke Test Results
├── 4. DEPLOYMENT
│   ├── 4.1 Bootstrap Script
│   ├── 4.2 Manual Deployment
│   └── 4.3 CI/CD Pipeline
├── 5. SECURITY
└── 6. COST BREAKDOWN
```

---

## 1. QUICK START

### 1.1 Prerequisites

```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install Docker
sudo apt-get install docker.io

# Install Node.js (for worker)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install pnpm
npm install -g pnpm

# Install uv (Python)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1.2 Local Development

```bash
# Clone and navigate
git checkout feat/azure-native-migration

# Terminal 1: Agent Core (FastAPI)
cd apps/agent-core
cp .env.example .env
echo "EXTRACTOR_MODE=fixture" >> .env
uv sync
uv run uvicorn src.main:app --port 8001 --reload

# Terminal 2: Worker (Node.js mode)
cd invoicify-worker
pnpm install
pnpm dev:node

# Terminal 3: Frontend
cd apps/web
pnpm install
pnpm dev

# Test health endpoints
curl http://localhost:8001/health
curl http://localhost:8787/health
```

### 1.3 Azure Deployment (5 minutes)

```bash
# 1. Create .env.azure with your credentials
cp .env.azure.example .env.azure
# Edit with your Azure subscription ID and tenant ID

# 2. Run bootstrap script
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh

# 3. Add GitHub Secrets (displayed by script)
# 4. Push to main branch - auto-deploys
git push origin feat/azure-native-migration
```

---

## 2. ARCHITECTURE

### 2.1 Monorepo Structure

```
invoicify/
├── apps/
│   ├── agent-core/          # FastAPI Agent Core (Python)
│   │   ├── src/
│   │   │   ├── mcp_servers/ # MCP Server implementations
│   │   │   │   ├── quickbooks_mcp.py  # QuickBooks Online
│   │   │   │   └── hubspot_mcp.py     # HubSpot CRM
│   │   │   ├── extraction/  # Azure Document Intelligence OCR
│   │   │   ├── queue/       # Azure Storage Queue consumer
│   │   │   ├── cache/       # L1/L2/L3 cache
│   │   │   ├── trust/       # Trust battery
│   │   │   └── main.py      # FastAPI entry point
│   │   ├── tests/
│   │   │   ├── tdd/         # Unit tests (51)
│   │   │   ├── mcp_servers/ # MCP integration tests (32)
│   │   │   └── e2e/         # End-to-end tests
│   │   └── Dockerfile
│   ├── web/                 # Next.js Frontend
│   ├── api/                 # Separate API Layer
│   ├── edge-api/            # Edge Routing
│   └── voice-agent/         # Sarvam Voice Integration
│
├── invoicify-worker/        # Node.js Worker (TypeScript)
│   ├── src/
│   │   ├── app.ts           # Hono app (shared)
│   │   ├── server.ts        # Node.js server for Azure
│   │   └── lib/
│   │       ├── db-adapter.ts    # PostgreSQL adapter
│   │       └── r2-adapter.ts    # Azure Blob adapter
│   ├── Dockerfile
│   └── package.json
│
├── infra/
│   └── main.bicep           # Azure Infrastructure (810 lines)
│
├── scripts/
│   ├── bootstrap.sh         # One-command Azure setup
│   ├── seed-keyvault.sh     # Key Vault secret seeding
│   └── start_*.sh           # Local Docker startup
│
└── .github/workflows/
    └── azure-deploy.yml     # CI/CD pipeline
```

### 2.2 Azure Services (All Free Tier)

| Service | Purpose | Free Tier | After Free |
|---------|---------|-----------|------------|
| **Container Apps** | API + Worker | 180k vCPU-sec/mo | Always free |
| **PostgreSQL B1MS** | Database | 750 hrs/mo (12mo) | ~$12/mo |
| **Blob Storage** | PDF storage | 5GB (12mo) | ~$0.10/mo |
| **Document Intelligence** | OCR extraction | 500 pages/mo (12mo) | Pay-per-page |
| **AI Search** | Vendor RAG | 3 indexes, 50MB | Always free |
| **Storage Queue** | Async processing | Free | Always free |
| **Event Grid** | Event routing | 100k ops/mo | Always free |
| **Key Vault** | Secrets | 10k tx/mo (12mo) | ~$0 |
| **Static Web Apps** | Frontend | 100GB BW | Always free |

**Total Month 1-12:** $0/month  
**Total Month 13+:** ~$42/month

### 2.3 MCP Server Integration

Invoicify uses the **Model Context Protocol (MCP)** to integrate with external services:

#### QuickBooks MCP
- `qb_create_bill()` - Create bills from approved invoices
- `qb_get_vendor()` - Lookup vendor information
- `qb_list_accounts()` - Retrieve chart of accounts
- `qb_check_bill_exists()` - Prevent duplicate payments

#### HubSpot MCP
- `hs_create_deal()` - Create deals for approved invoices
- `hs_get_company()` - Lookup company information
- `hs_update_deal()` - Update deal stage
- `hs_search_deals()` - Search existing deals
- `hs_create_company()` - Create new company records

### 2.4 Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant W as Static Web Apps
    participant A as Container Apps API
    participant Q as Storage Queue
    participant D as Document Intelligence
    participant P as PostgreSQL
    participant S as AI Search

    U->>W: Upload PDF Invoice
    W->>A: POST /api/v1/invoices
    A->>D: Extract with OCR
    D-->>A: Structured JSON
    A->>S: Lookup vendor policy
    S-->>A: Trust level + rules
    A->>P: Store invoice
    A->>Q: Queue for async processing
    A-->>W: Response
    W-->>U: ✅ Uploaded
```

---

## 3. TESTING

### 3.1 Unit Tests (83 Total Passing)

```bash
cd apps/agent-core
PYTHONPATH=. uv run pytest tests/ -v

# Test Breakdown:
# ┌─────────────────────────────────────┬───────┐
# │ Test Suite                          │ Count │
# ├─────────────────────────────────────┼───────┤
# │ TDD Tests (Core)                    │    51 │
# │ MCP Server Tests (QuickBooks)       │    10 │
# │ MCP Server Tests (HubSpot)          │    22 │
# │ E2E Tests                           │     7 │
# ├─────────────────────────────────────┼───────┤
# │ TOTAL                               │    83 │
# └─────────────────────────────────────┴───────┘
```

#### Test Categories

```bash
# Core TDD Tests (51)
test_sarvam_extractor.py       - 13 tests (OCR, PII, validation)
test_intake_router.py          - 21 tests (dedup, rate limit, priority)
test_production_components.py  - 17 tests (QStash, QB, cache, audit)

# MCP Server Tests (32)
mcp_servers/test_quickbooks_mcp.py - 10 tests (QB integration)
mcp_servers/test_hubspot_mcp.py    - 22 tests (HubSpot integration)

# E2E Tests (7)
e2e/test_full_e2e_real.py     - Real service connections
e2e/test_complete_pipeline.py - Full invoice workflow
e2e/test_invoice_pipeline.py  - Pipeline stages
```

### 3.2 Smoke Test Results

```bash
# QuickBooks MCP Smoke Test
$ PYTHONPATH=. uv run pytest tests/mcp_servers/test_quickbooks_mcp.py -v

============================== test session starts ==============================
tests/mcp_servers/test_quickbooks_mcp.py::test_qb_create_bill PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_qb_get_vendor PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_qb_list_accounts PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_qb_check_bill_exists PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_mcp_server_init PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_error_handling_401 PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_error_handling_429 PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_token_manager PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_retry_logic PASSED
tests/mcp_servers/test_quickbooks_mcp.py::test_tool_registration PASSED
============================== 10/10 tests passed ✓ =============================
```

```bash
# HubSpot MCP Smoke Test
$ PYTHONPATH=. uv run pytest tests/mcp_servers/test_hubspot_mcp.py -v

============================== test session starts ==============================
tests/mcp_servers/test_hubspot_mcp.py::test_hs_create_deal PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_hs_get_deal PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_hs_update_deal PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_hs_get_company PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_hs_create_company PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_hs_search_deals PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_token_manager_auth PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_token_manager_refresh PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_token_manager_invalid PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_client_create_deal PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_client_get_company PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_error_401_unauthorized PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_error_429_rate_limit PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_error_network_retry PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_error_timeout PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_tool_create_deal PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_tool_update_deal PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_tool_get_company PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_tool_create_company PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_tool_search_deals PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_server_initialization PASSED
tests/mcp_servers/test_hubspot_mcp.py::test_mcp_server_config_validation PASSED
============================== 22/22 tests passed ✓ =============================
```

### 3.3 E2E Tests (Real Services)

```bash
cd apps/agent-core
PYTHONPATH=. uv run python tests/e2e/test_full_e2e_real.py

# Tests:
# ✅ Redis connection
# ✅ Qdrant connection
# ✅ Ollama connection
# ✅ Sarvam OCR (with API key)
# ✅ Azure LLM (with credentials)
# ✅ Trust Battery
# ✅ Full pipeline execution
```

### 3.4 Local Testing

```bash
# Test Agent Core
cd apps/agent-core
uv run uvicorn src.main:app --port 8001
curl http://localhost:8001/health

# Test Worker
cd invoicify-worker
pnpm dev:node
curl http://localhost:8787/health
```

---

## 4. DEPLOYMENT

### 4.1 Bootstrap Script (Recommended)

```bash
./scripts/bootstrap.sh
```

**Creates:**
- ✅ Resource Group
- ✅ Container Registry
- ✅ PostgreSQL Server
- ✅ Storage Queue
- ✅ Blob Storage
- ✅ Key Vault
- ✅ Document Intelligence
- ✅ AI Search
- ✅ Container Apps (API + Worker)
- ✅ Static Web App

### 4.2 Manual Deployment

See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for complete instructions.

### 4.3 CI/CD Pipeline

```yaml
# .github/workflows/azure-deploy.yml

on: push to feat/azure-native-migration

Jobs:
  1. test - Run pytest (83 tests)
  2. deploy-infra - Deploy Bicep (on infra/ changes)
  3. deploy-agent-core - Build + push FastAPI image
  4. deploy-worker - Build + push Node.js worker image
  5. deploy-web - Deploy Static Web App (on apps/web/ changes)
```

---

## 5. SECURITY

### Secret Management

```bash
# ✅ GitHub Secrets - CI/CD credentials
# ✅ Azure Key Vault - Runtime secrets
# ✅ .gitignore - Prevents accidental commits (124 patterns)
# ✅ Pre-commit hook - Scans for secrets
```

### .gitignore Protection

```
# Protected from git:
.env*                 # Environment files
*.pem                 # Private keys
*.key                 # API keys
credentials.json      # OAuth credentials
secrets/              # Secret directory
azure-credentials/    # Azure auth files
```

### Pre-commit Hook

```bash
# Automatically installed
cp .githooks/pre-commit .git/hooks/pre-commit

# Scans for:
# - API keys (OpenRouter, Azure, HubSpot, QuickBooks)
# - Passwords
# - Connection strings
# - Private keys
```

### RBAC

- ✅ Managed Identity for Container Apps
- ✅ Key Vault access via RBAC
- ✅ Storage access via Managed Identity
- ✅ No credentials in code

### Security Best Practices

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                          │
├─────────────────────────────────────────────────────────────┤
│  GitHub Secrets    → CI/CD credentials                      │
│  Azure Key Vault   → Runtime secrets                        │
│  Managed Identity  → Azure service auth (no credentials)    │
│  .gitignore        → Prevents accidental commits            │
│  Pre-commit hook   → Scans for secrets before commit        │
│  Input validation  → Pydantic + Zod at boundaries           │
│  Rate limiting     → Intake router protection               │
│  Idempotency       → Request-Id headers                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. COST BREAKDOWN

| Month | Azure Cost | Notes |
|-------|-----------|-------|
| 1-12 | $0 | All services in free tier |
| 13+ | ~$42/mo | PostgreSQL + Storage + Container Registry |

### Free Tier Limits

```
Container Apps:         180,000 vCPU-sec/month + 2M requests
PostgreSQL B1MS:        750 hours/month (12 months)
Blob Storage:           5GB hot block (12 months)
Document Intelligence:  500 pages/month (12 months)
AI Search:              3 indexes, 50MB (always free)
Storage Queue:          Free (always)
Event Grid:             100k operations/month (always free)
Key Vault:              10k transactions/month (12 months)
Static Web Apps:        100GB bandwidth (always free)
```

### Cost Optimization

- **L1/L2/L3 Cache:** 90% reduction in LLM calls
- **Trust Battery:** 60-80% auto-approval rate
- **Serverless:** Scale to zero when idle
- **Free Tier:** All services within free limits for 12 months

---

## 📄 ADDITIONAL DOCUMENTATION

| Document | Purpose |
|----------|---------|
| [DEPLOY.md](DEPLOY.md) | Quick deployment guide |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Complete deployment instructions |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture details |
| [prd.md](prd.md) | Product requirements |
| [DOCKER_TESTING_GUIDE.md](DOCKER_TESTING_GUIDE.md) | Local Docker testing |
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | Implementation status |
| [CONTRACT_VERIFICATION.md](CONTRACT_VERIFICATION.md) | Reference documentation |

---

## 🆘 TROUBLESHOOTING

### Container won't start

```bash
az containerapp logs show \
  --name invoicify-api \
  --resource-group invoicify-rg \
  --follow
```

### Database connection fails

```bash
az keyvault secret show \
  --vault-name invoicify-kv \
  --name db-url
```

### Worker not processing

```bash
az containerapp logs show \
  --name invoicify-worker \
  --resource-group invoicify-rg
```

### MCP Server errors

```bash
# Check QuickBooks MCP logs
cd apps/agent-core
PYTHONPATH=. uv run pytest tests/mcp_servers/test_quickbooks_mcp.py -v

# Check HubSpot MCP logs
PYTHONPATH=. uv run pytest tests/mcp_servers/test_hubspot_mcp.py -v
```

---

## 📞 SUPPORT

- **Issues:** https://github.com/Aparnap2/invoicify/issues
- **Azure Portal:** https://portal.azure.com
- **Documentation:** See DEPLOYMENT_GUIDE.md
- **MCP Protocol:** https://modelcontextprotocol.io

---

## 🎯 KEY FEATURES

| Feature | Status | Description |
|---------|--------|-------------|
| **Multi-Channel Ingestion** | ✅ | Email, Web Upload, API, Mobile |
| **AI Extraction** | ✅ | Azure OCR + LLM parsing (99% accuracy) |
| **Trust Battery** | ✅ | 4 levels: PROBATION → STRATEGIC |
| **QuickBooks MCP** | ✅ | Idempotent bill creation |
| **HubSpot MCP** | ✅ | Deal and company management |
| **Audit Ledger** | ✅ | Append-only, cryptographic receipts |
| **Data Minimization** | ✅ | Store hashes, not PDFs (SOC 2) |

---

**Built with ❤️ on Azure Free Tier**
**Last Updated:** March 6, 2026
**Version:** 4.1 (Azure-Native with MCP Integration)
**Tests:** 83 passing (51 core + 22 HubSpot + 10 QuickBooks)
