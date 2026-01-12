"""Neo4j client for knowledge graph operations."""

import logging
from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from neo4j import GraphDatabase, RoutingControl

from app.config import get_settings

logger = logging.getLogger(__name__)


class VendorNode(BaseModel):
    """Vendor node in the knowledge graph."""
    id: str
    name: str
    trust_score: float = 0.5
    avg_invoice_amount: float = 0.0
    payment_terms_days: Optional[int] = None
    total_invoices: int = 0
    consecutive_accurate: int = 0
    consecutive_errors: int = 0
    accurate_decisions: int = 0
    created_at: Optional[str] = None


class InvoiceNode(BaseModel):
    """Invoice node in the knowledge graph."""
    id: str
    vendor_id: str
    invoice_number: str
    amount: float
    risk_score: float = 0.0
    status: str
    created_at: Optional[str] = None


class ContractNode(BaseModel):
    """Contract node in the knowledge graph."""
    id: str
    vendor_id: str
    terms: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Neo4jClient:
    """Client for interacting with Neo4j knowledge graph."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Initialize the Neo4j client."""
        settings = get_settings()
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver = None

    def _get_driver(self):
        """Get or create the Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
        return self._driver

    def close(self):
        """Close the Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    async def execute_query(
        self,
        query: str,
        parameters: Optional[dict] = None,
        database: str = "neo4j",
        routing: RoutingControl = RoutingControl.WRITE,
    ) -> list[dict]:
        """Execute a Cypher query."""
        driver = self._get_driver()
        records, summary, keys = driver.execute_query(
            query,
            parameters,
            database_=database,
            routing_=routing,
        )
        logger.debug(
            f"Query executed in {summary.result_available_after}ms, "
            f"nodes created: {summary.counters.nodes_created}"
        )
        return [dict(record) for record in records]

    # ==================== VENDOR OPERATIONS ====================

    async def create_vendor(self, vendor: VendorNode) -> dict:
        """Create or update a vendor node."""
        query = """
        MERGE (v:Vendor {id: $id})
        SET v.name = $name,
            v.trust_score = $trust_score,
            v.avg_invoice_amount = $avg_invoice_amount,
            v.payment_terms_days = $payment_terms_days,
            v.total_invoices = $total_invoices,
            v.created_at = $created_at
        RETURN v
        """
        result = await self.execute_query(query, vendor.model_dump())
        return result[0] if result else None

    async def create_vendor_simple(
        self,
        name: str,
        industry: Optional[str] = None,
        trust_score: float = 0.5,
        total_invoices: int = 0,
        total_payments: float = 0.0,
    ) -> dict:
        """Create a vendor with simple parameters."""
        from uuid import uuid4
        vendor = VendorNode(
            id=str(uuid4()),
            name=name,
            trust_score=trust_score,
            total_invoices=total_invoices,
            avg_invoice_amount=total_payments / max(total_invoices, 1),
        )
        return await self.create_vendor(vendor)

    async def get_vendor(self, vendor_id: str) -> Optional[VendorNode]:
        """Get a vendor by ID."""
        query = """
        MATCH (v:Vendor {id: $id})
        RETURN v
        """
        records = await self.execute_query(query, {"id": vendor_id})
        if records:
            return VendorNode(**records[0]["v"])
        return None

    async def get_vendor_by_name(self, name: str) -> Optional[VendorNode]:
        """Get a vendor by name."""
        query = """
        MATCH (v:Vendor {name: $name})
        RETURN v
        """
        records = await self.execute_query(query, {"name": name})
        if records:
            return VendorNode(**records[0]["v"])
        return None

    async def update_vendor_trust(
        self,
        vendor_id: str,
        trust_score: float,
        consecutive_accurate: int = 0,
        consecutive_errors: int = 0,
        total_invoices: int = 0,
        accurate_decisions: int = 0,
    ) -> None:
        """Update vendor trust score by id or name."""
        # Try updating by id first, then by name
        query = """
        MATCH (v:Vendor)
        WHERE v.id = $id OR v.name = $id
        SET v.trust_score = $trust_score,
            v.consecutive_accurate = $consecutive_accurate,
            v.consecutive_errors = $consecutive_errors,
            v.total_invoices = $total_invoices,
            v.accurate_decisions = $accurate_decisions
        """
        await self.execute_query(
            query,
            {
                "id": vendor_id,
                "trust_score": trust_score,
                "consecutive_accurate": consecutive_accurate,
                "consecutive_errors": consecutive_errors,
                "total_invoices": total_invoices,
                "accurate_decisions": accurate_decisions,
            },
        )

    async def get_trusted_vendors(self, min_trust: float = 0.8) -> list[VendorNode]:
        """Get vendors with trust score above threshold."""
        query = """
        MATCH (v:Vendor)
        WHERE v.trust_score >= $min_trust
        RETURN v
        """
        records = await self.execute_query(query, {"min_trust": min_trust})
        return [VendorNode(**r["v"]) for r in records]

    # ==================== INVOICE OPERATIONS ====================

    async def create_invoice(self, invoice: InvoiceNode) -> dict:
        """Create an invoice node and link to vendor."""
        query = """
        MATCH (v:Vendor {id: $vendor_id})
        MERGE (i:Invoice {id: $id})
        SET i.invoice_number = $invoice_number,
            i.amount = $amount,
            i.risk_score = $risk_score,
            i.status = $status,
            i.created_at = $created_at
        MERGE (v)-[:ISSUED]->(i)
        RETURN i
        """
        result = await self.execute_query(query, invoice.model_dump())
        return result[0] if result else None

    async def create_invoice_simple(
        self,
        invoice_id: str,
        vendor_name: str,
        amount: float,
        status: str,
        due_date: str,
    ) -> dict:
        """Create an invoice with simple parameters."""
        # First get vendor ID by name
        vendor = await self.get_vendor_by_name(vendor_name)
        if not vendor:
            raise ValueError(f"Vendor not found: {vendor_name}")

        invoice = InvoiceNode(
            id=invoice_id,
            vendor_id=vendor.id,
            invoice_number=f"INV-{invoice_id[:8]}",
            amount=amount,
            status=status,
        )
        return await self.create_invoice(invoice)

    async def get_invoice(self, invoice_id: str) -> Optional[InvoiceNode]:
        """Get an invoice by ID."""
        query = """
        MATCH (i:Invoice {id: $id})
        RETURN i
        """
        records = await self.execute_query(query, {"id": invoice_id})
        if records:
            return InvoiceNode(**records[0]["i"])
        return None

    async def get_invoices_by_vendor(self, vendor_id: str) -> list[InvoiceNode]:
        """Get all invoices for a vendor."""
        query = """
        MATCH (v:Vendor {id: $vendor_id})-[:ISSUED]->(i:Invoice)
        RETURN i
        """
        records = await self.execute_query(query, {"vendor_id": vendor_id})
        return [InvoiceNode(**r["i"]) for r in records]

    async def update_invoice_status(
        self,
        invoice_id: str,
        status: str,
    ) -> None:
        """Update invoice status."""
        query = """
        MATCH (i:Invoice {id: $id})
        SET i.status = $status
        """
        await self.execute_query(query, {"id": invoice_id, "status": status})

    # ==================== CONTRACT OPERATIONS ====================

    async def create_contract(self, contract: ContractNode) -> dict:
        """Create a contract node and link to vendor."""
        query = """
        MATCH (v:Vendor {id: $vendor_id})
        MERGE (c:Contract {id: $id})
        SET c.terms = $terms,
            c.start_date = $start_date,
            c.end_date = $end_date
        MERGE (v)-[:HAS_CONTRACT]->(c)
        RETURN c
        """
        result = await self.execute_query(query, contract.model_dump())
        return result[0] if result else None

    async def get_vendor_contract(self, vendor_id: str) -> Optional[ContractNode]:
        """Get the contract for a vendor."""
        query = """
        MATCH (v:Vendor {id: $vendor_id})-[:HAS_CONTRACT]->(c:Contract)
        RETURN c
        """
        records = await self.execute_query(query, {"vendor_id": vendor_id})
        if records:
            return ContractNode(**records[0]["c"])
        return None

    # ==================== PAYMENT OPERATIONS ====================

    async def link_payment_to_invoice(
        self,
        payment_id: str,
        invoice_id: str,
        amount: float,
    ) -> None:
        """Link a payment to an invoice."""
        query = """
        MERGE (p:Payment {id: $payment_id})
        SET p.amount = $amount, p.status = 'scheduled'
        MATCH (i:Invoice {id: $invoice_id})
        MERGE (i)-[:PAID_BY]->(p)
        """
        await self.execute_query(
            query,
            {"payment_id": payment_id, "invoice_id": invoice_id, "amount": amount},
        )

    async def mark_payment_executed(self, payment_id: str) -> None:
        """Mark a payment as executed."""
        query = """
        MATCH (p:Payment {id: $id})
        SET p.status = 'executed', p.executed_at = datetime()
        """
        await self.execute_query(query, {"id": payment_id})

    # ==================== GRAPH TRAVERSAL ====================

    async def get_vendor_payment_history(self, vendor_id: str) -> list[dict]:
        """Get full payment history for a vendor."""
        query = """
        MATCH (v:Vendor {id: $vendor_id})-[:ISSUED]->(i:Invoice)-[:PAID_BY]->(p:Payment)
        RETURN i.id as invoice_id, i.amount as amount, i.status as status,
               p.id as payment_id, p.status as payment_status, p.executed_at as executed_at
        ORDER BY p.executed_at DESC
        """
        return await self.execute_query(query, {"vendor_id": vendor_id})

    async def find_anomaly_patterns(self, vendor_id: str) -> list[dict]:
        """Find potential anomalies in vendor payment patterns."""
        query = """
        MATCH (v:Vendor {id: $vendor_id})-[:ISSUED]->(i:Invoice)
        WITH v, i.amount as amount
        WITH v, avg(amount) as avg_amount, stdev(amount) as std_amount
        MATCH (v)-[:ISSUED]->(i:Invoice)
        WHERE abs(i.amount - avg_amount) > 2 * std_amount AND std_amount > 0
        RETURN i.id as invoice_id, i.amount, i.created_at as date,
               round((i.amount - avg_amount) / nullif(std_amount, 0), 2) as z_score
        """
        return await self.execute_query(query, {"vendor_id": vendor_id})

    # ==================== INITIALIZATION ====================

    async def initialize_schema(self) -> None:
        """Initialize the graph schema (constraints and indexes)."""
        queries = [
            # Create constraints
            "CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (v:Vendor) REQUIRE v.id IS UNIQUE",
            "CREATE CONSTRAINT invoice_id IF NOT EXISTS FOR (i:Invoice) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT contract_id IF NOT EXISTS FOR (c:Contract) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT payment_id IF NOT EXISTS FOR (p:Payment) REQUIRE p.id IS UNIQUE",
            # Create indexes
            "CREATE INDEX vendor_name IF NOT EXISTS FOR (v:Vendor) ON (v.name)",
            "CREATE INDEX invoice_status IF NOT EXISTS FOR (i:Invoice) ON (i.status)",
            "CREATE INDEX invoice_vendor IF NOT EXISTS FOR (i:Invoice) ON (i.vendor_id)",
        ]
        for query in queries:
            try:
                await self.execute_query(query)
                logger.info(f"Schema query executed: {query[:50]}...")
            except Exception as e:
                logger.warning(f"Schema query failed (may already exist): {e}")


# Singleton instance
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """Get the singleton Neo4j client instance."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client
