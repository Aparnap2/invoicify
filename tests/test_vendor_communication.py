"""
TDD test suite for vendor communication automation.

This test suite follows Test-Driven Development principles:
1. Write failing tests first
2. Implement minimal code to make tests pass
3. Refactor with confidence

Tests are written before implementation to ensure requirements drive development.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

# These imports will fail initially - that's expected in TDD
from app.services.email_service import EmailService, EmailProvider, EmailMessage, EmailResponse
from app.services.vendor_communication_service import (
    VendorCommunicationService,
    CommunicationTemplate,
    VendorContact,
    CommunicationRecord,
    CommunicationTrigger
)
from app.schemas.communication import (
    EmailTemplateRequest,
    VendorCommunicationRequest,
    CommunicationHistoryResponse
)


class TestEmailServiceAbstraction:
    """Test email service abstraction layer (FAILING TESTS - TDD Approach)."""

    @pytest.fixture
    def email_service(self):
        """Create email service instance."""
        return EmailService()

    @pytest.mark.asyncio
    async def test_send_email_with_mailgun_provider(self, email_service):
        """Test sending email via Mailgun provider."""
        email_message = EmailMessage(
            to="vendor@example.com",
            from_email="ap@company.com",
            subject="Invoice Validation Issue",
            html_content="<p>Your invoice has validation errors.</p>",
            text_content="Your invoice has validation errors.",
            template_data={"invoice_number": "INV-123", "vendor_name": "Test Vendor"}
        )

        # This should fail because EmailService is not implemented yet
        with patch('app.services.email_service.settings.MAILGUN_API_KEY', 'test_key'), \
             patch('app.services.email_service.settings.MAILGUN_DOMAIN', 'test_domain'):

            response = await email_service.send_email(
                message=email_message,
                provider=EmailProvider.MAILGUN
            )

        # These assertions should drive the implementation
        assert response.success is True
        assert response.message_id is not None
        assert response.provider == EmailProvider.MAILGUN
        assert "test_domain" in response.provider_response.get("message", "")

    @pytest.mark.asyncio
    async def test_send_email_with_sendgrid_provider(self, email_service):
        """Test sending email via SendGrid provider."""
        email_message = EmailMessage(
            to="vendor@example.com",
            from_email="ap@company.com",
            subject="Invoice Validation Issue",
            html_content="<p>Your invoice has validation errors.</p>",
            text_content="Your invoice has validation errors."
        )

        with patch('app.services.email_service.settings.SENDGRID_API_KEY', 'test_key'):
            response = await email_service.send_email(
                message=email_message,
                provider=EmailProvider.SENDGRID
            )

        assert response.success is True
        assert response.message_id is not None
        assert response.provider == EmailProvider.SENDGRID

    @pytest.mark.asyncio
    async def test_email_template_rendering(self, email_service):
        """Test email template rendering with dynamic data."""
        template_content = """
        <h1>Invoice Validation Issue</h1>
        <p>Dear {{vendor_name}},</p>
        <p>Your invoice {{invoice_number}} has the following issues:</p>
        <ul>
        {% for issue in validation_issues %}
            <li>{{issue.description}}</li>
        {% endfor %}
        </ul>
        <p>Please correct and resubmit.</p>
        """

        template_data = {
            "vendor_name": "Test Vendor",
            "invoice_number": "INV-123",
            "validation_issues": [
                {"description": "Missing PO number"},
                {"description": "Amount mismatch"}
            ]
        }

        # This should fail because template rendering is not implemented
        rendered_html, rendered_text = await email_service.render_template(
            template_content=template_content,
            template_data=template_data
        )

        assert "Test Vendor" in rendered_html
        assert "INV-123" in rendered_html
        assert "Missing PO number" in rendered_html
        assert "Amount mismatch" in rendered_html

    @pytest.mark.asyncio
    async def test_email_provider_fallback(self, email_service):
        """Test email provider fallback when primary provider fails."""
        email_message = EmailMessage(
            to="vendor@example.com",
            from_email="ap@company.com",
            subject="Test Email",
            html_content="<p>Test content</p>"
        )

        # Mock primary provider failure
        with patch('app.services.email_service.settings.MAILGUN_API_KEY', 'test_key'), \
             patch.object(email_service, '_send_via_mailgun', side_effect=Exception("Mailgun failed")), \
             patch('app.services.email_service.settings.SENDGRID_API_KEY', 'test_key'):

            response = await email_service.send_email_with_fallback(
                message=email_message,
                primary_provider=EmailProvider.MAILGUN,
                fallback_provider=EmailProvider.SENDGRID
            )

        assert response.success is True
        assert response.provider == EmailProvider.SENDGRID
        assert response.fallback_used is True

    @pytest.mark.asyncio
    async def test_email_queue_and_retry_logic(self, email_service):
        """Test email queue management and retry logic."""
        failed_email = EmailMessage(
            to="vendor@example.com",
            from_email="ap@company.com",
            subject="Test Email",
            html_content="<p>Test content</p>"
        )

        # Mock provider failures followed by success
        with patch('app.services.email_service.settings.MAILGUN_API_KEY', 'test_key') as mock_send:
            mock_send.side_effect = [
                Exception("First failure"),
                Exception("Second failure"),
                {"id": "success_message_id", "status": "sent"}
            ]

            response = await email_service.send_with_retry(
                message=failed_email,
                provider=EmailProvider.MAILGUN,
                max_retries=3
            )

        assert response.success is True
        assert response.retry_count == 2

    def test_email_validation_and_security(self, email_service):
        """Test email validation and security checks."""
        # Test invalid email addresses
        invalid_emails = [
            "not-an-email",
            "@invalid.com",
            "invalid@",
            "invalid..email@example.com"
        ]

        for invalid_email in invalid_emails:
            is_valid = email_service.validate_email_address(invalid_email)
            assert is_valid is False, f"Email {invalid_email} should be invalid"

        # Test valid email addresses
        valid_emails = [
            "valid@example.com",
            "test.email@company.co.uk",
            "user+tag@domain.org"
        ]

        for valid_email in valid_emails:
            is_valid = email_service.validate_email_address(valid_email)
            assert is_valid is True, f"Email {valid_email} should be valid"

        # Test content security checks
        malicious_content = "<script>alert('xss')</script>"
        is_safe = email_service.validate_email_content(malicious_content)
        assert is_safe is False

        safe_content = "<p>This is safe content</p>"
        is_safe = email_service.validate_email_content(safe_content)
        assert is_safe is True


class TestVendorCommunicationService:
    """Test vendor communication service (FAILING TESTS - TDD Approach)."""

    @pytest.fixture
    def communication_service(self):
        """Create vendor communication service instance."""
        return VendorCommunicationService()

    @pytest.fixture
    def sample_vendor_contact(self):
        """Sample vendor contact for testing."""
        return VendorContact(
            vendor_id="vendor_123",
            contact_name="John Doe",
            email="john.doe@vendorcompany.com",
            phone="+1-555-123-4567",
            is_primary=True,
            preferred_contact_method="email"
        )

    @pytest.fixture
    def sample_validation_issues(self):
        """Sample validation issues for testing."""
        return [
            {
                "code": "MISSING_PO_NUMBER",
                "description": "Purchase Order number is required",
                "field": "po_number",
                "severity": "error"
            },
            {
                "code": "AMOUNT_MISMATCH",
                "description": "Invoice total doesn't match line items",
                "field": "total_amount",
                "severity": "error",
                "details": {
                    "invoice_total": 1500.00,
                    "calculated_total": 1450.00,
                    "difference": 50.00
                }
            }
        ]

    @pytest.mark.asyncio
    async def test_send_validation_error_notification(
        self,
        communication_service,
        sample_vendor_contact,
        sample_validation_issues
    ):
        """Test sending validation error notification to vendor."""
        request = VendorCommunicationRequest(
            invoice_id="invoice_123",
            vendor_contact=sample_vendor_contact,
            communication_type="validation_error",
            invoice_data={
                "invoice_number": "INV-2024-001",
                "invoice_date": "2024-01-15",
                "total_amount": 1500.00,
                "vendor_name": "Test Vendor Corp"
            },
            validation_issues=sample_validation_issues,
            custom_message="Please review and correct the identified issues."
        )

        # This should fail because the service is not implemented yet
        response = await communication_service.send_communication(request)

        # These assertions drive the implementation
        assert response.success is True
        assert response.communication_id is not None
        assert response.communication_type == "validation_error"
        assert response.sent_at is not None
        assert response.vendor_contact.email == "john.doe@vendorcompany.com"

    @pytest.mark.asyncio
    async def test_template_selection_for_validation_errors(
        self,
        communication_service,
        sample_validation_issues
    ):
        """Test automatic template selection based on validation error types."""
        # Test missing required fields template
        missing_fields_request = EmailTemplateRequest(
            template_type="missing_required_fields",
            validation_issues=[issue for issue in sample_validation_issues if issue["code"] == "MISSING_PO_NUMBER"]
        )

        template = await communication_service._select_template(missing_fields_request)
        assert template.template_name == "validation_missing_fields"
        assert "missing required information" in template.subject.lower()

        # Test calculation errors template
        calculation_request = EmailTemplateRequest(
            template_type="calculation_error",
            validation_issues=[issue for issue in sample_validation_issues if issue["code"] == "AMOUNT_MISMATCH"]
        )

        template = await communication_service._select_template(calculation_request)
        assert template.template_name == "validation_calculation_error"
        assert "calculation" in template.subject.lower()

    @pytest.mark.asyncio
    async def test_communication_history_tracking(self, communication_service):
        """Test tracking of communication history."""
        vendor_id = "vendor_123"
        invoice_id = "invoice_456"

        # This should fail because history tracking is not implemented
        history = await communication_service.get_communication_history(
            vendor_id=vendor_id,
            invoice_id=invoice_id,
            limit=10
        )

        assert isinstance(history, list)
        assert len(history) >= 0

        # If there are communications, they should have required fields
        for communication in history:
            assert hasattr(communication, 'communication_id')
            assert hasattr(communication, 'sent_at')
            assert hasattr(communication, 'communication_type')
            assert hasattr(communication, 'vendor_contact')

    @pytest.mark.asyncio
    async def test_vendor_contact_resolution(self, communication_service):
        """Test vendor contact information resolution."""
        invoice_data = {
            "vendor_name": "Test Vendor Corp",
            "vendor_email": "billing@testvendor.com",
            "invoice_number": "INV-2024-001"
        }

        # This should fail because contact resolution is not implemented
        vendor_contact = await communication_service.resolve_vendor_contact(invoice_data)

        assert vendor_contact is not None
        assert vendor_contact.email == "billing@testvendor.com"
        assert vendor_contact.vendor_name == "Test Vendor Corp"
        assert vendor_contact.is_primary is True

    @pytest.mark.asyncio
    async def test_communication_triggers(self, communication_service):
        """Test automatic communication triggers based on validation results."""
        validation_result = {
            "passed": False,
            "error_count": 2,
            "issues": [
                {
                    "code": "MISSING_PO_NUMBER",
                    "severity": "error",
                    "requires_vendor_action": True
                },
                {
                    "code": "DUPLICATE_INVOICE",
                    "severity": "warning",
                    "requires_vendor_action": False
                }
            ]
        }

        invoice_data = {
            "invoice_id": "invoice_123",
            "vendor_name": "Test Vendor",
            "vendor_email": "contact@testvendor.com"
        }

        # This should fail because trigger logic is not implemented
        should_communicate, trigger_type = await communication_service.evaluate_communication_trigger(
            validation_result=validation_result,
            invoice_data=invoice_data
        )

        assert should_communicate is True
        assert trigger_type == CommunicationTrigger.VENDOR_ACTION_REQUIRED

    @pytest.mark.asyncio
    async def test_batch_communication_processing(self, communication_service):
        """Test processing multiple communications in batch."""
        batch_requests = [
            {
                "invoice_id": f"invoice_{i}",
                "vendor_contact": VendorContact(
                    vendor_id=f"vendor_{i}",
                    email=f"contact{i}@vendor{i}.com",
                    contact_name=f"Contact {i}"
                ),
                "communication_type": "validation_error",
                "validation_issues": [
                    {
                        "code": "MISSING_PO_NUMBER",
                        "description": "PO number required",
                        "severity": "error"
                    }
                ]
            }
            for i in range(3)
        ]

        # This should fail because batch processing is not implemented
        responses = await communication_service.send_batch_communications(batch_requests)

        assert len(responses) == 3
        for response in responses:
            assert response.communication_id is not None
            assert response.success is True

    @pytest.mark.asyncio
    async def test_communication_preferences(self, communication_service):
        """Test respecting vendor communication preferences."""
        vendor_contact = VendorContact(
            vendor_id="vendor_123",
            contact_name="Jane Smith",
            email="jane@vendor.com",
            phone="+1-555-987-6543",
            preferred_contact_method="email",
            communication_preferences={
                "business_hours_only": True,
                "timezone": "America/New_York",
                "frequency_limit": "max_1_per_day"
            }
        )

        request = VendorCommunicationRequest(
            invoice_id="invoice_123",
            vendor_contact=vendor_contact,
            communication_type="validation_error",
            validation_issues=[{"code": "TEST", "description": "Test issue"}]
        )

        # Mock current time outside business hours
        with patch('app.services.vendor_communication_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 15, 18, 0, 0)  # 6 PM

            # Should respect business hours preference
            can_send, reason = await communication_service.check_communication_timing(request)

            if vendor_contact.communication_preferences.get("business_hours_only"):
                assert can_send is False
                assert "business hours" in reason.lower()

    @pytest.mark.asyncio
    async def test_email_content_personalization(self, communication_service):
        """Test email content personalization based on vendor data."""
        request = VendorCommunicationRequest(
            invoice_id="invoice_123",
            vendor_contact=VendorContact(
                vendor_id="vendor_123",
                contact_name="Robert Johnson",
                email="robert@vendorcorp.com",
                company_name="Vendor Corp International"
            ),
            communication_type="validation_error",
            invoice_data={
                "invoice_number": "INV-2024-001",
                "total_amount": 2500.00,
                "due_date": "2024-02-15"
            },
            validation_issues=[
                {
                    "code": "MISSING_PO_NUMBER",
                    "description": "Purchase Order number is required",
                    "field": "po_number"
                }
            ]
        )

        # This should fail because personalization is not implemented
        personalized_content = await communication_service._personalize_email_content(request)

        assert "Robert Johnson" in personalized_content["html"]
        assert "Vendor Corp International" in personalized_content["html"]
        assert "INV-2024-001" in personalized_content["html"]
        assert "$2,500.00" in personalized_content["html"]
        assert "Purchase Order number" in personalized_content["html"]


class TestEmailTemplates:
    """Test email templates for different vendor communication scenarios."""

    @pytest.mark.asyncio
    async def test_validation_error_template_rendering(self):
        """Test rendering of validation error email template."""
        template_data = {
            "vendor_name": "Test Vendor Corp",
            "contact_name": "John Doe",
            "invoice_number": "INV-2024-001",
            "invoice_date": "January 15, 2024",
            "total_amount": "$1,500.00",
            "validation_issues": [
                {
                    "description": "Purchase Order number is missing",
                    "field": "po_number",
                    "severity": "error"
                },
                {
                    "description": "Invoice total ($1,500.00) doesn't match line items total ($1,450.00)",
                    "field": "total_amount",
                    "severity": "error",
                    "details": {
                        "difference": "$50.00"
                    }
                }
            ],
            "action_required": True,
            "support_contact": "ap-support@company.com"
        }

        # This should fail because templates are not implemented yet
        from app.services.vendor_communication_service import VendorCommunicationService
        service = VendorCommunicationService()

        rendered_email = await service._render_template(
            template_name="validation_error",
            template_data=template_data
        )

        # Verify template content
        assert "Test Vendor Corp" in rendered_email["subject"]
        assert "validation errors" in rendered_email["subject"].lower()
        assert "John Doe" in rendered_email["html"]
        assert "INV-2024-001" in rendered_email["html"]
        assert "Purchase Order number" in rendered_email["html"]
        assert "$1,500.00" in rendered_email["html"]
        assert "$50.00" in rendered_email["html"]
        assert "ap-support@company.com" in rendered_email["html"]

    @pytest.mark.asyncio
    async def test_missing_information_template_rendering(self):
        """Test rendering of missing information request template."""
        template_data = {
            "vendor_name": "Global Supplies Inc",
            "contact_name": "Sarah Chen",
            "invoice_number": "GS-2024-042",
            "missing_fields": [
                {
                    "field_name": "Purchase Order Number",
                    "field_value": "",
                    "required": True,
                    "description": "PO number is required for all invoices over $1,000"
                },
                {
                    "field_name": "Project Code",
                    "field_value": "",
                    "required": True,
                    "description": "Project code for expense allocation"
                }
            ],
            "urgent": True,
            "support_contact": "ap-support@company.com"
        }

        from app.services.vendor_communication_service import VendorCommunicationService
        service = VendorCommunicationService()

        rendered_email = await service._render_template(
            template_name="missing_information",
            template_data=template_data
        )

        assert "URGENT" in rendered_email["subject"] or "Action Required" in rendered_email["subject"]
        assert "Global Supplies Inc" in rendered_email["html"]
        assert "GS-2024-042" in rendered_email["html"]
        assert "Purchase Order Number" in rendered_email["html"]
        assert "Project Code" in rendered_email["html"]
        assert "Sarah Chen" in rendered_email["html"]

    @pytest.mark.asyncio
    async def test_confirmation_template_rendering(self):
        """Test rendering of invoice processing confirmation template."""
        template_data = {
            "vendor_name": "Quality Services LLC",
            "contact_name": "Michael Brown",
            "invoice_number": "QS-2024-001",
            "processing_status": "approved",
            "payment_date": "February 15, 2024",
            "payment_amount": "$3,250.00",
            "processed_date": "January 20, 2024",
            "reference_number": "REF-789456"
        }

        from app.services.vendor_communication_service import VendorCommunicationService
        service = VendorCommunicationService()

        rendered_email = await service._render_template(
            template_name="processing_confirmation",
            template_data=template_data
        )

        assert "approved" in rendered_email["subject"].lower() or "processed" in rendered_email["subject"].lower()
        assert "Quality Services LLC" in rendered_email["html"]
        assert "QS-2024-001" in rendered_email["html"]
        assert "February 15, 2024" in rendered_email["html"]
        assert "$3,250.00" in rendered_email["html"]
        assert "REF-789456" in rendered_email["html"]


# Integration test scenarios
class TestVendorCommunicationIntegration:
    """End-to-end tests for vendor communication automation."""

    @pytest.mark.asyncio
    async def test_full_validation_error_workflow(self):
        """Test complete workflow from validation failure to vendor communication."""
        # Simulate validation failure
        validation_result = {
            "passed": False,
            "error_count": 2,
            "validation_session_id": "session_123",
            "issues": [
                {
                    "code": "MISSING_PO_NUMBER",
                    "message": "Purchase Order number is required",
                    "field": "po_number",
                    "severity": "error",
                    "requires_vendor_action": True
                },
                {
                    "code": "INVALID_VENDOR_TAX_ID",
                    "message": "Vendor tax ID format is invalid",
                    "field": "vendor_tax_id",
                    "severity": "error",
                    "requires_vendor_action": True
                }
            ]
        }

        invoice_data = {
            "invoice_id": "invoice_456",
            "invoice_number": "INV-2024-789",
            "vendor_name": "Test Vendor Company",
            "vendor_email": "billing@testvendor.com",
            "total_amount": 2500.00,
            "invoice_date": "2024-01-18"
        }

        # This should fail because integration is not implemented
        from app.services.vendor_communication_service import VendorCommunicationService
        service = VendorCommunicationService()

        communication_response = await service.handle_validation_failure(
            validation_result=validation_result,
            invoice_data=invoice_data
        )

        assert communication_response.success is True
        assert communication_response.communication_id is not None
        assert communication_response.email_sent is True
        assert communication_response.vendor_contacted is True

        # Verify communication was recorded
        history = await service.get_communication_history(
            vendor_id=None,  # Will be resolved from invoice data
            invoice_id="invoice_456"
        )

        assert len(history) > 0
        latest_communication = history[0]
        assert latest_communication.communication_type == "validation_error"
        assert "billing@testvendor.com" in latest_communication.recipient_email