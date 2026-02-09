Below is a **complete, self-contained, production-grade blueprint for *Invoicify* only**.
This is written as if you were handing it to **your future self, a co-founder, or an investor**.
No fluff. No generic SaaS nonsense. This is a **vertical, proactive, context-aware agentic AI system that replaces a junior accountant/AP role**, not an “invoice OCR tool”.

---

# INVOICIFY

**Proactive Finance Ops AI Intern for Seed–Series A Startups**

---

# # 0. One-line Definition (Lock This)

> **Invoicify is a proactive, context-aware finance operations agent that autonomously manages invoices, payables, vendor risk, and cash-runway decisions with human-in-the-loop controls.**

Not:

* ❌ Invoice OCR
* ❌ Accounting dashboard
* ❌ Simple automation

---

# # 1. ICP (Locked)

**Primary ICP**

* Technical founders (Seed → Series A)
* 5–50 employees
* No full-time finance team or only 1 finance generalist

**Environment**

* SaaS / software startups
* Stripe + bank + accounting software
* Founder cares about runway, not bookkeeping

**Pain Reality**

* Invoices arrive everywhere
* Payments are reactive
* Founder only notices problems when cash is low or vendor complains
* No real-time “financial awareness”

---

# # 2. Core Problem Statement (Truth)

> Founders don’t want to *process invoices*.
> They want to **never think about invoices until something matters**.

Existing tools:

* Digitize invoices ❌
* Require manual review ❌
* Are reactive ❌
* Don’t understand runway ❌

---

# # 3. Product Goals (Non-Negotiable)

1. **Proactive** – acts without prompts
2. **Context-aware** – reasons over cash, vendors, history
3. **Role-replacing** – behaves like a junior accountant
4. **Safe** – HITL for risky decisions
5. **Explainable** – every action is auditable

---

# # 4. Scope Boundaries (Very Important)

## # In Scope

* Accounts Payable (AP)
* Vendor payments
* Cash runway awareness
* Exception detection
* Approval routing
* **Cash Reconciliation (Mandatory)**
* Audit trail
* Learning loop for vendor trust

## # Explicitly Out of Scope (v1)

* Payroll
* Tax filing
* Revenue recognition
* Full ERP replacement
* CFO analytics

---

## # Why Cash Reconciliation is Mandatory

The role is **not finished** when the payment is scheduled. The agent must:
1. Monitor the bank feed
2. Match the transaction to scheduled payments
3. Mark as "Reconciled" in the ERP
4. **Alert immediately** if no match is found for significant outflows

Without this, the founder still performs **50% of the manual labor**.

---

# # 5. Feature List (Grouped by Agent Capability)

## # A. Perception (Input Layer)

* Email inbox monitoring ([AP@company.com](mailto:AP@company.com))
* PDF / image invoice ingestion
* Vendor portal polling (future)
* Manual upload (fallback)

---

## # B. Understanding (Context Layer)

* Invoice field extraction
* Vendor identification & history
* Contract & payment terms awareness
* Budget category mapping
* Cash runway snapshot
* Historical payment behavior

### # The Brain Upgrades (v1.1)

#### # 1. Strategic Mode Switch
A global state variable that shifts the Agent's reasoning:

| Mode | Behavior | Priority |
| ------ | ---------- | ---------- |
| **SURVIVAL** | Conserve cash, delay non-essential payments | Float over speed |
| **GROWTH** | Pay fast, build vendor trust, capture early-payment discounts | Speed over float |
| **OPTIMIZE** | Balanced reasoning, capture discounts when free | Trade-off optimization |


```typescript
const StrategyMode = {
  SURVIVAL: "SURVIVAL",   // Conserve cash
  GROWTH: "GROWTH",       // Pay fast
  OPTIMIZE: "OPTIMIZE",   // Balance
} as const;
```text
#### # 2. Semantic Contract Matching
Using **pgvector** embeddings to verify invoice line items against signed PDF contract terms:
- Extract key clauses from signed contracts (embeddings)
- Embed invoice line items
- Calculate cosine similarity to detect "surprise" charges (e.g., "Overage Fees" not in contract)

#### # 3. Zombie Detection (Aspirational V2)
Integration with SSO/HRIS data to flag payments for software with zero active users:
- Query identity provider for active user counts per vendor
- Flag subscriptions with $0 active users for review
- Prevent "zombie" vendor payments

---

## # C. Reasoning (Agent Brain)

* Is this invoice normal?
* Is this vendor trusted?
* Can we pay now without harming runway?
* Is this duplicate/fraud/anomaly?
* Should this be escalated?

---

## # D. Action (Execution Layer)

* Auto-approve low-risk invoices
* Schedule payments
* Route approvals
* Delay payments strategically
* Notify founder only when needed

---

## # E. Learning (Memory Loop)

* Learn from approvals/rejections
* Learn vendor behavior
* Improve confidence thresholds
* Reduce HITL over time

---

# # 6. System Architecture (Detailed)

## # High-Level Architecture

```text
[ Email / Upload / API ]
          ↓
[ Ingestion Service ]
          ↓
[ LangGraph Agent Orchestrator ]
          ↓
 ┌───────────────────────────────────────┐
 │ Context Layer                         │
 │  - Postgres + pgvector               │
 │  - Redis / Valkey                    │
 │  - Neo4j + Graphiti                  │
 └───────────────────────────────────────┘
          ↓
[ Decision + HITL Gates ]
          ↓
[ Execution Workers ]
          ↓
[ ERP / Bank / Notifications ]
```text
---

# # 7. Agent Architecture (LangGraph)

## # Agent Pattern Used

* **Hierarchical Agent**
* **ReAct reasoning**
* **Plan → Execute**
* **Human-in-the-Loop nodes**

## # Why Not Swarm?

Finance decisions require **consistency + auditability**, not creative divergence.

---

## # LangGraph Node Graph (Conceptual - Legacy Linear Flow)

```text
START → Ingest → Extract → Context → Risk → Decision → Execute → Reconcile → END
```text
---

