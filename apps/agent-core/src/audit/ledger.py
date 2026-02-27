"""
Immutable Audit Ledger + Data Minimization.

Key Principles:
1. Append-only - No UPDATE or DELETE operations
2. Cryptographic receipts - SHA-256 hash instead of storing PDFs
3. WORM storage - Write Once, Read Many
4. Event sourcing - Complete state transition history

Schema:
    invoice_audit_events (append-only):
    - id: UNIQUEIDENTIFIER
    - invoice_id: UNIQUEIDENTIFIER
    - event_type: VARCHAR (EXTRACTED, APPROVED, BLOCKED, etc.)
    - actor: VARCHAR (agent, human:{user_id}, system)
    - previous_state: JSONB
    - new_state: JSONB
    - reasoning: TEXT (AI explanation)
    - created_at: DATETIME2

Usage:
    from src.audit.ledger import append_audit_event
    
    await append_audit_event(
        invoice_id="INV-123",
        event_type="AUTO_APPROVE",
        actor="agent",
        previous_state={"status": "ANALYZING"},
        new_state={"status": "APPROVED"},
        reasoning="CORE vendor, risk < 0.3",
    )
"""

import os
import json
import hashlib
import structlog
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

logger = structlog.get_logger()


class AuditLedger:
    """
    Immutable audit ledger for invoice processing.
    
    Every state transition is recorded as an append-only event.
    Supports full audit trail reconstruction.
    """
    
    def __init__(self, cosmos_client=None, sql_client=None):
        """
        Initialize ledger.
        
        Args:
            cosmos_client: Cosmos DB client
            sql_client: Azure SQL client
        """
        self.cosmos = cosmos_client
        self.sql = sql_client
    
    async def append_event(
        self,
        invoice_id: str,
        event_type: str,
        actor: str,
        previous_state: Optional[Dict[str, Any]],
        new_state: Dict[str, Any],
        reasoning: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Append audit event to ledger.
        
        Args:
            invoice_id: Invoice identifier
            event_type: Event type (EXTRACTED, APPROVED, BLOCKED, etc.)
            actor: Actor (agent, human:{user_id}, system)
            previous_state: State before transition
            new_state: State after transition
            reasoning: Decision reasoning
            metadata: Additional metadata
        
        Returns:
            Event ID
        """
        event_id = str(uuid4())
        
        event = {
            "id": event_id,
            "partition_key": invoice_id,
            "invoice_id": invoice_id,
            "event_type": event_type,
            "actor": actor,
            "previous_state": previous_state,
            "new_state": new_state,
            "reasoning": reasoning,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,  # For optimistic concurrency
        }
        
        logger.info(
            "audit_event_appended",
            event_id=event_id,
            invoice_id=invoice_id,
            event_type=event_type,
            actor=actor,
        )
        
        # Store in Cosmos DB (append-only)
        if self.cosmos:
            await self._store_cosmos(event)
        
        # Store in SQL (for complex queries)
        if self.sql:
            await self._store_sql(event)
        
        return event_id
    
    async def _store_cosmos(self, event: Dict[str, Any]):
        """Store event in Cosmos DB."""
        # Placeholder - would use Cosmos DB SDK
        logger.debug("cosmos_audit_store", event_id=event["id"])
    
    async def _store_sql(self, event: Dict[str, Any]):
        """Store event in Azure SQL."""
        # Placeholder - would use SQL SDK
        logger.debug("sql_audit_store", event_id=event["id"])
    
    async def get_invoice_history(self, invoice_id: str) -> List[Dict[str, Any]]:
        """
        Get complete audit history for invoice.
        
        Args:
            invoice_id: Invoice identifier
        
        Returns:
            List of events in chronological order
        """
        if self.sql:
            return await self._query_sql(invoice_id)
        elif self.cosmos:
            return await self._query_cosmos(invoice_id)
        else:
            return []
    
    async def _query_sql(self, invoice_id: str) -> List[Dict[str, Any]]:
        """Query events from SQL."""
        # Placeholder
        return []
    
    async def _query_cosmos(self, invoice_id: str) -> List[Dict[str, Any]]:
        """Query events from Cosmos DB."""
        # Placeholder
        return []


class AuditReceiptGenerator:
    """
    Generate cryptographic audit receipts.
    
    Instead of storing the PDF (liability), we store:
    - SHA-256 hash of the PDF
    - QuickBooks transaction ID
    - AI reasoning
    - Timestamp
    
    This allows verification without storing sensitive data.
    """
    
    @staticmethod
    def generate_receipt(
        file_bytes: bytes,
        quickbooks_id: str,
        ai_reasoning: str,
        invoice_id: str,
        tenant_id: str,
        decision: str,
    ) -> Dict[str, Any]:
        """
        Generate audit receipt.
        
        Args:
            file_bytes: Original PDF bytes
            quickbooks_id: QuickBooks transaction ID
            ai_reasoning: AI decision reasoning
            invoice_id: Invoice identifier
            tenant_id: Tenant identifier
            decision: Decision (APPROVED/REJECTED/BLOCKED)
        
        Returns:
            Audit receipt dict
        """
        # Generate SHA-256 hash of PDF
        pdf_hash = hashlib.sha256(file_bytes).hexdigest()
        
        receipt = {
            "id": f"receipt-{invoice_id}",
            "partition_key": tenant_id,
            "invoice_id": invoice_id,
            "quickbooks_id": quickbooks_id,
            "document_hash": pdf_hash,
            "hash_algorithm": "SHA-256",
            "decision": decision,
            "ai_reasoning": ai_reasoning,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_type": "SYNC_COMPLETED",
        }
        
        logger.info(
            "audit_receipt_generated",
            invoice_id=invoice_id,
            quickbooks_id=quickbooks_id,
            pdf_hash=pdf_hash[:16] + "...",
            decision=decision,
        )
        
        return receipt
    
    @staticmethod
    async def verify_receipt(
        file_bytes: bytes,
        receipt: Dict[str, Any],
    ) -> bool:
        """
        Verify audit receipt matches PDF.
        
        Args:
            file_bytes: PDF bytes to verify
            receipt: Audit receipt
        
        Returns:
            True if hash matches
        """
        pdf_hash = hashlib.sha256(file_bytes).hexdigest()
        stored_hash = receipt.get("document_hash")
        
        matches = pdf_hash == stored_hash
        
        logger.info(
            "receipt_verification",
            invoice_id=receipt.get("invoice_id"),
            hash_matches=matches,
        )
        
        return matches


class DataMinimizationPolicy:
    """
    Data minimization policy enforcement.
    
    Principles:
    1. Store minimum necessary data
    2. Delete immediately after processing
    3. Keep only cryptographic receipts
    4. Auto-evaporate orphaned data (TTL)
    """
    
    @staticmethod
    def get_retention_policy() -> Dict[str, int]:
        """
        Get data retention policy.
        
        Returns:
            Dict of data type → retention seconds
        """
        return {
            "pdf_blob": 259200,  # 3 days
            "extracted_json": 604800,  # 7 days
            "audit_receipt": 31536000,  # 1 year
            "audit_event": 31536000,  # 1 year
        }
    
    @staticmethod
    def should_store_pdf() -> bool:
        """
        Check if PDF should be stored permanently.
        
        Returns:
            False (we only store hash)
        """
        return False
    
    @staticmethod
    def get_required_fields() -> List[str]:
        """
        Get minimum required fields for audit.
        
        Returns:
            List of required field names
        """
        return [
            "invoice_id",
            "quickbooks_id",
            "document_hash",
            "decision",
            "timestamp",
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────

_ledger_instance: Optional[AuditLedger] = None


def get_ledger(cosmos_client=None, sql_client=None) -> AuditLedger:
    """Get or create audit ledger singleton."""
    global _ledger_instance
    if _ledger_instance is None:
        _ledger_instance = AuditLedger(cosmos_client, sql_client)
    return _ledger_instance


async def append_audit_event(
    invoice_id: str,
    event_type: str,
    actor: str,
    new_state: Dict[str, Any],
    reasoning: str,
    previous_state: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Append audit event to ledger.
    
    Usage:
        await append_audit_event(
            invoice_id="INV-123",
            event_type="AUTO_APPROVE",
            actor="agent",
            new_state={"status": "APPROVED"},
            reasoning="CORE vendor, risk < 0.3",
        )
    """
    ledger = get_ledger()
    return await ledger.append_event(
        invoice_id=invoice_id,
        event_type=event_type,
        actor=actor,
        previous_state=previous_state,
        new_state=new_state,
        reasoning=reasoning,
        metadata=metadata,
    )


def generate_audit_receipt(
    file_bytes: bytes,
    quickbooks_id: str,
    ai_reasoning: str,
    invoice_id: str,
    tenant_id: str,
    decision: str,
) -> Dict[str, Any]:
    """
    Generate cryptographic audit receipt.
    
    Usage:
        receipt = generate_audit_receipt(
            file_bytes=pdf_bytes,
            quickbooks_id="qb-123",
            ai_reasoning="Low risk vendor",
            invoice_id="INV-123",
            tenant_id="tenant-001",
            decision="APPROVED",
        )
    """
    generator = AuditReceiptGenerator()
    return generator.generate_receipt(
        file_bytes=file_bytes,
        quickbooks_id=quickbooks_id,
        ai_reasoning=ai_reasoning,
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        decision=decision,
    )
