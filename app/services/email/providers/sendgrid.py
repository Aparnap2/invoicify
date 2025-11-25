"""
SendGrid email provider for AP Intake & Validation system.

Implements EmailProvider interface for SendGrid API integration.
"""

import logging
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Attachment, Content, Email, To
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    SendGridAPIClient = None
    Mail = None

from ..base import EmailProvider, EmailMessage, EmailAttachment


logger = logging.getLogger(__name__)


class SendGridProvider(EmailProvider):
    """
    SendGrid email provider implementation.
    
    Handles SendGrid API operations for sending emails.
    Note: SendGrid is primarily for sending, not receiving emails.
    """
    
    def __init__(self, api_key: str, from_email: str, from_name: str = "AP Intake System"):
        """
        Initialize SendGrid provider.
        
        Args:
            api_key: SendGrid API key
            from_email: Default sender email
            from_name: Default sender name
        """
        if not SENDGRID_AVAILABLE:
            raise ImportError("SendGrid package not installed. Install with: pip install sendgrid")
        
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.client = None
        
        logger.info("SendGridProvider initialized")
    
    async def authenticate(self, **kwargs) -> bool:
        """
        Authenticate with SendGrid API.
        
        Returns:
            True if authentication successful
        """
        try:
            logger.info("Authenticating with SendGrid API")
            
            # Create SendGrid client
            self.client = SendGridAPIClient(api_key=self.api_key)
            
            # Test authentication by getting API limits
            response = self.client.client.api_keys.get()
            
            if response.status_code == 200:
                logger.info("SendGrid authentication successful")
                return True
            else:
                logger.error(f"SendGrid authentication failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"SendGrid authentication error: {str(e)}")
            return False
    
    async def fetch_emails(
        self, 
        limit: int = 50, 
        folder: str = "INBOX",
        since: Optional[datetime] = None
    ) -> List[EmailMessage]:
        """
        SendGrid is primarily for sending emails, not receiving.
        This method returns an empty list.
        
        Returns:
            Empty list (SendGrid doesn't support email retrieval)
        """
        logger.warning("SendGrid provider does not support email fetching")
        return []
    
    async def send_email(self, email_message: EmailMessage) -> bool:
        """
        Send email via SendGrid API.
        
        Args:
            email_message: Email message to send
            
        Returns:
            True if email sent successfully
        """
        try:
            if not self.client:
                await self.authenticate()
            
            logger.info(f"Sending email to {email_message.to_email}")
            
            # Create SendGrid message
            message = Mail(
                from_email=Email(self.from_email, self.from_name),
                to_emails=To(email_message.to_email),
                subject=email_message.subject
            )
            
            # Add content
            if email_message.html_body:
                message.add_content(Content("text/html", email_message.html_body))
            
            if email_message.body:
                message.add_content(Content("text/plain", email_message.body))
            
            # Add CC if present
            if email_message.cc_email:
                message.add_cc(Email(email_message.cc_email))
            
            # Add attachments
            for attachment in email_message.attachments:
                sendgrid_attachment = self._create_sendgrid_attachment(attachment)
                if sendgrid_attachment:
                    message.add_attachment(sendgrid_attachment)
            
            # Send message
            response = self.client.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"Email sent successfully via SendGrid: {response.headers.get('X-Message-Id')}")
                return True
            else:
                logger.error(f"SendGrid send failed: {response.status_code} - {response.body}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email via SendGrid: {str(e)}")
            return False
    
    async def mark_as_read(self, message_id: str) -> bool:
        """
        SendGrid does not support email operations like marking as read.
        
        Returns:
            False (not supported)
        """
        logger.warning("SendGrid provider does not support marking emails as read")
        return False
    
    async def move_to_folder(self, message_id: str, folder: str) -> bool:
        """
        SendGrid does not support email operations like moving to folders.
        
        Returns:
            False (not supported)
        """
        logger.warning("SendGrid provider does not support moving emails to folders")
        return False
    
    def _create_sendgrid_attachment(self, attachment: EmailAttachment) -> Optional[Attachment]:
        """
        Create SendGrid attachment from EmailAttachment.
        
        Args:
            attachment: EmailAttachment object
            
        Returns:
            SendGrid Attachment object or None
        """
        try:
            if not attachment.content:
                return None
            
            # Encode content
            encoded_content = base64.b64encode(attachment.content).decode()
            
            # Create SendGrid attachment
            sendgrid_attachment = Attachment()
            sendgrid_attachment.file_content = encoded_content
            sendgrid_attachment.file_type = attachment.content_type
            sendgrid_attachment.file_name = attachment.filename
            sendgrid_attachment.disposition = "attachment"
            
            return sendgrid_attachment
            
        except Exception as e:
            logger.error(f"Error creating SendGrid attachment: {str(e)}")
            return None
    
    async def send_template_email(
        self, 
        template_id: str, 
        recipient_email: str,
        template_data: Dict[str, Any],
        subject: Optional[str] = None
    ) -> bool:
        """
        Send email using SendGrid template.
        
        Args:
            template_id: SendGrid template ID
            recipient_email: Recipient email address
            template_data: Template substitution data
            subject: Optional subject override
            
        Returns:
            True if email sent successfully
        """
        try:
            if not self.client:
                await self.authenticate()
            
            logger.info(f"Sending template email {template_id} to {recipient_email}")
            
            # Create message with template
            message = Mail(
                from_email=Email(self.from_email, self.from_name),
                to_emails=To(recipient_email)
            )
            
            # Set template
            message.template_id = template_id
            
            # Add template data
            message.dynamic_template_data = template_data
            
            # Override subject if provided
            if subject:
                message.subject = subject
            
            # Send message
            response = self.client.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"Template email sent successfully: {response.headers.get('X-Message-Id')}")
                return True
            else:
                logger.error(f"Template email send failed: {response.status_code} - {response.body}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending template email: {str(e)}")
            return False
    
    async def get_send_stats(self) -> Dict[str, Any]:
        """
        Get SendGrid sending statistics.
        
        Returns:
            Dictionary with sending statistics
        """
        try:
            if not self.client:
                await self.authenticate()
            
            # Get global stats
            response = self.client.client.stats.get(
                query_params={"aggregated_by": "day", "limit": 1}
            )
            
            if response.status_code == 200:
                stats = response.body
                return {
                    'requests': stats[0].get('requests', 0),
                    'delivered': stats[0].get('delivered', 0),
                    'opens': stats[0].get('opens', 0),
                    'clicks': stats[0].get('clicks', 0),
                    'bounces': stats[0].get('bounces', 0),
                    'spam_reports': stats[0].get('spam_reports', 0)
                }
            else:
                logger.error(f"Failed to get SendGrid stats: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting SendGrid stats: {str(e)}")
            return {}
    
    async def validate_email(self, email_address: str) -> bool:
        """
        Validate email address using SendGrid Email Validation API.
        
        Args:
            email_address: Email address to validate
            
        Returns:
            True if email is valid
        """
        try:
            if not self.client:
                await self.authenticate()
            
            # Use SendGrid Email Validation API
            response = self.client.client.validations.email.post(
                request_body={"email": email_address}
            )
            
            if response.status_code == 200:
                result = response.body
                return result.get('result', {}).get('verdict') == 'valid'
            else:
                logger.error(f"Email validation failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error validating email: {str(e)}")
            return False
    
    async def get_suppression_list(self) -> List[str]:
        """
        Get list of suppressed email addresses.
        
        Returns:
            List of suppressed email addresses
        """
        try:
            if not self.client:
                await self.authenticate()
            
            # Get bounces
            bounces_response = self.client.client.suppression.bounces.get()
            suppressed_emails = []
            
            if bounces_response.status_code == 200:
                for bounce in bounces_response.body:
                    suppressed_emails.append(bounce.get('email'))
            
            # Get spam reports
            spam_response = self.client.client.suppression.spam_reports.get()
            if spam_response.status_code == 200:
                for spam_report in spam_response.body:
                    suppressed_emails.append(spam_report.get('email'))
            
            return list(set(suppressed_emails))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Error getting suppression list: {str(e)}")
            return []
    
    async def add_to_suppression_list(self, email_address: str, reason: str = "user") -> bool:
        """
        Add email address to suppression list.
        
        Args:
            email_address: Email address to suppress
            reason: Reason for suppression
            
        Returns:
            True if added successfully
        """
        try:
            if not self.client:
                await self.authenticate()
            
            # Add to bounces
            response = self.client.client.suppression.bounces.post(
                request_body={"email": email_address, "reason": reason}
            )
            
            if response.status_code == 201:
                logger.info(f"Added {email_address} to suppression list")
                return True
            else:
                logger.error(f"Failed to add to suppression list: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding to suppression list: {str(e)}")
            return False
    
    async def remove_from_suppression_list(self, email_address: str) -> bool:
        """
        Remove email address from suppression list.
        
        Args:
            email_address: Email address to unsuppress
            
        Returns:
            True if removed successfully
        """
        try:
            if not self.client:
                await self.authenticate()
            
            # Remove from bounces
            response = self.client.client.suppression.bounces.delete(email_address)
            
            if response.status_code == 204:
                logger.info(f"Removed {email_address} from suppression list")
                return True
            else:
                logger.error(f"Failed to remove from suppression list: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing from suppression list: {str(e)}")
            return False