"""
AP Workflow Pydantic Models.

Defines the LangGraph state machine state and step result schemas for the
Accounts Payable invoice processing pipeline.

All schemas are strict Pydantic v2 with validation.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class InvoiceStatus(str, Enum):
    """Status of an invoice in the AP workflow."""

    NEW = "new"
    INGESTED = "ingested"
    EXTRACTED = "extracted"
    ENRICHED = "enriched"
    FRAUD_CHECKED = "fraud_checked"
    DUPLICATE_CHECKED = "duplicate_checked"
    MATCHED = "matched"
    CODED = "coded"
    DECIDED = "decided"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    ERROR = "error"


class DecisionType(str, Enum):
    """Final decision from the workflow."""

    AUTO_APPROVE = "AUTO_APPROVE"
    HITL_REQUIRED = "HITL_REQUIRED"
    REJECT = "REJECT"


class TaskType(str, Enum):
    """Types of human-in-the-loop tasks."""

    TASK_SECURITY_REVIEW = "TASK_SECURITY_REVIEW"
    TASK_DUPLICATE_REVIEW = "TASK_DUPLICATE_REVIEW"
    TASK_PO_OWNER_APPROVAL = "TASK_PO_OWNER_APPROVAL"
    TASK_VENDOR_ONBOARDING = "TASK_VENDOR_ONBOARDING"


class TaskStatus(str, Enum):
    """Status of a human task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class NodeName(str, Enum):
    """Names of nodes in the AP workflow graph."""

    INGEST = "ingest"
    EXTRACT = "extract"
    ENRICH_CONTEXT = "enrich_context"
    FRAUD_GATE = "fraud_gate"
    DUPLICATE_CHECK = "duplicate_check"
    THREE_WAY_MATCH = "three_way_match"
    GL_CODING = "gl_coding"
    DECISION = "decision"
    DRAFT_RESOLUTION = "draft_resolution"
    EXECUTE = "execute"
    AUDIT_LOG = "audit_log"


# ─────────────────────────────────────────────────────────────────────────────
# Step Results (Outputs from each node)
# ─────────────────────────────────────────────────────────────────────────────


class StepResult(BaseModel):
    """Base class for all node step results."""

    node_name: NodeName
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    status: str = "success"  # "success" | "error" | "skipped"


class IngestResult(StepResult):
    """Result from the INGEST node."""

    idempotency_key: str
    is_duplicate: bool = False
    existing_invoice_id: Optional[UUID] = None


class ExtractResult(StepResult):
    """Result from the EXTRACT node."""

    extracted_vendor_name: str
    extracted_invoice_number: str
    extracted_total: Decimal
    extracted_currency: str
    extracted_date: date
    extracted_line_items: list[dict[str, Any]]
    raw_text: Optional[str] = None
    extraction_method: str = "unknown"  # "azure_di" | "fixture" | "ollama" | "sarvam"


class EnrichContextResult(StepResult):
    """Result from the ENRICH_CONTEXT node."""

    vendor_id: Optional[UUID] = None
    vendor_name: str
    vendor_trust_level: int = Field(default=0, ge=0, le=100)
    verified_bank_hash: Optional[str] = None
    past_invoice_count: int = 0
    open_po_count: int = 0
    is_new_vendor: bool = True


class FraudGateResult(StepResult):
    """Result from the FRAUD_GATE node."""

    is_safe: bool = True
    bank_detail_changed: bool = False
    vendor_mismatch: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    requires_security_review: bool = False


class DuplicateCheckResult(StepResult):
    """Result from the DUPLICATE_CHECK node."""

    is_duplicate: bool = False
    duplicate_invoice_ids: list[UUID] = Field(default_factory=list)
    match_type: Optional[str] = None  # "exact" | "fuzzy" | None
    similarity_score: Optional[float] = None
    requires_duplicate_review: bool = False


