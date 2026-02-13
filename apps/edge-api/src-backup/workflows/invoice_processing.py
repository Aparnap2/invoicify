"""
Temporal Workflow Implementation (TDD - Step 5)
GREEN phase: Implementation to make tests pass
"""

import logging
from datetime import timedelta
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    import sys

    sys.path.insert(0, "/home/aparna/Desktop/invoicify/python-worker/src")
    from activities.extract import (
        extract_invoice_data,
        VisionAPIError,
    )
    from activities.anomaly import AnomalyDetector
    from lib.events import EventProducer

logger = logging.getLogger(__name__)


@workflow.defn
class InvoiceProcessingWorkflow:
    """
    Main workflow for processing invoices.

    Orchestrates:
    1. Vision extraction from file URL
    2. Anomaly detection on invoice amount
    3. Decision logic (APPROVED vs REVIEW_REQUIRED)
    4. Event emission for downstream processing
    """

    def __init__(self):
        self._status = "STARTED"

    @workflow.run
    async def run(self, file_url: str) -> Dict[str, Any]:
        """
        Execute invoice processing workflow.

        Args:
            file_url: URL to invoice file

        Returns:
            Dict with processing result
        """
        workflow.logger.info(f"Starting workflow for file: {file_url}")
        self._status = "EXTRACTING"

        # Step 1: Extract invoice data using Vision API
        try:
            extraction_result = await workflow.execute_activity(
                extract_invoice_data,
                file_url,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=5),
                    maximum_attempts=3,
                    non_retryable_error_types=["VisionAPIError"],
                ),
            )
        except Exception as e:
            workflow.logger.error(f"Extraction failed: {e}")
            raise

        workflow.logger.info(
            f"Extracted invoice: {extraction_result['invoice_number']} "
            f"from {extraction_result['vendor_name']}"
        )

        # Step 2: Anomaly detection on invoice amount
        self._status = "ANALYZING"

        # Import here to avoid circular imports
        import sys

        sys.path.insert(0, "/home/aparna/Desktop/invoicify/python-worker/src")
        from activities.anomaly import detect_anomaly_activity, learn_anomaly_activity

        risk_score = await workflow.execute_activity(
            detect_anomaly_activity,
            extraction_result["total_amount"],
            start_to_close_timeout=timedelta(seconds=5),
        )

        # Learn from this invoice for future anomaly detection
        await workflow.execute_activity(
            learn_anomaly_activity,
            extraction_result["total_amount"],
            start_to_close_timeout=timedelta(seconds=5),
        )

        workflow.logger.info(
            f"Anomaly score for {extraction_result['vendor_name']}: {risk_score:.4f}"
        )

        # Step 3: Decision logic
        self._status = "DECIDING"

        if risk_score < 0.3:
            status = "APPROVED"
            workflow.logger.info(
                f"Auto-approved invoice {extraction_result['invoice_number']}"
            )
        elif risk_score < 0.8:
            status = "REVIEW_REQUIRED"
            workflow.logger.info(
                f"Flagged invoice {extraction_result['invoice_number']} for review"
            )
        else:
            status = "REJECTED"
            workflow.logger.warning(
                f"Rejected suspicious invoice {extraction_result['invoice_number']}"
            )

        # Step 4: Emit event for downstream processing
        self._status = "EMITTING"

        event_data = {
            "invoice_number": extraction_result["invoice_number"],
            "vendor_name": extraction_result["vendor_name"],
            "total_amount": extraction_result["total_amount"],
            "risk_score": risk_score,
            "status": status,
            "file_url": file_url,
        }

        try:
            await workflow.execute_activity(
                emit_invoice_processed_event,
                event_data,
                start_to_close_timeout=timedelta(seconds=5),
            )
        except Exception as e:
            workflow.logger.warning(f"Failed to emit event (non-critical): {e}")

        self._status = "COMPLETED"

        # Return result
        return {
            "status": status,
            "risk_score": risk_score,
            "vendor_name": extraction_result["vendor_name"],
            "total_amount": extraction_result["total_amount"],
            "invoice_number": extraction_result["invoice_number"],
            "due_date": extraction_result.get("due_date"),
            "currency": extraction_result.get("currency", "USD"),
            "confidence": extraction_result.get("confidence", 0.0),
        }

    @workflow.query
    def get_status(self) -> str:
        """Query current workflow status."""
        return self._status


async def emit_invoice_processed_event(event_data: dict) -> dict:
    """
    Activity to emit invoice processed event to Kafka.

    Args:
        event_data: Event data to emit

    Returns:
        Dict with emission status
    """
    import os

    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    topic = os.getenv("KAFKA_TOPIC", "invoice.processed")

    producer = EventProducer(bootstrap_servers=bootstrap_servers, topic=topic)

    await producer.start()
    try:
        await producer.produce(event_data, key=event_data.get("invoice_number"))
        logger.info(f"Emitted event for invoice: {event_data.get('invoice_number')}")
        return {"status": "success", "topic": topic}
    finally:
        await producer.stop()
