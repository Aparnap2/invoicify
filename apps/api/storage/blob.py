"""
Azure Blob Storage Client - Replaces Cloudflare R2

Usage:
    from storage.blob import BlobStorageClient
    
    client = BlobStorageClient()
    await client.upload_blob("invoices/tenant123/invoice.pdf", pdf_bytes)
    url = await client.get_blob_url("invoices/tenant123/invoice.pdf")
"""

import os
from typing import Optional, Dict, Any
from azure.storage.blob.aio import BlobServiceClient, BlobSasPermissions, generate_blob_sas
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


class BlobStorageClient:
    """
    Azure Blob Storage client for PDF storage.
    
    Replaces Cloudflare R2 with Azure Blob Storage.
    Uses DefaultAzureCredential for managed identity in production,
    connection string for local development with Azurite.
    """
    
    def __init__(self, connection_string: Optional[str] = None, account_url: Optional[str] = None):
        """
        Initialize blob client.
        
        Args:
            connection_string: Azure Storage connection string (for local dev with Azurite)
            account_url: Azure Storage account URL (for production with managed identity)
        """
        self.connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.account_url = account_url or os.getenv("AZURE_STORAGE_ACCOUNT_URL")
        self.container_name = os.getenv("AZURE_STORAGE_CONTAINER", "invoices")
        
        self._client: Optional[BlobServiceClient] = None
        self._container_client = None
    
    async def _get_client(self) -> BlobServiceClient:
        """Get or create blob service client."""
        if self._client is None:
            if self.connection_string:
                # Local development with Azurite
                self._client = BlobServiceClient.from_connection_string(
                    self.connection_string,
                    max_block_size=1024 * 1024 * 10,  # 10MB blocks
                )
            elif self.account_url:
                # Production with managed identity
                from azure.identity.aio import DefaultAzureCredential
                credential = DefaultAzureCredential()
                self._client = BlobServiceClient(
                    account_url=self.account_url,
                    credential=credential,
                )
            else:
                raise ValueError("Either connection_string or account_url must be provided")
        
        return self._client
    
    async def _get_container_client(self):
        """Get container client."""
        if self._container_client is None:
            client = await self._get_client()
            self._container_client = client.get_container_client(self.container_name)
        return self._container_client
    
    async def upload_blob(
        self,
        blob_name: str,
        data: bytes,
        content_type: str = "application/pdf",
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload blob to Azure Storage.
        
        Args:
            blob_name: Blob name (e.g., "invoices/tenant123/invoice.pdf")
            data: Binary data to upload
            content_type: MIME type
            metadata: Custom metadata
        
        Returns:
            Blob URL
        """
        container_client = await self._get_container_client()
        
        blob_client = container_client.get_blob_client(blob_name)
        
        await blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings={
                "content_type": content_type,
            },
            metadata=metadata or {},
        )
        
        logger.info("blob_uploaded", blob_name=blob_name, size=len(data))
        
        return blob_client.url
    
    async def download_blob(self, blob_name: str) -> bytes:
        """
        Download blob from Azure Storage.
        
        Args:
            blob_name: Blob name
        
        Returns:
            Binary data
        """
        container_client = await self._get_container_client()
        blob_client = container_client.get_blob_client(blob_name)
        
        download_stream = await blob_client.download_blob()
        data = await download_stream.readall()
        
        logger.info("blob_downloaded", blob_name=blob_name, size=len(data))
        
        return data
    
    async def get_blob_url(self, blob_name: str, expiry_hours: int = 1) -> str:
        """
        Get SAS URL for blob (time-limited access).
        
        Args:
            blob_name: Blob name
            expiry_hours: URL expiry time in hours
        
        Returns:
            SAS URL
        """
        if not self.connection_string:
            raise ValueError("SAS URLs require connection_string")
        
        container_client = await self._get_container_client()
        blob_client = container_client.get_blob_client(blob_name)
        
        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=blob_client.account_name,
            container_name=blob_client.container_name,
            blob_name=blob_name,
            account_key=blob_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=expiry_hours),
        )
        
        sas_url = f"{blob_client.url}?{sas_token}"
        
        return sas_url
    
    async def delete_blob(self, blob_name: str) -> None:
        """
        Delete blob from Azure Storage.
        
        Args:
            blob_name: Blob name
        """
        container_client = await self._get_container_client()
        blob_client = container_client.get_blob_client(blob_name)
        
        await blob_client.delete_blob()
        
        logger.info("blob_deleted", blob_name=blob_name)
    
    async def list_blobs(self, prefix: Optional[str] = None) -> list:
        """
        List blobs in container.
        
        Args:
            prefix: Optional prefix filter
        
        Returns:
            List of blob names
        """
        container_client = await self._get_container_client()
        
        blobs = []
        async for blob in container_client.list_blobs(name_starts_with=prefix):
            blobs.append(blob.name)
        
        return blobs
    
    async def create_container(self) -> None:
        """Create container if it doesn't exist."""
        client = await self._get_client()
        container_client = client.get_container_client(self.container_name)
        
        try:
            await container_client.create_container()
            logger.info("container_created", name=self.container_name)
        except Exception as e:
            if "ContainerAlreadyExists" in str(e):
                logger.debug("container_exists", name=self.container_name)
            else:
                raise


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

async def upload_invoice_pdf(tenant_id: str, invoice_id: str, pdf_bytes: bytes, metadata: Dict[str, str]) -> str:
    """
    Upload invoice PDF to Azure Storage.
    
    Args:
        tenant_id: Tenant ID
        invoice_id: Invoice ID
        pdf_bytes: PDF binary data
        metadata: Custom metadata
    
    Returns:
        Blob URL
    """
    client = BlobStorageClient()
    blob_name = f"{tenant_id}/{invoice_id}.pdf"
    return await client.upload_blob(blob_name, pdf_bytes, "application/pdf", metadata)


async def get_invoice_pdf_url(tenant_id: str, invoice_id: str) -> str:
    """
    Get time-limited SAS URL for invoice PDF.
    
    Args:
        tenant_id: Tenant ID
        invoice_id: Invoice ID
    
    Returns:
        SAS URL
    """
    client = BlobStorageClient()
    blob_name = f"{tenant_id}/{invoice_id}.pdf"
    return await client.get_blob_url(blob_name, expiry_hours=1)
