"""Salesforce MCP Server unit tests.

Tests for Salesforce integration including:
- JWTManager: OAuth 2.0 JWT Bearer authentication
- MCP Tools: sf_create_case, sf_get_account, sf_create_account, sf_update_case, sf_query, sf_get_case
- Error Handling: 401 retry, 429 backoff, missing credentials

All tests use mocking to avoid real API calls.
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response

from src.mcp_servers.salesforce_mcp import (
    ACCESS_TOKEN_TTL_SECONDS,
    CreateAccountRequest,
    CreateAccountResponse,
    CreateCaseRequest,
    CreateCaseResponse,
    GetAccountRequest,
    GetAccountResponse,
    GetCaseRequest,
    GetCaseResponse,
    JWT_EXPIRY_SECONDS,
    JWTManager,
    QueryRequest,
    QueryResponse,
    SalesforceMCPServer,
    SF_TOKEN_ENDPOINT_SANDBOX,
    UpdateCaseRequest,
    UpdateCaseResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sf_env_vars():
    """Set up Salesforce environment variables."""
    # Generate RSA key pair for testing
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    env = {
        "SF_CONSUMER_KEY": "test_consumer_key",
        "SF_USERNAME": "test@example.com",
        "SF_PRIVATE_KEY_PEM": pem.decode("utf-8"),
        "SF_INSTANCE_URL": "https://testorg.my.salesforce.com",
        "SF_SANDBOX": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


@pytest.fixture
def mock_access_token():
    """Mock Salesforce access token."""
    return {
        "access_token": "mock_salesforce_access_token_123",
        "instance_url": "https://testorg.my.salesforce.com",
        "id": "https://test.salesforce.com/id/00Dxx000000xxx/005xx000000xxx",
        "token_type": "Bearer",
        "issued_at": str(int(time.time() * 1000)),
        "signature": "mock_signature",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,  # Return as int, not string
    }


@pytest.fixture
def temp_key_file(tmp_path):
    """Create temporary PEM key file."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "private_key.pem"
    key_file.write_text(pem.decode("utf-8"))
    yield key_file


