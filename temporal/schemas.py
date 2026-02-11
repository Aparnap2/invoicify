"""Schemas for Temporal workflows."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """Line item in an invoice."""

    description: str
    quantity: Decimal = Field(default=1)
    unit_price: Decimal
    amount: Decimal


class InvoiceExtracted(BaseModel):
    """Extracted invoice data."""

    vendor_name: str
    invoice_number: str
    total_amount: Decimal
    currency: str = "USD"
    due_date: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class InvoiceInput(BaseModel):
    """Input to invoice processing workflow."""

    invoice_id: str
    vendor_name: str
    total_amount: float
    invoice_number: str
    due_date: Optional[str] = None
    currency: str = "USD"
    image_url: Optional[str] = None
    requires_approval: bool = False


class FinancialContext(BaseModel):
    """Company financial context for decision making."""

    current_cash: float
    monthly_burn_rate: float
    runway_days: float
    safety_buffer: float = 10000.0
    strategy_mode: str = "OPTIMIZE"  # SURVIVAL, GROWTH, OPTIMIZE
    payroll_date: Optional[str] = None
    payroll_amount: float = 0.0
    budgets: Dict[str, float] = Field(default_factory=dict)
    category_limits: Dict[str, float] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    """Result of invoice processing workflow."""

    invoice_id: str
    status: str
    anomaly_score: float
    analyst_confidence: float
    critic_risk_score: float
    approved: Optional[bool] = None
    approver_comments: Optional[str] = None
    processed_at: datetime = Field(default_factory=lambda: datetime.utcnow())
