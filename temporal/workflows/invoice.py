"""Temporal workflow for invoice processing."""

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

from temporal.schemas import InvoiceInput, ProcessingResult
from temporal.activities.agents import analyst_evaluate, critic_review
from temporal.activities.anomaly import detect_anomaly


@workflow.defn
class InvoiceProcessingWorkflow:
    """Main workflow for processing invoices."""

    def __init__(self):
        self._status = "STARTED"
        self._approval_result = None

    @workflow.run
    async def run(self, invoice_input: InvoiceInput) -> ProcessingResult:
        """Execute invoice processing workflow."""
        workflow.logger.info(
            f"Starting workflow for invoice: {invoice_input.invoice_id}"
        )
        self._status = "PROCESSING"

        # Step 1: Anomaly detection
        self._status = "ANOMALY_CHECK"
        anomaly_result = await workflow.execute_activity(
            detect_anomaly,
            {
                "amount": invoice_input.total_amount,
                "vendor_id": invoice_input.vendor_name,
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )

        # Step 2: Analyst evaluation
        self._status = "ANALYST_EVAL"
        analyst_result = await workflow.execute_activity(
            analyst_evaluate,
            {
                "vendor_name": invoice_input.vendor_name,
                "total_amount": invoice_input.total_amount,
                "invoice_number": invoice_input.invoice_number,
                "due_date": invoice_input.due_date,
                "currency": invoice_input.currency,
                "overall_confidence": 0.95,
            },
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1), maximum_attempts=3
            ),
        )

        # Step 3: Critic review
        self._status = "CRITIC_REVIEW"
        critic_result = await workflow.execute_activity(
            critic_review,
            {"invoice_data": invoice_input, "analyst_proposal": analyst_result},
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Step 4: Determine action
        if (
            analyst_result.proposed_action == "HITL_REQUIRED"
            or not critic_result["can_proceed"]
        ):
            self._status = "AWAITING_APPROVAL"

            # Wait for human approval signal
            await workflow.wait_condition(
                lambda: self._approval_result is not None, timeout=timedelta(hours=48)
            )

            final_action = (
                "APPROVED" if self._approval_result.get("approved") else "REJECTED"
            )
        else:
            final_action = analyst_result.proposed_action

        # Finalize
        self._status = "COMPLETED"

        return ProcessingResult(
            invoice_id=invoice_input.invoice_id,
            status=final_action,
            anomaly_score=anomaly_result["score"],
            analyst_confidence=analyst_result.confidence,
            critic_risk_score=critic_result["risk_score"],
            approved=self._approval_result.get("approved")
            if self._approval_result
            else None,
            approver_comments=self._approval_result.get("comments")
            if self._approval_result
            else None,
        )

    @workflow.signal
    async def approval_response(self, approved: bool, comments: str = ""):
        """Receive human approval decision."""
        workflow.logger.info(f"Received approval signal: approved={approved}")
        self._approval_result = {
            "approved": approved,
            "comments": comments,
            "timestamp": workflow.now(),
        }

    @workflow.query
    def get_status(self) -> str:
        """Query current workflow status."""
        return self._status
