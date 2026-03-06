"""Configuration management for Invoicify Agent Core.

Azure-native configuration. Uses Postgres, Azure Storage, Azure DI.
Environment variables map 1:1 to Azure Container Apps secrets.

Voice agent (Sarvam STT) and Edge API (Cloudflare Worker) removed.
CRM integration: HubSpot (replaces Salesforce).
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── LLM Configuration ─────────────────────────────────────────────────────
    # Default: OpenRouter free-tier (z-ai/glm-4.5-air runs Groq-speed, 0 cost)
    # Override with OPENAI_API_KEY + OPENAI_BASE_URL for any OpenAI-compatible API.
    llm_model: str = Field(
        default="z-ai/glm-4.5-air:free",
        description="LLM model identifier. Use OpenRouter free models by default.",
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenRouter API key (OPENAI_API_KEY env var). Required in production.",
    )
    openai_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenAI-compatible base URL. Default: OpenRouter.",
    )

    # Groq for fast JSON extraction (still free, 30 RPM)
    groq_api_key: Optional[str] = Field(
        default=None,
        description="Groq API key for Llama-3.3-70b JSON extraction step.",
    )

    # Extractor mode: 'fixture' | 'azure_di' | 'ollama' | 'sarvam'
    # Azure Container Apps production default: azure_di
    extractor_mode: str = Field(
        default="azure_di",
        description="""
Extraction backend selection:

- 'fixture'   → Hardcoded data (CI, no-key environments)
- 'azure_di'  → Azure Document Intelligence (international demos)
- 'sarvam'    → Sarvam Akshar OCR (Indian demos, Hindi/regional)
- 'ollama'    → Local Ollama (local dev, no API keys)
""",
    )

    # ── Azure Document Intelligence ───────────────────────────────────────────
    # Free tier: 500 pages/month. F0 plan.
    azure_document_intelligence_endpoint: Optional[str] = Field(
        default=None,
        description="Azure Document Intelligence endpoint URL.",
    )
    azure_document_intelligence_key: Optional[str] = Field(
        default=None,
        description="Azure Document Intelligence API key.",
    )

    # ── Azure Blob Storage ────────────────────────────────────────────────────
    # Replaces Cloudflare R2. Free: 5 GB LRS / month.
    azure_storage_connection_string: Optional[str] = Field(
        default=None,
        description="Azure Storage Account connection string.",
    )
    azure_storage_container: str = Field(
        default="invoices",
        description="Blob container name for invoice PDFs.",
    )

    # ── Azure Storage Queue ───────────────────────────────────────────────────
    # Replaces Upstash Redis queues + Cloudflare Queues. Free: unlimited messages.
    azure_queue_name: str = Field(
        default="invoice-processing",
        description="Storage Queue name for invoice processing jobs.",
    )
    azure_dlq_name: str = Field(
        default="invoice-dlq",
        description="Storage Queue name for dead-letter (failed) jobs.",
    )

    # ── Azure AI Search ───────────────────────────────────────────────────────
    # Replaces Qdrant vector store. Free: 50 MB, 3 indexes.
    azure_search_endpoint: Optional[str] = Field(
        default=None,
        description="Azure AI Search endpoint URL.",
    )
    azure_search_key: Optional[str] = Field(
        default=None,
        description="Azure AI Search admin key.",
    )
    azure_search_index: str = Field(
        default="invoices",
        description="Azure AI Search index name.",
    )

    # ── PostgreSQL (Azure Flexible Server) ───────────────────────────────────
    # Burstable B1MS: ~$0 for 12 months with free credits.
    database_url: str = Field(
        default="postgresql://invoicify:password@localhost:5432/invoicify",
        description="PostgreSQL connection URL.",
    )
    # LangGraph state persistence uses the same Postgres instance.
    checkpointer_url: str = Field(
        default="postgresql://invoicify:password@localhost:5432/invoicify",
        description="Postgres URL for LangGraph checkpointer.",
    )

    # ── Server Configuration ──────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001)
    debug: bool = Field(default=False)

    # ── Observability ─────────────────────────────────────────────────────────
    langfuse_public_key: Optional[str] = Field(default=None)
    langfuse_secret_key: Optional[str] = Field(default=None)
    langfuse_host: Optional[str] = Field(default="https://cloud.langfuse.com")

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")

    # ── Extraction Safety ─────────────────────────────────────────────────────
    extraction_confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for auto-approval.",
    )
    max_retries: int = Field(default=3, ge=0)

    # ── Trust Battery ─────────────────────────────────────────────────────────
    trust_battery_promotion_threshold: int = Field(default=50)
    trust_battery_core_threshold: int = Field(default=100)
    auto_approve_threshold_level1: float = Field(default=0)
    auto_approve_threshold_level2: float = Field(default=500)
    auto_approve_threshold_level3: float = Field(default=5000)

    # ── Strategic Mode ────────────────────────────────────────────────────────
    strategy_mode: str = Field(
        default="OPTIMIZE",
        description="SURVIVAL | GROWTH | OPTIMIZE",
    )
    safety_buffer: float = Field(default=10000)
    payroll_amount: float = Field(default=15000)
    payroll_date: str = Field(default="15")

    # ── QuickBooks Online ─────────────────────────────────────────────────────
    # OAuth 2.0 credentials for QBO API access
    # Get tokens: https://developer.intuit.com/app/developer/playground
    quickbooks_client_id: Optional[str] = Field(
        default=None,
        description="QuickBooks Online OAuth 2.0 Client ID",
    )
    quickbooks_client_secret: Optional[str] = Field(
        default=None,
        description="QuickBooks Online OAuth 2.0 Client Secret",
    )
    quickbooks_realm_id: Optional[str] = Field(
        default=None,
        description="QuickBooks Online Realm ID (Company ID)",
    )
    quickbooks_refresh_token: Optional[str] = Field(
        default=None,
        description="QuickBooks Online OAuth 2.0 Refresh Token",
    )
    quickbooks_sandbox: bool = Field(
        default=True,
        description="Use QuickBooks sandbox environment (true) or production (false)",
    )

    # ── HubSpot CRM ───────────────────────────────────────────────────────────
    # Private App token authentication (no OAuth, no JWT, token never expires)
    # Setup: app.hubspot.com → Settings → Integrations → Private Apps
    # 1. Create private app with scopes: crm.objects.deals.*, crm.objects.companies.*
    # 2. Copy token (starts with pat-na1-...)
    # 3. Set HUBSPOT_API_KEY env var
    hubspot_api_key: Optional[str] = Field(
        default=None,
        description="HubSpot Private App API token (never expires)",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return v.upper()

    @field_validator("strategy_mode")
    @classmethod
    def validate_strategy_mode(cls, v: str) -> str:
        valid = ["SURVIVAL", "GROWTH", "OPTIMIZE"]
        if v.upper() not in valid:
            raise ValueError(f"Invalid strategy mode: {v}. Must be one of {valid}")
        return v.upper()

    @field_validator("extractor_mode")
    @classmethod
    def validate_extractor_mode(cls, v: str) -> str:
        valid = ["fixture", "azure_di", "ollama", "sarvam"]
        if v.lower() not in valid:
            raise ValueError(f"Invalid extractor mode: {v}. Must be one of {valid}")
        return v.lower()

    @property
    def is_development(self) -> bool:
        return self.debug

    @property
    def is_survival_mode(self) -> bool:
        return self.strategy_mode == "SURVIVAL"

    @property
    def is_growth_mode(self) -> bool:
        return self.strategy_mode == "GROWTH"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
