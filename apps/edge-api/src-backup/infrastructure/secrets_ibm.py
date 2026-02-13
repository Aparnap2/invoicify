"""
IBM Secrets Manager Adapter (Trial/Enterprise)
Uses IBM Cloud Secrets Manager for secure secret storage
"""

import logging
from typing import Optional

from src.interfaces import SecretsAdapter

logger = logging.getLogger(__name__)


class IBMSecretsAdapter(SecretsAdapter):
    """
    Secrets adapter using IBM Cloud Secrets Manager.
    Provides enterprise-grade secret management with auto-rotation.
    """

    def __init__(self, api_key: str, region: str = "us-south"):
        """
        Initialize IBM Secrets Manager adapter.

        Args:
            api_key: IBM Cloud API key
            region: IBM Cloud region
        """
        self.api_key = api_key
        self.region = region
        self._client = None
        logger.info("Initialized IBMSecretsAdapter (Enterprise/Trial Mode)")

    def _get_client(self):
        """Lazy initialization of IBM Secrets Manager client."""
        if self._client is None:
            try:
                from ibm_secrets_manager_sdk import SecretsManagerV2
                from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

                authenticator = IAMAuthenticator(self.api_key)
                self._client = SecretsManagerV2(authenticator=authenticator)
                self._client.set_service_url(
                    f"https://{self.region}.secrets-manager.appdomain.cloud"
                )
            except ImportError:
                logger.error("ibm-secrets-manager-sdk not installed")
                raise
        return self._client

    def get_secret(self, key: str) -> str:
        """
        Retrieve secret from IBM Secrets Manager.

        Args:
            key: Secret name/ID

        Returns:
            Secret value

        Raises:
            KeyError: If secret not found
        """
        try:
            client = self._get_client()
            response = client.get_secret(id=key)
            secret_data = response.get_result()

            # Extract secret value based on type
            secret_type = secret_data.get("secret_type")
            if secret_type == "arbitrary":
                return secret_data["secret_data"]["payload"]
            elif secret_type == "username_password":
                return secret_data["secret_data"]["password"]
            else:
                return str(secret_data["secret_data"])

        except Exception as e:
            logger.error(f"Failed to retrieve secret {key}: {e}")
            raise KeyError(f"Secret not found: {key}")

    def get_database_url(self) -> str:
        """
        Get database connection URL from Secrets Manager.

        Returns:
            Database URL string
        """
        # Try to get secret by name
        try:
            return self.get_secret("database-url")
        except KeyError:
            # Construct from components
            username = self.get_secret("db-username")
            password = self.get_secret("db-password")
            host = self.get_secret("db-host")
            port = self.get_secret("db-port")
            database = self.get_secret("db-name")

            return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    def get_ibm_api_key(self) -> str:
        """
        Get IBM Cloud API key from Secrets Manager.

        Returns:
            API key string
        """
        return self.get_secret("ibm-api-key")

    def get_temporal_cert(self) -> str:
        """
        Get Temporal mTLS certificate from Secrets Manager.

        Returns:
            Certificate content
        """
        return self.get_secret("temporal-mtls-cert")