# # 7A. Analyst-Critic Pattern (Production-Grade)

We are moving from a **linear graph** to a **Review-Critique Loop**. The Analyst proposes; the Critic audits.

## # The Autonomous Brain Architecture

```mermaid
graph TD
    Start[START] --> Ingest[INGEST]
    Ingest --> Extract[EXTRACT]
    Extract --> ContextFetch[CONTEXT]

    subgraph "The Autonomous Brain"
        ContextFetch --> AnalystNode[Analyst: Draft Decision]
        AnalystNode --> CriticNode[Critic: Auditor]

| Anomaly/Risk Detected |
| Safety Check Passed |

    end

    Execute --> Reconcile[Reconciliation Agent]
    Reconcile --> End[END]
```text
## # Analyst Node (Proposer)
- **Role:** Pattern recognition and historical analysis
- **Inputs:** Invoice data, vendor history, budget context
- **Outputs:** Proposed action with confidence score
- **Proposals:** `AUTO_APPROVE`, `HITL_REQUIRED`, `DELAY_PAYMENT`, `REJECT`

## # Critic Node (Auditor) - **The Safety Layer**
- **Role:** Safety checks using Priority Matrix
- **Priority Order (Non-Negotiable):**

| Priority | Check | Action if Failed |
| ---------- | ------- | ------------------ |
| 1 | **RUNWAY** | Block if runway < safety threshold |
| 2 | **STRATEGY** | Enforce mode-specific rules (SURVIVAL/ GROWTH/ OPTIMIZE) |
| 3 | **CONTRACT** | Flag if payment terms violated |
| 4 | **TRUST** | Apply auto-approve thresholds |
| 5 | **BUDGET** | Verify category limits |


## # Why This Pattern?
1. **Separation of Concerns** - Analyst is creative; Critic is conservative
2. **Auditability** - Every decision has a "why"
3. **Safety** - Critical checks run last, always
4. **Learning** - Critic's rejections become training data

## # Output Format
```typescript
interface DecisionSignal {

| "STRATEGY" | "CONTRACT" | "TRUST" |
| "WARNING" |

  message: string;
  recommendation: string;
}
```text
---

# # 7B. Trust Battery System (Implemented)

Gradual agent autonomy based on demonstrated accuracy.

## # Trust Levels

| Level | Name | Consecutive Accurate | Auto-Approve Threshold |
| ------- | ------ | --------------------- | ------------------------ |
| 1 | Probation | 0-50 | $0 (review all) |
| 2 | Standard | 50-100 | $500 |
| 3 | Core | 100+ | $5,000 |


## # Behavior
- **Accurate decision**: Consecutive accurate count +1, trust level may promote
- **Error made**: Consecutive errors +1, consecutive accurate resets to 0
- **5 consecutive errors**: Trust level demotes by 1
- **Accuracy rate**: Calculated from all-time decisions

## # Trust Battery Table Schema
```sql
CREATE TABLE trust_battery (
    id UUID PRIMARY KEY,
    vendor_id UUID NOT NULL,
    consecutive_accurate INTEGER DEFAULT 0,
    consecutive_errors INTEGER DEFAULT 0,
    total_decisions INTEGER DEFAULT 0,
    accurate_decisions INTEGER DEFAULT 0,
    trust_level INTEGER DEFAULT 3,  -- 1=Probation, 2=Standard, 3=Core
    auto_approve_threshold DECIMAL(10,2) DEFAULT 500,
    last_decision_at TIMESTAMP,
    updated_at TIMESTAMP
);
```text
## # Calibration Report
Tracks agent performance for shadow mode:
- Total decisions vs verified decisions
- Recent accuracy (last 50 decisions)
- Recommendations for threshold adjustment

---

# # 7C. FinancialContext Object (Implemented)

Provides the agent with real-time company financial state.

```typescript
interface FinancialContext {
  currentCash: number;              // Current bank balance
  monthlyBurnRate: number;          // Avg monthly spending
  runwayDays: number;               // Days of runway remaining

|  |

  payrollAmount: number;            // Upcoming payroll amount
  safetyBuffer: number;             // Minimum cash to maintain

| "GROWTH" |

  autoApproveThreshold: number;     // Global auto-approve limit
  budgets: BudgetCategory[];        // Category spending limits

| 2 |

  consecutiveAccuracy: number;      // Consecutive accurate decisions
  pendingPaymentsThisMonth: number; // Scheduled payments
  categorySpending: Record<string, number>;  // YTD spending by category
}

interface BudgetCategory {
  category: string;           // e.g., "Software", "G&A"
  monthlyLimit: number;       // Max spend per month
  softCapAlert: boolean;      // Alert at 80% of limit
}
```text
## # Strategy Modes

| Mode | Behavior |
| ------ | ---------- |
| **SURVIVAL** | Conserve cash, delay non-essential payments |
| **GROWTH** | Pay fast, build vendor trust and early payment discounts |
| **OPTIMIZE** | Balance between cash conservation and vendor relationships |


---

# # 7D. Decision Signals (Implemented)

Every decision produces explainable signals for audit and transparency.

```typescript
interface DecisionSignal {

| "STRATEGY" | "CONTRACT" | "TRUST" | "BUDGET" | "DUPLICATE" |
| "WARNING" |

  message: string;           // Human-readable explanation
  recommendation: string;    // Suggested action
  scoreContribution?: number; // Risk score contribution (0-1)
}

interface ReasoningStep {
  node: string;              // Which node produced this
  decision: string;          // The decision made
  reasoning: string[];       // Step-by-step reasoning
  signals: DecisionSignal[]; // Supporting signals
}
```text
## # Example Output
```json
{
  "decision": "HITL_REQUIRED",
  "reasoning": [
    "Invoice amount $3,200 is within trust threshold",
    "Vendor trust level: CORE (consecutive accurate: 127)",
    "RUNWAY WARNING: Payment reduces runway to 4.2 months",
    "Payroll of $15,000 due in 3 days"
  ],
  "signals": [
    {
      "type": "RUNWAY",
      "severity": "WARNING",
      "message": "Payment would reduce runway below 5 months",
      "recommendation": "Delay until after payroll"
    }
  ]
}
```text
---

