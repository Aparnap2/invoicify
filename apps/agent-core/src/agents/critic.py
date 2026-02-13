"""Critic Node - Safety checks with Priority Matrix."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from src.config import get_settings
from src.schemas.invoice import InvoiceExtracted

logger = logging.getLogger(__name__)


class DecisionSignal(BaseModel):
    """A signal from the Critic's safety checks."""

    type: str  # "RUNWAY", "STRATEGY", "CONTRACT", "TRUST", "BUDGET"
    severity: str  # "CRITICAL", "WARNING", "INFO"
    message: str
    recommendation: str
    score_contribution: float = 0.0


class FinancialContext(BaseModel):
    """Company financial context for decision making."""

    current_cash: float
    monthly_burn_rate: float
    runway_days: float
    payroll_date: Optional[str] = None
    payroll_amount: float = 0.0
    safety_buffer: float = 10000.0
    strategy_mode: str = "OPTIMIZE"
    auto_approve_threshold: float = 500.0
    budgets: dict[str, float] = {}  # category -> current spend
    category_limits: dict[str, float] = {}  # category -> monthly limit


class CriticReview(BaseModel):
    """Critic's complete review of the analyst's proposal."""

    can_proceed: bool
    signals: list[DecisionSignal] = []
    blocked: bool = False
    block_reason: Optional[str] = None
    risk_score: float = 0.0
    reasoning: list[str] = []


