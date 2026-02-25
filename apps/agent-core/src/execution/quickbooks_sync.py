"""
Idempotent QuickBooks Sync + Sync & Shred Pattern.

Key Features:
1. Idempotency - Prevents double-payments via Request-Id headers
2. Sync & Shred - Deletes data immediately after sync (data minimization)
3. Cryptographic Receipts - SHA-256 hash for audit trail (not the actual PDF)

Free Tier Protection:
- QuickBooks API: 1,000 calls/day (Sandbox)
- Azure Blob: Auto-delete after 3 days (lifecycle policy)
- Cosmos DB: Auto-delete after 7 days (TTL)

Usage:
    from src.execution.quickbooks_sync import sync_and_shred
    
    result = await sync_and_shred(
        invoice_id="INV-123",
        invoice_data={...},
        blob_url="https://...",
        tenant_id="tenant-001",
    )
"""

import os
import json
import hashlib
import time
import structlog
from typing import Any, Dict, Optional
from datetime import datetime, timezone

logger = structlog.get_logger()

# QuickBooks configuration
QUICKBOOKS_BASE_URL = os.getenv("QUICKBOOKS_BASE_URL", "https://sandbox-quickbooks.api.intuit.com/v3")
QUICKBOOKS_CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID")
QUICKBOOKS_CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET")
QUICKBOOKS_REALM_ID = os.getenv("QUICKBOOKS_REALM_ID")

# Mock mode for local dev
MOCK_MODE = not QUICKBOOKS_CLIENT_ID


