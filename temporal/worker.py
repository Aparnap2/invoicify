"""
Temporal Worker Entry Point for Invoicify
Registers all workflows and activities with Temporal server.
"""

import asyncio
import logging
import os
from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

from temporal.workflows.invoice import InvoiceProcessingWorkflow
from temporal.activities.agents import analyst_evaluate, critic_review
from temporal.activities.anomaly import detect_anomaly

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Start the Temporal worker."""
    # Temporal connection configuration
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
    temporal_cert_path = os.getenv("TEMPORAL_CERT_PATH")
    temporal_key_path = os.getenv("TEMPORAL_KEY_PATH")

    # Configure TLS if certificates are provided (for Temporal Cloud)
    tls_config = None
    if temporal_cert_path and temporal_key_path:
        logger.info(f"Configuring mTLS for Temporal Cloud: {temporal_host}")
        try:
            with open(temporal_cert_path, "rb") as cert_file:
                client_cert = cert_file.read()
            with open(temporal_key_path, "rb") as key_file:
                client_key = key_file.read()
            
            tls_config = TLSConfig(
                client_cert=client_cert,
                client_private_key=client_key,
            )
        except Exception as e:
            logger.error(f"Failed to load TLS certificates: {e}")
            raise
    else:
        logger.info(f"Connecting to local Temporal: {temporal_host}")

    # Connect to Temporal
    logger.info(f"Connecting to Temporal at {temporal_host}...")
    try:
        client = await Client.connect(
            temporal_host,
            namespace=temporal_namespace,
            tls=tls_config,
        )
    except Exception as e:
        logger.error(f"Failed to connect to Temporal at {temporal_host}: {e}")
        raise

    logger.info("Connected to Temporal. Starting worker...")

    # Create worker with all workflows and activities
    worker = Worker(
        client,
        task_queue="invoice-processing",
        workflows=[InvoiceProcessingWorkflow],
        activities=[
            analyst_evaluate,
            critic_review,
            detect_anomaly,
        ],
    )

    logger.info("Worker started. Listening on task queue: invoice-processing")

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
