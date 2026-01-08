Absolutely — here’s a **fully detailed project scaffold** for **PROJECT #2: Invoice & Expense Automation Agent** that you can drop into your portfolio and *actually build* with agentic AI + workflow automation + real business value.
This includes **use-case context**, **features**, **SOPs**, **data model**, **integration workflow**, **code snippets**, **architecture**, **test plan**, and **demo milestones** — all grounded in industry reality.

Everything below is built from how modern invoice/AP automation actually works in the real world, not just theoretical ideas. ([NetSuite][1])

---

# 📌 Project: **Agentic Invoice & Expense Automation System**

**Tagline:**
*AI agent that fully automates invoice ingestion, extraction, validation, routing, approval, and system posting — with human-in-the-loop (HITL) controls and audit trails.*

**Primary Users:**
Finance/Accounts Payable teams, CFOs, Controllers

**Primary Pain Points:**

* Manual data entry from PDFs and emails
* Mismatched POs/invoices
* Missing fields requiring human scrubbing
* Slow multi-step approval loops
* Time-consuming GL coding tasks

**Architecture:** Cloudflare Edge (Workers + Pages + D1 + R2 + Queues) with Python AI Service

---

## 🎯 Outcome Promise

**Reduce accounts payable cycle time by up to 80%**
**Increase straight-through processing (STP) rate significantly**
**Free finance teams for higher-value work**

Industry trend: AI is shifting AP from manual processes to strategic value operations through better extraction, decision logic, approval workflows, and predictive analytics. ([highradius.com][2])

---

# 📐 Feature & SOP Breakdown

### **SOP-INV-01 — Invoice Ingestion & Normalization**

**Trigger:**
• Email attachments
• Supplier portal uploads
• Scanned uploads

**Tasks:**

1. Receive invoice (PDF, image, doc)
2. Normalize input (map to event schema)
3. Extract raw content

**Engineering:** Connectors for email inbox, S3 upload, or webhook ingestion.

---

### **SOP-INV-02 — Data Extraction (OCR + AI)**

**Goal:** Build structured data (vendor, line items, amounts, due date).

**Steps:**

1. Preprocess image/PDF
2. OCR extraction for text
3. AI field parsing (line items, totals, taxes)

**Outcomes:**

* Structured invoice json
* Confidence scores per field (used for HITL logic)

Key trend: Intelligent extraction + validation reduces error rates compared to simple RPA. ([Tipalti][3])

---

### **SOP-INV-03 — PO Matching & Validation**

**Goal:**
Match extracted invoice fields against Purchase Orders and budget controls.

**Checks:**

* PO number exists
* Amount matches tolerance
* Vendor terms validity
* Duplicate invoice detection

**Escalation Logic:**
• Flag mismatch or missing PO
• Merge with exceptions workflow

---

### **SOP-INV-04 — Routing & Approval**

**Goal:**
Route invoice for approval based on:

* Amount thresholds
* Department policies
* Role-based gates

**Outputs:**

* Approval request
* Notification to approvers
* SLA monitoring triggers

---

### **SOP-INV-05 — Posting to ERP / GL Coding**

**Goal:**
After approvals, update ERP (NetSuite, Odoo, SAP, QuickBooks), assign GL codes, and create payment entries.

**Tasks:**

* API update to ERP
* Reconciliation logs
* Notify relevant stakeholders

---

# 🧠 Integration Workflow (Agentic End-to-End)

```
(Invoices Uploaded via Email/Portal/Scanner)
              ↓
   Cloudflare Workers + Hono API
              ↓
   Normalized Event → D1 Database (SQLite)
              ↓
   Cloudflare Queues (Async Processing)
              ↓
   Python AI Service (Pydantic AI + LangGraph)
              ↓
   Workers AI (Llama 3.1 via OpenAI SDK)
              ↓
   Decision Response → Update D1
              ↓
   Cloudflare Pages (Next.js Frontend)
              ↓
   HITL approval (via API)
              ↓
   Execution Adapter → ERP/Accounting
              ↓
   Audit Log & Observability (D1)
```

**Architecture Notes:**
- **Workers API**: Hono-based CRUD endpoints at edge
- **D1**: SQLite database with Drizzle ORM (no connection pooling needed)
- **Queues**: Async job processing for heavy AI tasks
- **Python AI Service**: Separate FastAPI service calling Workers AI via OpenAI SDK
- **R2**: Invoice file storage (no egress fees)

