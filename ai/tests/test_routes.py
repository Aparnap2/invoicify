"""Tests for API routes."""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient

from app.main import app


@pytest.fixture
def async_client() -> AsyncClient:
    """Create async test client."""
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestHealthEndpoint:
    """Tests for health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, async_client: AsyncClient):
        """Test health check returns healthy status."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "model" in data


class TestRootEndpoint:
    """Tests for root endpoint."""

    @pytest.mark.asyncio
    async def test_root(self, async_client: AsyncClient):
        """Test root endpoint."""
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "invoicify-ai"
        assert data["status"] == "running"


class TestExtractionEndpoint:
    """Tests for extraction endpoint."""

    @pytest.mark.asyncio
    async def test_extract_endpoint_structure(self, async_client: AsyncClient):
        """Test extraction endpoint accepts valid request."""
        response = await async_client.post(
            "/api/v1/extract",
            json={
                "raw_content": "Invoice from Test Vendor\nTotal: $100.00",
                "source_file_name": "test.txt",
                "source_file_type": "txt",
            },
        )
        # Should not return 422 (validation error)
        assert response.status_code != 422

    @pytest.mark.asyncio
    async def test_extract_missing_content(self, async_client: AsyncClient):
        """Test extraction with missing content returns error."""
        response = await async_client.post(
            "/api/v1/extract",
            json={},
        )
        assert response.status_code == 422


class TestProcessingEndpoint:
    """Tests for processing endpoint."""

    @pytest.mark.asyncio
    async def test_process_endpoint_structure(self, async_client: AsyncClient):
        """Test processing endpoint accepts valid request."""
        response = await async_client.post(
            "/api/v1/process",
            json={
                "raw_content": "Invoice from Test Vendor\nTotal: $100.00",
                "source_file_name": "test.txt",
                "source_file_type": "txt",
            },
        )
        assert response.status_code != 422
        data = response.json()
        assert "thread_id" in data

    @pytest.mark.asyncio
    async def test_process_returns_result(self, async_client: AsyncClient):
        """Test processing returns result structure."""
        response = await async_client.post(
            "/api/v1/process",
            json={
                "raw_content": "Invoice from Test Vendor\nTotal: $100.00",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "thread_id" in data


class TestStatusEndpoint:
    """Tests for status endpoint."""

    @pytest.mark.asyncio
    async def test_status_returns_valid_response(self, async_client: AsyncClient):
        """Test status endpoint returns valid response structure."""
        response = await async_client.get("/api/v1/status/test-thread-id")
        assert response.status_code == 200
        data = response.json()
        # Status can be either not_found or running depending on state
        assert "status" in data
        assert data["thread_id"] == "test-thread-id"
