"""
Email service module for AP Intake & Validation system.

This module provides a comprehensive email service architecture with:
- Abstract base classes for email providers and processors
- Concrete implementations for Gmail, SendGrid, and Mailgun
- Security, extraction, and template processors
- Email service manager coordinating all operations

Key Components:
- EmailProvider: Abstract interface for email service providers
- EmailProcessor: Abstract interface for email processing
- EmailServiceManager: Facade coordinating providers and processors
- SecurityProcessor: Validates email security and detects threats
- ExtractionProcessor: Extracts invoice data from email content
- TemplateProcessor: Renders email templates and manages formatting

Usage:
    from app.services.email import EmailServiceManager, GmailProvider, SecurityProcessor
    
    # Create provider and processors
    provider = GmailProvider(credentials_path="credentials.json")
    security_processor = SecurityProcessor()
    
    # Create manager
    manager = EmailServiceManager(
        provider=provider,
        processors=[security_processor]
    )
    
    # Process emails
    emails = await manager.fetch_and_process_emails()
"""

from .base import (
    EmailProvider,
    EmailProcessor,
    EmailMessage,
    EmailAttachment,
    EmailTemplate
)

from .manager import EmailServiceManager

from .providers import (
    GmailProvider,
    SendGridProvider,
    MailgunProvider
)

from .processors import (
    SecurityProcessor,
    ExtractionProcessor,
    TemplateProcessor
)

__all__ = [
    # Base classes
    'EmailProvider',
    'EmailProcessor', 
    'EmailMessage',
    'EmailAttachment',
    'EmailTemplate',
    
    # Manager
    'EmailServiceManager',
    
    # Providers
    'GmailProvider',
    'SendGridProvider',
    'MailgunProvider',
    
    # Processors
    'SecurityProcessor',
    'ExtractionProcessor',
    'TemplateProcessor'
]