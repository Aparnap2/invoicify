"""
Database helpers for AP Workflow using asyncpg.

Provides async database operations for:
- Idempotency checks
- Invoice CRUD
- Vendor lookups
- Audit logging
- Human task management

Connection pooling via asyncpg for Azure PostgreSQL.
"""

import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

import asyncpg
import structlog
from pydantic import BaseModel

from src.config import get_settings

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Connection Pool Management
# ─────────────────────────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=str(settings.database_url),
            min_size=2,
            max_size=10,
        )
        logger.info("db_pool_created")
    return _pool


async def close_pool() -> None:
    """Close the database connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("db_pool_closed")


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a database connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency Checks
# ─────────────────────────────────────────────────────────────────────────────


async def check_idempotency(idempotency_key: str) -> tuple[bool, Optional[UUID], Optional[str]]:
    """
    Check if an invoice with this idempotency key already exists.
    
    Returns:
        Tuple of (exists, invoice_id, status)
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status FROM invoices 
            WHERE idempotency_key = $1
            """,
            idempotency_key,
        )
        if row:
            return True, row["id"], row["status"]
        return False, None, None


# ─────────────────────────────────────────────────────────────────────────────
# Vendor Operations
# ─────────────────────────────────────────────────────────────────────────────


async def get_or_create_vendor(
    name: str, verified_bank_hash: Optional[str] = None
) -> UUID:
    """
    Get vendor by normalized name or create new.
    
    Returns vendor ID.
    """
    normalized = name.lower().strip()
    
    async with get_connection() as conn:
        # Try to find existing vendor
        existing = await conn.fetchrow(
            "SELECT id FROM vendors WHERE normalized_name = $1", normalized
        )
        if existing:
            return existing["id"]
        
        # Create new vendor
        vendor_id = await conn.fetchval(
            """
            INSERT INTO vendors (name, normalized_name, verified_bank_hash)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            name,
            normalized,
            verified_bank_hash,
        )
        logger.info("vendor_created", vendor_id=vendor_id, name=name)
        return vendor_id


async def get_vendor_by_id(vendor_id: UUID) -> Optional[dict[str, Any]]:
    """Get vendor by ID."""
    async with get_connection() as conn:
        return await conn.fetchrow(
            "SELECT * FROM vendors WHERE id = $1", vendor_id
        )


async def get_vendor_by_name(name: str) -> Optional[dict[str, Any]]:
    """Get vendor by name (normalized)."""
    normalized = name.lower().strip()
    async with get_connection() as conn:
        return await conn.fetchrow(
            "SELECT * FROM vendors WHERE normalized_name = $1", normalized
        )


async def update_vendor_trust_level(vendor_id: UUID, trust_level: int) -> None:
    """Update vendor trust level."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE vendors SET trust_level = $1 WHERE id = $2",
            trust_level,
            vendor_id,
        )


async def update_vendor_bank_hash(vendor_id: UUID, bank_hash: str) -> None:
    """Update vendor's verified bank hash."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE vendors SET verified_bank_hash = $1 WHERE id = $2",
            bank_hash,
            vendor_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Invoice Operations
# ─────────────────────────────────────────────────────────────────────────────


async def create_invoice(
    trace_id: str,
    vendor_id: Optional[UUID],
    vendor_name: str,
    invoice_number: str,
    total: Decimal,
    currency: str,
    invoice_date: date,
    idempotency_key: str,
    extracted_data_json: Optional[str] = None,
) -> UUID:
    """Create a new invoice record."""
    async with get_connection() as conn:
        invoice_id = await conn.fetchval(
            """
            INSERT INTO invoices (
                trace_id, vendor_id, vendor_name, invoice_number,
                total, currency, invoice_date, idempotency_key,
                extracted_data_json, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'new')
            RETURNING id
            """,
            trace_id,
            vendor_id,
            vendor_name,
            invoice_number,
            total,
            currency,
            invoice_date,
            idempotency_key,
            extracted_data_json,
        )
        logger.info("invoice_created", invoice_id=invoice_id, trace_id=trace_id)
        return invoice_id


