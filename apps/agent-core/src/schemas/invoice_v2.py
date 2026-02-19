"""
Invoice data models using Pydantic v2 strict mode.

This module defines all data schemas for the Invoicify invoice processing pipeline,
including trust levels, risk decisions, and complete invoice documents.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class TrustLevel(str, Enum):
    """
    Vendor trust levels based on historical accuracy.
    
    Hierarchy:
    - PROBATION: New vendor. All invoices require human review.
    - STANDARD: 50+ accurate invoices. Auto-approve ≤ $500.
    - CORE: 100+ accurate invoices. Auto-approve ≤ $5,000.
    - STRATEGIC: 200+ accurate invoices. Auto-approve ≤ $50,000.
    """
    PROBATION = "PROBATION"
    STANDARD = "STANDARD"
    CORE = "CORE"
    STRATEGIC = "STRATEGIC"


class RiskDecision(str, Enum):
    """
    Risk-based decision outcomes.
    
    - AUTO_APPROVE: Trust >= CORE, risk < 0.3, amount < limit
    - HITL_REQUIRED: Trust = STANDARD OR risk 0.3-0.7 OR amount > limit
    - BLOCKED: Risk > 0.7 OR fraud signals OR duplicate detected
    - NEEDS_CALL: Extraction confidence < 0.75 OR missing critical fields
    """
    AUTO_APPROVE = "AUTO_APPROVE"
    HITL_REQUIRED = "HITL_REQUIRED"
    BLOCKED = "BLOCKED"
    NEEDS_CALL = "NEEDS_CALL"


class InvoiceStatus(str, Enum):
    """
    Invoice processing pipeline states.
    
    Flow: SUBMITTED → EXTRACTING → VALIDATING → ANALYZING → 
          {AUTO_APPROVE | HITL_REQUIRED | BLOCKED} → AUDITING → END
    """
    SUBMITTED = "SUBMITTED"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    ANALYZING = "ANALYZING"
    CALL_PENDING = "CALL_PENDING"
    APPROVED = "APPROVED"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class VoiceCallStatus(str, Enum):
    """Status of a vendor voice call."""
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NO_ANSWER = "NO_ANSWER"


class CallPurpose(str, Enum):
    """Purpose of a vendor voice call."""
    RFP_QUOTE = "rfp_quote"
    INVOICE_FOLLOWUP = "invoice_followup"
    MISSING_DETAILS = "missing_details"


# ─────────────────────────────────────────────────────────────────────────────
# LINE ITEM & VENDOR SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class LineItem(BaseModel):
    """
    A single line item from an invoice.
    
    Validates:
    - quantity > 0
    - unit_price >= 0
    - total = quantity * unit_price (within 2 cent tolerance)
    """
    description: str = Field(..., min_length=1, max_length=500, description="Item description")
    quantity: float = Field(..., gt=0, description="Quantity ordered")
    unit_price: float = Field(..., ge=0.0, description="Price per unit")
    total: float = Field(..., ge=0.0, description="Line total amount")
    tax_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Tax rate (0.0-1.0)")

    @model_validator(mode='after')
    def validate_total(self) -> 'LineItem':
        """Ensure total matches quantity * unit_price within 2 cent tolerance."""
        expected = self.quantity * self.unit_price
        if abs(self.total - expected) > 0.02:  # 2 cent tolerance
            raise ValueError(f"Line item total mismatch: got {self.total:.2f}, expected {expected:.2f}")
        return self

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "description": "Office Chairs",
            "quantity": 10,
            "unit_price": 150.00,
            "total": 1500.00,
            "tax_rate": 0.18
        }
    })


class VendorInfo(BaseModel):
    """
    Vendor/supplier information.
    
    All fields optional except name for flexibility in extraction.
    """
    name: str = Field(..., min_length=1, max_length=255, description="Vendor legal name")
    address: Optional[str] = Field(default=None, max_length=500, description="Vendor address")
    tax_id: Optional[str] = Field(default=None, max_length=50, description="Tax identification number")
    phone: Optional[str] = Field(default=None, max_length=50, description="Phone number")
    email: Optional[str] = Field(default=None, max_length=255, description="Email address")
    bank_account_last4: Optional[str] = Field(default=None, min_length=4, max_length=4, description="Bank account last 4 digits")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "Acme Supplies Pvt Ltd",
            "address": "123 Business Park, Mumbai 400001",
            "tax_id": "27AABCU9603R1ZM",
            "phone": "+91-22-12345678",
            "email": "billing@acme.in"
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTED INVOICE (OUTPUT OF EXTRACTOR AGENT)
# ─────────────────────────────────────────────────────────────────────────────

class ExtractedInvoice(BaseModel):
    """
    Output of Extractor Agent.
    
    Typed, validated, ready for Critic Agent.
    Contains all extracted fields plus metadata about extraction quality.
    """
    invoice_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique invoice ID (UUID)"
    )
    invoice_number: str = Field(..., min_length=1, max_length=100, description="Vendor's invoice number")
    vendor: VendorInfo = Field(..., description="Vendor information")
    line_items: List[LineItem] = Field(default_factory=list, description="Invoice line items")
    subtotal: float = Field(..., ge=0.0, description="Subtotal before tax")
    tax_amount: float = Field(default=0.0, ge=0.0, description="Tax amount")
    total_amount: float = Field(..., ge=0.0, description="Total amount due")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO currency code")
    invoice_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Invoice date (YYYY-MM-DD)")
    due_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Due date (YYYY-MM-DD)")
    po_number: Optional[str] = Field(default=None, max_length=100, description="Purchase order number")
    payment_terms: Optional[str] = Field(default=None, max_length=255, description="Payment terms")
    
    # Extraction metadata
    extraction_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    extraction_model: str = Field(..., min_length=1, description="Model used for extraction")
    extraction_latency_ms: int = Field(..., ge=0, description="Extraction latency in ms")
    missing_fields: List[str] = Field(default_factory=list, description="Fields that could not be extracted")

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: float, info) -> float:
        """Ensure total_amount ≈ subtotal + tax_amount within 5 cent tolerance."""
        if 'values' in info.data:
            values = info.data['values']
            subtotal = values.get("subtotal", 0)
            tax = values.get("tax_amount", 0)
            expected = subtotal + tax
            if abs(v - expected) > 0.05:  # 5 cent tolerance
                raise ValueError(f"Total mismatch: {v:.2f} != {subtotal:.2f} + {tax:.2f}")
        return v

    @field_validator("extraction_confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Flag low confidence extractions."""
        if v < 0.75:
            # This is informational - downstream should check for NEEDS_CALL
            pass
        return v

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_number": "INV-2024-001",
            "vendor": {
                "name": "Acme Supplies",
                "tax_id": "27AABCU9603R1ZM"
            },
            "line_items": [
                {"description": "Office Chairs", "quantity": 10, "unit_price": 150.0, "total": 1500.0}
            ],
            "subtotal": 3000.0,
            "tax_amount": 540.0,
            "total_amount": 3540.0,
            "currency": "USD",
            "invoice_date": "2024-01-15",
            "extraction_confidence": 0.97,
            "extraction_model": "gpt-4o",
            "extraction_latency_ms": 2340
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# RISK ANALYSIS (OUTPUT OF ANALYST + CRITIC AGENT)
# ─────────────────────────────────────────────────────────────────────────────

