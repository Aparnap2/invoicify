"""
Email providers for AP Intake & Validation system.

This module provides email provider implementations for different email services:
- GmailProvider: Gmail API integration for receiving and sending emails
- SendGridProvider: SendGrid API integration for sending emails
- MailgunProvider: Mailgun API integration for sending and receiving emails
"""

from .gmail import GmailProvider
from .sendgrid import SendGridProvider
from .mailgun import MailgunProvider

__all__ = [
    'GmailProvider',
    'SendGridProvider',
    'MailgunProvider'
]