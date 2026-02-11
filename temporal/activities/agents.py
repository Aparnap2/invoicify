"""Agent activities for Analyst and Critic nodes."""

import logging
import os
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from temporal.schemas import InvoiceExtracted, FinancialContext

logger = logging.getLogger(__name__)


class Anomaly(BaseModel):
    """Detected anomaly in invoice data."""

    type: str
    severity: str  # "low", "medium", "high"
    description: str
    amount_deviation: Optional[float] = None


class AnalystProposal(BaseModel):
    """Analyst's proposal for invoice action."""

    proposed_action: str  # "AUTO_APPROVE", "HITL_REQUIRED", "DELAY_PAYMENT", "REJECT"
    confidence: float
    anomalies: List[Anomaly] = []
    vendor_patterns: List[str] = []
    reasoning: List[str] = []
    suggested_amount: Optional[float] = None
    suggested_due_date: Optional[str] = None


async def analyst_evaluate(invoice_data: dict) -> AnalystProposal:
    """
    Analyst node: Pattern detection and proposal generation.

    Args:
        invoice_data: Extracted invoice data

    Returns:
        Analyst proposal with action recommendation
    """
    logger.info(f"Analyst evaluating invoice: {invoice_data.get('invoice_number')}")

    try:
        # Get vendor history from Neo4j
        vendor_history = await _get_vendor_history(invoice_data.get("vendor_name"))

        # Detect anomalies
        anomalies = _detect_anomalies(
            Decimal(str(invoice_data.get("total_amount", 0))), vendor_history
        )

        # Generate proposal
        proposal = _generate_proposal(invoice_data, vendor_history, anomalies)

        logger.info(
            f"Analyst proposal for {invoice_data.get('vendor_name')}: "
            f"{proposal.proposed_action} (confidence: {proposal.confidence:.2%})"
        )

        return proposal

    except Exception as e:
        logger.error(f"Error in analyst evaluation: {e}")
        # Return safe default
        return AnalystProposal(
            proposed_action="HITL_REQUIRED",
            confidence=0.5,
            anomalies=[],
            reasoning=[f"Error during analysis: {str(e)}"],
        )


async def _get_vendor_history(vendor_name: str) -> List[dict]:
    """Get vendor invoice history from Neo4j."""
    try:
        # Import here to avoid dependency issues in tests
        from temporal.infrastructure.neo4j import get_neo4j_client

        client = get_neo4j_client()
        invoices = await client.get_invoices_by_vendor(vendor_name)

        return [
            {"amount": float(i.amount), "status": i.status}
            for i in invoices[-10:]  # Last 10 invoices
        ]
    except Exception as e:
        logger.warning(f"Could not fetch vendor history for {vendor_name}: {e}")
        return []


def _detect_anomalies(amount: Decimal, vendor_history: List[dict]) -> List[Anomaly]:
    """Detect anomalies in invoice amount compared to vendor history."""
    anomalies = []

    if not vendor_history:
        anomalies.append(
            Anomaly(
                type="NEW_VENDOR",
                severity="medium",
                description="First invoice from this vendor - no historical data",
            )
        )
        return anomalies

    # Calculate statistics
    amounts = [h["amount"] for h in vendor_history if h["amount"] > 0]
    if not amounts:
        return anomalies

    avg_amount = sum(amounts) / len(amounts)
    max_amount = max(amounts)
    current_amount = float(amount)

    # Check for amount deviation
    if avg_amount > 0:
        deviation = (current_amount - avg_amount) / avg_amount

        if deviation > 1.5:  # More than 1.5x average
            anomaly_type = "AMOUNT_SPIKE" if deviation > 2.0 else "AMOUNT_DEVIATION"
            severity = "high" if deviation > 2.0 else "medium"
            anomalies.append(
                Anomaly(
                    type=anomaly_type,
                    severity=severity,
                    description=f"Amount ${current_amount:.2f} is {deviation:.1f}x the average ${avg_amount:.2f}",
                    amount_deviation=deviation,
                )
            )

    # Check for unusually high single invoice
    if current_amount > max_amount * 1.5:
        anomalies.append(
            Anomaly(
                type="UNUSUAL_HIGH",
                severity="high",
                description=f"Highest invoice ever from this vendor (previous max: ${max_amount:.2f})",
            )
        )

    return anomalies