class CriticAgent:
    """Critic Node - Safety checks using Priority Matrix.

    Priority Order (Non-Negotiable):
    1. RUNWAY - Does paying now endanger cash reserves?
    2. STRATEGY - Does this align with SURVIVAL/GROWTH/OPTIMIZE mode?
    3. CONTRACT - Are payment terms being violated?
    4. TRUST - What's the vendor's trust battery level?
    5. BUDGET - Is this within category limits?
    """

    def __init__(self):
        """Initialize the critic agent."""
        self.settings = get_settings()

    async def review(
        self,
        invoice_data: InvoiceExtracted,
        financial_context: FinancialContext,
        trust_level: int,  # 1, 2, or 3
        trust_threshold: float,
    ) -> CriticReview:
        """Perform safety checks on the analyst's proposal."""
        logger.info(f"Critic reviewing invoice: {invoice_data.invoice_number}")

        signals: list[DecisionSignal] = []
        reasoning: list[str] = []
        blocked = False
        block_reason: Optional[str] = None
        risk_score = 0.0

        # ===== 1. RUNWAY CHECK (Highest Priority) =====
        runway_signal = self._check_runway(
            invoice_data.total_amount, financial_context
        )
        signals.append(runway_signal)
        risk_score += runway_signal.score_contribution

        if runway_signal.severity == "CRITICAL":
            blocked = True
            block_reason = runway_signal.message
        reasoning.append(f"RUNWAY: {runway_signal.message}")

        # ===== 2. STRATEGY CHECK =====
        strategy_signal = self._check_strategy(
            invoice_data.total_amount, financial_context
        )
        signals.append(strategy_signal)
        risk_score += strategy_signal.score_contribution

        if strategy_signal.severity == "CRITICAL" and not blocked:
            blocked = True
            block_reason = strategy_signal.message
        reasoning.append(f"STRATEGY: {strategy_signal.message}")

        # ===== 3. CONTRACT CHECK =====
        contract_signal = self._check_contract(
            invoice_data.due_date, financial_context
        )
        signals.append(contract_signal)
        risk_score += contract_signal.score_contribution
        reasoning.append(f"CONTRACT: {contract_signal.message}")

        # ===== 4. TRUST CHECK =====
        trust_signal = self._check_trust(
            invoice_data.total_amount, trust_level, trust_threshold
        )
        signals.append(trust_signal)
        risk_score += trust_signal.score_contribution
        reasoning.append(f"TRUST: {trust_signal.message}")

        # ===== 5. BUDGET CHECK =====
        # Get category from vendor name or use default
        vendor_name = invoice_data.vendor_name.lower()
        if "aws" in vendor_name or "cloud" in vendor_name:
            category = "Infrastructure"
        elif "software" in vendor_name or "saas" in vendor_name:
            category = "Software"
        else:
            category = "General"

        budget_signal = self._check_budget(
            invoice_data.total_amount, category, financial_context
        )
        signals.append(budget_signal)
        risk_score += budget_signal.score_contribution
        reasoning.append(f"BUDGET: {budget_signal.message}")

        return CriticReview(
            can_proceed=not blocked,
            signals=signals,
            blocked=blocked,
            block_reason=block_reason,
            risk_score=min(risk_score, 1.0),  # Cap at 1.0
            reasoning=reasoning,
        )

    def _check_runway(
        self,
        amount: Decimal,
        context: FinancialContext,
    ) -> DecisionSignal:
        """Check if payment would endanger runway."""
        amount_float = float(amount)

        # Calculate post-payment cash
        post_payment_cash = context.current_cash - amount_float

        # Calculate post-payment runway
        if context.monthly_burn_rate > 0:
            post_runway = (post_payment_cash / context.monthly_burn_rate) * 30
        else:
            post_runway = 999  # No burn, infinite runway

        # Safety threshold is payroll + buffer
        safety_threshold = context.payroll_amount + context.safety_buffer

        # Check if payment would go below safety threshold
        if post_payment_cash < context.safety_buffer:
            return DecisionSignal(
                type="RUNWAY",
                severity="CRITICAL",
                message=f"Payment would reduce cash to ${post_payment_cash:.0f} (below ${context.safety_buffer:.0f} safety buffer)",
                recommendation="Delay payment until after payroll or cash infusion",
                score_contribution=0.40,
            )

        # Check if payment is close to payroll (before runway check)
        if context.payroll_date:
            try:
                payroll_day = int(context.payroll_date)
                today = datetime.now().day
                days_to_payroll = (payroll_day - today) % 30

                if days_to_payroll <= 3 and amount_float > context.payroll_amount * 0.5:
                    return DecisionSignal(
                        type="RUNWAY",
                        severity="WARNING",
                        message=f"Payment of ${amount_float:.0f} within 3 days of payroll (${context.payroll_amount:.0f})",
                        recommendation="Consider delaying until after payroll",
                        score_contribution=0.15,
                    )
            except ValueError:
                pass

        # Check if runway drops below 3 months
        if post_runway < 90:  # 3 months
            return DecisionSignal(
                type="RUNWAY",
                severity="WARNING",
                message=f"Payment would reduce runway to {post_runway:.0f} days",
                recommendation="Consider delaying non-essential payments",
                score_contribution=0.20,
            )

        return DecisionSignal(
            type="RUNWAY",
            severity="INFO",
            message=f"Payment of ${amount_float:.0f} is safe (runway: {post_runway:.0f} days)",
            recommendation="Proceed with payment",
            score_contribution=0.0,
        )

    def _check_strategy(
        self,
        amount: Decimal,
        context: FinancialContext,
    ) -> DecisionSignal:
        """Check if payment aligns with strategy mode."""
        amount_float = float(amount)

        if context.strategy_mode == "SURVIVAL":
            # In SURVIVAL mode, delay everything unless critical
            if amount_float > context.current_cash * 0.1:  # More than 10% of cash
                return DecisionSignal(
                    type="STRATEGY",
                    severity="CRITICAL",
                    message=f"SURVIVAL mode: ${amount_float:.0f} is >10% of cash (${context.current_cash:.0f})",
                    recommendation="Delay - preserve cash in SURVIVAL mode",
                    score_contribution=0.30,
                )
            elif amount_float > 1000:
                return DecisionSignal(
                    type="STRATEGY",
                    severity="WARNING",
                    message=f"SURVIVAL mode: Review all payments over $1,000",
                    recommendation="Consider delaying non-essential payment",
                    score_contribution=0.10,
                )

        elif context.strategy_mode == "GROWTH":
            # In GROWTH mode, pay fast but check for vendor terms
            return DecisionSignal(
                type="STRATEGY",
                severity="INFO",
                message=f"GROWTH mode: Prioritize early payment for vendor relationships",
                recommendation="Consider early payment discount",
                score_contribution=0.0,
            )

        else:  # OPTIMIZE
            # In OPTIMIZE mode, balance between cash and relationships
            if amount_float > context.current_cash * 0.2:
                return DecisionSignal(
                    type="STRATEGY",
                    severity="WARNING",
                    message=f"OPTIMIZE mode: ${amount_float:.0f} is >20% of cash",
                    recommendation="Verify this is essential spending",
                    score_contribution=0.10,
                )

            return DecisionSignal(
                type="STRATEGY",
                severity="INFO",
                message="OPTIMIZE mode: Balance cash and vendor relationships",
                recommendation="Proceed with standard payment timing",
                score_contribution=0.0,
            )

        return DecisionSignal(
            type="STRATEGY",
            severity="INFO",
            message="Strategy check passed",
            recommendation="Proceed",
            score_contribution=0.0,
        )

    def _check_contract(
        self,
        due_date,
        context: FinancialContext,
    ) -> DecisionSignal:
        """Check if payment terms are being violated."""
        if not due_date:
            return DecisionSignal(
                type="CONTRACT",
                severity="INFO",
                message="No due date specified - standard terms apply",
                recommendation="Proceed with standard payment timing",
                score_contribution=0.0,
            )

        # Handle date objects and date strings
        try:
            if hasattr(due_date, 'isoformat'):
                # It's a date/datetime object
                due = datetime.fromisoformat(due_date.isoformat())
            else:
                # It's a string
                due = datetime.fromisoformat(str(due_date).replace("Z", "+00:00").split("+")[0])
            today = datetime.now()
            days_until_due = (due - today).days

            if days_until_due < 0:
                return DecisionSignal(
                    type="CONTRACT",
                    severity="CRITICAL",
                    message=f"Invoice is {abs(days_until_due)} days past due",
                    recommendation="Pay immediately to avoid late fees",
                    score_contribution=0.20,
                )

            elif days_until_due <= 3:
                return DecisionSignal(
                    type="CONTRACT",
                    severity="WARNING",
                    message=f"Invoice due in {days_until_due} days",
                    recommendation="Prioritize payment to avoid late fees",
                    score_contribution=0.05,
                )

            elif days_until_due > 45:
                return DecisionSignal(
                    type="CONTRACT",
                    severity="INFO",
                    message=f"Invoice not due for {days_until_due} days",
                    recommendation="Consider payment timing optimization",
                    score_contribution=0.0,
                )

        except ValueError:
            pass

        return DecisionSignal(
            type="CONTRACT",
            severity="INFO",
            message="Payment terms are acceptable",
            recommendation="Proceed with standard timing",
            score_contribution=0.0,
        )

    def _check_trust(
        self,
        amount: Decimal,
        trust_level: int,
        trust_threshold: float,
    ) -> DecisionSignal:
        """Check if vendor trust level permits auto-approval."""
        amount_float = float(amount)

        # Level 1 (Probation) - always requires review
        if trust_level == 1:
            return DecisionSignal(
                type="TRUST",
                severity="INFO",
                message=f"Vendor at Level 1 (Probation): Manual review required",
                recommendation="Human must review before approval",
                score_contribution=0.0,
            )

        # Check amount against threshold
        if amount_float > trust_threshold:
            return DecisionSignal(
                type="TRUST",
                severity="WARNING",
                message=f"Amount ${amount_float:.0f} exceeds trust threshold ${trust_threshold:.0f}",
                recommendation=f"Requires approval despite Level {trust_level} trust",
                score_contribution=0.15,
            )

        return DecisionSignal(
            type="TRUST",
            severity="INFO",
            message=f"Vendor at Level {trust_level} - amount within threshold",
            recommendation="Auto-approve eligible",
            score_contribution=0.0,
        )

    def _check_budget(
        self,
        amount: Decimal,
        category: str,
        context: FinancialContext,
    ) -> DecisionSignal:
        """Check if payment is within budget category limits."""
        amount_float = float(amount)

        current_spend = context.budgets.get(category, 0)
        category_limit = context.category_limits.get(category, float("inf"))

        projected_spend = current_spend + amount_float

        if projected_spend > category_limit:
            overage = projected_spend - category_limit
            overage_percent = (overage / category_limit) * 100 if category_limit > 0 else 0

            if overage_percent > 20:
                return DecisionSignal(
                    type="BUDGET",
                    severity="CRITICAL",
                    message=f"Category '{category}': ${overage:.0f} ({overage_percent:.0f}%) over limit",
                    recommendation="Do not approve - budget exceeded",
                    score_contribution=0.20,
                )
            else:
                return DecisionSignal(
                    type="BUDGET",
                    severity="WARNING",
                    message=f"Category '{category}': Approaching limit (${projected_spend:.0f}/${category_limit:.0f})",
                    recommendation="Flag for review",
                    score_contribution=0.10,
                )

        elif projected_spend > category_limit * 0.8:
            return DecisionSignal(
                type="BUDGET",
                severity="INFO",
                message=f"Category '{category}': ${projected_spend:.0f}/${category_limit:.0f} (80% used)",
                recommendation="Monitor - approaching limit",
                score_contribution=0.0,
            )

        return DecisionSignal(
            type="BUDGET",
            severity="INFO",
            message=f"Category '{category}': Within budget (${projected_spend:.0f}/${category_limit:.0f})",
            recommendation="Within budget limits",
            score_contribution=0.0,
        )


# Singleton instance
_critic_agent: Optional[CriticAgent] = None


def get_critic_agent() -> CriticAgent:
    """Get the singleton Critic agent instance."""
    global _critic_agent
    if _critic_agent is None:
        _critic_agent = CriticAgent()
    return _critic_agent
