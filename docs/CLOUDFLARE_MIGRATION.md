# Cloudflare Migration Strategy - Invoicify

# # Executive Summary

Transform Invoicify from Python FastAPI + Next.js to **100% Cloudflare edge architecture** using Workers, D1, AI, Queues, and R2.

**Key Architecture Decisions:**
- Python AI service kept separate (Pydantic AI + LangGraph + Workers AI)
- Drizzle ORM for D1 (not Prisma)
- Workers just for API/CRUD (Hono + Drizzle)
- Workers AI accessed via Python service (not direct from Workers)

---

# # Current Architecture

```text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Next.js (Vercel)│────▶│ FastAPI (UVicorn)│────▶│ PostgreSQL      │
│  Frontend       │     │ AI Service      │     │ Database        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```text
# # Target Cloudflare Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                      Cloudflare Global Network                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Cloudflare  │    │  Cloudflare  │    │  Cloudflare  │      │
│  │  Pages       │    │  Workers     │    │  R2 Storage  │      │
│  │  (Frontend)  │    │  (API/AI)    │    │  (Invoices)  │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             │                                   │
│              ┌──────────────┼──────────────┐                   │
│              │   Cloudflare D1 (SQLite)   │                   │
│              │   Drizzle ORM              │                   │
│              └──────────────┬──────────────┘                   │
│                             │                                   │
│              ┌──────────────┼──────────────┐                   │
│              │   Cloudflare Queues         │                   │
│              │   Async Processing          │                   │
│              └──────────────┬──────────────┘                   │
│                             │                                   │
│              ┌──────────────┼──────────────┐                   │
│              │   Workers AI  │ Cloudflare   │                   │
│              │   (OpenAI SDK)│ Agents SDK   │                   │
│              └──────────────┴──────────────┘                   │
│                             │                                   │
│              ┌──────────────┼──────────────┐                   │
│              │   Python AI Service          │                   │
│              │   (Pydantic AI + LangGraph)  │                   │
│              │   Workers AI Provider        │                   │
│              └─────────────────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```text
---

# # Component Mapping

| Current | Cloudflare | Rationale |
| --------- | ------------ | ----------- |
| Next.js | **Pages** | Static + SSR frontend, edge-ready |
| FastAPI (API) | **Workers + Hono** | Edge compute for CRUD operations |
| FastAPI (AI) | **Keep Separate** | Python service with Pydantic AI + LangGraph |
| PostgreSQL | **D1 + Drizzle ORM** | SQLite-compatible, edge-native |
| LLM Provider | **Workers AI** | Called from Python service via OpenAI SDK |
| Celery | **Queues** | Async job processing in Workers |
| S3 | **R2** | Invoice file storage, no egress fees |


**Architecture Flow:**
```text
┌─────────────────────────────────────────────────────────────────┐
│                      Cloudflare Global Network                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Cloudflare  │    │  Cloudflare  │    │  Cloudflare  │      │
│  │  Pages       │    │  Workers     │    │  R2 Storage  │      │
│  │  (Frontend)  │    │  (API/CRUD)  │    │  (Invoices)  │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             │                                   │
│              ┌──────────────┼──────────────┐                   │
│              │   Cloudflare D1 (SQLite)   │                   │
│              │   Drizzle ORM              │                   │
│              └──────────────┬──────────────┘                   │
│                             │                                   │
│              ┌──────────────┼──────────────┐                   │
│              │   Cloudflare Queues         │                   │
│              │   Async Processing          │                   │
│              └──────────────┬──────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
│                             │                                   │
│         ┌───────────────────┴───────────────────┐               │
│         │                                       │               │
│         ▼                                       ▼               │
│  ┌─────────────────────────┐         ┌─────────────────────┐   │
│  │   Python AI Service     │◀───────▶│   Workers AI        │   │
│  │   (Pydantic AI + LangGraph)  │     │   OpenAI SDK       │   │
│  │   - Invoice extraction  │         │   - Llama 3.1 8B   │   │
│  │   - Workflows (HITL)    │         │   - Embeddings     │   │
│  └─────────────────────────┘         └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```text
---

# # Migration Phases

## # Phase 1: Infrastructure Setup
**Weeks 1-2**

- [ ] Create Cloudflare account + configure wrangler
- [ ] Initialize D1 database with Drizzle schema
- [ ] Set up R2 bucket for invoice documents
- [ ] Configure Pages project for frontend

```bash
# Initialize Cloudflare Workers project
npm create cloudflare@latest invoicify -- --type=worker --ts