class ThreeWayMatchResult(StepResult):
    """Result from the THREE_WAY_MATCH node."""

    po_match_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    po_number: Optional[str] = None
    po_total: Optional[Decimal] = None
    invoice_total: Optional[Decimal] = None
    variance: Optional[Decimal] = None
    variance_percentage: Optional[float] = None
    line_item_matches: list[dict[str, Any]] = Field(default_factory=list)
    requires_po_approval: bool = False
    tolerance_percentage: float = Field(default=5.0)

    @property
    def is_within_tolerance(self) -> bool:
        """Check if variance is within tolerance."""
        if self.variance_percentage is None:
            return False
        return abs(self.variance_percentage) <= self.tolerance_percentage


class GLCodingResult(StepResult):
    """Result from the GL_CODING node."""

    gl_code: Optional[str] = None
    gl_description: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "memory"  # "memory" | "llm_fallback" | "default"
    historical_matches: list[dict[str, Any]] = Field(default_factory=list)


class DecisionResult(StepResult):
    """Result from the DECISION node."""

    decision: DecisionType
    reason_codes: list[str] = Field(default_factory=list)
    auto_approve_conditions_met: list[str] = Field(default_factory=list)
    hitl_reasons: list[str] = Field(default_factory=list)
    reject_reasons: list[str] = Field(default_factory=list)


class DraftResolutionResult(StepResult):
    """Result from the DRAFT_RESOLUTION node."""

    task_type: TaskType
    task_id: UUID = Field(default_factory=uuid4)
    resolution_packet: dict[str, Any] = Field(default_factory=dict)
    draft_message: str = ""
    assigned_to: Optional[str] = None


class ExecuteResult(StepResult):
    """Result from the EXECUTE node."""

    success: bool = False
    quickbooks_bill_id: Optional[str] = None
    error_message: Optional[str] = None


class AuditLogEntry(BaseModel):
    """Entry written to the audit log."""

    id: UUID = Field(default_factory=uuid4)
    trace_id: str
    node_name: NodeName
    input_hash: str  # SHA256 of node input
    output_hash: str  # SHA256 of node output
    status: str  # "success" | "error" | "skipped"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    details: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Main Workflow State
# ─────────────────────────────────────────────────────────────────────────────


class InvoiceLineItem(BaseModel):
    """A single line item from an invoice."""

    line_number: int = Field(..., ge=1)
    description: str
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    amount: Decimal = Field(..., description="Line total")
    tax_code: Optional[str] = None
    gl_code: Optional[str] = None