def _generate_proposal(
    invoice_data: dict, vendor_history: List[dict], anomalies: List[Anomaly]
) -> AnalystProposal:
    """Generate analyst proposal based on analysis."""
    reasoning = []
    proposed_action = "AUTO_APPROVE"
    base_confidence = invoice_data.get("overall_confidence", 0.8)

    # High severity anomalies always require HITL
    high_severity = [a for a in anomalies if a.severity == "high"]
    if high_severity:
        proposed_action = "HITL_REQUIRED"
        reasoning.append(f"High severity anomaly: {high_severity[0].type}")

    # Medium severity reduces confidence (even if high severity exists)
    medium_severity = [a for a in anomalies if a.severity == "medium"]
    if medium_severity:
        base_confidence *= 0.7
        reasoning.append(f"Medium severity anomaly: {medium_severity[0].type}")

    # New vendor check
    if not vendor_history:
        proposed_action = "HITL_REQUIRED"
        reasoning.append("New vendor - requires human review for first invoice")

    # High amount threshold
    if invoice_data.get("total_amount", 0) > 10000:
        proposed_action = "HITL_REQUIRED"
        reasoning.append(
            f"High value invoice (${invoice_data['total_amount']}) requires approval"
        )

    # Build final reasoning
    reasoning.insert(
        0,
        f"Invoice ${invoice_data.get('total_amount')} from {invoice_data.get('vendor_name')} analyzed",
    )
    if anomalies:
        reasoning.append(f"Found {len(anomalies)} anomaly/anomalies")
    else:
        reasoning.append("No anomalies detected in amount or pattern")

    reasoning.append(f"Base confidence: {base_confidence:.2%}")

    return AnalystProposal(
        proposed_action=proposed_action,
        confidence=base_confidence,
        anomalies=anomalies,
        vendor_patterns=[],
        reasoning=reasoning,
        suggested_amount=float(invoice_data.get("total_amount", 0)),
        suggested_due_date=invoice_data.get("due_date"),
    )


async def critic_review(invoice_data: dict, analyst_proposal: AnalystProposal) -> dict:
    """
    Critic node: Safety checks using Priority Matrix.

    Priority Order:
    1. RUNWAY - Does paying now endanger cash reserves?
    2. STRATEGY - Does this align with strategy mode?
    3. CONTRACT - Are payment terms being violated?
    4. TRUST - What's the vendor's trust level?
    5. BUDGET - Is this within category limits?

    Args:
        invoice_data: Extracted invoice data
        analyst_proposal: Proposal from analyst

    Returns:
        Critic review with safety signals
    """
    logger.info(f"Critic reviewing invoice: {invoice_data.get('invoice_number')}")

    # Get financial context from environment/config
    financial_context = _get_financial_context()
    
    # Get vendor trust level (default to 1 for new vendors)
    trust_level = invoice_data.get("trust_level", 1)
    trust_threshold = _get_trust_threshold(trust_level)

    signals = []
    reasoning = []
    blocked = False
    block_reason = None
    risk_score = 0.0

    # 1. RUNWAY CHECK
    runway_signal = _check_runway(
        Decimal(str(invoice_data.get("total_amount", 0))),
        financial_context
    )
    signals.append(runway_signal)
    risk_score += runway_signal.get("score_contribution", 0.0)
    
    if runway_signal.get("severity") == "CRITICAL":
        blocked = True
        block_reason = runway_signal.get("message")
    reasoning.append(f"RUNWAY: {runway_signal.get('message')}")

    # 2. STRATEGY CHECK
    strategy_signal = _check_strategy(
        Decimal(str(invoice_data.get("total_amount", 0))),
        financial_context
    )
    signals.append(strategy_signal)
    risk_score += strategy_signal.get("score_contribution", 0.0)
    
    if strategy_signal.get("severity") == "CRITICAL" and not blocked:
        blocked = True
        block_reason = strategy_signal.get("message")
    reasoning.append(f"STRATEGY: {strategy_signal.get('message')}")

    # 3. CONTRACT CHECK
    contract_signal = _check_contract(
        invoice_data.get("due_date"),
        financial_context
    )
    signals.append(contract_signal)
    risk_score += contract_signal.get("score_contribution", 0.0)
    reasoning.append(f"CONTRACT: {contract_signal.get('message')}")

    # 4. TRUST CHECK
    trust_signal = _check_trust(
        Decimal(str(invoice_data.get("total_amount", 0))),
        trust_level,
        trust_threshold
    )
    signals.append(trust_signal)
    risk_score += trust_signal.get("score_contribution", 0.0)
    reasoning.append(f"TRUST: {trust_signal.get('message')}")

    # 5. BUDGET CHECK
    vendor_name = invoice_data.get("vendor_name", "").lower()
    category = _categorize_vendor(vendor_name)
    
    budget_signal = _check_budget(
        Decimal(str(invoice_data.get("total_amount", 0))),
        category,
        financial_context
    )
    signals.append(budget_signal)
    risk_score += budget_signal.get("score_contribution", 0.0)
    reasoning.append(f"BUDGET: {budget_signal.get('message')}")

    return {
        "can_proceed": not blocked,
        "blocked": blocked,
        "block_reason": block_reason,
        "risk_score": min(risk_score, 1.0),
        "signals": [s for s in signals],
        "reasoning": reasoning,
    }


