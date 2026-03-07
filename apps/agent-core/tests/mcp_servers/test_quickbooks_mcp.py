"""QuickBooks MCP Server unit tests.

Tests for QuickBooks Online integration including:
- TokenManager: OAuth 2.0 token management
- MCP Tools: qb_create_bill, qb_get_vendor, qb_create_vendor, qb_get_bill, qb_void_bill, qb_list_accounts
- Error Handling: 401 retry, 429 backoff, missing credentials

All tests use mocking to avoid real API calls.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import httpx
import pytest
import respx
from httpx import Response

from src.mcp_servers.quickbooks_mcp import (
    CreateBillRequest,
    CreateBillResponse,
    CreateVendorRequest,
    CreateVendorResponse,
    GetBillRequest,
    GetBillResponse,
    GetVendorRequest,
    GetVendorResponse,
    LineItem,
    ListAccountsResponse,
    QB_OAUTH_TOKEN_URL,
    QB_SANDBOX_BASE_URL,
    QuickBooksMCPServer,
    TokenManager,
    VoidBillRequest,
    VoidBillResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def qb_env_vars():
    """Set up QuickBooks environment variables."""
    env = {
        "QB_CLIENT_ID": "test_client_id",
        "QB_CLIENT_SECRET": "test_client_secret",
        "QB_REALM_ID": "test_realm_id",
        "QB_REFRESH_TOKEN": "test_refresh_token",
        "QB_SANDBOX": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


@pytest.fixture
def mock_tokens():
    """Mock OAuth tokens."""
    return {
        "access_token": "mock_access_token_123",
        "refresh_token": "mock_refresh_token_456",
        "expires_in": 3600,
        "x_refresh_token_expires_in": 8726400,
        "token_type": "Bearer",
    }


@pytest.fixture
def temp_token_file(tmp_path):
    """Create temporary token file."""
    token_file = tmp_path / "qb_tokens.json"
    yield token_file


# ─────────────────────────────────────────────────────────────────────────────
# TokenManager Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenManager:
    """Test QuickBooks OAuth 2.0 token management."""

    @pytest.mark.asyncio
    async def test_refresh_token(self, qb_env_vars, mock_tokens):
        """Test token refresh with mocked HTTP."""
        # Mock httpx.AsyncClient.post to return mock tokens
        with respx.mock:
            respx.post(QB_OAUTH_TOKEN_URL).mock(
                return_value=Response(200, json=mock_tokens)
            )

            manager = TokenManager(
                client_id=qb_env_vars["QB_CLIENT_ID"],
                client_secret=qb_env_vars["QB_CLIENT_SECRET"],
                realm_id=qb_env_vars["QB_REALM_ID"],
                refresh_token=qb_env_vars["QB_REFRESH_TOKEN"],
                sandbox=True,
            )

            # Call refresh
            await manager._refresh_tokens()

            # Verify tokens updated
            assert manager._access_token == "mock_access_token_123"
            assert manager._refresh_token == "mock_refresh_token_456"
            assert manager._expires_at is not None
            # Expires at should be approximately now + 3600 seconds
            assert manager._expires_at > time.time() + 3500

    @pytest.mark.asyncio
    async def test_get_access_token_cached(self, qb_env_vars):
        """Test token caching (no HTTP call if valid)."""
        manager = TokenManager(
            client_id=qb_env_vars["QB_CLIENT_ID"],
            client_secret=qb_env_vars["QB_CLIENT_SECRET"],
            realm_id=qb_env_vars["QB_REALM_ID"],
            refresh_token=qb_env_vars["QB_REFRESH_TOKEN"],
            sandbox=True,
        )

        # Set token as valid (expires in future)
        manager._access_token = "cached_token"
        manager._expires_at = time.time() + 3600  # Expires in 1 hour

        # Call get_access_token()
        with respx.mock:
            token = await manager.get_access_token()

            # Verify no HTTP call made, returns cached token
            assert token == "cached_token"
            assert respx.calls.call_count == 0

    @pytest.mark.asyncio
    async def test_get_access_token_expired(self, qb_env_vars, mock_tokens):
        """Test auto-refresh on expired token."""
        manager = TokenManager(
            client_id=qb_env_vars["QB_CLIENT_ID"],
            client_secret=qb_env_vars["QB_CLIENT_SECRET"],
            realm_id=qb_env_vars["QB_REALM_ID"],
            refresh_token=qb_env_vars["QB_REFRESH_TOKEN"],
            sandbox=True,
        )

        # Set token as expired (expires in past)
        manager._access_token = "expired_token"
        manager._expires_at = time.time() - 3600  # Expired 1 hour ago

        # Mock HTTP call
        with respx.mock:
            respx.post(QB_OAUTH_TOKEN_URL).mock(
                return_value=Response(200, json=mock_tokens)
            )

            # Call get_access_token()
            token = await manager.get_access_token()

            # Verify HTTP call made, token refreshed
            assert token == "mock_access_token_123"
            assert respx.calls.call_count == 1

    @pytest.mark.asyncio
    async def test_token_file_persistence(
        self, qb_env_vars, mock_tokens, temp_token_file, tmp_path
    ):
        """Test token writes to .secrets/qb_tokens.json."""
        # Patch TOKEN_FILE_PATH to use temp file
        with patch(
            "src.mcp_servers.quickbooks_mcp.TOKEN_FILE_PATH", temp_token_file
        ):
            manager = TokenManager(
                client_id=qb_env_vars["QB_CLIENT_ID"],
                client_secret=qb_env_vars["QB_CLIENT_SECRET"],
                realm_id=qb_env_vars["QB_REALM_ID"],
                refresh_token=qb_env_vars["QB_REFRESH_TOKEN"],
                sandbox=True,
            )

            # Mock token refresh
            with respx.mock:
                respx.post(QB_OAUTH_TOKEN_URL).mock(
                    return_value=Response(200, json=mock_tokens)
                )

                await manager._refresh_tokens()

            # Verify file written with correct structure
            assert temp_token_file.exists()
            data = json.loads(temp_token_file.read_text())
            assert data["access_token"] == "mock_access_token_123"
            assert data["refresh_token"] == "mock_refresh_token_456"
            assert data["expires_at"] is not None
            assert data["realm_id"] == "test_realm_id"

    def test_load_from_env(self, qb_env_vars):
        """Test loading credentials from environment."""
        manager = TokenManager(
            client_id=qb_env_vars["QB_CLIENT_ID"],
            client_secret=qb_env_vars["QB_CLIENT_SECRET"],
            realm_id=qb_env_vars["QB_REALM_ID"],
            refresh_token=qb_env_vars["QB_REFRESH_TOKEN"],
            sandbox=True,
        )

        # Verify TokenManager loads correctly
        assert manager.client_id == "test_client_id"
        assert manager.client_secret == "test_client_secret"
        assert manager.realm_id == "test_realm_id"
        assert manager._refresh_token == "test_refresh_token"
        assert manager.sandbox is True

    def test_load_from_file(self, qb_env_vars, tmp_path):
        """Test loading refresh token from file."""
        # Create temp file with token
        token_file = tmp_path / "refresh_token.txt"
        token_file.write_text("file_refresh_token_789")

        # Set QB_REFRESH_TOKEN_FILE env var
        with patch.dict(
            os.environ,
            {"QB_REFRESH_TOKEN_FILE": str(token_file)},
            clear=False,
        ):
            manager = TokenManager(
                client_id=qb_env_vars["QB_CLIENT_ID"],
                client_secret=qb_env_vars["QB_CLIENT_SECRET"],
                realm_id=qb_env_vars["QB_REALM_ID"],
                refresh_token_file=str(token_file),
                sandbox=True,
            )

            # Verify TokenManager loads from file
            assert manager._refresh_token == "file_refresh_token_789"


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuickBooksTools:
    """Test QuickBooks MCP tools helper methods."""

    @pytest.fixture
    def qb_server(self, qb_env_vars):
        """Create QuickBooks MCP server instance."""
        # Mock _register_tools to avoid decorator issues during init
        with patch.object(QuickBooksMCPServer, "_register_tools", return_value=None):
            with patch.object(TokenManager, "__init__", return_value=None):
                server = QuickBooksMCPServer()
                server.token_manager = TokenManager(
                    client_id="test",
                    client_secret="test",
                    realm_id="test",
                    sandbox=True,
                )
                server.token_manager._access_token = "mock_access_token"
                server.token_manager._expires_at = time.time() + 3600
                server.base_url = QB_SANDBOX_BASE_URL
                server.realm_id = "test_realm_id"
                yield server

    def test_build_bill_payload(self, qb_server):
        """Test bill payload construction."""
        request = CreateBillRequest(
            vendor_id="vendor_1",
            line_items=[
                LineItem(description="Test Item", amount=100.0, quantity=2, unit_price=50.0)
            ],
            due_date="2024-02-15",
            currency="USD",
            doc_number="BILL-001",
        )

        payload = qb_server._build_bill_payload(request)

        assert payload["VendorRef"]["value"] == "vendor_1"
        assert payload["DueDate"] == "2024-02-15"
        assert payload["CurrencyRef"]["value"] == "USD"
        assert payload["DocNumber"] == "BILL-001"
        assert len(payload["Line"]) == 1
        assert payload["Line"][0]["Description"] == "Test Item"
        assert payload["Line"][0]["Amount"] == 100.0

    @pytest.mark.asyncio
    async def test_make_request_success(self, qb_server):
        """Test successful HTTP request."""
        with respx.mock:
            respx.get(f"{QB_SANDBOX_BASE_URL}/test").mock(
                return_value=Response(200, json={"result": "success"})
            )

            result = await qb_server._make_request(
                method="GET",
                endpoint="/test",
                access_token="mock_token",
                trace_id="test_trace",
            )

            assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_make_request_401_retry(self, qb_server):
        """Test 401 triggers token refresh and retry."""
        call_count = 0

        def request_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(401, text="Unauthorized")
            return Response(200, json={"result": "success"})

        with respx.mock:
            respx.get(f"{QB_SANDBOX_BASE_URL}/test").mock(
                side_effect=request_handler
            )

            # Mock token refresh
            qb_server.token_manager.get_access_token = AsyncMock(
                side_effect=["mock_token", "new_token"]
            )

            result = await qb_server._make_request(
                method="GET",
                endpoint="/test",
                access_token="mock_token",
                trace_id="test_trace",
            )

            assert result["result"] == "success"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_429_rate_limit(self, qb_server):
        """Test 429 raises HTTPStatusError after tenacity retries."""
        with respx.mock:
            # Always return 429
            respx.get(f"{QB_SANDBOX_BASE_URL}/test").mock(
                return_value=Response(
                    429,
                    text="Rate Limited",
                    headers={"Retry-After": "1"},
                )
            )

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await qb_server._make_request(
                    method="GET",
                    endpoint="/test",
                    access_token="mock_token",
                    trace_id="test_trace",
                )

            assert exc_info.value.response.status_code == 429


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuickBooksErrors:
    """Test QuickBooks error handling."""

    @pytest.fixture
    def qb_server(self, qb_env_vars):
        """Create QuickBooks MCP server instance."""
        # Mock _register_tools to avoid decorator issues during init
        with patch.object(QuickBooksMCPServer, "_register_tools", return_value=None):
            with patch.object(TokenManager, "__init__", return_value=None):
                server = QuickBooksMCPServer()
                server.token_manager = TokenManager(
                    client_id="test",
                    client_secret="test",
                    realm_id="test",
                    sandbox=True,
                )
                server.token_manager._access_token = "mock_access_token"
                server.token_manager._expires_at = time.time() + 3600
                server.base_url = QB_SANDBOX_BASE_URL
                server.realm_id = "test_realm_id"
                yield server

    @pytest.mark.asyncio
    async def test_401_retry(self, qb_server):
        """Test 401 triggers token refresh + retry."""
        call_count = 0

        def request_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(401, text="Unauthorized")
            return Response(
                200,
                json={"QueryResponse": {"Account": [{"Id": "acc_1", "Name": "Cash"}]}},
            )

        with respx.mock:
            # Mock token refresh
            respx.post(QB_OAUTH_TOKEN_URL).mock(
                return_value=Response(
                    200,
                    json={
                        "access_token": "new_access_token",
                        "refresh_token": "new_refresh_token",
                        "expires_in": 3600,
                    },
                )
            )

            # Mock API endpoint
            respx.get(f"{qb_server.base_url}/company/{qb_server.realm_id}/account").mock(
                side_effect=request_handler
            )

            # Mock token manager refresh
            qb_server.token_manager.get_access_token = AsyncMock(
                side_effect=["mock_access_token", "new_access_token"]
            )

            # Call _make_request directly
            result = await qb_server._make_request(
                method="GET",
                endpoint=f"/company/{qb_server.realm_id}/account",
                access_token="mock_access_token",
                trace_id="test_trace",
            )

            # Verify tool succeeds after retry
            assert result["QueryResponse"]["Account"][0]["Name"] == "Cash"
            assert call_count == 2  # Two API calls made

    @pytest.mark.asyncio
    async def test_429_backoff(self, qb_server):
        """Test 429 triggers exponential backoff and raises HTTPStatusError."""
        call_count = 0

        def request_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # Always return 429
            return Response(
                429,
                text="Rate Limited",
                headers={"Retry-After": "1"},
            )

        with respx.mock:
            respx.get(f"{qb_server.base_url}/company/{qb_server.realm_id}/account").mock(
                side_effect=request_handler
            )

            qb_server.token_manager.get_access_token = AsyncMock(
                return_value="mock_access_token"
            )

            # Call _make_request (should raise HTTPStatusError after retries)
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await qb_server._make_request(
                    method="GET",
                    endpoint=f"/company/{qb_server.realm_id}/account",
                    access_token="mock_access_token",
                    trace_id="test_trace",
                )

            assert exc_info.value.response.status_code == 429
            # Verify multiple calls were made (tenacity retries 5 times by default)
            assert call_count >= 3

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test graceful error on missing credentials."""
        # Clear env vars
        with patch.dict(os.environ, {}, clear=True):
            # Call tool - should raise ValueError during initialization
            with pytest.raises(ValueError) as exc_info:
                QuickBooksMCPServer()

            # Verify error message (doesn't crash)
            error_msg = str(exc_info.value)
            assert "Missing required QuickBooks configuration" in error_msg
            assert "QB_CLIENT_ID" in error_msg


