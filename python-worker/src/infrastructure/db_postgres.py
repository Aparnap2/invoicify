"""
PostgreSQL Database Adapter (Standard/Free Tier)
Uses asyncpg for async PostgreSQL operations
"""

import logging
from typing import Any, Dict, List, Optional
import asyncpg

from src.interfaces import DatabaseAdapter

logger = logging.getLogger(__name__)


class PostgresAdapter(DatabaseAdapter):
    """
    Standard PostgreSQL adapter using asyncpg.
    Compatible with Supabase, standard PostgreSQL, and any Postgres-compatible DB.
    """

    def __init__(self, connection_url: str):
        """
        Initialize PostgreSQL adapter.

        Args:
            connection_url: PostgreSQL connection URL
        """
        self.connection_url = connection_url
        self.pool: Optional[asyncpg.Pool] = None
        logger.info("Initialized PostgresAdapter (Standard Mode)")

    async def connect(self) -> None:
        """Create connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_url, min_size=1, max_size=10
            )
            logger.info("Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from PostgreSQL")

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def save_invoice(self, invoice_data: Dict[str, Any]) -> str:
        """
        Save invoice to database.

        Args:
            invoice_data: Invoice data dictionary

        Returns:
            Invoice ID
        """
        query = """
        INSERT INTO invoices (
            vendor_name, invoice_number, total_amount, 
            due_date, currency, confidence, status, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                invoice_id = await conn.fetchval(
                    query,
                    invoice_data.get("vendor_name"),
                    invoice_data.get("invoice_number"),
                    invoice_data.get("total_amount"),
                    invoice_data.get("due_date"),
                    invoice_data.get("currency", "USD"),
                    invoice_data.get("confidence", 0.0),
                    invoice_data.get("status", "NEW"),
                )
                logger.info(f"Saved invoice: {invoice_id}")
                return str(invoice_id)
        except Exception as e:
            logger.error(f"Failed to save invoice: {e}")
            raise

    async def get_vendor_history(
        self, vendor_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get historical invoices for a vendor.

        Args:
            vendor_id: Vendor identifier
            limit: Maximum number of records

        Returns:
            List of invoice records
        """
        query = """
        SELECT * FROM invoices 
        WHERE vendor_name = $1 
        ORDER BY created_at DESC 
        LIMIT $2
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, vendor_id, limit)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get vendor history: {e}")
            return []

    async def update_vendor_trust(self, vendor_id: str, trust_level: int) -> None:
        """
        Update vendor trust level.

        Args:
            vendor_id: Vendor identifier
            trust_level: New trust level (1-3)
        """
        query = """
        INSERT INTO vendors (name, trust_level, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (name) DO UPDATE 
        SET trust_level = $2, updated_at = NOW()
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, vendor_id, trust_level)
                logger.info(f"Updated trust level for {vendor_id}: {trust_level}")
        except Exception as e:
            logger.error(f"Failed to update vendor trust: {e}")
            raise

    async def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve invoice by ID.

        Args:
            invoice_id: Invoice identifier

        Returns:
            Invoice data or None
        """
        query = "SELECT * FROM invoices WHERE id = $1"

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, int(invoice_id))
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get invoice: {e}")
            return None