def _get_financial_context() -> dict:
    """Get financial context from environment variables."""
    return {
        "current_cash": float(os.getenv("CURRENT_CASH", "50000")),
        "monthly_burn_rate": float(os.getenv("MONTHLY_BURN_RATE", "15000")),
        "runway_days": float(os.getenv("RUNWAY_DAYS", "100")),
        "safety_buffer": float(os.getenv("SAFETY_BUFFER", "10000")),
        "strategy_mode": os.getenv("STRATEGY_MODE", "OPTIMIZE"),
        "payroll_date": os.getenv("PAYROLL_DATE", "15"),
        "payroll_amount": float(os.getenv("PAYROLL_AMOUNT", "15000")),
        "budgets": {},
        "category_limits": {
            "Infrastructure": 5000.0,
            "Software": 3000.0,
            "General": 2000.0,
        },
    }


def _get_trust_threshold(trust_level: int) -> float:
    """Get auto-approve threshold based on trust level."""
    thresholds = {
        1: 0.0,      # Probation - no auto-approve
        2: 500.0,    # Standard
        3: 5000.0,   # Core
    }
    return thresholds.get(trust_level, 0.0)


def _categorize_vendor(vendor_name: str) -> str:
    """Categorize vendor based on name."""
    if "aws" in vendor_name or "cloud" in vendor_name:
        return "Infrastructure"
    elif "software" in vendor_name or "saas" in vendor_name:
        return "Software"
    else:
        return "General"


def _check_runway(amount: Decimal, context: dict) -> dict:
    """Check if payment would endanger runway."""
    amount_float = float(amount)
    post_payment_cash = context["current_cash"] - amount_float
    
    if context["monthly_burn_rate"] > 0:
        post_runway = (post_payment_cash / context["monthly_burn_rate"]) * 30
    else:
        post_runway = 999
    
    # Safety threshold is payroll + buffer
    safety_threshold = context.get("payroll_amount", 0) + context["safety_buffer"]
    
    if post_payment_cash < context["safety_buffer"]:
        return {
            "type": "RUNWAY",
            "severity": "CRITICAL",
            "message": f"Payment would reduce cash to ${post_payment_cash:.0f} (below ${context['safety_buffer']:.0f} safety buffer)",
            "recommendation": "Delay payment until after payroll or cash infusion",
            "score_contribution": 0.40,
        }
    
    # Check if payment is close to payroll (before runway check)
    payroll_date = context.get("payroll_date")
    if payroll_date:
        try:
            from datetime import datetime
            payroll_day = int(payroll_date)
            today = datetime.now().day
            days_to_payroll = (payroll_day - today) % 30
            
            if days_to_payroll <= 3 and amount_float > context.get("payroll_amount", 0) * 0.5:
                return {
                    "type": "RUNWAY",
                    "severity": "WARNING",
                    "message": f"Payment of ${amount_float:.0f} within 3 days of payroll (${context.get('payroll_amount', 0):.0f})",
                    "recommendation": "Consider delaying until after payroll",
                    "score_contribution": 0.15,
                }
        except (ValueError, TypeError):
            pass
    
    if post_runway < 90:
        return {
            "type": "RUNWAY",
            "severity": "WARNING",
            "message": f"Payment would reduce runway to {post_runway:.0f} days",
            "recommendation": "Consider delaying non-essential payments",
            "score_contribution": 0.20,
        }
    
    return {
        "type": "RUNWAY",
        "severity": "INFO",
        "message": f"Payment safe (runway: {post_runway:.0f} days)",
        "recommendation": "Proceed",
        "score_contribution": 0.0,
    }


