"""
Vendor communication service for automated invoice discrepancy notifications.

Integrates with the validation workflow to automatically send professional
emails to vendors when validation fails, following SOLID principles.

Key Features:
- Template-based email communication
- Vendor contact resolution and preferences
- Communication history tracking
- Integration with validation workflow
- Multi-language support
- Business hours and frequency considerations
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func

from app.core.config import settings
from app.core.exceptions import EmailServiceException
from app.services.email_service import EmailService, EmailProvider, EmailMessage, EmailResponse
from app.db.session import AsyncSessionLocal
from app.models.invoice import Invoice
from app.models.reference import Vendor
from app.schemas.communication import (
    CommunicationType,
    CommunicationStatus,
    ContactMethod,
    SeverityLevel,
    VendorContact,
    ValidationIssue,
    VendorCommunicationRequest,
    VendorCommunicationResponse,
    CommunicationRecord,
    EmailTemplate,
    TemplateRenderResponse,
    CommunicationTrigger,
    CommunicationHistoryResponse
)

logger = logging.getLogger(__name__)


class VendorCommunicationService:
    """Service for managing vendor communications for invoice discrepancies."""

    def __init__(self):
        """Initialize vendor communication service."""
        self.email_service = EmailService()
        self.templates = self._load_templates()
        self.business_hours = {
            "start": getattr(settings, 'BUSINESS_HOURS_START', '09:00'),
            "end": getattr(settings, 'BUSINESS_HOURS_END', '17:00'),
            "timezone": getattr(settings, 'DEFAULT_TIMEZONE', 'UTC'),
            "weekend_communications": getattr(settings, 'ALLOW_WEEKEND_COMMUNICATIONS', False)
        }

    async def send_communication(
        self,
        request: VendorCommunicationRequest
    ) -> VendorCommunicationResponse:
        """Send communication to vendor."""
        try:
            communication_id = str(uuid.uuid4())

            # Generate email content
            email_message = await self._generate_email_message(
                request=request,
                communication_id=communication_id
            )

            # Check timing constraints
            can_send, timing_reason = await self.check_communication_timing(request)
            if not can_send and request.send_immediately:
                logger.info(f"Communication delayed due to timing: {timing_reason}")
                return VendorCommunicationResponse(
                    success=False,
                    communication_id=communication_id,
                    communication_type=request.communication_type,
                    error_message=f"Communication delayed: {timing_reason}"
                )

            # Send email
            email_response = await self.email_service.send_with_retry(
                message=email_message,
                max_retries=3
            )

            if email_response.success:
                # Record communication
                await self._record_communication(
                    communication_id=communication_id,
                    request=request,
                    email_message=email_message,
                    email_response=email_response
                )

                return VendorCommunicationResponse(
                    success=True,
                    communication_id=communication_id,
                    communication_type=request.communication_type,
                    email_sent=True,
                    vendor_contacted=True,
                    message_id=email_response.message_id,
                    sent_at=datetime.utcnow(),
                    delivery_status=CommunicationStatus.SENT
                )
            else:
                return VendorCommunicationResponse(
                    success=False,
                    communication_id=communication_id,
                    communication_type=request.communication_type,
                    error_message=email_response.error_message
                )

        except Exception as e:
            logger.error(f"Failed to send vendor communication: {e}")
            return VendorCommunicationResponse(
                success=False,
                communication_type=request.communication_type,
                error_message=str(e)
            )

    async def handle_validation_failure(
        self,
        validation_result: Dict[str, Any],
        invoice_data: Dict[str, Any]
    ) -> VendorCommunicationResponse:
        """Handle validation failure by sending vendor communication."""
        try:
            # Evaluate if communication is needed
            should_communicate, trigger_type = await self.evaluate_communication_trigger(
                validation_result=validation_result,
                invoice_data=invoice_data
            )

            if not should_communicate:
                return VendorCommunicationResponse(
                    success=True,
                    communication_type=CommunicationType.VALIDATION_ERROR,
                    vendor_contacted=False,
                    message="No communication required for this validation result"
                )

            # Resolve vendor contact
            vendor_contact = await self.resolve_vendor_contact(invoice_data)
            if not vendor_contact:
                return VendorCommunicationResponse(
                    success=False,
                    communication_type=CommunicationType.VALIDATION_ERROR,
                    error_message="Unable to resolve vendor contact information"
                )

            # Convert validation issues
            validation_issues = []
            for issue in validation_result.get('issues', []):
                validation_issues.append(ValidationIssue(**issue))

            # Determine communication type based on issues
            communication_type = self._determine_communication_type(validation_issues)

            # Create communication request
            request = VendorCommunicationRequest(
                invoice_id=invoice_data.get('invoice_id'),
                vendor_contact=vendor_contact,
                communication_type=communication_type,
                invoice_data=invoice_data,
                validation_issues=validation_issues,
                priority=self._determine_priority(validation_issues)
            )

            # Send communication
            return await self.send_communication(request)

        except Exception as e:
            logger.error(f"Failed to handle validation failure: {e}")
            return VendorCommunicationResponse(
                success=False,
                communication_type=CommunicationType.VALIDATION_ERROR,
                error_message=str(e)
            )

    async def check_communication_timing(
        self,
        request: VendorCommunicationRequest
    ) -> Tuple[bool, str]:
        """Check if communication should be sent based on timing constraints."""
        vendor_contact = request.vendor_contact
        current_time = datetime.now(timezone.utc)

        # Check business hours if enabled
        if vendor_contact.communication_preferences and vendor_contact.communication_preferences.get('business_hours_only'):
            if not self._is_business_hours(current_time, vendor_contact.timezone):
                return False, "Outside business hours"

        # Check weekend communications
        if not self.business_hours['weekend_communications']:
            if current_time.weekday() >= 5:  # Saturday or Sunday
                return False, "Weekend communications disabled"

        # Check frequency limits
        if vendor_contact.communication_preferences:
            freq_limit = vendor_contact.communication_preferences.get('frequency_limit')
            if freq_limit != 'unlimited':
                recent_communications = await self._get_recent_communications(
                    vendor_contact.vendor_id,
                    freq_limit
                )
                if recent_communications:
                    return False, f"Frequency limit: {freq_limit}"

        return True, "Timing OK"

    async def resolve_vendor_contact(self, invoice_data: Dict[str, Any]) -> Optional[VendorContact]:
        """Resolve vendor contact information from invoice data."""
        try:
            vendor_name = invoice_data.get('vendor_name')
            vendor_email = invoice_data.get('vendor_email')

            if not vendor_name:
                logger.warning("No vendor name in invoice data")
                return None

            # Try to find vendor in database
            async with AsyncSessionLocal() as session:
                # Search for vendor by name
                vendor_query = select(Vendor).where(
                    Vendor.name.ilike(f"%{vendor_name}%")
                )
                vendor_result = await session.execute(vendor_query)
                vendor = vendor_result.scalar_one_or_none()

                if vendor:
                    # Use vendor's preferred contact information
                    return VendorContact(
                        vendor_id=str(vendor.id),
                        contact_name=vendor.contact_name or vendor.name,
                        email=vendor_email or vendor.email,
                        phone=vendor.phone,
                        company_name=vendor.name,
                        is_primary=True,
                        preferred_contact_method=ContactMethod.EMAIL
                    )
                else:
                    # Create basic contact from invoice data
                    if vendor_email:
                        return VendorContact(
                            vendor_id=f"unknown_{uuid.uuid4().hex[:8]}",
                            contact_name=vendor_name,
                            email=vendor_email,
                            company_name=vendor_name,
                            is_primary=True,
                            preferred_contact_method=ContactMethod.EMAIL
                        )
                    else:
                        logger.warning(f"No email found for vendor: {vendor_name}")
                        return None

        except Exception as e:
            logger.error(f"Failed to resolve vendor contact: {e}")
            return None

    async def evaluate_communication_trigger(
        self,
        validation_result: Dict[str, Any],
        invoice_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Evaluate if communication should be triggered based on validation results."""
        if validation_result.get('passed', True):
            return False, "Validation passed"

        issues = validation_result.get('issues', [])
        if not issues:
            return False, "No validation issues"

        # Check if any issues require vendor action
        vendor_action_issues = [
            issue for issue in issues
            if issue.get('requires_vendor_action', False)
        ]

        if vendor_action_issues:
            return True, CommunicationTrigger.VENDOR_ACTION_REQUIRED

        # Check for errors (not just warnings)
        error_issues = [
            issue for issue in issues
            if issue.get('severity', 'info') in ['error', 'high']
        ]

        if error_issues:
            return True, CommunicationTrigger.VALIDATION_ERROR

        # Check for duplicate invoices
        duplicate_issues = [
            issue for issue in issues
            if issue.get('code') == 'DUPLICATE_INVOICE'
        ]

        if duplicate_issues:
            return True, CommunicationTrigger.DUPLICATE_DETECTED

        return False, "No communication trigger found"

    async def send_batch_communications(
        self,
        requests: List[VendorCommunicationRequest]
    ) -> List[VendorCommunicationResponse]:
        """Send multiple communications in batch."""
        responses = []

        # Process in parallel with rate limiting
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent emails

        async def process_single_request(request):
            async with semaphore:
                return await self.send_communication(request)

        # Create tasks for all requests
        tasks = [process_single_request(request) for request in requests]

        # Wait for all tasks to complete
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed responses
        processed_responses = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                processed_responses.append(VendorCommunicationResponse(
                    success=False,
                    communication_type=requests[i].communication_type,
                    error_message=str(response)
                ))
            else:
                processed_responses.append(response)

        return processed_responses

    async def get_communication_history(
        self,
        vendor_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
        limit: int = 20
    ) -> List[CommunicationRecord]:
        """Get communication history for vendor or invoice."""
        try:
            # This would typically query a communication records table
            # For now, return empty list to be implemented with proper database schema
            logger.info(f"Getting communication history for vendor: {vendor_id}, invoice: {invoice_id}")
            return []

        except Exception as e:
            logger.error(f"Failed to get communication history: {e}")
            return []

    async def _generate_email_message(
        self,
        request: VendorCommunicationRequest,
        communication_id: str
    ) -> EmailMessage:
        """Generate email message from request."""
        # Select appropriate template
        template_name = self._select_template_name(request.communication_type)
        template = self.templates.get(template_name)

        if not template:
            raise EmailServiceException(f"Template not found: {template_name}")

        # Prepare template data
        template_data = await self._prepare_template_data(request)

        # Render template
        subject, html_content, text_content = await self._render_email_template(
            template=template,
            template_data=template_data
        )

        # Create email message
        email_message = EmailMessage(
            to=request.vendor_contact.email,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'ap@company.com'),
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tracking_enabled=request.tracking_enabled,
            headers={
                'X-Communication-ID': communication_id,
                'X-Communication-Type': request.communication_type.value,
                'X-Invoice-ID': request.invoice_id
            }
        )

        # Add attachments if provided
        if request.attachments:
            email_message.attachments = request.attachments

        return email_message

    async def _prepare_template_data(self, request: VendorCommunicationRequest) -> Dict[str, Any]:
        """Prepare data for email template rendering."""
        template_data = {
            'vendor_name': request.vendor_contact.company_name,
            'contact_name': request.vendor_contact.contact_name,
            'invoice_data': request.invoice_data or {},
            'validation_issues': request.validation_issues or [],
            'custom_message': request.custom_message,
            'communication_date': datetime.now().strftime('%B %d, %Y'),
            'support_contact': getattr(settings, 'SUPPORT_EMAIL', 'ap@company.com'),
            'company_name': getattr(settings, 'COMPANY_NAME', 'Your Company')
        }

        # Add invoice-specific data
        if request.invoice_data:
            template_data.update({
                'invoice_number': request.invoice_data.get('invoice_number'),
                'invoice_date': request.invoice_data.get('invoice_date'),
                'total_amount': request.invoice_data.get('total_amount'),
                'due_date': request.invoice_data.get('due_date'),
                'po_number': request.invoice_data.get('po_number')
            })

        return template_data

    def _select_template_name(self, communication_type: CommunicationType) -> str:
        """Select appropriate email template based on communication type."""
        template_mapping = {
            CommunicationType.VALIDATION_ERROR: 'validation_error',
            CommunicationType.MISSING_INFORMATION: 'missing_information',
            CommunicationType.CALCULATION_ERROR: 'calculation_error',
            CommunicationType.DUPLICATE_INVOICE: 'duplicate_invoice',
            CommunicationType.PROCESSING_CONFIRMATION: 'processing_confirmation',
            CommunicationType.PAYMENT_STATUS: 'payment_status',
            CommunicationType.GENERAL_INQUIRY: 'general_inquiry'
        }

        return template_mapping.get(communication_type, 'validation_error')

    def _determine_communication_type(self, validation_issues: List[ValidationIssue]) -> CommunicationType:
        """Determine communication type based on validation issues."""
        issue_codes = [issue.code for issue in validation_issues]

        # Check for specific issue types
        if any('MISSING_' in code or code.endswith('_REQUIRED') for code in issue_codes):
            return CommunicationType.MISSING_INFORMATION
        elif any('MISMATCH' in code or 'CALCULATION' in code or 'AMOUNT' in code for code in issue_codes):
            return CommunicationType.CALCULATION_ERROR
        elif 'DUPLICATE' in issue_codes:
            return CommunicationType.DUPLICATE_INVOICE
        else:
            return CommunicationType.VALIDATION_ERROR

    def _determine_priority(self, validation_issues: List[ValidationIssue]) -> SeverityLevel:
        """Determine communication priority based on validation issues."""
        if not validation_issues:
            return SeverityLevel.LOW

        severities = [issue.severity for issue in validation_issues]

        if SeverityLevel.URGENT in severities:
            return SeverityLevel.URGENT
        elif SeverityLevel.HIGH in severities:
            return SeverityLevel.HIGH
        elif SeverityLevel.MEDIUM in severities:
            return SeverityLevel.MEDIUM
        else:
            return SeverityLevel.LOW

    def _is_business_hours(self, current_time: datetime, timezone_str: Optional[str] = None) -> bool:
        """Check if current time is within business hours."""
        try:
            # Simple implementation - can be enhanced with proper timezone handling
            hour = current_time.hour
            minute = current_time.minute

            start_time = time.fromisoformat(self.business_hours['start'])
            end_time = time.fromisoformat(self.business_hours['end'])

            current_time_only = time(hour, minute)

            return start_time <= current_time_only <= end_time

        except Exception as e:
            logger.warning(f"Error checking business hours: {e}")
            return True  # Default to allowing communication

    async def _get_recent_communications(
        self,
        vendor_id: str,
        frequency_limit: str
    ) -> List[CommunicationRecord]:
        """Get recent communications for frequency limiting."""
        # This would query the database for recent communications
        # For now, return empty list
        return []

    async def _record_communication(
        self,
        communication_id: str,
        request: VendorCommunicationRequest,
        email_message: EmailMessage,
        email_response: EmailResponse
    ) -> None:
        """Record communication in database."""
        try:
            # This would save to a communications table
            # For now, just log the communication
            logger.info(
                f"Recorded communication {communication_id}: "
                f"Type={request.communication_type}, "
                f"Vendor={request.vendor_contact.vendor_id}, "
                f"Email={request.vendor_contact.email}, "
                f"MessageID={email_response.message_id}"
            )
        except Exception as e:
            logger.error(f"Failed to record communication: {e}")

    async def _render_email_template(
        self,
        template: Dict[str, Any],
        template_data: Dict[str, Any]
    ) -> Tuple[str, str, str]:
        """Render email template with data."""
        try:
            # Use email service template engine
            subject_rendered, _ = await self.email_service.render_template(
                template_content=template['subject_template'],
                template_data=template_data
            )

            html_rendered, text_rendered = await self.email_service.render_template(
                template_content=template['html_template'],
                template_data=template_data
            )

            return subject_rendered, html_rendered, text_rendered

        except Exception as e:
            logger.error(f"Failed to render email template: {e}")
            raise EmailServiceException(f"Template rendering failed: {str(e)}")

    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load email templates."""
        return {
            'validation_error': {
                'subject_template': 'Action Required: Invoice Validation Issues - {{vendor_name}}',
                'html_template': self._get_validation_error_template(),
                'text_template': self._get_validation_error_text_template()
            },
            'missing_information': {
                'subject_template': 'URGENT: Missing Information Required for Invoice {{invoice_number}}',
                'html_template': self._get_missing_information_template(),
                'text_template': self._get_missing_information_text_template()
            },
            'calculation_error': {
                'subject_template': 'Invoice Calculation Discrepancy - {{vendor_name}}',
                'html_template': self._get_calculation_error_template(),
                'text_template': self._get_calculation_error_text_template()
            },
            'duplicate_invoice': {
                'subject_template': 'Duplicate Invoice Alert - {{invoice_number}}',
                'html_template': self._get_duplicate_invoice_template(),
                'text_template': self._get_duplicate_invoice_text_template()
            },
            'processing_confirmation': {
                'subject_template': 'Invoice Processing Confirmation - {{invoice_number}}',
                'html_template': self._get_processing_confirmation_template(),
                'text_template': self._get_processing_confirmation_text_template()
            }
        }

    def _get_validation_error_template(self) -> str:
        """Get validation error email HTML template."""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Invoice Validation Issues</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .header { background-color: #f8f9fa; padding: 20px; border-bottom: 2px solid #dc3545; }
                .content { padding: 20px; }
                .issue { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; }
                .error { border-left-color: #dc3545; background-color: #f8d7da; }
                .footer { background-color: #f8f9fa; padding: 20px; border-top: 1px solid #dee2e6; font-size: 12px; }
                .btn { background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🚨 Action Required: Invoice Validation Issues</h2>
                <p>Dear {{contact_name}},</p>
            </div>

            <div class="content">
                <p>We've encountered validation issues while processing your invoice <strong>{{invoice_number}}</strong> submitted on {{invoice_data.invoice_date}}.</p>

                {% if validation_issues %}
                <h3>Issues Found:</h3>
                {% for issue in validation_issues %}
                <div class="issue {% if issue.severity == 'high' or issue.severity == 'urgent' %}error{% endif %}">
                    <h4>{{issue.description}}</h4>
                    {% if issue.field %}
                    <p><strong>Field:</strong> {{issue.field}}</p>
                    {% endif %}
                    {% if issue.details %}
                    <p><strong>Details:</strong> {{issue.details}}</p>
                    {% endif %}
                    {% if issue.suggested_fix %}
                    <p><strong>Suggested Fix:</strong> {{issue.suggested_fix}}</p>
                    {% endif %}
                </div>
                {% endfor %}
                {% endif %}

                {% if custom_message %}
                <div class="issue">
                    <h4>Additional Information:</h4>
                    <p>{{custom_message}}</p>
                </div>
                {% endif %}

                <h3>Next Steps:</h3>
                <ol>
                    <li>Please review and correct the issues identified above</li>
                    <li>Resubmit the corrected invoice at your earliest convenience</li>
                    <li>Reference invoice number {{invoice_number}} in all communications</li>
                </ol>

                <p><strong>Payment Timeline:</strong> Please note that payment processing will begin only after these issues are resolved.</p>

                {% if support_contact %}
                <p>For questions or assistance, please contact our AP team at <a href="mailto:{{support_contact}}">{{support_contact}}</a></p>
                {% endif %}
            </div>

            <div class="footer">
                <p>This is an automated message from {{company_name}} Accounts Payable Department.</p>
                <p>Communication Date: {{communication_date}}</p>
                <p>If you believe this message was sent in error, please contact {{support_contact}}.</p>
            </div>
        </body>
        </html>
        '''

    def _get_validation_error_text_template(self) -> str:
        """Get validation error email text template."""
        return '''
        ACTION REQUIRED: INVOICE VALIDATION ISSUES

        Dear {{contact_name}},

        We've encountered validation issues while processing your invoice {{invoice_number}} submitted on {{invoice_data.invoice_date}}.

        ISSUES FOUND:
        {% for issue in validation_issues %}
        - {{issue.description}}
        {% if issue.field %}  Field: {{issue.field}}{% endif %}
        {% if issue.details %}  Details: {{issue.details}}{% endif %}
        {% if issue.suggested_fix %}  Suggested Fix: {{issue.suggested_fix}}{% endif %}

        {% endfor %}
        {% if custom_message %}

        ADDITIONAL INFORMATION:
        {{custom_message}}
        {% endif %}

        NEXT STEPS:
        1. Please review and correct the issues identified above
        2. Resubmit the corrected invoice at your earliest convenience
        3. Reference invoice number {{invoice_number}} in all communications

        PAYMENT TIMELINE:
        Please note that payment processing will begin only after these issues are resolved.

        {% if support_contact %}
        For questions or assistance, please contact our AP team at {{support_contact}}
        {% endif %}

        ---
        This is an automated message from {{company_name}} Accounts Payable Department.
        Communication Date: {{communication_date}}
        If you believe this message was sent in error, please contact {{support_contact}}.
        '''

    def _get_missing_information_template(self) -> str:
        """Get missing information email HTML template."""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>URGENT: Missing Information Required</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .header { background-color: #fff3cd; padding: 20px; border-bottom: 2px solid #ffc107; }
                .content { padding: 20px; }
                .urgent { background-color: #f8d7da; border-left: 4px solid #dc3545; padding: 15px; margin: 10px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; border-top: 1px solid #dee2e6; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🚨 URGENT: Missing Information Required</h2>
                <p>Dear {{contact_name}},</p>
            </div>

            <div class="content">
                <p>Your invoice <strong>{{invoice_number}}</strong> cannot be processed because required information is missing.</p>

                {% if validation_issues %}
                <div class="urgent">
                    <h3>Missing Required Information:</h3>
                    {% for issue in validation_issues %}
                    <p><strong>{{issue.description}}</strong></p>
                    {% if issue.field %}<p>Field: {{issue.field}}</p>{% endif %}
                    {% if issue.details %}<p>Details: {{issue.details}}</p>{% endif %}
                    {% endfor %}
                </div>
                {% endif %}

                <h3>Immediate Action Required:</h3>
                <p>Please provide the missing information within 24 hours to avoid payment delays.</p>

                <p><strong>How to Submit:</strong></p>
                <ul>
                    <li>Reply to this email with the missing information</li>
                    <li>Resubmit the complete invoice</li>
                    <li>Reference invoice number {{invoice_number}}</li>
                </ul>

                {% if support_contact %}
                <p>For immediate assistance, please contact: {{support_contact}}</p>
                {% endif %}
            </div>

            <div class="footer">
                <p>This is an automated message from {{company_name}} Accounts Payable Department.</p>
                <p>Communication Date: {{communication_date}}</p>
            </div>
        </body>
        </html>
        '''

    def _get_missing_information_text_template(self) -> str:
        """Get missing information email text template."""
        return '''
        URGENT: MISSING INFORMATION REQUIRED

        Dear {{contact_name}},

        Your invoice {{invoice_number}} cannot be processed because required information is missing.

        MISSING REQUIRED INFORMATION:
        {% for issue in validation_issues %}
        - {{issue.description}}
        {% if issue.field %}  Field: {{issue.field}}{% endif %}
        {% if issue.details %}  Details: {{issue.details}}{% endif %}
        {% endfor %}

        IMMEDIATE ACTION REQUIRED:
        Please provide the missing information within 24 hours to avoid payment delays.

        HOW TO SUBMIT:
        - Reply to this email with the missing information
        - Resubmit the complete invoice
        - Reference invoice number {{invoice_number}}

        {% if support_contact %}
        For immediate assistance, please contact: {{support_contact}}
        {% endif %}

        ---
        This is an automated message from {{company_name}} Accounts Payable Department.
        Communication Date: {{communication_date}}
        '''

    def _get_calculation_error_template(self) -> str:
        """Get calculation error email HTML template."""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Invoice Calculation Discrepancy</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .header { background-color: #d1ecf1; padding: 20px; border-bottom: 2px solid #17a2b8; }
                .content { padding: 20px; }
                .discrepancy { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 10px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; border-top: 1px solid #dee2e6; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ Invoice Calculation Discrepancy</h2>
                <p>Dear {{contact_name}},</p>
            </div>

            <div class="content">
                <p>We've identified calculation discrepancies in your invoice <strong>{{invoice_number}}</strong>.</p>

                {% if validation_issues %}
                <div class="discrepancy">
                    <h3>Calculation Issues:</h3>
                    {% for issue in validation_issues %}
                    <p><strong>{{issue.description}}</strong></p>
                    {% if issue.field %}<p>Field: {{issue.field}}</p>{% endif %}
                    {% if issue.details %}
                    <p>Details:</p>
                    <ul>
                        {% for key, value in issue.details.items() %}
                        <li>{{key}}: {{value}}</li>
                        {% endfor %}
                    </ul>
                    {% endif %}
                    {% endfor %}
                </div>
                {% endif %}

                <h3>Required Actions:</h3>
                <ol>
                    <li>Please review the calculation details above</li>
                    <li>Correct the calculations in your invoice</li>
                    <li>Resubmit the revised invoice</li>
                </ol>

                <p><strong>Important:</strong> Payments will be processed based on the corrected calculations.</p>

                {% if support_contact %}
                <p>For questions about these calculations, please contact: {{support_contact}}</p>
                {% endif %}
            </div>

            <div class="footer">
                <p>This is an automated message from {{company_name}} Accounts Payable Department.</p>
                <p>Communication Date: {{communication_date}}</p>
            </div>
        </body>
        </html>
        '''

    def _get_calculation_error_text_template(self) -> str:
        """Get calculation error email text template."""
        return '''
        INVOICE CALCULATION DISCREPANCY

        Dear {{contact_name}},

        We've identified calculation discrepancies in your invoice {{invoice_number}}.

        CALCULATION ISSUES:
        {% for issue in validation_issues %}
        - {{issue.description}}
        {% if issue.field %}  Field: {{issue.field}}{% endif %}
        {% if issue.details %}
        Details:
        {% for key, value in issue.details.items() %}
        - {{key}}: {{value}}
        {% endfor %}
        {% endif %}
        {% endfor %}

        REQUIRED ACTIONS:
        1. Please review the calculation details above
        2. Correct the calculations in your invoice
        3. Resubmit the revised invoice

        IMPORTANT:
        Payments will be processed based on the corrected calculations.

        {% if support_contact %}
        For questions about these calculations, please contact: {{support_contact}}
        {% endif %}

        ---
        This is an automated message from {{company_name}} Accounts Payable Department.
        Communication Date: {{communication_date}}
        '''

    def _get_duplicate_invoice_template(self) -> str:
        """Get duplicate invoice email HTML template."""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Duplicate Invoice Alert</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .header { background-color: #f8d7da; padding: 20px; border-bottom: 2px solid #dc3545; }
                .content { padding: 20px; }
                .duplicate { background-color: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 10px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; border-top: 1px solid #dee2e6; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🔄 Duplicate Invoice Alert</h2>
                <p>Dear {{contact_name}},</p>
            </div>

            <div class="content">
                <p>We've detected a potential duplicate invoice: <strong>{{invoice_number}}</strong>.</p>

                <div class="duplicate">
                    <h3>Duplicate Detection Details:</h3>
                    <p>This invoice appears to match another invoice already in our system.</p>

                    {% if validation_issues %}
                    {% for issue in validation_issues %}
                    {% if issue.code == 'DUPLICATE_INVOICE' %}
                    <p><strong>{{issue.description}}</strong></p>
                    {% if issue.details %}
                    <p>Match Details:</p>
                    <ul>
                        {% for key, value in issue.details.items() %}
                        <li>{{key}}: {{value}}</li>
                        {% endfor %}
                    </ul>
                    {% endif %}
                    {% endif %}
                    {% endfor %}
                    {% endif %}
                </div>

                <h3>What This Means:</h3>
                <p>This duplicate invoice will not be processed to prevent duplicate payments.</p>

                <h3>Next Steps:</h3>
                <ol>
                    <li>Please verify if this is an intentional resubmission</li>
                    <li>If this is a new invoice, please provide a unique invoice number</li>
                    <li>If this is a correction, please mark it clearly as "Correction"</li>
                </ol>

                {% if support_contact %}
                <p>If you need to clarify the status of this invoice, please contact: {{support_contact}}</p>
                {% endif %}
            </div>

            <div class="footer">
                <p>This is an automated message from {{company_name}} Accounts Payable Department.</p>
                <p>Communication Date: {{communication_date}}</p>
            </div>
        </body>
        </html>
        '''

    def _get_duplicate_invoice_text_template(self) -> str:
        """Get duplicate invoice email text template."""
        return '''
        DUPLICATE INVOICE ALERT

        Dear {{contact_name}},

        We've detected a potential duplicate invoice: {{invoice_number}}.

        DUPLICATE DETECTION DETAILS:
        This invoice appears to match another invoice already in our system.

        {% for issue in validation_issues %}
        {% if issue.code == 'DUPLICATE_INVOICE' %}
        {{issue.description}}
        {% if issue.details %}
        Match Details:
        {% for key, value in issue.details.items() %}
        - {{key}}: {{value}}
        {% endfor %}
        {% endif %}
        {% endif %}
        {% endfor %}

        WHAT THIS MEANS:
        This duplicate invoice will not be processed to prevent duplicate payments.

        NEXT STEPS:
        1. Please verify if this is an intentional resubmission
        2. If this is a new invoice, please provide a unique invoice number
        3. If this is a correction, please mark it clearly as "Correction"

        {% if support_contact %}
        If you need to clarify the status of this invoice, please contact: {{support_contact}}
        {% endif %}

        ---
        This is an automated message from {{company_name}} Accounts Payable Department.
        Communication Date: {{communication_date}}
        '''

    def _get_processing_confirmation_template(self) -> str:
        """Get processing confirmation email HTML template."""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Invoice Processing Confirmation</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .header { background-color: #d4edda; padding: 20px; border-bottom: 2px solid #28a745; }
                .content { padding: 20px; }
                .confirmation { background-color: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 10px 0; }
                .footer { background-color: #f8f9fa; padding: 20px; border-top: 1px solid #dee2e6; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>✅ Invoice Processing Confirmation</h2>
                <p>Dear {{contact_name}},</p>
            </div>

            <div class="content">
                <p>Good news! Your invoice <strong>{{invoice_number}}</strong> has been successfully processed and approved for payment.</p>

                <div class="confirmation">
                    <h3>Processing Details:</h3>
                    <ul>
                        <li><strong>Invoice Number:</strong> {{invoice_number}}</li>
                        <li><strong>Processing Date:</strong> {{communication_date}}</li>
                        <li><strong>Status:</strong> Approved for Payment</li>
                        {% if invoice_data.total_amount %}
                        <li><strong>Amount:</strong> ${{"%.2f"|format(invoice_data.total_amount)}}</li>
                        {% endif %}
                        {% if invoice_data.due_date %}
                        <li><strong>Expected Payment Date:</strong> {{invoice_data.due_date}}</li>
                        {% endif %}
                    </ul>
                </div>

                <h3>What Happens Next:</h3>
                <ul>
                    <li>Your invoice has been queued for payment processing</li>
                    <li>Payment will be made according to our standard payment terms</li>
                    <li>You will receive a payment confirmation when the transaction is complete</li>
                </ul>

                <h3>Payment Information:</h3>
                <p>Payment will be processed to the bank account on file. If you need to update payment details, please contact our AP department.</p>

                {% if support_contact %}
                <p>For questions about this payment, please contact: {{support_contact}}</p>
                {% endif %}
            </div>

            <div class="footer">
                <p>This is an automated message from {{company_name}} Accounts Payable Department.</p>
                <p>Communication Date: {{communication_date}}</p>
            </div>
        </body>
        </html>
        '''

    def _get_processing_confirmation_text_template(self) -> str:
        """Get processing confirmation email text template."""
        return '''
        INVOICE PROCESSING CONFIRMATION

        Dear {{contact_name}},

        Good news! Your invoice {{invoice_number}} has been successfully processed and approved for payment.

        PROCESSING DETAILS:
        - Invoice Number: {{invoice_number}}
        - Processing Date: {{communication_date}}
        - Status: Approved for Payment
        {% if invoice_data.total_amount %}- Amount: ${{"%.2f"|format(invoice_data.total_amount)}}{% endif %}
        {% if invoice_data.due_date %}- Expected Payment Date: {{invoice_data.due_date}}{% endif %}

        WHAT HAPPENS NEXT:
        - Your invoice has been queued for payment processing
        - Payment will be made according to our standard payment terms
        - You will receive a payment confirmation when the transaction is complete

        PAYMENT INFORMATION:
        Payment will be processed to the bank account on file. If you need to update payment details, please contact our AP department.

        {% if support_contact %}
        For questions about this payment, please contact: {{support_contact}}
        {% endif %}

        ---
        This is an automated message from {{company_name}} Accounts Payable Department.
        Communication Date: {{communication_date}}
        '''