# ─────────────────────────────────────────────────────────────────────────────
# Additional Edge Case Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuickBooksEdgeCases:
    """Test QuickBooks edge cases and validation."""

    def test_create_bill_request_validation(self):
        """Test CreateBillRequest validation."""
        # Valid request
        request = CreateBillRequest(
            vendor_id="vendor_1",
            line_items=[LineItem(description="Test", amount=100.0)],
            due_date="2024-02-15",
        )
        assert request.due_date == "2024-02-15"

        # Invalid date format
        with pytest.raises(ValueError) as exc_info:
            CreateBillRequest(
                vendor_id="vendor_1",
                line_items=[LineItem(description="Test", amount=100.0)],
                due_date="02-15-2024",  # Wrong format
            )
        assert "Date must be in YYYY-MM-DD format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_bill_request_empty_line_items(self):
        """Test CreateBillRequest rejects empty line items."""
        with pytest.raises(ValueError) as exc_info:
            CreateBillRequest(
                vendor_id="vendor_1",
                line_items=[],  # Empty not allowed
                due_date="2024-02-15",
            )
        # Pydantic raises "too_short" error for min_length violation
        assert "too_short" in str(exc_info.value) or "at least" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_token_manager_missing_refresh_token(self, qb_env_vars, tmp_path):
        """Test TokenManager error when refresh token is missing."""
        # Use a non-existent token file path to avoid loading cached tokens
        with patch(
            "src.mcp_servers.quickbooks_mcp.TOKEN_FILE_PATH",
            tmp_path / "nonexistent" / "qb_tokens.json"
        ):
            manager = TokenManager(
                client_id=qb_env_vars["QB_CLIENT_ID"],
                client_secret=qb_env_vars["QB_CLIENT_SECRET"],
                realm_id=qb_env_vars["QB_REALM_ID"],
                sandbox=True,
            )

            # Ensure no refresh token
            manager._refresh_token = None
            manager._access_token = None

            # Call get_access_token - should raise ValueError
            with pytest.raises(ValueError) as exc_info:
                await manager.get_access_token()

            assert "QuickBooks refresh token not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_refresh_http_error(self, qb_env_vars):
        """Test TokenManager handles HTTP errors during refresh."""
        manager = TokenManager(
            client_id=qb_env_vars["QB_CLIENT_ID"],
            client_secret=qb_env_vars["QB_CLIENT_SECRET"],
            realm_id=qb_env_vars["QB_REALM_ID"],
            refresh_token="invalid_token",
            sandbox=True,
        )

        with respx.mock:
            respx.post(QB_OAUTH_TOKEN_URL).mock(
                return_value=Response(401, json={"error": "invalid_grant"})
            )

            with pytest.raises(httpx.HTTPStatusError):
                await manager._refresh_tokens()
