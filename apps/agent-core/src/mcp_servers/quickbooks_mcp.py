"""QuickBooks Online MCP Server with OAuth 2.0 token management.

This module implements a production-grade Model Context Protocol (MCP) server
for QuickBooks Online API integration. It provides 6 tools for invoice processing:

1. qb_create_bill - Create bills in QuickBooks
2. qb_get_vendor - Query vendor information
3. qb_create_vendor - Create new vendors
4. qb_get_bill - Retrieve bill details
5. qb_void_bill - Void existing bills
6. qb_list_accounts - List chart of accounts

Features:
- OAuth 2.0 token refresh with automatic rotation
- Token persistence to Redis (stateless, containerized environments)
- Exponential backoff for rate limiting (429)
- Automatic token refresh on 401 errors
- Structured logging with trace_id correlation
- Typed I/O models using Pydantic v2

Usage:
    # Run as MCP server
    python -m src.mcp_servers.quickbooks_mcp

    # Run smoke test
    python -m src.mcp_servers.quickbooks_mcp --smoke-test

Environment Variables:
    QB_CLIENT_ID - QuickBooks OAuth client ID
    QB_CLIENT_SECRET - QuickBooks OAuth client secret
    QB_REALM_ID - QuickBooks company ID
    QB_REFRESH_TOKEN - OAuth refresh token (or use QB_REFRESH_TOKEN_FILE)
    QB_REFRESH_TOKEN_FILE - Path to file containing refresh token
    QB_SANDBOX - Use sandbox environment (default: true)
    REDIS_URL - Redis URL for token store (Azure Cache for Redis)
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog
from mcp.server import FastMCP
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.db.token_store import get_token_store

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Configuration Constants
# ─────────────────────────────────────────────────────────────────────────────

QB_OAUTH_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QB_SANDBOX_BASE_URL = "https://sandbox-quickbooks.api.intuit.com/v3"
QB_PRODUCTION_BASE_URL = "https://quickbooks.api.intuit.com/v3"

ACCESS_TOKEN_TTL_SECONDS = 3600  # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 8726400  # 100 days


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic I/O Models
# ─────────────────────────────────────────────────────────────────────────────


class LineItem(BaseModel):
    """Line item for bill creation."""

    description: str = Field(..., description="Item description")
    amount: float = Field(..., ge=0, description="Line item amount")
    quantity: Optional[float] = Field(default=1, ge=0, description="Quantity")
    unit_price: Optional[float] = Field(default=0, ge=0, description="Unit price")
    account_ref: Optional[str] = Field(default=None, description="Account reference ID")


class CreateBillRequest(BaseModel):
    """Request model for creating a bill."""

    vendor_id: str = Field(..., description="QuickBooks Vendor ID")
    line_items: List[LineItem] = Field(..., min_length=1, description="Bill line items")
    due_date: str = Field(..., description="Bill due date (YYYY-MM-DD)")
    currency: str = Field(default="USD", description="Currency code (ISO 4217)")
    doc_number: Optional[str] = Field(default=None, description="Document number")
    txn_date: Optional[str] = Field(default=None, description="Transaction date (YYYY-MM-DD)")
    private_note: Optional[str] = Field(default=None, description="Private note")

    @field_validator("due_date", "txn_date", mode="before")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format is YYYY-MM-DD."""
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got: {v}")


class CreateBillResponse(BaseModel):
    """Response model for bill creation."""

    bill_id: str = Field(..., description="QuickBooks Bill ID")
    sync_token: str = Field(..., description="Sync token for updates")
    total_amount: float = Field(..., description="Total bill amount")
    status: str = Field(..., description="Bill status")
    vendor_ref: str = Field(..., description="Vendor reference")
    doc_number: Optional[str] = Field(default=None, description="Document number")
    due_date: str = Field(..., description="Bill due date")
    created_at: str = Field(..., description="Creation timestamp")


class GetVendorRequest(BaseModel):
    """Request model for querying vendors."""

    vendor_name: str = Field(..., description="Vendor name to search for")


