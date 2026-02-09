# Nivi Architecture Diagrams

# # System Overview

```mermaid
graph TB
    subgraph "Edge Layer"
        USER[User/Browser]
        CF[Cloudflare Worker<br/>Hono + tRPC]
        UPLOAD[File Upload API]
    end

    subgraph "Event Streaming"
        WS[WarpStream Agent<br/>Kafka Protocol]
        COS_BUCKET[IBM COS<br/>Event Storage]
    end

    subgraph "IBM Cloud - Free Tier"
        subgraph "Code Engine"
            WORKER[Temporal Worker<br/>Python 3.11]
        end

        subgraph "Data Lake"
            LAKE_RAW[/raw/{date}/{id}.pdf/]
            LAKE_PROC[/processed/{date}/{id}.json/]
            LAKE_ML[/ml-models/{vendor}.pkl/]
        end
    end

    subgraph "Temporal Cloud"
        TEMP[Temporal Server<br/>Namespace: nivi-prod]
        WF[InvoiceProcessingWorkflow]
    end

    subgraph "Knowledge Layer"
        NEO4J[(Neo4j Aura<br/>Graph Database)]
        QDRANT[(Qdrant Cloud<br/>Vector Search)]
    end

    subgraph "AI Services"
        GROQ[Groq API<br/>Llama 3 Vision]
        RIVER[River ML<br/>HalfSpaceTrees]
    end

| Upload Invoice |
| POST /upload |
| Produce |
| Store Segments |
| Consume |

| Execute |
| Orchestrate |

| Activity |
| Activity |
| Activity |
| Activity |

| Read/Write |
| Read/Write |
| Read/Write |

```text
# # Temporal Workflow

```mermaid
flowchart TD
    START([Start]) --> EXTRACT[Extract Invoice Data<br/>Groq Vision API]

    EXTRACT --> ANOMALY[Detect Anomaly<br/>River ML]

    ANOMALY --> ANALYST[Analyst Evaluation<br/>Pattern Detection]

    ANALYST --> CRITIC[Critic Review<br/>Safety Check]

    CRITIC --> DECISION{Decision?}

| Auto-Approve |
| HITL Required |
| Reject |


    SIGNAL --> HUMAN[Human Review<br/>48hr Timeout]

| Approved |
| Rejected |


    APPROVE --> FINALIZE[Finalize<br/>Update Qdrant]
    REJECT --> FINALIZE

    FINALIZE --> END([End])

    style EXTRACT fill:#bbf
    style ANOMALY fill:#bfb
    style ANALYST fill:#fbf
    style CRITIC fill:#fbb
    style DECISION fill:#ff9
    style SIGNAL fill:#f99
```text
# # Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CF as Cloudflare Worker
    participant Kafka as WarpStream/Kafka
    participant Worker as Temporal Worker
    participant Groq as Groq API
    participant River as River ML
    participant Neo4j as Neo4j Aura
    participant COS as IBM COS

    User->>CF: Upload Invoice PDF
    CF->>CF: Validate & Store Metadata
    CF->>Kafka: Produce: invoice.ingested
    CF->>User: Return 202 Accepted

    Kafka->>Worker: Consume: invoice.ingested
    Worker->>Groq: Extract Data (Vision)
    Groq-->>Worker: Invoice Data JSON

    Worker->>River: Detect Anomaly
    River-->>Worker: Anomaly Score
    River->>COS: Save Model State

    Worker->>Neo4j: Get Vendor History
    Neo4j-->>Worker: Past Invoices

    Worker->>Worker: Analyst Evaluation
    Worker->>Worker: Critic Review

    alt Auto-Approve
        Worker->>Neo4j: Create Invoice Node
        Worker->>Kafka: Produce: invoice.processed
    else HITL Required
        Worker->>Kafka: Produce: invoice.approval_needed
        Note over Worker: Wait for Signal
        User->>CF: Approve/Reject
        CF->>Worker: Signal: approval_response
        Worker->>Neo4j: Update Status
    end

    Worker->>COS: Save Processed Data
```text
# # Test Infrastructure

```mermaid
graph TB
    subgraph "Test Environment"
        TEST[Test Runner<br/>Docker]

        subgraph "Services"
            TEMP_DEV[Temporal Dev<br/>:7233]
            KAFKA[Redpanda<br/>:19092]
            MOCK[Mockoon<br/>:3000]
            MINIO[MinIO<br/>:9000]
        end

        subgraph "External (Host)"
            OLLAMA[Ollama<br/>:11434]
            NEO4J_DEV[Neo4j<br/>:7687]
            QDRANT_DEV[Qdrant<br/>:6333]
        end
    end

    subgraph "Test Types"
        UNIT[Unit Tests<br/>Mocked]
        INT[Integration Tests<br/>Real Services]
        E2E[E2E Tests<br/>Full Flow]
    end