# # 7E. Updated Process Map (Implemented)

```text
[Invoice Arrival]
        ↓
[INGEST] - Store raw, create invoice record
        ↓
[EXTRACT] - OCR + field extraction, confidence scoring
        ↓
[CONTEXT] - Load FinancialContext, vendor history, budget status
        ↓
[RISK] - Calculate risk score (formula below)
        ↓
[ANALYST] - Propose action based on patterns
   │     - Check for duplicates/anomalies
   │     - Consider vendor payment preferences
   ↓
[CRITIC] - Priority Matrix Review
   │     1. RUNWAY: Safe to pay now?
   │     2. STRATEGY: Aligns with mode?
   │     3. CONTRACT: Terms violated?
   │     4. TRUST: Within auto-approve threshold?
   │     5. BUDGET: Within category limits?
   ↓
[ROUTE]
   ├─ AUTO_APPROVE → [POST_LEDGER] → [SCHEDULE_PAYMENT]
   ├─ HITL_REQUIRED → [HUMAN_REVIEW]
   │     ├─ Approved → [POST_LEDGER] → [SCHEDULE_PAYMENT]
   │     ├─ Rejected → [REJECT]
   │     └─ Delayed → [RESCHEDULE]
   └─ REJECT → [REJECT]
        ↓
[LEARN] - Record decision, update trust battery
        ↓
[RECONCILE] - Monitor bank feed, match transactions, mark as reconciled
        ↓
[END]
```text
## # The Complete Invoice Lifecycle

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         INVOICIFY AGENT LIFECYCLE                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [INVOICE]                                                                │
│      ↓                                                                   │
│  [INGEST] ────── Store raw, create record                                │
│      ↓                                                                   │
│  [EXTRACT] ───── OCR, field extraction, confidence score                 │
│      ↓                                                                   │
│  [CONTEXT] ──── Load FinancialContext, vendor history                    │
│      ↓                                                                   │
│  [RISK] ──────── Calculate risk score (formula)                          │
│      ↓                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    THE AUTONOMOUS BRAIN                            │  │
│  │                                                                    │  │
│  │   [ANALYST] ──── Propose action based on patterns                  │  │
│  │        ↓                                                          │  │
│  │   [CRITIC] ───── Safety checks (Priority Matrix)                   │  │
│  │        │         1. RUNWAY → 2. STRATEGY → 3. CONTRACT            │  │
│  │        │         4. TRUST → 5. BUDGET                              │  │
│  │        ↓                                                          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│      ↓                                                                   │
│  [ROUTE]                                                                  │
│      ├─ LOW RISK ──→ [AUTO_APPROVE]                                      │
│      ├─ MEDIUM ───→ [HITL_REVIEW]                                        │
│      └─ HIGH ─────→ [ESCALATE]                                           │
│      ↓                                                                   │
│  [POST_LEDGER] ─── Record in ERP                                         │
│      ↓                                                                   │
│  [SCHEDULE_PAYMENT] ── Set payment date                                  │
│      ↓                                                                   │
│  [RECONCILE] ────── Monitor bank → Match transaction → Mark complete    │
│      ↓                                                                   │
│  [LEARN] ────────── Update trust battery, calibration                    │
│      ↓                                                                   │
│  [END]                                                                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```text
## # Risk Scoring Formula (Implemented)
```typescript
const RISK_WEIGHTS = {
  amount: 0.30,
  duplicate: 0.25,
  trust: 0.20,
  runway: 0.15,
  newVendor: 0.10,
};

function calculateRiskScore(inputs: RiskInputs): {
  score: number;        // 0-1
  signals: DecisionSignal[];
} {
  const score =
    RISK_WEIGHTS.amount * inputs.amountDeviation +
    RISK_WEIGHTS.duplicate * inputs.duplicateScore +
    RISK_WEIGHTS.trust * (1 - inputs.vendorTrust) +
    RISK_WEIGHTS.runway * inputs.runwayPressure +
    RISK_WEIGHTS.newVendor * (inputs.isNewVendor ? 1 : 0);

  return { score, signals: inputs.signals };
}
```text
## # HITL Thresholds (Configurable)

| Risk Score | Action |
| ------------ | -------- |
| < 0.3 | Auto-approve (if trust level allows) |
| 0.3 - 0.6 | HITL review |
| > 0.6 | Escalate / Block |


---

# # 7F. Updated KPIs (Implemented)

## # Operational

| Metric | Target | Description |
| -------- | -------- | ------------- |
| Auto-approval rate | >60% | % invoices auto-approved |
| HITL rate | <40% | Requires human review |
| Processing time | <30s | End-to-end invoice processing |
| Accuracy rate | >95% | Agent decisions matching human |


## # Trust Battery Metrics

| Metric | Target | Description |
| -------- | -------- | ------------- |
| Core vendors | >50% | Vendors at trust level 3 |
| Promotion rate | >10%/month | Vendors moving up levels |
| Demotion rate | <5%/month | Vendors moving down levels |
| False positive rate | <10% | Unnecessary escalations |


## # Business Impact

| Metric | Target | Description |
| -------- | -------- | ------------- |
| Late fees avoided | 100% | Zero late payments |
| Duplicate prevention | 100% | Zero duplicate payments |
| Runway alerts | >80% accuracy | True positive rate |


## # Learning Loop

| Metric | Target | Description |
| -------- | -------- | ------------- |
| Feedback loop time | <24h | Human decision → trust update |
| Threshold calibration | Monthly | Auto-adjust based on accuracy |
| Pattern detection | >5 patterns/month | Identified vendor behaviors |


---

# # 8. The Context Layer (The "Founder's Memory")

This is what makes Invoicify intelligent, not just automated. It gives the agent a "temporal memory" of company context so the founder doesn't have to context-switch to explain "why this is OK (or not) this time."

## # 8A. Temporal Knowledge Graph (Neo4j + Graphiti)

Graphiti is the "Hippocampus" of the agent. It stores "Episodes" of business interactions, allowing the agent to reason about changes over time.

**Graph Model:**

```typescript
// Nodes
Vendor { id, name, category }
Invoice { id, number, amount, status }
Contract { id, terms, active_period }
Policy { id, name, rules, valid_from, valid_to }
Person { id, role, approver_level }