class GetVendorResponse(BaseModel):
    """Response model for vendor query."""

    vendor_id: str = Field(..., description="QuickBooks Vendor ID")
    display_name: str = Field(..., description="Vendor display name")
    email: Optional[str] = Field(default=None, description="Vendor email")
    phone: Optional[str] = Field(default=None, description="Vendor phone")
    balance: float = Field(default=0, description="Current balance")
    active: bool = Field(default=True, description="Vendor active status")


class CreateVendorRequest(BaseModel):
    """Request model for creating a vendor."""

    display_name: str = Field(..., description="Vendor display name")
    email: Optional[str] = Field(default=None, description="Vendor email")
    phone: Optional[str] = Field(default=None, description="Vendor phone")
    given_name: Optional[str] = Field(default=None, description="Contact first name")
    family_name: Optional[str] = Field(default=None, description="Contact last name")
    company_name: Optional[str] = Field(default=None, description="Company name")


class CreateVendorResponse(BaseModel):
    """Response model for vendor creation."""

    vendor_id: str = Field(..., description="QuickBooks Vendor ID")
    display_name: str = Field(..., description="Vendor display name")
    sync_token: str = Field(..., description="Sync token")
    created_at: str = Field(..., description="Creation timestamp")
    active: bool = Field(default=True, description="Active status")


class GetBillRequest(BaseModel):
    """Request model for retrieving a bill."""

    bill_id: str = Field(..., description="QuickBooks Bill ID")


class GetBillResponse(BaseModel):
    """Response model for bill retrieval."""

    bill_id: str = Field(..., description="QuickBooks Bill ID")
    sync_token: str = Field(..., description="Sync token")
    vendor_ref: str = Field(..., description="Vendor reference")
    total_amount: float = Field(..., description="Total amount")
    balance: float = Field(..., description="Remaining balance")
    status: str = Field(..., description="Bill status")
    due_date: str = Field(..., description="Due date")
    txn_date: str = Field(..., description="Transaction date")
    line_items: List[Dict[str, Any]] = Field(default_factory=list, description="Line items")


class VoidBillRequest(BaseModel):
    """Request model for voiding a bill."""

    bill_id: str = Field(..., description="QuickBooks Bill ID")


class VoidBillResponse(BaseModel):
    """Response model for bill voiding."""

    bill_id: str = Field(..., description="QuickBooks Bill ID")
    sync_token: str = Field(..., description="Updated sync token")
    status: str = Field(..., description="Bill status (should be 'Void')")
    voided_at: str = Field(..., description="Void timestamp")


class ListAccountsResponse(BaseModel):
    """Response model for listing accounts."""

    accounts: List[Dict[str, Any]] = Field(..., description="List of accounts")
    count: int = Field(..., description="Number of accounts returned")


# ─────────────────────────────────────────────────────────────────────────────
# Token Manager
# ─────────────────────────────────────────────────────────────────────────────