# Create D1 database
npx wrangler d1 create invoicify-db

# Create R2 bucket
npx wrangler r2 bucket create invoicify-files

# Install Drizzle
npm install drizzle-orm
npm install -D drizzle-kit
```text
**wrangler.toml Configuration:**
```toml
name = "invoicify-api"
main = "src/index.ts"
compatibility_date = "2024-09-26"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "invoicify-db"
database_id = "YOUR_DB_ID"
migrations_dir = "drizzle/migrations"

[[r2_buckets]]
binding = "INVOICE_BUCKET"
bucket_name = "invoicify-files"
```text
**Drizzle Schema (src/db/schema.ts):**
```typescript
import { sqliteTable, text, integer, real } from 'drizzle-orm/sqlite-core';
import { sql } from 'drizzle-orm';

export const invoices = sqliteTable('invoices', {
  id: text('id').primaryKey(),
  vendorName: text('vendor_name').notNull(),
  invoiceNumber: text('invoice_number').notNull(),
  totalAmount: real('total_amount').notNull(),
  currency: text('currency').default('USD'),
  status: text('status').default('NEW'),
  dueDate: text('due_date'),
  rawContent: text('raw_content'),
  extractedData: text('extracted_data'), // JSON string
  confidenceScore: real('confidence_score'),
  createdAt: text('created_at').default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text('updated_at'),
});

export const lineItems = sqliteTable('line_items', {
  id: text('id').primaryKey(),
  invoiceId: text('invoice_id').references(() => invoices.id),
  description: text('description').notNull(),
  quantity: real('quantity').notNull(),
  unitPrice: real('unit_price').notNull(),
  amount: real('amount').notNull(),
});

export const auditLogs = sqliteTable('audit_logs', {
  id: text('id').primaryKey(),
  action: text('action').notNull(),
  entityType: text('entity_type').notNull(),
  entityId: text('entity_id').notNull(),
  oldValue: text('old_value'),
  newValue: text('new_value'),
  performedBy: text('performed_by'),
  createdAt: text('created_at').default(sql`CURRENT_TIMESTAMP`),
});
```text
## # Phase 2: Backend Migration
**Weeks 3-4**

- [ ] Create Hono-based Worker API
- [ ] Implement Drizzle database layer
- [ ] Build AI extraction endpoint with Workers AI (OpenAI SDK)
- [ ] Set up R2 file uploads

```typescript
// src/index.ts - Main Worker entry
import { Hono } from 'hono';
import { drizzle } from 'drizzle-orm/d1';
import { invoices } from './db/schema';
import { eq } from 'drizzle-orm';

interface Env {
  DB: D1Database;
  AI: Ai;
  INVOICE_BUCKET: R2Bucket;
}

const app = new Hono<{ Bindings: Env }>();

// GET /api/invoices - List invoices
app.get('/api/invoices', async (c) => {
  const db = drizzle(c.env.DB);
  const result = await db.select().from(invoices).all();
  return c.json({ invoices: result });
});

// GET /api/invoices/:id - Get single invoice
app.get('/api/invoices/:id', async (c) => {
  const db = drizzle(c.env.DB);
  const id = c.req.param('id');
  const result = await db.select().from(invoices).where(eq(invoices.id, id)).get();
  return result ? c.json(result) : c.json({ error: 'Not found' }, 404);
});

// POST /api/invoices - Create invoice (triggers AI extraction)
app.post('/api/invoices', async (c) => {
  const db = drizzle(c.env.DB);
  const body = await c.req.json();

  const invoice = await db.insert(invoices).values({
    id: crypto.randomUUID(),
    vendorName: body.vendorName,
    invoiceNumber: body.invoiceNumber,
    totalAmount: body.totalAmount,

|  |

    status: 'NEW',
    rawContent: body.rawContent,
    createdAt: new Date().toISOString(),
  }).returning().get();

  return c.json(invoice, 201);
});

export default app;
```text
**Workers AI with OpenAI SDK (src/lib/ai.ts):**
```typescript
import { OpenAI } from 'openai';

export function createAI(apiToken: string) {
  return new OpenAI({
    apiKey: apiToken,
    baseURL: 'https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/gateway/openai',
  });
}

