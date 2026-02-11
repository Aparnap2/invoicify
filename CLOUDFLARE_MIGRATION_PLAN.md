# Cloudflare Migration Plan: Invoicify-Worker

## Executive Summary

This document outlines the strategic migration from the hybrid Python/TypeScript architecture to a **Cloudflare-Only Stack** using Durable Objects, Queues, and Groq API for invoice processing.

**Current State**:
- `python-worker/`: Contains working TypeScript Hono app with routes, QuickBooks integration, vendor trust system
- `worker/`: Basic Cloudflare scaffolding (to be archived)
- `ai/` & `temporal/`: Python/LangGraph/Temporal code (to be archived)

**Target State**:
- `invoicify-worker/`: Single Cloudflare-native TypeScript codebase
- Replaces Temporal with Durable Objects
- Replaces Python ML with TypeScript z-score calculations
- Replaces LangGraph with Groq Vision API

---

## Phase 1: Foundation (Safety First)

### 1.1 Create Backup Branch
```bash
git checkout -b migration/cloudflare-only
git add -A
git commit -m "SNAPSHOT: Pre-migration baseline"
git tag baseline-pre-migration
```

### 1.2 Rename Directory Structure
```bash
mv python-worker invoicify-worker
mkdir -p invoicify-worker/src/durable-objects
mkdir -p invoicify-worker/src/lib/groq
```