// Edges (Time-Aware via Graphiti)
(:Vendor)-[:TRUST_STATUS {level: 'PROBATION', valid_from: '2025-01-01', valid_to: '2025-02-01'}]->(:Company)
(:Vendor)-[:TRUST_STATUS {level: 'TRUSTED', valid_from: '2025-02-02'}]->(:Company)
(:Vendor)-[:VIOLATED_TERM {severity: 'HIGH', episode_id: 'xxx'}]->(:Contract)
(:Invoice)-[:BELONGS_TO_EPISODE {reason: 'Series A Demo'}]->(:Episode)
```text
**Episodic Memory Examples:**

* "Jan 1st: Founder put vendor 'Acme' on probation due to bad service"
* "Jan 12th: Founder overrode probation to pay Acme"
* "Last month you rejected this vendor due to quality - has this been resolved?"

**Query Examples:**

```python
# "What happened with this vendor last month?"
results = graphiti.search(
    "AWS overage approval history",
    filter_by_time="last_6_months"
)
# Returns: "On Jan 12, Founder approved AWS overage due to 'Staging Demo'."
```text
## # 8B. Semantic Memory (Postgres + pgvector)

Stores embeddings of invoices, contracts, and approval rationales for similarity search.

**Tables:**

```sql
-- Invoices with embeddings
CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    vendor_id UUID,
    status TEXT,
    embedding vector(1536),  -- OpenAI text-embedding-3-small
    risk_score FLOAT,
    extracted_text TEXT,
    created_at TIMESTAMP
);

-- Episodes (Graphiti sync)
CREATE TABLE episodes (
    id UUID PRIMARY KEY,
    content TEXT,
    embedding vector(1536),
    timestamp TIMESTAMP,
    vendor_id UUID,
    invoice_id UUID
);
```text
**Used for:**

* "Is this similar to previous invoices?"
* "Have we seen this pattern before?"
* Contract similarity search

## # 8C. Source of Truth (Postgres)

```sql
CREATE TABLE vendors (
    id UUID PRIMARY KEY,
    name TEXT UNIQUE,
    category TEXT,
    trust_level INTEGER DEFAULT 1,  -- 1=Probation, 2=Standard, 3=Core
    auto_approve_threshold DECIMAL(10,2) DEFAULT 0,
    consecutive_accurate INTEGER DEFAULT 0,
    consecutive_errors INTEGER DEFAULT 0
);

CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    vendor_id UUID,
    invoice_number TEXT,
    amount DECIMAL(10,2),
    status TEXT,  -- 'RECEIVED', 'HITL', 'APPROVED', 'PAID', 'RECONCILED'
    risk_score FLOAT,
    analyst_proposal TEXT,
    critic_decision TEXT,
    stripe_payout_id TEXT,
    qbo_bill_id TEXT,
    policy_version_at_decision TEXT
);

CREATE TABLE payments (
    id UUID PRIMARY KEY,
    invoice_id UUID,
    amount DECIMAL(10,2),
    scheduled_date DATE,
    stripe_payout_id TEXT,
    status TEXT  -- 'SCHEDULED', 'CLEARED', 'RECONCILED'
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    episode_id UUID,
    action TEXT,
    rationale TEXT,
    actor TEXT,  -- 'AGENT' or 'HUMAN'
    timestamp TIMESTAMP
);
```text
## # 8D. Redis (Agent State)

* Agent state cache for workflow checkpoints
* HITL queues with TTL
* Idempotency keys (prevent double payments)
* Rate limiting per vendor

---

# # 9. SOPs (Standard Operating Procedures)

## # SOP-FIN-001: Invoice Lifecycle

```text
Invoice Received
→ Parsed
→ Context Loaded
→ Risk Scored
→ Action Taken
→ Logged
→ Learned
```text
---

## # SOP-FIN-002: Risk Scoring

Inputs:

* Vendor trust score
* Amount deviation
* Timing vs runway
* Duplicate likelihood

Outputs:

* Risk score (0–1)
* Confidence score
* Explanation

---

## # SOP-FIN-003: Human-in-the-Loop

Trigger Conditions:

* Risk score > threshold
* New vendor
* Amount spike
* Low runway

Actions:

* Pause workflow
* Notify approver
* Capture decision
* Feed back to learning loop

---

## # SOP-FIN-004: Cash Reconciliation (Mandatory)

**Trigger:** Bank Feed update (Mercury API / Plaid / Teller)

**Steps:**

1. **Search** - Identify all "Cleared" transactions in the last 24 hours
2. **Match** - Fuzzy matching on `Amount`, `Vendor Name`, and `Date` against `payments` table
   ```typescript
   function matchTransaction(bankTx, scheduledPayments) {
     return scheduledPayments.find(p =>
       Math.abs(p.amount - bankTx.amount) < 0.01 &&
       similarStrings(p.vendorName, bankTx.description) > 0.8 &&
       Math.abs(dateDiff(p.scheduledDate, bankTx.date)) < 3
     );
   }
   ```
3. **Validate** - Confirm transaction ID matches bank's record
4. **Action** - API call to ERP (Xero/QBO) to mark bill as "Reconciled"
5. **Alert** - If no match found for significant outflow → **Alert Founder Immediately**

**Reconciliation States:**

| State | Meaning |
| ------- | --------- |
| `SCHEDULED` | Payment created, waiting for bank clear |
| `CLEARED` | Transaction matched in bank feed |
| `RECONCILED` | Marked complete in ERP |
| `ORPHANED` | Bank transaction with no matching invoice |


---

# # 10. The "Context-Switching" Workflow (Process Map)

When an invoice arrives, the agent builds a "Context Frame" before deciding.

```text
[INVOICE ARRIVAL]
        ↓
