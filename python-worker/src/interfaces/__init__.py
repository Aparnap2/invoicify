"""
Abstract Base Classes for Infrastructure Adapters
Implements the Adapter Pattern for Switchable Architecture
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.

    Implementations:
    - PostgresAdapter: Standard PostgreSQL (Supabase/Free Tier)
    - HyperProtectAdapter: IBM Hyper Protect PostgreSQL (Trial/Enterprise)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish database connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    async def save_invoice(self, invoice_data: Dict[str, Any]) -> str:
        """
        Save invoice to database.

        Args:
            invoice_data: Invoice data dictionary

        Returns:
            Invoice ID
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def update_vendor_trust(self, vendor_id: str, trust_level: int) -> None:
        """
        Update vendor trust level.

        Args:
            vendor_id: Vendor identifier
            trust_level: New trust level (1-3)
        """
        pass

    @abstractmethod
    async def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve invoice by ID.

        Args:
            invoice_id: Invoice identifier

        Returns:
            Invoice data or None
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check database connectivity.

        Returns:
            True if healthy
        """
        pass


class SecretsAdapter(ABC):
    """
    Abstract base class for secrets management adapters.

    Implementations:
    - EnvSecretsAdapter: Environment variables (Free Tier)
    - IBMSecretsAdapter: IBM Secrets Manager (Trial/Enterprise)
    """

    @abstractmethod
    def get_secret(self, key: str) -> str:
        """
        Retrieve secret by key.

        Args:
            key: Secret key/name

        Returns:
            Secret value

        Raises:
            KeyError: If secret not found
        """
        pass

    @abstractmethod
    def get_database_url(self) -> str:
        """
        Get database connection URL.

        Returns:
            Database URL string
        """
        pass

    @abstractmethod
    def get_ibm_api_key(self) -> str:
        """
        Get IBM Cloud API key.

        Returns:
            API key string
        """
        pass

    @abstractmethod
    def get_temporal_cert(self) -> str:
        """
        Get Temporal mTLS certificate.

        Returns:
            Certificate content
        """
        pass


class ObjectStorageAdapter(ABC):
    """
    Abstract base class for object storage adapters.

    Implementations:
    - MinIOAdapter: MinIO/Local (Free Tier)
    - IBMCOSAdapter: IBM Cloud Object Storage (Trial/Enterprise)
    """

    @abstractmethod
    async def upload_file(self, bucket: str, key: str, data: bytes) -> str:
        """
        Upload file to object storage.

        Args:
            bucket: Bucket name
            key: Object key/path
            data: File bytes

        Returns:
            Object URL
        """
        pass

    @abstractmethod
    async def download_file(self, bucket: str, key: str) -> bytes:
        """
        Download file from object storage.

        Args:
            bucket: Bucket name
            key: Object key/path

        Returns:
            File bytes
        """
        pass

    @abstractmethod
    async def delete_file(self, bucket: str, key: str) -> None:
        """
        Delete file from object storage.

        Args:
            bucket: Bucket name
            key: Object key/path
        """
        pass


class WarehouseAdapter(ABC):
    """
    Abstract base class for analytics warehouse adapters.

    Implementations:
    - DuckDBAdapter: DuckDB + Parquet (Free Tier)
    - Db2WarehouseAdapter: IBM Db2 Warehouse (Trial/Enterprise)
    """

    @abstractmethod
    async def query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute analytical query.

        Args:
            sql: SQL query string

        Returns:
            Query results
        """
        pass

    @abstractmethod
    async def save_analytics(self, table: str, data: Dict[str, Any]) -> None:
        """
        Save analytics data.

        Args:
            table: Target table
            data: Data to save
        """
        pass