// Use with Workers AI native (for Llama models)
export async function extractWithWorkersAI(env: Env, content: string) {
  const response = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [{
      role: 'user',
      content: `Extract invoice data from this content. Return JSON with: vendorName, invoiceNumber, totalAmount, lineItems array. Content: ${content}`
    }],
    schema: {
      type: 'object',
      properties: {
        vendorName: { type: 'string' },
        invoiceNumber: { type: 'string' },
        totalAmount: { type: 'number' },
        lineItems: { type: 'array' }
      }
    }
  });

  return response;
}
```text
## # Phase 3: Queue Processing
**Weeks 5-6**

- [ ] Set up Cloudflare Queues for async processing
- [ ] Migrate LangGraph workflow to Queue Consumers
- [ ] Implement human-in-the-loop with Durable Objects

```typescript
// src/queues/processor.ts
export default {
  async queue(batch, env) {
    for (const message of batch.messages) {
      const { type, data } = JSON.parse(message.body)

      switch (type) {
        case 'EXTRACT':
          await processExtraction(data, env)
          break
        case 'VALIDATE':
          await processValidation(data, env)
          break
        case 'APPROVE':
          await processApproval(data, env)
          break
      }
    }
  }
}

async function processExtraction(data, env) {
  const result = await extractInvoice(data.rawContent)

  // Write to D1
  await env.DB.insert(invoicesTable).values({
    ...result,
    status: 'EXTRACTED'
  })

  // Queue validation
  await env.INVOICE_QUEUE.send({
    type: 'VALIDATE',
    data: { invoiceId: result.id }
  })
}
```text
## # Phase 4: Frontend Migration
**Weeks 7-8**

- [ ] Deploy Next.js to Cloudflare Pages
- [ ] Replace API calls to point to Worker endpoints
- [ ] Implement optimistic updates with React Query
- [ ] Add real-time updates via Durable Objects

## # Phase 5: AI & Vector Integration
**Weeks 9-10**

- [ ] Configure Python AI service to use Workers AI via OpenAI SDK
- [ ] Set up Vectorize for invoice embedding search
- [ ] Implement similarity search for duplicate detection

**Python AI Service - Workers AI Integration (ai/app/ai/workers_ai.py):**
```python
from openai import OpenAI
from pydantic_settings import SettingsConfigDict

class WorkersAIClient:
    def __init__(self, api_token: str, account_id: str):
        self.client = OpenAI(
            api_key=api_token,
            base_url=f"https://gateway.ai.cloudflare.com/v1/{account_id}/gateway/openai"
        )

    async def extract_invoice(self, raw_content: str) -> dict:
        """Extract invoice data using Llama 3.1 via Workers AI"""
        response = self.client.chat.completions.create(
            model="@cf/meta/llama-3.1-8b-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "Extract invoice data. Return JSON with: vendorName, invoiceNumber, totalAmount, lineItems array."
                },
                {"role": "user", "content": raw_content}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
```text
**Vectorize for Duplicate Detection:**
```typescript
// In Worker - src/lib/vectorize.ts
export async function findSimilarInvoices(env: Env, invoiceText: string) {
  // Get embedding from Workers AI
  const embedding = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: invoiceText
  });

  // Query Vectorize
  return await env.VECTORIZE.query(embedding.vector, {
    topK: 5,
    filter: { status: 'PROCESSED' }
  });
}
```text
---

# # Estimated Costs (Monthly)

| Component | Free Tier | Pay-as-you-go |
| ----------- | ----------- | --------------- |
| Workers | 100K requests/day | $0.30/million |
| Workers AI | 10K tokens/day | $0.01/1K tokens |
| D1 | 5GB storage, 5M reads/day | $0.75/GB |
| R2 | 1GB storage, 1M reads | $0.015/GB |
| Vectorize | 1M vectors | $0.05/1M |
| Queues | 1M operations | $0.40/1M |


**Total estimated:** $5-20/month (depends on volume)

---

# # Reusable Components from Current Code

| File | Migration |
| ------ | ----------- |
| `ai/app/schemas/invoice.py` | Convert Pydantic → Zod schemas |
| `ai/app/agents/extractor.py` | Rewrite with Workers AI SDK |
| `ai/app/graphs/invoice_workflow.py` | Convert to Queue Consumers |
| `fullstack/lib/utils.ts` | Reuse (pure functions) |
| `fullstack/prisma/schema.prisma` | Modify for SQLite/D1 |


---

# # Rollback Strategy

1. Keep existing deployment during migration
2. Deploy Cloudflare version to staging subdomain
3. Run parallel for 1 week
4. Switch DNS after validation

---

# # Success Metrics

- **Cold start**: < 100ms (edge)
- **AI extraction**: < 2s
- **Cost reduction**: 50-70% vs current
- **Availability**: 99.9% SLA