---

## 🧱 Data Model (Drizzle + Cloudflare D1)

**Invoice Events Table (SQLite)**

```typescript
import { sqliteTable, text, real, integer } from 'drizzle-orm/sqlite-core';
import { sql } from 'drizzle-orm';

export const invoices = sqliteTable("invoices", {
  id: text("id").primaryKey(), // UUID string
  vendorName: text("vendor_name").notNull(),
  invoiceNumber: text("invoice_number").notNull(),
  dueDate: text("due_date"),
  totalAmount: real("total_amount").notNull(),
  currency: text("currency").default("USD"),
  rawContent: text("raw_content"),
  extractedData: text("extracted_data"), // JSON string
  status: text("status").default("NEW"),
  confidenceScore: real("confidence_score"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at"),
});

export const lineItems = sqliteTable("line_items", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id").references(() => invoices.id),
  description: text("description").notNull(),
  quantity: real("quantity").notNull(),
  unitPrice: real("unit_price").notNull(),
  amount: real("amount").notNull(),
});

export const invoiceApprovals = sqliteTable("invoice_approvals", {
  id: text("id").primaryKey(),
  invoiceId: text("invoice_id").notNull().references(() => invoices.id),
  approverId: text("approver_id").notNull(),
  status: text("status").notNull(), // APPROVED | REJECTED
  comments: text("comments"),
  riskLevel: text("risk_level"),
  decisionAt: text("decision_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

export const auditLogs = sqliteTable("audit_logs", {
  id: text("id").primaryKey(),
  action: text("action").notNull(), // CREATE | UPDATE | APPROVE | REJECT | DELETE
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id").notNull(),
  oldValue: text("old_value"),
  newValue: text("new_value"),
  performedBy: text("performed_by"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});
```

---

## 🧠 Agentic Workflow Graph (LangGraph)

```python
# services/ai/graphs/invoice_automation.py
from langgraph.graph import StateGraph

class InvoiceState(dict):
    pass

def extract_fields(state):
    # OCR + AI logic
    state["fields"] = your_ocr_parser(state["raw_content"])
    return state

def validate_po(state):
    state["matched"] = match_to_po(state["fields"])
    return state

def decide_escalation(state):
    if not state.get("matched"):
        state["decision_state"] = "ESCALATE"
    else:
        state["decision_state"] = "CONFIDENT"
    return state

graph = StateGraph(InvoiceState)
graph.add_node("extract_fields", extract_fields)
graph.add_node("validate_po", validate_po)
graph.add_node("escalate", decide_escalation)
graph.set_entry_point("extract_fields")
graph.add_edge("extract_fields", "validate_po")
graph.add_edge("validate_po", "escalate")
```

**Note:** OCR + AI parsing modules should call specialized models or libraries; this graph orchestrates data + logic.

---

## 🧪 Testing & Validation

### Unit Tests

* OCR extraction correct fields
* PO matching logic
* Duplicate detection

### Integration Tests

* End-to-end flow (ingest → extract → match)
* HITL approval path

**Metric Baselines:**
• First pass match accuracy ~90% (industry trend)
• Exception rate reduction
• Cycle time per invoice

---

## 🧰 Ready-to-Paste API Endpoints

**Cloudflare Worker API (TypeScript / Hono)**

```typescript
// src/index.ts
import { Hono } from 'hono';
import { drizzle } from 'drizzle-orm/d1';
import { invoices } from './db/schema';
import { eq, desc } from 'drizzle-orm';

interface Env {
  DB: D1Database;
  AI: Ai;
  INVOICE_BUCKET: R2Bucket;
}

const app = new Hono<{ Bindings: Env }>();

// GET /api/invoices - List invoices
app.get('/api/invoices', async (c) => {
  const db = drizzle(c.env.DB);
  const result = await db.select()
    .from(invoices)
    .orderBy(desc(invoices.createdAt))
    .limit(20)
    .all();
  return c.json({ invoices: result });
});

// GET /api/invoices/:id - Get single invoice
app.get('/api/invoices/:id', async (c) => {
  const db = drizzle(c.env.DB);
  const result = await db.select()
    .from(invoices)
    .where(eq(invoices.id, c.req.param('id')))
    .get();
  return result ? c.json(result) : c.json({ error: 'Not found' }, 404);
});

// POST /api/invoices - Create invoice
app.post('/api/invoices', async (c) => {
  const db = drizzle(c.env.DB);
  const body = await c.req.json();

  const invoice = await db.insert(invoices).values({
    id: crypto.randomUUID(),
    vendorName: body.vendorName,
    invoiceNumber: body.invoiceNumber,
    totalAmount: body.totalAmount,
    currency: body.currency || 'USD',
    status: 'NEW',
    rawContent: body.rawContent,
    createdAt: new Date().toISOString(),
  }).returning().get();

  return c.json(invoice, 201);
});

// PATCH /api/invoices/:id/status - Update status
app.patch('/api/invoices/:id/status', async (c) => {
  const db = drizzle(c.env.DB);
  const { status } = await c.req.json();

  await db.update(invoices)
    .set({ status, updatedAt: new Date().toISOString() })
    .where(eq(invoices.id, c.req.param('id')));

  return c.json({ success: true });
});

export default app;
```

