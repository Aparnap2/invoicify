# Invoicify AI - Cloudflare-Native Architecture

Vertical AI Agent for Finance Operations - Cloudflare-native invoice processing with Groq Vision, Durable Objects, and Edge AI.

## Executive Summary

**Invoicify** is a fully Cloudflare-native autonomous Accounts Payable (AP) agent that processes invoices entirely at the edge: ingestion → extraction → risk assessment → decision → execution → reconciliation.

**Core Value Proposition:** Prevent cash bleed through intelligent automation while maintaining founder-level control over financial decisions through adaptive trust levels and explainable AI.

## Architecture (Cloudflare-Only Stack)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CLOUDFLARE EDGE NETWORK                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     INVOICIFY-WORKER (Hono)                         │   │
│  │                                                                     │   │
│  │   Routes: /api/v1/invoices    /api/v1/upload    /api/v1/workflow    │   │
│  │           /api/v1/risk        /api/v1/trust     /api/v1/quickbooks  │   │
│  │                                                                     │   │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐ │   │
│  │   │   Upload    │  │   Status    │  │    HITL Review              │ │   │
│  │   │   Handler   │  │   Endpoint  │  │    (Human-in-Loop)          │ │   │
│  │   └──────┬──────┘  └─────────────┘  └─────────────────────────────┘ │   │
│  │          │                                                          │   │
│  │   ┌──────▼────────────────────────────────────────────────────────┐  │   │
│  │   │              INVOICE QUEUE (Cloudflare Queues)                │  │   │
│  │   │         Async processing buffer with retries                  │  │   │
│  │   └─────────────────────────┬─────────────────────────────────────┘  │   │
│  └─────────────────────────────┼──────────────────────────────────────┘   │
│                                │                                            │
│  ┌─────────────────────────────▼──────────────────────────────────────┐    │
│  │              INVOICE PROCESSOR (Durable Object)                    │    │
│  │                                                                    │    │
│  │  Step 1: Download PDF from R2 Storage                              │    │
│  │         ↓                                                          │    │
│  │  Step 2: Extract with Groq Vision (llama-3.2-90b-vision)           │    │
│  │         ↓                                                          │    │
│  │  Step 3: Calculate Risk Score (z-score + signals)                  │    │
│  │         ↓                                                          │    │
│  │  Step 4: Make Decision (AUTO_APPROVE | HITL | REJECT)              │    │
│  │         ↓                                                          │    │
│  │  Step 5: Execute (QuickBooks + R2 + D1 Update)                     │    │
│  │                                                                    │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                      DATA & STORAGE LAYER                          │    │
│  │                                                                    │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │    │
│  │  │    D1 DB     │  │  R2 Storage  │  │     KV Cache           │   │    │
│  │  │  (SQLite)    │  │  (PDF/JSON)  │  │   (Session/Tokens)     │   │    │
│  │  │              │  │              │  │                        │   │    │
│  │  │ • invoices   │  │ • Raw PDFs   │  │ • QuickBooks tokens    │   │    │
│  │  │ • vendors    │  │ • Processed  │  │ • Rate limits          │   │    │
│  │  │ • audit_logs │  │ • Extracted  │  │ • Cache                │   │    │
│  │  │ • trust      │  │              │  │                        │   │    │
│  │  └──────────────┘  └──────────────┘  └────────────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ API/WebSocket
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        VITE + REACT SPA (Frontend)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Dashboard   │  │    HITL      │  │    Audit     │  │   Analytics  │    │
│  │    (KPIs)    │  │   Review     │  │   Timeline   │  │   (Charts)   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|-------|------------|-----|
| **Edge Runtime** | Cloudflare Workers | Global edge deployment, cold starts <1ms |
| **API Framework** | Hono.js | Ultra-lightweight, Cloudflare-native |
| **Database** | D1 (SQLite) | Edge SQL with automatic replication |
| **Storage** | R2 (S3-compatible) | Zero egress fees, ideal for PDFs |
| **Queue** | Cloudflare Queues | Native async processing with DLQ |
| **State** | Durable Objects | Stateful processing at the edge |
| **AI (Vision)** | Groq API (Llama 3.2 Vision) | Ultra-fast inference, PDF understanding |
| **AI (Risk)** | TypeScript z-score | Deterministic, no model training needed |
| **Auth** | Cloudflare Access / JWT | Edge authentication |
| **Integrations** | QuickBooks Online, Salesforce | REST API clients |
| **Frontend** | React 19 + Vite + Tailwind | Modern stack |

