"""
Domain Models for Invoice Processing
Core data structures used across the application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import Dict, List, Optional, Any


class InvoiceStatus(Enum):
    """Invoice processing states."""

    INGESTED = "ingested"
    EXTRACTING = "extracting"
    RISK_CHECKING = "risk_checking"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAYING = "paying"
    PAID = "paid"
    FAILED = "failed"


class Decision(Enum):
    """Processing decisions."""

    APPROVE = "approve"
    REVIEW = "review"
    REJECT = "reject"


class TrustLevel(Enum):
    """Vendor trust levels (1-5)."""

    NEW = 1
    LIMITED = 2
    STANDARD = 3
    TRUSTED = 4
    VERIFIED = 5


class TrustOutcome(Enum):
    """Outcomes that affect trust battery."""

    PAYMENT_SUCCESS = auto()
    PAYMENT_FAILED = auto()
    DISPUTE_RESOLVED = auto()
    DISPUTE_UNRESOLVED = auto()
    MANUAL_REVIEW_APPROVED = auto()
    MANUAL_REVIEW_REJECTED = auto()


@dataclass
class LineItem:
    """Invoice line item."""

    description: str
    quantity: int
    unit_price: Decimal
    total: Decimal


@dataclass
class InvoiceData:
    """Structured invoice data extracted from documents."""

    invoice_id: str
    vendor_id: str
    vendor_name: str
    invoice_number: str
    issue_date: datetime
    due_date: datetime
    total_amount: Decimal
    currency: str = "USD"
    line_items: List[LineItem] = field(default_factory=list)
    raw_markdown: str = ""  # Docling Markdown output
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "invoice_id": self.invoice_id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "invoice_number": self.invoice_number,
            "issue_date": self.issue_date.isoformat(),
            "due_date": self.due_date.isoformat(),
            "total_amount": str(self.total_amount),
            "currency": self.currency,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "total": str(item.total),
                }
                for item in self.line_items
            ],
            "confidence": self.confidence,
        }


@dataclass
class RiskBreakdown:
    """Breakdown of risk factors."""

    amount_anomaly_score: float  # 0.0-1.0
    pattern_anomaly_score: float  # 0.0-1.0
    vendor_trust_penalty: float  # 0.0-1.0
    time_based_risk: float  # 0.0-1.0
    duplicate_risk: float  # 0.0-1.0

    @property
    def overall_score(self) -> float:
        """Calculate weighted overall risk score."""
        weights = {
            "amount": 0.35,
            "pattern": 0.25,
            "trust": 0.20,
            "time": 0.10,
            "duplicate": 0.10,
        }
        score = (
            self.amount_anomaly_score * weights["amount"]
            + self.pattern_anomaly_score * weights["pattern"]
            + self.vendor_trust_penalty * weights["trust"]
            + self.time_based_risk * weights["time"]
            + self.duplicate_risk * weights["duplicate"]
        )
        return min(1.0, max(0.0, score))


@dataclass
class RiskScore:
    """Risk assessment result."""

    overall_score: float  # 0.0-1.0
    breakdown: RiskBreakdown
    reasons: List[str] = field(default_factory=list)
    recommended_action: Decision = Decision.REVIEW

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "overall_score": self.overall_score,
            "breakdown": {
                "amount_anomaly_score": self.breakdown.amount_anomaly_score,
                "pattern_anomaly_score": self.breakdown.pattern_anomaly_score,
                "vendor_trust_penalty": self.breakdown.vendor_trust_penalty,
                "time_based_risk": self.breakdown.time_based_risk,
                "duplicate_risk": self.breakdown.duplicate_risk,
            },
            "reasons": self.reasons,
            "recommended_action": self.recommended_action.value,
        }


@dataclass
class TrustBattery:
    """Vendor trust battery tracking."""

    vendor_id: str
    level: TrustLevel = TrustLevel.NEW
    successful_payments: int = 0
    disputes: int = 0
    total_invoices: int = 0
    total_amount_paid: Decimal = field(default_factory=lambda: Decimal("0.00"))
    avg_invoice_amount: Decimal = field(default_factory=lambda: Decimal("0.00"))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_payment_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "vendor_id": self.vendor_id,
            "level": self.level.value,
            "level_name": self.level.name,
            "successful_payments": self.successful_payments,
            "disputes": self.disputes,
            "total_invoices": self.total_invoices,
            "total_amount_paid": str(self.total_amount_paid),
            "avg_invoice_amount": str(self.avg_invoice_amount),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class InvoiceResult:
    """Result of invoice processing workflow."""

    invoice_id: str
    status: InvoiceStatus
    risk_score: RiskScore
    decision: Decision
    vendor_trust_level: TrustLevel
    payment_amount: Optional[Decimal] = None
    payment_reference: Optional[str] = None
    processed_at: datetime = field(default_factory=datetime.utcnow)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "invoice_id": self.invoice_id,
            "status": self.status.value,
            "risk_score": self.risk_score.to_dict(),
            "decision": self.decision.value,
            "vendor_trust_level": self.vendor_trust_level.name,
            "payment_amount": str(self.payment_amount) if self.payment_amount else None,
            "payment_reference": self.payment_reference,
            "processed_at": self.processed_at.isoformat(),
            "errors": self.errors,
        }