[INGEST → EXTRACT → DEDUPE]
        ↓
[TIME TRAVEL STEP - Graphiti Recall]
   Query: "What happened with this vendor last month?"
   Returns: Recent episodes, past disputes, approval patterns
        ↓
[CONTEXT LOAD]
   ├── pgvector: Similar invoices + contract terms
   └── Neo4j: Vendor relationship over time
        ↓
[THE AUTONOMOUS BRAIN]
   [ANALYST] → Propose action (pattern detection)
        ↓
   [CRITIC] → Safety checks (Priority Matrix)
        ↓
[GATE]
   ├── Risk ≤ Threshold → Auto-Execute
   └── Risk > Threshold → HITL Review
        ↓
[EXECUTE]
   ├── Stripe Test Mode: Create payout
   └── QuickBooks: Post Bill + BillPayment
        ↓
[RECONCILE]
   Webhook → Match payout to invoice → Update status
        ↓
[WRITE-BACK]
   Graphiti: Add new episode ("Founder approved due to X reason")
   Trust Battery: Update vendor trust
```text
## # The "Money Shot" Demo Flow

1. **Context Setup:** Manually add episode to Graphiti: "Jan 1st: Founder put vendor 'Acme' on probation due to bad service."

2. **Trigger:** Send an invoice from 'Acme'.

3. **Agent Action:** Agent pauses (HITL).

4. **Reason:** "Vendor is on probation (Episode Jan 1st)."

5. **Resolution:** Founder approves with override.

6. **Execution:** System shows Stripe Payout succeeded & QBO Bill created.

7. **Update:** Agent writes new episode: "Jan 12th: Founder overrode probation to pay Acme."

## # Process States

| State | Description |
| ------- | ------------- |
| `NEW` | Invoice received, not yet processed |
| `EXTRACTED` | Fields extracted with confidence score |
| `CONTEXT_LOADED` | Graphiti/Neo4j context retrieved |
| `VALIDATED` | Risk assessed, ready for decision |
| `APPROVED` | Auto-approved or human-approved |
| `PENDING` | Scheduled, waiting for payment execution |
| `PAID` | Payment executed, awaiting reconciliation |
| `RECONCILED` | Bank transaction matched, complete |
| `REJECTED` | Rejected with reason |


---

# # 11. User Stories (Real Founder Language)

> “I want invoices handled automatically so I only see problems, not paperwork.”

> “I want to know if paying something now will hurt my runway.”

> “I want confidence nothing slips through or gets paid twice.”

---

# # 12. KPIs (What Actually Matters)

## # Operational

* % invoices auto-processed
* HITL rate over time
* Processing time per invoice

## # Business

* Late fees avoided
* Duplicate payments prevented
* Runway risk alerts accuracy

## # Trust

* False positive rate
* False negative rate
* Manual overrides

---

# # 13. Dev Plan (Step-by-Step)

## # Phase 1 – Foundation (2 weeks)

* Postgres + pgvector
* Redis
* LangGraph skeleton
* Email ingestion

## # Phase 2 – Core Agent (3 weeks)

* Invoice extraction
* Context fetch
* Risk scoring
* HITL flow

## # Phase 3 – Execution (2 weeks)

* Payment scheduling
* Ledger posting
* Notifications

## # Phase 4 – Learning Loop (2 weeks)

* Feedback ingestion
* Threshold tuning
* Vendor scoring

## # Phase 5 – UX & Polish (2 weeks)

* Approval UI
* Audit timeline
* Confidence explanations

---

# # 14. Deliverables Checklist

## # Must-Have

* [ ] Autonomous invoice handling
* [ ] Context-aware decisions
* [ ] HITL controls
* [ ] Audit trail
* [ ] Learning loop

## # Nice-to-Have

* [ ] Vendor insights
* [ ] Cash optimization suggestions
* [ ] Payment timing intelligence

---

# # 15. What Makes Invoicify Defensible

1. **Context graph** (hard to copy)
2. **Decision history** (moat over time)
3. **Trust calibration**
4. **Founder-centric UX**
5. **Role-based framing**

---

## # The "Trust Battery" (Calibration)

**Shadow Mode Deployment (First 14 Days)**

For the initial 14 days, Invoicify runs in **Shadow Mode**:
- Agent makes decisions but **does not execute**
- Records what it "would have done"
- Tracks human decisions for comparison

**Calibration Report Generation (Day 15)**

```typescript
interface CalibrationReport {
  totalInvoices: number;
  shadowDecisions: number;
  truePositives: number;      // Caught duplicates/frauds
  timeSaved: number;          // Hours of manual work avoided
  accuracyRate: number;       // % matching human decisions
  recommendations: string[];  // Threshold tuning suggestions
}
```text
**Example Report:**
> *"I would have caught 3 duplicates and saved 4.2 hours. My accuracy was 99.4%. Recommend promoting 2 vendors to Core trust level."*

**Why This Wins Trust:**
1. **No risk** - Cannot make mistakes during learning period
2. **Measurable** - Founder sees concrete value immediately
3. **Transparent** - Full audit of agent reasoning available
4. **Earned Autonomy** - Trust battery naturally increases with proven accuracy

---

# # 16. How This Fits the Bigger Vision

* Invoicify → **Finance Intern**
* Finance Intern → **Entry Point to Founder OS**
* Founder OS → **Virtual Office**

Nothing here is wasted.

---

# # 17. Final Reality Check

If Invoicify does not:

* Reduce founder anxiety
* Reduce manual work
* Surface problems early

Then it has failed.

---
Below is the **complete, execution-ready technical package for Invoicify**.
This is not conceptual. This is **what you build**.

I will give you, in order:

1. **Exact DB schemas (Postgres + pgvector + Neo4j)**
2. **LangGraph code skeleton (production-style)**
3. **Risk scoring formula (deterministic + learnable)**
4. **UI wireframe (textual + component spec, founder-grade)**

No gaps. No hand-waving.

---

# 1. EXACT DATABASE SCHEMAS

# # 1.1 Postgres (Source of Truth)

## # invoices

```sql
CREATE TABLE invoices (
    id UUID PRIMARY KEY,
    vendor_id UUID NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date DATE,
    due_date DATE,
    currency TEXT DEFAULT 'USD',
    amount NUMERIC(12,2) NOT NULL,
    status TEXT CHECK (status IN (
        'received','parsed','approved','scheduled','paid','rejected'
    )),
    risk_score NUMERIC(4,3),
    confidence_score NUMERIC(4,3),
    embedding VECTOR(1536),
    raw_document_url TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```text
---

## # vendors

```sql
CREATE TABLE vendors (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    trust_score NUMERIC(4,3) DEFAULT 0.5,
    avg_invoice_amount NUMERIC(12,2),
    payment_terms_days INT,
    anomaly_rate NUMERIC(4,3),
    created_at TIMESTAMP DEFAULT now()
);
```text
---

## # approvals

```sql
CREATE TABLE approvals (
    id UUID PRIMARY KEY,
    invoice_id UUID REFERENCES invoices(id),
    approved_by TEXT,
    decision TEXT CHECK (decision IN ('approved','rejected','delayed')),
    reason TEXT,
    confidence_override BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT now()
);
```text
---

## # payments

```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY,
    invoice_id UUID REFERENCES invoices(id),
    scheduled_date DATE,
    executed_date DATE,
    status TEXT CHECK (status IN ('scheduled','executed','failed')),
    payment_method TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```text
---

## # agent_runs (critical for auditability)

```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY,
    invoice_id UUID,
    node TEXT,
    input JSONB,
    output JSONB,
    decision TEXT,
    confidence NUMERIC(4,3),
    created_at TIMESTAMP DEFAULT now()
);
```text
---

# # 1.2 pgvector (Semantic Memory)

Stored inline as `embedding VECTOR(1536)` in:

* invoices
* vendors
* approvals.reason (optional)

Use for:

* similarity detection
* anomaly detection
* historical reasoning

---

# # 1.3 Neo4j (Context Graph)

## # Nodes

```text
(:Vendor {id, name, trust_score})
(:Invoice {id, amount, risk_score})
(:Approval {id, decision})
(:Payment {id, status})
```text
## # Relationships

```text
(Vendor)-[:ISSUED]->(Invoice)
(Invoice)-[:REQUIRES]->(Approval)
(Invoice)-[:PAID_BY]->(Payment)
```text
This is **not optional**.
Graphs are how you reason over financial behavior over time.

---

# 2. LANGGRAPH CODE SKELETON (REALISTIC)

Python, production-style.

## # 2.1 Agent State (LangGraph SQL State)

```python
from pydantic import BaseModel
from typing import Optional

