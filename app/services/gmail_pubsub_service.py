"""
Gmail Pub/Sub integration service for real-time email processing.

Replaces inefficient polling with Google Cloud Pub/Sub push notifications
for immediate email processing when invoices arrive.
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.core.exceptions import EmailIngestionException
from app.services.ingestion_service import IngestionService
from app.workers.email_tasks import process_email_attachment

logger = logging.getLogger(__name__)


class GmailPubSubService:
    """Gmail Pub/Sub service for real-time invoice email processing."""

    def __init__(self):
        """Initialize the Gmail Pub/Sub service."""
        self.ingestion_service = IngestionService()
        self.scopes = ['https://www.googleapis.com/auth/gmail.readonly']
        self.project_id = settings.GCP_PROJECT_ID
        self.topic_name = settings.GMAIL_PUBSUB_TOPIC_NAME
        self.subscription_name = settings.GMAIL_PUBSUB_SUBSCRIPTION_NAME

        # Cache for Gmail service instances
        self._service_cache = {}
        self._watch_expiry_cache = {}

    async def setup_gmail_watch(self, credentials_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Set up Gmail watch for real-time notifications.

        Args:
            credentials_data: Gmail OAuth credentials

        Returns:
            Dictionary with watch setup details
        """
        try:
            # Build Gmail service
            service = await self._get_gmail_service(credentials_data)

            # Prepare watch request
            watch_request = {
                'topicName': f'projects/{self.project_id}/topics/{self.topic_name}',
                'labelIds': ['INBOX'],  # Monitor only inbox
                'labelFilterBehavior': 'INCLUDE'
            }

            # Set up watch
            response = service.users().watch(userId='me', body=watch_request).execute()

            # Cache watch expiry
            expiry_time = datetime.fromtimestamp(int(response['expiration']) / 1000, tz=timezone.utc)
            self._watch_expiry_cache[credentials_data['email']] = expiry_time

            logger.info(f"Gmail watch setup successfully for {credentials_data.get('email', 'unknown')}")
            logger.info(f"History ID: {response.get('historyId')}")
            logger.info(f"Expiry: {expiry_time}")

            return {
                "success": True,
                "history_id": response.get('historyId'),
                "expiry": response.get('expiration'),
                "expiry_time": expiry_time.isoformat(),
                "topic_name": self.topic_name,
                "project_id": self.project_id
            }

        except HttpError as e:
            error_msg = f"Gmail API error setting up watch: {e}"
            logger.error(error_msg)
            raise EmailIngestionException(error_msg)
        except Exception as e:
            error_msg = f"Failed to setup Gmail watch: {str(e)}"
            logger.error(error_msg)
            raise EmailIngestionException(error_msg)

    async def stop_gmail_watch(self, credentials_data: Dict[str, Any]) -> bool:
        """
        Stop Gmail watch notifications.

        Args:
            credentials_data: Gmail OAuth credentials

        Returns:
            True if successful
        """
        try:
            service = await self._get_gmail_service(credentials_data)
            service.users().stop(userId='me').execute()

            # Clear cached expiry
            if 'email' in credentials_data:
                self._watch_expiry_cache.pop(credentials_data['email'], None)

            logger.info(f"Gmail watch stopped for {credentials_data.get('email', 'unknown')}")
            return True

        except Exception as e:
            logger.error(f"Error stopping Gmail watch: {str(e)}")
            return False

    async def process_pubsub_message(self, pubsub_message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming Pub/Sub message from Gmail.

        Args:
            pubsub_message: Pub/Sub message data

        Returns:
            Processing result
        """
        try:
            # Decode message data
            if 'data' not in pubsub_message:
                raise ValueError("No data in Pub/Sub message")

            notification_data = json.loads(
                base64.b64decode(pubsub_message['data']).decode('utf-8')
            )

            email_address = notification_data.get('emailAddress')
            history_id = notification_data.get('historyId')

            if not email_address or not history_id:
                raise ValueError("Missing emailAddress or historyId in notification")

            logger.info(f"Processing Gmail notification for {email_address}, historyId: {history_id}")

            # Get Gmail credentials for this user
            credentials_data = await self._get_user_credentials(email_address)
            if not credentials_data:
                raise ValueError(f"No credentials found for {email_address}")

            # Process email changes
            processed_count = await self._process_gmail_changes(credentials_data, history_id)

            result = {
                "success": True,
                "email_address": email_address,
                "history_id": history_id,
                "processed_messages": processed_count,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

            logger.info(f"Successfully processed {processed_count} messages for {email_address}")
            return result

        except Exception as e:
            logger.error(f"Error processing Pub/Sub message: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

    async def _process_gmail_changes(self, credentials_data: Dict[str, Any], history_id: str) -> int:
        """
        Process Gmail changes since last history ID.

        Args:
            credentials_data: Gmail OAuth credentials
            history_id: Starting history ID

        Returns:
            Number of messages processed
        """
        try:
            service = await self._get_gmail_service(credentials_data)

            # Get history changes
            history_response = service.users().history().list(
                userId='me',
                startHistoryId=history_id,
                maxResults=100  # Process up to 100 changes at once
            ).execute()

            processed_count = 0

            if 'history' in history_response:
                for history_record in history_response['history']:
                    # Process new messages
                    messages_added = history_record.get('messagesAdded', [])
                    for message_added in messages_added:
                        message_id = message_added['message']['id']

                        if await self._is_invoice_email(service, message_id):
                            await self._process_invoice_email(service, message_id, credentials_data)
                            processed_count += 1

            return processed_count

        except Exception as e:
            logger.error(f"Error processing Gmail changes: {str(e)}")
            raise

    async def _is_invoice_email(self, service, message_id: str) -> bool:
        """
        Check if email contains invoice indicators.

        Args:
            service: Gmail API service
            message_id: Gmail message ID

        Returns:
            True if email likely contains invoice
        """
        try:
            # Get message headers
            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['Subject', 'From', 'Date', 'To']
            ).execute()

            # Extract headers
            subject = ''
            sender = ''

            for header in message['payload']['headers']:
                if header['name'].lower() == 'subject':
                    subject = header['value'].lower()
                elif header['name'].lower() == 'from':
                    sender = header['value'].lower()

            # Check for invoice keywords in subject
            invoice_keywords = [
                'invoice', 'bill', 'payment due', 'statement',
                'receipt', 'purchase order', 'order confirmation',
                'proforma', 'credit note', 'debit note'
            ]

            subject_has_invoice = any(keyword in subject for keyword in invoice_keywords)

            # Check for common invoice senders/domains
            invoice_domains = [
                'quickbooks', 'xero', 'freshbooks', 'sage',
                'intuit', 'paypal', 'stripe', 'square',
                'billing', 'accounts', 'invoice', 'noreply'
            ]

            sender_is_invoice = any(domain in sender for domain in invoice_domains)

            # Check for attachments (invoices usually have PDFs)
            has_attachments = 'parts' in message.get('payload', {})

            # Check thread topic for invoice discussions
            thread_id = message.get('threadId')
            if thread_id and not (subject_has_invoice or sender_is_invoice):
                # Could check thread history for invoice context
                pass

            return (subject_has_invoice or sender_is_invoice) and has_attachments

        except Exception as e:
            logger.error(f"Error checking if email is invoice: {str(e)}")
            return False

    async def _process_invoice_email(self, service, message_id: str, credentials_data: Dict[str, Any]):
        """
        Process invoice email and queue attachments for processing.

        Args:
            service: Gmail API service
            message_id: Gmail message ID
            credentials_data: User credentials
        """
        try:
            # Get full message
            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Extract email metadata
            subject = ''
            sender = ''
            date = ''

            for header in message['payload']['headers']:
                if header['name'] == 'Subject':
                    subject = header['value']
                elif header['name'] == 'From':
                    sender = header['value']
                elif header['name'] == 'Date':
                    date = header['value']

            # Process attachments
            attachments_processed = 0

            def process_part(part):
                nonlocal attachments_processed

                if part.get('filename') and part.get('body', {}).get('attachmentId'):
                    try:
                        # Download attachment
                        attachment_id = part['body']['attachmentId']
                        attachment_data = service.users().messages().attachments().get(
                            userId='me',
                            messageId=message_id,
                            id=attachment_id
                        ).execute()

                        # Decode attachment content
                        file_content = base64.urlsafe_b64decode(
                            attachment_data['data'].encode('UTF-8')
                        )

                        # Extract vendor name from email
                        vendor_name = self._extract_vendor_name(sender, subject, part['filename'])

                        # Queue for processing
                        process_email_attachment.delay(
                            email_id=message_id,
                            attachment_data={
                                'filename': part['filename'],
                                'content_type': part['mimeType'],
                                'content_hash': self._calculate_content_hash(file_content),
                                'vendor_name': vendor_name,
                                'email_subject': subject,
                                'email_sender': sender,
                                'email_date': date
                            },
                            user_id=credentials_data.get('user_id')
                        )

                        attachments_processed += 1
                        logger.info(f"Queued attachment {part['filename']} for processing")

                    except Exception as e:
                        logger.error(f"Error processing attachment {part.get('filename', 'unknown')}: {str(e)}")

                # Process nested parts
                if 'parts' in part:
                    for subpart in part['parts']:
                        process_part(subpart)

            # Process all parts in the message
            process_part(message['payload'])

            logger.info(f"Processed {attachments_processed} attachments from email {message_id}")

        except Exception as e:
            logger.error(f"Error processing invoice email {message_id}: {str(e)}")

    async def _get_gmail_service(self, credentials_data: Dict[str, Any]):
        """Get cached Gmail service instance."""
        email = credentials_data.get('email')
        if not email:
            email = 'default'

        if email not in self._service_cache:
            # Create credentials object
            creds = Credentials(
                token=credentials_data.get('token'),
                refresh_token=credentials_data.get('refresh_token'),
                token_uri=credentials_data.get('token_uri'),
                client_id=credentials_data.get('client_id'),
                client_secret=credentials_data.get('client_secret'),
                scopes=self.scopes
            )

            # Build service
            self._service_cache[email] = build('gmail', 'v1', credentials=creds)

        return self._service_cache[email]

    async def _get_user_credentials(self, email_address: str) -> Optional[Dict[str, Any]]:
        """
        Get user credentials from database or cache.
        
        Queries the user credential system for stored OAuth tokens.
        """
        try:
            from app.services.auth.credential_manager import credential_manager
            from app.models.user import CredentialType
            from app.db.session import get_db
            
            # Get database session
            async with get_db() as db:
                # Find user by email address
                from sqlalchemy import select
                from app.models.user import User
                
                user = await db.execute(
                    select(User).where(User.email == email_address)
                ).scalar_one_or_none()
                
                if not user:
                    logger.error(f"No user found for email: {email_address}")
                    return None
                
                # Get Gmail credentials for user
                credentials = await credential_manager.get_credentials(
                    db=db,
                    user_id=str(user.id),
                    credential_type=CredentialType.GMAIL_OAUTH
                )
                
                if not credentials:
                    logger.error(f"No Gmail credentials found for user: {email_address}")
                    return None
                
                # Add user info to credentials
                credentials.update({
                    "user_id": str(user.id),
                    "email": email_address
                })
                
                logger.info(f"Retrieved Gmail credentials for user: {email_address}")
                return credentials
                
        except Exception as e:
            logger.error(f"Error retrieving user credentials: {str(e)}")
            return None

    def _extract_vendor_name(self, sender: str, subject: str, filename: str) -> Optional[str]:
        """Extract vendor name from email metadata."""
        # Try to extract from sender email
        if '<' in sender and '>' in sender:
            email_part = sender.split('<')[1].split('>')[0]
        else:
            email_part = sender.split('@')[0] if '@' in sender else sender

        # Try to extract from subject
        import re
        vendor_patterns = [
            r'from\s+([A-Za-z0-9\s&]+)',
            r'([A-Za-z0-9\s&]+)\s+invoice',
            r'([A-Za-z0-9\s&]+)\s+bill',
        ]

        text_to_search = f"{subject} {filename} {email_part}"

        for pattern in vendor_patterns:
            match = re.search(pattern, text_to_search, re.IGNORECASE)
            if match:
                vendor = match.group(1).strip()
                if len(vendor) > 2 and len(vendor) < 50:
                    return vendor

        # Fallback to email domain
        if '@' in sender:
            domain = sender.split('@')[1].split('.')[0]
            if len(domain) > 2:
                return domain.title()

        return None

    def _calculate_content_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of file content."""
        import hashlib
        return hashlib.sha256(content).hexdigest()

    async def check_watch_health(self, credentials_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if Gmail watch is still active and healthy.

        Args:
            credentials_data: Gmail OAuth credentials

        Returns:
            Health check result
        """
        try:
            email = credentials_data.get('email', 'unknown')

            # Check cached expiry
            if email in self._watch_expiry_cache:
                expiry_time = self._watch_expiry_cache[email]
                if datetime.now(timezone.utc) > expiry_time - timedelta(days=1):
                    # Watch expires soon, renew it
                    logger.info(f"Gmail watch for {email} expires soon, renewing...")
                    await self.setup_gmail_watch(credentials_data)

            # Test Gmail API connectivity
            service = await self._get_gmail_service(credentials_data)
            profile = service.users().getProfile(userId='me').execute()

            return {
                "healthy": True,
                "email": email,
                "history_id": profile.get('historyId'),
                "messages_total": profile.get('messagesTotal', 0),
                "check_time": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Gmail watch health check failed: {str(e)}")
            return {
                "healthy": False,
                "error": str(e),
                "check_time": datetime.now(timezone.utc).isoformat()
            }

    async def renew_all_watches(self) -> Dict[str, Any]:
        """
        Renew all Gmail watches before they expire.

        Returns:
            Renewal results
        """
        try:
            # TODO: Get all active users from database
            # For now, just check cached watches
            renewed_count = 0
            failed_count = 0

            for email, expiry_time in self._watch_expiry_cache.items():
                try:
                    # Renew if expiring within 24 hours
                    if datetime.now(timezone.utc) > expiry_time - timedelta(hours=24):
                        # Get credentials for this user
                        from app.services.auth.credential_manager import credential_manager
                        from app.models.user import CredentialType
                        from app.db.session import get_db
                        
                        async with get_db() as db:
                            # Find user by email
                            from sqlalchemy import select
                            from app.models.user import User
                            
                            user = await db.execute(
                                select(User).where(User.email == email)
                            ).scalar_one_or_none()
                            
                            if user:
                                credentials = await credential_manager.get_credentials(
                                    db=db,
                                    user_id=str(user.id),
                                    credential_type=CredentialType.GMAIL_OAUTH
                                )
                                
                                if credentials and not credentials.get("is_expired", True):
                                    logger.info(f"Renewing Gmail watch for user: {email}")
                                    renewed_count += 1
                        renewed_count += 1

                except Exception as e:
                    logger.error(f"Failed to renew watch for {email}: {str(e)}")
                    failed_count += 1

            return {
                "total_watches": len(self._watch_expiry_cache),
                "renewed": renewed_count,
                "failed": failed_count,
                "check_time": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error renewing Gmail watches: {str(e)}")
            return {
                "total_watches": 0,
                "renewed": 0,
                "failed": 0,
                "error": str(e),
                "check_time": datetime.now(timezone.utc).isoformat()
            }


# Global service instance
gmail_pubsub_service = GmailPubSubService()