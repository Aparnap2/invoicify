"""
Azure Blob Storage utility for invoice PDF management.

Provides async upload/download operations for invoice files.
Used by Telegram MCP, email intake, and web upload endpoints.

Features:
- Async upload with metadata
- Presigned URL generation (SAS tokens)
- Automatic container creation
- Content-Type detection
- Error handling with structured logging

Usage:
    from src.storage.azure_blob import upload_pdf_bytes, get_blob_url
    
    # Upload PDF bytes
    blob_url = await upload_pdf_bytes(
        file_bytes=pdf_data,
        blob_name="invoices/telegram/2024/01/abc123.pdf",
        metadata={"source": "telegram", "chat_id": "123456"}
    )
    
    # Get presigned URL for download
    download_url = await get_blob_url(blob_name, expiry_minutes=60)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import structlog
from azure.storage.blob.aio import (
    BlobServiceClient,
    ContainerClient,
    BlobClient,
)
from azure.core.exceptions import AzureError, ResourceExistsError

logger = structlog.get_logger()

# Configuration
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "invoices")

# Module-level client cache
_blob_service_client: Optional[BlobServiceClient] = None
_container_client: Optional[ContainerClient] = None


async def get_blob_service_client() -> BlobServiceClient:
    """
    Get or create BlobServiceClient (singleton pattern).
    
    Returns:
        Async BlobServiceClient instance
        
    Raises:
        ValueError: If connection string not configured
    """
    global _blob_service_client
    
    if _blob_service_client is None:
        if not AZURE_STORAGE_CONNECTION_STRING:
            logger.error("azure_storage_connection_string_missing")
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING not configured. "
                "Set this environment variable to use Azure Blob Storage."
            )
        
        _blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )
        logger.info("azure_blob_service_client_initialized")
    
    return _blob_service_client


async def get_container_client() -> ContainerClient:
    """
    Get or create ContainerClient (singleton pattern).
    Creates container if it doesn't exist.
    
    Returns:
        Async ContainerClient instance
        
    Raises:
        ValueError: If connection string not configured
    """
    global _container_client
    
    if _container_client is None:
        service_client = await get_blob_service_client()
        _container_client = service_client.get_container_client(AZURE_STORAGE_CONTAINER)
        
        # Create container if it doesn't exist
        try:
            await _container_client.create_container()
            logger.info(
                "azure_blob_container_created",
                container_name=AZURE_STORAGE_CONTAINER,
            )
        except ResourceExistsError:
            # Container already exists
            logger.debug(
                "azure_blob_container_exists",
                container_name=AZURE_STORAGE_CONTAINER,
            )
        except AzureError as e:
            logger.error(
                "azure_blob_container_creation_failed",
                container_name=AZURE_STORAGE_CONTAINER,
                error=str(e),
            )
            raise
    
    return _container_client


async def upload_pdf_bytes(
    file_bytes: bytes,
    blob_name: str,
    tenant_id: str,
    metadata: Optional[Dict[str, Any]] = None,
    content_type: str = "application/pdf",
) -> str:
    """
    Upload PDF bytes to Azure Blob Storage.
    
    Args:
        file_bytes: Raw PDF file bytes
        blob_name: Blob path/name (e.g., "invoices/telegram/2024/01/abc123.pdf")
        metadata: Optional metadata dict (stored as blob tags)
        content_type: MIME type (default: application/pdf)
    
    Returns:
        Blob URL (e.g., "https://account.blob.core.windows.net/container/path.pdf")
        
    Raises:
        ValueError: If file_bytes empty or blob_name invalid
        AzureError: If upload fails
    """
    if not file_bytes:
        logger.error("upload_pdf_bytes_empty_file")
        raise ValueError("file_bytes cannot be empty")
    
    if not blob_name:
        logger.error("upload_pdf_bytes_missing_blob_name")
        raise ValueError("blob_name cannot be empty")
    
    if not tenant_id:
        logger.error("upload_pdf_bytes_missing_tenant_id")
        raise ValueError("tenant_id cannot be empty")
    
    # Prepend tenant_id to blob path for tenant isolation
    tenant_isolated_path = f"{tenant_id}/documents/{blob_name}"
    
    if not tenant_isolated_path.endswith(".pdf"):
        logger.warning("upload_pdf_bytes_non_pdf_extension", blob_name=tenant_isolated_path)
    
    container_client = await get_container_client()
    blob_client = container_client.get_blob_client(tenant_isolated_path)
    
    # Prepare metadata (convert all values to strings)
    blob_metadata = {}
    if metadata:
        for key, value in metadata.items():
            if value is not None:
                blob_metadata[key] = str(value)
    
    # Add timestamp
    blob_metadata["uploaded_at"] = datetime.now(timezone.utc).isoformat()
    
    try:
        # Upload blob
        await blob_client.upload_blob(
            data=file_bytes,
            blob_type="BlockBlob",
            content_type=content_type,
            metadata=blob_metadata,
            overwrite=True,  # Overwrite if exists
        )
        
        blob_url = blob_client.url
        
        logger.info(
            "azure_blob_upload_success",
            blob_name=blob_name,
            blob_url=blob_url,
            file_size=len(file_bytes),
            metadata_keys=list(blob_metadata.keys()),
        )
        
        return blob_url
        
    except AzureError as e:
        logger.error(
            "azure_blob_upload_failed",
            blob_name=blob_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def get_blob_url(
    blob_name: str,
    tenant_id: str,
    expiry_minutes: int = 60,
) -> str:
    """
    Generate presigned URL (SAS token) for blob download.
    
    Args:
        blob_name: Blob path/name
        tenant_id: Tenant identifier for path isolation
        expiry_minutes: URL validity duration (default: 60 minutes)
    
    Returns:
        Presigned URL with SAS token
        
    Raises:
        ValueError: If blob_name invalid or connection string missing
    """
    if not blob_name:
        logger.error("get_blob_url_missing_blob_name")
        raise ValueError("blob_name cannot be empty")
    
    if not tenant_id:
        logger.error("get_blob_url_missing_tenant_id")
        raise ValueError("tenant_id cannot be empty")
    
    tenant_isolated_path = f"{tenant_id}/documents/{blob_name}"
    
    container_client = await get_container_client()
    blob_client = container_client.get_blob_client(tenant_isolated_path)
    
    # Generate SAS token
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions
    
    expiry = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
    
    sas_token = generate_blob_sas(
        account_name=container_client.account_name,
        container_name=container_client.container_name,
        blob_name=blob_name,
        account_key=container_client.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )
    
    # Build presigned URL
    presigned_url = f"{blob_client.url}?{sas_token}"
    
    logger.debug(
        "azure_blob_sas_generated",
        blob_name=blob_name,
        expiry_minutes=expiry_minutes,
    )
    
    return presigned_url


async def download_blob_bytes(blob_name: str, tenant_id: str) -> bytes:
    """
    Download blob content as bytes.
    
    Args:
        blob_name: Blob path/name
        tenant_id: Tenant identifier for path isolation
    
    Returns:
        Raw blob bytes
        
    Raises:
        ValueError: If blob_name invalid
        AzureError: If blob not found or download fails
    """
    if not blob_name:
        logger.error("download_blob_bytes_missing_blob_name")
        raise ValueError("blob_name cannot be empty")
    
    if not tenant_id:
        logger.error("download_blob_bytes_missing_tenant_id")
        raise ValueError("tenant_id cannot be empty")
    
    tenant_isolated_path = f"{tenant_id}/documents/{blob_name}"
    
    container_client = await get_container_client()
    blob_client = container_client.get_blob_client(tenant_isolated_path)
    
    try:
        download_stream = await blob_client.download_blob()
        blob_bytes = await download_stream.readall()
        
        logger.debug(
            "azure_blob_download_success",
            blob_name=blob_name,
            file_size=len(blob_bytes),
        )
        
        return blob_bytes
        
    except AzureError as e:
        logger.error(
            "azure_blob_download_failed",
            blob_name=blob_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def delete_blob(blob_name: str, tenant_id: str) -> bool:
    """
    Delete blob from storage.
    
    Args:
        blob_name: Blob path/name
        tenant_id: Tenant identifier for path isolation
    
    Returns:
        True if deleted, False if blob didn't exist
        
    Raises:
        AzureError: If deletion fails
    """
    if not blob_name:
        logger.error("delete_blob_missing_blob_name")
        raise ValueError("blob_name cannot be empty")
    
    if not tenant_id:
        logger.error("delete_blob_missing_tenant_id")
        raise ValueError("tenant_id cannot be empty")
    
    tenant_isolated_path = f"{tenant_id}/documents/{blob_name}"
    
    container_client = await get_container_client()
    blob_client = container_client.get_blob_client(tenant_isolated_path)
    
    try:
        await blob_client.delete_blob()
        
        logger.info(
            "azure_blob_deleted",
            blob_name=blob_name,
        )
        
        return True
        
    except AzureError as e:
        # Check if blob doesn't exist (404)
        if e.status_code == 404:
            logger.debug(
                "azure_blob_not_found",
                blob_name=blob_name,
            )
            return False
        
        logger.error(
            "azure_blob_delete_failed",
            blob_name=blob_name,
            error=str(e),
        )
        raise


async def blob_exists(blob_name: str, tenant_id: str) -> bool:
    """
    Check if blob exists in container.
    
    Args:
        blob_name: Blob path/name
        tenant_id: Tenant identifier for path isolation
    
    Returns:
        True if exists, False otherwise
    """
    if not blob_name or not tenant_id:
        return False
    
    tenant_isolated_path = f"{tenant_id}/documents/{blob_name}"
    
    container_client = await get_container_client()
    blob_client = container_client.get_blob_client(tenant_isolated_path)
    
    try:
        return await blob_client.exists()
    except AzureError:
        return False


# CLI entry point for testing
if __name__ == "__main__":
    import sys
    import asyncio
    
    async def test_upload():
        """Test blob upload with sample data."""
        print("Azure Blob Storage - Test Mode")
        print(f"Connection String configured: {bool(AZURE_STORAGE_CONNECTION_STRING)}")
        print(f"Container: {AZURE_STORAGE_CONTAINER}")
        
        if not AZURE_STORAGE_CONNECTION_STRING:
            print("❌ AZURE_STORAGE_CONNECTION_STRING not set")
            return
        
        tenant_id = "test-tenant-001"
        
        try:
            # Test with sample PDF bytes (minimal valid PDF header)
            sample_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
            
            blob_name = f"test/{datetime.now().strftime('%Y/%m/%d')}/test_upload.pdf"
            
            print(f"\nUploading test file: {blob_name}")
            blob_url = await upload_pdf_bytes(
                file_bytes=sample_pdf,
                blob_name=blob_name,
                tenant_id=tenant_id,
                metadata={"test": "true", "purpose": "cli_test"},
            )
            
            print(f"✅ Upload successful: {blob_url}")
            
            # Test existence check
            exists = await blob_exists(blob_name, tenant_id)
            print(f"✅ Blob exists: {exists}")
            
            # Test download
            downloaded = await download_blob_bytes(blob_name, tenant_id)
            print(f"✅ Download successful: {len(downloaded)} bytes")
            
            # Test presigned URL
            presigned = await get_blob_url(blob_name, tenant_id, expiry_minutes=5)
            print(f"✅ Presigned URL generated (expires in 5 min)")
            print(f"   {presigned[:100]}...")
            
            # Cleanup: delete test blob
            deleted = await delete_blob(blob_name, tenant_id)
            print(f"✅ Test blob deleted: {deleted}")
            
            print("\n✅ All tests passed!")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
    
    if "--test" in sys.argv:
        asyncio.run(test_upload())
    else:
        print("Azure Blob Storage Utility")
        print("Usage: python -m src.storage.azure_blob --test")
        print(f"Container: {AZURE_STORAGE_CONTAINER}")
        print(f"Connection configured: {bool(AZURE_STORAGE_CONNECTION_STRING)}")
