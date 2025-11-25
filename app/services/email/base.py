"""
Base classes for email service abstraction.

Defines interfaces for email providers and processors following SOLID principles.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class EmailStatus(str, Enum):
    """Email processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    BLOCKED = "blocked"


class SecurityFlag(str, Enum):
    """Email security flag types."""
    MALICIOUS_PATTERN = "malicious_pattern"
    UNTRUSTED_SENDER = "untrusted_sender"
    EXCESSIVE_URLS = "excessive_urls"
    EXCESSIVE_ATTACHMENTS = "excessive_attachments"
    SUSPICIOUS_CONTENT = "suspicious_content"


@dataclass
class EmailAttachment:
    """Email attachment data structure."""
    filename: str
    content_type: str
    size_bytes: int
    content_hash: str
    storage_path: Optional[str] = None
    is_pdf: bool = False
    is_scanned: bool = False


@dataclass
class EmailMessage:
    """Unified email message structure."""
    id: str
    provider_message_id: str
    thread_id: Optional[str]
    subject: str
    from_email: str
    to_emails: List[str]
    cc_emails: List[str] = None
    bcc_emails: List[str] = None
    date_sent: datetime
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    snippet: Optional[str] = None
    attachments: List[EmailAttachment] = None
    labels: List[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class EmailQuery:
    """Email query parameters."""
    user_id: str
    max_results: int = 50
    days_back: int = 7
    query: Optional[str] = None
    label_filter: Optional[str] = None
    has_attachments: bool = False


@dataclass
class EmailResult:
    """Result of email operation."""
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None
    error_code: Optional[str] = None
    processing_time_ms: Optional[int] = None


@dataclass
class SecurityResult:
    """Email security validation result."""
    is_safe: bool
    security_score: int  # 0-100, higher is better
    flags: List[SecurityFlag]
    details: Dict[str, Any]
    blocked_reason: Optional[str] = None


@dataclass
class ExtractionResult:
    """Invoice extraction result."""
    success: bool
    confidence: float  # 0.0-1.0
    vendor_name: Optional[str] = None
    invoice_date: Optional[datetime] = None
    invoice_amount: Optional[float] = None
    extracted_data: Dict[str, Any] = None
    error_message: Optional[str] = None


@dataclass
class ProcessingResult:
    """Result of email processing."""
    success: bool
    status: EmailStatus
    message: Optional[str] = None
    security_result: Optional[SecurityResult] = None
    extraction_result: Optional[ExtractionResult] = None
    processing_time_ms: Optional[int] = None
    error_details: Dict[str, Any] = None


class EmailProvider(ABC):
    """
    Abstract base class for email providers.
    
    Implements Strategy pattern for different email services.
    """
    
    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> EmailResult:
        """
        Authenticate with the email provider.
        
        Args:
            credentials: Provider-specific credentials
            
        Returns:
            EmailResult with authentication status
        """
        pass
    
    @abstractmethod
    async def get_messages(self, query: EmailQuery) -> EmailResult:
        """
        Retrieve messages from the provider.
        
        Args:
            query: Email query parameters
            
        Returns:
            EmailResult with list of EmailMessage
        """
        pass
    
    @abstractmethod
    async def send_email(self, message: EmailMessage) -> EmailResult:
        """
        Send an email through the provider.
        
        Args:
            message: Email message to send
            
        Returns:
            EmailResult with delivery status
        """
        pass
    
    @abstractmethod
    async def watch_messages(self, webhook_url: str) -> EmailResult:
        """
        Set up real-time message monitoring.
        
        Args:
            webhook_url: URL to receive notifications
            
        Returns:
            EmailResult with watch status
        """
        pass
    
    @abstractmethod
    async def stop_watching(self) -> EmailResult:
        """
        Stop real-time message monitoring.
        
        Returns:
            EmailResult with stop status
        """
        pass


class EmailProcessor(ABC):
    """
    Abstract base class for email processors.
    
    Implements Chain of Responsibility pattern for email processing.
    """
    
    @abstractmethod
    async def process(self, email: EmailMessage) -> ProcessingResult:
        """
        Process an email message.
        
        Args:
            email: Email message to process
            
        Returns:
            ProcessingResult with processing status
        """
        pass
    
    @abstractmethod
    def can_handle(self, email: EmailMessage) -> bool:
        """
        Check if this processor can handle the email.
        
        Args:
            email: Email message to check
            
        Returns:
            True if processor can handle the email
        """
        pass


class EmailTemplate(ABC):
    """
    Abstract base class for email templates.
    
    Implements Template Method pattern for email rendering.
    """
    
    @abstractmethod
    async def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render an email template.
        
        Args:
            template_name: Name of the template
            context: Template context data
            
        Returns:
            Rendered email content
        """
        pass
    
    @abstractmethod
    def validate_template(self, template_name: str) -> bool:
        """
        Validate if template exists and is valid.
        
        Args:
            template_name: Name of the template
            
        Returns:
            True if template is valid
        """
        pass