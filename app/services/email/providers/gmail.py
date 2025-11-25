"""
Gmail email provider for AP Intake & Validation system.

Implements EmailProvider interface for Gmail API integration.
"""

import logging
import base64
import email
import os
from email.message import EmailMessage
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..base import EmailProvider, EmailMessage, EmailAttachment


logger = logging.getLogger(__name__)


class GmailProvider(EmailProvider):
    """
    Gmail email provider implementation.
    
    Handles Gmail API operations including authentication, message retrieval,
    and sending emails using OAuth2.
    """
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']
    
    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
        user_id: str = "me"
    ):
        """
        Initialize Gmail provider.
        
        Args:
            credentials_path: Path to OAuth2 credentials file
            token_path: Path to store OAuth2 token
            user_id: Gmail user ID (typically 'me')
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.user_id = user_id
        self.service = None
        self.credentials = None
        
        logger.info(f"GmailProvider initialized for user: {user_id}")
    
    async def authenticate(self, **kwargs) -> bool:
        """
        Authenticate with Gmail API using OAuth2.
        
        Returns:
            True if authentication successful
        """
        try:
            logger.info("Authenticating with Gmail API")
            
            # Load existing token or get new one
            self.credentials = self._get_credentials()
            
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    logger.info("Refreshing expired Gmail credentials")
                    self.credentials.refresh(Request())
                else:
                    logger.info("Getting new Gmail credentials")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, self.SCOPES
                    )
                    self.credentials = flow.run_local_server(port=0)
                
                # Save credentials for future use
                with open(self.token_path, 'w') as token:
                    token.write(self.credentials.to_json())
            
            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=self.credentials)
            
            # Test authentication
            profile = self.service.users().getProfile(userId=self.user_id).execute()
            logger.info(f"Gmail authentication successful for: {profile['emailAddress']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Gmail authentication failed: {str(e)}")
            return False
    
    async def fetch_emails(
        self, 
        limit: int = 50, 
        folder: str = "INBOX",
        since: Optional[datetime] = None
    ) -> List[EmailMessage]:
        """
        Fetch emails from Gmail.
        
        Args:
            limit: Maximum number of emails to fetch
            folder: Gmail folder/label to fetch from
            since: Only fetch emails after this date
            
        Returns:
            List of email messages
        """
        try:
            if not self.service:
                await self.authenticate()
            
            logger.info(f"Fetching {limit} emails from {folder}")
            
            # Build query
            query = f"label:{folder}"
            if since:
                query += f" after:{since.strftime('%Y/%m/%d')}"
            
            # Get message list
            results = self.service.users().messages().list(
                userId=self.user_id,
                q=query,
                maxResults=limit
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Found {len(messages)} messages")
            
            # Fetch full message details
            email_messages = []
            for message_ref in messages:
                try:
                    email_message = await self._get_full_message(message_ref['id'])
                    if email_message:
                        email_messages.append(email_message)
                except Exception as e:
                    logger.error(f"Error fetching message {message_ref['id']}: {str(e)}")
                    continue
            
            logger.info(f"Successfully fetched {len(email_messages)} emails")
            return email_messages
            
        except HttpError as e:
            logger.error(f"Gmail API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching emails: {str(e)}")
            return []
    
    async def send_email(self, email_message: EmailMessage) -> bool:
        """
        Send email via Gmail API.
        
        Args:
            email_message: Email message to send
            
        Returns:
            True if email sent successfully
        """
        try:
            if not self.service:
                await self.authenticate()
            
            logger.info(f"Sending email to {email_message.to_email}")
            
            # Create MIME message
            mime_message = self._create_mime_message(email_message)
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
            
            # Send message
            message = {
                'raw': raw_message
            }
            
            result = self.service.users().messages().send(
                userId=self.user_id,
                body=message
            ).execute()
            
            logger.info(f"Email sent successfully: {result['id']}")
            return True
            
        except HttpError as e:
            logger.error(f"Gmail API error sending email: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False
    
    async def mark_as_read(self, message_id: str) -> bool:
        """
        Mark email as read in Gmail.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            True if marked as read successfully
        """
        try:
            if not self.service:
                await self.authenticate()
            
            logger.info(f"Marking message {message_id} as read")
            
            # Remove UNREAD label
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            return True
            
        except HttpError as e:
            logger.error(f"Gmail API error marking as read: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error marking as read: {str(e)}")
            return False
    
    async def move_to_folder(self, message_id: str, folder: str) -> bool:
        """
        Move email to specified folder/label.
        
        Args:
            message_id: Gmail message ID
            folder: Target folder/label
            
        Returns:
            True if moved successfully
        """
        try:
            if not self.service:
                await self.authenticate()
            
            logger.info(f"Moving message {message_id} to {folder}")
            
            # Add label
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body={'addLabelIds': [folder]}
            ).execute()
            
            return True
            
        except HttpError as e:
            logger.error(f"Gmail API error moving message: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error moving message: {str(e)}")
            return False
    
    def _get_credentials(self) -> Optional[Credentials]:
        """
        Get OAuth2 credentials from file or create new ones.
        
        Returns:
            Credentials object or None
        """
        try:
            if os.path.exists(self.token_path):
                return Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
        except Exception as e:
            logger.error(f"Error loading credentials: {str(e)}")
        
        return None
    
    async def _get_full_message(self, message_id: str) -> Optional[EmailMessage]:
        """
        Get full message details from Gmail.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            EmailMessage object or None
        """
        try:
            message = self.service.users().messages().get(
                userId=self.user_id,
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = {h['name']: h['value'] for h in message['payload']['headers']}
            
            # Extract body
            body = self._extract_body(message['payload'])
            
            # Extract attachments
            attachments = self._extract_attachments(message['payload'])
            
            # Create EmailMessage
            email_message = EmailMessage(
                message_id=message_id,
                subject=headers.get('Subject', ''),
                from_email=headers.get('From', ''),
                to_email=headers.get('To', ''),
                cc_email=headers.get('Cc', ''),
                body=body,
                html_body=self._extract_html_body(message['payload']),
                date=datetime.fromtimestamp(int(message['internalDate']) / 1000),
                attachments=attachments,
                is_read='UNREAD' not in message.get('labelIds', []),
                folder=self._get_folder_from_labels(message.get('labelIds', []))
            )
            
            return email_message
            
        except Exception as e:
            logger.error(f"Error getting full message {message_id}: {str(e)}")
            return None
    
    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """
        Extract plain text body from message payload.
        
        Args:
            payload: Gmail message payload
            
        Returns:
            Plain text body
        """
        try:
            if 'parts' in payload:
                # Multipart message
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body']['data']
                        return base64.urlsafe_b64decode(data).decode('utf-8')
            else:
                # Single part message
                if payload['mimeType'] == 'text/plain':
                    data = payload['body']['data']
                    return base64.urlsafe_b64decode(data).decode('utf-8')
            
            return ""
            
        except Exception as e:
            logger.error(f"Error extracting body: {str(e)}")
            return ""
    
    def _extract_html_body(self, payload: Dict[str, Any]) -> str:
        """
        Extract HTML body from message payload.
        
        Args:
            payload: Gmail message payload
            
        Returns:
            HTML body
        """
        try:
            if 'parts' in payload:
                # Multipart message
                for part in payload['parts']:
                    if part['mimeType'] == 'text/html':
                        data = part['body']['data']
                        return base64.urlsafe_b64decode(data).decode('utf-8')
            else:
                # Single part message
                if payload['mimeType'] == 'text/html':
                    data = payload['body']['data']
                    return base64.urlsafe_b64decode(data).decode('utf-8')
            
            return ""
            
        except Exception as e:
            logger.error(f"Error extracting HTML body: {str(e)}")
            return ""
    
    def _extract_attachments(self, payload: Dict[str, Any]) -> List[EmailAttachment]:
        """
        Extract attachments from message payload.
        
        Args:
            payload: Gmail message payload
            
        Returns:
            List of email attachments
        """
        attachments = []
        
        try:
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('filename'):
                        attachment = self._create_attachment(part)
                        if attachment:
                            attachments.append(attachment)
            
        except Exception as e:
            logger.error(f"Error extracting attachments: {str(e)}")
        
        return attachments
    
    def _create_attachment(self, part: Dict[str, Any]) -> Optional[EmailAttachment]:
        """
        Create EmailAttachment from Gmail part.
        
        Args:
            part: Gmail message part
            
        Returns:
            EmailAttachment object or None
        """
        try:
            filename = part['filename']
            content_type = part['mimeType']
            size = part['body'].get('size', 0)
            
            # Get attachment data
            attachment_id = part['body'].get('attachmentId')
            content = None
            
            if attachment_id and self.service:
                attachment = self.service.users().messages().attachments().get(
                    userId=self.user_id,
                    messageId=part.get('messageId'),
                    id=attachment_id
                ).execute()
                
                data = attachment['data']
                content = base64.urlsafe_b64decode(data)
            
            return EmailAttachment(
                filename=filename,
                content_type=content_type,
                size=size,
                content=content
            )
            
        except Exception as e:
            logger.error(f"Error creating attachment: {str(e)}")
            return None
    
    def _get_folder_from_labels(self, label_ids: List[str]) -> str:
        """
        Determine folder from Gmail labels.
        
        Args:
            label_ids: List of Gmail label IDs
            
        Returns:
            Folder name
        """
        # Map common Gmail labels to folder names
        label_map = {
            'INBOX': 'INBOX',
            'SENT': 'SENT',
            'DRAFT': 'DRAFT',
            'SPAM': 'SPAM',
            'TRASH': 'TRASH',
            'IMPORTANT': 'IMPORTANT',
            'STARRED': 'STARRED'
        }
        
        for label_id in label_ids:
            if label_id in label_map:
                return label_map[label_id]
        
        return 'INBOX'  # Default
    
    def _create_mime_message(self, email_message: EmailMessage) -> EmailMessage:
        """
        Create MIME message from EmailMessage.
        
        Args:
            email_message: EmailMessage object
            
        Returns:
            MIME EmailMessage
        """
        mime_message = email.message.EmailMessage()
        
        # Set headers
        mime_message['Subject'] = email_message.subject
        mime_message['From'] = email_message.from_email
        mime_message['To'] = email_message.to_email
        
        if email_message.cc_email:
            mime_message['Cc'] = email_message.cc_email
        
        # Set body
        if email_message.html_body:
            mime_message.add_alternative(email_message.html_body, subtype='html')
        
        if email_message.body:
            mime_message.set_content(email_message.body)
        
        # Add attachments
        for attachment in email_message.attachments:
            if attachment.content:
                mime_message.add_attachment(
                    attachment.content,
                    maintype=attachment.content_type.split('/')[0],
                    subtype=attachment.content_type.split('/')[1],
                    filename=attachment.filename
                )
        
        return mime_message
    
    async def get_labels(self) -> List[str]:
        """
        Get list of Gmail labels.
        
        Returns:
            List of label names
        """
        try:
            if not self.service:
                await self.authenticate()
            
            results = self.service.users().labels().list(userId=self.user_id).execute()
            labels = results.get('labels', [])
            
            return [label['name'] for label in labels]
            
        except Exception as e:
            logger.error(f"Error getting labels: {str(e)}")
            return []
    
    async def create_label(self, label_name: str) -> bool:
        """
        Create a new Gmail label.
        
        Args:
            label_name: Name of the label to create
            
        Returns:
            True if label created successfully
        """
        try:
            if not self.service:
                await self.authenticate()
            
            label_object = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            
            self.service.users().labels().create(
                userId=self.user_id,
                body=label_object
            ).execute()
            
            logger.info(f"Created Gmail label: {label_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating label {label_name}: {str(e)}")
            return False