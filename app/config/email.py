"""
Email service configuration for AP Intake & Validation system.

Separates email-related settings from core configuration.
"""

from pydantic import BaseSettings
from typing import Optional


class EmailConfig(BaseSettings):
    """Email service configuration."""
    
    # Email ingestion settings
    EMAIL_INGESTION_ENABLED: bool = True
    EMAIL_MONITORING_INTERVAL_MINUTES: int = 60
    EMAIL_MAX_PROCESSING_DAYS: int = 7
    EMAIL_SECURITY_VALIDATION_ENABLED: bool = True
    EMAIL_AUTO_PROCESS_INVOICES: bool = True
    
    # Gmail OAuth settings
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    GCP_PROJECT_ID: Optional[str] = None
    
    # Gmail Pub/Sub settings
    GMAIL_PUBSUB_TOPIC_NAME: str = "gmail-invoice-notifications"
    GMAIL_PUBSUB_SUBSCRIPTION_NAME: str = "gmail-invoice-subscription"
    GMAIL_WEBHOOK_URL: str = "http://localhost:8000/api/v1/gmail/gmail-webhook"
    
    # Microsoft Graph settings
    GRAPH_TENANT_ID: Optional[str] = None
    GRAPH_CLIENT_ID: Optional[str] = None
    GRAPH_CLIENT_SECRET: Optional[str] = None
    
    # Email provider settings
    SENDGRID_API_KEY: Optional[str] = None
    MAILGUN_API_KEY: Optional[str] = None
    MAILGUN_DOMAIN: Optional[str] = None
    
    # SMTP settings (for fallback)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    
    # Email processing settings
    EMAIL_MAX_ATTACHMENTS: int = 10
    EMAIL_MAX_ATTACHMENT_SIZE_MB: int = 25
    EMAIL_ALLOWED_SENDER_DOMAINS: list = []  # Empty means allow all
    EMAIL_BLOCKED_SENDER_DOMAINS: list = []
    
    # Email template settings
    EMAIL_TEMPLATE_DIR: str = "./templates/email"
    EMAIL_DEFAULT_FROM_EMAIL: str = "noreply@apintake.com"
    EMAIL_DEFAULT_FROM_NAME: str = "AP Intake System"
    
    # Email queue settings
    EMAIL_QUEUE_NAME: str = "email_processing"
    EMAIL_RETRY_ATTEMPTS: int = 3
    EMAIL_RETRY_DELAY_SECONDS: int = 300
    
    class Config:
        env_prefix = "EMAIL_"
        env_file = ".env"
        case_sensitive = True