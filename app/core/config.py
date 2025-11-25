"""
Application configuration settings.
"""

import os
from typing import List, Optional

from pydantic import field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Basic application settings
    PROJECT_NAME: str = "AP Intake & Validation"
    PROJECT_DESCRIPTION: str = "Transform emailed PDF invoices into validated, structured bills"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALLOWED_HOSTS: List[str] = ["*"]

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string."""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600
    DATABASE_POOL_PRE_PING: bool = True

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # Storage
    STORAGE_TYPE: str = "local"  # local, s3, r2, supabase
    STORAGE_PATH: str = "./storage"

    # Enhanced Local Storage Configuration
    STORAGE_COMPRESSION_ENABLED: bool = True
    STORAGE_COMPRESSION_TYPE: str = "gzip"  # gzip, lz4, none
    STORAGE_COMPRESSION_THRESHOLD: int = 1024  # bytes

    # AWS S3 configuration
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None

    # Docling configuration
    DOCLING_CONFIDENCE_THRESHOLD: float = 0.85
    DOCLING_MAX_PAGES: int = 50
    DOCLING_TIMEOUT: int = 30

    # LangGraph configuration
    LANGGRAPH_PERSIST_PATH: str = "./langgraph_storage"
    LANGGRAPH_STATE_TTL: int = 3600

    # LLM configuration for low-confidence patching
    OPENAI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "openrouter"  # openai, openrouter
    LLM_MODEL: str = "z-ai/glm-4.5-air:free"  # Default to OpenRouter model
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MAX_TOKENS: int = 1000
    LLM_TEMPERATURE: float = 0.1
    # OpenRouter app identification headers
    OPENROUTER_APP_NAME: str = "AP Intake & Validation"
    OPENROUTER_APP_URL: str = "https://github.com/ap-team/ap-intake"

    # Email configuration
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    GRAPH_TENANT_ID: Optional[str] = None
    GRAPH_CLIENT_ID: Optional[str] = None
    GRAPH_CLIENT_SECRET: Optional[str] = None

    # Email ingestion configuration
    EMAIL_INGESTION_ENABLED: bool = True
    EMAIL_MONITORING_INTERVAL_MINUTES: int = 60
    EMAIL_MAX_PROCESSING_DAYS: int = 7
    EMAIL_SECURITY_VALIDATION_ENABLED: bool = True
    EMAIL_AUTO_PROCESS_INVOICES: bool = True

    # Gmail Integration
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    GCP_PROJECT_ID: Optional[str] = None
    GMAIL_PUBSUB_TOPIC_NAME: str = "gmail-invoice-notifications"
    GMAIL_PUBSUB_SUBSCRIPTION_NAME: str = "gmail-invoice-subscription"
    GMAIL_WEBHOOK_URL: str = "http://localhost:8000/api/v1/gmail/gmail-webhook"

    # Export configuration
    EXPORT_PATH: str = "./exports"
    QUICKBOOKS_SANDBOX_CLIENT_ID: Optional[str] = None
    QUICKBOOKS_SANDBOX_CLIENT_SECRET: Optional[str] = None
    QUICKBOOKS_REDIRECT_URI: Optional[str] = "http://localhost:8000/api/v1/quickbooks/callback"
    QUICKBOOKS_ENVIRONMENT: str = "sandbox"  # sandbox or production
    QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN: Optional[str] = None
    XERO_SANDBOX_CLIENT_ID: Optional[str] = None
    XERO_SANDBOX_CLIENT_SECRET: Optional[str] = None

    # File handling
    MAX_FILE_SIZE_MB: int = 25
    ALLOWED_FILE_TYPES: List[str] = ["pdf", "jpeg", "jpg", "png"]

    @field_validator("ALLOWED_FILE_TYPES", mode="before")
    @classmethod
    def parse_file_types(cls, v):
        """Parse allowed file types from comma-separated string."""
        if isinstance(v, str):
            return [i.strip().lower() for i in v.split(",")]
        return v

    # Background worker configuration
    WORKER_CONCURRENCY: int = 4
    WORKER_PREFETCH_MULTIPLIER: int = 1
    WORKER_TASK_SOFT_TIME_LIMIT: int = 300
    WORKER_TASK_TIME_LIMIT: int = 600

    # Idempotency Settings
    IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600  # 24 hours
    IDEMPOTENCY_MAX_EXECUTIONS: int = 3
    IDEMPOTENCY_CLEANUP_HOURS: int = 1
    IDEMPOTENCY_CACHE_PREFIX: str = "idempotency"
    IDEMPOTENCY_ENABLE_METRICS: bool = True

    # Staging Settings
    STAGING_QUALITY_THRESHOLD: int = 70
    STAGING_APPROVAL_TIMEOUT_HOURS: int = 72
    STAGING_MAX_BATCH_SIZE: int = 1000
    STAGING_ENABLE_DIFF_TRACKING: bool = True
    STAGING_ENABLE_APPROVAL_CHAINS: bool = True
    STAGING_DEFAULT_PRIORITY: int = 5
    STAGING_COMPLIANCE_FLAGS: List[str] = ["SOX", "GDPR", "FINANCIAL"]
    STAGING_ENABLE_ROLLBACK: bool = True

    # Observability
    SENTRY_DSN: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # OpenTelemetry Configuration
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "ap-intake-api"
    OTEL_SERVICE_VERSION: str = VERSION
    JAEGER_ENDPOINT: Optional[str] = None
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_EXPORTER_OTLP_HEADERS: Optional[str] = None
    OTEL_RESOURCE_ATTRIBUTES: Optional[str] = None
    OTEL_PROPAGATORS: str = "tracecontext,baggage,b3"

    # Logging
    LOG_LEVEL: str = "INFO"

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    # UI configuration
    UI_HOST: str = "http://localhost:3000"
    API_HOST: str = "http://localhost:8000"

    # n8n integration configuration
    N8N_BASE_URL: str = "http://localhost:5678"
    N8N_API_KEY: Optional[str] = None
    N8N_USERNAME: Optional[str] = None
    N8N_PASSWORD: Optional[str] = None
    N8N_WEBHOOK_SECRET: Optional[str] = None
    N8N_TIMEOUT: int = 30
    N8N_MAX_RETRIES: int = 3
    N8N_RETRY_DELAY: float = 1.0
    N8N_ENCRYPTION_KEY: Optional[str] = None

    # n8n workflow IDs
    N8N_AP_WORKFLOW_ID: str = "ap_invoice_processing"
    N8N_AR_WORKFLOW_ID: str = "ar_invoice_processing"
    N8N_WORKING_CAPITAL_WORKFLOW_ID: str = "working_capital_analysis"
    N8N_CUSTOMER_ONBOARDING_WORKFLOW_ID: str = "customer_onboarding"
    N8N_EXCEPTION_HANDLING_WORKFLOW_ID: str = "exception_handling"
    N8N_WEEKLY_REPORT_WORKFLOW_ID: str = "weekly_report_generation"

    # Swappable Integration Configuration
    # Master switch for using swappable integration system
    USE_SWAPPABLE_INTEGRATION: bool = True

    # Integration system configuration
    INTEGRATION_DEFAULT_PROVIDER: str = "native"  # native, n8n, quickbooks
    INTEGRATION_FALLBACK_ENABLED: bool = True
    INTEGRATION_AUTO_FAILOVER: bool = True
    INTEGRATION_CIRCUIT_BREAKER_ENABLED: bool = True
    INTEGRATION_CIRCUIT_BREAKER_THRESHOLD: int = 5
    INTEGRATION_CIRCUIT_BREAKER_TIMEOUT: int = 300

    # Provider-specific configuration
    USE_N8N: bool = False  # Legacy switch for backward compatibility
    N8N_PROVIDER_ENABLED: bool = False
    N8N_PROVIDER_PRIORITY: int = 10
    N8N_PROVIDER_HEALTH_CHECK_INTERVAL: int = 60

    USE_NATIVE_PROVIDER: bool = True
    NATIVE_PROVIDER_ENABLED: bool = True
    NATIVE_PROVIDER_PRIORITY: int = 1
    NATIVE_PROVIDER_MAX_CONCURRENT_WORKFLOWS: int = 100

    # Integration monitoring and metrics
    INTEGRATION_MONITORING_ENABLED: bool = True
    INTEGRATION_METRICS_RETENTION_DAYS: int = 30
    INTEGRATION_HEALTH_CHECK_INTERVAL: int = 60

    @field_validator("INTEGRATION_DEFAULT_PROVIDER", mode="before")
    @classmethod
    def validate_default_provider(cls, v):
        """Validate default provider is supported."""
        valid_providers = ["native", "n8n", "quickbooks"]
        if v not in valid_providers:
            raise ValueError(f"Default provider must be one of {valid_providers}")
        return v

    @field_validator("INTEGRATION_CIRCUIT_BREAKER_THRESHOLD", mode="before")
    @classmethod
    def validate_circuit_breaker_threshold(cls, v):
        """Validate circuit breaker threshold."""
        if v < 1 or v > 100:
            raise ValueError("Circuit breaker threshold must be between 1 and 100")
        return v

    @field_validator("N8N_PROVIDER_PRIORITY", "NATIVE_PROVIDER_PRIORITY", mode="before")
    @classmethod
    def validate_provider_priority(cls, v):
        """Validate provider priority."""
        if v < 1 or v > 100:
            raise ValueError("Provider priority must be between 1 and 100")
        return v

    @field_validator("NATIVE_PROVIDER_MAX_CONCURRENT_WORKFLOWS", mode="before")
    @classmethod
    def validate_max_concurrent_workflows(cls, v):
        """Validate max concurrent workflows."""
        if v < 1 or v > 1000:
            raise ValueError("Max concurrent workflows must be between 1 and 1000")
        return v

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # Ignore extra fields in .env
    )


# Create settings instance
settings = Settings()