"""Analyst Node - Pattern detection and proposal generation."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.clients.neo4j_client import get_neo4j_client
from app.clients.ollama_client import get_ollama_client
from app.config import get_settings
from app.schemas.invoice import InvoiceExtracted

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
    anomalies: list[Anomaly] = []
    vendor_patterns: list[str] = []
    reasoning: list[str] = []
    suggested_amount: Optional[Decimal] = None
    suggested_due_date: Optional[str] = None


class AnalystAgent:
    """Analyst Node - Proposes actions based on historical patterns."""

    def __init__(self):
        """Initialize the analyst agent."""
        self.settings = get_settings()
        self.ollama = get_ollama_client()
        self.neo4j = get_neo4j_client()

    async def analyze(
        self,
        invoice_data: InvoiceExtracted,
        vendor_id: Optional[str] = None,
    ) -> AnalystProposal:
        """Analyze invoice and propose an action."""
        logger.info(f"Analyst analyzing invoice: {invoice_data.invoice_number}")

        # 1. Get vendor history from Neo4j
        vendor_history = []
        vendor_patterns = []
        if vendor_id:
            try:
                invoices = await self.neo4j.get_invoices_by_vendor(vendor_id)
                vendor_history = [
                    {
                        "amount": float(i.amount),
                        "status": i.status,
                    }
                    for i in invoices[-10:]  # Last 10 invoices
                ]

                # Get anomaly patterns
                anomalies = await self.neo4j.find_anomaly_patterns(vendor_id)
                vendor_patterns = [
                    f"Found {len(anomalies)} potential anomalies in payment history"
                ]
            except Exception as e:
                logger.warning(f"Failed to fetch vendor history: {e}")
                vendor_history = []
                vendor_patterns = ["Could not retrieve vendor history"]

        # 2. Detect anomalies in current invoice
        detected_anomalies = self._detect_anomalies(
            invoice_data.total_amount, vendor_history
        )

        # 3. Calculate confidence based on extraction confidence
        base_confidence = invoice_data.overall_confidence if hasattr(invoice_data, 'overall_confidence') else 0.8

        # 4. Generate proposal
        proposal = await self._generate_proposal(
            invoice_data=invoice_data,
            vendor_history=vendor_history,
            anomalies=detected_anomalies,
            base_confidence=base_confidence,
        )

        return proposal

    def _detect_anomalies(
        self,
        total_amount: Decimal,
        vendor_history: list[dict],
    ) -> list[Anomaly]:
        """Detect anomalies in the invoice amount."""
        anomalies = []

        if not vendor_history:
            # No history - could be a new vendor
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

        # Check for amount deviation
        current_amount = float(total_amount)
        if avg_amount > 0:
            deviation = (current_amount - avg_amount) / avg_amount

            if deviation > 2.0:  # More than 2x average
                anomalies.append(
                    Anomaly(
                        type="AMOUNT_SPIKE",
                        severity="high",
                        description=f"Amount ${current_amount:.2f} is {deviation:.1f}x the average ${avg_amount:.2f}",
                        amount_deviation=deviation,
                    )
                )
            elif deviation > 1.5:  # More than 1.5x average
                anomalies.append(
                    Anomaly(
                        type="AMOUNT_DEVIATION",
                        severity="medium",
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

    async def _generate_proposal(
        self,
        invoice_data: InvoiceExtracted,
        vendor_history: list[dict],
        anomalies: list[Anomaly],
        base_confidence: float,
    ) -> AnalystProposal:
        """Generate the analyst's proposal."""
        reasoning = []
        proposed_action = "AUTO_APPROVE"

        # High severity anomalies always require HITL
        high_severity_anomalies = [a for a in anomalies if a.severity == "high"]
        if high_severity_anomalies:
            proposed_action = "HITL_REQUIRED"
            reasoning.append(
                f"High severity anomaly detected: {high_severity_anomalies[0].type}"
            )

        # Medium severity anomalies - consider context
        medium_severity_anomalies = [a for a in anomalies if a.severity == "medium"]
        if medium_severity_anomalies and not high_severity_anomalies:
            # Could still auto-approve but with lower confidence
            base_confidence *= 0.7
            reasoning.append(
                f"Medium severity anomaly: {medium_severity_anomalies[0].type} - reducing confidence"
            )

        # New vendor check
        if not vendor_history:
            proposed_action = "HITL_REQUIRED"
            reasoning.append("New vendor - requires human review for first invoice")

        # High amount threshold
        if float(invoice_data.total_amount) > 10000:
            proposed_action = "HITL_REQUIRED"
            reasoning.append(f"High value invoice (${invoice_data.total_amount}) requires approval")

        # Check extraction confidence - InvoiceExtracted has overall_confidence at top level
        requires_review = getattr(invoice_data, 'requires_review', False)
        if requires_review:
            proposed_action = "HITL_REQUIRED"
            reasoning.append("Extraction confidence below threshold - requires review")

        # Build reasoning chain
        reasoning.insert(
            0,
            f"Invoice ${invoice_data.total_amount} from {invoice_data.vendor_name} analyzed",
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
            suggested_amount=invoice_data.total_amount,
            suggested_due_date=str(invoice_data.due_date) if invoice_data.due_date else None,
        )


# Singleton instance
_analyst_agent: Optional[AnalystAgent] = None


def get_analyst_agent() -> AnalystAgent:
    """Get the singleton Analyst agent instance."""
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = AnalystAgent()
    return _analyst_agent
