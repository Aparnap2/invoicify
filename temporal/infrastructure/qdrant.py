"""
Qdrant Vector Database Client for Temporal Activities

Provides vector similarity search for invoices.
Adapted from ai/app/services/qdrant.py for Temporal use.
"""

import os
import logging
from typing import Optional, List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
)

logger = logging.getLogger(__name__)

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "invoices"
EMBEDDING_DIM = 384  # All-MiniLM-L6-v2 dimension


class QdrantClientWrapper:
    """
    Qdrant client wrapper for Temporal activities.

    Handles:
    - Collection management
    - Vector upsertion
    - Similarity search
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
            logger.error(f"Error creating collection: {e}")
            return False

    async def upsert(
        self,
        collection_name: str,
        points: List[dict],
    ) -> None:
        """
        Upsert points to collection.

        Args:
            collection_name: Name of the collection
            points: List of points to upsert
        """
        try:
            from qdrant_client.models import PointStruct

            qdrant_points = [
                PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p["payload"],
                )
                for p in points
            ]

            self.client.upsert(
                collection_name=collection_name,
                points=qdrant_points,
            )
        except Exception as e:
            logger.error(f"Error upserting points: {e}")
            raise

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        query_filter: Optional[Filter] = None,
        score_threshold: Optional[float] = None,
    ) -> List:
        """
        Search for similar vectors.

        Args:
            collection_name: Name of the collection
            query_vector: Query vector
            limit: Maximum results to return
            query_filter: Optional filter for search
            score_threshold: Minimum similarity score

        Returns:
            List of search results
        """
        try:
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
            )
            return results
        except Exception as e:
            logger.error(f"Error searching: {e}")
            raise

    async def retrieve(
        self,
        collection_name: str,
        ids: List[str],
    ) -> List:
        """
        Retrieve points by IDs.

        Args:
            collection_name: Name of the collection
            ids: List of point IDs

        Returns:
            List of retrieved points
        """
        try:
            results = self.client.retrieve(
                collection_name=collection_name,
                ids=ids,
            )
            return results
        except Exception as e:
            logger.error(f"Error retrieving points: {e}")
            raise

    async def count(
        self,
        collection_name: str,
        count_filter: Optional[Filter] = None,
    ) -> int:
        """
        Count points in collection.

        Args:
            collection_name: Name of the collection
            count_filter: Optional filter for counting

        Returns:
            Count of points
        """
        try:
            result = self.client.count(
                collection_name=collection_name,
                count_filter=count_filter,
            )
            return result.count
        except Exception as e:
            logger.error(f"Error counting points: {e}")
            return 0


# Singleton instance
_qdrant_client: Optional[QdrantClientWrapper] = None


def get_qdrant_client() -> QdrantClientWrapper:
    """Get singleton Qdrant client instance."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClientWrapper()
        _qdrant_client.ensure_collection()
    return _qdrant_client


def reset_qdrant_client():
    """Reset singleton (for testing)."""
    global _qdrant_client
    _qdrant_client = None