## Key Architecture Decisions

### 1. Durable Objects for Invoice Processing

**Why Durable Objects?**
- ✅ Stateful processing survives Worker restarts
- ✅ Single-threaded execution guarantees consistency
- ✅ Built-in storage for job state
- ✅ Alarms for timeout/retry handling
- ✅ Automatic regional placement near user

**Processing Flow:**
```
Upload → R2 → Queue → Durable Object → Groq → Risk → Decision → QBO
```

### 2. Groq Vision vs. Self-Hosted OCR

**Why Groq?**
- ✅ No infrastructure to maintain
- ✅ Sub-second inference for PDF extraction
- ✅ Native JSON output with schema
- ✅ Handles scanned and digital PDFs
- ✅ Cost-effective at scale

**vs. IBM Docling:**
- ❌ No local GPU needed
- ❌ No container orchestration
- ❌ No Python dependencies
- ✅ Simpler deployment

### 3. Z-Score Risk vs. River ML

**Why Z-Score?**
- ✅ Deterministic (no training required)
- ✅ Works with any amount of history
- ✅ TypeScript-native (no Python)
- ✅ Explainable (business understands z-scores)
- ✅ No model persistence needed

**Risk Formula:**
```
risk = min(z_score / 3, 1.0) + signals
where z_score = |amount - mean| / std_dev
```

### 4. Cloudflare Queues vs. Kafka

**Why Queues?**
- ✅ Native Cloudflare integration
- ✅ Automatic retries with backoff
- ✅ Dead letter queue built-in
- ✅ No infrastructure to manage
- ✅ Cost-effective

## Features

### Core Processing Pipeline

1. **Ingestion** - Upload PDF via Hono API → Store in R2 → Queue message
2. **Extraction** - Durable Object downloads PDF → Groq Vision extracts JSON
3. **Risk Assessment** - Calculate z-score + business signals → 0-1 risk score
4. **Decision** - Risk < 0.3: Auto-approve | 0.3-0.7: HITL | > 0.7: Reject
5. **Execution** - Create QuickBooks bill → Update D1 → Store processed JSON
6. **Audit** - Full decision trail with reasoning

### Trust Battery System

```typescript
// Levels: 1 (New) → 5 (Trusted)
// Auto-approve threshold increases with trust
Level 1: $0 (All manual)
Level 2: $500
Level 3: $1,000
Level 4: $2,500
Level 5: $5,000+ (Trusted)
```

### Human-in-the-Loop (HITL)

- High-risk invoices queued for review
- Dashboard shows extracted data + reasoning
- Approve/reject with comments
- Slack notification for urgent items
- Audit trail for compliance

### Real-Time Status Tracking

```typescript
// Poll status endpoint
GET /api/v1/invoices/:traceId/status

Response:
{
  traceId: "inv-123",
  status: "processing",
  stage: "extraction", // upload | queued | extraction | risk | decision | complete
  progress: 45,
  estimatedCompletion: "2025-02-11T10:30:00Z"
}
```

## API Reference

### Upload Invoice
```bash
POST /api/v1/upload
Content-Type: multipart/form-data

file: <invoice.pdf>
metadata: {"source": "email", "userId": "user-123"}

Response:
{
  "traceId": "inv-abc-123",
  "status": "queued",
  "r2Key": "raw/2025-02-11/inv-abc-123.pdf"
}
```

### Check Status
```bash
GET /api/v1/invoices/:traceId/status

Response:
{
  "traceId": "inv-abc-123",
  "status": "completed",
  "extractedData": {
    "vendorName": "Acme Corp",
    "amount": 1250.00,
    "currency": "USD"
  },
  "riskScore": 0.15,
  "decision": "AUTO_APPROVED",
  "quickbooksBillId": "qb-456"
}
```

### Manual Review (HITL)
```bash
POST /api/v1/invoices/:traceId/review
Authorization: Bearer <token>

{
  "action": "approve",
  "reason": "Valid invoice, matches PO"
}

Response:
{
  "traceId": "inv-abc-123",
  "status": "approved",
  "reviewedBy": "user-123",
  "reviewedAt": "2025-02-11T10:35:00Z"
}
```

## Development

### Setup

