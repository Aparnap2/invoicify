"""
Email service with provider abstraction for Mailgun, SendGrid, and others.

Follows SOLID principles:
- Interface Segregation: Separate interfaces for different provider capabilities
- Dependency Inversion: Depends on abstractions, not concrete providers
- Single Responsibility: Each provider handles one email service
- Open/Closed: Open for extension, closed for modification
"""

import asyncio
import logging
import re
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

import aiohttp
import jinja2
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import EmailServiceException
from app.schemas.communication import (
    EmailProvider,
    EmailMessage,
    EmailResponse,
    EmailDeliveryStatus,
    CommunicationStatus,
    EmailSecurityValidation
)

logger = logging.getLogger(__name__)


class EmailProviderInterface(ABC):
    """Abstract interface for email providers."""

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> EmailResponse:
        """Send email via provider."""
        pass

    @abstractmethod
    async def get_delivery_status(self, message_id: str) -> EmailDeliveryStatus:
        """Get delivery status for sent email."""
        pass

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Validate provider credentials."""
        pass


class MailgunProvider(EmailProviderInterface):
    """Mailgun email provider implementation."""

    def __init__(self):
        """Initialize Mailgun provider."""
        self.api_key = getattr(settings, 'MAILGUN_API_KEY', None)
        self.domain = getattr(settings, 'MAILGUN_DOMAIN', None)
        self.base_url = f"https://api.mailgun.net/v3/{self.domain}" if self.domain else None
        self.webhook_secret = getattr(settings, 'MAILGUN_WEBHOOK_SECRET', None)

    async def send_email(self, message: EmailMessage) -> EmailResponse:
        """Send email via Mailgun API."""
        try:
            # Prepare email data
            data = {
                "from": message.from_email,
                "to": message.to if isinstance(message.to, str) else ",".join(message.to),
                "subject": message.subject,
                "text": message.text_content,
                "html": message.html_content,
                "tracking": "yes" if message.tracking_enabled else "no"
            }

            # Add optional fields
            if message.cc:
                data["cc"] = ",".join(message.cc) if isinstance(message.cc, list) else message.cc
            if message.bcc:
                data["bcc"] = ",".join(message.bcc) if isinstance(message.bcc, list) else message.bcc
            if message.headers:
                data["h:X-Mailgun-Variables"] = str(message.headers)

            # Add template support
            if message.template_name:
                data["template"] = message.template_name
                if message.template_data:
                    data["h:X-Mailgun-Variables"] = str(message.template_data)

            # Add attachments
            files = []
            if message.attachments:
                for attachment in message.attachments:
                    files.append(
                        ('attachment', (attachment['filename'], attachment['content'], attachment['mime_type']))
                    )

            # Make API request
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth('api', self.api_key)

                if files:
                    # Multipart request with attachments
                    data_parts = []
                    for key, value in data.items():
                        data_parts.append((key, value))
                    data_parts.extend(files)

                    async with session.post(
                        f"{self.base_url}/messages",
                        auth=auth,
                        data=data_parts
                    ) as response:
                        result = await response.json()
                else:
                    # Regular form data request
                    async with session.post(
                        f"{self.base_url}/messages",
                        auth=auth,
                        data=data
                    ) as response:
                        result = await response.json()

                if response.status == 200:
                    return EmailResponse(
                        success=True,
                        message_id=result.get('id'),
                        provider=EmailProvider.MAILGUN,
                        provider_response=result,
                        delivery_status="sent"
                    )
                else:
                    return EmailResponse(
                        success=False,
                        provider=EmailProvider.MAILGUN,
                        error_message=result.get('message', 'Unknown error'),
                        provider_response=result
                    )

        except Exception as e:
            logger.error(f"Mailgun email send failed: {e}")
            return EmailResponse(
                success=False,
                provider=EmailProvider.MAILGUN,
                error_message=str(e)
            )

    async def get_delivery_status(self, message_id: str) -> EmailDeliveryStatus:
        """Get delivery status from Mailgun."""
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth('api', self.api_key)

                async with session.get(
                    f"{self.base_url}/events",
                    auth=auth,
                    params={
                        "message-id": message_id,
                        "limit": 1
                    }
                ) as response:
                    result = await response.json()

                    if response.status == 200 and result.get('items'):
                        event = result['items'][0]
                        return EmailDeliveryStatus(
                            message_id=message_id,
                            provider=EmailProvider.MAILGUN,
                            status=self._map_mailgun_status(event.get('event')),
                            timestamp=datetime.fromisoformat(event.get('timestamp', '').replace('Z', '+00:00')),
                            events=[event]
                        )
                    else:
                        return EmailDeliveryStatus(
                            message_id=message_id,
                            provider=EmailProvider.MAILGUN,
                            status=CommunicationStatus.PENDING
                        )

        except Exception as e:
            logger.error(f"Failed to get Mailgun delivery status: {e}")
            return EmailDeliveryStatus(
                message_id=message_id,
                provider=EmailProvider.MAILGUN,
                status=CommunicationStatus.FAILED
            )

    def validate_credentials(self) -> bool:
        """Validate Mailgun credentials."""
        return bool(self.api_key and self.domain and self.base_url)

    def _map_mailgun_status(self, mailgun_event: str) -> CommunicationStatus:
        """Map Mailgun events to CommunicationStatus."""
        status_mapping = {
            'accepted': CommunicationStatus.SENT,
            'rejected': CommunicationStatus.FAILED,
            'delivered': CommunicationStatus.DELIVERED,
            'opened': CommunicationStatus.OPENED,
            'clicked': CommunicationStatus.OPENED,  # Mailgun doesn't have separate clicked status
            'bounced': CommunicationStatus.BOUNCED,
            'complained': CommunicationStatus.FAILED
        }
        return status_mapping.get(mailgun_event, CommunicationStatus.PENDING)


class SendGridProvider(EmailProviderInterface):
    """SendGrid email provider implementation."""

    def __init__(self):
        """Initialize SendGrid provider."""
        self.api_key = getattr(settings, 'SENDGRID_API_KEY', None)
        self.base_url = "https://api.sendgrid.com/v3"

    async def send_email(self, message: EmailMessage) -> EmailResponse:
        """Send email via SendGrid API."""
        try:
            # Prepare SendGrid personalization
            personalizations = []
            for recipient in (message.to if isinstance(message.to, list) else [message.to]):
                personalization = {
                    "to": [{"email": recipient}],
                    "subject": message.subject
                }

                if message.cc:
                    personalization["cc"] = [{"email": email} for email in
                                           (message.cc if isinstance(message.cc, list) else [message.cc])]

                personalizations.append(personization)

            # Prepare email content
            content = []
            if message.html_content:
                content.append({"type": "text/html", "value": message.html_content})
            if message.text_content:
                content.append({"type": "text/plain", "value": message.text_content})

            # Prepare SendGrid request
            data = {
                "personalizations": personalizations,
                "from": {"email": message.from_email},
                "content": content,
                "tracking_settings": {
                    "click_tracking": {"enable": message.tracking_enabled},
                    "open_tracking": {"enable": message.tracking_enabled}
                }
            }

            # Add template support
            if message.template_name:
                data["template_id"] = message.template_name
                if message.template_data:
                    for personalization in personalizations:
                        personalization["dynamic_template_data"] = message.template_data

            # Add attachments
            if message.attachments:
                data["attachments"] = []
                for attachment in message.attachments:
                    # Convert content to base64 if needed
                    content = attachment.get('content')
                    if isinstance(content, bytes):
                        import base64
                        content = base64.b64encode(content).decode()

                    data["attachments"].append({
                        "content": content,
                        "filename": attachment['filename'],
                        "type": attachment.get('mime_type', 'application/octet-stream')
                    })

            # Make API request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/mail/send",
                    headers=headers,
                    json=data
                ) as response:

                    if response.status == 202:  # SendGrid returns 202 for accepted
                        # Get message ID from response headers
                        message_id = response.headers.get('X-Message-Id')
                        return EmailResponse(
                            success=True,
                            message_id=message_id,
                            provider=EmailProvider.SENDGRID,
                            delivery_status="sent"
                        )
                    else:
                        error_text = await response.text()
                        return EmailResponse(
                            success=False,
                            provider=EmailProvider.SENDGRID,
                            error_message=f"SendGrid API error: {response.status} - {error_text}"
                        )

        except Exception as e:
            logger.error(f"SendGrid email send failed: {e}")
            return EmailResponse(
                success=False,
                provider=EmailProvider.SENDGRID,
                error_message=str(e)
            )

    async def get_delivery_status(self, message_id: str) -> EmailDeliveryStatus:
        """Get delivery status from SendGrid."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/messages/{message_id}",
                    headers=headers
                ) as response:

                    if response.status == 200:
                        result = await response.json()
                        return EmailDeliveryStatus(
                            message_id=message_id,
                            provider=EmailProvider.SENDGRID,
                            status=self._map_sendgrid_status(result.get('status', 'pending')),
                            events=[result]
                        )
                    else:
                        return EmailDeliveryStatus(
                            message_id=message_id,
                            provider=EmailProvider.SENDGRID,
                            status=CommunicationStatus.PENDING
                        )

        except Exception as e:
            logger.error(f"Failed to get SendGrid delivery status: {e}")
            return EmailDeliveryStatus(
                message_id=message_id,
                provider=EmailProvider.SENDGRID,
                status=CommunicationStatus.FAILED
            )

    def validate_credentials(self) -> bool:
        """Validate SendGrid credentials."""
        return bool(self.api_key)

    def _map_sendgrid_status(self, sendgrid_status: str) -> CommunicationStatus:
        """Map SendGrid status to CommunicationStatus."""
        status_mapping = {
            'processed': CommunicationStatus.SENT,
            'delivered': CommunicationStatus.DELIVERED,
            'open': CommunicationStatus.OPENED,
            'click': CommunicationStatus.OPENED,
            'bounce': CommunicationStatus.BOUNCED,
            'spamreport': CommunicationStatus.FAILED,
            'unsubscribe': CommunicationStatus.FAILED
        }
        return status_mapping.get(sendgrid_status, CommunicationStatus.PENDING)


