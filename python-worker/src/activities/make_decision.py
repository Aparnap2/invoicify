"""
Make Decision Activity
Determines whether to APPROVE, REVIEW, or REJECT an invoice.
"""

import logging
from decimal import Decimal
from typing import Dict, Any

from temporalio import activity

from src.domain.models import Decision, TrustLevel, TrustBattery

logger = logging.getLogger(__name__)


@activity.defn
async def make_invoice_decision(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity: Make decision on invoice based on risk and trust.

    Args:
        params: Dict with 'invoice_data', 'risk_score', 'trust_battery'

    Returns:
        Dict with 'decision' and 'reason'
    """
    invoice_data = params["invoice_data"]
    risk_score = params["risk_score"]
    trust_battery_data = params.get("trust_battery", {})

    amount = Decimal(str(invoice_data.get("total_amount", "0.00")))
    trust_level = TrustLevel(trust_battery_data.get("level", 1))

    logger.info(
        f"🤖 Making decision: amount=${amount}, "
        f"risk={risk_score['overall_score']:.2f}, "
        f"trust={trust_level.name}"
    )

    # Decision logic
    decision, reason = _evaluate_decision(
        amount=amount,
        risk_score=risk_score,
        trust_level=trust_level,
    )

    logger.info(f"🤖 Decision: {decision.value} - {reason}")

    return {
        "decision": decision.value,
        "reason": reason,
    }


def _evaluate_decision(
    amount: Decimal,
    risk_score: Dict[str, Any],
    trust_level: TrustLevel,
) -> tuple:
    """
    Evaluate decision based on business rules.

    Returns:
        (Decision, reason)
    """
    overall_score = risk_score.get("overall_score", 0.5)
    breakdown = risk_score.get("breakdown", {})

    # Auto-approval limits by trust level
    AUTO_APPROVAL_LIMITS = {
        TrustLevel.NEW: Decimal("0.00"),
        TrustLevel.LIMITED: Decimal("500.00"),
        TrustLevel.STANDARD: Decimal("2000.00"),
        TrustLevel.TRUSTED: Decimal("5000.00"),
        TrustLevel.VERIFIED: Decimal("20000.00"),
    }

    # Check 1: High risk score (>0.7) → Always review
    if overall_score > 0.7:
        return (
            Decision.REVIEW,
            f"High risk score ({overall_score:.2f}) requires manual review",
        )

    # Check 2: Critical risk factors → Reject
    if breakdown.get("duplicate_risk", 0) > 0.8:
        return (Decision.REJECT, "Duplicate invoice detected")

    # Check 3: Trust level and amount
    auto_approve_limit = AUTO_APPROVAL_LIMITS.get(trust_level, Decimal("0.00"))

    if amount > auto_approve_limit:
        return (
            Decision.REVIEW,
            f"Amount ${amount} exceeds auto-approval limit (${auto_approve_limit}) "
            f"for {trust_level.name} vendors",
        )

    # Check 4: New vendor without history → Review
    if trust_level == TrustLevel.NEW:
        return (Decision.REVIEW, "New vendor requires manual review for first invoice")

    # Check 5: Low risk + within limits → Approve
    if overall_score < 0.3:
        return (
            Decision.APPROVE,
            f"Low risk ({overall_score:.2f}) and within auto-approval limits",
        )

    # Default: Review
    return (
        Decision.REVIEW,
        f"Moderate risk score ({overall_score:.2f}) requires review",
    )
