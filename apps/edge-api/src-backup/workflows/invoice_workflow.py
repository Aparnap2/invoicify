"""
Temporal Workflow Implementation with Docling, Risk Scoring, and Trust Battery
Comprehensive invoice processing workflow using Hexagonal Architecture.
"""

import logging
from datetime import timedelta
from typing import Dict, Any
from decimal import Decimal

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from src.activities.extract_docling import extract_invoice_with_docling
    from src.activities.risk_score import calculate_risk_score
    from src.activities.make_decision import make_invoice_decision
    from src.activities.update_trust import update_vendor_trust
    from src.activities.process_payment import process_payment
    from src.lib.events import EventProducer
    from src.domain.models import InvoiceResult, InvoiceStatus, Decision

logger = logging.getLogger(__name__)


@workflow.defn
class InvoiceProcessingWorkflow:
    """
    Complete invoice processing workflow.

    Orchestration:
    1. Extract invoice using Docling (Markdown → Structured data)
    2. Get vendor trust battery
    3. Calculate risk score (amount + pattern + trust)
    4. Make decision (APPROVE / REVIEW / REJECT)
    5. Execute payment (if approved)
    6. Update trust battery
    7. Emit events
    """

    def __init__(self):
        self._status = InvoiceStatus.INGESTED
        self._invoice_id: str = ""
        self._decision: Decision = Decision.REVIEW
        self._risk_score: float = 0.0

    @workflow.run
    async def run(
        self,
        file_url: str,
        invoice_id: str = None,
        uploaded_by: str = "system",
    ) -> Dict[str, Any]:
        """
        Execute complete invoice processing workflow.

        Args:
            file_url: URL to invoice file (PDF, image, etc.)
            invoice_id: Optional invoice ID (generated if not provided)
            uploaded_by: User who uploaded the invoice

        Returns:
            InvoiceResult with complete processing details
        """
        self._invoice_id = invoice_id or workflow.uuid4()

        workflow.logger.info(
            f"🚀 Starting workflow for invoice: {self._invoice_id}, file: {file_url}"
        )

        # Step 1: Extract invoice data using Docling
        self._status = InvoiceStatus.EXTRACTING

        try:
            invoice_data = await workflow.execute_activity(
                extract_invoice_with_docling,
                file_url,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=5),
                    maximum_attempts=3,
                    non_retryable_error_types=["VisionExtractionError"],
                ),
            )
        except Exception as e:
            workflow.logger.error(f"❌ Extraction failed: {e}")
            self._status = InvoiceStatus.FAILED
            return self._create_result(error=str(e))

        workflow.logger.info(
            f"📄 Extracted invoice: {invoice_data['invoice_number']} "
            f"from {invoice_data['vendor_name']}, "
            f"amount: ${invoice_data['total_amount']}"
        )

        # Step 2: Get vendor trust battery
        trust_battery = await workflow.execute_activity(
            get_vendor_trust_activity,
            invoice_data["vendor_id"],
            start_to_close_timeout=timedelta(seconds=5),
        )

        workflow.logger.info(
            f"🔋 Vendor trust level: {trust_battery['level_name']} "
            f"({trust_battery['successful_payments']} successful payments)"
        )

        # Step 3: Calculate comprehensive risk score
        self._status = InvoiceStatus.RISK_CHECKING

        risk_result = await workflow.execute_activity(
            calculate_risk_score,
            {
                "invoice_data": invoice_data,
                "trust_battery": trust_battery,
            },
            start_to_close_timeout=timedelta(seconds=10),
        )

        self._risk_score = risk_result["overall_score"]
        reasons = risk_result.get("reasons", [])

        workflow.logger.info(
            f"⚠️  Risk score: {self._risk_score:.2f}, reasons: {len(reasons)}"
        )
        for reason in reasons[:3]:  # Log top 3 reasons
            workflow.logger.info(f"   - {reason}")

        # Step 4: Make decision
        decision_result = await workflow.execute_activity(
            make_invoice_decision,
            {
                "invoice_data": invoice_data,
                "risk_score": risk_result,
                "trust_battery": trust_battery,
            },
            start_to_close_timeout=timedelta(seconds=5),
        )

        self._decision = Decision(decision_result["decision"])

        workflow.logger.info(
            f"🤖 Decision: {self._decision.value}, "
            f"reason: {decision_result.get('reason', 'N/A')}"
        )

        # Step 5: Execute payment (if approved)
        payment_result = None
        if self._decision == Decision.APPROVE:
            self._status = InvoiceStatus.PAYING

            try:
                payment_result = await workflow.execute_activity(
                    process_payment,
                    {
                        "invoice_id": self._invoice_id,
                        "vendor_id": invoice_data["vendor_id"],
                        "amount": invoice_data["total_amount"],
                        "currency": invoice_data.get("currency", "USD"),
                    },
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=5),
                        maximum_interval=timedelta(seconds=30),
                        maximum_attempts=5,
                    ),
                )

                self._status = InvoiceStatus.PAID
                workflow.logger.info(
                    f"✅ Payment processed: {payment_result['reference']}"
                )

            except Exception as e:
                workflow.logger.error(f"❌ Payment failed: {e}")
                self._status = InvoiceStatus.FAILED
                return self._create_result(
                    error=f"Payment failed: {e}",
                    invoice_data=invoice_data,
                )
        else:
            self._status = InvoiceStatus.REVIEW_REQUIRED

        # Step 6: Update vendor trust battery
        trust_outcome = self._determine_trust_outcome(
            self._decision, payment_result is not None
        )

        updated_trust = await workflow.execute_activity(
            update_vendor_trust,
            {
                "vendor_id": invoice_data["vendor_id"],
                "outcome": trust_outcome.value,
                "amount": invoice_data["total_amount"],
            },
            start_to_close_timeout=timedelta(seconds=5),
        )

        workflow.logger.info(
            f"🔋 Updated trust: level={updated_trust['level_name']}, "
            f"payments={updated_trust['successful_payments']}"
        )

        # Step 7: Emit events
        try:
            await workflow.execute_activity(
                emit_invoice_event_activity,
                {
                    "invoice_id": self._invoice_id,
                    "status": self._status.value,
                    "vendor_id": invoice_data["vendor_id"],
                    "amount": invoice_data["total_amount"],
                    "risk_score": self._risk_score,
                    "decision": self._decision.value,
                    "payment_reference": payment_result.get("reference")
                    if payment_result
                    else None,
                },
                start_to_close_timeout=timedelta(seconds=5),
            )
        except Exception as e:
            workflow.logger.warning(f"⚠️  Event emission failed (non-critical): {e}")

        # Return final result
        return self._create_result(
            invoice_data=invoice_data,
            payment_result=payment_result,
        )

    def _determine_trust_outcome(
        self, decision: Decision, payment_executed: bool
    ) -> Any:
        """Determine trust outcome based on decision and payment status."""
        from src.domain.models import TrustOutcome

        if decision == Decision.APPROVE and payment_executed:
            return TrustOutcome.PAYMENT_SUCCESS
        elif decision == Decision.REJECT:
            return TrustOutcome.MANUAL_REVIEW_REJECTED
        else:
            return TrustOutcome.MANUAL_REVIEW_APPROVED

    def _create_result(
        self,
        invoice_data: Dict = None,
        payment_result: Dict = None,
        error: str = None,
    ) -> Dict[str, Any]:
        """Create workflow result."""
        result = {
            "invoice_id": self._invoice_id,
            "status": self._status.value,
            "decision": self._decision.value,
            "risk_score": self._risk_score,
            "processed_at": workflow.now().isoformat(),
        }

        if invoice_data:
            result.update(
                {
                    "vendor_name": invoice_data.get("vendor_name"),
                    "vendor_id": invoice_data.get("vendor_id"),
                    "total_amount": invoice_data.get("total_amount"),
                    "invoice_number": invoice_data.get("invoice_number"),
                    "currency": invoice_data.get("currency", "USD"),
                }
            )

        if payment_result:
            result.update(
                {
                    "payment_reference": payment_result.get("reference"),
                    "payment_amount": payment_result.get("amount"),
                }
            )

        if error:
            result["error"] = error

        return result

    @workflow.query
    def get_status(self) -> str:
        """Query current workflow status."""
        return self._status.value

    @workflow.query
    def get_decision(self) -> str:
        """Query current decision."""
        return self._decision.value

    @workflow.query
    def get_risk_score(self) -> float:
        """Query current risk score."""
        return self._risk_score


# Activity implementations


async def get_vendor_trust_activity(vendor_id: str) -> Dict[str, Any]:
    """Activity: Get vendor trust battery."""
    from src.config.factory import get_db
    from src.domain.trust_battery import TrustBatteryService

    db = get_db()
    service = TrustBatteryService(db)

    battery = await service.get_vendor_trust(vendor_id)
    return battery.to_dict()


async def emit_invoice_event_activity(event_data: Dict) -> Dict:
    """Activity: Emit invoice event to Kafka."""
    import os

    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    topic = os.getenv("KAFKA_TOPIC", "invoice.processed")

    producer = EventProducer(bootstrap_servers=bootstrap_servers, topic=topic)

    await producer.start()
    try:
        await producer.produce(event_data, key=event_data.get("invoice_id"))
        logger.info(f"📤 Emitted event for invoice: {event_data.get('invoice_id')}")
        return {"status": "success", "topic": topic}
    finally:
        await producer.stop()
