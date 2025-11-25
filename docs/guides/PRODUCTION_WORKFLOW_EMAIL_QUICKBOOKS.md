# Production Invoice Processing Workflow: Email + QuickBooks Integration

## Executive Summary

The AP Intake system is designed for **automated invoice processing from email sources and QuickBooks integration**, not manual API uploads. The production workflow continuously monitors email inboxes and QuickBooks for new invoices, processes them through AI-powered extraction, validates against business rules, and exports structured data back to QuickBooks.

## Production Workflow Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Gmail/Email   │    │   QuickBooks     │    │   Other Sources     │
│   Monitoring    │    │   API Monitoring │    │   (Future)          │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────────┘
          │                      │                       │
          ▼                      ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                Email Ingestion Service                          │
│  • Gmail OAuth 2.0 integration                                  │
│  • Security validation (malicious patterns, trusted domains)    │
│  • PDF attachment extraction                                     │
│  • Duplicate detection (SHA-256)                               │
│  • Auto-processing queuing                                      │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│              Background Processing Queue                         │
│  • Celery workers with async invoice processing                 │
│  • Rate limiting and retry logic                                │
│  • Dead letter queue handling                                   │
│  • Real-time status updates                                     │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│            Enhanced Invoice Processor                           │
│  • LangGraph state machine workflow                             │
│  • Docling AI extraction + LLM patching                         │
│  • Multi-strategy validation (17 exception types)              │
│  • Confidence scoring and bbox tracking                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│             Validation & Exception Handling                     │
│  • Business rules validation                                    │
│  • Vendor/PO matching                                          │
│  • Mathematical validation (calculations, totals)              │
│  • Exception creation with resolution workflows                │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Integration Factory                              │
│  • Swappable providers (Native, n8n, custom)                   │
│  • Circuit breaker pattern for reliability                     │
│  • Auto-failover and fallback mechanisms                       │
│  • QuickBooks integration provider                             │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│              QuickBooks Export                                   │
│  • OAuth 2.0 authentication                                     │
│  • Invoice/Bill creation                                        │
│  • Vendor and account matching                                 │
│  • Batch processing and sync                                   │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Human Review Interface                           │
│  • Web dashboard for exceptions                                 │
│  • Real-time processing status                                  │
│  • Batch approval workflows                                    │
│  • CFO digest and analytics                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Detailed Workflow Steps

### 1. Email Monitoring & Ingestion

**Trigger**: Continuous monitoring via Celery Beat scheduled tasks

**Process**:
- **Gmail OAuth 2.0 Integration**: Secure access to user inboxes
- **Smart Email Filtering**: Searches for invoices with patterns like:
  ```
  - "has:attachment filename:pdf (invoice OR bill OR receipt)"
  - "from:*.intuit.com has:attachment filename:pdf"
  - "newer:7d has:attachment filename:pdf invoice"
  ```
- **Security Validation**: Multi-layer security checks
  - Malicious pattern detection
  - Trusted domain verification (*.intuit.com, *.xero.com, etc.)
  - URL and attachment count thresholds
  - PDF structure validation
- **Duplicate Prevention**: SHA-256 content hashing to prevent reprocessing

**Key Files**:
- `app/services/email_ingestion_service.py:80-123` - Main ingestion logic
- `app/workers/email_tasks.py:28-87` - Background monitoring tasks

### 2. AI-Powered Extraction & Enhancement

**Trigger**: Email attachments queued for processing

**Process**:
- **Docling Document Parsing**: Advanced PDF extraction with confidence scores
- **LLM Patching**: deepseek/deepseek-chat-v3.1:free integration for low-confidence field correction
- **BBox Coordinate Tracking**: Field-level provenance for audit trails
- **Quality Metrics**: Per-field confidence scoring and overall quality assessment

**Extraction Workflow States** (`app/workflows/enhanced_invoice_processor.py`):
1. **receive** - File validation and metadata extraction
2. **extract** - AI-powered data extraction with confidence scoring
3. **enhance** - LLM patching for low-confidence fields
4. **validate** - Business rules and mathematical validation
5. **triage** - Intelligent routing (auto-approve vs human review)

