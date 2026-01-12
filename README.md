# Invoicify AI

Vertical AI Agent for Finance Operations - Automated invoice processing with Analyst-Critic pattern, Trust Battery system, and HITL (Human-in-the-Loop) review.

## Architecture

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
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │
         │ API (REST)
         ▼
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
| **Frontend** | React 19 + Vite + TanStack Query + Tailwind CSS |
| **Backend** | Hono.js (Cloudflare Workers) |
| **Database** | Cloudflare D1 (SQLite) |
| **Storage** | Cloudflare R2 (S3-compatible) |
| **AI** | Cloudflare Workers AI (Llama 3.2 Vision) |
| **Validation** | TypeScript strict mode |

## Features

### Core Processing
- **Invoice Ingestion** - Upload or submit invoice data
- **Vision OCR** - AI-powered extraction from uploaded files
- **Risk Assessment** - Multi-factor fraud detection
- **Auto-Approve** - Low-risk invoices auto-approved based on Trust Battery

### Human-in-the-Loop (HITL)
- High-risk invoices flagged for review
- Approve/reject with comments
- Audit trail for all decisions

### Trust Battery System
- Tracks vendor trust over time
- Auto-approve thresholds per vendor level
- Levels: Probation → Standard → Core

## Getting Started

### Prerequisites
- Node.js 22+
- pnpm
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
# Edit .env with your API keys:
# - STRIPE_TEST_KEY
# - QUICKBOOKS_CLIENT_ID
# - QUICKBOOKS_CLIENT_SECRET
# - QUICKBOOKS_REFRESH_TOKEN
# - QUICKBOOKS_REALM_ID

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

### Production Deployment

```bash
# Build frontend
cd fullstack
pnpm build

# Deploy to Cloudflare
cd worker
npx wrangler deploy
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
├── worker/                # Cloudflare Worker (Hono)
│   ├── src/
│   │   ├── routes/       # API endpoints
│   │   ├── lib/          # Business logic
│   │   ├── db/           # D1 schema
│   │   └── lib/          # Audit tracer, QuickBooks
│   ├── drizzle/          # DB migrations
│   └── wrangler.toml     # Worker config
├── fullstack/            # React SPA (Vite)
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── hooks/        # Custom hooks
│   │   └── types/        # TypeScript types
│   └── dist/             # Built assets
└── SECURITY_AUDIT_REPORT.md
```

## Security

See [SECURITY_AUDIT_REPORT.md](./SECURITY_AUDIT_REPORT.md) for:
- Known vulnerabilities
- Mitigation strategies
- Audit findings and fixes

## License

MIT