def _check_strategy(amount: Decimal, context: dict) -> dict:
    """Check if payment aligns with strategy mode."""
    amount_float = float(amount)
    mode = context["strategy_mode"]
    
    if mode == "SURVIVAL":
        if amount_float > context["current_cash"] * 0.1:
            return {
                "type": "STRATEGY",
                "severity": "CRITICAL",
                "message": f"SURVIVAL mode: ${amount_float:.0f} is >10% of cash",
                "recommendation": "Delay",
                "score_contribution": 0.30,
            }
        elif amount_float > 1000:
            return {
                "type": "STRATEGY",
                "severity": "WARNING",
                "message": f"SURVIVAL mode: Review all payments over $1,000",
                "recommendation": "Consider delaying non-essential payment",
                "score_contribution": 0.10,
            }
    elif mode == "GROWTH":
        # In GROWTH mode, pay fast but check for vendor terms
        return {
            "type": "STRATEGY",
            "severity": "INFO",
            "message": f"GROWTH mode: Prioritize early payment for vendor relationships",
            "recommendation": "Consider early payment discount",
            "score_contribution": 0.0,
        }
    elif mode == "OPTIMIZE":
        if amount_float > context["current_cash"] * 0.2:
            return {
                "type": "STRATEGY",
                "severity": "WARNING",
                "message": f"OPTIMIZE mode: ${amount_float:.0f} is >20% of cash",
                "recommendation": "Verify essential",
                "score_contribution": 0.10,
            }
    
    return {
        "type": "STRATEGY",
        "severity": "INFO",
        "message": f"{mode} mode: Payment acceptable",
        "recommendation": "Proceed",
        "score_contribution": 0.0,
    }


def _check_contract(due_date, context: dict) -> dict:
    """Check if payment terms are being violated."""
    if not due_date:
        return {
            "type": "CONTRACT",
            "severity": "INFO",
            "message": "No due date specified",
            "recommendation": "Proceed",
            "score_contribution": 0.0,
        }
    
    try:
        from datetime import datetime
        if hasattr(due_date, 'isoformat'):
            due = datetime.fromisoformat(due_date.isoformat())
        else:
            due = datetime.fromisoformat(str(due_date).replace("Z", "+00:00").split("+")[0])
        
        today = datetime.now()
        days_until_due = (due - today).days
        
        if days_until_due < 0:
            return {
                "type": "CONTRACT",
                "severity": "CRITICAL",
                "message": f"Invoice {abs(days_until_due)} days past due",
                "recommendation": "Pay immediately",
                "score_contribution": 0.20,
            }
        elif days_until_due <= 3:
            return {
                "type": "CONTRACT",
                "severity": "WARNING",
                "message": f"Due in {days_until_due} days",
                "recommendation": "Prioritize",
                "score_contribution": 0.05,
            }
    except (ValueError, AttributeError):
        pass
    
    return {
        "type": "CONTRACT",
        "severity": "INFO",
        "message": "Payment terms acceptable",
        "recommendation": "Proceed",
        "score_contribution": 0.0,
    }


def _check_trust(amount: Decimal, trust_level: int, trust_threshold: float) -> dict:
    """Check if vendor trust level permits auto-approval."""
    amount_float = float(amount)
    
    if trust_level == 1:
        return {
            "type": "TRUST",
            "severity": "INFO",
            "message": "Level 1 (Probation): Manual review required",
            "recommendation": "Human review",
            "score_contribution": 0.0,
        }
    
    if amount_float > trust_threshold:
        return {
            "type": "TRUST",
            "severity": "WARNING",
            "message": f"Amount ${amount_float:.0f} exceeds threshold ${trust_threshold:.0f}",
            "recommendation": "Requires approval",
            "score_contribution": 0.15,
        }
    
    return {
        "type": "TRUST",
        "severity": "INFO",
        "message": f"Level {trust_level} - within threshold",
        "recommendation": "Auto-approve eligible",
        "score_contribution": 0.0,
    }


def _check_budget(amount: Decimal, category: str, context: dict) -> dict:
    """Check if payment is within budget category limits."""
    amount_float = float(amount)
    current_spend = context["budgets"].get(category, 0)
    category_limit = context["category_limits"].get(category, float("inf"))
    
    projected_spend = current_spend + amount_float
    
    if projected_spend > category_limit:
        overage = projected_spend - category_limit
        overage_percent = (overage / category_limit) * 100 if category_limit > 0 else 0
        
        if overage_percent > 20:
            return {
                "type": "BUDGET",
                "severity": "CRITICAL",
                "message": f"Category '{category}': ${overage:.0f} over limit",
                "recommendation": "Do not approve",
                "score_contribution": 0.20,
            }
        else:
            return {
                "type": "BUDGET",
                "severity": "WARNING",
                "message": f"Category '{category}': Approaching limit",
                "recommendation": "Flag for review",
                "score_contribution": 0.10,
            }
    
    return {
        "type": "BUDGET",
        "severity": "INFO",
        "message": f"Category '{category}': Within budget",
        "recommendation": "Within limits",
        "score_contribution": 0.0,
    }
