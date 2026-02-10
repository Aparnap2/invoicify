# Invoicify AI

Vertical AI Agent for Finance Operations - Automated invoice processing with Analyst-Critic pattern, Trust Battery system, and Slack "Intern's Desk" interface.

## Executive Summary

**Invoicify** is an autonomous Accounts Payable (AP) agent that replaces the "AP Intern" role by owning the complete invoice lifecycle: ingestion → extraction → risk assessment → decision → execution → reconciliation → learning.

**Core Value Proposition:** Prevent cash bleed through intelligent automation while maintaining founder-level control over financial decisions through adaptive trust levels and explainable AI.

## Architecture (DigitalOcean Stack)

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloudflare Workers                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Hono API  │  │    D1 DB    │  │       R2 Storage        │  │
│  │  (Worker)   │  │  (SQLite)   │  │    (Invoice Files)      │  │
│  └──────┬──────┘  └─────────────┘  └─────────────────────────┘  │
│         │                                                       │
│  ┌──────▼──────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Cloudflare  │  │   Workers   │  │     Vision OCR AI       │  │
│  │   AI (Llama)│  │    KV       │  │    (Extraction)         │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                      │                │
│  ┌──────▼───────────────────────┐  ┌───────────▼─────────────┐  │
│  │      Neo4j Knowledge Graph   │  │   Slack "Intern's Desk"  │  │
│  │    (Temporal Vendor Data)    │  │   (Conversational AI)    │  │
│  └──────────────────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
          │                                                       │
          │ API (REST)                        │ Slack Events      │
          ▼                                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Vite + React SPA                            │
│  ┌───────────┐  ┌────────────┐  ┌───────────────────────────┐  │
│  │Dashboard  │  │ HITL Review│  │      Audit Timeline       │  │
│  │  (KPIs)   │  │  (Approve) │  │    (Full History)         │  │
│  └───────────┘  └────────────┘  └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Ingress** | Cloudflare Worker (Hono.js) |
| **Event Bus** | WarpStream (Kafka-compatible) |
| **Compute** | Python Worker (Docker) on DigitalOcean Droplet |
| **Orchestrator** | Temporal Cloud (Durable Workflows) |
| **Storage** | DigitalOcean Spaces (S3-compatible) |
| **Database** | Supabase (Postgres, Free Tier) |
| **AI (Vision)** | IBM Docling (local) + IBM Granite 13B (Watsonx API) |
| **AI (ML)** | River (Online Anomaly Detection) |
| **Integrations** | QuickBooks Online, Salesforce (Read-Only) |
| **Frontend** | React 19 + Vite + TanStack Query + Tailwind CSS |

## Features

### Core Processing
- **Invoice Ingestion** - Upload or submit invoice data
- **Vision OCR** - AI-powered extraction from uploaded files
- **Risk Assessment** - Multi-factor fraud detection
- **Auto-Approve** - Low-risk invoices auto-approved based on Trust Battery

### Analyst-Critic Agent Pattern
- **Analyst Node** - Proposes action based on historical patterns and vendor history
- **Critic Node** - Safety checks with priority matrix (RUNWAY > STRATEGY > CONTRACT > TRUST > BUDGET)
- **Reasoning Chain** - Every decision explained with confidence scores

### Human-in-the-Loop (HITL)
- High-risk invoices flagged for review
- Approve/reject with comments
- Audit trail for all decisions
- Slack integration with interactive buttons

### Trust Battery System
- Tracks vendor trust over time
- Auto-approve thresholds per vendor level
- Levels: Probation → Standard → Core

### Slack "Intern's Desk" Interface
Conversational AI that lives in Slack - no dashboard required.

**Proactive Alerts (The "Tap on the Shoulder"):**
```
@finance-intern blocked a $12k invoice from NewVendor.
It looks like a duplicate of one we paid last week.
[Approve Override] [Reject]
```

**Conversational Queries (The "Shout Across the Room"):**
```
Founder: "How much runway do we have?"
Intern:  "Current cash $450k. Burn ~$50k/mo. Runway: ~9 months.
         (Note: We have a large tax bill due next month.)"

Founder: "Did we pay Acme yet?"
Intern:  "Yes! $2,450 on Jan 10. It was auto-approved because
         Acme is a Core vendor with 100% accuracy."
```

**Episode Creation (Memory Injection):**
```
Founder: "@finance-intern, from now on, auto-approve Vercel invoices under $500"
Intern:  "Understood. I've updated the Vercel trust policy and
         logged this instruction to my memory."
```

