"""Invoice data models using Pydantic v2."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class InvoiceStatus(str, Enum):
    """Status of an invoice in the processing pipeline."""

    NEW = "new"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    VALIDATING = "validating"
    MATCHED = "matched"
    EXCEPTION = "exception"
    APPROVAL_PENDING = "approval_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    ARCHIVED = "archived"


class ApprovalStatus(str, Enum):
    """Status of an approval action."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    """Risk level for invoice processing."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LineItem(BaseModel):
    """A single line item from an invoice."""

    line_number: int = Field(..., ge=1, description="Line item number")
    description: str = Field(..., min_length=1, description="Item description")
    quantity: Decimal = Field(..., gt=0, description="Quantity")
    unit_price: Decimal = Field(..., ge=0, description="Unit price")
    unit_of_measure: str = Field(default="EA", description="Unit of measure")
    amount: Decimal = Field(..., description="Line total amount")
    tax_code: Optional[str] = Field(default=None, description="Tax code")
    gl_code: Optional[str] = Field(default=None, description="General Ledger code")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Any) -> Decimal:
        """Ensure amount is Decimal."""
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class ExtractedConfidence(BaseModel):
    """Confidence scores for extracted fields."""

    field_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    extraction_method: str = Field(default="llm", description="How field was extracted")


class InvoiceExtraction(BaseModel):
    """Complete extraction result from invoice processing."""

    confidence_scores: list[ExtractedConfidence] = Field(
        default_factory=list, description="Per-field confidence"
    )
    overall_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Overall extraction confidence"
    )
    extraction_notes: list[str] = Field(
        default_factory=list, description="Notes about extraction"
    )
    requires_review: bool = Field(
        default=False, description="Whether this extraction needs human review"
    )


class InvoiceBase(BaseModel):
    """Base invoice model with common fields."""

    vendor_name: str = Field(..., min_length=1, description="Vendor/Supplier name")
    vendor_address: Optional[str] = Field(default=None, description="Vendor address")
    vendor_tax_id: Optional[str] = Field(default=None, description="Vendor tax ID")

    invoice_number: str = Field(..., min_length=1, description="Invoice number")
    invoice_date: date = Field(..., description="Invoice date")
    due_date: date = Field(..., description="Payment due date")

    currency: str = Field(default="USD", min_length=3, max_length=3, description="Currency code")

    subtotal: Decimal = Field(..., description="Subtotal before tax")
    tax_amount: Decimal = Field(default=Decimal("0"), description="Tax amount")
    total_amount: Decimal = Field(..., description="Total amount due")

    line_items: list[LineItem] = Field(
        default_factory=list, description="Invoice line items"
    )

    payment_terms: Optional[str] = Field(default=None, description="Payment terms")
    po_number: Optional[str] = Field(default=None, description="Purchase order number")

    notes: Optional[str] = Field(default=None, description="Additional notes")


class InvoiceCreate(InvoiceBase):
    """Model for creating a new invoice."""

    source_file_name: str = Field(..., description="Original file name")
    source_file_type: str = Field(..., description="File type (pdf, png, jpg)")


class InvoiceExtracted(InvoiceBase, InvoiceExtraction):
    """Complete extracted invoice model."""

    id: UUID = Field(default_factory=uuid4, description="Invoice ID")
    status: InvoiceStatus = Field(default=InvoiceStatus.NEW)

    # AI-specific fields
    extracted_at: Optional[str] = Field(default=None, description="Extraction timestamp")
    raw_text: Optional[str] = Field(default=None, description="Raw extracted text")

    class Config:
        from_attributes = True


class POValidationResult(BaseModel):
    """Result of PO matching validation."""

    is_valid: bool
    po_number: Optional[str] = None
    po_amount: Optional[Decimal] = None
    invoice_amount: Optional[Decimal] = None
    variance: Optional[Decimal] = None
    variance_percentage: Optional[float] = None
    tolerance_percentage: float = Field(default=5.0)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_within_tolerance(self) -> bool:
        """Check if variance is within tolerance."""
        if self.variance_percentage is None:
            return False
        return abs(self.variance_percentage) <= self.tolerance_percentage


class ApprovalRequest(BaseModel):
    """Request for human approval of an invoice."""

    invoice_id: UUID
    reason: str = Field(..., description="Reason for approval request")
    risk_level: RiskLevel
    suggested_action: str = Field(..., description="Suggested action")
    extracted_data: InvoiceExtracted


class ApprovalAction(BaseModel):
    """Action taken on an approval request."""

    invoice_id: UUID
    decision: ApprovalStatus = Field(..., description="Approve or reject")
    comments: Optional[str] = Field(default=None, description="Comments")
    approver_id: str = Field(..., description="ID of approver")
    approver_email: str = Field(..., description="Email of approver")


class DuplicateCheck(BaseModel):
    """Duplicate invoice check result."""

    is_duplicate: bool
    potential_duplicates: list[UUID] = Field(default_factory=list)
    match_fields: dict[str, Any] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    """Complete result of invoice processing workflow."""

    invoice_id: UUID
    status: InvoiceStatus
    extraction: InvoiceExtracted
    po_validation: Optional[POValidationResult] = None
    duplicate_check: Optional[DuplicateCheck] = None
    requires_approval: bool
    approval_request: Optional[ApprovalRequest] = None
    error_message: Optional[str] = None
