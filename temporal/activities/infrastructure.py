"""Infrastructure adapters for Temporal activities.

This module provides adapters for external services:
- Neo4jActivityAdapter: Vendor history and pattern tracking
- QdrantActivityAdapter: Vector similarity search
- IBMCOSAdapter: ML model persistence
"""

import logging
import os
import pickle
from typing import Optional, List, Dict, Any
from io import BytesIO

import ibm_boto3
from ibm_botocore.config import Config

from temporal.infrastructure.neo4j import get_neo4j_client
from temporal.infrastructure.qdrant import get_qdrant_client

logger = logging.getLogger(__name__)


class Neo4jActivityAdapter:
    """Adapter for Neo4j operations in Temporal activities."""

    def __init__(self):
        """Initialize the Neo4j adapter."""
        self._client = None

    async def get_client(self):
        """Get or create Neo4j client."""
        if self._client is None:
            self._client = get_neo4j_client()
        return self._client

    async def get_vendor_history(
        self, vendor_name: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get vendor invoice history from Neo4j.

        Args:
            vendor_name: Name of the vendor
            limit: Maximum number of invoices to return

        Returns:
            List of invoice dictionaries with amount and status
        """
        try:
            client = await self.get_client()
            invoices = await client.get_invoices_by_vendor(vendor_name)

            return [
                {
                    "amount": float(i.get("amount", 0)),
                    "status": i.get("status", "UNKNOWN"),
                    "invoice_number": i.get("invoice_number", ""),
                    "date": i.get("created_at"),
                }
                for i in invoices[-limit:]
            ]
        except Exception as e:
            logger.error(f"Failed to get vendor history for {vendor_name}: {e}")
            return []

    async def find_anomaly_patterns(
        self, vendor_name: str
    ) -> List[Dict[str, Any]]:
        """
        Find anomaly patterns in vendor payment history.

        Args:
            vendor_name: Name of the vendor

        Returns:
            List of anomaly patterns
        """
        try:
            client = await self.get_client()
            patterns = await client.find_anomaly_patterns(vendor_name)
            return patterns
        except Exception as e:
            logger.error(f"Failed to find anomaly patterns for {vendor_name}: {e}")
            return []

    async def save_invoice(
        self,
        vendor_name: str,
        invoice_number: str,
        amount: float,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Save invoice to Neo4j.

        Args:
            vendor_name: Name of the vendor
            invoice_number: Invoice number
            amount: Invoice amount
            status: Invoice status
            metadata: Additional metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self.get_client()
            # Use invoice_number as invoice_id and current date as due_date
            from datetime import datetime
            due_date = datetime.now().strftime("%Y-%m-%d")
            
            await client.create_invoice(
                invoice_id=invoice_number,
                vendor_name=vendor_name,
                amount=amount,
                status=status,
                due_date=due_date,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save invoice {invoice_number}: {e}")
            return False


class QdrantActivityAdapter:
    """Adapter for Qdrant vector operations in Temporal activities."""

    def __init__(self):
        """Initialize the Qdrant adapter."""
        self._client = None

    async def get_client(self):
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = get_qdrant_client()
        return self._client

    async def search_similar_invoices(
        self,
        vendor_name: str,
        amount: float,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar invoices using vector similarity.

        Args:
            vendor_name: Name of the vendor
            amount: Invoice amount
            limit: Maximum number of results

        Returns:
            List of similar invoices
        """
        try:
            client = await self.get_client()
            # Create a simple feature vector for similarity search
            # In production, this would use more sophisticated features
            features = [amount, len(vendor_name)]
            
            results = await client.search(
                collection_name="invoices",
                query_vector=features,
                limit=limit,
                query_filter={"must": [{"key": "vendor_name", "match": {"value": vendor_name}}]},
            )
            
            return [
                {
                    "invoice_number": r.payload.get("invoice_number"),
                    "amount": r.payload.get("amount"),
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to search similar invoices: {e}")
            return []

    async def index_invoice(
        self,
        vendor_name: str,
        invoice_number: str,
        amount: float,
        features: Optional[List[float]] = None,
    ) -> bool:
        """
        Index invoice in Qdrant for similarity search.

        Args:
            vendor_name: Name of the vendor
            invoice_number: Invoice number
            amount: Invoice amount
            features: Feature vector for similarity search

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self.get_client()
            
            # Generate feature vector if not provided
            if features is None:
                features = [amount, len(vendor_name)]
            
            # Use hash of invoice_number as integer ID (Qdrant requires int or UUID)
            import hashlib
            point_id = int(hashlib.md5(f"{vendor_name}_{invoice_number}".encode()).hexdigest()[:8], 16)
            
            await client.upsert(
                collection_name="invoices",
                points=[
                    {
                        "id": point_id,
                        "vector": features,
                        "payload": {
                            "vendor_name": vendor_name,
                            "invoice_number": invoice_number,
                            "amount": amount,
                        },
                    }
                ],
            )
            return True
        except Exception as e:
            logger.error(f"Failed to index invoice {invoice_number}: {e}")
            return False


class IBMCOSAdapter:
    """Adapter for IBM Cloud Object Storage operations.

    Used for ML model persistence in serverless environments.
    """

    def __init__(self):
        """Initialize the IBM COS adapter."""
        self._client = None
        self.bucket = os.getenv("IBM_COS_BUCKET", "nivi-lake-prod")

    def get_client(self):
        """Get or create IBM COS client."""
        if self._client is None:
            self._client = ibm_boto3.client(
                service_name="s3",
                ibm_api_key_id=os.getenv("IBM_CLOUD_API_KEY"),
                ibm_service_instance_id=os.getenv("IBM_COS_INSTANCE_ID"),
                config=Config(signature_version="oauth"),
                endpoint_url=os.getenv(
                    "IBM_COS_ENDPOINT",
                    "https://s3.us-south.cloud-object-storage.appdomain.cloud",
                ),
            )
        return self._client

    async def load_model(self, vendor_id: str) -> Optional[Any]:
        """
        Load ML model from IBM COS.

        Args:
            vendor_id: Vendor identifier

        Returns:
            Loaded model or None if not found
        """
        try:
            client = self.get_client()
            key = f"ml-models/{vendor_id}.pkl"

            response = client.get_object(Bucket=self.bucket, Key=key)
            model_bytes = response["Body"].read()
            model = pickle.loads(model_bytes)

            logger.debug(f"Loaded model for vendor: {vendor_id}")
            return model

        except client.exceptions.NoSuchKey:
            logger.debug(f"No existing model for vendor: {vendor_id}")
            return None
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return None

    async def save_model(self, vendor_id: str, model: Any) -> bool:
        """
        Save ML model to IBM COS.

        Args:
            vendor_id: Vendor identifier
            model: Trained model to save

        Returns:
            True if successful, False otherwise
        """
        try:
            client = self.get_client()
            key = f"ml-models/{vendor_id}.pkl"

            # Serialize model
            model_bytes = pickle.dumps(model)

            # Upload to COS
            client.put_object(Bucket=self.bucket, Key=key, Body=model_bytes)

            logger.debug(f"Saved model for vendor: {vendor_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving model: {e}")
            return False

    async def load_invoice_document(
        self, invoice_id: str
    ) -> Optional[BytesIO]:
        """
        Load invoice document from IBM COS.

        Args:
            invoice_id: Invoice identifier

        Returns:
            Invoice document as BytesIO or None if not found
        """
        try:
            client = self.get_client()
            key = f"invoices/{invoice_id}.pdf"

            response = client.get_object(Bucket=self.bucket, Key=key)
            return BytesIO(response["Body"].read())

        except client.exceptions.NoSuchKey:
            logger.debug(f"No invoice document found: {invoice_id}")
            return None
        except Exception as e:
            logger.error(f"Error loading invoice document: {e}")
            return None

    async def save_invoice_document(
        self, invoice_id: str, document_data: bytes
    ) -> bool:
        """
        Save invoice document to IBM COS.

        Args:
            invoice_id: Invoice identifier
            document_data: Document bytes

        Returns:
            True if successful, False otherwise
        """
        try:
            client = self.get_client()
            key = f"invoices/{invoice_id}.pdf"

            client.put_object(Bucket=self.bucket, Key=key, Body=document_data)

            logger.debug(f"Saved invoice document: {invoice_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving invoice document: {e}")
            return False


# Singleton instances
_neo4j_adapter: Optional[Neo4jActivityAdapter] = None
_qdrant_adapter: Optional[QdrantActivityAdapter] = None
_cos_adapter: Optional[IBMCOSAdapter] = None


def get_neo4j_adapter() -> Neo4jActivityAdapter:
    """Get the singleton Neo4j adapter instance."""
    global _neo4j_adapter
    if _neo4j_adapter is None:
        _neo4j_adapter = Neo4jActivityAdapter()
    return _neo4j_adapter


def get_qdrant_adapter() -> QdrantActivityAdapter:
    """Get the singleton Qdrant adapter instance."""
    global _qdrant_adapter
    if _qdrant_adapter is None:
        _qdrant_adapter = QdrantActivityAdapter()
    return _qdrant_adapter


def get_cos_adapter() -> IBMCOSAdapter:
    """Get the singleton IBM COS adapter instance."""
    global _cos_adapter
    if _cos_adapter is None:
        _cos_adapter = IBMCOSAdapter()
    return _cos_adapter