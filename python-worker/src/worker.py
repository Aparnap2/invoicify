"""
Temporal Worker Entry Point
Registers all workflows and activities with Temporal server.
"""

import asyncio
import logging
import os
from temporalio.client import Client
from temporalio.worker import Worker

from python_worker.src.workflows.invoice_processing import (
    InvoiceProcessingWorkflow,
    emit_invoice_processed_event,
)
from python_worker.src.activities.extract import extract_invoice_data
from python_worker.src.activities.anomaly import AnomalyDetector

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Start Temporal worker."""
    # Connect to Temporal server
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}...")

    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    logger.info(f"Connected to Temporal. Starting worker...")

    # Create anomaly detector instance for reuse
    # Note: In production, each activity gets its own instance
    # This is just for registration
    detector = AnomalyDetector(vendor_id="default")

    # Create worker
    worker = Worker(
        client,
        task_queue="invoice-processing-queue",
        workflows=[InvoiceProcessingWorkflow],
        activities=[
            extract_invoice_data,
            detector.score,
            detector.learn,
            detector.is_anomaly,
            emit_invoice_processed_event,
        ],
    )

    logger.info("Worker started. Listening for tasks...")

    # Run worker
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
