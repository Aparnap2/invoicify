"""
QStash Durable Queue + Retry Logic.

QStash provides:
- Guaranteed delivery (retries with exponential backoff)
- Scheduled jobs (CRON)
- Dead letter queue (DLQ)
- Idempotency via deduplication keys

Free Tier: 1,000 messages/day
Strategy: Batch invoices to protect quota (10 invoices/batch = 10k invoices/day)

Usage:
    from src.queue.qstash_publisher import enqueue_invoice_batch
    
    await enqueue_invoice_batch([
        {"invoice_id": "123", "blob_url": "..."},
        {"invoice_id": "456", "blob_url": "..."},
    ])
"""

import os
import json
import time
import structlog
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = structlog.get_logger()

# QStash configuration
QSTASH_TOKEN = os.getenv("QSTASH_TOKEN")
QSTASH_BASE_URL = "https://qstash.upstash.io"
AGENT_CORE_BASE_URL = os.getenv("AGENT_CORE_BASE_URL", "http://localhost:8000")

# Free tier protection
BATCH_SIZE = int(os.getenv("QSTASH_BATCH_SIZE", "10"))  # 10 invoices per message
MAX_DAILY_MESSAGES = int(os.getenv("QSTASH_MAX_DAILY_MESSAGES", "1000"))


