"""MCP server registry for LangGraph agent.

This module provides a single import point for loading all ERP tools
from MCP servers. It gracefully handles missing credentials by skipping
unavailable servers and logging warnings.

Usage:
    from src.mcp_servers.registry import get_erp_tools

    tools = await get_erp_tools()
    # tools is List[BaseTool] with qb_* and hs_* tools
"""

import os
from pathlib import Path
from typing import List

import structlog
from langchain_core.tools import BaseTool

logger = structlog.get_logger(__name__)

# Module-level cache for loaded tools
_cached_tools: List[BaseTool] | None = None


def _has_qb_credentials() -> bool:
    """Check if QuickBooks credentials are configured.

    Returns:
        True if all required QuickBooks OAuth credentials are present.

    Required environment variables:
        - QB_CLIENT_ID
        - QB_CLIENT_SECRET
        - QB_REFRESH_TOKEN
        - QB_REALM_ID
    """
    required = ["QB_CLIENT_ID", "QB_CLIENT_SECRET", "QB_REFRESH_TOKEN", "QB_REALM_ID"]
    return all(os.getenv(var) for var in required)


def _has_hs_credentials() -> bool:
    """Check if HubSpot credentials are configured.

    Returns:
        True if HubSpot Private App token is present.

    Required environment variables:
        - HUBSPOT_API_KEY
    """
    return bool(os.getenv("HUBSPOT_API_KEY"))


async def _load_quickbooks_tools() -> List[BaseTool]:
    """Load QuickBooks MCP tools.
    
    Returns:
        List of QuickBooks tools (qb_create_bill, qb_get_vendor, etc.)
        or empty list if server fails to load.
    """
    try:
        from langchain_mcp_adapters import MCPServer
        
        # Get the agent-core root directory
        agent_core_dir = Path(__file__).parent.parent.parent
        
        qb_server = MCPServer(
            name="quickbooks",
            command="uv",
            args=["run", "python", "-m", "src.mcp_servers.quickbooks_mcp"],
            cwd=str(agent_core_dir),
        )
        
        tools = await qb_server.list_tools()
        logger.info(
            "quickbooks_tools_loaded",
            tool_count=len(tools),
            tool_names=[tool.name for tool in tools],
        )
        return tools
        
    except ImportError:
        logger.warning(
            "langchain_mcp_adapters_not_installed",
            message="Install with: uv add langchain-mcp-adapters",
        )
        return []
    except Exception as e:
        logger.warning(
            "quickbooks_tools_load_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return []


async def _load_hubspot_tools() -> List[BaseTool]:
    """Load HubSpot MCP tools.

    Returns:
        List of HubSpot tools (hs_create_deal, hs_get_company, etc.)
        or empty list if server fails to load.
    """
    try:
        from langchain_mcp_adapters import MCPServer

        agent_core_dir = Path(__file__).parent.parent.parent

        hs_server = MCPServer(
            name="hubspot",
            command="uv",
            args=["run", "python", "-m", "src.mcp_servers.hubspot_mcp"],
            cwd=str(agent_core_dir),
        )

        tools = await hs_server.list_tools()
        logger.info(
            "hubspot_tools_loaded",
            tool_count=len(tools),
            tool_names=[tool.name for tool in tools],
        )
        return tools

    except ImportError:
        logger.warning("langchain_mcp_adapters_not_installed")
        return []
    except Exception as e:
        logger.warning("hubspot_tools_load_failed", error=str(e))
        return []


async def get_erp_tools() -> List[BaseTool]:
    """Load all available ERP tools from MCP servers.

    This function:
    1. Checks for QuickBooks credentials and loads QB tools if present
    2. Checks for HubSpot credentials and loads HS tools if present
    3. Merges both tool lists into a single list
    4. Gracefully degrades if credentials missing (logs warning, skips tools)

    Returns:
        Merged list of LangChain tools from QuickBooks and HubSpot.
        Returns empty list if no credentials are configured.

    Example:
        >>> from src.mcp_servers.registry import get_erp_tools
        >>> tools = await get_erp_tools()
        >>> print(f"Loaded {len(tools)} ERP tools")
        Loaded 12 ERP tools
    """
    global _cached_tools

    # Return cached tools if available
    if _cached_tools is not None:
        logger.debug("returning_cached_erp_tools", tool_count=len(_cached_tools))
        return _cached_tools

    tools: List[BaseTool] = []

    # Load QuickBooks tools (if credentials present)
    if _has_qb_credentials():
        logger.info("quickbooks_credentials_found", loading=True)
        qb_tools = await _load_quickbooks_tools()
        tools.extend(qb_tools)
    else:
        logger.warning(
            "quickbooks_credentials_missing",
            skip=True,
            required_vars=["QB_CLIENT_ID", "QB_CLIENT_SECRET", "QB_REFRESH_TOKEN", "QB_REALM_ID"],
        )

    # Load HubSpot tools (if credentials present)
    if _has_hs_credentials():
        logger.info("hubspot_credentials_found", loading=True)
        hs_tools = await _load_hubspot_tools()
        tools.extend(hs_tools)
    else:
        logger.warning(
            "hubspot_credentials_missing",
            skip=True,
            required_vars=["HUBSPOT_API_KEY"],
        )

    # Cache the loaded tools
    _cached_tools = tools

    logger.info(
        "erp_tools_loaded_complete",
        total_count=len(tools),
        quickbooks_count=len([t for t in tools if t.name.startswith("qb_")]),
        hubspot_count=len([t for t in tools if t.name.startswith("hs_")]),
    )

    return tools


def clear_cache() -> None:
    """Clear the cached tools.
    
    Useful for testing or when credentials change at runtime.
    """
    global _cached_tools
    _cached_tools = None
    logger.debug("erp_tools_cache_cleared")
