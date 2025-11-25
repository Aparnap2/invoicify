"""
Mailgun email provider for AP Intake & Validation system.

Implements EmailProvider interface for Mailgun API integration.
"""

import logging
import base64
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from ..base import EmailProvider, EmailMessage, EmailAttachment


logger = logging.getLogger(__name__)


class MailgunProvider(EmailProvider):
    """
    Mailgun email provider implementation.
    
    Handles Mailgun API operations for sending and receiving emails.
    """
    
    def __init__(
        self, 
        api_key: str, 
        domain: str, 
        from_email: str, 
        from_name: str = "AP Intake System",
        api_url: str = "https://api.mailgun.net/v3"
    ):
        """
        Initialize Mailgun provider.
        
        Args:
            api_key: Mailgun API key
            domain: Mailgun domain
            from_email: Default sender email
            from_name: Default sender name
            api_url: Mailgun API URL
        """
        if not REQUESTS_AVAILABLE:
            raise ImportError("Requests package not installed. Install with: pip install requests")
        
        self.api_key = api_key
        self.domain = domain
        self.from_email = from_email
        self.from_name = from_name
        self.api_url = api_url
        self.auth = ('api', self.api_key)
        
        logger.info(f"MailgunProvider initialized for domain: {domain}")
    
    async def authenticate(self, **kwargs) -> bool:
        """
        Authenticate with Mailgun API.
        
        Returns:
            True if authentication successful
        """
        try:
            logger.info("Authenticating with Mailgun API")
            
            # Test authentication by getting account info
            response = requests.get(
                f"{self.api_url}/domains/{self.domain}",
                auth=self.auth
            )
            
            if response.status_code == 200:
                logger.info("Mailgun authentication successful")
                return True
            else:
                logger.error(f"Mailgun authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Mailgun authentication error: {str(e)}")
            return False
    
    async def fetch_emails(
        self, 
        limit: int = 50, 
        folder: str = "INBOX",
        since: Optional[datetime] = None
    ) -> List[EmailMessage]:
        """
        Fetch emails from Mailgun (stored emails).
        
        Args:
            limit: Maximum number of emails to fetch
            folder: Mailgun tag or filter
            since: Only fetch emails after this date
            
        Returns:
            List of email messages
        """
        try:
            logger.info(f"Fetching {limit} emails from Mailgun")
            
            # Build query parameters
            params = {'limit': limit}
            
            if since:
                params['begin'] = since.strftime('%Y-%m-%d')
            
            if folder != "INBOX":
                params['tag'] = folder
            
            # Get stored emails
            response = requests.get(
                f"{self.api_url}/{self.domain}/events",
                auth=self.auth,
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch emails: {response.status_code}")
                return []
            
            events = response.json().get('items', [])
            email_messages = []
            
            for event in events:
                if event.get('event') in ['accepted', 'delivered', 'opened']:
                    email_message = self._parse_mailgun_event(event)
                    if email_message:
                        email_messages.append(email_message)
            
            logger.info(f"Successfully fetched {len(email_messages)} emails")
            return email_messages
            
        except Exception as e:
            logger.error(f"Error fetching emails from Mailgun: {str(e)}")
            return []
    
    async def send_email(self, email_message: EmailMessage) -> bool:
        """
        Send email via Mailgun API.
        
        Args:
            email_message: Email message to send
            
        Returns:
            True if email sent successfully
        """
        try:
            logger.info(f"Sending email to {email_message.to_email}")
            
            # Prepare email data
            data = {
                'from': f"{self.from_name} <{self.from_email}>",
                'to': email_message.to_email,
                'subject': email_message.subject,
                'text': email_message.body or '',
                'html': email_message.html_body or ''
            }
            
            # Add CC if present
            if email_message.cc_email:
                data['cc'] = email_message.cc_email
            
            # Add attachments
            files = []
            for attachment in email_message.attachments:
                if attachment.content:
                    files.append((
                        attachment.filename,
                        attachment.content,
                        attachment.content_type
                    ))
            
            # Send email
            response = requests.post(
                f"{self.api_url}/{self.domain}/messages",
                auth=self.auth,
                data=data,
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Email sent successfully via Mailgun: {result.get('id')}")
                return True
            else:
                logger.error(f"Mailgun send failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email via Mailgun: {str(e)}")
            return False
    
    async def mark_as_read(self, message_id: str) -> bool:
        """
        Mailgun doesn't have a direct "mark as read" concept for stored emails.
        This method is not applicable for Mailgun.
        
        Returns:
            False (not supported)
        """
        logger.warning("Mailgun provider does not support marking emails as read")
        return False
    
    async def move_to_folder(self, message_id: str, folder: str) -> bool:
        """
        Move email to folder using Mailgun tags.
        
        Args:
            message_id: Mailgun message ID
            folder: Target folder (as tag)
            
        Returns:
            True if moved successfully
        """
        try:
            logger.info(f"Tagging message {message_id} with {folder}")
            
            # Add tag to message
            response = requests.post(
                f"{self.api_url}/{self.domain}/messages/{message_id}/tags",
                auth=self.auth,
                data={'tag': folder}
            )
            
            if response.status_code == 200:
                logger.info(f"Message tagged successfully: {folder}")
                return True
            else:
                logger.error(f"Failed to tag message: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error tagging message: {str(e)}")
            return False
    
    def _parse_mailgun_event(self, event: Dict[str, Any]) -> Optional[EmailMessage]:
        """
        Parse Mailgun event into EmailMessage.
        
        Args:
            event: Mailgun event data
            
        Returns:
            EmailMessage object or None
        """
        try:
            message_data = event.get('message', {})
            
            email_message = EmailMessage(
                message_id=event.get('id'),
                subject=message_data.get('subject', ''),
                from_email=message_data.get('from', ''),
                to_email=message_data.get('to', ''),
                cc_email=message_data.get('cc', ''),
                body=message_data.get('body', ''),
                html_body=message_data.get('html', ''),
                date=datetime.fromisoformat(event.get('timestamp', '').replace('Z', '+00:00')),
                is_read=event.get('event') in ['opened', 'clicked'],
                folder=event.get('tag', 'INBOX')
            )
            
            return email_message
            
        except Exception as e:
            logger.error(f"Error parsing Mailgun event: {str(e)}")
            return None
    
    async def get_domain_stats(self) -> Dict[str, Any]:
        """
        Get domain statistics from Mailgun.
        
        Returns:
            Dictionary with domain statistics
        """
        try:
            response = requests.get(
                f"{self.api_url}/{self.domain}/stats",
                auth=self.auth,
                params={
                    'event': ['accepted', 'delivered', 'opened', 'clicked', 'bounced', 'complained'],
                    'duration': '24h'
                }
            )
            
            if response.status_code == 200:
                stats = response.json()
                return {
                    'accepted': self._extract_stat(stats, 'accepted'),
                    'delivered': self._extract_stat(stats, 'delivered'),
                    'opened': self._extract_stat(stats, 'opened'),
                    'clicked': self._extract_stat(stats, 'clicked'),
                    'bounced': self._extract_stat(stats, 'bounced'),
                    'complained': self._extract_stat(stats, 'complained')
                }
            else:
                logger.error(f"Failed to get domain stats: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting domain stats: {str(e)}")
            return {}
    
    def _extract_stat(self, stats: Dict[str, Any], event_type: str) -> int:
        """
        Extract specific stat from Mailgun stats response.
        
        Args:
            stats: Mailgun stats response
            event_type: Type of event to extract
            
        Returns:
            Stat count
        """
        try:
            for stat in stats:
                if stat.get('event') == event_type:
                    return stat.get('total', 0)
            return 0
        except Exception:
            return 0
    
    async def validate_email(self, email_address: str) -> bool:
        """
        Validate email address using Mailgun Email Validation API.
        
        Args:
            email_address: Email address to validate
            
        Returns:
            True if email is valid
        """
        try:
            response = requests.get(
                f"https://api.mailgun.net/v4/address/validate",
                auth=self.auth,
                params={'address': email_address}
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('result', {}).get('is_valid', False)
            else:
                logger.error(f"Email validation failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error validating email: {str(e)}")
            return False
    
    async def get_bounces(self) -> List[Dict[str, Any]]:
        """
        Get list of bounced emails.
        
        Returns:
            List of bounce information
        """
        try:
            response = requests.get(
                f"{self.api_url}/{self.domain}/bounces",
                auth=self.auth
            )
            
            if response.status_code == 200:
                return response.json().get('items', [])
            else:
                logger.error(f"Failed to get bounces: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting bounces: {str(e)}")
            return []
    
    async def add_bounce(self, email_address: str, code: int = 550, error: str = "Bounced") -> bool:
        """
        Add email to bounce list.
        
        Args:
            email_address: Email address to add
            code: Bounce code
            error: Bounce error message
            
        Returns:
            True if added successfully
        """
        try:
            response = requests.post(
                f"{self.api_url}/{self.domain}/bounces",
                auth=self.auth,
                data={
                    'address': email_address,
                    'code': code,
                    'error': error
                }
            )
            
            if response.status_code == 200:
                logger.info(f"Added {email_address} to bounce list")
                return True
            else:
                logger.error(f"Failed to add bounce: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding bounce: {str(e)}")
            return False
    
    async def delete_bounce(self, email_address: str) -> bool:
        """
        Remove email from bounce list.
        
        Args:
            email_address: Email address to remove
            
        Returns:
            True if removed successfully
        """
        try:
            response = requests.delete(
                f"{self.api_url}/{self.domain}/bounces/{email_address}",
                auth=self.auth
            )
            
            if response.status_code == 200:
                logger.info(f"Removed {email_address} from bounce list")
                return True
            else:
                logger.error(f"Failed to delete bounce: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting bounce: {str(e)}")
            return False
    
    async def get_complaints(self) -> List[Dict[str, Any]]:
        """
        Get list of spam complaints.
        
        Returns:
            List of complaint information
        """
        try:
            response = requests.get(
                f"{self.api_url}/{self.domain}/complaints",
                auth=self.auth
            )
            
            if response.status_code == 200:
                return response.json().get('items', [])
            else:
                logger.error(f"Failed to get complaints: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting complaints: {str(e)}")
            return []
    
    async def add_complaint(self, email_address: str) -> bool:
        """
        Add email to spam complaint list.
        
        Args:
            email_address: Email address to add
            
        Returns:
            True if added successfully
        """
        try:
            response = requests.post(
                f"{self.api_url}/{self.domain}/complaints",
                auth=self.auth,
                data={'address': email_address}
            )
            
            if response.status_code == 200:
                logger.info(f"Added {email_address} to complaint list")
                return True
            else:
                logger.error(f"Failed to add complaint: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding complaint: {str(e)}")
            return False
    
    async def delete_complaint(self, email_address: str) -> bool:
        """
        Remove email from spam complaint list.
        
        Args:
            email_address: Email address to remove
            
        Returns:
            True if removed successfully
        """
        try:
            response = requests.delete(
                f"{self.api_url}/{self.domain}/complaints/{email_address}",
                auth=self.auth
            )
            
            if response.status_code == 200:
                logger.info(f"Removed {email_address} from complaint list")
                return True
            else:
                logger.error(f"Failed to delete complaint: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting complaint: {str(e)}")
            return False
    
    async def send_template_email(
        self, 
        template_name: str, 
        recipient_email: str,
        template_data: Dict[str, Any],
        subject: Optional[str] = None
    ) -> bool:
        """
        Send email using Mailgun template.
        
        Args:
            template_name: Mailgun template name
            recipient_email: Recipient email address
            template_data: Template substitution data
            subject: Optional subject override
            
        Returns:
            True if email sent successfully
        """
        try:
            logger.info(f"Sending template email {template_name} to {recipient_email}")
            
            # Prepare email data
            data = {
                'from': f"{self.from_name} <{self.from_email}>",
                'to': recipient_email,
                'subject': subject or 'Template Email',
                'template': template_name,
                'h:X-Mailgun-Variables': json.dumps(template_data)
            }
            
            # Send email
            response = requests.post(
                f"{self.api_url}/{self.domain}/messages",
                auth=self.auth,
                data=data
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Template email sent successfully: {result.get('id')}")
                return True
            else:
                logger.error(f"Template email send failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending template email: {str(e)}")
            return False