class InvoiceState(BaseModel):
    invoice_id: str
    vendor_id: str
    amount: float
    risk_score: Optional[float]
    confidence: Optional[float]
    action: Optional[str]
```text
---

## # 2.2 Core Graph

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(InvoiceState)
```text
---

## # 2.3 Nodes

### # Extract

```python
def extract_invoice(state: InvoiceState):
    # OCR + parser already done upstream
    return state
```text
---

### # Context Fetch

```python
def fetch_context(state: InvoiceState):
    vendor = get_vendor(state.vendor_id)
    runway = get_company_runway()
    history = fetch_similar_invoices(state.amount)
    return {
        **state.dict(),
        "vendor_trust": vendor.trust_score,
        "runway_days": runway,
        "history_similarity": history.similarity
    }
```text
---

### # Risk Assessment (Core Brain)

```python
def assess_risk(state):
    risk, confidence = calculate_risk(state)
    return {
        **state,
        "risk_score": risk,
        "confidence": confidence
    }
```text
---

### # Decision Router

```python
def route_action(state):
    if state["risk_score"] < 0.3 and state["confidence"] > 0.8:
        return "auto_approve"
    elif state["risk_score"] < 0.6:
        return "hitl"
    else:
        return "escalate"
```text
---

### # HITL Node

```python
def human_review(state):
    pause_for_approval(state.invoice_id)
    return state
```text
---

## # 2.4 Graph Assembly

```python
graph.add_node("extract", extract_invoice)
graph.add_node("context", fetch_context)
graph.add_node("risk", assess_risk)
graph.add_node("hitl", human_review)

graph.add_edge("extract", "context")
graph.add_edge("context", "risk")
graph.add_conditional_edges(
    "risk",
    route_action,
    {
        "auto_approve": END,
        "hitl": "hitl",
        "escalate": "hitl"
    }
)

app = graph.compile()
```text
---

# 3. RISK SCORING FORMULA (REAL, NOT ML-BS)

This is **hybrid deterministic + learnable**.

## # 3.1 Inputs

| Signal | Range |
| -------------------- | ----- |
| Vendor trust | 0–1 |
| Amount deviation | 0–1 |
| Duplicate similarity | 0–1 |
| Runway pressure | 0–1 |
| New vendor | 0/1 |


---

## # 3.2 Formula

```text
risk_score =
  (0.30 * amount_deviation)
+ (0.25 * duplicate_similarity)
+ (0.20 * (1 - vendor_trust))
+ (0.15 * runway_pressure)
+ (0.10 * is_new_vendor)
```text
## # Confidence

```text
confidence = 1 - variance(history_similarity)
```text
## # Why this matters:

* Deterministic
* Auditable
* ML can tune weights later
* Founders can trust it

---

# 4. UI WIREFRAME (FOUNDER-GRADE)

No fluff. One screen philosophy.

---

# # 4.1 Main Dashboard

