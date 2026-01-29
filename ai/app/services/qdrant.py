"""
Qdrant Vector Database Service for Invoice Semantic Search

Provides embedding generation and vector search for invoices.
Uses FastEmbed for local embedding generation.
"""

import os
from typing import Optional, list
import numpy as np
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from fastembed import TextEmbedding


# ============================================================================
# Configuration
# ============================================================================

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "invoices"
EMBEDDING_DIM = 384  # All-MiniLM-L6-v2 dimension


# ============================================================================
# Data Models
# ============================================================================


class InvoiceDocument(BaseModel):
    """Invoice document for vector storage."""
    invoice_id: str
    tenant_id: str
    vendor_name: str
    invoice_number: str
    total_amount: float
    currency: str
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    status: str
    extracted_text: str  # Concatenated text for embedding
    metadata: dict = {}


class SearchResult(BaseModel):
    """Search result from Qdrant."""
    invoice_id: str
    score: float
    vendor_name: str
    invoice_number: str
    total_amount: float
    invoice_date: Optional[str] = None
    status: str


# ============================================================================
# Qdrant Service
# ============================================================================


class QdrantService:
    """
    Qdrant service for invoice semantic search.

    Handles:
    - Collection management
    - Vector upsertion
    - Semantic search
    """

    def __init__(
        self,
        url: str = QDRANT_URL,
        api_key: Optional[str] = QDRANT_API_KEY,
        collection_name: str = COLLECTION_NAME,
    ):
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.client = QdrantClient(url=url, api_key=api_key)
        self.embedding_model: Optional[TextEmbedding] = None

    def _get_embedding_model(self) -> TextEmbedding:
        """Lazy initialization of embedding model."""
        if self.embedding_model is None:
            # Use BAAI/bge-small-en-v1.5 for good quality/speed tradeoff
            # Or all-MiniLM-L6-v2 for fastest
            self.embedding_model = TextEmbedding(
                model_name="BAAI/bge-small-en-v1.5",
                providers=["Openvino"],  # Use CPU inference
            )
        return self.embedding_model

    def ensure_collection(self) -> bool:
        """
        Create collection if it doesn't exist.

        Returns True if collection exists or was created successfully.
        """
        try:
            if not self.client.collection_exists(self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                # Create payload index for filtering
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="tenant_id",
                    field_schema="keyword",
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="vendor_name",
                    field_schema="keyword",
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="status",
                    field_schema="keyword",
                )
            return True
        except Exception as e:
            print(f"Error creating collection: {e}")
            return False

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for text using FastEmbed.

        Args:
            text: Text to embed

        Returns:
            List of embedding floats
        """
        model = self._get_embedding_model()
        # FastEmbed returns generator, take first result
        embeddings = list(model.embed([text]))
        return embeddings[0].tolist()

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        model = self._get_embedding_model()
        embeddings = list(model.embed(texts))
        return [e.tolist() for e in embeddings]

    def upsert_invoice(self, invoice: InvoiceDocument) -> bool:
        """
        Upsert a single invoice document.

        Args:
            invoice: Invoice document to store

        Returns:
            True if successful
        """
        try:
            # Generate embedding from extracted text
            embedding = self.generate_embedding(invoice.extracted_text)

            # Create payload
            payload = invoice.model_dump()
            del payload["invoice_id"]  # Use as point ID instead
            del payload["extracted_text"]  # Keep only metadata in payload

            # Store embedding in payload for retrieval
            payload["extracted_text_preview"] = invoice.extracted_text[:500]

            point = PointStruct(
                id=invoice.invoice_id,
                vector=embedding,
                payload=payload,
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
            return True
        except Exception as e:
            print(f"Error upserting invoice: {e}")
            return False

    def upsert_invoices_batch(
        self, invoices: list[InvoiceDocument], batch_size: int = 32
    ) -> tuple[int, int]:
        """
        Upsert multiple invoices in batches.

        Args:
            invoices: List of invoice documents
            batch_size: Batch size for processing

        Returns:
            Tuple of (successful, failed)
        """
        successful = 0
        failed = 0

        for i in range(0, len(invoices), batch_size):
            batch = invoices[i : i + batch_size]

            try:
                # Generate embeddings for batch
                texts = [inv.extracted_text for inv in batch]
                embeddings = self.generate_embeddings_batch(texts)

                points = []
                for invoice, embedding in zip(batch, embeddings):
                    payload = invoice.model_dump()
                    del payload["invoice_id"]
                    del payload["extracted_text"]
                    payload["extracted_text_preview"] = invoice.extracted_text[:500]

                    points.append(
                        PointStruct(
                            id=invoice.invoice_id,
                            vector=embedding,
                            payload=payload,
                        )
                    )

                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
                successful += len(points)
            except Exception as e:
                print(f"Error upserting batch: {e}")
                failed += len(batch)

        return successful, failed

    def search(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        limit: int = 10,
        min_score: float = 0.5,
    ) -> list[SearchResult]:
        """
        Search invoices using semantic query.

        Args:
            query: Natural language search query
            tenant_id: Optional tenant filter
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            List of search results sorted by score
        """
        # Generate query embedding
        query_embedding = self.generate_embedding(query)

        # Build filter
        must_conditions = []
        if tenant_id:
            must_conditions.append(
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            )

        search_filter = Filter(must=must_conditions) if must_conditions else None

        # Search
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
            score_threshold=min_score,
            query_filter=search_filter,
        )

        # Convert to SearchResult
        search_results = []
        for hit in results:
            payload = hit.payload
            search_results.append(
                SearchResult(
                    invoice_id=hit.id,
                    score=hit.score,
                    vendor_name=payload.get("vendor_name", ""),
                    invoice_number=payload.get("invoice_number", ""),
                    total_amount=payload.get("total_amount", 0),
                    invoice_date=payload.get("invoice_date"),
                    status=payload.get("status", ""),
                )
            )

        return search_results

    def get_invoice(self, invoice_id: str) -> Optional[dict]:
        """
        Get invoice by ID.

        Args:
            invoice_id: Invoice ID

        Returns:
            Invoice payload or None
        """
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[invoice_id],
            )
            if points:
                return points[0].payload
            return None
        except Exception as e:
            print(f"Error retrieving invoice: {e}")
            return None

    def delete_invoice(self, invoice_id: str) -> bool:
        """
        Delete invoice by ID.

        Args:
            invoice_id: Invoice ID

        Returns:
            True if successful
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points=[invoice_id],
            )
            return True
        except Exception as e:
            print(f"Error deleting invoice: {e}")
            return False

    def count_invoices(self, tenant_id: Optional[str] = None) -> int:
        """
        Count invoices in collection.

        Args:
            tenant_id: Optional tenant filter

        Returns:
            Count of invoices
        """
        try:
            filter_conditions = None
            if tenant_id:
                filter_conditions = Filter(must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
                ])

            count = self.client.count(
                collection_name=self.collection_name,
                count_filter=filter_conditions,
            )
            return count.count
        except Exception as e:
            print(f"Error counting invoices: {e}")
            return 0


# ============================================================================
# Singleton
# ============================================================================

_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """Get singleton Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service


def reset_qdrant_service():
    """Reset singleton (for testing)."""
    global _qdrant_service
    _qdrant_service = None