async def update_invoice_status(
    invoice_id: UUID,
    status: str,
    error_message: Optional[str] = None,
    quickbooks_bill_id: Optional[str] = None,
) -> None:
    """Update invoice status."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE invoices 
            SET status = $1, error_message = $2, quickbooks_bill_id = $3, updated_at = NOW()
            WHERE id = $4
            """,
            status,
            error_message,
            quickbooks_bill_id,
            invoice_id,
        )


async def update_invoice_extracted_data(
    invoice_id: UUID, extracted_data_json: str
) -> None:
    """Update invoice with extracted data."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE invoices 
            SET extracted_data_json = $1, status = 'extracted', updated_at = NOW()
            WHERE id = $2
            """,
            extracted_data_json,
            invoice_id,
        )


async def get_invoice_by_trace_id(trace_id: str) -> Optional[dict[str, Any]]:
    """Get invoice by trace ID."""
    async with get_connection() as conn:
        return await conn.fetchrow(
            "SELECT * FROM invoices WHERE trace_id = $1", trace_id
        )


async def get_invoice_by_id(invoice_id: UUID) -> Optional[dict[str, Any]]:
    """Get invoice by ID."""
    async with get_connection() as conn:
        return await conn.fetchrow("SELECT * FROM invoices WHERE id = $1", invoice_id)


# ─────────────────────────────────────────────────────────────────────────────
# Line Item Operations
# ─────────────────────────────────────────────────────────────────────────────


async def create_invoice_line_items(
    invoice_id: UUID, line_items: list[dict[str, Any]]
) -> None:
    """Create invoice line items."""
    async with get_connection() as conn:
        for item in line_items:
            await conn.execute(
                """
                INSERT INTO invoice_line_items (
                    invoice_id, line_number, description,
                    quantity, unit_price, amount, tax_code, gl_code
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                invoice_id,
                item.get("line_number", 1),
                item.get("description", ""),
                Decimal(str(item.get("quantity", 1))),
                Decimal(str(item.get("unit_price", 0))),
                Decimal(str(item.get("amount", 0))),
                item.get("tax_code"),
                item.get("gl_code"),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Purchase Order Operations
# ─────────────────────────────────────────────────────────────────────────────


async def get_open_purchase_orders(vendor_id: UUID) -> list[dict[str, Any]]:
    """Get all open POs for a vendor."""
    async with get_connection() as conn:
        return await conn.fetch(
            """
            SELECT * FROM purchase_orders 
            WHERE vendor_id = $1 AND status = 'open'
            """,
            vendor_id,
        )


async def get_purchase_order_by_number(po_number: str) -> Optional[dict[str, Any]]:
    """Get PO by number."""
    async with get_connection() as conn:
        return await conn.fetchrow(
            "SELECT * FROM purchase_orders WHERE po_number = $1", po_number
        )


async def get_po_line_items(po_id: UUID) -> list[dict[str, Any]]:
    """Get line items for a PO."""
    async with get_connection() as conn:
        return await conn.fetch(
            "SELECT * FROM po_line_items WHERE po_id = $1 ORDER BY line_number", po_id
        )


# ─────────────────────────────────────────────────────────────────────────────
# Human Task Operations
# ─────────────────────────────────────────────────────────────────────────────


async def create_human_task(
    trace_id: str,
    task_type: str,
    payload_json: dict[str, Any],
    assigned_to: Optional[str] = None,
) -> UUID:
    """Create a new human task."""
    async with get_connection() as conn:
        task_id = await conn.fetchval(
            """
            INSERT INTO human_tasks (trace_id, task_type, payload_json, assigned_to)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            trace_id,
            task_type,
            json.dumps(payload_json),
            assigned_to,
        )
        logger.info("human_task_created", task_id=task_id, task_type=task_type)
        return task_id


async def get_human_task(task_id: UUID) -> Optional[dict[str, Any]]:
    """Get human task by ID."""
    async with get_connection() as conn:
        return await conn.fetchrow("SELECT * FROM human_tasks WHERE id = $1", task_id)


async def get_human_task_by_trace(trace_id: str) -> list[dict[str, Any]]:
    """Get all human tasks for a trace."""
    async with get_connection() as conn:
        return await conn.fetch(
            "SELECT * FROM human_tasks WHERE trace_id = $1 ORDER BY created_at DESC",
            trace_id,
        )


