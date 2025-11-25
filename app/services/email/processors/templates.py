"""
Email template processor for AP Intake & Validation system.

Implements template rendering and management following Template Method pattern.
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path
import os

from ..base import EmailTemplate


logger = logging.getLogger(__name__)


class TemplateProcessor(EmailTemplate):
    """
    Email template processor.
    
    Handles template rendering and validation with multiple template engines.
    """
    
    def __init__(
        self,
        template_dir: str = "./templates/email",
        default_from_email: str = "noreply@apintake.com",
        default_from_name: str = "AP Intake System"
    ):
        """
        Initialize template processor.
        
        Args:
            template_dir: Directory containing email templates
            default_from_email: Default sender email
            default_from_name: Default sender name
        """
        self.template_dir = Path(template_dir)
        self.default_from_email = default_from_email
        self.default_from_name = default_from_name
        
        # Ensure template directory exists
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        # Available templates
        self.available_templates = self._discover_templates()
        
        logger.info(f"TemplateProcessor initialized with {len(self.available_templates)} templates")
    
    async def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render an email template.
        
        Args:
            template_name: Name of the template
            context: Template context data
            
        Returns:
            Rendered email content
        """
        try:
            logger.info(f"Rendering template: {template_name}")
            
            # Get template file path
            template_path = self._get_template_path(template_name)
            
            if not template_path or not template_path.exists():
                raise ValueError(f"Template '{template_name}' not found")
            
            # Read template content
            template_content = template_path.read_text(encoding='utf-8')
            
            # Simple template rendering (can be extended with Jinja2)
            rendered_content = self._render_template(template_content, context)
            
            logger.info(f"Template '{template_name}' rendered successfully")
            
            return rendered_content
            
        except Exception as e:
            logger.error(f"Error rendering template '{template_name}': {str(e)}")
            raise
    
    def validate_template(self, template_name: str) -> bool:
        """
        Validate if template exists and is valid.
        
        Args:
            template_name: Name of the template
            
        Returns:
            True if template is valid
        """
        try:
            template_path = self._get_template_path(template_name)
            
            if not template_path or not template_path.exists():
                return False
            
            # Basic validation - check if template has required placeholders
            template_content = template_path.read_text(encoding='utf-8')
            
            # Check for common template variables
            required_vars = ['{{', '}}']
            return any(var in template_content for var in required_vars)
            
        except Exception as e:
            logger.error(f"Error validating template '{template_name}': {str(e)}")
            return False
    
    def get_available_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Get list of available templates with metadata.
        
        Returns:
            Dictionary of template information
        """
        templates = {}
        
        for template_name in self.available_templates:
            template_path = self._get_template_path(template_name)
            
            if template_path and template_path.exists():
                stat = template_path.stat()
                templates[template_name] = {
                    'name': template_name,
                    'path': str(template_path),
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'valid': self.validate_template(template_name)
                }
        
        return templates
    
    async def render_invoice_notification(
        self, 
        invoice_data: Dict[str, Any], 
        recipient_email: str
    ) -> Dict[str, str]:
        """
        Render invoice notification email.
        
        Args:
            invoice_data: Invoice information
            recipient_email: Recipient email address
            
        Returns:
            Dictionary with subject and body
        """
        context = {
            'invoice': invoice_data,
            'recipient_email': recipient_email,
            'sender_email': self.default_from_email,
            'sender_name': self.default_from_name,
            'current_date': self._get_current_date()
        }
        
        # Render subject
        subject = await self.render('invoice_notification_subject.txt', context)
        
        # Render body (HTML and text versions)
        html_body = await self.render('invoice_notification_body.html', context)
        text_body = await self.render('invoice_notification_body.txt', context)
        
        return {
            'subject': subject.strip(),
            'html_body': html_body,
            'text_body': text_body,
            'from_email': self.default_from_email,
            'from_name': self.default_from_name
        }
    
    async def render_exception_notification(
        self, 
        exception_data: Dict[str, Any], 
        recipient_email: str
    ) -> Dict[str, str]:
        """
        Render exception notification email.
        
        Args:
            exception_data: Exception information
            recipient_email: Recipient email address
            
        Returns:
            Dictionary with subject and body
        """
        context = {
            'exception': exception_data,
            'recipient_email': recipient_email,
            'sender_email': self.default_from_email,
            'sender_name': self.default_from_name,
            'current_date': self._get_current_date()
        }
        
        # Render subject
        subject = await self.render('exception_notification_subject.txt', context)
        
        # Render body
        html_body = await self.render('exception_notification_body.html', context)
        text_body = await self.render('exception_notification_body.txt', context)
        
        return {
            'subject': subject.strip(),
            'html_body': html_body,
            'text_body': text_body,
            'from_email': self.default_from_email,
            'from_name': self.default_from_name
        }
    
    async def render_weekly_report(
        self, 
        report_data: Dict[str, Any], 
        recipient_email: str
    ) -> Dict[str, str]:
        """
        Render weekly report email.
        
        Args:
            report_data: Weekly report information
            recipient_email: Recipient email address
            
        Returns:
            Dictionary with subject and body
        """
        context = {
            'report': report_data,
            'recipient_email': recipient_email,
            'sender_email': self.default_from_email,
            'sender_name': self.default_from_name,
            'current_date': self._get_current_date()
        }
        
        # Render subject
        subject = await self.render('weekly_report_subject.txt', context)
        
        # Render body
        html_body = await self.render('weekly_report_body.html', context)
        text_body = await self.render('weekly_report_body.txt', context)
        
        return {
            'subject': subject.strip(),
            'html_body': html_body,
            'text_body': text_body,
            'from_email': self.default_from_email,
            'from_name': self.default_from_name
        }
    
    def _discover_templates(self) -> list:
        """
        Discover available templates in template directory.
        
        Returns:
            List of template names
        """
        templates = []
        
        if not self.template_dir.exists():
            return templates
        
        # Look for template files
        for file_path in self.template_dir.rglob("*.html"):
            template_name = file_path.stem
            if template_name not in templates:
                templates.append(template_name)
        
        for file_path in self.template_dir.rglob("*.txt"):
            template_name = file_path.stem
            if template_name not in templates:
                templates.append(template_name)
        
        return sorted(templates)
    
    def _get_template_path(self, template_name: str) -> Optional[Path]:
        """
        Get template file path.
        
        Args:
            template_name: Name of the template
            
        Returns:
            Path to template file or None
        """
        # Try HTML first, then TXT
        for extension in ['.html', '.txt']:
            template_path = self.template_dir / f"{template_name}{extension}"
            if template_path.exists():
                return template_path
        
        return None
    
    def _render_template(self, template_content: str, context: Dict[str, Any]) -> str:
        """
        Render template content with context.
        
        Args:
            template_content: Template content string
            context: Template context data
            
        Returns:
            Rendered content
        """
        # Simple string replacement (can be enhanced with Jinja2)
        rendered = template_content
        
        for key, value in context.items():
            if isinstance(value, dict):
                # Handle nested dictionaries
                for nested_key, nested_value in value.items():
                    placeholder = f"{{{{ {key}.{nested_key} }}}}"
                    rendered = rendered.replace(placeholder, str(nested_value))
            else:
                placeholder = f"{{{{ {key} }}}}"
                rendered = rendered.replace(placeholder, str(value))
        
        return rendered
    
    def _get_current_date(self) -> str:
        """
        Get current date string for templates.
        
        Returns:
            Formatted current date
        """
        from datetime import datetime
        return datetime.now().strftime("%B %d, %Y")
    
    def create_default_templates(self) -> None:
        """
        Create default email templates if they don't exist.
        """
        default_templates = {
            'invoice_notification_subject.txt': (
                "Invoice Processing Notification - {{ invoice.vendor_name|default:'Unknown Vendor' }}"
            ),
            'invoice_notification_body.html': self._get_invoice_notification_html_template(),
            'invoice_notification_body.txt': self._get_invoice_notification_text_template(),
            'exception_notification_subject.txt': (
                "Invoice Processing Exception - {{ exception.reason_code|default:'Processing Error' }}"
            ),
            'exception_notification_body.html': self._get_exception_notification_html_template(),
            'exception_notification_body.txt': self._get_exception_notification_text_template(),
            'weekly_report_subject.txt': (
                "Weekly AP Processing Report - {{ report.week_start_date|default:'This Week' }}"
            ),
            'weekly_report_body.html': self._get_weekly_report_html_template(),
            'weekly_report_body.txt': self._get_weekly_report_text_template()
        }
        
        created_count = 0
        for template_name, content in default_templates.items():
            template_path = self.template_dir / template_name
            if not template_path.exists():
                template_path.parent.mkdir(parents=True, exist_ok=True)
                template_path.write_text(content, encoding='utf-8')
                created_count += 1
                logger.info(f"Created default template: {template_name}")
        
        if created_count > 0:
            logger.info(f"Created {created_count} default email templates")
    
    def _get_invoice_notification_html_template(self) -> str:
        """Get HTML template for invoice notification."""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Invoice Processing Notification</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .content { background: #ffffff; padding: 20px; border-radius: 5px; border: 1px solid #dee2e6; }
        .footer { background: #f8f9fa; padding: 20px; border-radius: 5px; margin-top: 20px; font-size: 12px; color: #666; }
        .btn { display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }
        .field { margin-bottom: 10px; }
        .label { font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Invoice Processing Notification</h2>
            <p>An invoice has been processed in the AP Intake system.</p>
        </div>
        
        <div class="content">
            {% if invoice.vendor_name %}
            <div class="field">
                <span class="label">Vendor:</span> {{ invoice.vendor_name }}
            </div>
            {% endif %}
            
            {% if invoice.invoice_date %}
            <div class="field">
                <span class="label">Invoice Date:</span> {{ invoice.invoice_date }}
            </div>
            {% endif %}
            
            {% if invoice.invoice_amount %}
            <div class="field">
                <span class="label">Amount:</span> ${{ invoice.invoice_amount }}
            </div>
            {% endif %}
            
            {% if invoice.confidence %}
            <div class="field">
                <span class="label">Processing Confidence:</span> {{ "%.1f"|format(invoice.confidence * 100) }}%
            </div>
            {% endif %}
            
            <div style="margin-top: 20px;">
                <a href="{{ dashboard_url|default:'#' }}" class="btn">View in Dashboard</a>
            </div>
        </div>
        
        <div class="footer">
            <p>This is an automated message from {{ sender_name }}.</p>
            <p>If you have questions, please contact support.</p>
            <p>Sent on {{ current_date }}</p>
        </div>
    </div>
</body>
</html>
        """.strip()
    
    def _get_invoice_notification_text_template(self) -> str:
        """Get text template for invoice notification."""
        return """
Invoice Processing Notification

An invoice has been processed in the AP Intake system.

{% if invoice.vendor_name %}
Vendor: {{ invoice.vendor_name }}
{% endif %}

{% if invoice.invoice_date %}
Invoice Date: {{ invoice.invoice_date }}
{% endif %}

{% if invoice.invoice_amount %}
Amount: ${{ invoice.invoice_amount }}
{% endif %}

{% if invoice.confidence %}
Processing Confidence: {{ "%.1f"|format(invoice.confidence * 100) }}%
{% endif %}

---
This is an automated message from {{ sender_name }}.
If you have questions, please contact support.
Sent on {{ current_date }}
        """.strip()
    
    def _get_exception_notification_html_template(self) -> str:
        """Get HTML template for exception notification."""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Invoice Processing Exception</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #f8d7da; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .content { background: #ffffff; padding: 20px; border-radius: 5px; border: 1px solid #dee2e6; }
        .footer { background: #f8f9fa; padding: 20px; border-radius: 5px; margin-top: 20px; font-size: 12px; color: #666; }
        .btn { display: inline-block; padding: 10px 20px; background: #dc3545; color: white; text-decoration: none; border-radius: 5px; }
        .error { background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Invoice Processing Exception</h2>
            <p>An exception occurred during invoice processing.</p>
        </div>
        
        <div class="content">
            <div class="error">
                <strong>Exception Code:</strong> {{ exception.reason_code|default:'Unknown' }}
            </div>
            
            {% if exception.details %}
            <div class="error">
                <strong>Details:</strong> {{ exception.details }}
            </div>
            {% endif %}
            
            {% if exception.invoice_id %}
            <div style="margin: 10px 0;">
                <strong>Invoice ID:</strong> {{ exception.invoice_id }}
            </div>
            {% endif %}
            
            <div style="margin-top: 20px;">
                <a href="{{ dashboard_url|default:'#' }}" class="btn">Review in Dashboard</a>
            </div>
        </div>
        
        <div class="footer">
            <p>This is an automated message from {{ sender_name }}.</p>
            <p>If you have questions, please contact support.</p>
            <p>Sent on {{ current_date }}</p>
        </div>
    </div>
</body>
</html>
        """.strip()
    
    def _get_exception_notification_text_template(self) -> str:
        """Get text template for exception notification."""
        return """
Invoice Processing Exception

An exception occurred during invoice processing.

Exception Code: {{ exception.reason_code|default:'Unknown' }}

{% if exception.details %}
Details: {{ exception.details }}
{% endif %}

{% if exception.invoice_id %}
Invoice ID: {{ exception.invoice_id }}
{% endif %}

---
This is an automated message from {{ sender_name }}.
If you have questions, please contact support.
Sent on {{ current_date }}
        """.strip()
    
    def _get_weekly_report_html_template(self) -> str:
        """Get HTML template for weekly report."""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Weekly AP Processing Report</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 800px; margin: 0 auto; padding: 20px; }
        .header { background: #e9ecef; padding: 20px; border-radius: 5px; margin-bottom: 20px; text-align: center; }
        .content { background: #ffffff; padding: 20px; border-radius: 5px; border: 1px solid #dee2e6; }
        .footer { background: #f8f9fa; padding: 20px; border-radius: 5px; margin-top: 20px; font-size: 12px; color: #666; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
        .metric { background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #007bff; }
        .metric-label { font-size: 14px; color: #666; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Weekly AP Processing Report</h2>
            <p>Report for {{ report.week_start_date|default:'This Week' }} to {{ report.week_end_date|default:'Today' }}</p>
        </div>
        
        <div class="content">
            <h3>Processing Metrics</h3>
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value">{{ report.invoices_processed|default:0 }}</div>
                    <div class="metric-label">Invoices Processed</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{{ report.auto_processed|default:0 }}</div>
                    <div class="metric-label">Auto Processed</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{{ "%.1f"|format(report.auto_processing_rate * 100) }}%</div>
                    <div class="metric-label">Auto Processing Rate</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{{ report.exceptions_created|default:0 }}</div>
                    <div class="metric-label">Exceptions Created</div>
                </div>
            </div>
            
            {% if report.performance_summary %}
            <h3>Performance Summary</h3>
            <p>{{ report.performance_summary }}</p>
            {% endif %}
            
            <div style="margin-top: 30px; text-align: center;">
                <a href="{{ dashboard_url|default:'#' }}" style="display: inline-block; padding: 12px 24px; background: #007bff; color: white; text-decoration: none; border-radius: 5px;">View Full Dashboard</a>
            </div>
        </div>
        
        <div class="footer">
            <p>This is an automated weekly report from {{ sender_name }}.</p>
            <p>Generated on {{ current_date }}</p>
        </div>
    </div>
</body>
</html>
        """.strip()
    
    def _get_weekly_report_text_template(self) -> str:
        """Get text template for weekly report."""
        return """
Weekly AP Processing Report

Report for {{ report.week_start_date|default:'This Week' }} to {{ report.week_end_date|default:'Today' }}

Processing Metrics:
- Invoices Processed: {{ report.invoices_processed|default:0 }}
- Auto Processed: {{ report.auto_processed|default:0 }}
- Auto Processing Rate: {{ "%.1f"|format(report.auto_processing_rate * 100) }}%
- Exceptions Created: {{ report.exceptions_created|default:0 }}

{% if report.performance_summary %}
Performance Summary:
{{ report.performance_summary }}
{% endif %}

---
This is an automated weekly report from {{ sender_name }}.
Generated on {{ current_date }}
        """.strip()