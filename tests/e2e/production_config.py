#!/usr/bin/env python3
"""
Production E2E Test Configuration Loader.

Loads and validates all required environment variables for production
end-to-end testing with real Azure services, OpenRouter LLM, and local Docker containers.

Environment Variables Required:
    - Azure Document Intelligence (OCR)
    - Azure Blob Storage (PDF storage)
    - Azure Storage Queue (async processing)
    - OpenRouter API (LLM)
    - Local Docker services (Redis, Qdrant, Ollama)
    - Mockoon mocks (QuickBooks, Salesforce)

Usage:
    from tests.e2e.production_config import ProductionConfig, ConfigValidationError
    
    try:
        config = ProductionConfig.load()
        print(f"Azure Storage: {config.azure_storage_container}")
        print(f"LLM Model: {config.llm_model}")
    except ConfigValidationError as e:
        print(f"Configuration error: {e}")
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)


class ConfigValidationError(Exception):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, message: str, missing_vars: Optional[List[str]] = None):
        super().__init__(message)
        self.missing_vars = missing_vars or []


@dataclass
class AzureDocumentIntelligenceConfig:
    """Azure Document Intelligence (OCR) configuration."""

    endpoint: str
    key: str

    @classmethod
    def from_env(cls) -> "AzureDocumentIntelligenceConfig":
        """Load from environment variables."""
        missing = []
        endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        if not endpoint:
            missing.append("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")

        key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        if not key:
            missing.append("AZURE_DOCUMENT_INTELLIGENCE_KEY")

        if missing:
            raise ConfigValidationError(
                "Azure Document Intelligence configuration incomplete",
                missing_vars=missing,
            )

        return cls(endpoint=endpoint, key=key)


@dataclass
class AzureStorageConfig:
    """Azure Blob Storage configuration."""

    connection_string: str
    container_name: str

    @classmethod
    def from_env(cls) -> "AzureStorageConfig":
        """Load from environment variables."""
        missing = []
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            missing.append("AZURE_STORAGE_CONNECTION_STRING")

        container_name = os.getenv("AZURE_STORAGE_CONTAINER", "invoices")
        if not container_name:
            missing.append("AZURE_STORAGE_CONTAINER")

        if missing:
            raise ConfigValidationError(
                "Azure Storage configuration incomplete",
                missing_vars=missing,
            )

        return cls(connection_string=connection_string, container_name=container_name)


@dataclass
class AzureQueueConfig:
    """Azure Storage Queue configuration."""

    connection_string: str
    queue_name: str
    dlq_name: str

    @classmethod
    def from_env(cls) -> "AzureQueueConfig":
        """Load from environment variables."""
        missing = []
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            missing.append("AZURE_STORAGE_CONNECTION_STRING")

        queue_name = os.getenv("AZURE_QUEUE_NAME", "invoice-processing")
        dlq_name = os.getenv("AZURE_DLQ_NAME", "invoice-dlq")

        if missing:
            raise ConfigValidationError(
                "Azure Queue configuration incomplete",
                missing_vars=missing,
            )

        return cls(
            connection_string=connection_string,
            queue_name=queue_name,
            dlq_name=dlq_name,
        )


@dataclass
class OpenRouterConfig:
    """OpenRouter LLM configuration."""

    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        """Load from environment variables."""
        missing = []
        api_key = os.getenv("OPENAI_API_KEY")  # OpenRouter uses OPENAI_API_KEY
        if not api_key:
            missing.append("OPENAI_API_KEY")

        base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        model = os.getenv("LLM_MODEL", "z-ai/glm-4.5-air:free")

        if missing:
            raise ConfigValidationError(
                "OpenRouter LLM configuration incomplete",
                missing_vars=missing,
            )

        return cls(api_key=api_key, base_url=base_url, model=model)


@dataclass
class DockerServicesConfig:
    """Local Docker services configuration."""

    redis_host: str
    redis_port: int
    qdrant_host: str
    qdrant_port: int
    ollama_host: str
    ollama_port: int

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def qdrant_url(self) -> str:
        """Get Qdrant HTTP URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def ollama_url(self) -> str:
        """Get Ollama API URL."""
        return f"http://{self.ollama_host}:{self.ollama_port}"

    @classmethod
    def from_env(cls) -> "DockerServicesConfig":
        """Load from environment variables."""
        return cls(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
            ollama_host=os.getenv("OLLAMA_HOST", "localhost"),
            ollama_port=int(os.getenv("OLLAMA_PORT", "11434")),
        )


