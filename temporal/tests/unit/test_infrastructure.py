"""
Unit tests for Infrastructure Adapters
Following TDD: Write tests first, then implementation
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from io import BytesIO

from temporal.activities.infrastructure import (
    Neo4jActivityAdapter,
    QdrantActivityAdapter,
    IBMCOSAdapter,
    get_neo4j_adapter,
    get_qdrant_adapter,
    get_cos_adapter,
)


class TestNeo4jActivityAdapter:
    """Test suite for Neo4j adapter."""

    @pytest.mark.asyncio
    async def test_get_vendor_history_returns_list(self):
        """Test that get_vendor_history returns a list of invoices."""
        # Arrange
        adapter = Neo4jActivityAdapter()
        mock_client = AsyncMock()
        mock_invoice = {
            "amount": 100.0,
            "status": "APPROVED",
            "invoice_number": "INV-001",
            "created_at": "2025-01-01",
        }
        mock_client.get_invoices_by_vendor.return_value = [mock_invoice]

        with patch("temporal.activities.infrastructure.get_neo4j_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.get_vendor_history("Test Vendor")

        # Assert
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["amount"] == 100.0
        assert result[0]["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_get_vendor_history_handles_error(self):
        """Test that get_vendor_history handles errors gracefully."""
        # Arrange
        adapter = Neo4jActivityAdapter()
        mock_client = AsyncMock()
        mock_client.get_invoices_by_vendor.side_effect = Exception("Connection failed")

        with patch("temporal.activities.infrastructure.get_neo4j_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.get_vendor_history("Test Vendor")

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_save_invoice_returns_true_on_success(self):
        """Test that save_invoice returns True on success."""
        # Arrange
        adapter = Neo4jActivityAdapter()
        mock_client = AsyncMock()
        mock_client.create_invoice.return_value = None

        with patch("temporal.activities.infrastructure.get_neo4j_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.save_invoice(
                vendor_name="Test Vendor",
                invoice_number="INV-001",
                amount=100.0,
                status="APPROVED",
            )

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_save_invoice_returns_false_on_error(self):
        """Test that save_invoice returns False on error."""
        # Arrange
        adapter = Neo4jActivityAdapter()
        mock_client = AsyncMock()
        mock_client.create_invoice.side_effect = Exception("Save failed")

        with patch("temporal.activities.infrastructure.get_neo4j_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.save_invoice(
                vendor_name="Test Vendor",
                invoice_number="INV-001",
                amount=100.0,
                status="APPROVED",
            )

        # Assert
        assert result is False


class TestQdrantActivityAdapter:
    """Test suite for Qdrant adapter."""

    @pytest.mark.asyncio
    async def test_search_similar_invoices_returns_list(self):
        """Test that search_similar_invoices returns a list of invoices."""
        # Arrange
        adapter = QdrantActivityAdapter()
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.payload = {
            "invoice_number": "INV-001",
            "amount": 100.0,
        }
        mock_result.score = 0.95
        mock_client.search.return_value = [mock_result]

        with patch("temporal.activities.infrastructure.get_qdrant_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.search_similar_invoices(
                vendor_name="Test Vendor",
                amount=100.0,
            )

        # Assert
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["invoice_number"] == "INV-001"
        assert result[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_similar_invoices_handles_error(self):
        """Test that search_similar_invoices handles errors gracefully."""
        # Arrange
        adapter = QdrantActivityAdapter()
        mock_client = AsyncMock()
        mock_client.search.side_effect = Exception("Search failed")

        with patch("temporal.activities.infrastructure.get_qdrant_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.search_similar_invoices(
                vendor_name="Test Vendor",
                amount=100.0,
            )

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_index_invoice_returns_true_on_success(self):
        """Test that index_invoice returns True on success."""
        # Arrange
        adapter = QdrantActivityAdapter()
        mock_client = AsyncMock()
        mock_client.upsert.return_value = None

        with patch("temporal.activities.infrastructure.get_qdrant_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            # Act
            result = await adapter.index_invoice(
                vendor_name="Test Vendor",
                invoice_number="INV-001",
                amount=100.0,
            )

        # Assert
        assert result is True


class TestIBMCOSAdapter:
    """Test suite for IBM COS adapter."""

    @pytest.mark.asyncio
    async def test_load_model_returns_model(self):
        """Test that load_model returns a model when it exists."""
        # Arrange
        adapter = IBMCOSAdapter()
        mock_client = MagicMock()
        mock_model = {"type": "test_model", "version": 1}
        mock_response = {"Body": BytesIO(b"test_data")}
        mock_client.get_object.return_value = mock_response

        with patch("ibm_boto3.client") as mock_boto:
            mock_boto.return_value = mock_client

            with patch("pickle.loads") as mock_loads:
                mock_loads.return_value = mock_model

                # Act
                result = await adapter.load_model("test-vendor")

        # Assert
        assert result is not None
        assert result["type"] == "test_model"

    @pytest.mark.asyncio
    async def test_load_model_returns_none_when_not_found(self):
        """Test that load_model returns None when model doesn't exist."""
        # Arrange
        adapter = IBMCOSAdapter()
        mock_client = MagicMock()
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception("Not found")

        with patch("ibm_boto3.client") as mock_boto:
            mock_boto.return_value = mock_client

            # Act
            result = await adapter.load_model("test-vendor")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_save_model_returns_true_on_success(self):
        """Test that save_model returns True on success."""
        # Arrange
        adapter = IBMCOSAdapter()
        mock_client = MagicMock()
        mock_client.put_object.return_value = None

        with patch("ibm_boto3.client") as mock_boto:
            mock_boto.return_value = mock_client

            with patch("pickle.dumps") as mock_dumps:
                mock_dumps.return_value = b"test_data"

                # Act
                result = await adapter.save_model("test-vendor", {"test": "model"})

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_save_model_returns_false_on_error(self):
        """Test that save_model returns False on error."""
        # Arrange
        adapter = IBMCOSAdapter()
        mock_client = MagicMock()
        mock_client.put_object.side_effect = Exception("Save failed")

        with patch("ibm_boto3.client") as mock_boto:
            mock_boto.return_value = mock_client

            # Act
            result = await adapter.save_model("test-vendor", {"test": "model"})

        # Assert
        assert result is False


class TestSingletonGetters:
    """Test singleton getter functions."""

    def test_get_neo4j_adapter_returns_singleton(self):
        """Test that get_neo4j_adapter returns the same instance."""
        # Act
        adapter1 = get_neo4j_adapter()
        adapter2 = get_neo4j_adapter()

        # Assert
        assert adapter1 is adapter2

    def test_get_qdrant_adapter_returns_singleton(self):
        """Test that get_qdrant_adapter returns the same instance."""
        # Act
        adapter1 = get_qdrant_adapter()
        adapter2 = get_qdrant_adapter()

        # Assert
        assert adapter1 is adapter2

    def test_get_cos_adapter_returns_singleton(self):
        """Test that get_cos_adapter returns the same instance."""
        # Act
        adapter1 = get_cos_adapter()
        adapter2 = get_cos_adapter()

        # Assert
        assert adapter1 is adapter2