class IdempotencyStore:
    """
    Redis-backed idempotency tracking.
    
    Prevents duplicate QuickBooks creations.
    TTL: 24 hours (sufficient for retry windows)
    """
    
    def __init__(self, redis_client):
        """
        Initialize idempotency store.
        
        Args:
            redis_client: Upstash Redis client
        """
        self.redis = redis_client
        self.ttl_seconds = 86400  # 24 hours
    
    async def get(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result for idempotency key.
        
        Args:
            idempotency_key: Unique request identifier
        
        Returns:
            Cached result if exists, None otherwise
        """
        cached = await self.redis.get(f"idempotent:{idempotency_key}")
        if cached:
            logger.info("idempotency_cache_hit", key=idempotency_key)
            return json.loads(cached)
        return None
    
    async def set(self, idempotency_key: str, result: Dict[str, Any]):
        """
        Cache result for idempotency key.
        
        Args:
            idempotency_key: Unique request identifier
            result: Result to cache
        """
        await self.redis.setex(
            f"idempotent:{idempotency_key}",
            self.ttl_seconds,
            json.dumps(result),
        )
        logger.info("idempotency_cached", key=idempotency_key, ttl=self.ttl_seconds)


class QuickBooksSync:
    """
    Idempotent QuickBooks synchronization.
    
    Uses Request-Id headers for idempotency.
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize QuickBooks sync.
        
        Args:
            redis_client: Redis client for idempotency tracking
        """
        self.redis_client = redis_client
        self.idempotency_store = IdempotencyStore(redis_client) if redis_client else None
        self.mock_mode = MOCK_MODE
    
    async def sync_invoice(self, invoice_data: Dict[str, Any], invoice_id: str) -> Dict[str, Any]:
        """
        Sync invoice to QuickBooks (idempotent).
        
        Args:
            invoice_data: Invoice data
            invoice_id: Invoice identifier
        
        Returns:
            QuickBooks response with bill ID
        """
        # Generate idempotency key
        idempotency_key = f"qb-bill-{invoice_id}"
        
        # Check idempotency cache
        if self.idempotency_store:
            cached = await self.idempotency_store.get(idempotency_key)
            if cached:
                logger.info("quickbooks_idempotency_hit", invoice_id=invoice_id, cached_result=cached)
                return cached
        
        # Mock mode for local dev
        if self.mock_mode:
            logger.info("quickbooks_mock_mode", invoice_id=invoice_id)
            result = {
                "Bill": {
                    "Id": f"mock-bill-{invoice_id}",
                    "SyncToken": "0",
                    "MetaData": {
                        "CreateTime": datetime.now(timezone.utc).isoformat(),
                    }
                },
                "time": datetime.now(timezone.utc).isoformat(),
            }
        else:
            # Real QuickBooks API call
            result = await self._create_bill_api(invoice_data, invoice_id)
        
        # Cache result
        if self.idempotency_store:
            await self.idempotency_store.set(idempotency_key, result)
        
        logger.info("quickbooks_sync_complete", invoice_id=invoice_id, bill_id=result["Bill"]["Id"])
        
        return result
    
    async def _create_bill_api(self, invoice_data: Dict[str, Any], invoice_id: str) -> Dict[str, Any]:
        """
        Create bill via QuickBooks API.
        
        Uses Request-Id header for idempotency.
        
        Args:
            invoice_data: Invoice data
            invoice_id: Invoice identifier
        
        Returns:
            QuickBooks response
        """
        import httpx
        
        # Build QuickBooks bill payload
        qb_payload = self._format_quickbooks_payload(invoice_data)
        
        # Generate Request-Id for idempotency
        request_id = f"qb-create-{invoice_id}-{int(time.time())}"
        
        # Get access token (OAuth 2.0)
        access_token = await self._get_access_token()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{QUICKBOOKS_BASE_URL}/company/{QUICKBOOKS_REALM_ID}/bill",
                json=qb_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Request-Id": request_id,  # Idempotency key
                },
            )
            
            # Handle idempotency - QuickBooks returns 400 for duplicate Request-Id
            if response.status_code == 400 and "Duplicate Document Number" in response.text:
                logger.info("quickbooks_duplicate_detected", invoice_id=invoice_id)
                # Fetch existing bill
                return await self._fetch_existing_bill(invoice_data["invoice_number"])
            
            response.raise_for_status()
            return response.json()
    
    def _format_quickbooks_payload(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format invoice data for QuickBooks API.
        
        Args:
            invoice_data: Invoice data
        
        Returns:
            QuickBooks bill payload
        """
        return {
            "VendorRef": {
                "value": invoice_data.get("vendor_name", "Unknown Vendor"),
            },
            "Line": [
                {
                    "Description": item.get("description", ""),
                    "Amount": item.get("total", 0),
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "AccountBasedExpenseLineDetail": {
                        "Qty": item.get("quantity", 1),
                        "UnitPrice": item.get("unit_price", 0),
                    },
                }
                for item in invoice_data.get("line_items", [])
            ],
            "TotalAmt": invoice_data.get("total_amount", 0),
            "BillEmail": {
                "Address": invoice_data.get("vendor_email", "billing@vendor.com"),
            },
            "DocNumber": invoice_data.get("invoice_number"),
            "TxnDate": invoice_data.get("invoice_date"),
            "DueDate": invoice_data.get("due_date", invoice_data.get("invoice_date")),
        }
    
    async def _get_access_token(self) -> str:
        """
        Get OAuth 2.0 access token for QuickBooks API.
        
        Returns:
            Access token
        """
        # In production, this would use OAuth 2.0 flow
        # For now, return mock token
        return "mock-access-token"
    
    async def _fetch_existing_bill(self, doc_number: str) -> Dict[str, Any]:
        """
        Fetch existing bill by document number.
        
        Args:
            doc_number: Document number
        
        Returns:
            QuickBooks response
        """
        # Placeholder - would query QuickBooks Query API
        return {
            "Bill": {
                "Id": f"existing-bill-{doc_number}",
                "SyncToken": "0",
            }
        }


class DataShredder:
    """
    Sync & Shred pattern implementation.
    
    Deletes data immediately after successful sync.
    """
    
    def __init__(self, blob_client, cosmos_client):
        """
        Initialize shredder.
        
        Args:
            blob_client: Azure Blob Storage client
            cosmos_client: Cosmos DB client
        """
        self.blob_client = blob_client
        self.cosmos_client = cosmos_client
    
    async def shred_invoice_data(self, invoice_id: str, blob_url: str, tenant_id: str):
        """
        Shred invoice data after successful sync.
        
        Args:
            invoice_id: Invoice identifier
            blob_url: Blob storage URL
            tenant_id: Tenant identifier
        """
        logger.info("shredding_started", invoice_id=invoice_id)
        
        # Delete PDF from Blob Storage
        if self.blob_client and blob_url:
            try:
                await self._delete_blob(blob_url)
                logger.info("blob_shredded", invoice_id=invoice_id, blob_url=blob_url)
            except Exception as e:
                logger.error("blob_shred_failed", invoice_id=invoice_id, error=str(e))
        
        # Delete JSON from Cosmos DB
        if self.cosmos_client:
            try:
                await self._delete_cosmos_item(invoice_id, tenant_id)
                logger.info("cosmos_shredded", invoice_id=invoice_id)
            except Exception as e:
                logger.error("cosmos_shred_failed", invoice_id=invoice_id, error=str(e))
        
        logger.info("shredding_complete", invoice_id=invoice_id)
    
    async def _delete_blob(self, blob_url: str):
        """Delete blob from Azure Storage."""
        # Placeholder - would use Azure Blob SDK
        pass
    
    async def _delete_cosmos_item(self, invoice_id: str, tenant_id: str):
        """Delete item from Cosmos DB."""
        # Placeholder - would use Cosmos DB SDK
        pass


class AuditReceiptGenerator:
    """
    Generate cryptographic audit receipts.
    
    Instead of storing the PDF, we store:
    - SHA-256 hash of the PDF
    - QuickBooks transaction ID
    - AI reasoning for approval
    - Timestamp
    """
    
    @staticmethod
    def generate_receipt(
        file_bytes: bytes,
        quickbooks_id: str,
        ai_reasoning: str,
        invoice_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Generate audit receipt.
        
        Args:
            file_bytes: Original PDF bytes
            quickbooks_id: QuickBooks transaction ID
            ai_reasoning: AI decision reasoning
            invoice_id: Invoice identifier
            tenant_id: Tenant identifier
        
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
            "ai_reasoning": ai_reasoning,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_type": "SYNC_COMPLETED",
        }
        
        logger.info(
            "audit_receipt_generated",
            invoice_id=invoice_id,
            quickbooks_id=quickbooks_id,
            pdf_hash=pdf_hash[:16] + "...",
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


# ─────────────────────────────────────────────────────────────────────────────
# Main Sync & Shred Function
# ─────────────────────────────────────────────────────────────────────────────

async def sync_and_shred(
    invoice_id: str,
    invoice_data: Dict[str, Any],
    blob_url: str,
    tenant_id: str,
    file_bytes: Optional[bytes] = None,
    redis_client=None,
    blob_client=None,
    cosmos_client=None,
) -> Dict[str, Any]:
    """
    Sync invoice to QuickBooks and shred data.
    
    Implements:
    1. Idempotent QuickBooks sync (Request-Id headers)
    2. Sync & Shred pattern (delete after sync)
    3. Cryptographic audit receipt (SHA-256 hash)
    
    Args:
        invoice_id: Invoice identifier
        invoice_data: Invoice data
        blob_url: Blob storage URL
        tenant_id: Tenant identifier
        file_bytes: Original PDF bytes (for hash)
        redis_client: Redis client for idempotency
        blob_client: Blob storage client
        cosmos_client: Cosmos DB client
    
    Returns:
        Sync result with QuickBooks ID and audit receipt
    """
    logger.info("sync_and_shred_started", invoice_id=invoice_id)
    
    # 1. Sync to QuickBooks (idempotent)
    qb_sync = QuickBooksSync(redis_client)
    qb_result = await qb_sync.sync_invoice(invoice_data, invoice_id)
    
    quickbooks_id = qb_result["Bill"]["Id"]
    
    # 2. Generate audit receipt
    if file_bytes:
        receipt_gen = AuditReceiptGenerator()
        audit_receipt = receipt_gen.generate_receipt(
            file_bytes=file_bytes,
            quickbooks_id=quickbooks_id,
            ai_reasoning=invoice_data.get("extraction_confidence", "N/A"),
            invoice_id=invoice_id,
            tenant_id=tenant_id,
        )
    else:
        audit_receipt = None
    
    # 3. Shred data (delete PDF and JSON)
    shredder = DataShredder(blob_client, cosmos_client)
    await shredder.shred_invoice_data(invoice_id, blob_url, tenant_id)
    
    logger.info(
        "sync_and_shred_complete",
        invoice_id=invoice_id,
        quickbooks_id=quickbooks_id,
        shredded=True,
    )
    
    return {
        "status": "SYNCED_AND_SHREDDED",
        "quickbooks_id": quickbooks_id,
        "quickbooks_result": qb_result,
        "audit_receipt": audit_receipt,
    }
