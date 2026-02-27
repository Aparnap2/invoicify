"""
TDD Integration Tests - Real Docker + Real Azure AI

Run with:
    uv run pytest tests/tdd/test_azure_integration.py -v -s

Requirements:
- Docker containers running (azurite, azure-sql, cosmos, ollama)
- Azure AI credentials in .env
"""

import pytest
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent-core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "api"))

# Test configuration - loaded from environment variables
# Set these in .env.local or export before running tests:
#   export AZURITE_CONNECTION_STRING="..."
#   export SQL_CONNECTION_STRING="..."

AZURITE_CONN = os.getenv(
    "AZURITE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OugDPfYIDSZRfj63d3==;BlobEndpoint=http://localhost:10000/devstoreaccount1"
)

SQL_CONN = os.getenv(
    "SQL_CONNECTION_STRING",
    "Server=localhost,1433;Database=invoicify;User Id=sa;Password=Invoicify@Local123;TrustServerCertificate=True"
)


class TestAzureBlobStorageTDD:
    """TDD for Azure Blob Storage with real Azurite container."""
    
    @pytest.mark.asyncio
    async def test_red_green_refactor_blob_upload(self):
        """
        TDD Cycle:
        1. RED: Write test that fails (no implementation)
        2. GREEN: Make it pass (implement)
        3. REFACTOR: Clean up
        """
        # RED - This should fail initially
        from azure.storage.blob.aio import BlobServiceClient
        
        # Create client
        client = BlobServiceClient.from_connection_string(AZURITE_CONN)
        
        # GREEN - Implementation
        container_client = client.get_container_client("test-invoices")
        
        # Create container if not exists
        try:
            await container_client.create_container()
        except Exception:
            pass  # Already exists
        
        # Upload test blob
        test_data = b"test invoice pdf content"
        blob_name = f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(test_data, overwrite=True)
        
        # Verify upload
        download_stream = await blob_client.download_blob()
        downloaded = await download_stream.readall()
        
        assert downloaded == test_data
        assert len(downloaded) == len(test_data)
        
        # REFACTOR - Clean up
        await blob_client.delete_blob()
        print(f"✅ Blob upload/download test passed: {blob_name}")
    
    @pytest.mark.asyncio
    async def test_blob_metadata(self):
        """Test blob metadata storage and retrieval."""
        from azure.storage.blob.aio import BlobServiceClient
        
        client = BlobServiceClient.from_connection_string(AZURITE_CONN)
        container_client = client.get_container_client("test-invoices")
        
        # Upload with metadata
        blob_name = f"metadata-test-{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        metadata = {
            "tenant_id": "test-tenant-001",
            "invoice_id": "inv-123",
            "vendor": "Acme Supplies"
        }
        
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(
            b"test content",
            metadata=metadata,
            overwrite=True
        )
        
        # Retrieve metadata
        props = await blob_client.get_blob_properties()
        
        # Verify
        assert props.metadata["tenant_id"] == "test-tenant-001"
        assert props.metadata["invoice_id"] == "inv-123"
        assert props.metadata["vendor"] == "acme supplies"  # Azure lowercases
        
        # Cleanup
        await blob_client.delete_blob()
        print(f"✅ Blob metadata test passed: {blob_name}")


