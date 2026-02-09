# Invoicify Upgrade Plan - Cloudflare-Only Stack

# # Architecture Summary

```text
┌─────────────────────────────────────────────────────────────────┐
│                      Cloudflare Global Network                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Email      │  │   R2 Storage │  │   Manual     │         │
│  │   IMAP       │  │   (Invoices) │  │   Upload     │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                 │                   │
│         └────────────────┼─────────────────┘                   │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Cloudflare Workers (Hono API)               │   │
│  │  - Invoice CRUD  - R2 Upload  - Vision OCR  - Fraud     │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Cloudflare D1 (Drizzle ORM)                 │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Workers AI (Llama Vision)                   │   │
│  │  - OCR  - Fraud Detection  - Risk Analysis               │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    QuickBooks Integration                │   │
│  └───────────────────────────┬─────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Cloudflare Pages (Next.js)                  │   │
│  │  - Dashboard  - Analytics  - Approval UI  - Reports     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```text
---

# # Technology Stack

| Component | Technology | Rationale |
| ----------- | ------------ | ----------- |
| Runtime | Cloudflare Workers | Edge compute, low latency |
| API Framework | Hono | Fast, lightweight, WSGI compatible |
| Database | Cloudflare D1 + Drizzle | SQLite at edge, type-safe |
| Storage | Cloudflare R2 | No egress fees, S3-compatible |
| AI/OCR | Workers AI (Llama Vision) | Multimodal, no Tesseract needed |
| ERP | QuickBooks Online API | OAuth2 + REST |
| Frontend | Next.js 16 + shadcn/ui | React, components, hooks |
| Charts | Recharts | Lightweight, composable |


---

# # Implementation Phases

## # Phase 1: D1 Schema + Migrations (Week 1)

**Files to create:**
- `worker/src/db/schema.ts` - Drizzle schema for D1
- `worker/drizzle.config.ts` - Drizzle Kit config
- `worker/wrangler.toml` - Workers config with D1 binding

**Schema:**
```typescript
// worker/src/db/schema.ts
import { sqliteTable, text, real, integer } from 'drizzle-orm/sqlite-core';
import { sql } from 'drizzle-orm';

export const invoices = sqliteTable('invoices', {
  id: text('id').primaryKey(),
  vendorName: text('vendor_name').notNull(),
  vendorId: text('vendor_id'),
  invoiceNumber: text('invoice_number').notNull(),
  totalAmount: real('total_amount').notNull(),
  currency: text('currency').default('USD'),
  status: text('status').default('NEW'),
  dueDate: text('due_date'),
  rawContent: text('raw_content'),
  extractedData: text('extracted_data'),
  confidenceScore: real('confidence_score'),
  riskScore: real('risk_score'),
  riskLevel: text('risk_level'),
  fileUrl: text('file_url'),
  createdAt: text('created_at').default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text('updated_at'),
});

export const vendors = sqliteTable('vendors', {
  id: text('id').primaryKey(),
  name: text('name').notNull(),
  taxId: text('tax_id'),
  email: text('email'),
  bankAccount: text('bank_account'),
  isVerified: integer('is_verified', { mode: 'boolean' }).default(false),
  riskLevel: text('risk_level'),
  createdAt: text('created_at').default(sql`CURRENT_TIMESTAMP`),
});

export const approvals = sqliteTable('approvals', {
  id: text('id').primaryKey(),
  invoiceId: text('invoice_id').notNull(),
  approverId: text('approver_id').notNull(),
  status: text('status').notNull(),
  comments: text('comments'),
  createdAt: text('created_at').default(sql`CURRENT_TIMESTAMP`),
});

export const auditLogs = sqliteTable('audit_logs', {
  id: text('id').primaryKey(),
  action: text('action').notNull(),
  entityId: text('entity_id').notNull(),
  performedBy: text('performed_by'),
  createdAt: text('created_at').default(sql`CURRENT_TIMESTAMP`),
});
```text
---

## # Phase 2: Llama Vision OCR (Week 2)

**Files to create:**
- `worker/src/lib/vision-ocr.ts` - Vision extraction
- `worker/src/routes/extract.ts` - Extraction endpoint

**Vision Extraction:**
```typescript
// worker/src/lib/vision-ocr.ts
export async function extractInvoiceWithVision(
  env: Env,
  imageBase64: string
): Promise<InvoiceExtractionResult> {
  const response = await env.AI.run('@cf/meta/llama-3.2-11b-vision-instruct', {
    messages: [
      {
        role: 'user',
        content: [
          { type: 'text', text: 'Extract invoice data. Return JSON with: vendorName, invoiceNumber, totalAmount, lineItems (array with description, quantity, unitPrice, amount), dueDate, currency.' },
          { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${imageBase64}` } }
        ]
      }
    ],
    response_format: { type: 'json_object' }
  });

  const parsed = JSON.parse(response.completion);
  return {
    data: parsed,
    confidence: response.usage ? calculateConfidence(response.usage) : 0.85
  };
}
```text
---

## # Phase 3: Cloudflare R2 Storage (Week 3)

**Files to create:**
- `worker/src/lib/r2-storage.ts` - R2 operations
- `worker/src/routes/upload.ts` - Upload endpoint

**R2 Upload:**
```typescript
// worker/src/lib/r2-storage.ts
export async function uploadToR2(
  env: Env,
  key: string,
  body: ArrayBuffer,
  contentType: string
): Promise<string> {
  await env.INVOICE_BUCKET.put(key, body, {
    httpMetadata: { contentType }
  });
  return `https://${env.INVOICE_BUCKET}.r2.dev/${key}`;
}
```text
**wrangler.toml:**
```toml
name = "invoicify-api"
main = "src/index.ts"
compatibility_date = "2024-09-26"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "invoicify-db"
database_id = "${CLOUDFLARE_DATABASE_ID}"
migrations_dir = "drizzle/migrations"

