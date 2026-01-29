"""
Invoice Event Schemas for Redpanda/Kafka Consumer

Defines Pydantic schemas for invoice lifecycle events.
Published by Worker, consumed by AI Service.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class InvoiceState(str, Enum):
    """Invoice lifecycle states."""
    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    RISK_SCORED = "risk_scored"
    APPROVED = "approved"
    REJECTED = "rejected"
    SYNCED = "synced"


class RiskLevel(str, Enum):
    """Risk assessment levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SyncTarget(str, Enum):
    """External sync targets."""
    QUICKBOOKS = "quickbooks"
    SHEETS = "sheets"
    SLACK = "slack"


class InvoiceStatusEvent(BaseModel):
    """
    Main invoice status event schema.

    Single topic (invoice.status) with state in payload.
    Published after each invoice lifecycle transition.
    """
    invoice_id: str = Field(..., description="Unique invoice identifier")
    tenant_id: str = Field(..., description="Tenant/organization ID for multi-tenancy")
    state: InvoiceState = Field(..., description="Current lifecycle state")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    trace_id: str = Field(..., description="Trace ID for distributed tracing")
    vendor_id: Optional[str] = Field(None, description="Vendor ID if available")
    invoice_number: Optional[str] = Field(None, description="Invoice number for reference")
    total_amount: Optional[float] = Field(None, description="Total amount if available")
    currency: Optional[str] = Field(None, description="Currency code")
    risk_score: Optional[float] = Field(None, ge=0, le=1, description="Risk score (0-1) if risk_scored")
    risk_level: Optional[RiskLevel] = Field(None, description="Risk level if risk_scored")
    sync_target: Optional[SyncTarget] = Field(None, description="External sync target if synced")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "invoice_id": "inv-001",
                "tenant_id": "tenant-001",
                "state": "extracted",
                "timestamp": "2024-01-15T10:30:00Z",
                "trace_id": "trace-abc123",
                "vendor_id": "vendor-001",
                "invoice_number": "INV-001",
                "total_amount": 1500.00,
                "currency": "USD",
            }
        }


class InvoiceExtractedEvent(InvoiceStatusEvent):
    """Event published after successful invoice extraction."""
    line_items_count: Optional[int] = Field(None, description="Number of line items extracted")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="OCR confidence score")


class InvoiceRiskScoredEvent(InvoiceStatusEvent):
    """Event published after risk assessment."""
    risk_signals: list[str] = Field(default_factory=list, description="Risk signal descriptions")
    suggested_action: str = Field(..., description="Suggested action: approve, reject, hitl")
    runway_impact_days: Optional[int] = Field(None, description="Days of runway impact")


class InvoiceDecisionEvent(InvoiceStatusEvent):
    """Event published after approval/rejection decision."""
    decision: str = Field(..., description="Decision made: approved or rejected")
    decided_by: str = Field(default="system", description="Who made the decision")
    decision_reason: Optional[str] = Field(None, description="Reason for decision")


class InvoiceSyncedEvent(InvoiceStatusEvent):
    """Event published after external sync."""
    sync_target: SyncTarget = Field(..., description="Where the invoice was synced")
    external_id: Optional[str] = Field(None, description="External system ID")
    sync_status: str = Field(default="success", description="Sync status")


# ============================================================================
# Consumer Offset Tracking
# ============================================================================

class ConsumerOffset(BaseModel):
    """Track consumer offset for idempotent processing."""
    topic: str = "invoice.status"
    partition: int
    offset: int
    invoice_id: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
