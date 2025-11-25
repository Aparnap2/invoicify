"""
Base configuration settings for AP Intake & Validation system.

Provides essential settings with environment-specific overrides.
"""

from pydantic import BaseSettings
from typing import List


class BaseConfig(BaseSettings):
    """Base configuration with essential settings only."""
    
    # Core application settings
    PROJECT_NAME: str = "AP Intake & Validation"
    PROJECT_DESCRIPTION: str = "Transform emailed PDF invoices into validated, structured bills"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    
    # Basic security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS settings
    ALLOWED_HOSTS: List[str] = ["*"]
    
    # Basic database
    DATABASE_URL: str
    
    # Basic Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Basic storage
    STORAGE_TYPE: str = "local"
    STORAGE_PATH: str = "./storage"
    
    # File handling
    MAX_FILE_SIZE_MB: int = 25
    ALLOWED_FILE_TYPES: List[str] = ["pdf", "jpeg", "jpg", "png"]
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # UI configuration
    UI_HOST: str = "http://localhost:3000"
    API_HOST: str = "http://localhost:8000"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""
    
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    
    # Development database settings
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Development rate limiting (more lenient)
    RATE_LIMIT_CALLS: int = 1000
    RATE_LIMIT_PERIOD: int = 3600
    
    # Development CORS (allow localhost)
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001"
    ]


class ProductionConfig(BaseConfig):
    """Production environment configuration."""
    
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Production database settings
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    
    # Production rate limiting (more restrictive)
    RATE_LIMIT_CALLS: int = 100
    RATE_LIMIT_PERIOD: int = 3600
    
    # Production CORS (restrictive)
    ALLOWED_ORIGINS: List[str] = []  # Configure based on actual domains
    
    # Production security
    ENABLE_HTTPS_REDIRECT: bool = True
    ENABLE_SECURITY_HEADERS: bool = True


class TestingConfig(BaseConfig):
    """Testing environment configuration."""
    
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    
    # Testing database (in-memory or separate test DB)
    DATABASE_URL: str = "sqlite:///./test.db"
    
    # Testing rate limiting (disabled)
    RATE_LIMIT_CALLS: int = 10000
    RATE_LIMIT_PERIOD: int = 3600
    
    # Testing storage
    STORAGE_PATH: str = "./test_storage"