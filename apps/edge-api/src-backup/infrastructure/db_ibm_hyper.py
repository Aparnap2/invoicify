"""
IBM Hyper Protect PostgreSQL Adapter (Trial/Enterprise)
FIPS-compliant PostgreSQL with SSL certificate handling
"""

import logging
import ssl
from typing import Any, Dict, List, Optional
import asyncpg

from src.interfaces import DatabaseAdapter

logger = logging.getLogger(__name__)


class HyperProtectAdapter(DatabaseAdapter):
    """
    IBM Hyper Protect PostgreSQL adapter.
    Provides FIPS-compliant secure connections with IBM Cloud Databases.
    """

    def __init__(
        self,
        connection_url: str,
        ssl_cert_path: Optional[str] = None,
        ssl_key_path: Optional[str] = None,
        ssl_root_cert_path: Optional[str] = None,
    ):
        """
        Initialize Hyper Protect adapter.

        Args:
            connection_url: PostgreSQL connection URL
            ssl_cert_path: Path to client certificate
            ssl_key_path: Path to client private key
            ssl_root_cert_path: Path to CA root certificate
        """
        self.connection_url = connection_url
        self.ssl_cert_path = ssl_cert_path
        self.ssl_key_path = ssl_key_path
        self.ssl_root_cert_path = ssl_root_cert_path
        self.pool: Optional[asyncpg.Pool] = None
        logger.info("Initialized HyperProtectAdapter (Enterprise/Trial Mode)")

    def _create_ssl_context(self) -> ssl.SSLContext:
        """
        Create FIPS-compliant SSL context.

        Returns:
            SSL context configured for FIPS
        """
        # Create SSL context with FIPS-compliant settings
        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=self.ssl_root_cert_path
        )

        # Load client certificate if provided
        if self.ssl_cert_path and self.ssl_key_path:
            ssl_context.load_cert_chain(
                certfile=self.ssl_cert_path, keyfile=self.ssl_key_path
            )

        # Enforce FIPS-compliant cipher suites
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.set_ciphers("FIPS:!aNULL:!eNULL:!EXPORT:!DES:!MD5:!PSK:!RC4")

        return ssl_context

    async def connect(self) -> None:
        """Create FIPS-compliant connection pool."""
        try:
            # Create SSL context for FIPS compliance
            ssl_context = self._create_ssl_context()

            self.pool = await asyncpg.create_pool(
                self.connection_url,
                min_size=1,
                max_size=10,
                ssl=ssl_context,
                # IBM Hyper Protect specific settings
                command_timeout=60,
                server_settings={
                    "application_name": "nivi_worker",
                    "sslmode": "verify-full",
                },
            )
            logger.info("Connected to IBM Hyper Protect PostgreSQL (FIPS Mode)")
        except Exception as e:
            logger.error(f"Failed to connect to Hyper Protect DB: {e}")
            raise

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from Hyper Protect PostgreSQL")

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
        """Save invoice with audit logging."""
        query = """
        INSERT INTO invoices (
            vendor_name, invoice_number, total_amount, 
            due_date, currency, confidence, status, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                # Use transaction for audit logging
                async with conn.transaction():
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

                    # Audit log for FIPS compliance
                    await conn.execute(
                        """
                        INSERT INTO audit_logs (action, entity_type, entity_id, timestamp)
                        VALUES ($1, $2, $3, NOW())
                        """,
                        "CREATE",
                        "invoice",
                        invoice_id,
                    )

                logger.info(f"Saved invoice with audit: {invoice_id}")
                return str(invoice_id)
        except Exception as e:
            logger.error(f"Failed to save invoice: {e}")
            raise

    async def get_vendor_history(
        self, vendor_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get vendor history with audit logging."""
        query = """
        SELECT * FROM invoices 
        WHERE vendor_name = $1 
        ORDER BY created_at DESC 
        LIMIT $2
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    rows = await conn.fetch(query, vendor_id, limit)

                    # Audit log access
                    await conn.execute(
                        """
                        INSERT INTO audit_logs (action, entity_type, details, timestamp)
                        VALUES ($1, $2, $3, NOW())
                        """,
                        "READ",
                        "vendor_history",
                        f"Accessed history for vendor: {vendor_id}",
                    )

                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get vendor history: {e}")
            return []

    async def update_vendor_trust(self, vendor_id: str, trust_level: int) -> None:
        """Update vendor trust with audit logging."""
        query = """
        INSERT INTO vendors (name, trust_level, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (name) DO UPDATE 
        SET trust_level = $2, updated_at = NOW()
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(query, vendor_id, trust_level)

                    # Audit log the change
                    await conn.execute(
                        """
                        INSERT INTO audit_logs (action, entity_type, details, timestamp)
                        VALUES ($1, $2, $3, NOW())
                        """,
                        "UPDATE",
                        "vendor_trust",
                        f"Updated {vendor_id} trust to {trust_level}",
                    )

                logger.info(f"Updated trust level for {vendor_id}: {trust_level}")
        except Exception as e:
            logger.error(f"Failed to update vendor trust: {e}")
            raise

    async def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve invoice with access logging."""
        query = "SELECT * FROM invoices WHERE id = $1"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(query, int(invoice_id))

                    if row:
                        # Audit log access to sensitive data
                        await conn.execute(
                            """
                            INSERT INTO audit_logs (action, entity_type, entity_id, timestamp)
                            VALUES ($1, $2, $3, NOW())
                            """,
                            "READ",
                            "invoice",
                            invoice_id,
                        )

                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get invoice: {e}")
            return None
