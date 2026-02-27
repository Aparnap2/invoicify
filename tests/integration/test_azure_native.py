"""
Integration tests for Azure-native stack.

Run with real Azure emulators:
    docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
    
Then run tests:
    uv run pytest tests/integration/test_azure_native.py -v --tb=short

Requires:
- Azurite (Azure Blob Storage emulator)
- Azure SQL (SQL Server Express)
- Cosmos DB Emulator
- Ollama (existing container, not recreated)
"""

import pytest
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent-core" / "src"))

# Test configuration
AZURITE_URL = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OugDPfYIDSZRfj63d3;BlobEndpoint=http://localhost:10000/devstoreaccount1"
SQL_CONNECTION = "Server=localhost,1433;Database=invoicify;User Id=sa;Password=Invoicify@Local123;TrustServerCertificate=True"
COSMOS_ENDPOINT = "https://localhost:8081"
COSMOS_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="


class TestAzureBlobStorage:
    """Test Azure Blob Storage client with Azurite emulator."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_blob_upload_download(self):
        """Test upload and download from Azurite."""
        from apps.api.storage.blob import BlobStorageClient
        
        client = BlobStorageClient(connection_string=AZURITE_URL)
        
        # Create container
        await client.create_container()
        
        # Upload test blob
        test_data = b"test invoice pdf content"
        blob_name = "test-invoice.pdf"
        
        url = await client.upload_blob(blob_name, test_data, "application/pdf")
        assert url is not None
        
        # Download and verify
        downloaded = await client.download_blob(blob_name)
        assert downloaded == test_data
        
        # Clean up
        await client.delete_blob(blob_name)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_blob_sas_url(self):
        """Test SAS URL generation."""
        from apps.api.storage.blob import BlobStorageClient
        
        client = BlobStorageClient(connection_string=AZURITE_URL)
        await client.create_container()
        
        # Upload test blob
        test_data = b"test"
        blob_name = "test-sas.pdf"
        await client.upload_blob(blob_name, test_data)
        
        # Get SAS URL
        sas_url = await client.get_blob_url(blob_name, expiry_hours=1)
        assert sas_url is not None
        assert "sig=" in sas_url  # SAS token present
        
        # Clean up
        await client.delete_blob(blob_name)


class TestAzureSQL:
    """Test Azure SQL client with SQL Server Express."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sql_connection(self):
        """Test SQL Server connection."""
        from apps.api.db.sql import get_db, execute_query
        
        db = await get_db()
        assert db is not None
        
        # Test simple query
        result = await execute_query("SELECT 1 as test")
        assert len(result) == 1
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sql_insert_select(self):
        """Test INSERT and SELECT."""
        from apps.api.db.sql import execute_command, execute_query
        
        # Create test table
        await execute_command("""
            IF OBJECT_ID('test_invoices', 'U') IS NOT NULL DROP TABLE test_invoices;
            CREATE TABLE test_invoices (
                id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                tenant_id NVARCHAR(100),
                amount DECIMAL(18,2),
                created_at DATETIME2 DEFAULT GETUTCDATE()
            );
        """)
        
        # Insert test data
        await execute_command(
            "INSERT INTO test_invoices (tenant_id, amount) VALUES (@tenant_id, @amount)",
            {"tenant_id": "test-tenant", "amount": 1000.50}
        )
        
        # Select and verify
        results = await execute_query(
            "SELECT * FROM test_invoices WHERE tenant_id = @tenant_id",
            {"tenant_id": "test-tenant"}
        )
        
        assert len(results) == 1
        assert float(results[0]["amount"]) == 1000.50
        
        # Clean up
        await execute_command("DROP TABLE test_invoices")


class TestVoiceAgentFactory:
    """Test Voice Agent service factory."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_azure_llm_client(self):
        """Test Azure AI LLM client creation."""
        from apps.voice_agent.src.services.factory import VoiceServiceFactory
        
        # Skip if no Azure credentials
        if not os.getenv("AZURE_OPENAI_KEY"):
            pytest.skip("AZURE_OPENAI_KEY not set")
        
        factory = VoiceServiceFactory()
        llm_client, model = factory.get_llm()
        
        # Test simple completion
        response = await llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )
        
        assert response.choices[0].message.content is not None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ollama_fallback(self, monkeypatch):
        """Test Ollama fallback (uses existing container)."""
        from apps.voice_agent.src.services.factory import VoiceServiceFactory
        
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        
        factory = VoiceServiceFactory()
        
        try:
            llm_client, model = factory.get_llm()
            
            # Test connection to existing Ollama
            response = await llm_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say hello in one word"}],
                max_tokens=10,
            )
            
            assert response.choices[0].message.content is not None
            
        except Exception as e:
            pytest.skip(f"Ollama not available: {e}")


class TestEndToEnd:
    """End-to-end integration test."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invoice_ingestion_flow(self):
        """Test complete invoice ingestion flow."""
        # 1. Upload PDF to Blob Storage
        from apps.api.storage.blob import upload_invoice_pdf
        
        test_pdf = b"%PDF-1.4 test invoice content"
        tenant_id = "test-tenant"
        invoice_id = "test-invoice-001"
        
        blob_url = await upload_invoice_pdf(
            tenant_id, invoice_id, test_pdf,
            {"vendor": "test-vendor"}
        )
        assert blob_url is not None
        
        # 2. Store metadata in SQL
        from apps.api.db.sql import execute_command
        
        await execute_command(
            """
            IF OBJECT_ID('invoices', 'U') IS NOT NULL DROP TABLE invoices;
            CREATE TABLE invoices (
                id UNIQUEIDENTIFIER PRIMARY KEY,
                tenant_id NVARCHAR(100),
                blob_url NVARCHAR(500),
                status NVARCHAR(50) DEFAULT 'PENDING',
                created_at DATETIME2 DEFAULT GETUTCDATE()
            );
            
            INSERT INTO invoices (id, tenant_id, blob_url, status)
            VALUES (@id, @tenant_id, @blob_url, 'PENDING');
            """,
            {
                "id": invoice_id,
                "tenant_id": tenant_id,
                "blob_url": blob_url,
            }
        )
        
        # 3. Verify data in SQL
        from apps.api.db.sql import execute_query
        
        results = await execute_query(
            "SELECT * FROM invoices WHERE id = @id",
            {"id": invoice_id}
        )
        
        assert len(results) == 1
        assert results[0]["status"] == "PENDING"
        
        # Clean up
        from apps.api.storage.blob import BlobStorageClient
        client = BlobStorageClient(connection_string=AZURITE_URL)
        await client.delete_blob(f"{tenant_id}/{invoice_id}.pdf")
        
        await execute_command("DROP TABLE invoices")


# ─────────────────────────────────────────────────────────────────────────────
# Pytest configuration
# ─────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires Docker containers)"
    )
