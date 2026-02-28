"""
Azure Storage Queue consumer for Invoicify agent-core.

Replaces: Upstash Redis queues + Cloudflare Queues binding.
Free tier: Unlimited messages, 64 KB max per message.

Architecture:
    invoicify-worker (Hono) → enqueues message to Azure Storage Queue
    agent-core (this file)  → polls queue, calls run_pipeline()

Message format (JSON):
    {
      "trace_id": "uuid",
      "blob_name": "invoices/2025/INV-001.pdf",
      "blob_url": "https://storage.blob.core.windows.net/invoices/INV-001.pdf?sas"
    }

Idempotency: Each message is processed exactly once (delete-on-success).
Retry: Failed messages go to DLQ after max_dequeue_count=5 (Azure default).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any, Dict, Optional

import structlog
from azure.storage.queue import QueueClient, QueueServiceClient
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

QUEUE_NAME = os.getenv("AZURE_QUEUE_NAME", "invoice-processing")
DLQ_NAME = os.getenv("AZURE_DLQ_NAME", "invoice-dlq")
POLL_INTERVAL_SECONDS = float(os.getenv("QUEUE_POLL_INTERVAL", "5"))
MAX_MESSAGES_PER_BATCH = int(os.getenv("QUEUE_BATCH_SIZE", "4"))
VISIBILITY_TIMEOUT = int(os.getenv("QUEUE_VISIBILITY_TIMEOUT", "300"))  # 5 min


class AzureQueueConsumer:
    """
    Long-running queue consumer.
    Run as a background asyncio task alongside the FastAPI server,
    or as a separate Container App job (recommended for production scale).
    """

    def __init__(self, pipeline_fn) -> None:
        """
        Args:
            pipeline_fn: Coroutine function matching signature:
                async def run_pipeline(trace_id, blob_name, blob_url) -> None
        """
        self.pipeline_fn = pipeline_fn
        self._running = False

        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not conn_str:
            logger.warning("azure_storage_connection_string_missing_queue_disabled")
            self.queue_client: Optional[QueueClient] = None
            self.dlq_client: Optional[QueueClient] = None
        else:
            svc = QueueServiceClient.from_connection_string(conn_str)
            self.queue_client = svc.get_queue_client(QUEUE_NAME)
            self.dlq_client = svc.get_queue_client(DLQ_NAME)
            # Ensure queues exist (idempotent)
            try:
                self.queue_client.create_queue()
            except Exception:
                pass
            try:
                self.dlq_client.create_queue()
            except Exception:
                pass

    async def start(self) -> None:
        """Start the polling loop. Call once at application startup."""
        if not self.queue_client:
            logger.warning("queue_consumer_not_started_no_connection_string")
            return

        self._running = True
        logger.info("azure_queue_consumer_started", queue=QUEUE_NAME, poll_interval=POLL_INTERVAL_SECONDS)

        while self._running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error("queue_poll_error", error=str(e))
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        logger.info("azure_queue_consumer_stopped")

    async def _process_batch(self) -> None:
        messages = self.queue_client.receive_messages(
            max_messages=MAX_MESSAGES_PER_BATCH,
            visibility_timeout=VISIBILITY_TIMEOUT,
        )

        tasks = []
        for msg in messages:
            tasks.append(self._handle_message(msg))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_message(self, message: Any) -> None:
        receipt = message.pop_receipt
        message_id = message.id
        dequeue_count = message.dequeue_count

        try:
            # Azure encodes messages as base64 by default
            content = message.content
            try:
                content = base64.b64decode(content).decode("utf-8")
            except Exception:
                pass  # Not base64 encoded

            payload: Dict[str, Any] = json.loads(content)
            trace_id = payload["trace_id"]
            blob_name = payload.get("blob_name", "")
            blob_url = payload.get("blob_url", "")

            logger.info("queue_message_received", trace_id=trace_id, dequeue_count=dequeue_count)

            # Call the pipeline
            await self.pipeline_fn(trace_id, blob_name, blob_url)

            # Success: delete message from queue
            self.queue_client.delete_message(message_id, receipt)
            logger.info("queue_message_processed", trace_id=trace_id)

        except Exception as e:
            logger.error("queue_message_failed", message_id=message_id, error=str(e), dequeue_count=dequeue_count)

            # Move to DLQ if max retries reached
            if dequeue_count >= 5 and self.dlq_client:
                self.dlq_client.send_message(message.content)
                self.queue_client.delete_message(message_id, receipt)
                logger.error("message_moved_to_dlq", message_id=message_id)
            # Otherwise, let visibility timeout expire so Azure retries automatically


# ── Enqueueing helper (used by the Hono worker via HTTP) ─────────────────────

async def enqueue_invoice(trace_id: str, blob_name: str, blob_url: str) -> None:
    """
    Enqueue an invoice processing job from the agent-core side.
    In practice, the Hono worker enqueues directly via Azure SDK.
    This helper is for testing and direct API calls.
    """
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING not set")

    svc = QueueServiceClient.from_connection_string(conn_str)
    client = svc.get_queue_client(QUEUE_NAME)

    payload = json.dumps({"trace_id": trace_id, "blob_name": blob_name, "blob_url": blob_url})
    client.send_message(base64.b64encode(payload.encode()).decode())
    logger.info("invoice_enqueued", trace_id=trace_id, queue=QUEUE_NAME)