class TokenManager:
    """
    OAuth 2.0 Token Manager for QuickBooks API.

    Handles:
    - Token refresh using refresh_token grant
    - Automatic token rotation (new refresh_token returned on each refresh)
    - Token persistence to Redis (stateless, containerized environments)
    - Auto-refresh when access_token expires
    - Support for both env var and file-based refresh tokens
    - Graceful degradation when Redis unavailable

    Token Lifecycle:
    - access_token: Valid for 1 hour (3600 seconds)
    - refresh_token: Valid for 100 days of inactivity
    - refresh_token rotates on each use (single-use token)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        realm_id: str,
        refresh_token: Optional[str] = None,
        refresh_token_file: Optional[str] = None,
        sandbox: bool = True,
    ):
        """
        Initialize Token Manager.

        Args:
            client_id: QuickBooks OAuth client ID
            client_secret: QuickBooks OAuth client secret
            realm_id: QuickBooks company/realm ID
            refresh_token: OAuth refresh token (from env)
            refresh_token_file: Path to file containing refresh token
            sandbox: Use sandbox environment
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.realm_id = realm_id
        self.sandbox = sandbox
        self._refresh_token_source = refresh_token or refresh_token_file
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[float] = None
        self._trace_id: str = str(uuid.uuid4())

        # Initialize Redis token store
        self.token_store = get_token_store()

        # Override with provided refresh token if available
        if refresh_token:
            self._refresh_token = refresh_token
        elif refresh_token_file:
            self._refresh_token = self._read_refresh_token_from_file(refresh_token_file)

    async def connect(self) -> None:
        """Connect to Redis token store."""
        await self.token_store.connect()

    def _read_refresh_token_from_file(self, file_path: str) -> Optional[str]:
        """
        Read refresh token from a file (fallback method).

        Args:
            file_path: Path to file containing refresh token

        Returns:
            Refresh token or None if file doesn't exist
        """
        try:
            path = Path(file_path)
            if path.exists():
                token = path.read_text().strip()
                logger.info(
                    "refresh_token_loaded_from_file",
                    trace_id=self._trace_id,
                    file_path=str(path),
                )
                return token
        except Exception as e:
            logger.warning(
                "refresh_token_file_read_failed",
                trace_id=self._trace_id,
                file_path=file_path,
                error=str(e),
            )
        return None

    async def _load_tokens_from_redis(self) -> None:
        """
        Load cached tokens from Redis.

        Only loads if access_token is not expired.
        """
        tokens = await self.token_store.get_tokens(self.realm_id)
        
        if not tokens:
            logger.debug(
                "tokens_not_found_in_redis",
                trace_id=self._trace_id,
                realm_id=self.realm_id,
            )
            return

        expires_at = tokens.get("expires_at", 0)

        # Check if tokens are still valid (with 5-minute buffer)
        if time.time() < expires_at - 300:
            self._access_token = tokens.get("access_token")
            self._refresh_token = tokens.get("refresh_token")
            self._expires_at = expires_at

            logger.info(
                "tokens_loaded_from_redis",
                trace_id=self._trace_id,
                realm_id=self.realm_id,
                expires_in_seconds=int(expires_at - time.time()),
            )
        else:
            logger.info(
                "tokens_expired_in_redis",
                trace_id=self._trace_id,
                realm_id=self.realm_id,
                expired_ago_seconds=int(time.time() - expires_at),
            )

    async def _save_tokens_to_redis(self) -> None:
        """
        Save tokens to Redis.

        Persists both access_token and refresh_token for future use.
        """
        if not self._access_token or not self._refresh_token or not self._expires_at:
            logger.warning(
                "token_save_skipped_missing_tokens",
                trace_id=self._trace_id,
            )
            return

        success = await self.token_store.set_tokens(
            realm_id=self.realm_id,
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            expires_at=int(self._expires_at),
        )

        if not success:
            logger.warning(
                "token_save_to_redis_failed",
                trace_id=self._trace_id,
                realm_id=self.realm_id,
            )

    async def get_access_token(self, trace_id: Optional[str] = None) -> str:
        """
        Get valid access token, refreshing if necessary.

        Args:
            trace_id: Optional trace ID for correlation

        Returns:
            Valid access token

        Raises:
            ValueError: If refresh token is missing or invalid
        """
        current_trace_id = trace_id or self._trace_id

        # Check if we have a valid access token (with 5-minute buffer)
        if self._access_token and self._expires_at and time.time() < self._expires_at - 300:
            logger.debug(
                "access_token_valid",
                trace_id=current_trace_id,
                expires_in_seconds=int(self._expires_at - time.time()),
            )
            return self._access_token

        # Need to refresh
        if not self._refresh_token:
            logger.error(
                "refresh_token_missing",
                trace_id=current_trace_id,
            )
            raise ValueError(
                "QuickBooks refresh token not found. "
                "Set QB_REFRESH_TOKEN or QB_REFRESH_TOKEN_FILE environment variable."
            )

        await self._refresh_tokens(trace_id=current_trace_id)
        return self._access_token

    async def _refresh_tokens(self, trace_id: Optional[str] = None) -> None:
        """
        Refresh access and refresh tokens using OAuth 2.0 flow.

        Args:
            trace_id: Optional trace ID for correlation

        Raises:
            httpx.HTTPStatusError: If token refresh fails
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "token_refresh_started",
            trace_id=current_trace_id,
        )

        # Build Basic auth header (base64 encoded client_id:client_secret)
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                QB_OAUTH_TOKEN_URL,
                json=payload,
                headers={
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            if response.status_code != 200:
                logger.error(
                    "token_refresh_failed",
                    trace_id=current_trace_id,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )
                response.raise_for_status()

            data = response.json()

        # Update tokens (refresh_token rotates on each use)
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        self._expires_at = time.time() + data.get("expires_in", ACCESS_TOKEN_TTL_SECONDS)

        # Persist to Redis
        await self._save_tokens_to_redis()

        logger.info(
            "token_refresh_successful",
            trace_id=current_trace_id,
            access_token_expires_in=data.get("expires_in"),
            refresh_token_expires_in=data.get("x_refresh_token_expires_in"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# QuickBooks MCP Server
# ─────────────────────────────────────────────────────────────────────────────


class QuickBooksMCPServer:
    """
    QuickBooks Online MCP Server.

    Provides 6 tools for invoice processing:
    1. qb_create_bill - Create bills
    2. qb_get_vendor - Query vendors
    3. qb_create_vendor - Create vendors
    4. qb_get_bill - Get bill details
    5. qb_void_bill - Void bills
    6. qb_list_accounts - List accounts

    Features:
    - OAuth 2.0 with auto-refresh
    - Rate limiting with exponential backoff
    - Structured logging with trace_id
    - Typed I/O with Pydantic
    """

    async def initialize(self) -> None:
        """Initialize QuickBooks MCP Server (async)."""
        self.server = FastMCP("quickbooks")
        self._trace_id: str = str(uuid.uuid4())

        # Load configuration
        self.client_id = os.getenv("QB_CLIENT_ID")
        self.client_secret = os.getenv("QB_CLIENT_SECRET")
        self.realm_id = os.getenv("QB_REALM_ID")
        self.refresh_token = os.getenv("QB_REFRESH_TOKEN")
        self.refresh_token_file = os.getenv("QB_REFRESH_TOKEN_FILE")
        self.sandbox = os.getenv("QB_SANDBOX", "true").lower() != "false"

        # Validate required configuration
        self._validate_config()

        # Initialize token manager
        self.token_manager = TokenManager(
            client_id=self.client_id or "",
            client_secret=self.client_secret or "",
            realm_id=self.realm_id or "",
            refresh_token=self.refresh_token,
            refresh_token_file=self.refresh_token_file,
            sandbox=self.sandbox,
        )

        # Connect to Redis token store and load cached tokens
        await self.token_manager.connect()
        await self.token_manager._load_tokens_from_redis()

        # Base URL
        self.base_url = QB_SANDBOX_BASE_URL if self.sandbox else QB_PRODUCTION_BASE_URL

        # Register tools
        self._register_tools()

        logger.info(
            "quickbooks_mcp_server_initialized",
            trace_id=self._trace_id,
            sandbox=self.sandbox,
            base_url=self.base_url,
            redis_connected=self.token_manager.token_store._client is not None,
        )

    def _validate_config(self) -> None:
        """
        Validate required configuration.

        Raises:
            ValueError: If required configuration is missing
        """
        missing = []
        if not self.client_id:
            missing.append("QB_CLIENT_ID")
        if not self.client_secret:
            missing.append("QB_CLIENT_SECRET")
        if not self.realm_id:
            missing.append("QB_REALM_ID")
        if not self.refresh_token and not self.refresh_token_file:
            missing.append("QB_REFRESH_TOKEN or QB_REFRESH_TOKEN_FILE")

        if missing:
            logger.error(
                "quickbooks_config_missing",
                trace_id=self._trace_id,
                missing_vars=missing,
            )
            raise ValueError(
                f"Missing required QuickBooks configuration: {', '.join(missing)}. "
                "Please set these environment variables."
            )

    def _register_tools(self) -> None:
        """Register all MCP tools."""

        @self.server.tool()
        async def qb_create_bill(
            vendor_id: str,
            line_items: List[Dict[str, Any]],
            due_date: str,
            currency: str = "USD",
            doc_number: Optional[str] = None,
            txn_date: Optional[str] = None,
            private_note: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Create a bill in QuickBooks.

            Args:
                vendor_id: QuickBooks Vendor ID
                line_items: List of line items with description, amount, quantity, unit_price
                due_date: Bill due date (YYYY-MM-DD)
                currency: Currency code (default: USD)
                doc_number: Optional document number
                txn_date: Optional transaction date (YYYY-MM-DD)
                private_note: Optional private note

            Returns:
                Bill creation result with bill_id, sync_token, total_amount, status
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "qb_create_bill_called",
                trace_id=trace_id,
                vendor_id=vendor_id,
                line_items_count=len(line_items),
            )

            try:
                # Validate request
                request = CreateBillRequest(
                    vendor_id=vendor_id,
                    line_items=[LineItem(**item) for item in line_items],
                    due_date=due_date,
                    currency=currency,
                    doc_number=doc_number,
                    txn_date=txn_date,
                    private_note=private_note,
                )

                # Get access token
                access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # Build payload
                payload = self._build_bill_payload(request)

                # Make API call with retry
                response = await self._make_request(
                    method="POST",
                    endpoint=f"/company/{self.realm_id}/bill",
                    json=payload,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                bill = response.get("Bill", {})
                result = CreateBillResponse(
                    bill_id=bill.get("Id", ""),
                    sync_token=bill.get("SyncToken", "0"),
                    total_amount=bill.get("TotalAmt", 0),
                    status=bill.get("Balance", "Due"),
                    vendor_ref=bill.get("VendorRef", {}).get("value", ""),
                    doc_number=bill.get("DocNumber"),
                    due_date=bill.get("DueDate", due_date),
                    created_at=bill.get("MetaData", {}).get("CreateTime", datetime.now(timezone.utc).isoformat()),
                )

                logger.info(
                    "qb_create_bill_successful",
                    trace_id=trace_id,
                    bill_id=result.bill_id,
                    total_amount=result.total_amount,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "qb_create_bill_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def qb_get_vendor(vendor_name: str) -> Dict[str, Any]:
            """
            Query vendor information from QuickBooks.

            Args:
                vendor_name: Vendor name to search for

            Returns:
                Vendor information with vendor_id, display_name, email, phone, balance
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "qb_get_vendor_called",
                trace_id=trace_id,
                vendor_name=vendor_name,
            )

            try:
                # Get access token
                access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # Build query (escape single quotes)
                escaped_name = vendor_name.replace("'", "''")
                query = f"SELECT * FROM Vendor WHERE DisplayName LIKE '%{escaped_name}%' MAXRESULTS 10"

                # Make API call
                response = await self._make_request(
                    method="GET",
                    endpoint=f"/company/{self.realm_id}/query",
                    params={"query": query},
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                vendors = response.get("QueryResponse", {}).get("Vendor", [])
                if not vendors:
                    logger.warning(
                        "qb_get_vendor_no_results",
                        trace_id=trace_id,
                        vendor_name=vendor_name,
                    )
                    return {"error": f"No vendor found matching '{vendor_name}'"}

                # Return first match
                vendor = vendors[0]
                result = GetVendorResponse(
                    vendor_id=vendor.get("Id", ""),
                    display_name=vendor.get("DisplayName", ""),
                    email=vendor.get("PrimaryEmailAddr", {}).get("Address") if vendor.get("PrimaryEmailAddr") else None,
                    phone=vendor.get("PrimaryPhone", {}).get("FreeFormNumber") if vendor.get("PrimaryPhone") else None,
                    balance=vendor.get("Balance", 0),
                    active=vendor.get("Active", True),
                )

                logger.info(
                    "qb_get_vendor_successful",
                    trace_id=trace_id,
                    vendor_id=result.vendor_id,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "qb_get_vendor_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def qb_create_vendor(
            display_name: str,
            email: Optional[str] = None,
            phone: Optional[str] = None,
            given_name: Optional[str] = None,
            family_name: Optional[str] = None,
            company_name: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Create a new vendor in QuickBooks.

            Args:
                display_name: Vendor display name (required)
                email: Vendor email address
                phone: Vendor phone number
                given_name: Contact first name
                family_name: Contact last name
                company_name: Company name

            Returns:
                Vendor creation result with vendor_id, display_name, sync_token
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "qb_create_vendor_called",
                trace_id=trace_id,
                display_name=display_name,
            )

            try:
                # Get access token
                access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # Build payload
                payload: Dict[str, Any] = {
                    "DisplayName": display_name,
                    "Active": True,
                }

                if email:
                    payload["PrimaryEmailAddr"] = {"Address": email}
                if phone:
                    payload["PrimaryPhone"] = {"FreeFormNumber": phone}
                if given_name or family_name:
                    payload["GivenName"] = given_name
                    payload["FamilyName"] = family_name
                if company_name:
                    payload["CompanyName"] = company_name

                # Make API call
                response = await self._make_request(
                    method="POST",
                    endpoint=f"/company/{self.realm_id}/vendor",
                    json=payload,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                vendor = response.get("Vendor", {})
                result = CreateVendorResponse(
                    vendor_id=vendor.get("Id", ""),
                    display_name=vendor.get("DisplayName", ""),
                    sync_token=vendor.get("SyncToken", "0"),
                    created_at=vendor.get("MetaData", {}).get("CreateTime", datetime.now(timezone.utc).isoformat()),
                    active=vendor.get("Active", True),
                )

                logger.info(
                    "qb_create_vendor_successful",
                    trace_id=trace_id,
                    vendor_id=result.vendor_id,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "qb_create_vendor_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def qb_get_bill(bill_id: str) -> Dict[str, Any]:
            """
            Retrieve bill details from QuickBooks.

            Args:
                bill_id: QuickBooks Bill ID

            Returns:
                Bill details with bill_id, sync_token, vendor_ref, total_amount, balance, status
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "qb_get_bill_called",
                trace_id=trace_id,
                bill_id=bill_id,
            )

            try:
                # Get access token
                access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # Make API call
                response = await self._make_request(
                    method="GET",
                    endpoint=f"/company/{self.realm_id}/bill/{bill_id}",
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                bill = response.get("Bill", {})
                result = GetBillResponse(
                    bill_id=bill.get("Id", ""),
                    sync_token=bill.get("SyncToken", "0"),
                    vendor_ref=bill.get("VendorRef", {}).get("value", ""),
                    total_amount=bill.get("TotalAmt", 0),
                    balance=bill.get("Balance", 0),
                    status="Void" if bill.get("PrivateNote", "").lower() == "void" else "Due",
                    due_date=bill.get("DueDate", ""),
                    txn_date=bill.get("TxnDate", ""),
                    line_items=bill.get("Line", []),
                )

                logger.info(
                    "qb_get_bill_successful",
                    trace_id=trace_id,
                    bill_id=result.bill_id,
                    total_amount=result.total_amount,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "qb_get_bill_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def qb_void_bill(bill_id: str) -> Dict[str, Any]:
            """
            Void a bill in QuickBooks.

            Args:
                bill_id: QuickBooks Bill ID

            Returns:
                Void result with bill_id, sync_token, status
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "qb_void_bill_called",
                trace_id=trace_id,
                bill_id=bill_id,
            )

            try:
                # Get access token
                access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # First, get the bill to get its sync_token
                bill_response = await self._make_request(
                    method="GET",
                    endpoint=f"/company/{self.realm_id}/bill/{bill_id}",
                    access_token=access_token,
                    trace_id=trace_id,
                )

                bill = bill_response.get("Bill", {})
                sync_token = bill.get("SyncToken", "0")

                # Build void payload
                payload = {
                    "Id": bill_id,
                    "SyncToken": sync_token,
                    "sparse": True,
                    "PrivateNote": "Void",
                }

                # Make void API call
                response = await self._make_request(
                    method="POST",
                    endpoint=f"/company/{self.realm_id}/bill/{bill_id}/void",
                    json=payload,
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                voided_bill = response.get("Bill", {})
                result = VoidBillResponse(
                    bill_id=voided_bill.get("Id", bill_id),
                    sync_token=voided_bill.get("SyncToken", sync_token),
                    status="Void",
                    voided_at=datetime.now(timezone.utc).isoformat(),
                )

                logger.info(
                    "qb_void_bill_successful",
                    trace_id=trace_id,
                    bill_id=result.bill_id,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "qb_void_bill_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def qb_list_accounts() -> Dict[str, Any]:
            """
            List all accounts from QuickBooks chart of accounts.

            Returns:
                List of accounts with account details
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "qb_list_accounts_called",
                trace_id=trace_id,
            )

            try:
                # Get access token
                access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # Make API call
                response = await self._make_request(
                    method="GET",
                    endpoint=f"/company/{self.realm_id}/account",
                    access_token=access_token,
                    trace_id=trace_id,
                )

                # Parse response
                accounts = response.get("QueryResponse", {}).get("Account", [])
                result = ListAccountsResponse(
                    accounts=accounts,
                    count=len(accounts),
                )

                logger.info(
                    "qb_list_accounts_successful",
                    trace_id=trace_id,
                    count=result.count,
                )

                return result.model_dump()

            except Exception as e:
                logger.error(
                    "qb_list_accounts_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

    def _build_bill_payload(self, request: CreateBillRequest) -> Dict[str, Any]:
        """
        Build QuickBooks bill creation payload.

        Args:
            request: CreateBillRequest model

        Returns:
            QuickBooks API payload
        """
        return {
            "VendorRef": {"value": request.vendor_id},
            "Line": [
                {
                    "Description": item.description,
                    "Amount": item.amount,
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "AccountBasedExpenseLineDetail": {
                        "Qty": item.quantity or 1,
                        "UnitPrice": item.unit_price or 0,
                        **(
                            {"AccountRef": {"value": item.account_ref}}
                            if item.account_ref
                            else {}
                        ),
                    },
                }
                for item in request.line_items
            ],
            "DueDate": request.due_date,
            "CurrencyRef": {"value": request.currency},
            **({"DocNumber": request.doc_number} if request.doc_number else {}),
            **({"TxnDate": request.txn_date} if request.txn_date else {}),
            **({"PrivateNote": request.private_note} if request.private_note else {}),
        }

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
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
        Make HTTP request to QuickBooks API with retry logic.

        Handles:
        - 429 Rate Limit: Exponential backoff
        - 401 Unauthorized: Refresh token and retry once

        Args:
            method: HTTP method
            endpoint: API endpoint
            access_token: OAuth access token
            trace_id: Trace ID for correlation
            json: Request body (for POST/PUT)
            params: Query parameters (for GET)

        Returns:
            API response as dict

        Raises:
            httpx.HTTPStatusError: If request fails after retries
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=f"{self.base_url}{endpoint}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=json,
                params=params,
            )

            logger.debug(
                "quickbooks_api_request",
                trace_id=trace_id,
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
            )

            # Handle 401 - refresh token and retry once
            if response.status_code == 401:
                logger.warning(
                    "quickbooks_401_refreshing_token",
                    trace_id=trace_id,
                )

                # Refresh token
                new_access_token = await self.token_manager.get_access_token(trace_id=trace_id)

                # Retry once
                retry_response = await client.request(
                    method=method,
                    url=f"{self.base_url}{endpoint}",
                    headers={
                        "Authorization": f"Bearer {new_access_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=json,
                    params=params,
                )

                if retry_response.status_code == 401:
                    logger.error(
                        "quickbooks_401_after_refresh",
                        trace_id=trace_id,
                    )
                    raise httpx.HTTPStatusError(
                        "Authentication failed after token refresh",
                        request=response.request,
                        response=retry_response,
                    )

                return retry_response.json()

            # Handle rate limiting (429)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                logger.warning(
                    "quickbooks_rate_limited",
                    trace_id=trace_id,
                    retry_after_seconds=retry_after,
                )
                raise httpx.HTTPStatusError(
                    f"Rate limited. Retry after {retry_after} seconds",
                    request=response.request,
                    response=response,
                )

            # Raise for other errors
            response.raise_for_status()

            return response.json()

    async def run(self) -> None:
        """Run the MCP server using stdio transport."""
        await self.initialize()
        
        logger.info(
            "quickbooks_mcp_server_starting",
            trace_id=self._trace_id,
            transport="stdio",
        )

        await self.server.run_stdio_async()

    async def smoke_test(self) -> bool:
        """
        Run smoke test to verify QuickBooks connectivity.

        Returns:
            True if test passes, False otherwise
        """
        trace_id = str(uuid.uuid4())
        logger.info(
            "quickbooks_smoke_test_started",
            trace_id=trace_id,
        )

        try:
            # Test token refresh
            access_token = await self.token_manager.get_access_token(trace_id=trace_id)
            if not access_token:
                logger.error(
                    "smoke_test_token_refresh_failed",
                    trace_id=trace_id,
                )
                return False

            # Test qb_list_accounts
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/company/{self.realm_id}/account",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "smoke_test_api_call_failed",
                        trace_id=trace_id,
                        status_code=response.status_code,
                    )
                    return False

                data = response.json()
                count = data.get("QueryResponse", {}).get("Account", [])
                logger.info(
                    "smoke_test_successful",
                    trace_id=trace_id,
                    accounts_count=len(count),
                )
                return True

        except Exception as e:
            logger.error(
                "smoke_test_failed",
                trace_id=trace_id,
                error=str(e),
            )
            return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point with smoke test support."""
    parser = argparse.ArgumentParser(
        description="QuickBooks MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run as MCP server
  python -m src.mcp_servers.quickbooks_mcp

  # Run smoke test
  python -m src.mcp_servers.quickbooks_mcp --smoke-test

Environment Variables:
  QB_CLIENT_ID          QuickBooks OAuth client ID
  QB_CLIENT_SECRET      QuickBooks OAuth client secret
  QB_REALM_ID           QuickBooks company ID
  QB_REFRESH_TOKEN      OAuth refresh token
  QB_REFRESH_TOKEN_FILE Path to file containing refresh token
  QB_SANDBOX            Use sandbox (default: true)
        """,
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run smoke test to verify QuickBooks connectivity",
    )

    args = parser.parse_args()

    # Load .env file explicitly (for smoke tests)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    async def run_smoke_test():
        """Run smoke test asynchronously."""
        try:
            server = QuickBooksMCPServer()
            await server.initialize()
        except ValueError as e:
            # Graceful error for missing credentials
            print(f"QB: ✗ {str(e)}")
            exit(1)
        result = await server.smoke_test()

        if result:
            print("QB: ✓")
            exit(0)
        else:
            print("QB: ✗ Smoke test failed")
            exit(1)

    async def run_server():
        """Run MCP server asynchronously."""
        try:
            server = QuickBooksMCPServer()
            await server.initialize()
        except ValueError as e:
            # Graceful error for missing credentials
            logger.error("quickbooks_mcp_startup_failed", error=str(e))
            print(f"Error: {str(e)}", file=sys.stderr)
            exit(1)
        await server.run()

    if args.smoke_test:
        # Run smoke test
        asyncio.run(run_smoke_test())
    else:
        # Run MCP server
        asyncio.run(run_server())


if __name__ == "__main__":
    main()