```text
┌─────────────────────────────────────────────┐
│ Invoicify – Finance Intern                  │
│ Runway: 7.3 months 🟢                       │
├─────────────────────────────────────────────┤
│ Incoming Invoices                           │
│ ┌────────────┬─────────┬──────┬─────────┐ │
│ │ Vendor     │ Amount  │ Risk │ Action  │ │
│ ├────────────┼─────────┼──────┼─────────┤ │
│ │ AWS        │ $3,200  │ LOW  │ Auto ✓  │ │
│ │ NewVendorX │ $12,500 │ HIGH │ Review  │ │
│ └────────────┴─────────┴──────┴─────────┘ │
└─────────────────────────────────────────────┘
```text
---

# # 4.2 Invoice Detail (HITL Screen)

```text
Invoice: #INV-23901
Vendor: NewVendorX
Amount: $12,500
Due: 14 days

Why flagged:
• Amount 3× higher than normal
• Vendor has no payment history
• Runway impact: -0.8 months

[ Approve ]  [ Delay ]  [ Reject ]
```text
---

# # 4.3 Audit Timeline

```text
• Invoice received (09:41)
• Parsed successfully
• Risk score: 0.71 (High)
• Escalated to human
• Approved by Founder (09:55)
• Payment scheduled
```text
This **builds trust**.

---

# 5. FINAL DEV CHECKLIST (PIN THIS)

## # Must Ship

* [ ] Autonomous processing
* [ ] Risk-based routing
* [ ] HITL UI
* [ ] Audit trail
* [ ] Learning loop

## # Must NOT Ship

* ❌ Manual-first workflows
* ❌ Feature bloat
* ❌ Generic dashboards
* ❌ Black-box decisions

---

# 6. REALITY STATEMENT (Important)

If Invoicify cannot:

* Act without prompts
* Explain its decisions
* Reduce founder attention

Then it is **not an agent**.
It is just software.

---

## # The Final Reality Check

If Invoicify does not **automatically reconcile the bank account** and **strategically delay payments during a cash crunch**, it is just an expensive OCR tool.

With these consolidated upgrades, it is a **Finance Ops Intern**.

---

# # Revised Technical Implementation Guide

| Module | Technical Choice | Reason |
| :--- | :--- | :--- |
| **Orchestration** | **LangGraph** | Required for the Analyst-Critic loop and state persistence |
| **Memory** | **pgvector (Postgres)** | Stores historical invoice "fingerprints" and contract clauses for semantic matching |
| **Banking** | **Mercury API / Plaid** | Native Mercury integration is the "gold standard" for this ICP |
| **Safety** | **Idempotency Keys** | Every payment request must have a hash-based key to prevent double-payments |
| **Agent Runtime** | **Cloudflare Workers** | Serverless edge deployment for low latency, high availability |
| **Database** | **D1 (SQLite)** | Lightweight, production-ready for edge functions |
| **OCR** | **Vision API / Tesseract** | Document extraction with confidence scoring |
| **Learning** | **Trust Battery** | Gradual autonomy based on demonstrated accuracy |


---

# # What I recommend next (order matters):

1. **Implement DB schemas**
2. **Wire LangGraph skeleton**
3. **Hardcode risk formula**
4. **Build HITL UI**
5. **Only then optimize**

---

# APPENDIX A: IMPLEMENTATION-SPECIFIC ADDENDUM

> This section addresses gaps identified during live build for production deployment.

---

# # 1. Day 0 Bootstrap Module

The PRD assumes the agent "learns over time" via Trust Battery and Calibration Reports, but does not specify **how to seed initial intelligence** so the agent isn't "dumb" on Day 1.

## # Bootstrap Requirements

On first install, the system **MUST** ingest historical data to achieve functional baseline:

| Data Source | Target Table | Minimum Seeding |
| ------------- | -------------- | ----------------- |
| **Last 6 months bills/payments** | `vendors` | 50+ vendor records |
| **Historical payment patterns** | `episodes` (Graphiti) | 100+ decision records |
| **Past invoice embeddings** | `pgvector` | 200+ invoice vectors |


## # Bootstrap Methods (Priority Order)

1. **QuickBooks Online API Import**
   ```typescript
   // Fetch last 6 months of bills
   await qbClient.queryBills({
     txnDate: { $gte: "2024-07-01" },
     MAXRESULTS: 500
   });
   ```

2. **CSV Upload Fallback**
   ```typescript
   interface BootstrapCSV {
     vendorName: string;
     invoiceNumber: string;
     amount: number;
     dueDate: string;
     paidDate?: string;

| "pending" |

   }
   ```

3. **Manual Entry** (for Phase 1 MVP)
   - Allow founders to manually add top 5 vendors
   - Trust Battery starts at Level 2 (Standard) for manually-verified vendors

## # Bootstrap Validation

After seeding, run `POST /api/v1/bootstrap/verify`:
- Returns: `{ vendorsSeeded: number, episodesSeeded: number, embeddingsSeeded: number }`
- Fails deployment if thresholds not met

---

# # 2. Execution Layer Specification

**Current PRD Ambiguity:** The "Banking" row lists "Mercury API / Plaid" but this portfolio build uses **Stripe + QuickBooks Online**.

## # Corrected Tech Stack Table

| Module | Technical Choice | Reason |
| :--- | :--- | :--- |
| **Orchestration** | **LangGraph** | Required for Analyst-Critic loop and state persistence |
| **Memory** | **pgvector** (via Neon/Supabase) | Stores invoice "fingerprints" for semantic matching |
| **Banking / Payments** | **Stripe Connect (Test Mode)** | Simulates payment processing for portfolio build |
| **Ledger / Accounting** | **QuickBooks Online API** | Authoritative source for vendor data, bills, payments |
| **Safety** | **Idempotency Keys** | Every payment request uses hash-based keys |
| **Agent Runtime** | **Cloudflare Workers** | Serverless edge for low latency |
| **Database** | **D1 (SQLite)** + **Neon (Postgres/pgvector)** | Hybrid: transactional + vector search |
| **OCR** | **Cloudflare Workers AI (Llama 3.2 Vision)** | On-device document extraction |
| **Learning** | **Trust Battery** | Gradual autonomy based on accuracy |
| **Knowledge Graph** | **Graphiti** (self-hosted or cloud) | Episodic memory for vendor relationships |


