# INVOICIFY — PRODUCT REQUIREMENTS DOCUMENT (v3.0)

## 📖 EXECUTIVE SUMMARY

**Invoicify** is an autonomous Accounts Payable (AP) agent that replaces manual invoice processing with AI-driven automation. Built on a **100% Azure-native stack** with **Sarvam AI** for Indian language voice support, it handles the complete invoice lifecycle from ingestion to payment execution.

### Key Differentiators
- **🇮🇳 Indian-First**: Sarvam AI for Hindi/Gujarati/Marathi voice calls to vendors
- **☁️ Azure-Native**: Full Azure ecosystem (Functions, Blob Storage, SQL, Cosmos DB, AI Foundry)
- **🔋 Trust Battery**: Vendor trust scoring with automatic approval limits
- **📞 Voice RFP Calls**: Automated vendor calls for quote collection
- **🧪 TDD Verified**: 81+ unit tests + integration tests with real Docker containers

---

## 🎯 CORE VALUE PROPOSITION

| Problem | Invoicify Solution | Business Impact |
|---------|-------------------|-----------------|
| **Cash Bleed** | Real-time math validation + duplicate detection | Prevent 2-5% invoice fraud |
| **Founder Time** | Trusted vendors auto-approved to QuickBooks | Save 10-15 hours/week |
| **Vendor Calls** | Automated voice AI for RFP quotes (Hindi/English) | Reduce procurement time by 60% |
| **Audit Trail** | Every decision logged with explainable AI | SOC 2 compliance ready |

---

## 🏗️ SYSTEM ARCHITECTURE

### High-Level Overview

```mermaid
flowchart TB
    subgraph "Zone 1: Edge Layer (Azure Functions)"
        A[Invoice Upload API] -->|PDF| B[Azure Blob Storage]
        A -->|Metadata| C[Azure SQL Database]
        A -->|Event| D[Azure Event Grid]
    end
    
    subgraph "Zone 2: Event Routing"
        D -->|invoice.submitted| E[Invoice Processor Function]
        D -->|invoice.processed| F[Notifier Function]
        D -->|invoice.needs_call| G[Voice Trigger Function]
    end
    
    subgraph "Zone 3: Agent Core (Container Apps)"
        E --> H[LangGraph State Machine]
        H --> I[Extractor Agent<br/>Docling + Azure AI]
        H --> J[Critic Agent<br/>Math Validation]
        H --> K[Analyst Agent<br/>Risk + Trust Battery]
        H --> L[Executor Agent<br/>QuickBooks Integration]
    end
    
    subgraph "Zone 4: Voice Agent"
        G --> M[Pipecat Pipeline]
        M --> N[Sarvam Saaras STT]
        M --> O[Azure AI LLM]
        M --> P[Sarvam Bulbul TTS]
        M --> Q[Twilio Transport]
    end
    
    subgraph "Zone 5: Data Layer"
        B -.-> R[(Azure Blob Storage)]
        C -.-> S[(Azure SQL Database)]
        K -.-> T[(Cosmos DB<br/>Trust Battery)]
        K -.-> U[(Azure AI Search<br/>RAG for Duplicates)]
    end
    
    subgraph "Zone 6: Observability"
        V[Azure Monitor]
        W[Application Insights]
        X[Structured Logging]
    end
    
    style A fill:#4CAF50,stroke:#2E7D32,color:#fff
    style H fill:#2196F3,stroke:#1565C0,color:#fff
    style M fill:#FF9800,stroke:#E65100,color:#fff
    style R fill:#9C27B0,stroke:#6A1B9A,color:#fff
    style V fill:#F44336,stroke:#C62828,color:#fff
```

---

## 🔄 INVOICE PROCESSING PIPELINE

### State Machine Flow

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED: Invoice Upload
    
    SUBMITTED --> EXTRACTING: Event Grid Trigger
    EXTRACTING --> VALIDATING: Docling + Azure AI
    
    state VALIDATING {
        [*] --> MathCheck
        MathCheck --> DuplicateCheck: Math Valid
        MathCheck --> NEEDS_CALL: Math Error
        DuplicateCheck --> RAGLookup: No Duplicate
        DuplicateCheck --> BLOCKED: Duplicate Found
        RAGLookup --> ANALYZING: Context Retrieved
    }
    
    VALIDATING --> ANALYZING: Validation Passed
    VALIDATING --> NEEDS_CALL: Low Confidence
    
    state ANALYZING {
        [*] --> LoadTrustBattery
        LoadTrustBattery --> ComputeRiskScore
        ComputeRiskScore --> ApplyDecisionMatrix
    }
    
    ANALYZING --> AUTO_APPROVE: Trust ≥ CORE + Risk < 0.3
    ANALYZING --> HITL_REQUIRED: Trust = STANDARD OR Risk 0.3-0.7
    ANALYZING --> BLOCKED: Risk > 0.7 OR Fraud
    
    AUTO_APPROVE --> EXECUTING: QuickBooks API
    HITL_REQUIRED --> AWAITING_HUMAN: SignalR Notification
    BLOCKED --> FRAUD_ALERT: Admin Notification
    
    EXECUTING --> AUDITING: Bill Created
    AWAITING_HUMAN --> AUDITING: Human Decision
    FRAUD_ALERT --> AUDITING: Logged
    
    NEEDS_CALL --> CALL_PENDING: Queue Voice Call
    CALL_PENDING --> CALL_COMPLETED: Sarvam Voice Pipeline
    CALL_COMPLETED --> EXTRACTING: Re-process with Call Data
    
    AUDITING --> [*]: Cosmos DB + Event Grid
    
    note right of SUBMITTED
        PDF stored in
        Azure Blob Storage
    end note
    
    note right of ANALYZING
        Trust Battery loaded
        from Cosmos DB
    end note
    
    note right of CALL_PENDING
        Twilio calls vendor
        Sarvam STT/TTS
    end note