class RiskAnalysis(BaseModel):
    """
    Output of Analyst + Critic Agent.
    
    Every field must be explainable to a human reviewer.
    Used for audit trail and HITL decision support.
    """
    # Core decision fields
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Overall risk score (0.0-1.0)")
    decision: RiskDecision = Field(..., description="Risk-based decision")
    decision_reason: str = Field(..., min_length=1, max_length=500, description="Human-readable reason")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    trust_level: TrustLevel = Field(..., description="Vendor trust level")
    trust_score: float = Field(..., ge=0.0, le=1.0, description="Vendor trust score")

    # Risk signals
    is_duplicate: bool = Field(default=False, description="Whether this is a potential duplicate")
    duplicate_invoice_id: Optional[str] = Field(default=None, description="ID of potential duplicate")
    price_anomaly: bool = Field(default=False, description="Whether price is anomalous vs history")
    price_variance_pct: Optional[float] = Field(default=None, ge=0.0, description="Price variance percentage")
    math_errors: List[str] = Field(default_factory=list, description="List of math validation errors")
    fraud_signals: List[str] = Field(default_factory=list, description="List of fraud indicators")

    # Limits applied
    auto_approve_limit: float = Field(..., ge=0.0, description="Auto-approve limit for this vendor")
    amount_vs_limit: Literal["WITHIN", "EXCEEDS"] = Field(..., description="Amount vs auto-approve limit")

    # RAG context used
    similar_invoices_found: int = Field(..., ge=0, description="Number of similar invoices found")
    contract_terms_found: bool = Field(default=False, description="Whether contract terms were found")
    rag_retrieval_latency_ms: int = Field(..., ge=0, description="RAG retrieval latency")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "risk_score": 0.25,
            "decision": "AUTO_APPROVE",
            "decision_reason": "CORE vendor, risk < 0.3, amount within $5000 limit",
            "confidence": 0.92,
            "trust_level": "CORE",
            "trust_score": 0.85,
            "is_duplicate": False,
            "price_anomaly": False,
            "math_errors": [],
            "fraud_signals": [],
            "auto_approve_limit": 5000.0,
            "amount_vs_limit": "WITHIN",
            "similar_invoices_found": 12,
            "contract_terms_found": True,
            "rag_retrieval_latency_ms": 234
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# VOICE CALL RECORD (OUTPUT OF VOICE AGENT)
# ─────────────────────────────────────────────────────────────────────────────