# ─────────────────────────────────────────────────────────────────────────────
# JWTManager Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestJWTManager:
    """Test Salesforce JWT Bearer authentication."""

    @pytest.mark.asyncio
    async def test_mint_jwt(self, sf_env_vars):
        """Test JWT minting with RSA signature."""
        manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )

        # Call _generate_jwt()
        jwt_token = manager._generate_jwt()

        # Verify JWT structure
        decoded = jwt.decode(jwt_token, options={"verify_signature": False})
        assert decoded["iss"] == sf_env_vars["SF_CONSUMER_KEY"]
        assert decoded["sub"] == sf_env_vars["SF_USERNAME"]
        assert "test.salesforce.com" in decoded["aud"]
        assert "exp" in decoded
        assert "iat" in decoded
        # Verify expiry is approximately 5 minutes from now
        assert decoded["exp"] - decoded["iat"] == JWT_EXPIRY_SECONDS

    @pytest.mark.asyncio
    async def test_get_access_token_cached(self, sf_env_vars):
        """Test token caching (no HTTP call if valid)."""
        manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )

        # Set token as valid (expires in future)
        manager._access_token = "cached_token"
        manager._expires_at = time.time() + ACCESS_TOKEN_TTL_SECONDS

        # Call get_access_token()
        with respx.mock:
            token = await manager.get_access_token()

            # Verify no HTTP call made, returns cached token
            assert token == "cached_token"
            assert respx.calls.call_count == 0

    @pytest.mark.asyncio
    async def test_get_access_token_expired(self, sf_env_vars, mock_access_token):
        """Test auto-refresh on expired token."""
        manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )

        # Set token as expired (expires in past)
        manager._access_token = "expired_token"
        manager._expires_at = time.time() - ACCESS_TOKEN_TTL_SECONDS

        # Mock HTTP call
        with respx.mock:
            respx.post(SF_TOKEN_ENDPOINT_SANDBOX).mock(
                return_value=Response(200, json=mock_access_token)
            )

            # Call get_access_token()
            token = await manager.get_access_token()

            # Verify HTTP call made, JWT re-minted
            assert token == "mock_salesforce_access_token_123"
            assert respx.calls.call_count == 1

    @pytest.mark.asyncio
    async def test_load_private_key_from_string(self, sf_env_vars):
        """Test loading PEM key from string."""
        manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )

        # Verify JWTManager loads correctly
        assert manager._private_key is not None
        assert manager.consumer_key == sf_env_vars["SF_CONSUMER_KEY"]
        assert manager.username == sf_env_vars["SF_USERNAME"]

    @pytest.mark.asyncio
    async def test_load_private_key_from_file(self, sf_env_vars, temp_key_file):
        """Test loading private key from file."""
        # Set SF_PRIVATE_KEY_PEM to file path
        with patch.dict(
            os.environ,
            {"SF_PRIVATE_KEY_PEM": str(temp_key_file)},
            clear=False,
        ):
            manager = JWTManager(
                consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
                username=sf_env_vars["SF_USERNAME"],
                private_key_pem=str(temp_key_file),
                instance_url=sf_env_vars["SF_INSTANCE_URL"],
                sandbox=True,
            )

            # Verify JWTManager loads from file
            assert manager._private_key is not None

    @pytest.mark.asyncio
    async def test_load_private_key_invalid(self, sf_env_vars):
        """Test loading invalid PEM key raises error."""
        with pytest.raises(ValueError) as exc_info:
            JWTManager(
                consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
                username=sf_env_vars["SF_USERNAME"],
                private_key_pem="invalid_pem_content",
                instance_url=sf_env_vars["SF_INSTANCE_URL"],
                sandbox=True,
            )

        assert "Failed to load private key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalidate_token(self, sf_env_vars):
        """Test token invalidation forces re-mint."""
        manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )

        # Set cached token
        manager._access_token = "cached_token"
        manager._expires_at = time.time() + ACCESS_TOKEN_TTL_SECONDS

        # Invalidate
        manager.invalidate_token()

        # Verify token cleared
        assert manager._access_token is None
        assert manager._expires_at is None


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSalesforceTools:
    """Test Salesforce MCP tools helper methods."""

    @pytest.fixture
    def sf_server(self, sf_env_vars):
        """Create Salesforce MCP server instance."""
        # Mock _register_tools to avoid decorator issues during init
        with patch.object(SalesforceMCPServer, "_register_tools", return_value=None):
            with patch.object(JWTManager, "__init__", return_value=None):
                server = SalesforceMCPServer()
                server.jwt_manager = JWTManager(
                    consumer_key="test",
                    username="test",
                    private_key_pem="test",
                    instance_url="https://testorg.my.salesforce.com",
                    sandbox=True,
                )
                server.jwt_manager._access_token = "mock_access_token"
                server.jwt_manager._expires_at = time.time() + ACCESS_TOKEN_TTL_SECONDS
                server.base_url = "https://testorg.my.salesforce.com/services/data/v58.0"
                yield server

    @pytest.mark.asyncio
    async def test_make_request_success(self, sf_server):
        """Test successful HTTP request."""
        with respx.mock:
            respx.get(f"{sf_server.base_url}/test").mock(
                return_value=Response(200, json={"result": "success"})
            )

            result = await sf_server._make_request(
                method="GET",
                endpoint="/test",
                access_token="mock_token",
                trace_id="test_trace",
            )

            assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_make_request_401_retry(self, sf_server):
        """Test 401 triggers JWT re-mint and retry."""
        call_count = 0

        def request_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(401, text="Session expired")
            return Response(200, json={"result": "success"})

        with respx.mock:
            respx.get(f"{sf_server.base_url}/test").mock(
                side_effect=request_handler
            )

            # Mock JWT re-mint
            sf_server.jwt_manager.invalidate_token = MagicMock()
            sf_server.jwt_manager.get_access_token = AsyncMock(
                side_effect=["mock_token", "new_token"]
            )

            result = await sf_server._make_request(
                method="GET",
                endpoint="/test",
                access_token="mock_token",
                trace_id="test_trace",
            )

            assert result["result"] == "success"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_429_rate_limit(self, sf_server):
        """Test 429 raises RetryError after tenacity retries."""
        from tenacity import RetryError

        with respx.mock:
            respx.get(f"{sf_server.base_url}/test").mock(
                return_value=Response(
                    429,
                    text="Rate Limited",
                    headers={"Retry-After": "1"},
                )
            )

            with pytest.raises(RetryError):
                await sf_server._make_request(
                    method="GET",
                    endpoint="/test",
                    access_token="mock_token",
                    trace_id="test_trace",
                )

    def test_create_case_request_validation(self):
        """Test CreateCaseRequest validation."""
        request = CreateCaseRequest(
            subject="Test Case",
            description="Test Description",
            account_name="Test Account",
            priority="High",
            type="Question",
        )
        assert request.subject == "Test Case"
        assert request.priority == "High"

    def test_create_account_request_validation(self):
        """Test CreateAccountRequest validation."""
        request = CreateAccountRequest(name="Test Account")
        assert request.name == "Test Account"

        request = CreateAccountRequest(
            name="Test Account",
            phone="555-1234",
            industry="Technology",
        )
        assert request.phone == "555-1234"
        assert request.industry == "Technology"


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSalesforceErrors:
    """Test Salesforce error handling."""

    @pytest.fixture
    def sf_server(self, sf_env_vars):
        """Create Salesforce MCP server instance."""
        # Mock _register_tools to avoid decorator issues during init
        with patch.object(SalesforceMCPServer, "_register_tools", return_value=None):
            with patch.object(JWTManager, "__init__", return_value=None):
                server = SalesforceMCPServer()
                server.jwt_manager = JWTManager(
                    consumer_key="test",
                    username="test",
                    private_key_pem="test",
                    instance_url="https://testorg.my.salesforce.com",
                    sandbox=True,
                )
                server.jwt_manager._access_token = "mock_access_token"
                server.jwt_manager._expires_at = time.time() + ACCESS_TOKEN_TTL_SECONDS
                server.base_url = "https://testorg.my.salesforce.com/services/data/v58.0"
                yield server

    @pytest.mark.asyncio
    async def test_401_retry(self, sf_server):
        """Test 401 triggers JWT re-mint + retry."""
        call_count = 0

        def request_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return Response(401, text="Session expired")
            return Response(
                200,
                json={
                    "totalSize": 1,
                    "done": True,
                    "records": [{"Id": "001xx000000xxx", "Name": "Account"}],
                },
            )

        with respx.mock:
            # Mock API endpoint
            respx.get(f"{sf_server.base_url}/query").mock(
                side_effect=request_handler
            )

            # Mock token manager
            sf_server.jwt_manager.get_access_token = AsyncMock(
                side_effect=["mock_access_token", "new_access_token"]
            )
            sf_server.jwt_manager.invalidate_token = MagicMock()

            # Call _make_request directly
            result = await sf_server._make_request(
                method="GET",
                endpoint="/query",
                access_token="mock_access_token",
                trace_id="test_trace",
            )

            # Verify tool succeeds after retry
            assert result["totalSize"] == 1
            assert call_count == 2  # Two API calls made

    @pytest.mark.asyncio
    async def test_429_backoff(self, sf_server):
        """Test 429 triggers exponential backoff and raises RetryError."""
        from tenacity import RetryError

        call_count = 0

        def request_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # Always return 429
            return Response(
                429,
                text="Rate Limit Exceeded",
                headers={"Retry-After": "1"},
            )

        with respx.mock:
            respx.get(f"{sf_server.base_url}/query").mock(
                side_effect=request_handler
            )

            sf_server.jwt_manager.get_access_token = AsyncMock(
                return_value="mock_access_token"
            )

            # Call _make_request (should raise RetryError after retries)
            with pytest.raises(RetryError):
                await sf_server._make_request(
                    method="GET",
                    endpoint="/query",
                    access_token="mock_access_token",
                    trace_id="test_trace",
                )

            # Verify multiple calls were made
            assert call_count >= 3

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test graceful error on missing credentials."""
        # Clear env vars
        with patch.dict(os.environ, {}, clear=True):
            # Call tool - should raise ValueError during initialization
            with pytest.raises(ValueError) as exc_info:
                SalesforceMCPServer()

            # Verify error message
            error_msg = str(exc_info.value)
            assert "Missing required Salesforce configuration" in error_msg
            assert "SF_CONSUMER_KEY" in error_msg


# ─────────────────────────────────────────────────────────────────────────────
# Additional Edge Case Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSalesforceEdgeCases:
    """Test Salesforce edge cases and validation."""

    def test_create_case_request_validation(self):
        """Test CreateCaseRequest validation."""
        request = CreateCaseRequest(
            subject="Test Case",
            description="Test Description",
            account_name="Test Account",
            priority="High",
            type="Question",
        )
        assert request.subject == "Test Case"
        assert request.priority == "High"

    def test_create_account_request_validation(self):
        """Test CreateAccountRequest validation."""
        request = CreateAccountRequest(name="Test Account")
        assert request.name == "Test Account"
        assert request.phone is None

    def test_jwt_manager_sandbox_vs_production(self, sf_env_vars):
        """Test JWT manager uses correct endpoints for sandbox vs production."""
        # Sandbox
        sandbox_manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )
        assert "test.salesforce.com" in sandbox_manager.token_endpoint
        assert "test.salesforce.com" in sandbox_manager.audience

        # Production
        prod_manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=False,
        )
        assert "login.salesforce.com" in prod_manager.token_endpoint
        assert "login.salesforce.com" in prod_manager.audience

    def test_jwt_expiry_claims(self, sf_env_vars):
        """Test JWT expiry claims are within acceptable range."""
        manager = JWTManager(
            consumer_key=sf_env_vars["SF_CONSUMER_KEY"],
            username=sf_env_vars["SF_USERNAME"],
            private_key_pem=sf_env_vars["SF_PRIVATE_KEY_PEM"],
            instance_url=sf_env_vars["SF_INSTANCE_URL"],
            sandbox=True,
        )

        jwt_token = manager._generate_jwt()
        decoded = jwt.decode(jwt_token, options={"verify_signature": False})

        # JWT expiry should be 5 minutes (300 seconds)
        assert decoded["exp"] - decoded["iat"] == JWT_EXPIRY_SECONDS
        # Should be less than access token lifetime
        assert JWT_EXPIRY_SECONDS < ACCESS_TOKEN_TTL_SECONDS