[[r2_buckets]]
binding = "INVOICE_BUCKET"
bucket_name = "invoicify-files"
```text
---

## # Phase 4: Fraud Detection (Week 4)

**Files to create:**
- `worker/src/lib/fraud-detection.ts` - Risk analysis
- `worker/src/lib/duplicate-check.ts` - Duplicate detection

**Risk Analysis:**
```typescript
// worker/src/lib/fraud-detection.ts
export function calculateRiskScore(
  invoice: InvoiceData,
  vendorHistory: VendorHistory
): RiskResult {
  const indicators: RiskIndicator[] = [];

  // Amount anomaly (>3x average)
  if (invoice.amount > vendorHistory.avgAmount * 3) {
    indicators.push({ type: 'AMOUNT_ANOMALY', severity: 'HIGH', score: 30 });
  }

  // New vendor
  if (!vendorHistory.exists) {
    indicators.push({ type: 'NEW_VENDOR', severity: 'MEDIUM', score: 20 });
  }

  // Bank account changed
  if (invoice.bankAccount !== vendorHistory.bankAccount) {
    indicators.push({ type: 'BANK_CHANGE', severity: 'HIGH', score: 25 });
  }

  // Urgent payment
  if (['COD', 'Immediate', 'Net 0'].includes(invoice.paymentTerms)) {
    indicators.push({ type: 'URGENT_PAYMENT', severity: 'MEDIUM', score: 15 });
  }

  return {
    score: indicators.reduce((sum, i) => sum + i.score, 0),
    level: classifyRisk(indicators),
    indicators
  };
}
```text
---

## # Phase 5: QuickBooks Integration (Week 5)

**Files to create:**
- `worker/src/lib/quickbooks.ts` - QuickBooks adapter

**QuickBooks Adapter:**
```typescript
// worker/src/lib/quickbooks.ts
export class QuickBooksAdapter {
  constructor(private env: Env) {}

  async createBill(invoice: InvoiceData): Promise<string> {
    const token = await this.getAccessToken();
    const vendorId = await this.ensureVendor(invoice.vendorName);

    const response = await fetch(
      `https://quickbooks.api.intuit.com/v3/company/${this.env.QB_REALM_ID}/bill`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          VendorRef: { value: vendorId },
          TxnDate: invoice.invoiceDate,
          DueDate: invoice.dueDate,
          Line: invoice.lineItems.map(item => ({
            Amount: item.amount,
            DetailType: 'AccountBasedExpenseLineDetail',
            AccountBasedExpenseLineDetail: {
              AccountRef: { value: this.env.QB_EXPENSE_ACCOUNT }
            }
          })),
          DocNumber: invoice.invoiceNumber
        })
      }
    );

    const result = await response.json();
    return result.Bill.Id;
  }
}
```text
---

## # Phase 6: Analytics Dashboard (Week 6)

**Files to create:**
- `fullstack/app/dashboard/analytics/page.tsx` - Analytics page
- `fullstack/components/analytics/*` - Reusable chart components

**Reusable Components:**
```typescript
// fullstack/components/analytics/KpiCard.tsx
'use client';
interface KpiCardProps {
  title: string;

|  |

  change?: number;
  icon: React.ReactNode;
}
export function KpiCard({ title, value, change, icon }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {change !== undefined && (
          <p className={change >= 0 ? 'text-green-600' : 'text-red-600'}>
            {change >= 0 ? '+' : ''}{change}%
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// fullstack/components/analytics/InvoiceChart.tsx
'use client';
export function InvoiceChart({ data }: { data: ChartData }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data}>
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Area type="monotone" dataKey="count" stroke="#8884d8" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```text
---

# # Dependencies

## # Worker (TypeScript)
```json
{
  "dependencies": {
    "hono": "^4.0.0",
    "drizzle-orm": "^0.45.0",
    "@cloudflare/ai": "^1.0.0"
  },
  "devDependencies": {
    "wrangler": "^4.0.0",
    "drizzle-kit": "^0.30.0",
    "typescript": "^5.0.0"
  }
}
```text
## # Frontend (TypeScript)
```json
{
  "dependencies": {
    "next": "^16.0.0",
    "react": "^19.0.0",
    "recharts": "^2.10.0",
    "lucide-react": "^0.560.0",
    "@tanstack/react-query": "^5.0.0"
  }
}
```text
---

# # Timeline

| Phase | Week | Deliverables |
| ------- | ------ | -------------- |
| 1: D1 Schema | Week 1 | Schema, migrations, wrangler config |
| 2: Vision OCR | Week 2 | Llama Vision extraction, extraction endpoint |
| 3: R2 Storage | Week 3 | Upload/download, file URL management |
| 4: Fraud Detection | Week 4 | Risk scoring, duplicate detection |
| 5: QuickBooks | Week 5 | Bill creation, vendor sync |
| 6: Analytics | Week 6 | Dashboard, KPI cards, charts |