```bash
# Clone and setup
cd invoicify-worker
npm install

# Local development
npm run dev

# Run tests
npm run test

# Type checking
npm run typecheck
```

### Environment Setup

Create `.dev.vars`:
```
GROQ_API_KEY=your-groq-key
QUICKBOOKS_CLIENT_ID=your-qbo-id
QUICKBOOKS_CLIENT_SECRET=your-qbo-secret
ENVIRONMENT=development
```

### Database Migrations

```bash
# Create migration
wrangler d1 migrations create invoicify-db add_new_field

# Edit migrations/*.sql
# Apply locally
wrangler d1 migrations apply invoicify-db --local

# Apply to production
wrangler d1 migrations apply invoicify-db --remote
```

### Deployment

```bash
# Deploy to Cloudflare
npm run deploy

# View logs
wrangler tail
```

## Project Structure

```
invoicify-worker/
├── src/
│   ├── index.ts                    # Main Hono app
│   ├── db/
│   │   ├── schema.ts              # Drizzle schema
│   │   └── index.ts               # DB connection
│   ├── durable-objects/
│   │   └── InvoiceProcessor.ts    # Core processing DO
│   ├── lib/
│   │   ├── groq.ts                # Groq Vision client
│   │   ├── risk.ts                # Z-score calculation
│   │   ├── storage.ts             # R2 helpers
│   │   └── quickbooks.ts          # QBO integration
│   ├── routes/
│   │   ├── invoices.ts            # CRUD endpoints
│   │   ├── upload.ts              # File upload
│   │   ├── risk.ts                # Risk endpoints
│   │   └── workflow.ts            # Status/tracking
│   └── types/
│       └── index.ts               # TypeScript types
├── migrations/                     # D1 SQL migrations
├── tests/
│   ├── unit/                      # Unit tests
│   └── integration/               # Integration tests
├── wrangler.toml                  # Cloudflare config
└── package.json
```

## Testing

### Unit Tests
```bash
npm run test
# Vitest with coverage
```

### Golden Invoice Test
```bash
# Upload test invoice
curl -X POST http://localhost:8787/api/v1/upload \
  -F "file=@fixtures/invoice.pdf" \
  -F "metadata={\"source\":\"test\"}"

# Poll status until complete
watch -n 2 'curl http://localhost:8787/api/v1/invoices/{traceId}/status'
```

### Integration Tests
```bash
# Test full pipeline
npm run test:integration

# Test Durable Object
npm run test:do

# Test Queue processing
npm run test:queue
```

## Monitoring

### Logs
```bash
# Real-time logs
wrangler tail

# Filtered logs
wrangler tail --format=pretty
```

### Metrics
- Processing latency (P50, P95, P99)
- Queue depth
- Error rates
- Groq API latency
- D1 query performance

### Alerts
- Queue depth > 100
- Error rate > 5%
- Processing time > 60s
- Groq API errors

## Security

### Authentication
- JWT tokens via Cloudflare Access
- API keys for service-to-service
- OAuth for QuickBooks integration

### Data Protection
- TLS 1.3 for all connections
- Encryption at rest (D1, R2)
- PII redaction in logs
- Audit logs for all actions

### Access Control
- Role-based permissions
- IP allowlisting (optional)
- Rate limiting per API key

## Roadmap

### Phase 1: Foundation ✅
- [x] Hono API with D1
- [x] File upload to R2
- [x] Basic invoice CRUD

### Phase 2: Cloudflare-Native Processing ✅
- [x] Durable Objects for processing
- [x] Queue-based async
- [x] Groq Vision extraction
- [x] Z-score risk calculation

### Phase 3: Integrations ✅
- [x] QuickBooks Online
- [x] Slack notifications
- [x] Salesforce read-only

### Phase 4: Advanced Features 🚧
- [ ] Multi-currency support
- [ ] PO matching
- [ ] Duplicate detection (vector search)
- [ ] Batch processing
- [ ] Advanced analytics

### Phase 5: Enterprise 📝
- [ ] SSO/SAML
- [ ] Custom workflows
- [ ] Webhook integrations
- [ ] Audit compliance (SOC2)

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## License

MIT License - see LICENSE file

## Support

- Documentation: [docs.invoicify.ai](https://docs.invoicify.ai)
- Issues: [GitHub Issues](https://github.com/yourusername/invoicify/issues)
- Email: support@invoicify.ai

---

**Built with ❤️ on Cloudflare**
