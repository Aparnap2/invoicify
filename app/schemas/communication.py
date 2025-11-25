"""
Communication schemas for vendor communication automation.

Data contracts for email service abstraction, vendor communication,
and template management following SOLID principles.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, EmailStr, validator


class EmailProvider(str, Enum):
    """Email service providers."""
    MAILGUN = "mailgun"
    SENDGRID = "sendgrid"
    AWS_SES = "aws_ses"
    POSTMARK = "postmark"


class CommunicationType(str, Enum):
    """Types of vendor communications."""
    VALIDATION_ERROR = "validation_error"
    MISSING_INFORMATION = "missing_information"
    CALCULATION_ERROR = "calculation_error"
    DUPLICATE_INVOICE = "duplicate_invoice"
    PROCESSING_CONFIRMATION = "processing_confirmation"
    PAYMENT_STATUS = "payment_status"
    GENERAL_INQUIRY = "general_inquiry"


class CommunicationStatus(str, Enum):
    """Communication status tracking."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    OPENED = "opened"
    REPLIED = "replied"


class ContactMethod(str, Enum):
    """Preferred contact methods."""
    EMAIL = "email"
    PHONE = "phone"
    SMS = "sms"
    FAX = "fax"


class SeverityLevel(str, Enum):
    """Issue severity levels for communications."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# Email Service Abstraction Schemas
class EmailMessage(BaseModel):
    """Email message model for provider abstraction."""
    to: Union[EmailStr, List[EmailStr]]
    from_email: EmailStr
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    subject: str
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    template_name: Optional[str] = None
    template_data: Optional[Dict[str, Any]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    headers: Optional[Dict[str, str]] = None
    tracking_enabled: bool = True
    priority: Optional[str] = None

    @validator('to')
    def validate_to_field(cls, v):
        """Validate to field accepts single email or list."""
        if isinstance(v, str):
            return [v]
        return v

    @validator('html_content', 'text_content')
    def validate_content(cls, v, values):
        """Ensure at least one content type is provided."""
        if not v and not values.get('text_content') and not values.get('html_content'):
            if not values.get('template_name'):
                raise ValueError('Either html_content, text_content, or template_name must be provided')
        return v


class EmailResponse(BaseModel):
    """Email sending response from providers."""
    success: bool
    message_id: Optional[str] = None
    provider: EmailProvider
    provider_response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    delivery_status: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = 0
    fallback_used: bool = False


class EmailDeliveryStatus(BaseModel):
    """Email delivery status tracking."""
    message_id: str
    provider: EmailProvider
    status: CommunicationStatus
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    bounced_at: Optional[datetime] = None
    bounce_reason: Optional[str] = None
    events: List[Dict[str, Any]] = []


# Vendor Communication Schemas
class VendorContact(BaseModel):
    """Vendor contact information."""
    vendor_id: str
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    department: Optional[str] = None
    is_primary: bool = False
    preferred_contact_method: ContactMethod = ContactMethod.EMAIL
    communication_preferences: Optional[Dict[str, Any]] = None
    timezone: Optional[str] = None
    business_hours: Optional[Dict[str, str]] = None
    language_preference: str = "en"

    @validator('communication_preferences')
    def validate_preferences(cls, v):
        """Set default communication preferences."""
        if v is None:
            return {
                "business_hours_only": False,
                "frequency_limit": "unlimited",
                "weekend_communications": True,
                "urgent_only": False
            }
        return v


class ValidationIssue(BaseModel):
    """Validation issue for vendor communication."""
    code: str
    description: str
    field: Optional[str] = None
    severity: SeverityLevel
    line_number: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    requires_vendor_action: bool = False
    suggested_fix: Optional[str] = None


class CommunicationTrigger(str, Enum):
    """Communication trigger types."""
    VENDOR_ACTION_REQUIRED = "vendor_action_required"
    VALIDATION_ERROR = "validation_error"
    DUPLICATE_DETECTED = "duplicate_detected"
    PROCESSING_COMPLETE = "processing_complete"
    PAYMENT_SCHEDULED = "payment_scheduled"


class CommunicationTriggerCondition(BaseModel):
    """Communication trigger conditions."""
    trigger_type: CommunicationTrigger
    condition_met: bool
    urgency: SeverityLevel = SeverityLevel.MEDIUM
    auto_send: bool = True
    requires_approval: bool = False
    delay_minutes: int = 0


class EmailTemplateRequest(BaseModel):
    """Request for email template rendering."""
    template_type: str
    template_data: Dict[str, Any]
    validation_issues: Optional[List[ValidationIssue]] = None
    vendor_contact: Optional[VendorContact] = None
    invoice_data: Optional[Dict[str, Any]] = None
    custom_message: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class VendorCommunicationRequest(BaseModel):
    """Request for vendor communication."""
    invoice_id: str
    vendor_contact: VendorContact
    communication_type: CommunicationType
    invoice_data: Optional[Dict[str, Any]] = None
    validation_issues: Optional[List[ValidationIssue]] = None
    custom_message: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    priority: SeverityLevel = SeverityLevel.MEDIUM
    send_immediately: bool = True
    tracking_enabled: bool = True

    @validator('validation_issues')
    def validate_issues_for_type(cls, v, values):
        """Validate validation issues are provided for error communications."""
        communication_type = values.get('communication_type')
        if communication_type in [
            CommunicationType.VALIDATION_ERROR,
            CommunicationType.MISSING_INFORMATION,
            CommunicationType.CALCULATION_ERROR,
            CommunicationType.DUPLICATE_INVOICE
        ]:
            if not v or len(v) == 0:
                raise ValueError(f'Validation issues required for {communication_type}')
        return v


class VendorCommunicationResponse(BaseModel):
    """Response from vendor communication request."""
    success: bool
    communication_id: Optional[str] = None
    communication_type: CommunicationType
    email_sent: bool = False
    vendor_contacted: bool = False
    message_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    delivery_status: Optional[CommunicationStatus] = None


class CommunicationRecord(BaseModel):
    """Record of vendor communication."""
    communication_id: str
    invoice_id: str
    vendor_id: str
    vendor_contact: VendorContact
    communication_type: CommunicationType
    status: CommunicationStatus
    email_message: Optional[EmailMessage] = None
    email_response: Optional[EmailResponse] = None
    validation_issues: Optional[List[ValidationIssue]] = None
    invoice_data: Optional[Dict[str, Any]] = None
    custom_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class CommunicationHistoryResponse(BaseModel):
    """Response for communication history query."""
    communications: List[CommunicationRecord]
    total_count: int
    page: int
    page_size: int
    has_more: bool


# Template Management Schemas
class EmailTemplate(BaseModel):
    """Email template definition."""
    template_name: str
    template_type: str
    subject_template: str
    html_template: str
    text_template: Optional[str] = None
    variables: List[str]
    language: str = "en"
    locale: str = "en_US"
    active: bool = True
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    description: Optional[str] = None

    class Config:
        """Pydantic config."""
        use_enum_values = True


class TemplateRenderRequest(BaseModel):
    """Request to render email template."""
    template_name: str
    template_data: Dict[str, Any]
    language: Optional[str] = "en"
    locale: Optional[str] = "en_US"


class TemplateRenderResponse(BaseModel):
    """Response from template rendering."""
    subject: str
    html_content: str
    text_content: Optional[str] = None
    rendered_at: datetime = Field(default_factory=datetime.utcnow)
    template_used: str
    variables_substituted: List[str]


# Email Queue and Batch Processing Schemas
class EmailQueueItem(BaseModel):
    """Email queue item for batch processing."""
    queue_id: str
    email_message: EmailMessage
    provider: EmailProvider
    priority: int = 5  # 1-10, where 1 is highest priority
    max_retries: int = 3
    retry_count: int = 0
    scheduled_for: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class BatchCommunicationRequest(BaseModel):
    """Request for batch communication processing."""
    batch_id: str
    communications: List[VendorCommunicationRequest]
    batch_settings: Optional[Dict[str, Any]] = None
    send_immediately: bool = True
    scheduled_for: Optional[datetime] = None


class BatchCommunicationResponse(BaseModel):
    """Response from batch communication processing."""
    batch_id: str
    total_count: int
    success_count: int
    failed_count: int
    communication_ids: List[str]
    errors: List[Dict[str, Any]] = []
    processed_at: datetime = Field(default_factory=datetime.utcnow)


# Analytics and Metrics Schemas
class CommunicationMetrics(BaseModel):
    """Communication performance metrics."""
    period_start: datetime
    period_end: datetime
    total_sent: int
    total_delivered: int
    total_opened: int
    total_failed: int
    delivery_rate: float
    open_rate: float
    failure_rate: float
    average_delivery_time_seconds: float
    provider_metrics: Dict[EmailProvider, Dict[str, Any]]
    template_performance: Dict[str, Dict[str, Any]]
    vendor_response_metrics: Dict[str, Any]


class VendorCommunicationStats(BaseModel):
    """Vendor-specific communication statistics."""
    vendor_id: str
    vendor_name: str
    total_communications: int
    successful_communications: int
    failed_communications: int
    average_response_time_hours: Optional[float] = None
    preferred_contact_method: ContactMethod
    last_communication_date: Optional[datetime] = None
    communication_frequency: Dict[str, int]
    issue_resolution_rate: float


# Configuration Schemas
class EmailServiceConfig(BaseModel):
    """Email service configuration."""
    default_provider: EmailProvider
    fallback_provider: Optional[EmailProvider] = None
    api_keys: Dict[EmailProvider, str]
    domains: Dict[EmailProvider, str]
    retry_config: Dict[str, Any]
    rate_limits: Dict[EmailProvider, Dict[str, int]]
    webhooks: Dict[EmailProvider, str]
    tracking_enabled: bool = True
    security_config: Dict[str, Any]


class VendorCommunicationConfig(BaseModel):
    """Vendor communication service configuration."""
    business_hours: Dict[str, str]
    timezone: str
    default_language: str = "en"
    communication_limits: Dict[str, Any]
    template_settings: Dict[str, Any]
    approval_required_for: List[str]
    auto_send_enabled: bool = True
    tracking_enabled: bool = True
    security_settings: Dict[str, Any]


# Webhook and Event Schemas
class EmailWebhookEvent(BaseModel):
    """Email webhook event from providers."""
    event_type: str
    message_id: str
    provider: EmailProvider
    timestamp: datetime
    recipient: str
    status: CommunicationStatus
    metadata: Optional[Dict[str, Any]] = None
    bounce_reason: Optional[str] = None
    spam_complaint: bool = False


class CommunicationEvent(BaseModel):
    """Internal communication tracking event."""
    event_id: str
    communication_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any]
    source: str
    user_id: Optional[str] = None


# Security and Validation Schemas
class EmailSecurityValidation(BaseModel):
    """Email security validation results."""
    is_valid: bool
    security_flags: List[str]
    spam_score: Optional[float] = None
    phishing_risk: Optional[str] = None
    content_issues: List[str] = []
    recipient_issues: List[str] = []
    attachment_issues: List[str] = []


class CommunicationAuditLog(BaseModel):
    """Audit log for vendor communications."""
    log_id: str
    communication_id: str
    action: str
    actor: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# API Request/Response Schemas
class SendCommunicationRequest(BaseModel):
    """API request to send vendor communication."""
    invoice_id: str
    communication_type: CommunicationType
    message: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    send_immediately: bool = True
    priority: SeverityLevel = SeverityLevel.MEDIUM


class SendCommunicationResponse(BaseModel):
    """API response for send communication request."""
    success: bool
    communication_id: Optional[str] = None
    message: str
    estimated_delivery_time: Optional[datetime] = None
    retry_count: int = 0


class GetCommunicationHistoryRequest(BaseModel):
    """API request for communication history."""
    vendor_id: Optional[str] = None
    invoice_id: Optional[str] = None
    communication_type: Optional[CommunicationType] = None
    status: Optional[CommunicationStatus] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    page_size: int = 20
    sort_by: str = "created_at"
    sort_order: str = "desc"


class GetCommunicationHistoryResponse(BaseModel):
    """API response for communication history."""
    success: bool
    communications: List[CommunicationRecord]
    pagination: Dict[str, Any]
    total_count: int
    filters_applied: Dict[str, Any]