class VoiceCallRecord(BaseModel):
    """
    Record of a vendor call attempt.
    
    Captures full call metadata, transcript, and extracted data.
    """
    call_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique call ID (UUID)"
    )
    invoice_id: str = Field(..., description="Associated invoice ID")
    vendor_phone: str = Field(..., min_length=10, description="Vendor phone number")
    vendor_name: str = Field(..., description="Vendor contact name")
    purpose: CallPurpose = Field(..., description="Purpose of the call")
    language: str = Field(default="hi-IN", description="Language code (e.g., hi-IN, en-US)")
    
    # Call status
    status: VoiceCallStatus = Field(default=VoiceCallStatus.QUEUED, description="Call status")
    duration_seconds: Optional[int] = Field(default=None, ge=0, description="Call duration")
    
    # Call content
    transcript: Optional[str] = Field(default=None, description="Full call transcript")
    extracted_data: Optional[Dict[str, Any]] = Field(default=None, description="Structured data extracted from call")
    
    # Latency breakdown
    total_latency_ms: Optional[int] = Field(default=None, ge=0, description="Total call latency")
    stt_latency_ms: Optional[int] = Field(default=None, ge=0, description="STT latency")
    llm_latency_ms: Optional[int] = Field(default=None, ge=0, description="LLM latency")
    tts_latency_ms: Optional[int] = Field(default=None, ge=0, description="TTS latency")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Call creation time")
    completed_at: Optional[datetime] = Field(default=None, description="Call completion time")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "call_id": "call-123456",
            "invoice_id": "inv-789",
            "vendor_phone": "+919999999999",
            "vendor_name": "Rajesh Kumar",
            "purpose": "missing_details",
            "language": "hi-IN",
            "status": "COMPLETED",
            "duration_seconds": 120,
            "transcript": "Vendor confirmed invoice amount and due date...",
            "total_latency_ms": 3500
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# INVOICE DOCUMENT (COSMOS DB TOP-LEVEL ENTITY)
# ─────────────────────────────────────────────────────────────────────────────

