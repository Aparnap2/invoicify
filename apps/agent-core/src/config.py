"""Configuration management for AI service."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration - Now using local Ollama by default
    llm_model: str = Field(
        default="ollama/ministral-3:3b",
        description="LLM model to use (ollama/ministral-3:3b, ollama/sam860/LFM2:2.6b)"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL"
    )
    embedding_model: str = Field(
        default="ollama/nomic-embed-text:latest",
        description="Embedding model for vector operations"
    )
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key (fallback)")

    # OCR Model - for document extraction
    ocr_model: Optional[str] = Field(default=None, description="OCR model for document extraction")

    # Server Configuration
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001)
    debug: bool = Field(default=False)

    # Database Configuration - Using local Postgres
    database_url: str = Field(
        default="postgresql://neo4j:password@localhost:5432/invoicify"
    )

    # Redis Configuration - For caching and queues
    redis_url: str = Field(default="redis://localhost:6379")

    # Neo4j Configuration - Knowledge graph for vendor relationships
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="founderos_secret")

    # LangGraph Checkpointer
    checkpointer_url: str = Field(
        default="postgresql://neo4j:password@localhost:5432/invoicify",
        description="Postgres URL for LangGraph state persistence"
    )

    # Langfuse Observability
    langfuse_public_key: Optional[str] = Field(default=None, description="Langfuse public key")
    langfuse_secret_key: Optional[str] = Field(default=None, description="Langfuse secret key")
    langfuse_host: Optional[str] = Field(default=None, description="Langfuse server URL")

    # Logging
    log_level: str = Field(default="INFO")

    # Extraction Settings
    extraction_confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for auto-approval",
    )
    max_retries: int = Field(default=3, ge=0)

    # Trust Battery Settings
    trust_battery_promotion_threshold: int = Field(
        default=50,
        description="Consecutive accurate decisions to promote trust level"
    )
    trust_battery_core_threshold: int = Field(
        default=100,
        description="Consecutive accurate decisions to reach Core level"
    )
    auto_approve_threshold_level1: float = Field(
        default=0,
        description="Auto-approve threshold for Level 1 (Probation)"
    )
    auto_approve_threshold_level2: float = Field(
        default=500,
        description="Auto-approve threshold for Level 2 (Standard)"
    )
    auto_approve_threshold_level3: float = Field(
        default=5000,
        description="Auto-approve threshold for Level 3 (Core)"
    )

    # Strategic Mode Settings
    strategy_mode: str = Field(
        default="OPTIMIZE",
        description="Company strategy mode: SURVIVAL, GROWTH, or OPTIMIZE"
    )
    safety_buffer: float = Field(
        default=10000,
        description="Minimum cash buffer to maintain"
    )
    payroll_amount: float = Field(
        default=15000,
        description="Upcoming payroll amount"
    )
    payroll_date: str = Field(
        default="15",
        description="Day of month for payroll"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    @field_validator("strategy_mode")
    @classmethod
    def validate_strategy_mode(cls, v: str) -> str:
        """Validate strategy mode."""
        valid_modes = ["SURVIVAL", "GROWTH", "OPTIMIZE"]
        if v.upper() not in valid_modes:
            raise ValueError(f"Invalid strategy mode: {v}. Must be one of {valid_modes}")
        return v.upper()

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.debug

    @property
    def is_survival_mode(self) -> bool:
        """Check if running in SURVIVAL mode."""
        return self.strategy_mode == "SURVIVAL"

    @property
    def is_growth_mode(self) -> bool:
        """Check if running in GROWTH mode."""
        return self.strategy_mode == "GROWTH"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
