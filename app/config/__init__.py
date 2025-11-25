"""
Configuration module for AP Intake & Validation system.

Provides modular configuration management with environment-specific settings.
"""

from .base import BaseConfig, DevelopmentConfig, ProductionConfig
from .database import DatabaseConfig
from .email import EmailConfig
from .integrations import IntegrationsConfig
from .security import SecurityConfig
from .monitoring import MonitoringConfig

# Factory function to get appropriate config
def get_config() -> BaseConfig:
    """Get configuration based on environment."""
    import os
    
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return ProductionConfig()
    elif env == "development":
        return DevelopmentConfig()
    else:
        return DevelopmentConfig()  # Default to development

# Create global config instance
config = get_config()