### Temporal Knowledge Graph (Neo4j)
- Vendor invoice history as temporal relationships
- Trust score evolution over time
- Pattern detection for recurring invoices

## Getting Started

### Prerequisites
- Node.js 22+
- pnpm
- Python 3.11+
- DigitalOcean account with Droplet and Spaces
- Cloudflare account with D1 and R2 enabled
- Wrangler CLI (`npm install -g wrangler`)

### Environment Setup

1. **Clone and install:**
```bash
git clone <repo>
cd invoicify
```

2. **Configure environment:**
```bash
# Worker environment
cd worker
cp .env.example .env
# Edit .env with your API keys

# Frontend environment
cd ../fullstack
cp .env.example .env.local
# Set VITE_API_URL=http://localhost:8787/api/v1 (dev)
```

3. **Start development:**

```bash
# Terminal 1: Start Worker (with local D1)
cd worker
pnpm dev

# Terminal 2: Start Frontend
cd fullstack
pnpm dev
```

4. **Access:**
- Frontend: http://localhost:3000
- API: http://localhost:8787/api/v1
- Health: http://localhost:8787/health

### Production Deployment (DigitalOcean)

```bash
# 1. SSH into DigitalOcean Droplet
ssh root@your-droplet-ip

# 2. Clone repository
git clone https://github.com/your-username/invoicify.git
cd invoicify

# 3. Create .env file
cat > .env << EOF
# DigitalOcean Spaces
DO_SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com
DO_SPACES_ACCESS_KEY=DO00...
DO_SPACES_SECRET_KEY=...
DO_SPACES_BUCKET=invoicify-storage

# Temporal Cloud
TEMPORAL_HOST=namespace.tmprl.cloud:7233
TEMPORAL_NAMESPACE=invoicify
TEMPORAL_CERT=...  # mTLS Cert
TEMPORAL_KEY=...   # mTLS Key

# IBM Watsonx (Granite API)
IBM_WATSONX_APIKEY=...
IBM_WATSONX_PROJECT_ID=...

# Supabase (Postgres)
DATABASE_URL=postgresql://...

# QuickBooks
QUICKBOOKS_CLIENT_ID=...
QUICKBOOKS_CLIENT_SECRET=...
QUICKBOOKS_REFRESH_TOKEN=...
QUICKBOOKS_REALM_ID=...

# Salesforce
SALESFORCE_USER=...
SALESFORCE_PASSWORD=...
SALESFORCE_TOKEN=...

# Gmail
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
EOF

# 4. Build and run
docker-compose up -d

# 5. Check logs
docker logs -f invoicify-worker

# 6. Deploy Cloudflare Worker
cd edge/
wrangler deploy
```

## API Reference

### Invoices

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/invoices` | List invoices (paginated) |
| GET | `/api/v1/invoices/:id` | Get invoice details |
| POST | `/api/v1/invoices` | Create invoice |
| PUT | `/api/v1/invoices/:id` | Update invoice |
| PATCH | `/api/v1/invoices/:id/status` | Update status |
| POST | `/api/v1/invoices/:id/approve` | HITL approve/reject |

### Risk

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/risk/:invoiceId` | Get risk assessment |
| POST | `/api/v1/risk/:invoiceId/analyze` | Re-run analysis |
| GET | `/api/v1/risk/list/high-risk` | List high-risk invoices |
| POST | `/api/v1/risk/feedback` | Submit feedback |

### Workflow

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/workflow/start` | Start invoice processing |
| POST | `/api/v1/workflow/:id/approve` | Continue after HITL |

### Slack Intern ("The Intern's Desk")

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/slack/intern/command` | Slash command `/intern` handler |
| POST | `/api/v1/slack/intern/events` | Event subscriptions (app_mention) |
| POST | `/api/v1/slack/interactions` | Button click interactions |

**Supported Queries:**
- `"How much runway do we have?"` - Returns runway calculation with context
- `"What's our burn rate?"` - Monthly spending breakdown
- `"How much cash do we have?"` - Current cash balance
- `"How much did we pay to [Vendor]?"` - Vendor spend history
- `"What's pending?"` - List of pending invoices
- `"Help"` - Show available commands

**Supported Instructions:**
- `"From now on, auto-approve [Vendor] under $500"` - Trust policy
- `"Always flag [Vendor] for review"` - Review rule

### QuickBooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/quickbooks/auth` | Get OAuth URL |
| GET | `/api/v1/quickbooks/callback` | OAuth callback |

## Environment Variables