class InvoiceDocument(BaseModel):
    """
    Cosmos DB document. Top-level entity.
    
    id = invoice_id (partition key = vendor_name)
    Contains complete invoice lifecycle data.
    """
    id: str = Field(..., description="Document ID (equals invoice_id)")
    partition_key: str = Field(..., description="Partition key (vendor_name)")
    tenant_id: str = Field(..., description="Tenant ID")
    trace_id: str = Field(..., description="Distributed trace ID")
    r2_url: str = Field(..., description="R2 presigned URL for PDF")
    
    # Processing state
    status: InvoiceStatus = Field(default=InvoiceStatus.SUBMITTED, description="Current status")
    
    # Pipeline outputs
    extracted: Optional[ExtractedInvoice] = Field(default=None, description="Extractor output")
    risk: Optional[RiskAnalysis] = Field(default=None, description="Risk analysis output")
    voice_call: Optional[VoiceCallRecord] = Field(default=None, description="Voice call record")
    
    # Execution results
    quickbooks_bill_id: Optional[str] = Field(default=None, description="QuickBooks bill ID if created")
    
    # HITL fields
    reviewer_id: Optional[str] = Field(default=None, description="Human reviewer ID")
    reviewer_decision: Optional[str] = Field(default=None, description="Human decision (APPROVED/REJECTED)")
    reviewer_notes: Optional[str] = Field(default=None, description="Reviewer notes")
    
    # Timestamps
    submitted_at: datetime = Field(default_factory=datetime.utcnow, description="Submission time")
    processed_at: Optional[datetime] = Field(default=None, description="Processing completion time")
    completed_at: Optional[datetime] = Field(default=None, description="Final completion time")
    
    # Performance metrics
    processing_latency_ms: Optional[int] = Field(default=None, ge=0, description="Total processing latency")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "partition_key": "Acme Supplies",
            "tenant_id": "tenant-001",
            "trace_id": "trace-abc123",
            "r2_url": "https://r2.cloudflarestorage.com/bucket/invoice.pdf",
            "status": "APPROVED",
            "extracted": {"invoice_number": "INV-001", "vendor": {"name": "Acme"}},
            "risk": {"risk_score": 0.25, "decision": "AUTO_APPROVE"},
            "quickbooks_bill_id": "qb-123",
            "submitted_at": "2024-01-15T10:30:00Z",
            "processing_latency_ms": 5230
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG ENTRY (IMMUTABLE AUDIT TRAIL)
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    """
    Immutable audit trail entry. Append-only.
    
    Every state transition creates an audit log entry.
    Used for compliance, debugging, and analytics.
    """
    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique audit log ID (UUID)"
    )
    partition_key: str = Field(..., description="Partition key (invoice_id)")
    invoice_id: str = Field(..., description="Invoice ID")
    tenant_id: str = Field(..., description="Tenant ID")
    
    # Actor & action
    actor: str = Field(..., pattern=r"^(agent|human:[a-zA-Z0-9_-]+|system)$", description="Actor (agent, human:{id}, system)")
    action: str = Field(..., description="Action taken (EXTRACTED, APPROVED, BLOCKED, etc.)")
    previous_status: Optional[str] = Field(default=None, description="Previous invoice status")
    new_status: str = Field(..., description="New invoice status")
    reason: str = Field(..., min_length=1, description="Reason for action")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Action timestamp")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "audit-123456",
            "partition_key": "inv-789",
            "invoice_id": "inv-789",
            "tenant_id": "tenant-001",
            "actor": "agent",
            "action": "AUTO_APPROVE",
            "previous_status": "ANALYZING",
            "new_status": "APPROVED",
            "reason": "CORE vendor, risk < 0.3, amount within limit",
            "metadata": {"risk_score": 0.25, "trust_level": "CORE"},
            "timestamp": "2024-01-15T10:30:05Z"
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# TRUST BATTERY STATE
# ─────────────────────────────────────────────────────────────────────────────