### 1.3 Clean Up Python Files
**Delete these files from invoicify-worker/**:
```bash
# Remove Python artifacts
rm -f invoicify-worker/pyproject.toml
rm -rf invoicify-worker/.venv
rm -f invoicify-worker/src/__init__.py
rm -f invoicify-worker/src/worker.py
rm -rf invoicify-worker/src/activities/*.py
rm -rf invoicify-worker/src/domain/*.py
rm -rf invoicify-worker/src/infrastructure/*.py
rm -rf invoicify-worker/src/workflows/*.py
rm -rf invoicify-worker/src/__pycache__
rm -rf invoicify-worker/src/activities/__pycache__
rm -rf invoicify-worker/src/domain/__pycache__
rm -rf invoicify-worker/src/infrastructure/__pycache__
rm -rf invoicify-worker/.pytest_cache
```

---

## Phase 2: Cloudflare Configuration

### 2.1 Update wrangler.toml

**File**: `invoicify-worker/wrangler.toml`

```toml
name = "invoicify-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"
node_compat = true

# D1 Database
[[d1_databases]]
binding = "DB"
database_name = "invoicify-db"
database_id = "your-database-id-here"

# R2 Storage
[[r2_buckets]]
binding = "R2_BUCKET"
bucket_name = "invoicify-storage"

# Queue for async processing
[[queues.producers]]
binding = "INVOICE_QUEUE"
queue = "invoicify-queue"

[[queues.consumers]]
queue = "invoicify-queue"
max_batch_size = 10
max_batch_timeout = 30

# Durable Objects
[[durable_objects.bindings]]
name = "INVOICE_PROCESSOR"
class_name = "InvoiceProcessor"

# KV for session/cache
[[kv_namespaces]]
binding = "CACHE"
id = "your-kv-id-here"

[vars]
ENVIRONMENT = "development"

# Secrets (set via wrangler secret put)
# GROQ_API_KEY
# QUICKBOOKS_CLIENT_ID
# QUICKBOOKS_CLIENT_SECRET
# SALESFORCE_USERNAME
# SALESFORCE_PASSWORD
# SALESFORCE_SECURITY_TOKEN
```

### 2.2 Update package.json

**File**: `invoicify-worker/package.json`

```json
{
  "name": "invoicify-worker",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "wrangler dev --port 8787",
    "deploy": "wrangler deploy",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "db:migrate:create": "wrangler d1 migrations create invoicify-db",
    "db:migrate:local": "wrangler d1 migrations apply invoicify-db --local",
    "db:migrate:prod": "wrangler d1 migrations apply invoicify-db --remote",
    "db:seed": "wrangler d1 execute invoicify-db --file ./seed.sql",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "hono": "^4.6.0",
    "drizzle-orm": "^0.38.0",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20250109.0",
    "typescript": "^5.7.0",
    "vitest": "^2.1.0",
    "wrangler": "^3.103.0"
  }
}
```

---

## Phase 3: Database Schema Updates

### 3.1 Update Drizzle Schema

**File**: `invoicify-worker/src/db/schema.ts`

Add these new fields to existing schema:

```typescript
// Add to invoices table
r2KeyRaw: text('r2_key_raw'),
r2KeyProcessed: text('r2_key_processed'),
queueMessageId: text('queue_message_id'),
processedBy: text('processed_by'), // DO instance ID
startedAt: text('started_at'),
completedAt: text('completed_at'),
```

### 3.2 Create Migration

```bash
cd invoicify-worker
wrangler d1 migrations create invoicify-db add_cloudflare_fields
```

**Migration SQL**:
```sql
ALTER TABLE invoices ADD COLUMN r2_key_raw TEXT;
ALTER TABLE invoices ADD COLUMN r2_key_processed TEXT;
ALTER TABLE invoices ADD COLUMN queue_message_id TEXT;
ALTER TABLE invoices ADD COLUMN processed_by TEXT;
ALTER TABLE invoices ADD COLUMN started_at TEXT;
ALTER TABLE invoices ADD COLUMN completed_at TEXT;

-- Index for queue processing
CREATE INDEX idx_invoices_queue ON invoices(queue_message_id);
CREATE INDEX idx_invoices_processed_by ON invoices(processed_by);
```

---

## Phase 4: Durable Object Implementation

### 4.1 Create InvoiceProcessor Durable Object

**File**: `invoicify-worker/src/durable-objects/InvoiceProcessor.ts`

```typescript
import { DurableObject } from 'cloudflare:workers';
import type { Env } from '../db';

export interface InvoiceMessage {
  traceId: string;
  r2KeyRaw: string;
  vendorId?: string;
  uploadedAt: string;
}

export class InvoiceProcessor extends DurableObject {
  private env: Env;
  
  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    this.env = env;
    
    // Resume any in-progress processing after restart
    this.ctx.blockConcurrencyWhile(async () => {
      await this.resumePending();
    });
  }

  // HTTP endpoint for manual triggering/debugging
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    
    if (url.pathname === '/status') {
      const storage = await this.ctx.storage.list();
      return Response.json({
        id: this.ctx.id.toString(),
        pendingJobs: storage.size,
        timestamp: new Date().toISOString()
      });
    }
    
    return new Response('InvoiceProcessor Durable Object', { status: 200 });
  }

  // Queue consumer handler
  async queue(batch: MessageBatch<InvoiceMessage>): Promise<void> {
    for (const message of batch.messages) {
      try {
        await this.processInvoice(message.body);
        message.ack();
      } catch (error) {
        console.error(`Failed to process invoice ${message.body.traceId}:`, error);
        
        // Retry with exponential backoff
        if (message.attempts < 3) {
          message.retry();
        } else {
          // Move to dead letter queue or manual review
          await this.handleFailedInvoice(message.body, error as Error);
          message.ack();
        }
      }
    }
  }

  private async processInvoice(message: InvoiceMessage): Promise<void> {
    const { traceId, r2KeyRaw } = message;
    
    // Store processing state
    await this.ctx.storage.put(`job:${traceId}`, {
      status: 'processing',
      startedAt: Date.now(),
      r2KeyRaw
    });

    try {
      // Step 1: Download PDF from R2
      const pdfBuffer = await this.downloadFromR2(r2KeyRaw);
      
      // Step 2: Extract with Groq Vision
      const extractedData = await this.extractWithGroq(pdfBuffer, traceId);
      
      // Step 3: Calculate risk score
      const riskScore = await this.calculateRisk(extractedData);
      
      // Step 4: Make decision
      const decision = await this.makeDecision(extractedData, riskScore);
      
      // Step 5: Execute
      if (decision.action === 'AUTO_APPROVE') {
        await this.autoApprove(traceId, extractedData, riskScore);
      } else if (decision.action === 'HITL') {
        await this.sendToHumanReview(traceId, extractedData, riskScore, decision.reasons);
      } else {
        await this.reject(traceId, extractedData, riskScore, decision.reasons);
      }
      
      // Update state
      await this.ctx.storage.put(`job:${traceId}`, {
        status: 'completed',
        completedAt: Date.now(),
        decision: decision.action
      });
      
    } catch (error) {
      await this.ctx.storage.put(`job:${traceId}`, {
        status: 'failed',
        failedAt: Date.now(),
        error: (error as Error).message
      });
      throw error;
    }
  }

  private async downloadFromR2(key: string): Promise<ArrayBuffer> {
    const object = await this.env.R2_BUCKET.get(key);
    if (!object) {
      throw new Error(`PDF not found in R2: ${key}`);
    }
    return await object.arrayBuffer();
  }

  private async extractWithGroq(pdfBuffer: ArrayBuffer, traceId: string): Promise<any> {
    // Convert to base64
    const base64 = btoa(String.fromCharCode(...new Uint8Array(pdfBuffer)));
    
    // Call Groq API
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.env.GROQ_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'llama-3.2-90b-vision-preview',
        messages: [{
          role: 'user',
          content: [
            {
              type: 'text',
              text: 'Extract invoice data as JSON. Include: vendor_name, invoice_number, amount (numeric), currency, invoice_date (ISO), due_date (ISO), line_items (array of {description, quantity, unit_price, total})'
            },
            {
              type: 'image_url',
              image_url: {
                url: `data:application/pdf;base64,${base64}`
              }
            }
          ]
        }],
        response_format: { type: 'json_object' },
        temperature: 0.1
      })
    });

    if (!response.ok) {
      throw new Error(`Groq API error: ${response.statusText}`);
    }

    const data = await response.json();
    return JSON.parse(data.choices[0].message.content);
  }

  private async calculateRisk(invoiceData: any): Promise<number> {
    // Query vendor history from D1
    const vendorHistory = await this.getVendorHistory(invoiceData.vendor_name);
    
    // Calculate z-score for amount
    const zScore = this.calculateZScore(
      parseFloat(invoiceData.amount),
      vendorHistory.map(h => h.amount)
    );
    
    // Normalize to 0-1 risk score
    let riskScore = Math.min(zScore / 3, 1.0);
    
    // Additional signals
    if (parseFloat(invoiceData.amount) > 10000) riskScore += 0.2;
    if (vendorHistory.length < 3) riskScore += 0.3;
    
    return Math.min(riskScore, 1.0);
  }

  private calculateZScore(amount: number, history: number[]): number {
    if (history.length < 5) return 0.5;
    
    const mean = history.reduce((a, b) => a + b, 0) / history.length;
    const variance = history.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / history.length;
    const stdDev = Math.sqrt(variance);
    
    if (stdDev === 0) return 0;
    return Math.abs((amount - mean) / stdDev);
  }

  private async getVendorHistory(vendorName: string): Promise<any[]> {
    // Query D1 for vendor's past invoices
    const result = await this.env.DB.prepare(`
      SELECT amount FROM invoices 
      WHERE vendor_name = ? 
      ORDER BY created_at DESC 
      LIMIT 20
    `).bind(vendorName).all();
    
    return result.results || [];
  }

  private async makeDecision(invoiceData: any, riskScore: number): Promise<{action: string, reasons: string[]}> {
    const reasons: string[] = [];
    
    if (riskScore > 0.7) {
      reasons.push(`High risk score: ${riskScore.toFixed(2)}`);
      return { action: 'REJECT', reasons };
    }
    
    if (riskScore > 0.3) {
      reasons.push(`Medium risk score: ${riskScore.toFixed(2)}`);
      return { action: 'HITL', reasons };
    }
    
    return { action: 'AUTO_APPROVE', reasons: ['Low risk'] };
  }

  private async autoApprove(traceId: string, invoiceData: any, riskScore: number): Promise<void> {
    // Create QuickBooks bill
    // Update D1 status
    // Store processed result in R2
    console.log(`Auto-approved invoice ${traceId}`);
  }

  private async sendToHumanReview(traceId: string, invoiceData: any, riskScore: number, reasons: string[]): Promise<void> {
    // Update D1 status to HITL
    // Send notification
    console.log(`Sent ${traceId} to human review`);
  }

  private async reject(traceId: string, invoiceData: any, riskScore: number, reasons: string[]): Promise<void> {
    // Update D1 status to REJECTED
    console.log(`Rejected invoice ${traceId}`);
  }

  private async handleFailedInvoice(message: InvoiceMessage, error: Error): Promise<void> {
    // Store in failed queue or alert
    console.error(`Invoice ${message.traceId} failed permanently:`, error.message);
  }

  private async resumePending(): Promise<void> {
    // Check for any jobs that were processing before restart
    const jobs = await this.ctx.storage.list({ prefix: 'job:' });
    for (const [key, value] of jobs) {
      if ((value as any).status === 'processing') {
        console.log(`Resuming job: ${key}`);
        // Could re-process or mark as failed depending on requirements
      }
    }
  }
}
```

---

## Phase 5: Update Main Index

### 5.1 Update src/index.ts

Add Durable Object and Queue exports:

```typescript
import { InvoiceProcessor } from './durable-objects/InvoiceProcessor';

// ... existing Hono app code ...

export { InvoiceProcessor };

// Queue handler export
export default {
  fetch: app.fetch,
  
  async queue(batch: MessageBatch<any>, env: Env, ctx: ExecutionContext) {
    // Route to Durable Object
    const id = env.INVOICE_PROCESSOR.idFromName('processor-1');
    const processor = env.INVOICE_PROCESSOR.get(id);
    await processor.queue(batch);
  },
  
  async scheduled(controller: any, env: Env, ctx: ExecutionContext) {
    console.log("Scheduled job at", new Date().toISOString());
  }
};
```

---

## Phase 6: Integration Testing

### 6.1 Create Test Suite

**File**: `invoicify-worker/src/durable-objects/__tests__/InvoiceProcessor.test.ts`

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { InvoiceProcessor } from '../InvoiceProcessor';

describe('InvoiceProcessor', () => {
  let processor: InvoiceProcessor;
  let mockEnv: any;
  
  beforeEach(() => {
    mockEnv = {
      DB: { prepare: vi.fn() },
      R2_BUCKET: { get: vi.fn() },
      GROQ_API_KEY: 'test-key'
    };
    
    processor = new InvoiceProcessor({} as any, mockEnv);
  });

  it('should calculate z-score correctly', () => {
    const zScore = (processor as any).calculateZScore(150, [100, 110, 120, 130, 140]);
    expect(zScore).toBeGreaterThan(0);
  });

  it('should return low risk for unknown vendors', () => {
    const risk = (processor as any).calculateZScore(100, []);
    expect(risk).toBe(0.5);
  });
});
```

---

## Phase 7: Deployment Checklist

### 7.1 Pre-Deployment
- [ ] All tests passing
- [ ] Migration applied to local D1
- [ ] R2 bucket created
- [ ] Queue created
- [ ] Durable Object bindings configured
- [ ] Secrets set (GROQ_API_KEY, etc.)

### 7.2 Deploy Steps
```bash
cd invoicify-worker

# Apply migrations
wrangler d1 migrations apply invoicify-db --remote

# Deploy
wrangler deploy

# Verify
wrangler tail
```

### 7.3 Post-Deployment
- [ ] Upload test invoice
- [ ] Verify queue processing
- [ ] Check D1 records
- [ ] Verify R2 storage
- [ ] Test Durable Object status endpoint

---

## Golden Invoice Test

Upload a test invoice and verify:
1. ✅ PDF stored in R2
2. ✅ Queue message sent
3. ✅ Durable Object processes message
4. ✅ Groq extracts data
5. ✅ Risk score calculated
6. ✅ Decision made (approve/HITL/reject)
7. ✅ D1 updated with results
8. ✅ Processed JSON stored in R2

---

## Risk Mitigation

### Risk: Groq API Rate Limits
**Mitigation**: Implement exponential backoff, cache results

### Risk: Durable Object Restarts
**Mitigation**: Use `blockConcurrencyWhile` to resume state

### Risk: Queue Message Loss
**Mitigation**: ACK only after successful processing, retry logic

### Risk: Large PDF Processing
**Mitigation**: Size limits, timeout handling, streaming

---

## Rollback Plan

If migration fails:
```bash
git checkout baseline-pre-migration
wrangler deploy --env production-legacy
```

---

## Timeline

- **Phase 1-2**: 1 day (Foundation & Config)
- **Phase 3-4**: 2 days (Database & Durable Objects)
- **Phase 5**: 1 day (Integration)
- **Phase 6-7**: 1 day (Testing & Deployment)

**Total**: 5 days

---

## Success Criteria

1. ✅ All existing routes continue working
2. ✅ Invoice processing via Durable Objects
3. ✅ Risk calculation in TypeScript
4. ✅ Groq Vision extraction
5. ✅ Queue-based async processing
6. ✅ <30s end-to-end processing time
7. ✅ Zero data loss during migration
