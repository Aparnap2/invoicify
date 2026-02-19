"""Type definitions and schemas for invoicify-agent."""

from typing import TypedDict, List, Optional, Dict, Any, Annotated
from datetime import datetime
import operator


class InvoiceState(TypedDict, total=False):
    """State for invoice processing."""
    trace_id: str
    invoice_id: str
    r2_url: str
    tenant_id: str
    metadata: Dict[str, Any]
    
    # Processing state
    status: str
    current_stage: str
    
    # Extracted data
    vendor_name: Optional[str]
    invoice_number: Optional[str]
    total_amount: Optional[float]
    line_items: List[Dict[str, Any]]
    extraction_confidence: Optional[float]
    
    # Validation
    math_valid: Optional[bool]
    is_duplicate: Optional[bool]
    
    # Risk analysis
    risk_score: Optional[float]
    trust_level: Optional[str]
    decision: Optional[str]
    
    # Execution
    quickbooks_bill_id: Optional[str]
    
    # Errors
    error_message: Optional[str]
    
    # Audit
    audit_log: Annotated[List[str], operator.add]
    
    # Performance
    stage_latencies: Dict[str, int]
    started_at: datetime
    completed_at: Optional[datetime]


__all__ = ["InvoiceState"]