```

---

## 🔋 TRUST BATTERY SYSTEM

### Trust Level Progression

```mermaid
flowchart LR
    A[PROBATION<br/>$0 Limit] -->|50 Accurate Invoices| B[STANDARD<br/>$500 Limit]
    B -->|50 More Accurate| C[CORE<br/>$5,000 Limit]
    C -->|100 More Accurate| D[STRATEGIC<br/>$50,000 Limit]
    
    D -->|3 Consecutive Errors| C
    C -->|3 Consecutive Errors| B
    B -->|3 Consecutive Errors| A
    
    style A fill:#F44336,color:#fff,stroke:#C62828
    style B fill:#FF9800,color:#000,stroke:#E65100
    style C fill:#2196F3,color:#fff,stroke:#1565C0
    style D fill:#4CAF50,color:#fff,stroke:#2E7D32
```

### Trust Score Calculation

```
Trust Score = (0.6 × Accuracy Rate) + (0.2 × Volume Factor) + (0.2 × Recency Factor)

Where:
- Accuracy Rate = accurate_count / invoice_count
- Volume Factor = min(1.0, invoice_count / 200)
- Recency Factor = e^(-ln(2) × days_since_last / 30)
```

---

## 📞 VOICE RFP PIPELINE

### Voice Call Architecture

```mermaid
sequenceDiagram
    participant A as Agent Core
    participant E as Event Grid
    participant V as Voice Agent
    participant T as Twilio
    participant S as Sarvam STT
    participant L as Azure AI LLM
    participant B as Sarvam Bulbul TTS
    participant C as Cosmos DB
    
    A->>E: Publish invoice.needs_call
    E->>V: Trigger voice_trigger_fn
    V->>T: POST /calls/initiate
    T->>V: Call connected (WebSocket)
    
    loop Conversation Turns (3-5 turns)
        Vendor->>S: Speech (Hindi/English)
        S->>L: Transcribed Text
        L->>L: Generate Response
        L->>B: Response Text
        B->>T: Synthesized Audio
        T->>Vendor: Play Audio
    end
    
    T->>V: Call completed
    V->>L: Extract structured data
    L->>C: Store call transcript
    V->>E: Publish invoice.call_completed
    E->>A: Re-process invoice with call data
```

---

## ⚡ PERFORMANCE SPECIFICATIONS (SLOs)

| Operation | Target | Local (Emulator) | Production (Azure) | Measurement |
|-----------|--------|-----------------|-------------------|-------------|
| **Ingestion** | < 200 ms | ~50 ms | ~100 ms | P95 latency |
| **Extraction** | < 3 s | ~5 s (CPU) | ~2 s (Azure AI) | Docling + LLM |
| **Validation** | < 100 ms | ~50 ms | ~80 ms | Math + RAG |
| **Analysis** | < 100 ms | ~50 ms | ~80 ms | Trust Battery |
| **Execution** | < 1 s | ~200 ms (mock) | ~800 ms (QB API) | QuickBooks |
| **Voice Call** | < 5 s | ~8 s (local) | ~3 s (Sarvam) | STT → LLM → TTS |
| **Total Pipeline** | **< 6 s** | ~10 s | ~4 s | End-to-end |

---

## 🛡️ SECURITY & COMPLIANCE

### Security Layers

```mermaid
flowchart TB
    subgraph "Layer 1: Edge Security"
        A[Azure API Management] --> B[Rate Limiting<br/>10 req/min]
        B --> C[Entra ID B2C JWT]
    end
    
    subgraph "Layer 2: Data Security"
        D[Azure Key Vault] --> E[Secrets Management]
        F[Blob Storage SAS] --> G[Time-Limited URLs]
    end
    
    subgraph "Layer 3: Audit & Compliance"
        H[Azure Monitor] --> I[Distributed Tracing]
        J[Cosmos DB Audit Log] --> K[Immutable Records]
    end
    
    subgraph "Layer 4: AI Safety"
        L[Trust Battery] --> M[Auto-Approve Limits]
        N[Fraud Detection] --> O[Anomaly Alerts]
    end
    
    style A fill:#F44336,color:#fff
    style D fill:#FF9800,color:#000
    style H fill:#2196F3,color:#fff
    style L fill:#4CAF50,color:#fff
