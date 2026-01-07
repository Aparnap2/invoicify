"""Configuration management for AI service."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration
    llm_model: str = Field(default="openai:gpt-4o", description="LLM model to use")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")

    # Server Configuration
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001)
    debug: bool = Field(default=False)

    # Database Configuration
    database_url: str = Field(
        default="postgresql://user:password@localhost:5432/invoicify"
    )

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379")

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

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.debug

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