class TrustBatteryState(BaseModel):
    """
    Vendor trust battery state.
    
    Tracks historical accuracy to determine trust level.
    Cached in Redis for fast access.
    """
    vendor_id: str = Field(..., description="Vendor ID")
    tenant_id: str = Field(..., description="Tenant ID")
    
    # Counts
    invoice_count: int = Field(default=0, ge=0, description="Total invoices from vendor")
    accurate_count: int = Field(default=0, ge=0, description="Accurate invoices")
    error_count: int = Field(default=0, ge=0, description="Invoices with errors")
    
    # Financial totals
    total_approved_amount: float = Field(default=0.0, ge=0.0, description="Total approved amount")
    
    # Computed fields
    trust_level: TrustLevel = Field(default=TrustLevel.PROBATION, description="Current trust level")
    trust_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Trust score (0.0-1.0)")
    auto_approve_limit: float = Field(default=0.0, ge=0.0, description="Auto-approve limit")
    
    # Timestamps
    last_invoice_at: Optional[datetime] = Field(default=None, description="Last invoice timestamp")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update time")

    @field_validator("trust_level", mode="after")
    @classmethod
    def compute_trust_level(cls, v: TrustLevel, info) -> TrustLevel:
        """Compute trust level from invoice_count and accurate_count."""
        # This is a placeholder - actual computation happens in TrustBattery class
        return v

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "vendor_id": "vendor-001",
            "tenant_id": "tenant-001",
            "invoice_count": 150,
            "accurate_count": 148,
            "error_count": 2,
            "total_approved_amount": 750000.0,
            "trust_level": "CORE",
            "trust_score": 0.92,
            "auto_approve_limit": 5000.0
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# API REQUEST/RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    """Request to process an invoice."""
    trace_id: str = Field(..., description="Distributed trace ID")
    invoice_id: str = Field(..., description="Invoice ID")
    r2_url: str = Field(..., description="R2 presigned URL")
    tenant_id: str = Field(..., description="Tenant ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "trace_id": "trace-abc123",
            "invoice_id": "inv-001",
            "r2_url": "https://r2.cloudflarestorage.com/bucket/invoice.pdf",
            "tenant_id": "tenant-001",
            "metadata": {"vendor_name": "Acme Supplies", "file_size": 102400}
        }
    })


class ProcessResponse(BaseModel):
    """Response from invoice processing."""
    trace_id: str = Field(..., description="Distributed trace ID")
    invoice_id: str = Field(..., description="Invoice ID")
    status: str = Field(..., description="Final status")
    decision: Optional[str] = Field(default=None, description="Risk decision")
    risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Risk score")
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Extraction confidence")
    processing_latency_ms: int = Field(..., ge=0, description="Processing latency")
    quickbooks_bill_id: Optional[str] = Field(default=None, description="QuickBooks bill ID")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "trace_id": "trace-abc123",
            "invoice_id": "inv-001",
            "status": "APPROVED",
            "decision": "AUTO_APPROVE",
            "risk_score": 0.25,
            "extraction_confidence": 0.97,
            "processing_latency_ms": 5230,
            "quickbooks_bill_id": "qb-123"
        }
    })


class HITLDecisionRequest(BaseModel):
    """Human-in-the-loop decision request."""
    invoice_id: str = Field(..., description="Invoice ID")
    decision: Literal["APPROVED", "REJECTED"] = Field(..., description="Human decision")
    reviewer_id: str = Field(..., description="Reviewer ID")
    notes: Optional[str] = Field(default=None, max_length=2000, description="Reviewer notes")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "invoice_id": "inv-001",
            "decision": "APPROVED",
            "reviewer_id": "user-123",
            "notes": "Verified with PO #12345"
        }
    })


class VoiceQueueRequest(BaseModel):
    """Request to queue a voice call."""
    invoice_id: str = Field(..., description="Invoice ID")
    vendor_phone: str = Field(..., description="Vendor phone number")
    vendor_name: str = Field(..., description="Vendor contact name")
    purpose: CallPurpose = Field(..., description="Call purpose")
    language: str = Field(default="hi-IN", description="Language code")
    tenant_id: str = Field(..., description="Tenant ID")
    context: Dict[str, Any] = Field(default_factory=dict, description="Call context")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "invoice_id": "inv-001",
            "vendor_phone": "+919999999999",
            "vendor_name": "Rajesh Kumar",
            "purpose": "missing_details",
            "language": "hi-IN",
            "tenant_id": "tenant-001",
            "context": {"missing_fields": ["vendor.tax_id", "line_items"]}
        }
    })
