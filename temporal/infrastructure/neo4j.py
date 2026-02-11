"""Neo4j client for Temporal activities."""

import os
import logging
from typing import List, Optional
from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async Neo4j client for graph operations."""

    def __init__(self):
        self._driver = None
        self._uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = os.getenv("NEO4J_USER", "neo4j")
        self._password = os.getenv("NEO4J_PASSWORD", "password")

    async def connect(self):
        """Initialize Neo4j driver."""
        # Always create a fresh driver to avoid event loop issues
        if self._driver is not None:
            try:
                await self._driver.close()
            except Exception:
                pass
        self._driver = AsyncGraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )

    async def close(self):
        """Close Neo4j driver."""
        if self._driver:
            try:
                await self._driver.close()
            except Exception:
                pass
            self._driver = None

    async def get_invoices_by_vendor(self, vendor_name: str) -> List[dict]:
        """Get all invoices for a vendor."""
        await self.connect()

        query = """
        MATCH (v:Vendor {name: $vendor_name})-[:SENT]->(i:Invoice)
        RETURN i ORDER BY i.created_at DESC LIMIT 10
        """

        async with self._driver.session() as session:
            result = await session.run(query, vendor_name=vendor_name)
            records = []
            async for record in result:
                invoice = record["i"]
                # Neo4j returns a dict-like object, convert to proper dict
                invoice_dict = dict(invoice)
                records.append(
                    {
                        "id": invoice_dict.get("id"),
                        "invoice_number": invoice_dict.get("id"),  # Use id as invoice_number
                        "amount": invoice_dict.get("amount"),
                        "status": invoice_dict.get("status"),
                        "created_at": invoice_dict.get("created_at"),
                    }
                )
            return records

    async def find_anomaly_patterns(self, vendor_name: str) -> List[dict]:
        """Find anomaly patterns in vendor payment history."""
        await self.connect()

        query = """
        MATCH (v:Vendor {name: $vendor_name})-[:SENT]->(i:Invoice)
        WITH v, i
        ORDER BY i.created_at DESC
        WITH v, collect(i) as invoices
        UNWIND range(0, size(invoices)-2) as idx
        WITH invoices[idx] as current, invoices[idx+1] as next
        WHERE current.amount > 0 AND next.amount > 0
        WITH current, next, abs(current.amount - next.amount) / next.amount as deviation
        WHERE deviation > 0.5
        RETURN {
            invoice_id: current.id,
            amount: current.amount,
            deviation: deviation,
            previous_amount: next.amount
        } as anomaly
        LIMIT 5
        """

        async with self._driver.session() as session:
            result = await session.run(query, vendor_name=vendor_name)
            records = []
            async for record in result:
                records.append(record["anomaly"])
            return records

    async def create_invoice(
        self,
        invoice_id: str,
        vendor_name: str,
        amount: float,
        status: str,
        due_date: str,
    ):
        """Create invoice node in graph."""
        await self.connect()

        query = """
        MERGE (v:Vendor {name: $vendor_name})
        CREATE (i:Invoice {
            id: $invoice_id,
            amount: $amount,
            status: $status,
            due_date: $due_date,
            created_at: datetime()
        })
        CREATE (v)-[:SENT]->(i)
        """

        async with self._driver.session() as session:
            await session.run(
                query,
                invoice_id=invoice_id,
                vendor_name=vendor_name,
                amount=amount,
                status=status,
                due_date=due_date,
            )


# Singleton client instance
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """Get singleton Neo4j client."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client