### Worker (`worker/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `STRIPE_TEST_KEY` | Yes | Stripe test API key |
| `QUICKBOOKS_CLIENT_ID` | Yes | QuickBooks OAuth client ID |
| `QUICKBOOKS_CLIENT_SECRET` | Yes | QuickBooks OAuth secret |
| `QUICKBOOKS_REFRESH_TOKEN` | Yes | QuickBooks refresh token |
| `QUICKBOOKS_REALM_ID` | Yes | QuickBooks company ID |

### Frontend (`fullstack/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes | API base URL |

### DigitalOcean Droplet (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DO_SPACES_ENDPOINT` | Yes | DigitalOcean Spaces endpoint |
| `DO_SPACES_ACCESS_KEY` | Yes | Spaces access key |
| `DO_SPACES_SECRET_KEY` | Yes | Spaces secret key |
| `DO_SPACES_BUCKET` | Yes | Spaces bucket name |
| `TEMPORAL_HOST` | Yes | Temporal Cloud host |
| `TEMPORAL_NAMESPACE` | Yes | Temporal namespace |
| `TEMPORAL_CERT` | Yes | Temporal mTLS certificate |
| `TEMPORAL_KEY` | Yes | Temporal mTLS key |
| `IBM_WATSONX_APIKEY` | Yes | IBM Watsonx API key |
| `IBM_WATSONX_PROJECT_ID` | Yes | IBM Watsonx project ID |
| `DATABASE_URL` | Yes | Supabase database URL |
| `QUICKBOOKS_CLIENT_ID` | Yes | QuickBooks OAuth client ID |
| `QUICKBOOKS_CLIENT_SECRET` | Yes | QuickBooks OAuth secret |
| `QUICKBOOKS_REFRESH_TOKEN` | Yes | QuickBooks refresh token |
| `QUICKBOOKS_REALM_ID` | Yes | QuickBooks company ID |
| `SALESFORCE_USER` | Yes | Salesforce username |
| `SALESFORCE_PASSWORD` | Yes | Salesforce password |
| `SALESFORCE_TOKEN` | Yes | Salesforce security token |
| `GMAIL_CLIENT_ID` | Yes | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | Yes | Gmail OAuth secret |
| `GMAIL_REFRESH_TOKEN` | Yes | Gmail refresh token |

## Project Structure

```
invoicify/
├── ai/                    # Python AI service (FastAPI)
│   ├── app/
│   │   ├── agents/       # Analyst, Critic agents
│   │   ├── graphs/       # LangGraph workflows
│   │   ├── services/     # Trust Battery, Reconciliation
│   │   └── clients/      # Ollama, Neo4j clients
│   └── tests/
├── temporal/              # Temporal workflow implementation
│   ├── activities/       # Temporal activities
│   ├── workflows/        # Temporal workflows
│   ├── infrastructure/   # Infrastructure adapters
│   └── tests/            # Unit and integration tests
├── worker/                # Cloudflare Worker (Hono)
│   ├── src/
│   │   ├── routes/       # API endpoints
│   │   │   ├── slack.ts  # Slack Intern & HITL
│   │   │   ├── workflow.ts # Agent workflow
│   │   │   └── ...
│   │   ├── lib/          # Business logic
│   │   │   ├── slack-intern.ts  # "Intern's Desk" logic
│   │   │   ├── slack.ts         # HITL messages
│   │   │   ├── workflow.ts      # State machine
│   │   │   ├── neo4j.ts         # Knowledge graph
│   │   │   └── audit-tracer.ts  # Audit trail
│   │   └── db/           # D1 schema
│   ├── drizzle/          # DB migrations
│   ├── wrangler.toml     # Worker config
│   └── slack-manifest.json # Slack App Manifest
├── fullstack/            # React SPA (Vite)
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── hooks/        # Custom hooks
│   │   └── types/        # TypeScript types
│   └── dist/             # Built assets
├── prd.md                # Product Requirements Document
└── README.md             # This file
```

## Testing

### Run Tests

```bash
# Unit tests
cd temporal
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# All tests
pytest tests/ -v
```

### Test Coverage

- **Unit Tests**: 68/68 passing
- **Integration Tests**: 5/5 passing
- **Total**: 73/73 passing (91.3%), 7 skipped

## Security

- All secrets stored in environment variables
- OAuth 2.0 for external integrations
- Encryption at rest (DigitalOcean Spaces) and in transit (TLS 1.3)
- PII redaction in logs
- Input validation at every boundary

## License

MIT
