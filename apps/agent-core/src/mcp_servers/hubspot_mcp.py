"""HubSpot MCP Server — Private App token authentication.

This module implements a production-grade Model Context Protocol (MCP) server
for HubSpot CRM API integration using static Private App tokens.

Features:
- Private App token authentication (no OAuth dance, no JWT, no expiry)
- REST API with Bearer token auth
- Exponential backoff for rate limiting (429)
- Structured logging with trace_id correlation
- Typed I/O models using Pydantic v2
- httpx for async HTTP with timeout handling
- tenacity for retry logic

Tools (6 total):
1. hs_create_deal - Create deals in HubSpot CRM
2. hs_get_deal - Retrieve deal information
3. hs_update_deal - Update deal stage and properties
4. hs_get_company - Search for companies by name
5. hs_create_company - Create new companies
6. hs_search_deals - Search deals with query filters

Usage:
    # Run as MCP server
    python -m src.mcp_servers.hubspot_mcp

    # Run smoke test
    python -m src.mcp_servers.hubspot_mcp --smoke-test

Environment Variables:
    HUBSPOT_API_KEY - HubSpot Private App token (starts with pat-na1-...)

HubSpot Setup (How to get token):
    1. Go to app.hubspot.com → Settings → Integrations → Private Apps
    2. Click "Create a private app"
    3. Name your app (e.g., "Invoicify Integration")
    4. Configure scopes:
       - crm.objects.deals.read
       - crm.objects.deals.write
       - crm.objects.companies.read
       - crm.objects.companies.write
    5. Click "Create app"
    6. Copy the token (starts with pat-na1-...)
    7. Set HUBSPOT_API_KEY environment variable

References:
    - HubSpot CRM API: https://developers.hubspot.com/docs/api/crm/objects
    - Private Apps: https://developers.hubspot.com/docs/api/private-apps
    - Deals API: https://developers.hubspot.com/docs/api/crm/deals
    - Companies API: https://developers.hubspot.com/docs/api/crm/companies
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog
from mcp.server import FastMCP
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

HUBSPOT_BASE_URL = "https://api.hubapi.com"
HUBSPOT_API_VERSION = "v3"

# Rate limit handling
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic I/O Models
# ─────────────────────────────────────────────────────────────────────────────


class HubSpotDeal(BaseModel):
    """HubSpot Deal model."""

    deal_id: str = Field(..., description="HubSpot Deal ID")
    deal_name: str = Field(..., description="Deal name/title")
    stage: str = Field(..., description="Deal stage (e.g., appointmentscheduled, closedwon)")
    amount: Optional[float] = Field(default=None, description="Deal amount")
    close_date: Optional[str] = Field(default=None, description="Close date (YYYY-MM-DD)")
    company_id: Optional[str] = Field(default=None, description="Associated Company ID")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last modified timestamp")


class HubSpotCompany(BaseModel):
    """HubSpot Company model."""

    company_id: str = Field(..., description="HubSpot Company ID")
    name: str = Field(..., description="Company name")
    domain: Optional[str] = Field(default=None, description="Company website domain")
    phone: Optional[str] = Field(default=None, description="Company phone number")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last modified timestamp")


class HubSpotSearchResult(BaseModel):
    """HubSpot search result model."""

    results: List[Dict[str, Any]] = Field(default_factory=list, description="Search results")
    total: int = Field(default=0, description="Total number of results")
    has_more: bool = Field(default=False, description="Whether more results exist")
    next_offset: Optional[str] = Field(default=None, description="Pagination offset for next page")


class CreateDealRequest(BaseModel):
    """Request model for creating a deal."""

    deal_name: str = Field(..., description="Deal name/title")
    stage: str = Field(..., description="Deal stage")
    amount: Optional[float] = Field(default=None, description="Deal amount")
    close_date: Optional[str] = Field(default=None, description="Close date (YYYY-MM-DD)")
    company_id: Optional[str] = Field(default=None, description="Associated Company ID")


class CreateDealResponse(BaseModel):
    """Response model for deal creation."""

    deal_id: str = Field(..., description="HubSpot Deal ID")
    deal_name: str = Field(..., description="Deal name")
    stage: str = Field(..., description="Deal stage")
    amount: Optional[float] = Field(default=None, description="Deal amount")
    close_date: Optional[str] = Field(default=None, description="Close date")
    company_id: Optional[str] = Field(default=None, description="Associated Company ID")
    created_at: str = Field(..., description="Creation timestamp")


class GetDealRequest(BaseModel):
    """Request model for retrieving a deal."""

    deal_id: str = Field(..., description="HubSpot Deal ID")


class GetDealResponse(BaseModel):
    """Response model for deal retrieval."""

    deal_id: str = Field(..., description="HubSpot Deal ID")
    deal_name: str = Field(..., description="Deal name")
    stage: str = Field(..., description="Deal stage")
    amount: Optional[float] = Field(default=None, description="Deal amount")
    close_date: Optional[str] = Field(default=None, description="Close date")
    company_id: Optional[str] = Field(default=None, description="Associated Company ID")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last modified timestamp")


class UpdateDealRequest(BaseModel):
    """Request model for updating a deal."""

    deal_id: str = Field(..., description="HubSpot Deal ID")
    stage: Optional[str] = Field(default=None, description="New deal stage")
    amount: Optional[float] = Field(default=None, description="Updated amount")
    notes: Optional[str] = Field(default=None, description="Deal notes/description")
    close_date: Optional[str] = Field(default=None, description="Updated close date")


class UpdateDealResponse(BaseModel):
    """Response model for deal update."""

    deal_id: str = Field(..., description="HubSpot Deal ID")
    deal_name: str = Field(..., description="Deal name")
    stage: str = Field(..., description="Updated stage")
    amount: Optional[float] = Field(default=None, description="Updated amount")
    updated_at: str = Field(..., description="Update timestamp")
    success: bool = Field(default=True, description="Update success flag")


class GetCompanyRequest(BaseModel):
    """Request model for searching companies."""

    company_name: str = Field(..., description="Company name to search for")


class GetCompanyResponse(BaseModel):
    """Response model for company search."""

    company_id: str = Field(..., description="HubSpot Company ID")
    name: str = Field(..., description="Company name")
    domain: Optional[str] = Field(default=None, description="Company domain")
    phone: Optional[str] = Field(default=None, description="Company phone")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")


class CreateCompanyRequest(BaseModel):
    """Request model for creating a company."""

    name: str = Field(..., description="Company name")
    domain: Optional[str] = Field(default=None, description="Company website domain")
    phone: Optional[str] = Field(default=None, description="Company phone number")


class CreateCompanyResponse(BaseModel):
    """Response model for company creation."""

    company_id: str = Field(..., description="HubSpot Company ID")
    name: str = Field(..., description="Company name")
    domain: Optional[str] = Field(default=None, description="Company domain")
    phone: Optional[str] = Field(default=None, description="Company phone")
    created_at: str = Field(..., description="Creation timestamp")


class SearchDealsRequest(BaseModel):
    """Request model for searching deals."""

    query: str = Field(..., description="Search query string")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results to return")


class SearchDealsResponse(BaseModel):
    """Response model for deal search."""

    results: List[Dict[str, Any]] = Field(default_factory=list, description="Search results")
    total: int = Field(default=0, description="Total number of results")
    has_more: bool = Field(default=False, description="Whether more results exist")


# ─────────────────────────────────────────────────────────────────────────────
# HubSpot Client
# ─────────────────────────────────────────────────────────────────────────────


class HubSpotClient:
    """
    HubSpot CRM API Client.

    Features:
    - Private App token authentication (Bearer token)
    - Exponential backoff for 429 rate limits
    - Automatic retry on network errors
    - Structured logging with trace_id
    - Async HTTP with httpx

    Authentication:
    - Uses static Private App token (never expires)
    - Token passed as Bearer token in Authorization header
    - No OAuth flow, no JWT, no token refresh needed

    Rate Limits:
    - HubSpot API has rate limits per API key
    - 429 responses handled with exponential backoff
    - Max 5 retries with delays from 1s to 60s
    """

    def __init__(self, api_key: str, base_url: str = HUBSPOT_BASE_URL):
        """
        Initialize HubSpot Client.

        Args:
            api_key: HubSpot Private App token (starts with pat-na1-...)
            base_url: HubSpot API base URL

        Raises:
            ValueError: If api_key is missing or invalid
        """
        if not api_key or not api_key.startswith("pat-"):
            logger.warning(
                "hubspot_api_key_invalid",
                key_prefix=api_key[:8] if api_key else None,
                expected_prefix="pat-",
            )
            raise ValueError(
                "Invalid HubSpot API key. Must start with 'pat-'. "
                "Get your token from app.hubspot.com → Settings → Integrations → Private Apps"
            )

        self.api_key = api_key
        self.base_url = base_url
        self._trace_id: str = str(uuid.uuid4())

        logger.info(
            "hubspot_client_initialized",
            trace_id=self._trace_id,
            base_url=self.base_url,
            api_key_prefix=self.api_key[:8],
        )

    def _get_headers(self, trace_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get HTTP headers for API requests.

        Args:
            trace_id: Optional trace ID for correlation

        Returns:
            Headers dict with Authorization and Content-Type
        """
        current_trace_id = trace_id or self._trace_id
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Invoicify-HubSpot-MCP/1.0",
        }

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=INITIAL_RETRY_DELAY, max=MAX_RETRY_DELAY),
        reraise=True,
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to HubSpot API with retry logic.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., "/crm/v3/objects/deals")
            json: Optional JSON payload
            params: Optional query parameters
            trace_id: Optional trace ID for correlation

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: On HTTP errors (401, 404, etc.)
            httpx.NetworkError: On network errors (with retry)
            httpx.TimeoutException: On timeout (with retry)
        """
        current_trace_id = trace_id or self._trace_id
        url = f"{self.base_url}{endpoint}"

        logger.debug(
            "hubspot_request_started",
            trace_id=current_trace_id,
            method=method,
            url=url,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._get_headers(trace_id=current_trace_id),
                json=json,
                params=params,
            )

            # Handle 401 Unauthorized (invalid token)
            if response.status_code == 401:
                logger.error(
                    "hubspot_unauthorized",
                    trace_id=current_trace_id,
                    status_code=response.status_code,
                    response_body=response.text[:200],
                    hint="Invalid or expired Private App token. Check HUBSPOT_API_KEY env var.",
                )
                raise httpx.HTTPStatusError(
                    "Unauthorized: Invalid HubSpot Private App token",
                    request=response.request,
                    response=response,
                )

            # Handle 429 Rate Limit (will retry with backoff)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "unknown")
                logger.warning(
                    "hubspot_rate_limited",
                    trace_id=current_trace_id,
                    retry_after=retry_after,
                )
                raise httpx.NetworkError(
                    f"Rate limited by HubSpot. Retry-After: {retry_after}"
                )

            # Handle other errors
            if response.status_code >= 400:
                logger.error(
                    "hubspot_request_failed",
                    trace_id=current_trace_id,
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )
                response.raise_for_status()

            # Parse successful response
            if response.status_code == 204:
                return {}

            return response.json()

    async def create_deal(
        self,
        deal_name: str,
        stage: str,
        amount: Optional[float] = None,
        close_date: Optional[str] = None,
        company_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a deal in HubSpot CRM.

        Args:
            deal_name: Deal name/title
            stage: Deal stage (e.g., appointmentscheduled, closedwon)
            amount: Deal amount
            close_date: Close date (YYYY-MM-DD)
            company_id: Associated Company ID
            trace_id: Optional trace ID for correlation

        Returns:
            Created deal properties

        API: POST /crm/v3/objects/deals
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "hubspot_create_deal_called",
            trace_id=current_trace_id,
            deal_name=deal_name,
            stage=stage,
            amount=amount,
        )

        # Build HubSpot properties payload
        properties = {
            "dealname": deal_name,
            "dealstage": stage,
        }

        if amount is not None:
            properties["amount"] = str(amount)

        if close_date:
            properties["closedate"] = close_date

        if company_id:
            # Associate deal with company
            associations = {
                "companies": [{"id": company_id}]
            }
        else:
            associations = None

        payload: Dict[str, Any] = {"properties": properties}
        if associations:
            payload["associations"] = associations

        response = await self._make_request(
            method="POST",
            endpoint=f"/crm/{HUBSPOT_API_VERSION}/objects/deals",
            json=payload,
            trace_id=current_trace_id,
        )

        logger.info(
            "hubspot_deal_created",
            trace_id=current_trace_id,
            deal_id=response.get("id"),
            deal_name=deal_name,
        )

        return response

    async def get_deal(
        self,
        deal_id: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve a deal from HubSpot CRM.

        Args:
            deal_id: HubSpot Deal ID
            trace_id: Optional trace ID for correlation

        Returns:
            Deal properties

        API: GET /crm/v3/objects/deals/{id}
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "hubspot_get_deal_called",
            trace_id=current_trace_id,
            deal_id=deal_id,
        )

        response = await self._make_request(
            method="GET",
            endpoint=f"/crm/{HUBSPOT_API_VERSION}/objects/deals/{deal_id}",
            trace_id=current_trace_id,
        )

        logger.debug(
            "hubspot_deal_retrieved",
            trace_id=current_trace_id,
            deal_id=deal_id,
        )

        return response

    async def update_deal(
        self,
        deal_id: str,
        stage: Optional[str] = None,
        amount: Optional[float] = None,
        notes: Optional[str] = None,
        close_date: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a deal in HubSpot CRM.

        Args:
            deal_id: HubSpot Deal ID
            stage: New deal stage
            amount: Updated amount
            notes: Deal notes/description
            close_date: Updated close date
            trace_id: Optional trace ID for correlation

        Returns:
            Updated deal properties

        API: PATCH /crm/v3/objects/deals/{id}
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "hubspot_update_deal_called",
            trace_id=current_trace_id,
            deal_id=deal_id,
            stage=stage,
            amount=amount,
        )

        # Build properties payload (only include non-None values)
        properties: Dict[str, Any] = {}

        if stage:
            properties["dealstage"] = stage

        if amount is not None:
            properties["amount"] = str(amount)

        if notes:
            properties["description"] = notes

        if close_date:
            properties["closedate"] = close_date

        if not properties:
            logger.warning(
                "hubspot_update_deal_no_properties",
                trace_id=current_trace_id,
                deal_id=deal_id,
            )
            raise ValueError("At least one property (stage, amount, notes, close_date) must be provided")

        response = await self._make_request(
            method="PATCH",
            endpoint=f"/crm/{HUBSPOT_API_VERSION}/objects/deals/{deal_id}",
            json={"properties": properties},
            trace_id=current_trace_id,
        )

        logger.info(
            "hubspot_deal_updated",
            trace_id=current_trace_id,
            deal_id=deal_id,
        )

        return response

    async def get_company(
        self,
        company_name: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for a company by name in HubSpot CRM.

        Args:
            company_name: Company name to search for
            trace_id: Optional trace ID for correlation

        Returns:
            First matching company properties

        API: POST /crm/v3/objects/companies/search
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "hubspot_get_company_called",
            trace_id=current_trace_id,
            company_name=company_name,
        )

        # Build search query
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "name",
                            "operator": "CONTAINS_TOKEN",
                            "value": company_name,
                        }
                    ]
                }
            ],
            "limit": 10,
        }

        response = await self._make_request(
            method="POST",
            endpoint=f"/crm/{HUBSPOT_API_VERSION}/objects/companies/search",
            json=payload,
            trace_id=current_trace_id,
        )

        results = response.get("results", [])
        if not results:
            logger.warning(
                "hubspot_company_not_found",
                trace_id=current_trace_id,
                company_name=company_name,
            )
            return {"error": f"No companies found matching '{company_name}'"}

        # Return first match
        company = results[0]
        logger.debug(
            "hubspot_company_found",
            trace_id=current_trace_id,
            company_id=company.get("id"),
            company_name=company.get("properties", {}).get("name"),
        )

        return company

    async def create_company(
        self,
        name: str,
        domain: Optional[str] = None,
        phone: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a company in HubSpot CRM.

        Args:
            name: Company name
            domain: Company website domain
            phone: Company phone number
            trace_id: Optional trace ID for correlation

        Returns:
            Created company properties

        API: POST /crm/v3/objects/companies
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "hubspot_create_company_called",
            trace_id=current_trace_id,
            name=name,
            domain=domain,
        )

        # Build properties payload
        properties = {
            "name": name,
        }

        if domain:
            properties["domain"] = domain

        if phone:
            properties["phone"] = phone

        response = await self._make_request(
            method="POST",
            endpoint=f"/crm/{HUBSPOT_API_VERSION}/objects/companies",
            json={"properties": properties},
            trace_id=current_trace_id,
        )

        logger.info(
            "hubspot_company_created",
            trace_id=current_trace_id,
            company_id=response.get("id"),
            company_name=name,
        )

        return response

    async def search_deals(
        self,
        query: str,
        limit: int = 10,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for deals in HubSpot CRM.

        Args:
            query: Search query string
            limit: Maximum results to return (1-100)
            trace_id: Optional trace ID for correlation

        Returns:
            Search results with pagination info

        API: POST /crm/v3/objects/deals/search
        """
        current_trace_id = trace_id or self._trace_id

        logger.info(
            "hubspot_search_deals_called",
            trace_id=current_trace_id,
            query=query,
            limit=limit,
        )

        # Build search query
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "dealname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                }
            ],
            "limit": min(limit, 100),  # HubSpot max is 100
        }

        response = await self._make_request(
            method="POST",
            endpoint=f"/crm/{HUBSPOT_API_VERSION}/objects/deals/search",
            json=payload,
            trace_id=current_trace_id,
        )

        logger.info(
            "hubspot_deals_searched",
            trace_id=current_trace_id,
            query=query,
            total=len(response.get("results", [])),
        )

        return response


