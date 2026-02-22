"""
RAG Pipeline for Invoice Duplicate Detection.

Uses Qdrant for vector similarity search to find:
- Duplicate invoices (same vendor + same amount)
- Similar invoices (for price anomaly detection)
- Contract terms (for compliance checking)

Architecture:
1. Extract invoice embedding (fastembed)
2. Search Qdrant for similar vectors
3. Return duplicate risk score + context
"""

import asyncio
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)
from fastembed import TextEmbedding

logger = structlog.get_logger()


class RAGPipeline:
    """
    RAG pipeline for invoice context retrieval.
    
    Collections:
    - invoices: All processed invoices for duplicate detection
    - contracts: Contract terms for compliance checking
    """
    
    def __init__(self, qdrant_url: str = "http://localhost:6333"):
        """
        Initialize RAG pipeline.
        
        Args:
            qdrant_url: Qdrant server URL
        """
        self.client = QdrantClient(url=qdrant_url)
        self.embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        
        # Collection names
        self.invoices_collection = "invoices"
        self.contracts_collection = "contracts"
        
        # Initialize collections
        self._initialize_collections()
    
    def _initialize_collections(self):
        """Create collections if they don't exist."""
        # Get embedding dimension
        test_embedding = list(self.embedding_model.embed(["test"]))[0]
        embedding_dim = len(test_embedding)
        
        # Create invoices collection
        try:
            self.client.create_collection(
                collection_name=self.invoices_collection,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("created_qdrant_collection", name=self.invoices_collection)
        except Exception as e:
            if "already exists" not in str(e):
                raise
        
        # Create contracts collection
        try:
            self.client.create_collection(
                collection_name=self.contracts_collection,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("created_qdrant_collection", name=self.contracts_collection)
        except Exception as e:
            if "already exists" not in str(e):
                raise
    
    def _generate_invoice_embedding(self, invoice_data: Dict[str, Any]) -> List[float]:
        """
        Generate embedding for invoice.
        
        Embeds: vendor_name + invoice_number + total_amount + line_items
        """
        # Create text representation for embedding
        text = f"""
        Vendor: {invoice_data.get('vendor_name', '')}
        Invoice: {invoice_data.get('invoice_number', '')}
        Amount: ${invoice_data.get('total_amount', 0):.2f}
        Items: {', '.join([item.get('description', '') for item in invoice_data.get('line_items', [])])}
        """
        
        # Generate embedding
        embedding = list(self.embedding_model.embed([text]))[0]
        return embedding.tolist()
    
    def _generate_invoice_id(self, invoice_data: Dict[str, Any]) -> str:
        """Generate unique invoice ID for Qdrant point."""
        text = f"{invoice_data.get('vendor_name', '')}-{invoice_data.get('invoice_number', '')}"
        return hashlib.md5(text.encode()).hexdigest()
    
    async def index_invoice(self, invoice_data: Dict[str, Any], metadata: Optional[Dict] = None):
        """
        Index invoice in Qdrant for future retrieval.
        
        Args:
            invoice_data: Invoice data (vendor, amount, line items, etc.)
            metadata: Additional metadata (tenant_id, trust_level, etc.)
        """
        # Generate embedding
        embedding = self._generate_invoice_embedding(invoice_data)
        
        # Create point ID
        point_id = self._generate_invoice_id(invoice_data)
        
        # Prepare payload
        payload = {
            "vendor_name": invoice_data.get("vendor_name", ""),
            "invoice_number": invoice_data.get("invoice_number", ""),
            "total_amount": invoice_data.get("total_amount", 0),
            "invoice_date": invoice_data.get("invoice_date", ""),
            "tenant_id": metadata.get("tenant_id", "") if metadata else "",
            "trust_level": metadata.get("trust_level", "PROBATION") if metadata else "PROBATION",
            "decision": metadata.get("decision", "PENDING") if metadata else "PENDING",
            "indexed_at": datetime.utcnow().isoformat(),
        }
        
        # Upsert to Qdrant
        self.client.upsert(
            collection_name=self.invoices_collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )
        
        logger.info(
            "invoice_indexed",
            invoice_number=invoice_data.get("invoice_number"),
            vendor=invoice_data.get("vendor_name"),
        )
    
    async def check_duplicate(
        self,
        invoice_data: Dict[str, Any],
        tenant_id: str,
        threshold: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Check if invoice is a potential duplicate.
        
        Args:
            invoice_data: Invoice data to check
            tenant_id: Tenant ID for filtering
            threshold: Similarity threshold for duplicate (0.95 = 95% similar)
        
        Returns:
            Duplicate check result with risk score and similar invoices
        """
        # Generate embedding
        embedding = self._generate_invoice_embedding(invoice_data)
        
        # Search for similar invoices
        results = self.client.search(
            collection_name=self.invoices_collection,
            query_vector=embedding.tolist(),
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(value=tenant_id),
                    ),
                ]
            ),
            limit=5,
            score_threshold=0.8,  # Return results with >= 80% similarity
        )
        
        # Analyze results for duplicates
        duplicate_risk = False
        duplicate_invoice_id = None
        similar_invoices = []
        
        for result in results:
            similarity = result.score
            payload = result.payload
            
            # Check for exact duplicate (same vendor + same amount + high similarity)
            if (
                similarity >= threshold
                and payload.get("vendor_name") == invoice_data.get("vendor_name")
                and abs(payload.get("total_amount", 0) - invoice_data.get("total_amount", 0)) < 0.01
            ):
                duplicate_risk = True
                duplicate_invoice_id = payload.get("invoice_number")
            
            similar_invoices.append({
                "invoice_number": payload.get("invoice_number"),
                "vendor_name": payload.get("vendor_name"),
                "total_amount": payload.get("total_amount"),
                "similarity": similarity,
                "decision": payload.get("decision"),
            })
        
        return {
            "is_duplicate": duplicate_risk,
            "duplicate_invoice_id": duplicate_invoice_id,
            "similar_invoices_found": len(similar_invoices),
            "similar_invoices": similar_invoices,
            "rag_retrieval_latency_ms": 0,  # Will be calculated by caller
        }
    
    async def get_contract_terms(self, vendor_name: str) -> Dict[str, Any]:
        """
        Retrieve contract terms for vendor.
        
        Args:
            vendor_name: Vendor name
        
        Returns:
            Contract terms (price limits, payment terms, etc.)
        """
        # Generate embedding for vendor name
        embedding = list(self.embedding_model.embed([f"Contract terms for {vendor_name}"]))[0]
        
        # Search contracts collection
        results = self.client.search(
            collection_name=self.contracts_collection,
            query_vector=embedding.tolist(),
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="vendor_name",
                        match=MatchValue(value=vendor_name),
                    ),
                ]
            ),
            limit=1,
        )
        
        if results:
            return {
                "contract_terms_found": True,
                "terms": results[0].payload,
            }
        else:
            return {
                "contract_terms_found": False,
                "terms": {},
            }
    
    async def get_price_history(self, vendor_name: str, item_description: str) -> Dict[str, Any]:
        """
        Get historical prices for item from vendor.
        
        Args:
            vendor_name: Vendor name
            item_description: Item description
        
        Returns:
            Price history with average, min, max
        """
        # Generate embedding for item
        embedding = list(self.embedding_model.embed([f"{vendor_name} {item_description} price"]))[0]
        
        # Search for similar invoices
        results = self.client.search(
            collection_name=self.invoices_collection,
            query_vector=embedding.tolist(),
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="vendor_name",
                        match=MatchValue(value=vendor_name),
                    ),
                ]
            ),
            limit=10,
        )
        
        # Extract prices from line items
        prices = []
        for result in results:
            # This is simplified - in production would parse line items
            pass
        
        return {
            "average_price": 0,
            "min_price": 0,
            "max_price": 0,
            "sample_count": len(results),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline(qdrant_url: str = "http://localhost:6333") -> RAGPipeline:
    """Get or create RAG pipeline singleton."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline(qdrant_url)
    return _rag_pipeline


async def check_invoice_duplicate(invoice_data: Dict, tenant_id: str) -> Dict[str, Any]:
    """
    Check if invoice is duplicate.
    
    Usage:
        result = await check_invoice_duplicate(invoice_data, "tenant-001")
        if result["is_duplicate"]:
            # Block invoice
            pass
    """
    pipeline = get_rag_pipeline()
    return await pipeline.check_duplicate(invoice_data, tenant_id)


async def index_processed_invoice(invoice_data: Dict, metadata: Dict):
    """
    Index processed invoice in RAG.
    
    Usage:
        await index_processed_invoice(extracted_invoice, {
            "tenant_id": "tenant-001",
            "decision": "AUTO_APPROVE",
        })
    """
    pipeline = get_rag_pipeline()
    await pipeline.index_invoice(invoice_data, metadata)