## # Stripe Configuration

```typescript
// worker/wrangler.toml
[vars.STRIPE_TEST_KEY]
source = "env"

[vars.STRIPE_WEBHOOK_SECRET]
source = "secret"  # wrangler secret put STRIPE_WEBHOOK_SECRET
```text
## # QuickBooks Configuration

```typescript
// worker/wrangler.toml
[vars.QUICKBOOKS_CLIENT_ID]
source = "env"

[vars.QUICKBOOKS_CLIENT_SECRET]
source = "secret"  # wrangler secret put QUICKBOOKS_CLIENT_SECRET

[vars.QUICKBOOKS_REFRESH_TOKEN]
source = "secret"

[vars.QUICKBOOKS_REALM_ID]
source = "env"
```text
---

# # 3. Continuous Ingestion Pipeline

The PRD mentions "Email Ingestion" and "Bank Feed" as separate triggers, but requires a **unified write-back loop** to keep the Knowledge Graph synchronized.

## # Pipeline Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTINUOUS INGESTION PIPELINE                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐     │
│  │   INVOICE   │───▶│   EXTRACT   │───▶│   RISK ASSESSMENT   │     │
│  │   ARRIVES   │    │   (Vision)  │    │                     │     │
│  └─────────────┘    └─────────────┘    └──────────┬──────────┘     │
│                                                    │                 │
│                         ┌──────────────────────────┘                 │
│                         │                                           │
│                         ▼                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    WRITE-BACK LOOP                          │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                             │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ WRITE 1: pgvector Embeddings                        │   │   │
│  │  │ Every invoice → extracted_text embedding            │   │   │
│  │  │ Purpose: Semantic search, duplicate detection       │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ WRITE 2: Graphiti Episodes                          │   │   │
│  │  │ Every human decision → new episode record           │   │   │
│  │  │ Purpose: Learn from approvals/rejections            │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ WRITE 3: Vendor Trust Stats                         │   │   │
│  │  │ Every reconciled payment → update trust battery     │   │   │
│  │  │ Purpose: Auto-approve thresholds update             │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```text
## # Implementation Details

### # Write 1: pgvector Embeddings

```typescript
// worker/src/routes/extract.ts
await extractRoutes.post("/complete", async (c) => {
  const { invoiceId, extractedText } = await c.req.json();

  // Generate embedding
  const embedding = await env.AI.run("@cf/baai/bge-en-15", {
    text: extractedText,
  });

  // Store in pgvector (via Neon/Supabase)
  await db.insert(schema.invoiceEmbeddings).values({
    invoiceId,
    embedding,
    createdAt: new Date().toISOString(),
  });
});
```text
### # Write 2: Graphiti Episodes

```typescript
// worker/src/lib/audit-tracer.ts
export async function logDecision(
  env: Env,
  invoiceId: string,

| "rejected" |

  reasoning: string
) {
  // Write episode to Graphiti
  await graphitiClient.createEpisode({
    type: "HUMAN_DECISION",
    entities: [invoiceId],
    observations: [
      {
        type: "decision",
        value: decision,
        source: "human_reviewer",
        reasoning,
      },
    ],
  });
}
```text
### # Write 3: Trust Battery Update

```typescript
// worker/src/lib/trust-battery.ts
export async function recordDecision(
  env: Env,
  vendorId: string,

|  |

) {
  const db = getDb(env);

  // Update trust battery
  await db.insert(schema.trustHistory).values({
    vendorId,
    decision: outcome,
    timestamp: new Date().toISOString(),
  });

  // Recalculate level
  await recalculateVendorTrust(db, vendorId);
}
```text
## # Pipeline Performance Requirements

| Metric | Target | How Achieved |
| -------- | -------- | -------------- |
| **Embedding Latency** | < 500ms | Cloudflare Workers AI |
| **Episode Write Latency** | < 200ms | Graphiti async write |
| **Trust Update Latency** | < 100ms | D1 transaction |
| **End-to-End Pipeline** | < 2s | Parallel writes |


---

# # 4. API Contract Summary

## # Core Endpoints (v1)

| Method | Path | Description |
| -------- | ------ | ------------- |
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/invoices` | Create invoice |
| `GET` | `/api/v1/invoices` | List with pagination |
| `GET` | `/api/v1/invoices/:id` | Get details |
| `GET` | `/api/v1/invoices/search?q=` | Search |
| `POST` | `/api/v1/invoices/:id/approve` | HITL approve |
| `POST` | `/api/v1/workflow/start` | Start processing |
| `GET` | `/api/v1/risk/:invoiceId` | Get risk score |
| `POST` | `/api/v1/quickbooks/auth` | OAuth URL |


## # Response Standards

```typescript
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
  pagination?: {
    page: number;
    limit: number;
    total: number;
  };
}
```text
---

# # 5. Security Boundaries

| Boundary | Implementation |
| ---------- | ---------------- |
| **Auth** | API key validation (Phase 2) |
| **Rate Limiting** | Cloudflare WAF rules |
| **Input Validation** | Zod schemas on all POST/PUT |
| **SQL Injection** | Drizzle ORM parameterization |
| **XSS** | secureHeaders() middleware |
| **CORS** | Explicit origin allowlist |


---

# # 6. Deployment Checklist

- [ ] D1 database created and migrated
- [ ] R2 bucket provisioned
- [ ] Environment secrets set via `wrangler secret put`
- [ ] Frontend built (`pnpm build`)
- [ ] Assets served from Worker (`ASSETS` binding)
- [ ] Rate limiting rules configured in Cloudflare WAF
- [ ] QuickBooks OAuth flow tested
- [ ] Bootstrap data seeded (50+ vendors, 100+ episodes)

---

*End of Addendum*