class EmailTemplateEngine:
    """Jinja2-based email template engine."""

    def __init__(self):
        """Initialize template engine."""
        self.env = jinja2.Environment(
            loader=jinja2.DictLoader({}),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )

        # Add custom filters
        self.env.filters['currency'] = self._format_currency
        self.env.filters['date'] = self._format_date

    async def render_template(
        self,
        template_content: str,
        template_data: Dict[str, Any]
    ) -> tuple[str, str]:
        """Render Jinja2 template with data."""
        try:
            # Create template from content
            template = self.env.from_string(template_content)

            # Render HTML version
            html_content = template.render(**template_data)

            # Create plain text version by stripping HTML tags
            text_content = self._html_to_text(html_content)

            return html_content, text_content

        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            raise EmailServiceException(f"Template rendering failed: {str(e)}")

    def _format_currency(self, amount: Union[float, str]) -> str:
        """Format amount as currency."""
        try:
            if isinstance(amount, str):
                amount = float(amount.replace('$', '').replace(',', ''))
            return f"${amount:,.2f}"
        except (ValueError, TypeError):
            return str(amount)

    def _format_date(self, date_obj: Union[datetime, str], format_str: str = "%B %d, %Y") -> str:
        """Format date."""
        if isinstance(date_obj, str):
            try:
                date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            except ValueError:
                return date_obj

        if isinstance(date_obj, datetime):
            return date_obj.strftime(format_str)

        return str(date_obj)

    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion."""
        # Basic HTML tag removal for plain text version
        import re
        text = re.sub(r'<[^>]+>', '', html)
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text


class EmailSecurityValidator:
    """Email security and content validation."""

    def __init__(self):
        """Initialize security validator."""
        # Malicious patterns to detect
        self.malicious_patterns = [
            r'<script[^>]*>.*?</script>',  # Scripts
            r'javascript:',  # JavaScript URLs
            r'on\w+\s*=',  # Event handlers
            r'<iframe[^>]*>',  # Iframes
            r'<object[^>]*>',  # Objects
            r'<embed[^>]*>',  # Embeds
        ]

        # Spam indicators
        self.spam_patterns = [
            r'(?i)(click here|buy now|free money|guarantee|urgent|immediate)',
            r'(?i)(viagra|cialis|lottery|winner|congratulations)',
            r'[A-Z]{3,}',  # Excessive capitalization
            r'!!!{2,}',  # Excessive punctuation
        ]

        # Suspicious domains
        self.suspicious_domains = [
            r'.*\.bit$',
            r'.*\.tk$',
            r'.*\.ml$',
            r'.*\.ga$',
        ]

    def validate_email_address(self, email: str) -> bool:
        """Validate email address format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def validate_email_content(self, content: str) -> bool:
        """Validate email content for security issues."""
        if not content:
            return True

        # Check for malicious patterns
        for pattern in self.malicious_patterns:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                return False

        return True

    def get_security_flags(self, message: EmailMessage) -> List[str]:
        """Get security flags for email message."""
        flags = []

        # Validate recipients
        recipients = message.to if isinstance(message.to, list) else [message.to]
        for recipient in recipients:
            if not self.validate_email_address(recipient):
                flags.append("invalid_recipient")

        # Check content security
        content = message.html_content or message.text_content or ""
        if not self.validate_email_content(content):
            flags.append("malicious_content")

        # Check for spam indicators
        spam_score = 0
        for pattern in self.spam_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                spam_score += 1

        if spam_score >= 3:
            flags.append("spam_indicators")

        # Check sender domain
        sender_domain = message.from_email.split('@')[-1] if '@' in message.from_email else ""
        for pattern in self.suspicious_domains:
            if re.match(pattern, sender_domain):
                flags.append("suspicious_domain")
                break

        return flags