async def update_human_task_status(
    task_id: UUID,
    status: str,
    completed_by: Optional[str] = None,
    comments: Optional[str] = None,
) -> None:
    """Update human task status."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE human_tasks 
            SET status = $1, completed_by = $2, comments = $3, 
                completed_at = CASE WHEN $1 = 'completed' THEN NOW() ELSE completed_at END,
                updated_at = NOW()
            WHERE id = $4
            """,
            status,
            completed_by,
            comments,
            task_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log Operations
# ─────────────────────────────────────────────────────────────────────────────


async def create_audit_log(
    trace_id: str,
    node_name: str,
    input_hash: str,
    output_hash: str,
    status: str,
    details: Optional[dict[str, Any]] = None,
) -> UUID:
    """Create an audit log entry (append-only)."""
    async with get_connection() as conn:
        log_id = await conn.fetchval(
            """
            INSERT INTO audit_logs (trace_id, node_name, input_hash, output_hash, status, details)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            trace_id,
            node_name,
            input_hash,
            output_hash,
            status,
            json.dumps(details) if details else None,
        )
        return log_id


async def get_audit_logs(trace_id: str) -> list[dict[str, Any]]:
    """Get all audit logs for a trace."""
    async with get_connection() as conn:
        return await conn.fetch(
            """
            SELECT * FROM audit_logs 
            WHERE trace_id = $1 
            ORDER BY created_at ASC
            """,
            trace_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate Detection Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def check_invoice_duplicate(content_hash: str) -> tuple[bool, Optional[UUID]]:
    """
    Check if invoice with same content hash exists.
    
    Args:
        content_hash: SHA256 hash of invoice content
        
    Returns:
        Tuple of (exists, invoice_id)
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM invoices WHERE content_hash = $1",
            content_hash,
        )
        return (row is not None, row["id"] if row else None)


async def store_invoice_hash(trace_id: str, content_hash: str) -> None:
    """
    Store invoice content hash.
    
    Args:
        trace_id: Unique trace ID for the invoice
        content_hash: SHA256 hash of invoice content
    """
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE invoices SET content_hash = $1 WHERE trace_id = $2",
            content_hash,
            trace_id,
        )


async def find_potential_duplicates(
    vendor_name: str,
    invoice_number: str,
    total: Decimal,
    invoice_date: date,
    threshold_days: int = 30,
) -> list[dict[str, Any]]:
    """Find potential duplicate invoices."""
    normalized = vendor_name.lower().strip()
    
    async with get_connection() as conn:
        return await conn.fetch(
            """
            SELECT i.*, v.name as vendor_name
            FROM invoices i
            LEFT JOIN vendors v ON i.vendor_id = v.id
            WHERE LOWER(COALESCE(v.name, i.vendor_name)) = $1
              AND i.invoice_number = $2
              AND i.invoice_date >= $3
              AND i.invoice_date <= $4
              AND i.id != (
                  SELECT id FROM invoices 
                  WHERE trace_id = (
                      SELECT trace_id FROM invoices 
                      WHERE vendor_name = $1 AND invoice_number = $2 
                      ORDER BY created_at DESC LIMIT 1
                  )
              )
            """,
            normalized,
            invoice_number,
            invoice_date - datetime.timedelta(days=threshold_days),
            invoice_date + datetime.timedelta(days=threshold_days),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Historical Invoice Lookup
# ─────────────────────────────────────────────────────────────────────────────


async def get_vendor_invoice_history(
    vendor_id: UUID, limit: int = 10
) -> list[dict[str, Any]]:
    """Get recent invoice history for a vendor."""
    async with get_connection() as conn:
        return await conn.fetch(
            """
            SELECT * FROM invoices 
            WHERE vendor_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2
            """,
            vendor_id,
            limit,
        )


async def get_invoices_by_gl_code(
    gl_code: str, vendor_id: UUID, limit: int = 20
) -> list[dict[str, Any]]:
    """Get historical invoices with a specific GL code for a vendor."""
    async with get_connection() as conn:
        return await conn.fetch(
            """
            SELECT i.*, ili.gl_code
            FROM invoices i
            JOIN invoice_line_items ili ON i.id = ili.invoice_id
            WHERE ili.gl_code = $1 
              AND i.vendor_id = $2
            ORDER BY i.created_at DESC
            LIMIT $3
            """,
            gl_code,
            vendor_id,
            limit,
        )