@dataclass
class MockoonConfig:
    """Mockoon mock services configuration."""

    quickbooks_url: str
    salesforce_url: str

    @classmethod
    def from_env(cls) -> "MockoonConfig":
        """Load from environment variables."""
        return cls(
            quickbooks_url=os.getenv("MOCKOON_QUICKBOOKS_URL", "http://localhost:3010"),
            salesforce_url=os.getenv("MOCKOON_SALESFORCE_URL", "http://localhost:3020"),
        )


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration for audit ledger."""

    database_url: str

    @property
    def is_postgres(self) -> bool:
        """Check if URL is PostgreSQL."""
        return self.database_url.startswith("postgresql://")

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load from environment variables."""
        missing = []
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            missing.append("DATABASE_URL")

        if missing:
            raise ConfigValidationError(
                "Database configuration incomplete",
                missing_vars=missing,
            )

        return cls(database_url=database_url)


@dataclass
class ProductionConfig:
    """
    Complete production E2E test configuration.

    Aggregates all service configurations and provides validation.

    Attributes:
        azure_di: Azure Document Intelligence config
        azure_storage: Azure Blob Storage config
        azure_queue: Azure Storage Queue config
        openrouter: OpenRouter LLM config
        docker_services: Local Docker services config
        mockoon: Mockoon mock services config
        database: PostgreSQL audit ledger config
    """

    azure_di: AzureDocumentIntelligenceConfig
    azure_storage: AzureStorageConfig
    azure_queue: AzureQueueConfig
    openrouter: OpenRouterConfig
    docker_services: DockerServicesConfig
    mockoon: MockoonConfig
    database: DatabaseConfig

    # Test settings
    test_timeout_seconds: int = 180  # 3 minutes max
    request_timeout_seconds: float = 60.0
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0

    @classmethod
    def load(cls, validate: bool = True) -> "ProductionConfig":
        """
        Load configuration from environment variables.

        Args:
            validate: If True, validate all required vars. Default True.

        Returns:
            ProductionConfig instance with all configurations.

        Raises:
            ConfigValidationError: If required configuration is missing.
        """
        missing_all = []

        # Try to load each config section
        try:
            azure_di = AzureDocumentIntelligenceConfig.from_env()
        except ConfigValidationError as e:
            missing_all.extend(e.missing_vars)
            azure_di = None

        try:
            azure_storage = AzureStorageConfig.from_env()
        except ConfigValidationError as e:
            missing_all.extend(e.missing_vars)
            azure_storage = None

        try:
            azure_queue = AzureQueueConfig.from_env()
        except ConfigValidationError as e:
            missing_all.extend(e.missing_vars)
            azure_queue = None

        try:
            openrouter = OpenRouterConfig.from_env()
        except ConfigValidationError as e:
            missing_all.extend(e.missing_vars)
            openrouter = None

        # Docker services and Mockoon have defaults, so they won't fail
        docker_services = DockerServicesConfig.from_env()
        mockoon = MockoonConfig.from_env()

        try:
            database = DatabaseConfig.from_env()
        except ConfigValidationError as e:
            missing_all.extend(e.missing_vars)
            database = None

        if validate and missing_all:
            raise ConfigValidationError(
                f"Production E2E test configuration incomplete. Missing {len(missing_all)} required variable(s).",
                missing_vars=missing_all,
            )

        # Override timeout settings from env
        test_timeout = int(os.getenv("E2E_TEST_TIMEOUT_SECONDS", "180"))
        request_timeout = float(os.getenv("E2E_REQUEST_TIMEOUT_SECONDS", "60.0"))
        retry_attempts = int(os.getenv("E2E_RETRY_ATTEMPTS", "3"))
        retry_delay = float(os.getenv("E2E_RETRY_DELAY_SECONDS", "1.0"))

        return cls(
            azure_di=azure_di or AzureDocumentIntelligenceConfig(
                endpoint="", key=""
            ),
            azure_storage=azure_storage
            or AzureStorageConfig(connection_string="", container_name=""),
            azure_queue=azure_queue
            or AzureQueueConfig(connection_string="", queue_name="", dlq_name=""),
            openrouter=openrouter or OpenRouterConfig(api_key="", base_url="", model=""),
            docker_services=docker_services,
            mockoon=mockoon,
            database=database or DatabaseConfig(database_url=""),
            test_timeout_seconds=test_timeout,
            request_timeout_seconds=request_timeout,
            retry_attempts=retry_attempts,
            retry_delay_seconds=retry_delay,
        )

    def validate_azure_services(self) -> List[str]:
        """
        Validate Azure service configurations.

        Returns:
            List of validation error messages (empty if all valid).
        """
        errors = []

        if not self.azure_di.endpoint or not self.azure_di.key:
            errors.append("Azure Document Intelligence endpoint and key required")

        if not self.azure_storage.connection_string:
            errors.append("Azure Storage connection string required")

        if not self.azure_queue.connection_string:
            errors.append("Azure Queue connection string required")

        return errors

    def validate_llm(self) -> List[str]:
        """
        Validate LLM configuration.

        Returns:
            List of validation error messages (empty if all valid).
        """
        errors = []

        if not self.openrouter.api_key:
            errors.append("OpenRouter API key required (OPENAI_API_KEY)")

        if not self.openrouter.model:
            errors.append("LLM model required (LLM_MODEL)")

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (for logging)."""
        return {
            "azure_di": {
                "endpoint": self.azure_di.endpoint[:50] + "..." if self.azure_di.endpoint else "",
                "key_set": bool(self.azure_di.key),
            },
            "azure_storage": {
                "container": self.azure_storage.container_name,
                "connection_string_set": bool(self.azure_storage.connection_string),
            },
            "azure_queue": {
                "queue_name": self.azure_queue.queue_name,
                "dlq_name": self.azure_queue.dlq_name,
            },
            "openrouter": {
                "base_url": self.openrouter.base_url,
                "model": self.openrouter.model,
                "key_set": bool(self.openrouter.api_key),
            },
            "docker_services": {
                "redis": self.docker_services.redis_url,
                "qdrant": self.docker_services.qdrant_url,
                "ollama": self.docker_services.ollama_url,
            },
            "mockoon": {
                "quickbooks": self.mockoon.quickbooks_url,
                "salesforce": self.mockoon.salesforce_url,
            },
            "database": {
                "url_set": bool(self.database.database_url),
                "is_postgres": self.database.is_postgres,
            },
            "test_settings": {
                "timeout_seconds": self.test_timeout_seconds,
                "request_timeout_seconds": self.request_timeout_seconds,
                "retry_attempts": self.retry_attempts,
                "retry_delay_seconds": self.retry_delay_seconds,
            },
        }

    def print_summary(self) -> None:
        """Print configuration summary to console."""
        print("\n" + "=" * 80)
        print("PRODUCTION E2E TEST CONFIGURATION")
        print("=" * 80)

        config_dict = self.to_dict()

        print("\n📦 AZURE SERVICES:")
        print(f"  Document Intelligence: {'✅' if config_dict['azure_di']['key_set'] else '❌'} {config_dict['azure_di']['endpoint']}")
        print(f"  Blob Storage:          {'✅' if config_dict['azure_storage']['connection_string_set'] else '❌'} Container: {config_dict['azure_storage']['container']}")
        print(f"  Storage Queue:         {'✅' if config_dict['azure_queue']['queue_name'] else '❌'} {config_dict['azure_queue']['queue_name']}")

        print("\n🤖 LLM (OpenRouter):")
        print(f"  Model:     {'✅' if config_dict['openrouter']['key_set'] else '❌'} {config_dict['openrouter']['model']}")
        print(f"  Base URL:  {config_dict['openrouter']['base_url']}")

        print("\n🐳 DOCKER SERVICES:")
        print(f"  Redis:   {config_dict['docker_services']['redis']}")
        print(f"  Qdrant:  {config_dict['docker_services']['qdrant']}")
        print(f"  Ollama:  {config_dict['docker_services']['ollama']}")

        print("\n🎭 MOCKOON MOCKS:")
        print(f"  QuickBooks:  {config_dict['mockoon']['quickbooks']}")
        print(f"  Salesforce:  {config_dict['mockoon']['salesforce']}")

        print("\n💾 DATABASE:")
        print(f"  PostgreSQL:  {'✅' if config_dict['database']['url_set'] else '❌'} Configured")

        print("\n⚙️  TEST SETTINGS:")
        print(f"  Timeout:         {config_dict['test_settings']['timeout_seconds']}s")
        print(f"  Request Timeout: {config_dict['test_settings']['request_timeout_seconds']}s")
        print(f"  Retry Attempts:  {config_dict['test_settings']['retry_attempts']}")

        print("=" * 80 + "\n")


def get_config() -> ProductionConfig:
    """
    Get production configuration with validation.

    Returns:
        ProductionConfig instance.

    Raises:
        ConfigValidationError: If configuration is invalid.
    """
    return ProductionConfig.load(validate=True)


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = get_config()
        config.print_summary()
        print("✅ Configuration loaded successfully!")
        sys.exit(0)
    except ConfigValidationError as e:
        print(f"❌ Configuration Error: {e}")
        if e.missing_vars:
            print("\nMissing environment variables:")
            for var in e.missing_vars:
                print(f"  - {var}")
            print("\nCopy .env.azure.example to .env and fill in the values.")
        sys.exit(1)