class TestAzureSQLTDD:
    """TDD for Azure SQL with real SQL Server container."""
    
    @pytest.mark.asyncio
    async def test_red_green_refactor_sql_connection(self):
        """
        TDD Cycle for SQL connection:
        1. RED: Test fails (no connection)
        2. GREEN: Connect successfully
        3. REFACTOR: Add proper error handling
        """
        import asyncpg
        
        # GREEN - Connect to SQL Server
        # Note: asyncpg is for PostgreSQL, for SQL Server we use pyodbc
        # But let's test with simple TCP connection first
        
        import socket
        
        # Test connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 1433))
        sock.close()
        
        assert result == 0, "SQL Server port 1433 not accessible"
        print("✅ SQL Server connectivity test passed")
    
    @pytest.mark.asyncio
    async def test_sql_crud_operations(self):
        """Test CREATE, READ, UPDATE, DELETE with real SQL Server."""
        try:
            import pyodbc
        except ImportError:
            pytest.skip("pyodbc not available (requires libodbc.so.2)")
        
        # Connect
        conn = pyodbc.connect(SQL_CONN, autocommit=True)
        cursor = conn.cursor()
        
        # CREATE table
        table_name = f"test_invoices_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cursor.execute(f"""
            IF OBJECT_ID('{table_name}', 'U') IS NOT NULL DROP TABLE {table_name};
            CREATE TABLE {table_name} (
                id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                tenant_id NVARCHAR(100) NOT NULL,
                amount DECIMAL(18,2) NOT NULL,
                status NVARCHAR(50) DEFAULT 'PENDING',
                created_at DATETIME2 DEFAULT GETUTCDATE()
            );
        """)
        
        # INSERT
        cursor.execute(
            f"INSERT INTO {table_name} (tenant_id, amount, status) VALUES (?, ?, ?)",
            ("test-tenant", 1500.50, "PROCESSING")
        )
        
        # SELECT
        cursor.execute(f"SELECT * FROM {table_name} WHERE tenant_id = ?", ("test-tenant",))
        rows = cursor.fetchall()
        
        assert len(rows) == 1
        assert float(rows[0].amount) == 1500.50
        assert rows[0].status == "PROCESSING"
        
        # UPDATE
        cursor.execute(
            f"UPDATE {table_name} SET status = ? WHERE tenant_id = ?",
            ("APPROVED", "test-tenant")
        )
        
        # Verify UPDATE
        cursor.execute(f"SELECT status FROM {table_name} WHERE tenant_id = ?", ("test-tenant",))
        updated_status = cursor.fetchone()[0]
        assert updated_status == "APPROVED"
        
        # DELETE
        cursor.execute(f"DELETE FROM {table_name} WHERE tenant_id = ?", ("test-tenant",))
        
        # Verify DELETE
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id = ?", ("test-tenant",))
        count = cursor.fetchone()[0]
        assert count == 0
        
        # Cleanup table
        cursor.execute(f"DROP TABLE {table_name}")
        
        conn.close()
        print("✅ SQL CRUD operations test passed")


class TestAzureAITDD:
    """TDD for Azure AI LLM with real Azure OpenAI."""
    
    @pytest.fixture
    def azure_llm_client(self):
        """Create Azure AI client from environment variables."""
        from openai import AsyncAzureOpenAI
        
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        
        if not api_key or not endpoint:
            pytest.skip("Azure AI credentials not set (AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT)")
        
        return AsyncAzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint,
        ), deployment
    
    @pytest.mark.asyncio
    async def test_red_green_refactor_azure_llm_connection(self, azure_llm_client):
        """
        TDD Cycle for Azure AI:
        1. RED: Test fails (no connection)
        2. GREEN: Connect and get response
        3. REFACTOR: Add proper error handling
        """
        client, deployment = azure_llm_client
        
        # Test connection with simple completion
        response = await client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in one word"}
            ],
            max_tokens=10,
        )
        
        # Verify response
        assert response.choices[0].message.content is not None
        assert len(response.choices[0].message.content.strip()) > 0
        
        print(f"✅ Azure AI connection test passed: {response.choices[0].message.content}")
    
    @pytest.mark.asyncio
    async def test_azure_llm_invoice_extraction(self, azure_llm_client):
        """Test Azure AI for invoice data extraction."""
        import json
        
        client, deployment = azure_llm_client
        
        # Sample invoice text (from Docling extraction)
        invoice_text = """
        ACME SUPPLIES PVT LTD
        123 Business Park, Mumbai 400001
        GST: 27AABCU9603R1ZM
        
        Invoice #: INV-2024-001
        Date: 2024-01-15
        Due Date: 2024-02-15
        
        Bill To: TechCorp Solutions
        
        Line Items:
        - Office Chairs x 10 @ $150.00 = $1,500.00
        - Desks x 5 @ $300.00 = $1,500.00
        
        Subtotal: $3,000.00
        Tax (18%): $540.00
        Total: $3,540.00
        """
        
        # Extraction prompt
        system_prompt = """You are an invoice extraction expert. Extract data as JSON only.
        
        Required fields:
        - invoice_number: string
        - vendor_name: string
        - total_amount: number
        - invoice_date: string (YYYY-MM-DD)
        - line_items: array of {description, quantity, unit_price, total}
        
        Return ONLY valid JSON."""
        
        response = await client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract from this invoice:\n{invoice_text}"}
            ],
            temperature=0,
        )
        
        # Parse response
        extracted = json.loads(response.choices[0].message.content)
        
        # Verify extraction
        assert "invoice_number" in extracted
        assert "vendor_name" in extracted
        assert "total_amount" in extracted
        assert "line_items" in extracted
        
        # Verify values
        assert extracted["invoice_number"] == "INV-2024-001"
        assert "ACME" in extracted["vendor_name"].upper()
        assert abs(float(extracted["total_amount"]) - 3540.0) < 1.0
        assert len(extracted["line_items"]) >= 2
        
        print(f"✅ Azure AI invoice extraction test passed")
        print(f"   Extracted: {json.dumps(extracted, indent=2)[:200]}...")


class TestEndToEndTDD:
    """End-to-End TDD with all components."""
    
    @pytest.fixture
    def azure_llm_client(self):
        """Create Azure AI client from environment variables."""
        from openai import AsyncAzureOpenAI
        
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        
        if not api_key or not endpoint:
            return None
        
        return AsyncAzureOpenAI(
            api_key=api_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
            azure_endpoint=endpoint,
        )
    
    @pytest.mark.asyncio
    async def test_complete_invoice_processing_flow(self, azure_llm_client):
        """
        Complete TDD flow:
        1. Upload PDF to Azure Blob
        2. Store metadata in Azure SQL
        3. Extract data with Azure AI (optional)
        4. Verify end-to-end
        """
        from azure.storage.blob.aio import BlobServiceClient
        import pyodbc
        import json
        
        # Skip if pyodbc not available
        try:
            import pyodbc
        except ImportError:
            pytest.skip("pyodbc not available (requires libodbc.so.2)")
        
        # === Step 1: Upload to Blob Storage ===
        blob_client = BlobServiceClient.from_connection_string(AZURITE_CONN)
        container_client = blob_client.get_container_client("test-invoices")
        
        try:
            await container_client.create_container()
        except:
            pass
        
        invoice_id = f"inv-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        blob_name = f"test/{invoice_id}.pdf"
        pdf_content = b"%PDF-1.4 test invoice content"
        
        await container_client.upload_blob(blob_name, pdf_content, overwrite=True)
        blob_url = f"{AZURITE_CONN.split(';BlobEndpoint=')[1]}/{blob_name}"
        
        print(f"✅ Step 1: PDF uploaded to blob: {blob_name}")
        
        # === Step 2: Store metadata in SQL ===
        conn = pyodbc.connect(SQL_CONN, autocommit=True)
        cursor = conn.cursor()
        
        table_name = "invoices"
        cursor.execute(f"""
            IF OBJECT_ID('{table_name}', 'U') IS NOT NULL DROP TABLE {table_name};
            CREATE TABLE {table_name} (
                id NVARCHAR(100) PRIMARY KEY,
                tenant_id NVARCHAR(100),
                blob_url NVARCHAR(500),
                status NVARCHAR(50) DEFAULT 'PENDING',
                created_at DATETIME2 DEFAULT GETUTCDATE()
            );
        """)
        
        cursor.execute(
            f"INSERT INTO {table_name} (id, tenant_id, blob_url, status) VALUES (?, ?, ?, ?)",
            (invoice_id, "test-tenant", blob_url, "UPLOADED")
        )
        
        print(f"✅ Step 2: Metadata stored in SQL: {invoice_id}")
        
        # === Step 3: Extract with Azure AI (optional) ===
        if azure_llm_client:
            response = await azure_llm_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "Extract invoice data as JSON."},
                    {"role": "user", "content": f"Extract from: Test invoice for {invoice_id}"}
                ],
                max_tokens=100,
            )
            
            print(f"✅ Step 3: Azure AI extraction completed")
        else:
            print(f"⚠️  Step 3: Skipped Azure AI (no credentials)")
        
        # === Step 4: Verify end-to-end ===
        cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (invoice_id,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row.blob_url == blob_url
        assert row.status == "UPLOADED"
        
        # Cleanup
        cursor.execute(f"DROP TABLE {table_name}")
        conn.close()
        await container_client.delete_blob(blob_name)
        
        print(f"✅ Step 4: End-to-end verification passed")
        print(f"   Invoice ID: {invoice_id}")
        print(f"   Blob URL: {blob_url}")
        print(f"   Status: {row.status}")


# ─────────────────────────────────────────────────────────────────────────────
# Pytest configuration
# ─────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "tdd: mark test as TDD test (real Docker + real Azure AI)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
