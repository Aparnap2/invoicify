"""
Environment Variables Secrets Adapter (Free Tier)
Simple adapter that reads from environment variables
"""

import os
import logging
from typing import Optional

from src.interfaces import SecretsAdapter

logger = logging.getLogger(__name__)


class EnvSecretsAdapter(SecretsAdapter):
    """
    Secrets adapter that reads from environment variables.
    Suitable for free tier and development environments.
    """

    def __init__(self):
        """Initialize environment secrets adapter."""
        logger.info("Initialized EnvSecretsAdapter (Free Tier Mode)")

    def get_secret(self, key: str) -> str:
        """
        Retrieve secret from environment variable.

        Args:
            key: Environment variable name

        Returns:
            Secret value

        Raises:
            KeyError: If environment variable not set
        """
        value = os.getenv(key)
        if value is None:
            raise KeyError(f"Environment variable not set: {key}")
        return value

    def get_database_url(self) -> str:
        """
        Get database connection URL from environment.

        Returns:
            Database URL string
        """
        return self.get_secret("DATABASE_URL")

    def get_ibm_api_key(self) -> str:
        """
        Get IBM Cloud API key from environment.

        Returns:
            API key string
        """
        return self.get_secret("IBM_CLOUD_API_KEY")

    def get_temporal_cert(self) -> str:
        """
        Get Temporal mTLS certificate from environment.

        Returns:
            Certificate content
        """
        # Try to read from file path or direct content
        cert_path = os.getenv("TEMPORAL_CERT_PATH")
        if cert_path and os.path.exists(cert_path):
            with open(cert_path, "r") as f:
                return f.read()

        # Try direct environment variable
        return self.get_secret("TEMPORAL_CERT")
