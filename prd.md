# INVOICIFY: Production Architecture & Implementation Specification (v2.0)

## 📖 EXECUTIVE SUMMARY
**Invoicify** is an autonomous Accounts Payable (AP) agent designed to replace manual financial operations. It handles the complete lifecycle of an invoice with a "Human-on-the-loop" philosophy, prioritizing explainability, security, and extreme performance.

## 🎯 CORE VALUE PROPOSITION
- **Prevent Cash Bleed**: Real-time math validation and anomaly detection.
- **Save Founder Time**: Trusted vendors move straight to QuickBooks.
- **Full Traceability**: Every decision (Auto-Approve, HITL, Reject) includes an explainable audit trail.

---

## 🏗️ SYSTEM ARCHITECTURE (Hybrid Split)

### 1. Ingestion Layer (Edge-Native)
- **Runtime**: Cloudflare Workers (Hono)
- **Persistence**: D1 SQLite (metadata) / R2 (PDF objects)
- **Responsibility**: Fast ingestion, security, and callback management.

### 2. Decision Layer (Agent Core)
- **Runtime**: Python 3.12 (FastAPI)
- **Extactor**: IBM Docling (Markdown-mode)
- **Intelligence**: Groq Llama-3 (70B) for structured extraction.
- **Risk Engine**: Hybrid Math Validation + Trust Battery scoring.
- **Persistence**: Redis (hot-cache for trust state).

---

## ⚡ PERFORMANCE SPECIFICATIONS (SLOs)

| Operation | Target Latency | Optimization Method |
| :--- | :--- | :--- |
| **Ingestion** | < 200 ms | Hono + Cloudflare Edge |
| **Extraction** | < 3000 ms | Docling (max_pages=3) + Groq |
| **Analysis** | < 100 ms | Redis caching + local math validation |
| **QB Execution**| < 1000 ms | Async background execution |
| **Total Pipe** | **< 6.0 seconds** | Parallel Phase 1 (Extract + QB Sync) |

---

## 🔋 TRUST BATTERY LOGIC
The system implements a tiered trust model to balance automation and security:

1. **Probation (Level 1)**: $0 Limit. 100% human review. 
2. **Standard (Level 2)**: $500 Limit. Threshold reached after 50 accurate invoices.
3. **Core (Level 3)**: $5,000 Limit. Threshold reached after 100 accurate invoices.

*Demotion happens automatically after 3 consecutive errors.*

---

## 🛡️ SECURITY & OBSERVABILITY
- **Secrets**: Strictly managed via `.env` (Infisical/Doppler ready).
- **Audit Trail**: Synchronized from Agent Core back to Edge D1 `audit_logs`.
- **Timing Metrics**: Every operation is wrapped in a `timed` context manager for P95 tracking.
- **Retry Logic**: Tenacity-backed exponential backoff for all external API (Groq, QB, Edge).

---

## 🗺️ IMPLEMENTATION ROADMAP (PHASED)
- [x] **Phase 1: Architecture Reset**: Migration from Temporal/Redpanda to FastAPI/Hono.
- [x] **Phase 2: Performance Boost**: Parallelization, connection pooling, and Redis caching.
- [ ] **Phase 3: Deep Context**: Vector search for duplicate detection across PDF contents.
- [ ] **Phase 4: Global Expansion**: Multi-currency and tax region handling.
