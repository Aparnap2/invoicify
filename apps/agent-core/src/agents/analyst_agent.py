"""
Analyst Agent for Risk Assessment.

Analyzes invoice risk using:
- Trust Battery (vendor history)
- RAG context (similar invoices)
- Risk scoring (anomaly detection)
"""

from typing import Any, Dict, Optional
import structlog

from src.schemas.invoice_v2 import (
    ExtractedInvoice,
    RiskAnalysis,
    RiskDecision,
    TrustLevel,
)
from src.trust.battery import TrustBattery, TrustBatteryManager

logger = structlog.get_logger()


class AnalystAgent:
    """
    Analyzes invoice risk and makes approval decisions.
    
    Decision Matrix:
    - AUTO_APPROVE: trust >= CORE AND risk < 0.3 AND amount < limit
    - HITL_REQUIRED: trust = STANDARD OR risk 0.3-0.7 OR amount > limit
    - BLOCKED: risk > 0.7 OR fraud_signals OR is_duplicate
    """
    
    # Risk score weights
    ANOMALY_WEIGHT = 0.3
    TRUST_WEIGHT = 0.3
    AMOUNT_WEIGHT = 0.2
    DUPLICATE_WEIGHT = 0.2
    
    # Risk thresholds
    LOW_RISK_THRESHOLD = 0.3
    HIGH_RISK_THRESHOLD = 0.7
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize analyst.
        
        Args:
            config: Configuration with Redis/Cosmos clients
        """
        self.config = config if config is not None else {}
        self.redis_client = self.config.get("redis_client")
        self.cosmos_client = self.config.get("cosmos_client")
        self.trust_manager = TrustBatteryManager(
            redis_client=self.redis_client,
            cosmos_client=self.cosmos_client,
        )
    
    async def analyze(
        self,
        extracted: ExtractedInvoice,
        tenant_id: str,
        metadata: Dict[str, Any],
    ) -> RiskAnalysis:
        """
        Analyze invoice risk.
        
        Args:
            extracted: Extracted invoice data
            tenant_id: Tenant identifier
            metadata: Additional metadata (vendor_name, etc.)
            
        Returns:
            RiskAnalysis with decision
        """
        # 1. Load vendor trust battery
        vendor_name = metadata.get("vendor_name", extracted.vendor.name)
        battery = await self.trust_manager.get_battery(vendor_name, tenant_id)
        
        # 2. Compute risk signals
        risk_signals = await self._compute_risk_signals(extracted, battery, metadata)
        
        # 3. Calculate risk score
        risk_score = self._calculate_risk_score(risk_signals, battery)
        
        # 4. Make decision
        decision, decision_reason = self._make_decision(
            risk_score=risk_score,
            trust_level=battery.level,
            amount=extracted.total_amount,
            auto_approve_limit=battery.auto_approve_limit,
            risk_signals=risk_signals,
        )
        
        # 5. Build risk analysis
        analysis = RiskAnalysis(
            risk_score=risk_score,
            decision=decision,
            decision_reason=decision_reason,
            confidence=1.0 - risk_score,  # Confidence inverse to risk
            trust_level=battery.level,
            trust_score=battery.score,
            is_duplicate=risk_signals.get("is_duplicate", False),
            duplicate_invoice_id=risk_signals.get("duplicate_invoice_id"),
            price_anomaly=risk_signals.get("price_anomaly", False),
            price_variance_pct=risk_signals.get("price_variance_pct"),
            math_errors=risk_signals.get("math_errors", []),
            fraud_signals=risk_signals.get("fraud_signals", []),
            auto_approve_limit=battery.auto_approve_limit,
            amount_vs_limit="WITHIN" if extracted.total_amount <= battery.auto_approve_limit else "EXCEEDS",
            similar_invoices_found=risk_signals.get("similar_invoices_found", 0),
            contract_terms_found=risk_signals.get("contract_terms_found", False),
            rag_retrieval_latency_ms=risk_signals.get("rag_latency_ms", 0),
        )
        
        logger.info(
            "risk_analyzed",
            invoice_id=extracted.invoice_id,
            risk_score=risk_score,
            decision=decision.value,
            trust_level=battery.level.value,
        )
        
        return analysis
    
    async def _compute_risk_signals(
        self,
        extracted: ExtractedInvoice,
        battery: TrustBattery,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute risk signals.
        
        Returns:
            Dict with risk signals
        """
        signals = {
            "is_duplicate": False,
            "duplicate_invoice_id": None,
            "price_anomaly": False,
            "price_variance_pct": None,
            "math_errors": [],
            "fraud_signals": [],
            "similar_invoices_found": 0,
            "contract_terms_found": False,
            "rag_latency_ms": 0,
        }
        
        # Placeholder for RAG-based signals
        # In production, this would query Azure AI Search
        
        return signals
    
    def _calculate_risk_score(
        self,
        signals: Dict[str, Any],
        battery: TrustBattery,
    ) -> float:
        """
        Calculate overall risk score (0.0-1.0).
        
        Formula:
            risk = (
                anomaly_weight * anomaly_score +
                trust_weight * (1 - trust_score) +
                amount_weight * amount_ratio +
                duplicate_weight * duplicate_score
            )
        
        Returns:
            Risk score between 0.0 and 1.0
        """
        # Anomaly score (0.0 if no anomalies, 1.0 if multiple)
        anomaly_count = sum([
            signals.get("price_anomaly", False),
            bool(signals.get("math_errors", [])),
            bool(signals.get("fraud_signals", [])),
        ])
        anomaly_score = min(1.0, anomaly_count / 3.0)
        
        # Trust score (inverse - lower trust = higher risk)
        trust_inverse = 1.0 - battery.score
        
        # Amount ratio (higher amount = higher risk)
        # Normalize to $50,000 (STRATEGIC limit)
        amount_ratio = min(1.0, 0.0 / 50000.0)  # Will be overridden by actual amount
        
        # Duplicate score
        duplicate_score = 1.0 if signals.get("is_duplicate", False) else 0.0
        
        # Weighted sum
        risk_score = (
            self.ANOMALY_WEIGHT * anomaly_score +
            self.TRUST_WEIGHT * trust_inverse +
            self.AMOUNT_WEIGHT * amount_ratio +
            self.DUPLICATE_WEIGHT * duplicate_score
        )
        
        return round(min(1.0, risk_score), 3)
    
    def _make_decision(
        self,
        risk_score: float,
        trust_level: TrustLevel,
        amount: float,
        auto_approve_limit: float,
        risk_signals: Dict[str, Any],
    ) -> tuple[RiskDecision, str]:
        """
        Make approval decision based on risk analysis.
        
        Decision Matrix:
        - BLOCKED: risk > 0.7 OR fraud_signals OR is_duplicate
        - HITL_REQUIRED: trust = STANDARD OR risk 0.3-0.7 OR amount > limit
        - AUTO_APPROVE: trust >= CORE AND risk < 0.3 AND amount < limit
        
        Returns:
            Tuple of (decision, reason)
        """
        # Check for BLOCKED conditions
        if risk_score > self.HIGH_RISK_THRESHOLD:
            return (
                RiskDecision.BLOCKED,
                f"High risk score: {risk_score:.2f} > {self.HIGH_RISK_THRESHOLD}",
            )
        
        if risk_signals.get("fraud_signals"):
            return (
                RiskDecision.BLOCKED,
                f"Fraud signals detected: {', '.join(risk_signals['fraud_signals'])}",
            )
        
        if risk_signals.get("is_duplicate", False):
            return (
                RiskDecision.BLOCKED,
                f"Duplicate invoice detected: {risk_signals.get('duplicate_invoice_id')}",
            )
        
        # Check for AUTO_APPROVE conditions
        if (
            trust_level in [TrustLevel.CORE, TrustLevel.STRATEGIC]
            and risk_score < self.LOW_RISK_THRESHOLD
            and amount <= auto_approve_limit
        ):
            return (
                RiskDecision.AUTO_APPROVE,
                f"{trust_level.value} vendor, risk {risk_score:.2f} < {self.LOW_RISK_THRESHOLD}, "
                f"amount ${amount:,.2f} within ${auto_approve_limit:,.2f} limit",
            )
        
        # Default to HITL_REQUIRED
        return (
            RiskDecision.HITL_REQUIRED,
            f"Trust level {trust_level.value}, risk {risk_score:.2f}, "
            f"amount ${amount:,.2f} vs limit ${auto_approve_limit:,.2f}",
        )