| Runs |
| Runs |
| Runs |

| Mocks |
| Uses |
| Uses |
| Uses |
| Uses |
| Uses |
| Uses |

```text
# # Component Dependencies

```mermaid
graph LR
    subgraph "Activities"
        A1[analyst_evaluate]
        A2[critic_review]
        A3[detect_anomaly]
        A4[extract_invoice]
    end

    subgraph "Infrastructure"
        I1[Neo4jClient]
        I2[IBMCOSClient]
        I3[QdrantClient]
    end

    subgraph "External APIs"
        E1[Groq API]
        E2[River ML]
    end

    subgraph "Data Stores"
        D1[Neo4j Aura]
        D2[IBM COS]
        D3[Qdrant Cloud]
    end

| Uses |
| Uses |

| Uses |

| Uses |
| Uses |
| Reads/Writes |

| Calls |

| Connects |
| Connects |
| Connects |

```text
# # Security Architecture

```mermaid
graph TB
    subgraph "Authentication"
        MTLS[mTLS Certificates<br/>Temporal Cloud]
        IAM[IBM IAM<br/>Code Engine]
        API_KEY[API Keys<br/>Secrets Manager]
    end

    subgraph "Encryption"
        TLS[TLS 1.3<br/>In Transit]
        AT_REST[Encryption<br/>At Rest]
        FIELD[Field-Level<br/>Encryption]
    end

    subgraph "Data Protection"
        PII[PII Redaction<br/>Before Storage]
        AUDIT[Audit Logging<br/>All Actions]
        MASK[Data Masking<br/>Sensitive Fields]
    end

    subgraph "Access Control"
        ACL_KAFKA[Topic ACLs<br/>WarpStream]
        ACL_TEMP[Namespace ACLs<br/>Temporal]
        RLS[Row-Level<br/>Security]
    end

| HTTPS |
| mTLS |
| IAM + API Key |
| TLS |
| API Key |


    style EDGE fill:#bbf
    style WORKER fill:#bfb
```text
# # Deployment Flow

```mermaid
graph LR
    subgraph "Development"
        CODE[Code Changes]
        TEST[Run Tests<br/>Docker]
        COMMIT[Git Commit]
    end

    subgraph "CI/CD"
        BUILD[Build Docker<br/>Image]
        PUSH[Push to<br/>IBM CR]
        DEPLOY[Deploy to<br/>Code Engine]
    end

    subgraph "Production"
        CE_WORKER[Temporal Worker<br/>IBM CE]
        CE_WARP[WarpStream<br/>IBM CE]
        MONITOR[Monitoring<br/>IBM Log Analysis]
    end

    CODE --> TEST

| Pass |

    COMMIT --> BUILD
    BUILD --> PUSH
    PUSH --> DEPLOY
    DEPLOY --> CE_WORKER
    DEPLOY --> CE_WARP
    CE_WORKER --> MONITOR
    CE_WARP --> MONITOR
```text
# # Cost Breakdown

```mermaid
pie title Monthly Cost - $0 Total
    "IBM Code Engine" : 0
    "IBM COS" : 0
    "Temporal Cloud" : 0
    "Neo4j Aura" : 0
    "Qdrant Cloud" : 0
    "Groq API" : 0
```text
# # Technology Stack

```mermaid
mindmap
  root((Nivi Stack))
    Orchestration
      Temporal Cloud
      Python SDK
      Durable Execution
    Compute
      IBM Code Engine
      Serverless Containers
      Scale-to-Zero
    Storage
      IBM COS
      Data Lake
      ML Models
    Streaming
      WarpStream
      Kafka Protocol
      Event-Driven
    AI/ML
      Groq API
      River ML
      Online Learning
    Knowledge
      Neo4j Aura
      Graph Database
      Trust Tracking
    Search
      Qdrant Cloud
      Vector Search
      Similarity
    Testing
      Pytest
      Docker
      Mockoon
    Edge
      Cloudflare Workers
      Hono Framework
```text
---

*Use these diagrams in your documentation, presentations, and architecture reviews.*
