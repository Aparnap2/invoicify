"""Salesforce MCP Server with JWT Bearer authentication.

This module implements a production-grade Model Context Protocol (MCP) server
for Salesforce API integration using OAuth 2.0 JWT Bearer Flow.

Features:
- OAuth 2.0 JWT Bearer Flow (server-to-server, no browser)
- RSA-signed JWT with cryptography library
- Access token caching (15 minutes)
- Automatic token refresh on 401 errors
- Exponential backoff for rate limiting (429)
- Structured logging with trace_id correlation
- Typed I/O models using Pydantic v2

Tools (6 total):
1. sf_create_case - Create cases in Salesforce
2. sf_get_account - Query account information
3. sf_create_account - Create new accounts
4. sf_update_case - Update case status and resolution
5. sf_query - Execute SOQL queries
6. sf_get_case - Retrieve case details

Usage:
    # Run as MCP server
    python -m src.mcp_servers.salesforce_mcp

    # Run smoke test
    python -m src.mcp_servers.salesforce_mcp --smoke-test

Environment Variables:
    SF_CONSUMER_KEY - Salesforce Connected App consumer key
    SF_USERNAME - Pre-authorized Salesforce username
    SF_PRIVATE_KEY_PEM - RSA private key (PEM string or path to .pem file)
    SF_INSTANCE_URL - Salesforce instance URL (e.g., https://yourorg.my.salesforce.com)
    SF_SANDBOX - Use test.salesforce.com for token endpoint (default: true)

References:
    - Salesforce JWT Bearer Flow: https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_jwt_flow.htm&type=5
    - REST API: https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_list.htm
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import jwt
import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from mcp.server import Server
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Configuration Constants
# ─────────────────────────────────────────────────────────────────────────────

SF_TOKEN_ENDPOINT_PRODUCTION = "https://login.salesforce.com/services/oauth2/token"
SF_TOKEN_ENDPOINT_SANDBOX = "https://test.salesforce.com/services/oauth2/token"

ACCESS_TOKEN_TTL_SECONDS = 900  # 15 minutes
JWT_EXPIRY_SECONDS = 300  # 5 minutes (must be < access token lifetime)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic I/O Models
# ─────────────────────────────────────────────────────────────────────────────


class CreateCaseRequest(BaseModel):
    """Request model for creating a case."""

    subject: str = Field(..., description="Case subject")
    description: str = Field(..., description="Case description")
    account_name: str = Field(..., description="Account name")
    priority: str = Field(default="Medium", description="Case priority (Low, Medium, High)")
    type: str = Field(default="Question", description="Case type")


class CreateCaseResponse(BaseModel):
    """Response model for case creation."""

    case_id: str = Field(..., description="Salesforce Case ID")
    case_number: str = Field(..., description="Case number (e.g., 000000001)")
    status: str = Field(..., description="Case status")
    subject: str = Field(..., description="Case subject")
    priority: str = Field(..., description="Case priority")
    created_at: str = Field(..., description="Creation timestamp")


class GetAccountRequest(BaseModel):
    """Request model for querying accounts."""

    account_name: str = Field(..., description="Account name to search for")


class GetAccountResponse(BaseModel):
    """Response model for account query."""

    account_id: str = Field(..., description="Salesforce Account ID")
    name: str = Field(..., description="Account name")
    phone: Optional[str] = Field(default=None, description="Account phone")
    industry: Optional[str] = Field(default=None, description="Account industry")
    billing_city: Optional[str] = Field(default=None, description="Billing city")
    billing_state: Optional[str] = Field(default=None, description="Billing state")


class CreateAccountRequest(BaseModel):
    """Request model for creating an account."""

    name: str = Field(..., description="Account name")
    phone: Optional[str] = Field(default=None, description="Account phone")
    industry: Optional[str] = Field(default=None, description="Account industry")
    billing_street: Optional[str] = Field(default=None, description="Billing street")
    billing_city: Optional[str] = Field(default=None, description="Billing city")
    billing_state: Optional[str] = Field(default=None, description="Billing state")
    billing_postal_code: Optional[str] = Field(default=None, description="Billing postal code")
    billing_country: Optional[str] = Field(default=None, description="Billing country")


class CreateAccountResponse(BaseModel):
    """Response model for account creation."""

    account_id: str = Field(..., description="Salesforce Account ID")
    name: str = Field(..., description="Account name")
    created_at: str = Field(..., description="Creation timestamp")


class UpdateCaseRequest(BaseModel):
    """Request model for updating a case."""

    case_id: str = Field(..., description="Salesforce Case ID")
    status: str = Field(..., description="New case status")
    resolution_notes: Optional[str] = Field(default=None, description="Resolution notes")
    priority: Optional[str] = Field(default=None, description="Updated priority")
    subject: Optional[str] = Field(default=None, description="Updated subject")


class UpdateCaseResponse(BaseModel):
    """Response model for case update."""

    case_id: str = Field(..., description="Salesforce Case ID")
    case_number: str = Field(..., description="Case number")
    status: str = Field(..., description="Updated status")
    updated_at: str = Field(..., description="Update timestamp")
    success: bool = Field(default=True, description="Update success flag")


class QueryRequest(BaseModel):
    """Request model for SOQL queries."""

    soql: str = Field(..., description="SOQL query string")


class QueryResponse(BaseModel):
    """Response model for SOQL query results."""

    records: List[Dict[str, Any]] = Field(..., description="Query result records")
    total_size: int = Field(..., description="Total number of records")
    done: bool = Field(..., description="Query completion flag")
    next_records_url: Optional[str] = Field(default=None, description="URL for next batch")


class GetCaseRequest(BaseModel):
    """Request model for retrieving a case."""

    case_id: str = Field(..., description="Salesforce Case ID")


class GetCaseResponse(BaseModel):
    """Response model for case retrieval."""

    case_id: str = Field(..., description="Salesforce Case ID")
    case_number: str = Field(..., description="Case number")
    subject: str = Field(..., description="Case subject")
    description: Optional[str] = Field(default=None, description="Case description")
    status: str = Field(..., description="Case status")
    priority: str = Field(..., description="Case priority")
    type: str = Field(..., description="Case type")
    account_id: Optional[str] = Field(default=None, description="Related Account ID")
    account_name: Optional[str] = Field(default=None, description="Related Account Name")
    contact_id: Optional[str] = Field(default=None, description="Related Contact ID")
    owner_id: str = Field(..., description="Case Owner ID")
    created_date: str = Field(..., description="Creation timestamp")
    last_modified_date: str = Field(..., description="Last modified timestamp")


# ─────────────────────────────────────────────────────────────────────────────
# JWT Manager
# ─────────────────────────────────────────────────────────────────────────────


class JWTManager:
    """
    OAuth 2.0 JWT Bearer Flow Manager for Salesforce API.

    Handles:
    - RSA-signed JWT generation with cryptography library
    - Token minting via POST to Salesforce OAuth endpoint
    - Access token caching (15 minutes)
    - Automatic token refresh on expiry
    - Support for both production and sandbox environments

    JWT Claims:
    {
        "iss": SF_CONSUMER_KEY,
        "sub": SF_USERNAME,
        "aud": "https://login.salesforce.com" or "https://test.salesforce.com",
        "exp": now + 300s,
        "iat": now
    }

    Token Lifecycle:
    - access_token: Valid for 15 minutes (900 seconds)
    - No refresh token needed (JWT re-minted on each request)
    - Private key loaded at startup, kept in memory
    """

    def __init__(
        self,
        consumer_key: str,
        username: str,
        private_key_pem: str,
        instance_url: str,
        sandbox: bool = True,
    ):
        """
        Initialize JWT Manager.

        Args:
            consumer_key: Salesforce Connected App consumer key
            username: Pre-authorized Salesforce username
            private_key_pem: RSA private key (PEM string or path to .pem file)
            instance_url: Salesforce instance URL
            sandbox: Use test.salesforce.com for token endpoint
        """
        self.consumer_key = consumer_key
        self.username = username
        self.instance_url = instance_url
        self.sandbox = sandbox
        self._trace_id: str = str(uuid.uuid4())

        # Determine token endpoint
        self.token_endpoint = (
            SF_TOKEN_ENDPOINT_SANDBOX if sandbox else SF_TOKEN_ENDPOINT_PRODUCTION
        )

        # Determine audience (aud claim)
        self.audience = (
            SF_TOKEN_ENDPOINT_SANDBOX.replace("/services/oauth2/token", "")
            if sandbox
            else SF_TOKEN_ENDPOINT_PRODUCTION.replace("/services/oauth2/token", "")
        )

        # Load private key
        self._private_key = self._load_private_key(private_key_pem)

        # Token cache
        self._access_token: Optional[str] = None
        self._expires_at: Optional[float] = None

        logger.info(
            "jwt_manager_initialized",
            trace_id=self._trace_id,
            sandbox=self.sandbox,
            token_endpoint=self.token_endpoint,
        )

    def _load_private_key(self, private_key_pem: str) -> Any:
        """
        Load RSA private key from PEM string or file path.

        Args:
            private_key_pem: PEM string or path to .pem file

        Returns:
            Loaded private key object

        Raises:
            ValueError: If private key cannot be loaded
        """
        try:
            # Check if it's a file path
            if private_key_pem.startswith("/") or private_key_pem.endswith(".pem"):
                pem_path = Path(private_key_pem)
                if pem_path.exists():
                    logger.info(
                        "private_key_loaded_from_file",
                        trace_id=self._trace_id,
                        file_path=str(pem_path),
                    )
                    private_key_pem = pem_path.read_text()
                else:
                    logger.warning(
                        "private_key_file_not_found",
                        trace_id=self._trace_id,
                        file_path=private_key_pem,
                    )

            # Load PEM string
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
            )

            logger.info(
                "private_key_loaded",
                trace_id=self._trace_id,
                key_type=type(private_key).__name__,
            )

            return private_key

        except Exception as e:
            logger.error(
                "private_key_load_failed",
                trace_id=self._trace_id,
                error=str(e),
            )
            raise ValueError(f"Failed to load private key: {e}")

    def _generate_jwt(self, trace_id: Optional[str] = None) -> str:
        """
        Generate RSA-signed JWT for OAuth 2.0 Bearer Flow.

        Args:
            trace_id: Optional trace ID for correlation

        Returns:
            Signed JWT token string
        """
        current_trace_id = trace_id or self._trace_id
        now = datetime.now(timezone.utc)

        # Build JWT claims
        claims = {
            "iss": self.consumer_key,
            "sub": self.username,
            "aud": self.audience,
            "exp": int(now.timestamp()) + JWT_EXPIRY_SECONDS,
            "iat": int(now.timestamp()),
        }

        logger.debug(
            "jwt_claims_generated",
            trace_id=current_trace_id,
            iss=self.consumer_key[:8] + "...",
            sub=self.username,
            aud=self.audience,
        )

        # Sign JWT with RSA private key
        jwt_token = jwt.encode(
            claims,
            self._private_key,
            algorithm="RS256",
        )

        logger.info(
            "jwt_generated",
            trace_id=current_trace_id,
            expires_in_seconds=JWT_EXPIRY_SECONDS,
        )

        return jwt_token

    async def get_access_token(self, trace_id: Optional[str] = None) -> str:
        """
        Get valid access token, minting new JWT if necessary.

        Args:
            trace_id: Optional trace ID for correlation

        Returns:
            Valid access token

        Raises:
            ValueError: If token minting fails
        """
        current_trace_id = trace_id or self._trace_id

        # Check if we have a valid access token (with 1-minute buffer)
        if self._access_token and self._expires_at and time.time() < self._expires_at - 60:
            logger.debug(
                "access_token_valid",
                trace_id=current_trace_id,
                expires_in_seconds=int(self._expires_at - time.time()),
            )
            return self._access_token

        # Need to mint new token
        logger.info(
            "access_token_refresh_needed",
            trace_id=current_trace_id,
            expired_ago_seconds=(
                int(time.time() - self._expires_at) if self._expires_at else None
            ),
        )

        await self._mint_access_token(trace_id=current_trace_id)
        return self._access_token

    async def _mint_access_token(self, trace_id: Optional[str] = None) -> None:
        """
        Mint new access token using JWT Bearer Flow.

        Args:
            trace_id: Optional trace ID for correlation

        Raises:
            httpx.HTTPStatusError: If token minting fails
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "access_token_mint_started",
            trace_id=current_trace_id,
            token_endpoint=self.token_endpoint,
        )

        # Generate JWT
        jwt_token = self._generate_jwt(trace_id=current_trace_id)

        # POST to token endpoint
        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.token_endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )

            if response.status_code != 200:
                logger.error(
                    "access_token_mint_failed",
                    trace_id=current_trace_id,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )
                response.raise_for_status()

            data = response.json()

        # Cache access token
        self._access_token = data.get("access_token")
        self._expires_at = time.time() + data.get("expires_in", ACCESS_TOKEN_TTL_SECONDS)

        logger.info(
            "access_token_minted",
            trace_id=current_trace_id,
            expires_in_seconds=data.get("expires_in"),
            instance_url=data.get("instance_url"),
        )

    def invalidate_token(self) -> None:
        """Invalidate cached access token (force re-mint on next request)."""
        self._access_token = None
        self._expires_at = None
        logger.info(
            "access_token_invalidated",
            trace_id=self._trace_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Salesforce MCP Server
# ─────────────────────────────────────────────────────────────────────────────


class SalesforceMCPServer:
    """
    Salesforce MCP Server.

    Provides 6 tools for Salesforce integration:
    1. sf_create_case - Create cases
    2. sf_get_account - Query accounts
    3. sf_create_account - Create accounts
    4. sf_update_case - Update cases
    5. sf_query - Execute SOQL queries
    6. sf_get_case - Get case details

    Features:
    - OAuth 2.0 JWT Bearer Flow with auto-refresh
    - Rate limiting with exponential backoff (tenacity)
    - 401 error handling with JWT re-mint + retry
    - Structured logging with trace_id
    - Typed I/O with Pydantic
    """

    def __init__(self):
        """Initialize Salesforce MCP Server."""
        self.server = Server("salesforce")
        self._trace_id: str = str(uuid.uuid4())

        # Load configuration
        self.consumer_key = os.getenv("SF_CONSUMER_KEY")
        self.username = os.getenv("SF_USERNAME")
        self.private_key_pem = os.getenv("SF_PRIVATE_KEY_PEM")
        self.instance_url = os.getenv("SF_INSTANCE_URL")
        self.sandbox = os.getenv("SF_SANDBOX", "true").lower() != "false"

        # Validate required configuration
        self._validate_config()

        # Initialize JWT manager
        self.jwt_manager = JWTManager(
            consumer_key=self.consumer_key or "",
            username=self.username or "",
            private_key_pem=self.private_key_pem or "",
            instance_url=self.instance_url or "",
            sandbox=self.sandbox,
        )

        # Base URL for REST API
        self.base_url = f"{self.instance_url}/services/data/v58.0"

        # Register tools
        self._register_tools()

        logger.info(
            "salesforce_mcp_server_initialized",
            trace_id=self._trace_id,
            sandbox=self.sandbox,
            base_url=self.base_url,
        )

    def _validate_config(self) -> None:
        """
        Validate required configuration.

        Raises:
            ValueError: If required configuration is missing
        """
        missing = []
        if not self.consumer_key:
            missing.append("SF_CONSUMER_KEY")
        if not self.username:
            missing.append("SF_USERNAME")
        if not self.private_key_pem:
            missing.append("SF_PRIVATE_KEY_PEM")
        if not self.instance_url:
            missing.append("SF_INSTANCE_URL")

        if missing:
            logger.error(
                "salesforce_config_missing",
                trace_id=self._trace_id,
                missing_vars=missing,
            )
            raise ValueError(
                f"Missing required Salesforce configuration: {', '.join(missing)}. "
                "Please set these environment variables."
            )

    def _register_tools(self) -> None:
        """Register all MCP tools."""

        @self.server.tool()
        async def sf_create_case(
            subject: str,
            description: str,
            account_name: str,
            priority: str = "Medium",
            type: str = "Question",
        ) -> Dict[str, Any]:
            """
            Create a case in Salesforce.

            Args:
                subject: Case subject
                description: Case description
                account_name: Account name
                priority: Case priority (Low, Medium, High)
                type: Case type

            Returns:
                Case creation result with case_id, case_number, status
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "sf_create_case_called",
                trace_id=trace_id,
                subject=subject,
                account_name=account_name,
            )

            try:
                # Validate request
                request = CreateCaseRequest(
                    subject=subject,
                    description=description,
                    account_name=account_name,
                    priority=priority,
                    type=type,
                )

                # Get access token
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

                # Build payload
                payload = {
                    "Subject": request.subject,
                    "Description": request.description,
                    "Priority": request.priority,
                    "Type": request.type,
                }

                # Make API call with retry
                response = await self._make_request(
                    method="POST",
                    endpoint="/sobjects/Case",
                    json=payload,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                result = CreateCaseResponse(
                    case_id=response.get("id", ""),
                    case_number="",  # Will be fetched separately
                    status="New",
                    subject=request.subject,
                    priority=request.priority,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )

                # Fetch case number
                case_details = await self._get_case_details(
                    case_id=result.case_id,
                    access_token=access_token,
                    trace_id=trace_id,
                )
                result.case_number = case_details.get("CaseNumber", "")

                logger.info(
                    "sf_create_case_successful",
                    trace_id=trace_id,
                    case_id=result.case_id,
                    case_number=result.case_number,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "sf_create_case_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def sf_get_account(account_name: str) -> Dict[str, Any]:
            """
            Query account information from Salesforce.

            Args:
                account_name: Account name to search for

            Returns:
                Account information with account_id, name, phone, industry
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "sf_get_account_called",
                trace_id=trace_id,
                account_name=account_name,
            )

            try:
                # Get access token
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

                # Build SOQL query (escape single quotes)
                escaped_name = account_name.replace("'", "\\'")
                soql = (
                    f"SELECT Id, Name, Phone, Industry, BillingCity, BillingState "
                    f"FROM Account WHERE Name LIKE '%{escaped_name}%' LIMIT 10"
                )

                # Make API call
                response = await self._make_request(
                    method="GET",
                    endpoint="/query",
                    params={"q": soql},
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                records = response.get("records", [])
                if not records:
                    logger.warning(
                        "sf_get_account_no_results",
                        trace_id=trace_id,
                        account_name=account_name,
                    )
                    return {"error": f"No accounts found matching '{account_name}'"}

                # Return first match
                account = records[0]
                result = GetAccountResponse(
                    account_id=account.get("Id", ""),
                    name=account.get("Name", ""),
                    phone=account.get("Phone"),
                    industry=account.get("Industry"),
                    billing_city=account.get("BillingCity"),
                    billing_state=account.get("BillingState"),
                )

                logger.info(
                    "sf_get_account_successful",
                    trace_id=trace_id,
                    account_id=result.account_id,
                    account_name=result.name,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "sf_get_account_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def sf_create_account(
            name: str,
            phone: Optional[str] = None,
            industry: Optional[str] = None,
            billing_street: Optional[str] = None,
            billing_city: Optional[str] = None,
            billing_state: Optional[str] = None,
            billing_postal_code: Optional[str] = None,
            billing_country: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Create a new account in Salesforce.

            Args:
                name: Account name
                phone: Account phone
                industry: Account industry
                billing_street: Billing street address
                billing_city: Billing city
                billing_state: Billing state
                billing_postal_code: Billing postal code
                billing_country: Billing country

            Returns:
                Account creation result with account_id, name
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "sf_create_account_called",
                trace_id=trace_id,
                account_name=name,
            )

            try:
                # Validate request
                request = CreateAccountRequest(
                    name=name,
                    phone=phone,
                    industry=industry,
                    billing_street=billing_street,
                    billing_city=billing_city,
                    billing_state=billing_state,
                    billing_postal_code=billing_postal_code,
                    billing_country=billing_country,
                )

                # Get access token
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

                # Build payload
                payload = {
                    "Name": request.name,
                }
                if request.phone:
                    payload["Phone"] = request.phone
                if request.industry:
                    payload["Industry"] = request.industry
                if request.billing_street:
                    payload["BillingStreet"] = request.billing_street
                if request.billing_city:
                    payload["BillingCity"] = request.billing_city
                if request.billing_state:
                    payload["BillingState"] = request.billing_state
                if request.billing_postal_code:
                    payload["BillingPostalCode"] = request.billing_postal_code
                if request.billing_country:
                    payload["BillingCountry"] = request.billing_country

                # Make API call with retry
                response = await self._make_request(
                    method="POST",
                    endpoint="/sobjects/Account",
                    json=payload,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                result = CreateAccountResponse(
                    account_id=response.get("id", ""),
                    name=request.name,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )

                logger.info(
                    "sf_create_account_successful",
                    trace_id=trace_id,
                    account_id=result.account_id,
                    account_name=result.name,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "sf_create_account_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def sf_update_case(
            case_id: str,
            status: str,
            resolution_notes: Optional[str] = None,
            priority: Optional[str] = None,
            subject: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Update a case in Salesforce.

            Args:
                case_id: Salesforce Case ID
                status: New case status
                resolution_notes: Resolution notes
                priority: Updated priority
                subject: Updated subject

            Returns:
                Update result with case_id, status, updated_at
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "sf_update_case_called",
                trace_id=trace_id,
                case_id=case_id,
                status=status,
            )

            try:
                # Validate request
                request = UpdateCaseRequest(
                    case_id=case_id,
                    status=status,
                    resolution_notes=resolution_notes,
                    priority=priority,
                    subject=subject,
                )

                # Get access token
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

                # Build payload
                payload = {
                    "Status": request.status,
                }
                if request.resolution_notes:
                    payload["ResolutionNotes"] = request.resolution_notes
                if request.priority:
                    payload["Priority"] = request.priority
                if request.subject:
                    payload["Subject"] = request.subject

                # Make API call with retry
                await self._make_request(
                    method="PATCH",
                    endpoint=f"/sobjects/Case/{request.case_id}",
                    json=payload,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Fetch updated case details
                case_details = await self._get_case_details(
                    case_id=case_id,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                result = UpdateCaseResponse(
                    case_id=case_id,
                    case_number=case_details.get("CaseNumber", ""),
                    status=status,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    success=True,
                )

                logger.info(
                    "sf_update_case_successful",
                    trace_id=trace_id,
                    case_id=case_id,
                    status=status,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "sf_update_case_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def sf_query(soql: str) -> Dict[str, Any]:
            """
            Execute a SOQL query in Salesforce.

            Args:
                soql: SOQL query string

            Returns:
                Query results with records, total_size, done
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "sf_query_called",
                trace_id=trace_id,
                soql=soql[:100] + "..." if len(soql) > 100 else soql,
            )

            try:
                # Get access token
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

                # Make API call
                response = await self._make_request(
                    method="GET",
                    endpoint="/query",
                    params={"q": soql},
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                result = QueryResponse(
                    records=response.get("records", []),
                    total_size=response.get("totalSize", 0),
                    done=response.get("done", False),
                    next_records_url=response.get("nextRecordsUrl"),
                )

                logger.info(
                    "sf_query_successful",
                    trace_id=trace_id,
                    total_size=result.total_size,
                    done=result.done,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "sf_query_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def sf_get_case(case_id: str) -> Dict[str, Any]:
            """
            Retrieve case details from Salesforce.

            Args:
                case_id: Salesforce Case ID

            Returns:
                Case details with case_id, case_number, subject, status, etc.
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "sf_get_case_called",
                trace_id=trace_id,
                case_id=case_id,
            )

            try:
                # Get access token
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

                # Fetch case details
                case_details = await self._get_case_details(
                    case_id=case_id,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                result = GetCaseResponse(
                    case_id=case_details.get("Id", ""),
                    case_number=case_details.get("CaseNumber", ""),
                    subject=case_details.get("Subject", ""),
                    description=case_details.get("Description"),
                    status=case_details.get("Status", ""),
                    priority=case_details.get("Priority", ""),
                    type=case_details.get("Type", ""),
                    account_id=case_details.get("AccountId"),
                    account_name=case_details.get("Account", {}).get("Name")
                    if case_details.get("Account")
                    else None,
                    contact_id=case_details.get("ContactId"),
                    owner_id=case_details.get("OwnerId", ""),
                    created_date=case_details.get("CreatedDate", ""),
                    last_modified_date=case_details.get("LastModifiedDate", ""),
                )

                logger.info(
                    "sf_get_case_successful",
                    trace_id=trace_id,
                    case_id=case_id,
                    case_number=result.case_number,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "sf_get_case_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

    async def _get_case_details(
        self,
        case_id: str,
        access_token: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch case details with related account information.

        Args:
            case_id: Salesforce Case ID
            access_token: Valid access token
            trace_id: Trace ID for correlation

        Returns:
            Case details dictionary
        """
        # Query case with related account
        soql = (
            f"SELECT Id, CaseNumber, Subject, Description, Status, Priority, Type, "
            f"AccountId, Account.Name, ContactId, OwnerId, CreatedDate, LastModifiedDate "
            f"FROM Case WHERE Id = '{case_id}'"
        )

        response = await self._make_request(
            method="GET",
            endpoint="/query",
            params={"q": soql},
            access_token=access_token,
            trace_id=trace_id,
        )

        records = response.get("records", [])
        if not records:
            raise ValueError(f"Case {case_id} not found")

        return records[0]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        trace_id: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Salesforce API with retry logic.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint
            access_token: Valid access token
            trace_id: Trace ID for correlation
            json: Optional JSON payload
            params: Optional query parameters

        Returns:
            Response JSON dictionary

        Raises:
            httpx.HTTPStatusError: If request fails after retries
            httpx.RequestError: If network error occurs
        """
        url = f"{self.base_url}{endpoint}"

        logger.debug(
            "salesforce_api_request",
            trace_id=trace_id,
            method=method,
            url=url,
        )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
            )

            # Handle 401 Unauthorized - re-mint JWT and retry once
            if response.status_code == 401:
                logger.warning(
                    "salesforce_api_401_remint",
                    trace_id=trace_id,
                    endpoint=endpoint,
                )
                self.jwt_manager.invalidate_token()
                access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)
                headers["Authorization"] = f"Bearer {access_token}"

                # Retry once
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                )

            # Handle 429 Rate Limit
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "30")
                logger.warning(
                    "salesforce_api_429_rate_limit",
                    trace_id=trace_id,
                    retry_after_seconds=retry_after,
                )
                response.raise_for_status()

            # Handle other errors
            if response.status_code >= 400:
                logger.error(
                    "salesforce_api_error",
                    trace_id=trace_id,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )
                response.raise_for_status()

            # Parse response
            if response.status_code == 204:
                return {}

            return response.json()

    async def run(self) -> None:
        """Run the MCP server using stdio transport."""
        logger.info(
            "salesforce_mcp_server_starting",
            trace_id=self._trace_id,
        )

        await self.server.run(
            None,  # stdin
            None,  # stdout
            None,  # stderr
        )

    async def smoke_test(self) -> bool:
        """
        Run smoke test to verify Salesforce connectivity.

        Returns:
            True if test passes, False otherwise
        """
        trace_id = str(uuid.uuid4())
        logger.info(
            "salesforce_smoke_test_started",
            trace_id=trace_id,
        )

        try:
            # Get access token
            access_token = await self.jwt_manager.get_access_token(trace_id=trace_id)

            # Query organization
            soql = "SELECT Id, Name FROM Organization LIMIT 1"
            response = await self._make_request(
                method="GET",
                endpoint="/query",
                params={"q": soql},
                access_token=access_token,
                trace_id=trace_id,
            )

            records = response.get("records", [])
            if records:
                org_name = records[0].get("Name", "Unknown")
                logger.info(
                    "salesforce_smoke_test_passed",
                    trace_id=trace_id,
                    org_name=org_name,
                )
                print(f"SF: ✓ Connected to {org_name}")
                return True
            else:
                logger.error(
                    "salesforce_smoke_test_no_org",
                    trace_id=trace_id,
                )
                print("SF: ✗ No organization found")
                return False

        except Exception as e:
            logger.error(
                "salesforce_smoke_test_failed",
                trace_id=trace_id,
                error=str(e),
            )
            print(f"SF: ✗ {e}")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point with smoke test support."""
    parser = argparse.ArgumentParser(description="Salesforce MCP Server")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run smoke test to verify Salesforce connectivity",
    )
    args = parser.parse_args()

    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.INFO if not args.smoke_test else logging.DEBUG
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Create server
    try:
        server = SalesforceMCPServer()
    except ValueError as e:
        logger.error("salesforce_mcp_init_failed", error=str(e))
        print(f"Error: {e}")
        sys.exit(1)

    # Run smoke test or start server
    if args.smoke_test:
        success = asyncio.run(server.smoke_test())
        sys.exit(0 if success else 1)
    else:
        asyncio.run(server.run())


if __name__ == "__main__":
    import logging
    import sys

    main()
