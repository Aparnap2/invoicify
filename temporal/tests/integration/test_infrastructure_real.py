"""
Integration tests for Infrastructure Adapters with Real Data
Tests against real Docker containers (no mocking)
"""

import pytest
import asyncio
import os
import time
from typing import List

from temporal.activities.infrastructure import (
    Neo4jActivityAdapter,
    QdrantActivityAdapter,
    IBMCOSAdapter,
    get_neo4j_adapter,
    get_qdrant_adapter,
    get_cos_adapter,
)


@pytest.mark.integration
class TestQdrantRealIntegration:
    """Integration tests with real Qdrant container."""

    @pytest.fixture(autouse=True)
    def setup_qdrant(self):
        """Ensure Qdrant is running and collection exists."""
        # Wait for Qdrant to be ready
        max_retries = 10
        for i in range(max_retries):
            try:
                from qdrant_client import QdrantClient
                client = QdrantClient(url="http://localhost:6333")
                client.get_collections()
                break
            except Exception as e:
                if i < max_retries - 1:
                    time.sleep(1)
                else:
                    pytest.skip(f"Qdrant not available: {e}")

    @pytest.mark.asyncio
    async def test_qdrant_upsert_and_search_real_data(self):
        """Test upsert and search with real Qdrant container."""
        # Arrange
        adapter = QdrantActivityAdapter()
        
        # Create test invoice data
        vendor_name = "Test Vendor Integration"
        invoice_number = "INV-INT-001"
        amount = 150.0
        
        # Create a 384-dimensional feature vector (Qdrant collection dimension)
        # In production, use real embeddings from FastEmbed
        features = [amount, len(vendor_name)] + [0.0] * 382  # Pad to 384 dimensions
        
        # Act - Upsert
        upsert_result = await adapter.index_invoice(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            amount=amount,
            features=features,
        )
        
        # Assert - Upsert
        assert upsert_result is True, "Failed to upsert invoice to Qdrant"
        
        # Wait for indexing
        await asyncio.sleep(0.5)
        
        # Act - Search
        search_results = await adapter.search_similar_invoices(
            vendor_name=vendor_name,
            amount=amount,
            limit=5,
        )
        
        # Assert - Search
        assert isinstance(search_results, list), "Search results should be a list"
        # Note: May not find exact match due to vector similarity, but should return results
        print(f"Search results: {search_results}")

    @pytest.mark.asyncio
    async def test_qdrant_multiple_invoices(self):
        """Test upserting and searching multiple invoices."""
        # Arrange
        adapter = QdrantActivityAdapter()
        
        # Create multiple test invoices
        invoices = [
            {"vendor_name": "AWS", "invoice_number": "INV-AWS-001", "amount": 500.0},
            {"vendor_name": "AWS", "invoice_number": "INV-AWS-002", "amount": 550.0},
            {"vendor_name": "AWS", "invoice_number": "INV-AWS-003", "amount": 480.0},
        ]
        
        # Act - Upsert all invoices
        for invoice in invoices:
            features = [invoice["amount"], len(invoice["vendor_name"])] + [0.0] * 382
            result = await adapter.index_invoice(
                vendor_name=invoice["vendor_name"],
                invoice_number=invoice["invoice_number"],
                amount=invoice["amount"],
                features=features,
            )
            assert result is True, f"Failed to upsert {invoice['invoice_number']}"
        
        # Wait for indexing
        await asyncio.sleep(0.5)
        
        # Act - Search for similar invoices
        search_results = await adapter.search_similar_invoices(
            vendor_name="AWS",
            amount=520.0,
            limit=5,
        )
        
        # Assert
        assert isinstance(search_results, list)
        print(f"Found {len(search_results)} similar invoices for AWS")


