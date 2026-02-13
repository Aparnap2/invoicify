"""
River ML Risk Scorer
Multi-signal anomaly detection for invoice risk assessment.
Uses online learning to adapt to vendor patterns over time.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from river import anomaly, compose, preprocessing, stats

from src.domain.models import (
    InvoiceData,
    RiskBreakdown,
    RiskScore,
    Decision,
    TrustBattery,
)

logger = logging.getLogger(__name__)


class InvoiceRiskScorer:
    """
    Multi-signal risk scoring using River ML online learning.

    Signals:
    1. Amount Anomaly: Statistical deviation from vendor history
    2. Pattern Anomaly: Unusual invoice structure/features
    3. Vendor Trust: Penalty based on trust level
    4. Time-based Risk: Weekend/holiday submissions
    5. Duplicate Risk: Similarity to existing invoices
    """

    def __init__(self):
        # Amount anomaly detector (statistical)
        self.amount_scorer = stats.Mean()
        self.amount_std = stats.Var()

        # Pattern anomaly detector (Half-Space Trees)
        self.pattern_detector = anomaly.HalfSpaceTrees(
            n_trees=10,
            height=8,
            window_size=100,
        )

        # Gaussian scorer for statistical anomalies
        self.gaussian_scorer = anomaly.GaussianScorer()

        # Local Outlier Factor for density-based anomalies
        self.lof_detector = anomaly.LocalOutlierFactor()

        # Feature preprocessor
        self.preprocessor = compose.Pipeline(
            preprocessing.StandardScaler(),
        )

        # Vendor-specific models (vendor_id -> models)
        self.vendor_models: Dict[str, Dict] = {}

        logger.info("✅ RiskScorer initialized with River ML")

    def _get_vendor_models(self, vendor_id: str) -> Dict:
        """Get or create vendor-specific models."""
        if vendor_id not in self.vendor_models:
            self.vendor_models[vendor_id] = {
                "amount_mean": stats.Mean(),
                "amount_std": stats.Var(),
                "pattern_detector": anomaly.HalfSpaceTrees(
                    n_trees=10,
                    height=8,
                    window_size=50,
                ),
                "gaussian": anomaly.GaussianScorer(),
                "history_count": 0,
                "avg_amount": Decimal("0.00"),
            }
        return self.vendor_models[vendor_id]

    def _extract_features(self, invoice: InvoiceData) -> Dict[str, float]:
        """Extract numerical features from invoice for ML models."""
        # Time-based features
        hour = invoice.issue_date.hour
        is_weekend = invoice.issue_date.weekday() >= 5
        is_end_of_month = invoice.issue_date.day >= 25

        # Amount features
        amount = float(invoice.total_amount)
        line_count = len(invoice.line_items)
        avg_line_value = amount / max(line_count, 1)

        # Confidence feature
        confidence = invoice.confidence

        return {
            "amount": amount,
            "hour": hour,
            "is_weekend": float(is_weekend),
            "is_end_of_month": float(is_end_of_month),
            "line_count": line_count,
            "avg_line_value": avg_line_value,
            "confidence": confidence,
        }

    def _calculate_amount_anomaly(
        self,
        invoice: InvoiceData,
        vendor_models: Dict,
    ) -> float:
        """
        Calculate amount anomaly score based on vendor history.
        Returns 0.0 (normal) to 1.0 (highly anomalous).
        """
        history_count = vendor_models["history_count"]

        if history_count < 3:
            # Not enough history - moderate risk
            return 0.3

        current_amount = float(invoice.total_amount)
        mean_amount = vendor_models["amount_mean"].get()
        std_amount = vendor_models["amount_std"].get() ** 0.5

        if std_amount == 0:
            # All previous invoices same amount
            return 0.5 if current_amount != mean_amount else 0.0

        # Calculate z-score
        z_score = abs(current_amount - mean_amount) / std_amount

        # Convert to 0-1 scale (sigmoid-like)
        # z=0 -> 0.0, z=2 -> 0.5, z=4 -> 0.9
        anomaly_score = min(1.0, z_score / 4.0)

        logger.debug(
            f"Amount anomaly for {invoice.vendor_id}: "
            f"amount={current_amount}, mean={mean_amount:.2f}, "
            f"z={z_score:.2f}, score={anomaly_score:.2f}"
        )

        return anomaly_score

    def _calculate_pattern_anomaly(
        self,
        invoice: InvoiceData,
        vendor_models: Dict,
    ) -> float:
        """
        Calculate pattern anomaly using Half-Space Trees.
        """
        features = self._extract_features(invoice)
        feature_vector = {
            k: v for k, v in features.items() if isinstance(v, (int, float))
        }

        # Get anomaly score from pattern detector
        pattern_detector = vendor_models["pattern_detector"]
        raw_score = pattern_detector.score_one(feature_vector)

        # Learn from this invoice (online learning)
        pattern_detector.learn_one(feature_vector)

        # Normalize to 0-1 (typical raw scores 0.0 to 1.0)
        return min(1.0, max(0.0, raw_score))

    def _calculate_vendor_trust_penalty(
        self,
        invoice: InvoiceData,
        trust_battery: Optional[TrustBattery],
    ) -> float:
        """
        Calculate trust penalty based on vendor trust level.
        """
        if not trust_battery:
            return 0.8  # Unknown vendor - high penalty

        # Trust level 1 (NEW) = 0.8 penalty
        # Trust level 5 (VERIFIED) = 0.0 penalty
        level_value = trust_battery.level.value
        penalty = (6 - level_value) * 0.2

        # Additional penalty for disputes
        if trust_battery.disputes > 0:
            penalty += min(0.3, trust_battery.disputes * 0.1)

        return min(1.0, penalty)

    def _calculate_time_based_risk(self, invoice: InvoiceData) -> float:
        """
        Calculate risk based on submission timing.
        """
        risk = 0.0

        # Weekend submissions slightly riskier
        if invoice.issue_date.weekday() >= 5:
            risk += 0.1

        # End-of-month rush
        if invoice.issue_date.day >= 25:
            risk += 0.05

        # Late night submissions (outside business hours)
        hour = invoice.issue_date.hour
        if hour < 6 or hour > 22:
            risk += 0.1

        return min(1.0, risk)

    def _calculate_duplicate_risk(
        self,
        invoice: InvoiceData,
        existing_invoices: Optional[List[InvoiceData]] = None,
    ) -> float:
        """
        Calculate risk of duplicate invoice.
        """
        if not existing_invoices:
            return 0.0

        # Simple similarity check
        for existing in existing_invoices:
            # Same invoice number = high risk
            if existing.invoice_number == invoice.invoice_number:
                return 0.9

            # Same amount + same day = moderate risk
            if (
                existing.total_amount == invoice.total_amount
                and existing.issue_date.date() == invoice.issue_date.date()
            ):
                return 0.5

        return 0.0

    def score_invoice(
        self,
        invoice: InvoiceData,
        trust_battery: Optional[TrustBattery] = None,
        existing_invoices: Optional[List[InvoiceData]] = None,
    ) -> RiskScore:
        """
        Calculate comprehensive risk score for an invoice.

        Args:
            invoice: The invoice to score
            trust_battery: Vendor's trust battery (optional)
            existing_invoices: Previous invoices from this vendor (optional)

        Returns:
            RiskScore with overall score and breakdown
        """
        vendor_models = self._get_vendor_models(invoice.vendor_id)

        # Calculate individual risk signals
        amount_anomaly = self._calculate_amount_anomaly(invoice, vendor_models)
        pattern_anomaly = self._calculate_pattern_anomaly(invoice, vendor_models)
        trust_penalty = self._calculate_vendor_trust_penalty(invoice, trust_battery)
        time_risk = self._calculate_time_based_risk(invoice)
        duplicate_risk = self._calculate_duplicate_risk(invoice, existing_invoices)

        # Build breakdown
        breakdown = RiskBreakdown(
            amount_anomaly_score=amount_anomaly,
            pattern_anomaly_score=pattern_anomaly,
            vendor_trust_penalty=trust_penalty,
            time_based_risk=time_risk,
            duplicate_risk=duplicate_risk,
        )

        # Determine recommendation
        overall_score = breakdown.overall_score

        if overall_score < 0.2:
            recommendation = Decision.APPROVE
        elif overall_score > 0.6:
            recommendation = Decision.REJECT
        else:
            recommendation = Decision.REVIEW

        # Generate human-readable reasons
        reasons = self._generate_reasons(breakdown, invoice, trust_battery)

        logger.info(
            f"Risk score for invoice {invoice.invoice_id}: "
            f"overall={overall_score:.2f}, decision={recommendation.value}"
        )

        return RiskScore(
            overall_score=overall_score,
            breakdown=breakdown,
            reasons=reasons,
            recommended_action=recommendation,
        )

    def _generate_reasons(
        self,
        breakdown: RiskBreakdown,
        invoice: InvoiceData,
        trust_battery: Optional[TrustBattery],
    ) -> List[str]:
        """Generate human-readable risk reasons."""
        reasons = []

        if breakdown.amount_anomaly_score > 0.6:
            reasons.append(
                f"Amount ${invoice.total_amount} is unusually high for this vendor"
            )

        if breakdown.pattern_anomaly_score > 0.5:
            reasons.append("Invoice structure differs from typical pattern")

        if breakdown.vendor_trust_penalty > 0.5:
            if not trust_battery:
                reasons.append("New vendor with no payment history")
            else:
                reasons.append(
                    f"Vendor trust level is {trust_battery.level.name} "
                    f"({trust_battery.successful_payments} successful payments)"
                )

        if breakdown.time_based_risk > 0.1:
            reasons.append("Submitted outside normal business hours")

        if breakdown.duplicate_risk > 0.5:
            reasons.append("Possible duplicate invoice detected")

        if not reasons:
            reasons.append("No significant risk factors identified")

        return reasons

    def learn_from_payment(
        self,
        invoice: InvoiceData,
        was_successful: bool,
    ) -> None:
        """
        Update models based on payment outcome.
        Online learning - updates in real-time.

        Args:
            invoice: The processed invoice
            was_successful: Whether payment was successful
        """
        vendor_models = self._get_vendor_models(invoice.vendor_id)

        # Update amount statistics
        amount = float(invoice.total_amount)
        vendor_models["amount_mean"].update(amount)
        vendor_models["amount_std"].update(amount)
        vendor_models["history_count"] += 1

        # Update average amount
        current_avg = vendor_models["avg_amount"]
        count = vendor_models["history_count"]
        new_avg = (current_avg * (count - 1) + invoice.total_amount) / count
        vendor_models["avg_amount"] = new_avg

        # Update global models
        self.amount_scorer.update(amount)
        self.amount_std.update(amount)

        logger.info(
            f"Learned from payment: vendor={invoice.vendor_id}, "
            f"amount={amount}, success={was_successful}"
        )

    def get_vendor_stats(self, vendor_id: str) -> Optional[Dict]:
        """Get statistics for a vendor."""
        if vendor_id not in self.vendor_models:
            return None

        models = self.vendor_models[vendor_id]
        return {
            "history_count": models["history_count"],
            "avg_amount": float(models["avg_amount"]),
            "amount_mean": models["amount_mean"].get(),
            "amount_std": models["amount_std"].get() ** 0.5,
        }
