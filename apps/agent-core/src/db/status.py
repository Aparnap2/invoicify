"""
Direct Postgres status updater.

Replaces src/utils/edge_callback.py which called Cloudflare Worker at
http://host.docker.internal:8787 — broken in Azure Container Apps.

Usage:
    from src.db.status import update_invoice_status
    
    await update_invoice_status(
        trace_id="trace-123",
        status="APPROVED",
        metadata={"quickbooks_id": "qb-456"}
    )
"""

from __future__ import annotations

import asyncpg
import json
import structlog
from typing import Optional, Dict, Any
from src.config import get_settings

logger = structlog.get_logger()


async def update_invoice_status(
    trace_id: str,
    status: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write invoice status directly to Postgres.
    
    Idempotent: updates existing row, does not insert duplicates.
    Logs errors but never crashes the pipeline over a status write failure.
    
    Args:
        trace_id: Unique correlation ID from pipeline
        status: New status (APPROVED, REJECTED, ERROR, PAID, etc.)
        metadata: Optional JSON metadata (quickbooks_id, extracted_data, etc.)
    
    Replaces the old edge_callback.update_invoice_status() which
    called the Cloudflare Worker — that URL is unreachable in
    Azure Container Apps.
    """
    settings = get_settings()
    log = logger.bind(trace_id=trace_id, status=status)
    
    try:
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute(
                """
                UPDATE invoices
                SET    status     = $1,
                       updated_at = NOW(),
                       metadata   = COALESCE($2::jsonb, metadata)
                WHERE  trace_id   = $3
                """,
                status,
                json.dumps(metadata) if metadata else None,
                trace_id,
            )
            log.info("invoice_status_updated")
        finally:
            await conn.close()
    
    except Exception as e:
        # Log but never crash the pipeline over a status write failure
        log.error("invoice_status_update_failed", error=str(e))
