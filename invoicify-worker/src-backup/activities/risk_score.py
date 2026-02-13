"""
Risk Score Activity
Calculates comprehensive risk score using River ML.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from temporalio import activity

from src.domain.models import InvoiceData, TrustBattery, RiskScore
from src.domain.risk_scorer import InvoiceRiskScorer

logger = logging.getLogger(__name__)

# Global risk scorer instance (maintains learned state)
_risk_scorer: InvoiceRiskScorer = None


def _get_risk_scorer() -> InvoiceRiskScorer:
    """Get or create global risk scorer instance."""
    global _risk_scorer
    if _risk_scorer is None:
        _risk_scorer = InvoiceRiskScorer()
        logger.info("🎯 Initialized InvoiceRiskScorer")
    return _risk_scorer


@activity.defn
async def calculate_risk_score(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity: Calculate comprehensive risk score for invoice.

    Args:
        params: Dict with 'invoice_data' and 'trust_battery'

    Returns:
        RiskScore as dictionary with breakdown
    """
    invoice_data = params["invoice_data"]
    trust_battery_data = params.get("trust_battery", {})

    logger.info(
        f"🎯 Calculating risk for invoice: {invoice_data.get('invoice_number')}"
    )

    # Convert to domain models
    invoice = _dict_to_invoice(invoice_data)
    trust_battery = (
        _dict_to_trust_battery(trust_battery_data) if trust_battery_data else None
    )

    # Get risk scorer
    scorer = _get_risk_scorer()

    # Calculate risk
    risk_score = scorer.score_invoice(
        invoice=invoice,
        trust_battery=trust_battery,
    )

    logger.info(
        f"⚠️  Risk score: {risk_score.overall_score:.2f} "
        f"({risk_score.recommended_action.value})"
    )

    return risk_score.to_dict()


def _dict_to_invoice(data: Dict) -> InvoiceData:
    """Convert dictionary to InvoiceData."""
    from src.domain.models import LineItem

    line_items = []
    for item_data in data.get("line_items", []):
        line_items.append(
            LineItem(
                description=item_data.get("description", ""),
                quantity=item_data.get("quantity", 1),
                unit_price=Decimal(str(item_data.get("unit_price", "0.00"))),
                total=Decimal(str(item_data.get("total", "0.00"))),
            )
        )

    return InvoiceData(
        invoice_id=data.get("invoice_id", ""),
        vendor_id=data.get("vendor_id", ""),
        vendor_name=data.get("vendor_name", "Unknown"),
        invoice_number=data.get("invoice_number", "INV-UNKNOWN"),
        issue_date=datetime.fromisoformat(
            data.get("issue_date", datetime.utcnow().isoformat())
        ),
        due_date=datetime.fromisoformat(
            data.get("due_date", datetime.utcnow().isoformat())
        ),
        total_amount=Decimal(str(data.get("total_amount", "0.00"))),
        currency=data.get("currency", "USD"),
        line_items=line_items,
        raw_markdown=data.get("raw_markdown", ""),
        confidence=data.get("confidence", 0.0),
    )


def _dict_to_trust_battery(data: Dict) -> TrustBattery:
    """Convert dictionary to TrustBattery."""
    from src.domain.models import TrustLevel

    return TrustBattery(
        vendor_id=data.get("vendor_id", ""),
        level=TrustLevel(data.get("level", 1)),
        successful_payments=data.get("successful_payments", 0),
        disputes=data.get("disputes", 0),
        total_invoices=data.get("total_invoices", 0),
        total_amount_paid=Decimal(str(data.get("total_amount_paid", "0.00"))),
        avg_invoice_amount=Decimal(str(data.get("avg_invoice_amount", "0.00"))),
        created_at=datetime.fromisoformat(
            data.get("created_at", datetime.utcnow().isoformat())
        ),
        updated_at=datetime.fromisoformat(
            data.get("updated_at", datetime.utcnow().isoformat())
        ),
        last_payment_at=datetime.fromisoformat(data.get("last_payment_at"))
        if data.get("last_payment_at")
        else None,
    )