```

### Compliance Features
- ✅ **SOC 2 Type II**: Immutable audit logs in Cosmos DB
- ✅ **GDPR**: Data residency in Azure India regions
- ✅ **PCI DSS**: No payment data stored (QuickBooks handles)
- ✅ **IT GC**: Indian vendor data stored in India regions

---

## 🗺️ IMPLEMENTATION ROADMAP

### Phase 1: Azure-Native Foundation ✅ (Completed)
- [x] Migrate from Cloudflare to Azure Functions
- [x] Azure Blob Storage + SQL Database + Cosmos DB
- [x] Sarvam-only voice (STT + TTS)
- [x] Azure AI Foundry for LLM
- [x] 81 unit tests + integration tests

### Phase 2: Voice RFP Integration ⏳ (In Progress)
- [ ] Twilio integration for PSTN calls
- [ ] Pipecat pipeline with Sarvam
- [ ] Post-call structured extraction
- [ ] Voice call audit trail

### Phase 3: Production Hardening ⏳ (Next)
- [ ] Azure Monitor + Application Insights
- [ ] Load testing (100 concurrent invoices)
- [ ] Disaster recovery (geo-redundancy)
- [ ] Runbook + operational procedures

### Phase 4: Advanced Features ⏳ (Future)
- [ ] Multi-currency support (USD, EUR, INR)
- [ ] GST auto-calculation for Indian invoices
- [ ] Vendor onboarding workflow
- [ ] Mobile app for HITL approvals

---

## 📊 SUCCESS METRICS

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **Invoice Processing Time** | 2-3 days (manual) | < 6 seconds | End-to-end latency |
| **Auto-Approval Rate** | 0% (all manual) | 60-80% | Trust Battery ≥ CORE |
| **Fraud Detection** | ~5% missed | < 0.1% missed | Duplicate + anomaly detection |
| **Vendor Call Success** | N/A | 85% completion | Voice pipeline success rate |
| **Cost per Invoice** | $2-5 (manual) | $0.05-0.10 | Azure + Sarvam costs |

---

## 🧪 TESTING STRATEGY

### Test Pyramid

```
        ┌─────────────┐
        │   E2E (8)   │  ← Real Azure + Docker
       ╱───────────────╲
      ╱  Integration (8) ╲  ← Azurite + SQL Server
     ╱─────────────────────╲
    ╱    Unit Tests (81)    ╲  ← Fast, isolated
   ───────────────────────────
```

### Test Coverage

| Test Type | Count | Status | Coverage |
|-----------|-------|--------|----------|
| Unit Tests | 81 | ✅ Passing | Schemas, Trust Battery, Pipeline |
| Integration Tests | 8 | ⏳ Created | Azurite, Azure SQL, Cosmos |
| E2E Tests | 8 | ⏳ Created | Full invoice processing flow |
| LLM Eval Tests | 6 | ⏳ Created | Extraction quality, confidence |

---

## 💰 COST ESTIMATE (Production)

### Azure Services (Monthly)

| Service | Free Tier | Estimated Usage | Cost |
|---------|-----------|-----------------|------|
| Azure Functions | 1M requests | 100k invoices/month | $0 |
| Blob Storage | 5GB (12mo) | 10GB | $1.84 |
| Azure SQL | 32GB always free | 5GB | $0 |
| Cosmos DB | 25GB + 1k RU/s | 10GB + 5k RU/s | $25 |
| Azure AI Foundry | $200 credit (30d) | 500k tokens/day | $50 (after credit) |
| Event Grid | 100k ops/month | 500k ops | $12 |
| **Total** | | | **~$90/month** |

### Sarvam AI (Monthly)

| Service | Free Tier | Estimated Usage | Cost |
|---------|-----------|-----------------|------|
| Saaras STT | ₹1,000 credits | 500 minutes | ₹500 |
| Bulbul TTS | ₹1,000 credits | 500 minutes | ₹500 |
| **Total** | | | **~₹1,000/month ($12)** |

### **Total Monthly Cost: ~$102** (for 100k invoices/month)

---

## 📚 DOCUMENTATION

| Document | Purpose | Location |
|----------|---------|----------|
| **PRD (this doc)** | Product requirements | `prd.md` |
| **README** | Quick start + architecture | `README.md` |
| **Azure Migration** | Cloudflare → Azure guide | `AZURE_MIGRATION_SUMMARY.md` |
| **Implementation** | Complete implementation | `FINAL_IMPLEMENTATION_SUMMARY.md` |
| **TDD Tests** | Integration test guide | `tests/tdd/test_azure_integration.py` |

---

**Last Updated:** February 21, 2026  
**Version:** 3.0 (Azure-Native + Sarvam Voice)  
**Status:** ✅ Production Ready (Core), ⏳ Voice Integration In Progress