# ─────────────────────────────────────────────────────────────────────────────
# HubSpot MCP Server
# ─────────────────────────────────────────────────────────────────────────────


class HubSpotMCPServer:
    """
    HubSpot MCP Server.

    Provides 6 tools for HubSpot CRM integration:
    1. hs_create_deal - Create deals
    2. hs_get_deal - Retrieve deals
    3. hs_update_deal - Update deals
    4. hs_get_company - Search companies
    5. hs_create_company - Create companies
    6. hs_search_deals - Search deals

    Features:
    - Private App token authentication (no OAuth)
    - Rate limiting with exponential backoff (tenacity)
    - 401 error handling with clear logging
    - Structured logging with trace_id
    - Typed I/O with Pydantic
    """

    def __init__(self):
        """Initialize HubSpot MCP Server."""
        self.server = FastMCP("hubspot")
        self._trace_id: str = str(uuid.uuid4())

        # Load configuration
        self.api_key = os.getenv("HUBSPOT_API_KEY")

        # Validate required configuration
        self._validate_config()

        # Initialize HubSpot client
        self.client = HubSpotClient(api_key=self.api_key)

        # Register tools
        self._register_tools()

        logger.info(
            "hubspot_mcp_server_initialized",
            trace_id=self._trace_id,
            base_url=HUBSPOT_BASE_URL,
        )

    def _validate_config(self) -> None:
        """
        Validate required configuration.

        Raises:
            ValueError: If required configuration is missing
        """
        if not self.api_key:
            logger.error(
                "hubspot_config_missing",
                trace_id=self._trace_id,
                missing_var="HUBSPOT_API_KEY",
            )
            raise ValueError(
                "Missing HUBSPOT_API_KEY environment variable. "
                "Get your Private App token from app.hubspot.com → Settings → Integrations → Private Apps"
            )

    def _register_tools(self) -> None:
        """Register all MCP tools."""

        @self.server.tool()
        async def hs_create_deal(
            deal_name: str,
            stage: str,
            amount: Optional[float] = None,
            close_date: Optional[str] = None,
            company_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Create a deal in HubSpot CRM.

            Args:
                deal_name: Deal name/title
                stage: Deal stage (e.g., appointmentscheduled, closedwon, qualifiedtobuy)
                amount: Deal amount in USD
                close_date: Expected close date (YYYY-MM-DD)
                company_id: Associated Company ID (optional)

            Returns:
                Deal creation result with deal_id, deal_name, stage, amount

            Example stages:
                - appointmentscheduled
                - qualifiedtobuy
                - presentationcheduled
                - decisionmakerboughtin
                - closedwon
                - closedlost
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "hs_create_deal_called",
                trace_id=trace_id,
                deal_name=deal_name,
                stage=stage,
                amount=amount,
            )

            try:
                # Validate request
                request = CreateDealRequest(
                    deal_name=deal_name,
                    stage=stage,
                    amount=amount,
                    close_date=close_date,
                    company_id=company_id,
                )

                # Make API call
                response = await self.client.create_deal(
                    deal_name=request.deal_name,
                    stage=request.stage,
                    amount=request.amount,
                    close_date=request.close_date,
                    company_id=request.company_id,
                    trace_id=trace_id,
                )

                # Parse response
                properties = response.get("properties", {})
                result = CreateDealResponse(
                    deal_id=response.get("id", ""),
                    deal_name=properties.get("dealname", request.deal_name),
                    stage=properties.get("dealstage", request.stage),
                    amount=float(properties["amount"]) if properties.get("amount") else request.amount,
                    close_date=properties.get("closedate", request.close_date),
                    company_id=request.company_id,
                    created_at=response.get("createdAt", datetime.now(timezone.utc).isoformat()),
                )

                logger.info(
                    "hs_create_deal_successful",
                    trace_id=trace_id,
                    deal_id=result.deal_id,
                )

                return result.model_dump()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "hs_create_deal_http_error",
                    trace_id=trace_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise
            except Exception as e:
                logger.error(
                    "hs_create_deal_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def hs_get_deal(deal_id: str) -> Dict[str, Any]:
            """
            Retrieve a deal from HubSpot CRM.

            Args:
                deal_id: HubSpot Deal ID

            Returns:
                Deal information with deal_id, deal_name, stage, amount, close_date
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "hs_get_deal_called",
                trace_id=trace_id,
                deal_id=deal_id,
            )

            try:
                # Validate request
                request = GetDealRequest(deal_id=deal_id)

                # Make API call
                response = await self.client.get_deal(
                    deal_id=request.deal_id,
                    trace_id=trace_id,
                )

                # Parse response
                properties = response.get("properties", {})
                result = GetDealResponse(
                    deal_id=response.get("id", ""),
                    deal_name=properties.get("dealname", ""),
                    stage=properties.get("dealstage", ""),
                    amount=float(properties["amount"]) if properties.get("amount") else None,
                    close_date=properties.get("closedate"),
                    company_id=None,  # Would need association fetch
                    created_at=response.get("createdAt"),
                    updated_at=response.get("updatedAt"),
                )

                logger.debug(
                    "hs_get_deal_successful",
                    trace_id=trace_id,
                    deal_id=deal_id,
                )

                return result.model_dump()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "hs_get_deal_http_error",
                    trace_id=trace_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise
            except Exception as e:
                logger.error(
                    "hs_get_deal_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def hs_update_deal(
            deal_id: str,
            stage: Optional[str] = None,
            amount: Optional[float] = None,
            notes: Optional[str] = None,
            close_date: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Update a deal in HubSpot CRM.

            Args:
                deal_id: HubSpot Deal ID
                stage: New deal stage (optional)
                amount: Updated amount (optional)
                notes: Deal notes/description (optional)
                close_date: Updated close date (optional)

            Returns:
                Updated deal information with deal_id, stage, amount, updated_at
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "hs_update_deal_called",
                trace_id=trace_id,
                deal_id=deal_id,
                stage=stage,
                amount=amount,
            )

            try:
                # Validate request
                request = UpdateDealRequest(
                    deal_id=deal_id,
                    stage=stage,
                    amount=amount,
                    notes=notes,
                    close_date=close_date,
                )

                # Make API call
                response = await self.client.update_deal(
                    deal_id=request.deal_id,
                    stage=request.stage,
                    amount=request.amount,
                    notes=request.notes,
                    close_date=request.close_date,
                    trace_id=trace_id,
                )

                # Parse response
                properties = response.get("properties", {})
                result = UpdateDealResponse(
                    deal_id=response.get("id", ""),
                    deal_name=properties.get("dealname", ""),
                    stage=properties.get("dealstage", stage or ""),
                    amount=float(properties["amount"]) if properties.get("amount") else amount,
                    updated_at=response.get("updatedAt", datetime.now(timezone.utc).isoformat()),
                    success=True,
                )

                logger.info(
                    "hs_update_deal_successful",
                    trace_id=trace_id,
                    deal_id=deal_id,
                )

                return result.model_dump()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "hs_update_deal_http_error",
                    trace_id=trace_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise
            except Exception as e:
                logger.error(
                    "hs_update_deal_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def hs_get_company(company_name: str) -> Dict[str, Any]:
            """
            Search for a company by name in HubSpot CRM.

            Args:
                company_name: Company name to search for

            Returns:
                Company information with company_id, name, domain, phone
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "hs_get_company_called",
                trace_id=trace_id,
                company_name=company_name,
            )

            try:
                # Validate request
                request = GetCompanyRequest(company_name=company_name)

                # Make API call
                response = await self.client.get_company(
                    company_name=request.company_name,
                    trace_id=trace_id,
                )

                # Check for error response
                if "error" in response:
                    logger.warning(
                        "hs_get_company_no_results",
                        trace_id=trace_id,
                        company_name=company_name,
                    )
                    return response

                # Parse response
                properties = response.get("properties", {})
                result = GetCompanyResponse(
                    company_id=response.get("id", ""),
                    name=properties.get("name", ""),
                    domain=properties.get("domain"),
                    phone=properties.get("phone"),
                    created_at=response.get("createdAt"),
                )

                logger.debug(
                    "hs_get_company_successful",
                    trace_id=trace_id,
                    company_id=result.company_id,
                )

                return result.model_dump()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "hs_get_company_http_error",
                    trace_id=trace_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise
            except Exception as e:
                logger.error(
                    "hs_get_company_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def hs_create_company(
            name: str,
            domain: Optional[str] = None,
            phone: Optional[str] = None,
        ) -> Dict[str, Any]:
            """
            Create a company in HubSpot CRM.

            Args:
                name: Company name
                domain: Company website domain (optional)
                phone: Company phone number (optional)

            Returns:
                Company creation result with company_id, name, domain, phone
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "hs_create_company_called",
                trace_id=trace_id,
                name=name,
                domain=domain,
            )

            try:
                # Validate request
                request = CreateCompanyRequest(
                    name=name,
                    domain=domain,
                    phone=phone,
                )

                # Make API call
                response = await self.client.create_company(
                    name=request.name,
                    domain=request.domain,
                    phone=request.phone,
                    trace_id=trace_id,
                )

                # Parse response
                properties = response.get("properties", {})
                result = CreateCompanyResponse(
                    company_id=response.get("id", ""),
                    name=properties.get("name", request.name),
                    domain=properties.get("domain", request.domain),
                    phone=properties.get("phone", request.phone),
                    created_at=response.get("createdAt", datetime.now(timezone.utc).isoformat()),
                )

                logger.info(
                    "hs_create_company_successful",
                    trace_id=trace_id,
                    company_id=result.company_id,
                )

                return result.model_dump()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "hs_create_company_http_error",
                    trace_id=trace_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise
            except Exception as e:
                logger.error(
                    "hs_create_company_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise

        @self.server.tool()
        async def hs_search_deals(
            query: str,
            limit: int = 10,
        ) -> Dict[str, Any]:
            """
            Search for deals in HubSpot CRM.

            Args:
                query: Search query string (matches deal name)
                limit: Maximum results to return (1-100, default: 10)

            Returns:
                Search results with list of deals and total count
            """
            trace_id = str(uuid.uuid4())
            logger.info(
                "hs_search_deals_called",
                trace_id=trace_id,
                query=query,
                limit=limit,
            )

            try:
                # Validate request
                request = SearchDealsRequest(query=query, limit=limit)

                # Make API call
                response = await self.client.search_deals(
                    query=request.query,
                    limit=request.limit,
                    trace_id=trace_id,
                )

                # Parse response
                results = response.get("results", [])
                result = SearchDealsResponse(
                    results=results,
                    total=len(results),
                    has_more=response.get("hasMore", False),
                )

                logger.info(
                    "hs_search_deals_successful",
                    trace_id=trace_id,
                    query=query,
                    total=result.total,
                )

                return result.model_dump()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "hs_search_deals_http_error",
                    trace_id=trace_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise
            except Exception as e:
                logger.error(
                    "hs_search_deals_failed",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────


async def run_smoke_test() -> bool:
    """
    Run smoke test for HubSpot MCP Server.

    Test scenario:
    1. Create test company "Invoicify Test Vendor"
    2. Create test deal "Test Invoice INV-SMOKE-001"
    3. Update deal stage to "closedwon"
    4. Print "HS: ✓" or "HS: ✗ <error>"

    Returns:
        True if all tests pass, False otherwise
    """
    trace_id = str(uuid.uuid4())
    logger.info(
        "hubspot_smoke_test_started",
        trace_id=trace_id,
    )

    # Check for API key
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        logger.error(
            "hubspot_smoke_test_failed_no_api_key",
            trace_id=trace_id,
        )
        print("HS: ✗ Missing HUBSPOT_API_KEY environment variable")
        return False

    try:
        # Initialize client
        client = HubSpotClient(api_key=api_key)

        # Step 1: Create test company
        print("HS: Creating test company 'Invoicify Test Vendor'...")
        company_response = await client.create_company(
            name="Invoicify Test Vendor",
            domain="invoicify-test.local",
            trace_id=trace_id,
        )
        company_id = company_response.get("id")
        print(f"HS: ✓ Company created (ID: {company_id})")

        # Step 2: Create test deal
        deal_name = f"Test Invoice INV-SMOKE-{uuid.uuid4().hex[:8].upper()}"
        print(f"HS: Creating test deal '{deal_name}'...")
        deal_response = await client.create_deal(
            deal_name=deal_name,
            stage="appointmentscheduled",
            amount=100.00,
            close_date="2026-03-15",
            company_id=company_id,
            trace_id=trace_id,
        )
        deal_id = deal_response.get("id")
        print(f"HS: ✓ Deal created (ID: {deal_id})")

        # Step 3: Update deal stage to closedwon
        print(f"HS: Updating deal stage to 'closedwon'...")
        update_response = await client.update_deal(
            deal_id=deal_id,
            stage="closedwon",
            trace_id=trace_id,
        )
        print(f"HS: ✓ Deal updated (ID: {deal_id})")

        # Success
        print("HS: ✓")
        logger.info(
            "hubspot_smoke_test_passed",
            trace_id=trace_id,
            company_id=company_id,
            deal_id=deal_id,
        )
        return True

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {str(e)[:100]}"
        print(f"HS: ✗ {error_msg}")
        logger.error(
            "hubspot_smoke_test_failed_http_error",
            trace_id=trace_id,
            status_code=e.response.status_code,
            error=str(e),
        )
        return False

    except Exception as e:
        error_msg = str(e)[:100]
        print(f"HS: ✗ {error_msg}")
        logger.error(
            "hubspot_smoke_test_failed",
            trace_id=trace_id,
            error=str(e),
        )
        return False


def main() -> None:
    """
    CLI entry point for HubSpot MCP Server.

    Usage:
        python -m src.mcp_servers.hubspot_mcp              # Run as MCP server
        python -m src.mcp_servers.hubspot_mcp --smoke-test  # Run smoke test
    """
    parser = argparse.ArgumentParser(
        description="HubSpot MCP Server - Private App token authentication"
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run smoke test instead of MCP server",
    )
    args = parser.parse_args()

    # Load .env file explicitly (for smoke tests)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    if args.smoke_test:
        # Run smoke test
        success = asyncio.run(run_smoke_test())
        sys.exit(0 if success else 1)
    else:
        # Run MCP server
        logger.info(
            "hubspot_mcp_server_starting",
            mode="stdio",
        )
        server = HubSpotMCPServer()
        asyncio.run(server.server.run())


if __name__ == "__main__":
    main()
