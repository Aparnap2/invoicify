"""
Azure SQL Client - Replaces Cloudflare D1

Usage:
    from db.sql import get_db
    
    db = await get_db()
    await db.execute("INSERT INTO invoices (id, tenant_id) VALUES (@id, @tenantId)", 
                     {"id": invoice_id, "tenantId": tenant_id})
"""

import os
from typing import Optional, Dict, Any, List
import structlog
import asyncio

logger = structlog.get_logger()

# Global connection pool
_pool: Optional[Any] = None


async def get_db():
    """
    Get database connection pool.
    
    Uses DefaultAzureCredential for managed identity in production,
    SQL authentication for local development with SQL Server.
    
    Returns:
        Database connection pool
    """
    global _pool
    
    if _pool is not None:
        return _pool
    
    import asyncpg
    
    # Local development with SQL Server Docker
    server = os.getenv("AZURE_SQL_SERVER", "localhost")
    database = os.getenv("AZURE_SQL_DATABASE", "invoicify")
    username = os.getenv("AZURE_SQL_USERNAME", "sa")
    password = os.getenv("AZURE_SQL_PASSWORD", "DevPass123!")
    port = int(os.getenv("AZURE_SQL_PORT", "1433"))
    
    # Build connection string
    # For Azure SQL: server.database.windows.net
    # For local: localhost
    if "database.windows.net" in server:
        # Production Azure SQL with managed identity
        # Use pyodbc with Azure AD authentication
        import pyodbc
        
        connection_string = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Authentication=ActiveDirectoryDefault;"
        )
        
        _pool = pyodbc.connect(connection_string, autocommit=True)
        logger.info("azure_sql_connected_managed_identity", server=server)
    else:
        # Local development with SQL Server Docker
        connection_string = (
            f"postgresql://{username}:{password}@{server}:{port}/{database}"
        )
        
        _pool = await asyncpg.create_pool(
            connection_string,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("sql_server_connected_local", server=server)
    
    return _pool


async def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute SQL query and return results.
    
    Args:
        query: SQL query with @param placeholders
        params: Query parameters
    
    Returns:
        List of result rows as dicts
    """
    db = await get_db()
    
    try:
        # Check if using asyncpg (PostgreSQL/local) or pyodbc (Azure SQL)
        if hasattr(db, 'acquire'):
            # asyncpg pool
            async with db.acquire() as conn:
                if params:
                    # Convert @param to $1, $2 style for PostgreSQL
                    converted_query = _convert_params(query, params)
                    rows = await conn.fetch(converted_query, *params.values())
                else:
                    rows = await conn.fetch(query)
                
                return [dict(row) for row in rows]
        else:
            # pyodbc connection
            cursor = db.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            return [dict(zip(columns, row)) for row in rows]
    
    except Exception as e:
        logger.error("query_failed", query=query, error=str(e))
        raise


async def execute_command(query: str, params: Optional[Dict[str, Any]] = None) -> int:
    """
    Execute SQL command (INSERT, UPDATE, DELETE) and return affected rows.
    
    Args:
        query: SQL command with @param placeholders
        params: Command parameters
    
    Returns:
        Number of affected rows
    """
    db = await get_db()
    
    try:
        if hasattr(db, 'acquire'):
            # asyncpg pool
            async with db.acquire() as conn:
                if params:
                    converted_query = _convert_params(query, params)
                    result = await conn.execute(converted_query, *params.values())
                else:
                    result = await conn.execute(query)
                
                # asyncpg returns status string like "INSERT 0 1"
                parts = result.split()
                return int(parts[-1]) if parts else 0
        else:
            # pyodbc connection
            cursor = db.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            db.commit()
            return cursor.rowcount
    
    except Exception as e:
        logger.error("command_failed", query=query, error=str(e))
        raise


def _convert_params(query: str, params: Dict[str, Any]) -> str:
    """
    Convert @param style to $1, $2 style for PostgreSQL.
    
    Args:
        query: SQL query with @param placeholders
        params: Query parameters
    
    Returns:
        Converted query
    """
    import re
    
    param_order = list(params.keys())
    
    for i, param in enumerate(param_order, 1):
        query = re.sub(rf'@{param}', f'${i}', query)
    
    return query


# ─────────────────────────────────────────────────────────────────────────────
# Schema initialization
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
-- Invoices table
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='invoices' and xtype='U')
CREATE TABLE invoices (
    id            UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    tenant_id     NVARCHAR(100) NOT NULL,
    blob_url      NVARCHAR(500),
    status        NVARCHAR(50) NOT NULL DEFAULT 'PENDING',
    extracted     NVARCHAR(MAX),  -- JSON
    trust_level   NVARCHAR(20),
    call_sid      NVARCHAR(100),
    created_at    DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    updated_at    DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
);

-- Tenants table
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tenants' and xtype='U')
CREATE TABLE tenants (
    id            NVARCHAR(100) PRIMARY KEY,
    name          NVARCHAR(200),
    config        NVARCHAR(MAX),  -- JSON
    created_at    DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
);

-- Indexes
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_invoices_tenant')
CREATE INDEX idx_invoices_tenant ON invoices(tenant_id);

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_invoices_status')
CREATE INDEX idx_invoices_status ON invoices(status);

-- Trigger to update updated_at
IF OBJECT_ID('dbo.trg_invoices_updated', 'TR') IS NULL
CREATE TRIGGER trg_invoices_updated ON invoices
AFTER UPDATE
AS
BEGIN
    UPDATE invoices SET updated_at = GETUTCDATE()
    WHERE id IN (SELECT id FROM inserted);
END;
"""


async def initialize_schema():
    """Initialize database schema."""
    logger.info("initializing_database_schema")
    
    # Split schema into individual statements
    statements = [s.strip() for s in SCHEMA.split(';') if s.strip()]
    
    for statement in statements:
        try:
            await execute_command(statement)
        except Exception as e:
            # Ignore "already exists" errors
            if "already exists" not in str(e).lower() and "exists" not in str(e).lower():
                logger.warning("schema_init_warning", statement=statement[:50], error=str(e))
    
    logger.info("database_schema_initialized")