### 3. Comprehensive Validation System

**Validation Types**:
- **Structural Validation**: Required fields, formats, data types
- **Mathematical Validation**: Calculation verification, total matching
- **Business Rules Validation**: Vendor matching, PO validation, duplicate detection
- **Exception Taxonomy**: 17 different exception reason codes with resolution workflows

**Exception Examples**:
- `vendor_not_found` - New vendor requires setup
- `po_mismatch` - Purchase order discrepancies
- `calculation_error` - Mathematical inconsistencies
- `duplicate_invoice` - Potential duplicate invoice

### 4. QuickBooks Integration

**Authentication**: OAuth 2.0 flow with Intuit
**Export Process**:
- Invoice/Bill creation in QuickBooks Online
- Vendor matching and creation
- Account mapping and categorization
- Batch processing for efficiency
- Error handling and retry logic

**Key Files**:
- `app/services/quickbooks_service.py` - Main QuickBooks integration
- `app/workers/quickbooks_tasks.py` - Background export tasks

### 5. Human Review & Exception Management

**Dashboard Features**:
- Real-time processing status
- Exception resolution workflows
- Batch approval capabilities
- CFO digest generation
- Analytics and reporting

## Configuration & Setup

### Email Integration Configuration

```bash
# Gmail OAuth 2.0 Configuration
GMAIL_CLIENT_ID=your-gmail-client-id
GMAIL_CLIENT_SECRET=your-gmail-client-secret
GMAIL_REDIRECT_URI=http://localhost:8000/api/v1/email/callback

# Email Processing Settings
EMAIL_MONITORING_INTERVAL_MINUTES=60
EMAIL_PROCESSING_BATCH_SIZE=25
EMAIL_DAYS_BACK_LOOK=7
```

### QuickBooks Configuration

```bash
# QuickBooks OAuth 2.0 Configuration
QUICKBOOKS_SANDBOX_CLIENT_ID=your-qb-client-id
QUICKBOOKS_SANDBOX_CLIENT_SECRET=your-qb-client-secret
QUICKBOOKS_REDIRECT_URI=http://localhost:8000/api/v1/quickbooks/callback
QUICKBOOKS_ENVIRONMENT=sandbox  # or production

# QuickBooks Processing
QUICKBOOKS_BATCH_SIZE=10
QUICKBOOKS_SYNC_INTERVAL_MINUTES=30
```

### Production Workflow Settings

```bash
# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_WORKER_CONCURRENCY=4

# Processing Thresholds
DOCLING_CONFIDENCE_THRESHOLD=0.8
LLM_MAX_COST_PER_INVOICE=0.10
VALIDATION_STRICT_MODE=false

# Rate Limiting
QUICKBOOKS_RATE_LIMIT_CALLS=500  # Per minute
QUICKBOOKS_RATE_LIMIT_WINDOW=60
```

## Production Deployment

### Scheduled Tasks (Celery Beat)

```python
# Email monitoring - runs every 60 minutes
"email_monitor_*": {
    "task": "app.workers.email_tasks.monitor_gmail_inbox",
    "schedule": crontab(minute="*/60"),
    "args": (user_id, credentials_data, 1, 25, True)
}

# QuickBooks sync - runs every 30 minutes
"quickbooks_sync": {
    "task": "app.workers.quickbooks_tasks.sync_invoices",
    "schedule": crontab(minute="*/30"),
    "args": ()
}

# Health checks - runs every 5 minutes
"health_checks": {
    "task": "app.workers.email_tasks.health_check_email_services",
    "schedule": crontab(minute="*/5"),
    "args": ()
}
```

### Monitoring & Observability

**Key Metrics**:
- Email processing rate (emails/hour)
- Extraction confidence scores
- Validation pass/fail rates
- QuickBooks sync success rates
- Exception resolution times
- System health and availability

**Alerting**:
- Email monitoring failures
- QuickBooks API rate limits
- High exception rates
- Processing queue backlogs

## Example Production Flow

### End-to-End Example