class ExtractedInvoice(BaseModel):
    """Complete extracted invoice data."""

    vendor_name: str
    vendor_address: Optional[str] = None
    vendor_tax_id: Optional[str] = None
    vendor_bank_account: Optional[str] = None
    vendor_ifsc: Optional[str] = None
    vendor_iban: Optional[str] = None

    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None

    subtotal: Decimal
    tax_amount: Decimal = Field(default=Decimal("0"))
    total_amount: Decimal
    currency: str = Field(default="USD")

    line_items: list[InvoiceLineItem] = Field(default_factory=list)

    po_number: Optional[str] = None
    payment_terms: Optional[str] = None

    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_method: str = "unknown"

    @field_validator("total_amount", mode="before")
    @classmethod
    def validate_total(cls, v: Any) -> Decimal:
        """Ensure total_amount is Decimal."""
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class APWorkflowState(BaseModel):
    """
    LangGraph state for the AP workflow.

    This is the central state that flows through all nodes in the graph.
    Each node reads from this state and produces a StepResult that's
    stored in the step_results dict.
    """

    # ── Identifiers ─────────────────────────────────────────────────────────
    trace_id: str = Field(..., description="Unique trace ID for this invoice")
    idempotency_key: str = Field(..., description="SHA256 hash for idempotency")

    # ── Invoice Data (populated progressively) ─────────────────────────────
    invoice_status: InvoiceStatus = Field(default=InvoiceStatus.NEW)
    r2_key: Optional[str] = None
    r2_presigned_url: Optional[str] = None

    # Extraction results
    extracted_invoice: Optional[ExtractedInvoice] = None

    # Context enrichment
    vendor_id: Optional[UUID] = None
    vendor_trust_level: int = Field(default=0, ge=0, le=100)
    verified_bank_hash: Optional[str] = None

    # Step results (one per node)
    ingest_result: Optional[IngestResult] = None
    extract_result: Optional[ExtractResult] = None
    enrich_result: Optional[EnrichContextResult] = None
    fraud_result: Optional[FraudGateResult] = None
    duplicate_result: Optional[DuplicateCheckResult] = None
    three_way_result: Optional[ThreeWayMatchResult] = None
    coding_result: Optional[GLCodingResult] = None
    decision_result: Optional[DecisionResult] = None
    draft_result: Optional[DraftResolutionResult] = None
    execute_result: Optional[ExecuteResult] = None

    # ── Decision ────────────────────────────────────────────────────────────
    final_decision: Optional[DecisionType] = None
    task_id: Optional[UUID] = None  # If HITL task was created

    # ── Metadata ───────────────────────────────────────────────────────────
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    # ── Hash Helpers ──────────────────────────────────────────────────────
    @classmethod
    def compute_idempotency_key(
        cls,
        vendor_id: Optional[str],
        invoice_number: str,
        total: Decimal,
        currency: str,
        invoice_date: date,
    ) -> str:
        """
        Compute idempotency key for invoice.

        Key = sha256(vendor_id + invoice_number + total + currency + invoice_date)
        """
        key_string = f"{vendor_id or ''}{invoice_number}{total}{currency}{invoice_date}"
        return sha256(key_string.encode()).hexdigest()

    @model_validator(mode="after")
    def validate_state(self) -> "APWorkflowState":
        """Validate state consistency."""
        # Ensure trace_id is set
        if not self.trace_id:
            raise ValueError("trace_id is required")

        # Ensure idempotency_key is set
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required")

        return self


# ─────────────────────────────────────────────────────────────────────────────
# Human Task Models
# ─────────────────────────────────────────────────────────────────────────────


class HumanTask(BaseModel):
    """A human-in-the-loop task for approval."""

    id: UUID = Field(default_factory=uuid4)
    trace_id: str
    task_type: TaskType
    payload_json: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    assigned_to: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    comments: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Database Models (for SQLAlchemy/asyncpg)
# ─────────────────────────────────────────────────────────────────────────────


class Vendor(BaseModel):
    """Vendor record from database."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    normalized_name: str = Field(description="Lowercase, stripped for matching")
    verified_bank_hash: Optional[str] = None
    trust_level: int = Field(default=50, ge=0, le=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Invoice(BaseModel):
    """Invoice record from database."""

    id: UUID = Field(default_factory=uuid4)
    trace_id: str
    vendor_id: Optional[UUID] = None
    vendor_name: str
    invoice_number: str
    total: Decimal
    currency: str
    invoice_date: date
    status: InvoiceStatus = Field(default=InvoiceStatus.NEW)
    idempotency_key: str
    extracted_data_json: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InvoiceLineItemDB(BaseModel):
    """Invoice line item from database."""

    id: UUID = Field(default_factory=uuid4)
    invoice_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    tax_code: Optional[str] = None
    gl_code: Optional[str] = None


class PurchaseOrder(BaseModel):
    """Purchase order record."""

    id: UUID = Field(default_factory=uuid4)
    po_number: str
    vendor_id: UUID
    total: Decimal
    currency: str
    status: str = Field(default="open")  # "open" | "closed" | "partial"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class POLineItem(BaseModel):
    """PO line item."""

    id: UUID = Field(default_factory=uuid4)
    po_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class Receipt(BaseModel):
    """Goods receipt record."""

    id: UUID = Field(default_factory=uuid4)
    po_id: UUID
    receipt_number: str
    received_date: date
    status: str = Field(default="received")
