"""
Factory Pattern for Infrastructure Adapters
Decides which adapter to load based on environment configuration
"""

import os
import logging
from typing import Union

from src.interfaces import DatabaseAdapter, SecretsAdapter, VisionAdapter

logger = logging.getLogger(__name__)


def get_database_adapter() -> DatabaseAdapter:
    """
    Factory function to get database adapter.

    Returns:
        DatabaseAdapter: Configured database adapter

    Environment Variables:
        DB_MODE: 'free' or 'trial' (default: 'free')
        DATABASE_URL: PostgreSQL connection URL
        IBM_DB_CERT_PATH: Path to SSL certificate (for trial mode)
    """
    mode = os.getenv("DB_MODE", "free").lower()

    if mode == "trial":
        logger.info("🚀 Booting in Enterprise Trial Mode (IBM Hyper Protect)")

        from src.infrastructure.db_ibm_hyper import HyperProtectAdapter

        connection_url = os.getenv("DATABASE_URL")
        if not connection_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Get SSL certificate paths for FIPS compliance
        ssl_cert_path = os.getenv("IBM_DB_CERT_PATH")
        ssl_key_path = os.getenv("IBM_DB_KEY_PATH")
        ssl_root_cert_path = os.getenv("IBM_DB_ROOT_CERT_PATH")

        adapter = HyperProtectAdapter(
            connection_url=connection_url,
            ssl_cert_path=ssl_cert_path,
            ssl_key_path=ssl_key_path,
            ssl_root_cert_path=ssl_root_cert_path,
        )

    else:
        logger.info("🌱 Booting in Free Mode (Supabase/Standard PostgreSQL)")

        from src.infrastructure.db_postgres import PostgresAdapter

        connection_url = os.getenv("DATABASE_URL")
        if not connection_url:
            raise ValueError("DATABASE_URL environment variable not set")

        adapter = PostgresAdapter(connection_url=connection_url)

    return adapter


def get_secrets_adapter() -> SecretsAdapter:
    """
    Factory function to get secrets adapter.

    Returns:
        SecretsAdapter: Configured secrets adapter

    Environment Variables:
        SECRET_PROVIDER: 'env' or 'ibm_sm' (default: 'env')
        IBM_CLOUD_API_KEY: Required for IBM Secrets Manager
    """
    provider = os.getenv("SECRET_PROVIDER", "env").lower()

    if provider == "ibm_sm":
        logger.info("🔐 Using IBM Secrets Manager (Enterprise/Trial)")

        from src.infrastructure.secrets_ibm import IBMSecretsAdapter

        api_key = os.getenv("IBM_CLOUD_API_KEY")
        if not api_key:
            raise ValueError("IBM_CLOUD_API_KEY environment variable not set")

        region = os.getenv("IBM_CLOUD_REGION", "us-south")
        adapter = IBMSecretsAdapter(api_key=api_key, region=region)

    else:
        logger.info("🔑 Using Environment Variables (Free Tier)")

        from src.infrastructure.secrets_env import EnvSecretsAdapter

        adapter = EnvSecretsAdapter()

    return adapter


def get_warehouse_adapter():
    """
    Factory function to get analytics warehouse adapter.

    Returns:
        WarehouseAdapter: Configured warehouse adapter

    Environment Variables:
        WAREHOUSE_TYPE: 'duckdb' or 'db2' (default: 'duckdb')
    """
    warehouse_type = os.getenv("WAREHOUSE_TYPE", "duckdb").lower()

    if warehouse_type == "db2":
        logger.info("📊 Using IBM Db2 Warehouse (Enterprise/Trial)")
        # TODO: Implement Db2WarehouseAdapter
        raise NotImplementedError("Db2 Warehouse adapter not yet implemented")
    else:
        logger.info("🦆 Using DuckDB + Parquet (Free Tier)")
        # TODO: Implement DuckDBAdapter
        raise NotImplementedError("DuckDB adapter not yet implemented")


# Convenience functions for dependency injection
def get_db() -> DatabaseAdapter:
    """Get configured database adapter (singleton pattern)."""
    if not hasattr(get_db, "_instance"):
        get_db._instance = get_database_adapter()
    return get_db._instance


def get_secrets() -> SecretsAdapter:
    """Get configured secrets adapter (singleton pattern)."""
    if not hasattr(get_secrets, "_instance"):
        get_secrets._instance = get_secrets_adapter()
    return get_secrets._instance


def get_vision_adapter() -> VisionAdapter:
    """
    Factory function to get vision/document extraction adapter.

    Returns:
        VisionAdapter: Configured vision adapter

    Environment Variables:
        VISION_MODE: 'docling', 'watson', or 'groq' (default: 'docling')
        VISION_API_KEY: API key for cloud providers (watson/groq)
        VISION_API_URL: Custom endpoint URL (optional)
    """
    mode = os.getenv("VISION_MODE", "docling").lower()

    if mode == "watson":
        logger.info("🔍 Using IBM Watson Discovery (Enterprise)")
        # TODO: Implement WatsonAdapter
        raise NotImplementedError("Watson Vision adapter not yet implemented")

    elif mode == "groq":
        logger.info("🔍 Using Groq Cloud Vision API")
        # TODO: Implement GroqAdapter
        raise NotImplementedError("Groq Vision adapter not yet implemented")

    else:
        logger.info("📄 Using IBM Docling (Local Document Understanding)")

        from src.infrastructure.vision_docling import DoclingAdapter

        adapter = DoclingAdapter()

    return adapter


def get_vision() -> VisionAdapter:
    """Get configured vision adapter (singleton pattern)."""
    if not hasattr(get_vision, "_instance"):
        get_vision._instance = get_vision_adapter()
    return get_vision._instance