1. **Email Arrives**: Vendor sends invoice to `accounts@company.com`
2. **Gmail Monitoring**: Celery task detects new email with PDF attachment
3. **Security Validation**: Email passes security checks (trusted domain, no malicious patterns)
4. **Attachment Extraction**: PDF invoice extracted and hashed
5. **Duplicate Check**: SHA-256 hash verified as unique
6. **Queue Processing**: Attachment queued for AI processing
7. **AI Extraction**: Docling extracts invoice data with 92% confidence
8. **LLM Enhancement**: deepseek/deepseek-chat-v3.1:free patches low-confidence vendor name field
9. **Validation**: Business rules validation passes (vendor exists, PO matches)
10. **QuickBooks Export**: Invoice created in QuickBooks as Bill
11. **Notification**: User notified of successful processing
12. **Dashboard**: Invoice appears in processed invoices dashboard

### Processing Time Estimates

- **Email Detection**: < 1 minute (monitoring interval)
- **Security Validation**: < 5 seconds
- **PDF Extraction**: 2-10 seconds (depending on complexity)
- **LLM Enhancement**: 3-8 seconds (if needed)
- **Validation**: < 2 seconds
- **QuickBooks Export**: 5-15 seconds
- **Total Processing**: ~30-60 seconds per invoice

## Troubleshooting & Common Issues

### Email Integration Issues

**Problem**: No emails being processed
**Solution**: Check Gmail OAuth credentials and monitoring schedule
```bash
# Check email monitoring task status
curl http://localhost:8000/api/v1/email/monitoring/status

# Test Gmail connection
curl http://localhost:8000/api/v1/email/test-connection
```

### QuickBooks Integration Issues

**Problem**: Invoice export failures
**Solution**: Verify OAuth tokens and rate limits
```bash
# Check QuickBooks connection
curl http://localhost:8000/api/v1/quickbooks/health

# Review rate limits
curl http://localhost:8000/api/v1/quickbooks/rate-limit-status
```

### Processing Bottlenecks

**Problem**: Queue backlog building up
**Solution**: Scale Celery workers and check resource utilization
```bash
# Scale workers
docker-compose scale celery_worker=8

# Check queue depth
curl http://localhost:8000/api/v1/metrics/queues
```

## Security & Compliance

### Data Protection
- **Encryption**: All data encrypted at rest and in transit
- **Access Control**: OAuth 2.0 with limited scopes
- **Audit Trail**: Complete processing provenance
- **Data Retention**: Configurable retention policies

### Compliance Features
- **SOC 2 Type II**: Security controls and monitoring
- **GDPR Compliant**: Data handling and privacy controls
- **SOX Compliance**: Financial data integrity and audit trails

## Production Best Practices

1. **Start with Sandbox**: Use QuickBooks Sandbox for initial testing
2. **Gradual Ramp-up**: Begin with low processing volumes and increase gradually
3. **Monitor Exception Rates**: Keep exception rates below 20% target
4. **Regular Health Checks**: Automated monitoring of all components
5. **Backup Procedures**: Regular database and file storage backups
6. **Security Reviews**: Quarterly security assessments
7. **Performance Tuning**: Regular optimization of processing times

## Next Steps & Enhancements

### Short-term (Next 90 Days)
- **Outlook Integration**: Expand beyond Gmail to support Outlook/Exchange
- **Mobile App**: Native mobile app for exception management
- **Advanced Analytics**: ML for anomaly detection and prediction

### Medium-term (6-12 Months)
- **Multi-tenant Architecture**: Support for multiple organizations
- **Custom Workflow Builder**: Visual workflow designer
- **Advanced ERP Integrations**: NetSuite, Sage, SAP connectors

### Long-term (12+ Months)
- **Global Expansion**: Multi-language and multi-currency support
- **AI Platform Integration**: Advanced ML model deployment
- **Marketplace**: Third-party integration marketplace

---

This workflow documentation provides a comprehensive guide to how invoices are processed in production from email and QuickBooks sources, including all the technical details, configuration, and operational procedures needed for successful deployment.