class QStashPublisher:
    """
    QStash publisher with batching and idempotency.
    
    Protects free tier quota (1,000 msg/day) by batching invoices.
    """
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize QStash publisher.
        
        Args:
            token: QStash token (from env if not provided)
        """
        self.token = token or QSTASH_TOKEN
        self.enabled = bool(self.token)
        
        if not self.enabled:
            logger.warning("qstash_disabled_using_mock")
    
    async def publish(
        self,
        url: str,
        body: Dict[str, Any],
        deduplication_id: Optional[str] = None,
        retries: int = 3,
        delay_seconds: int = 0,
    ) -> Optional[str]:
        """
        Publish message to QStash.
        
        Args:
            url: Webhook URL to call
            body: Message body
            deduplication_id: Idempotency key (prevents duplicates)
            retries: Number of retry attempts
            delay_seconds: Delay before first delivery
        
        Returns:
            Message ID if successful, None if disabled
        """
        if not self.enabled:
            # Mock mode - just log
            logger.info(
                "qstash_mock_publish",
                url=url,
                body_keys=list(body.keys()),
                deduplication_id=deduplication_id,
            )
            return f"mock-{int(time.time())}"
        
        import httpx
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Upstash-Retries": str(retries),
            "Upstash-Retry-Delay": "exponential",
        }
        
        if deduplication_id:
            headers["Upstash-Deduplication-Id"] = deduplication_id
        
        if delay_seconds > 0:
            headers["Upstash-Delay"] = f"{delay_seconds}s"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{QSTASH_BASE_URL}/v2/publish/{url}",
                    json=body,
                    headers=headers,
                )
                response.raise_for_status()
                
                result = response.json()
                message_id = result.get("messageId")
                
                logger.info(
                    "qstash_published",
                    message_id=message_id,
                    url=url,
                    deduplication_id=deduplication_id,
                )
                
                return message_id
                
        except Exception as e:
            logger.error("qstash_publish_failed", error=str(e), url=url)
            raise
    
    async def publish_batch(
        self,
        url: str,
        batches: List[Dict[str, Any]],
        base_deduplication_id: str,
    ) -> List[Optional[str]]:
        """
        Publish multiple batches to QStash.
        
        Args:
            url: Webhook URL
            batches: List of batch payloads
            base_deduplication_id: Base ID for deduplication
        
        Returns:
            List of message IDs
        """
        message_ids = []
        
        for i, batch in enumerate(batches):
            dedup_id = f"{base_deduplication_id}-batch-{i}"
            message_id = await self.publish(
                url=url,
                body=batch,
                deduplication_id=dedup_id,
            )
            message_ids.append(message_id)
        
        return message_ids
    
    async def schedule(
        self,
        url: str,
        body: Dict[str, Any],
        cron: str,
        deduplication_id: str,
    ) -> Optional[str]:
        """
        Schedule recurring job with QStash CRON.
        
        Args:
            url: Webhook URL
            body: Message body
            cron: CRON expression (e.g., "30 17 * * *" for 11 PM IST)
            deduplication_id: Idempotency key
        
        Returns:
            Schedule ID if successful
        """
        if not self.enabled:
            logger.info("qstash_mock_schedule", url=url, cron=cron)
            return f"mock-schedule-{int(time.time())}"
        
        import httpx
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{QSTASH_BASE_URL}/v2/schedules",
                    json={
                        "url": url,
                        "body": json.dumps(body),
                        "cron": cron,
                        "deduplicationId": deduplication_id,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                
                result = response.json()
                schedule_id = result.get("scheduleId")
                
                logger.info(
                    "qstash_scheduled",
                    schedule_id=schedule_id,
                    cron=cron,
                    url=url,
                )
                
                return schedule_id
                
        except Exception as e:
            logger.error("qstash_schedule_failed", error=str(e), cron=cron)
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────

_publisher: Optional[QStashPublisher] = None


def get_publisher() -> QStashPublisher:
    """Get or create QStash publisher singleton."""
    global _publisher
    if _publisher is None:
        _publisher = QStashPublisher()
    return _publisher


async def enqueue_invoice_batch(
    invoices: List[Dict[str, Any]],
    tenant_id: str,
) -> List[Optional[str]]:
    """
    Enqueue invoice batch for processing.
    
    Batches invoices to protect QStash quota (10 invoices/message).
    
    Args:
        invoices: List of invoice data
        tenant_id: Tenant identifier
    
    Returns:
        List of message IDs
    """
    publisher = get_publisher()
    
    # Group invoices into batches
    batches = []
    for i in range(0, len(invoices), BATCH_SIZE):
        batch = invoices[i:i + BATCH_SIZE]
        batches.append({
            "type": "invoice_batch",
            "tenant_id": tenant_id,
            "invoices": batch,
            "batch_size": len(batch),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    
    # Publish batches
    base_dedup_id = f"invoice-batch-{tenant_id}-{int(time.time())}"
    message_ids = await publisher.publish_batch(
        url=f"{AGENT_CORE_BASE_URL}/api/internal/process-batch",
        batches=batches,
        base_deduplication_id=base_dedup_id,
    )
    
    logger.info(
        "invoice_batch_enqueued",
        tenant_id=tenant_id,
        total_invoices=len(invoices),
        batches=len(batches),
        message_ids=len([m for m in message_ids if m]),
    )
    
    return message_ids


async def enqueue_single_invoice(
    invoice_id: str,
    blob_url: str,
    tenant_id: str,
    priority: str = "STANDARD",
) -> Optional[str]:
    """
    Enqueue single invoice for processing.
    
    Args:
        invoice_id: Invoice identifier
        blob_url: Blob storage URL
        tenant_id: Tenant identifier
        priority: Priority level (URGENT/FAST_LANE/STANDARD)
    
    Returns:
        Message ID if successful
    """
    publisher = get_publisher()
    
    # URGENT invoices bypass queue (direct function call)
    if priority == "URGENT":
        logger.info("urgent_invoice_bypassing_queue", invoice_id=invoice_id)
        return None
    
    dedup_id = f"invoice-{invoice_id}"
    message_id = await publisher.publish(
        url=f"{AGENT_CORE_BASE_URL}/api/internal/process-single",
        body={
            "type": "invoice_single",
            "invoice_id": invoice_id,
            "blob_url": blob_url,
            "tenant_id": tenant_id,
            "priority": priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        deduplication_id=dedup_id,
    )
    
    logger.info(
        "invoice_enqueued",
        invoice_id=invoice_id,
        message_id=message_id,
        priority=priority,
    )
    
    return message_id


async def schedule_nightly_reconciliation() -> Optional[str]:
    """
    Schedule nightly reconciliation job.
    
    Runs every night at 11 PM IST (5:30 PM UTC).
    Reconciles all PENDING invoices older than 24 hours.
    
    Returns:
        Schedule ID if successful
    """
    publisher = get_publisher()
    
    schedule_id = await publisher.schedule(
        url=f"{AGENT_CORE_BASE_URL}/api/internal/reconcile",
        body={
            "type": "reconciliation",
            "trigger": "scheduled",
        },
        cron="30 17 * * *",  # 11 PM IST
        deduplication_id="nightly-reconciliation",
    )
    
    logger.info("nightly_reconciliation_scheduled", schedule_id=schedule_id)
    
    return schedule_id


async def enqueue_retry(
    invoice_id: str,
    reason: str,
    delay_seconds: int = 300,  # 5 minutes
    max_retries: int = 2,
) -> Optional[str]:
    """
    Enqueue failed invoice for retry.
    
    Args:
        invoice_id: Invoice identifier
        reason: Failure reason
        delay_seconds: Delay before retry
        max_retries: Maximum retry attempts
    
    Returns:
        Message ID if successful
    """
    publisher = get_publisher()
    
    dedup_id = f"retry-{invoice_id}-{int(time.time())}"
    message_id = await publisher.publish(
        url=f"{AGENT_CORE_BASE_URL}/api/internal/process-single",
        body={
            "type": "invoice_retry",
            "invoice_id": invoice_id,
            "retry_reason": reason,
            "retry_count": 1,
            "max_retries": max_retries,
        },
        deduplication_id=dedup_id,
        delay_seconds=delay_seconds,
        retries=max_retries,
    )
    
    logger.info(
        "retry_enqueued",
        invoice_id=invoice_id,
        message_id=message_id,
        delay_seconds=delay_seconds,
    )
    
    return message_id
