"""
Temporal Worker Entry Point
Registers all workflows and activities with Temporal server.
"""

import asyncio
import logging
import os
from temporalio.client import Client
from temporalio.worker import Worker

from src.workflows.invoice_processing import (
    InvoiceProcessingWorkflow,
    emit_invoice_processed_event,
)
from src.workflows.invoice_workflow import (
    InvoiceProcessingWorkflow as NewInvoiceProcessingWorkflow,
)
from src.activities.extract import extract_invoice_data
from src.activities.anomaly import AnomalyDetector

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Stateless activity wrappers for AnomalyDetector
# Creates a new detector instance per invocation to avoid cross-request state
async def score_invoice(amount: float) -> float:
    """Activity wrapper: Score invoice using fresh AnomalyDetector instance."""
    detector = AnomalyDetector(vendor_id="default")
    return detector.score(amount)


async def learn_invoice(amount: float) -> None:
    """Activity wrapper: Learn from invoice using fresh AnomalyDetector instance."""
    detector = AnomalyDetector(vendor_id="default")
    detector.learn(amount)


async def check_anomaly(amount: float) -> bool:
    """Activity wrapper: Check anomaly using fresh AnomalyDetector instance."""
    detector = AnomalyDetector(vendor_id="default")
    return detector.is_anomaly(amount)


async def main():
    """Start Temporal worker."""
    # Connect to Temporal server
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}...")

    try:
        client = await Client.connect(temporal_host, namespace=temporal_namespace)
    except Exception as e:
        logger.error(f"Failed to connect to Temporal at {temporal_host}: {e}")
        raise

    logger.info("Connected to Temporal. Starting worker...")

    # Create worker with stateless activity wrappers
    worker = Worker(
        client,
        task_queue="invoice-processing-queue",
        workflows=[InvoiceProcessingWorkflow, NewInvoiceProcessingWorkflow],
        activities=[
            extract_invoice_data,
            score_invoice,  # Stateless wrapper
            learn_invoice,  # Stateless wrapper
            check_anomaly,  # Stateless wrapper
            emit_invoice_processed_event,
        ],
    )

    logger.info("Worker started. Listening for tasks...")

    # Run worker with error handling
    try:
        await worker.run()
    except Exception as e:
        logger.error(f"Worker stopped unexpectedly: {e}")
        raise
    finally:
        await client.close()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