**Python AI Service Decision Endpoint (FastAPI + Workers AI)**

```python
# ai/app/api/routes.py
from fastapi import APIRouter
from openai import OpenAI
from pydantic import BaseModel
from app.graphs.invoice_workflow import create_invoice_workflow

router = APIRouter()

class WorkersAIClient:
    def __init__(self, account_id: str, api_token: str):
        self.client = OpenAI(
            api_key=api_token,
            base_url=f"https://gateway.ai.cloudflare.com/v1/{account_id}/gateway/openai"
        )

    async def extract_invoice(self, raw_content: str) -> dict:
        response = self.client.chat.completions.create(
            model="@cf/meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "Extract invoice data as JSON. Include: vendorName, invoiceNumber, totalAmount, lineItems, dueDate."},
                {"role": "user", "content": raw_content}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

class DecisionRequest(BaseModel):
    invoice_id: str
    raw_content: str

@router.post("/ai/decide_invoice")
async def decide_invoice(req: DecisionRequest):
    # Run LangGraph workflow with Workers AI
    workflow = create_invoice_workflow()
    result = await workflow.run(
        raw_content=req.raw_content,
        invoice_id=req.invoice_id
    )
    return {
        "request_id": req.invoice_id,
        "state": result["decision_state"],
        "confidence": result.get("confidence", 0.85),
        "extracted_data": result.get("extracted_fields"),
        "requires_approval": result["decision_state"] == "approval_pending"
    }
```

---

## 📊 Portfolio Deliverables

### **Technical**

* Clean repo with Cloudflare edge architecture:

  * **Cloudflare Workers** - Hono-based API at edge (low latency worldwide)
  * **Cloudflare Pages** - Next.js frontend deployment
  * **Cloudflare D1** - SQLite database with Drizzle ORM
  * **Cloudflare R2** - Invoice file storage (no egress fees)
  * **Cloudflare Queues** - Async job processing
  * **Python AI Service** - Pydantic AI + LangGraph + Workers AI
  * **Agentic workflow engine** - LangGraph with human-in-the-loop
  * **Approval UI** - React dashboard
  * **Execution adapter** - ERP integration ready

### **Documentation**

* Architecture diagram
* Data model docs
* SOP definitions
* Test plans

### **Demo**

* Sample invoice cycle:

  1. Upload PDF
  2. AI extracts data
  3. Matches PO
  4. Escalates exceptions
  5. HITL approval
  6. Posts to mock ERP
* Time-lapse video showing reduced manual steps

### **Impact Metrics**

* Invoices/hour throughput
* Exception rate
* Automation percentage vs manual

---

## 📊 Related Industry Trends

* AI + OCR is central to invoice automation and AP workflows, extracting invoice fields accurately with minimal manual input. ([Tipalti][3])
* Automation reduces manual work, errors and improves supplier relationships and cash-flow efficiency. ([NetSuite][1])
* Hybrid AI automation (with exceptions routed to humans) is today’s best practice, and full touchless automation is a trend for 2025. ([highradius.com][2])

---

## 🧠 Why This Project Shines in a Portfolio

**Business relevance:** finance teams are actively adopting intelligent AP automation; research shows wide adoption and efficiency gains. ([quadient.com][4])
**Engineering discipline:** combining NLP/OCR, decision logic, agentic workflow execution
**Measurable value:** reduction in cycle time, error rates, manual burden

---