class EmailService:
    """Main email service with provider abstraction and template support."""

    def __init__(self):
        """Initialize email service."""
        self.template_engine = EmailTemplateEngine()
        self.security_validator = EmailSecurityValidator()
        self.providers = {
            EmailProvider.MAILGUN: MailgunProvider(),
            EmailProvider.SENDGRID: SendGridProvider(),
        }

        # Default provider configuration
        self.default_provider = EmailProvider.MAILGUN
        self.fallback_provider = EmailProvider.SENDGRID

        # Initialize default provider if available
        if hasattr(settings, 'DEFAULT_EMAIL_PROVIDER'):
            self.default_provider = EmailProvider(settings.DEFAULT_EMAIL_PROVIDER)

        if hasattr(settings, 'FALLBACK_EMAIL_PROVIDER'):
            self.fallback_provider = EmailProvider(settings.FALLBACK_EMAIL_PROVIDER)

    async def send_email(
        self,
        message: EmailMessage,
        provider: Optional[EmailProvider] = None
    ) -> EmailResponse:
        """Send email via specified provider."""
        provider = provider or self.default_provider

        # Validate message
        validation_flags = self.security_validator.get_security_flags(message)
        if validation_flags:
            logger.warning(f"Email security validation flags: {validation_flags}")
            # Allow sending but log warnings for non-critical issues
            if "malicious_content" in validation_flags:
                return EmailResponse(
                    success=False,
                    provider=provider,
                    error_message="Email content contains potentially malicious elements"
                )

        # Get provider instance
        provider_instance = self.providers.get(provider)
        if not provider_instance:
            return EmailResponse(
                success=False,
                provider=provider,
                error_message=f"Email provider {provider} not available"
            )

        # Validate provider credentials
        if not provider_instance.validate_credentials():
            return EmailResponse(
                success=False,
                provider=provider,
                error_message=f"Invalid credentials for provider {provider}"
            )

        # Send email
        try:
            response = await provider_instance.send_email(message)
            logger.info(f"Email sent via {provider}: {response.message_id}")
            return response

        except Exception as e:
            logger.error(f"Failed to send email via {provider}: {e}")
            return EmailResponse(
                success=False,
                provider=provider,
                error_message=str(e)
            )

    async def send_email_with_fallback(
        self,
        message: EmailMessage,
        primary_provider: Optional[EmailProvider] = None,
        fallback_provider: Optional[EmailProvider] = None
    ) -> EmailResponse:
        """Send email with fallback to secondary provider."""
        primary_provider = primary_provider or self.default_provider
        fallback_provider = fallback_provider or self.fallback_provider

        # Try primary provider first
        response = await self.send_email(message, primary_provider)

        if response.success:
            return response

        logger.warning(f"Primary provider {primary_provider} failed, trying fallback {fallback_provider}")

        # Try fallback provider
        fallback_response = await self.send_email(message, fallback_provider)

        # Mark as fallback used if successful
        if fallback_response.success:
            fallback_response.fallback_used = True

        return fallback_response

    async def send_with_retry(
        self,
        message: EmailMessage,
        provider: Optional[EmailProvider] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> EmailResponse:
        """Send email with retry logic."""
        provider = provider or self.default_provider
        retry_count = 0

        while retry_count < max_retries:
            response = await self.send_email(message, provider)

            if response.success:
                response.retry_count = retry_count
                return response

            retry_count += 1

            if retry_count < max_retries:
                # Exponential backoff
                delay = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"Retrying email send in {delay}s (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(delay)

        # All retries failed
        response.retry_count = retry_count
        return response

    async def render_template(
        self,
        template_content: str,
        template_data: Dict[str, Any]
    ) -> tuple[str, str]:
        """Render email template with data."""
        return await self.template_engine.render_template(template_content, template_data)

    async def get_delivery_status(self, message_id: str, provider: EmailProvider) -> EmailDeliveryStatus:
        """Get delivery status for sent email."""
        provider_instance = self.providers.get(provider)
        if not provider_instance:
            raise EmailServiceException(f"Provider {provider} not available")

        return await provider_instance.get_delivery_status(message_id)

    def validate_email_address(self, email: str) -> bool:
        """Validate email address format."""
        return self.security_validator.validate_email_address(email)

    def validate_email_content(self, content: str) -> bool:
        """Validate email content for security."""
        return self.security_validator.validate_email_content(content)

    def get_provider_status(self) -> Dict[EmailProvider, bool]:
        """Get status of all configured providers."""
        status = {}
        for provider, instance in self.providers.items():
            status[provider] = instance.validate_credentials()
        return status