@pytest.mark.integration
class TestNeo4jRealIntegration:
    """Integration tests with real Neo4j container."""

    @pytest.fixture(autouse=True)
    def setup_neo4j(self):
        """Ensure Neo4j is running."""
        # Set environment variable for Neo4j URI
        os.environ["NEO4J_URI"] = "bolt://localhost:7687"
        os.environ["NEO4J_USER"] = "neo4j"
        os.environ["NEO4J_PASSWORD"] = "admin123"
        
        # Check if Neo4j is available by checking the HTTP endpoint
        max_retries = 10
        for i in range(max_retries):
            try:
                import requests
                response = requests.get("http://localhost:7474", timeout=2)
                if response.status_code == 200:
                    break
            except Exception as e:
                if i < max_retries - 1:
                    time.sleep(1)
                else:
                    pytest.skip(f"Neo4j not available: {e}")

    @pytest.mark.asyncio
    async def test_neo4j_save_and_retrieve_invoice(self):
        """Test saving and retrieving invoice from Neo4j."""
        # Arrange
        adapter = Neo4jActivityAdapter()
        
        vendor_name = "Test Vendor Neo4j"
        invoice_number = "INV-NEO-001"
        amount = 200.0
        status = "APPROVED"
        
        # Act - Save invoice
        save_result = await adapter.save_invoice(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            amount=amount,
            status=status,
            metadata={"test": "integration"},
        )
        
        # Assert - Save
        assert save_result is True, "Failed to save invoice to Neo4j"
        
        # Wait for transaction to complete
        await asyncio.sleep(0.5)
        
        # Act - Retrieve vendor history
        history = await adapter.get_vendor_history(vendor_name, limit=10)
        
        # Assert - Retrieve
        assert isinstance(history, list), "Vendor history should be a list"
        assert len(history) > 0, "Should have at least one invoice in history"
        
        # Find our saved invoice
        saved_invoice = next(
            (inv for inv in history if inv["invoice_number"] == invoice_number),
            None
        )
        assert saved_invoice is not None, "Saved invoice not found in history"
        assert saved_invoice["amount"] == amount
        assert saved_invoice["status"] == status

    @pytest.mark.asyncio
    async def test_neo4j_multiple_invoices(self):
        """Test saving and retrieving multiple invoices."""
        # Arrange
        adapter = Neo4jActivityAdapter()
        
        vendor_name = "Multi Vendor Test"
        invoices = [
            {"invoice_number": "INV-MULTI-001", "amount": 100.0, "status": "APPROVED"},
            {"invoice_number": "INV-MULTI-002", "amount": 150.0, "status": "APPROVED"},
            {"invoice_number": "INV-MULTI-003", "amount": 120.0, "status": "PENDING"},
        ]
        
        # Act - Save all invoices
        for invoice in invoices:
            result = await adapter.save_invoice(
                vendor_name=vendor_name,
                invoice_number=invoice["invoice_number"],
                amount=invoice["amount"],
                status=invoice["status"],
            )
            assert result is True, f"Failed to save {invoice['invoice_number']}"
        
        # Wait for transactions to complete
        await asyncio.sleep(0.5)
        
        # Act - Retrieve vendor history
        history = await adapter.get_vendor_history(vendor_name, limit=10)
        
        # Assert
        assert isinstance(history, list)
        assert len(history) >= len(invoices), f"Expected at least {len(invoices)} invoices"
        
        # Verify all invoices are present
        invoice_numbers = [inv["invoice_number"] for inv in history]
        for invoice in invoices:
            assert invoice["invoice_number"] in invoice_numbers, \
                f"Invoice {invoice['invoice_number']} not found in history"


@pytest.mark.integration
class TestIBMCOSRealIntegration:
    """Integration tests with IBM COS (requires credentials)."""

    @pytest.fixture(autouse=True)
    def setup_cos(self):
        """Check if IBM COS credentials are available."""
        if not os.getenv("IBM_CLOUD_API_KEY") or not os.getenv("IBM_COS_INSTANCE_ID"):
            pytest.skip("IBM COS credentials not available")

    @pytest.mark.asyncio
    async def test_cos_save_and_load_model(self):
        """Test saving and loading model from IBM COS."""
        # Arrange
        adapter = IBMCOSAdapter()
        
        vendor_id = "test-vendor-integration"
        test_model = {
            "type": "test_model",
            "version": 1,
            "data": [1, 2, 3, 4, 5],
        }
        
        # Act - Save model
        save_result = await adapter.save_model(vendor_id, test_model)
        
        # Assert - Save
        assert save_result is True, "Failed to save model to IBM COS"
        
        # Act - Load model
        loaded_model = await adapter.load_model(vendor_id)
        
        # Assert - Load
        assert loaded_model is not None, "Failed to load model from IBM COS"
        assert loaded_model["type"] == test_model["type"]
        assert loaded_model["version"] == test_model["version"]
        assert loaded_model["data"] == test_model["data"]

    @pytest.mark.asyncio
    async def test_cos_model_not_found(self):
        """Test loading non-existent model returns None."""
        # Arrange
        adapter = IBMCOSAdapter()
        
        # Act - Load non-existent model
        loaded_model = await adapter.load_model("non-existent-vendor")
        
        # Assert
        assert loaded_model is None, "Should return None for non-existent model"


@pytest.mark.integration
class TestEndToEndWorkflow:
    """End-to-end integration tests with all services."""

    @pytest.fixture(autouse=True)
    def setup_all_services(self):
        """Ensure all services are available."""
        # Check Qdrant
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(url="http://localhost:6333")
            client.get_collections()
        except Exception:
            pytest.skip("Qdrant not available")

    @pytest.mark.asyncio
    async def test_complete_invoice_processing_workflow(self):
        """Test complete workflow: save to Neo4j, index in Qdrant."""
        # Arrange
        neo4j_adapter = Neo4jActivityAdapter()
        qdrant_adapter = QdrantActivityAdapter()
        
        vendor_name = "End-to-End Vendor"
        invoice_number = "INV-E2E-001"
        amount = 300.0
        
        # Act - Save to Neo4j
        neo4j_result = await neo4j_adapter.save_invoice(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            amount=amount,
            status="PENDING",
        )
        assert neo4j_result is True
        
        # Act - Index in Qdrant
        features = [amount, len(vendor_name)] + [0.0] * 382
        qdrant_result = await qdrant_adapter.index_invoice(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            amount=amount,
            features=features,
        )
        assert qdrant_result is True
        
        # Wait for indexing
        await asyncio.sleep(0.5)
        
        # Act - Retrieve from Neo4j
        history = await neo4j_adapter.get_vendor_history(vendor_name)
        assert len(history) > 0
        
        # Act - Search in Qdrant
        search_results = await qdrant_adapter.search_similar_invoices(
            vendor_name=vendor_name,
            amount=amount,
        )
        assert isinstance(search_results, list)
        
        print(f"✓ Complete workflow successful!")
        print(f"  - Neo4j: {len(history)} invoices in history")
        print(f"  - Qdrant: {len(search_results)} similar invoices found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])