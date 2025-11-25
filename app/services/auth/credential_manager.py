"""
Secure credential management service for AP Intake & Validation system.

Provides secure storage, retrieval, and management of OAuth credentials
and other sensitive authentication data using encryption and proper security practices.
"""

import logging
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from ..models.user import UserCredential, CredentialType
from ..config import get_settings


logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Secure credential management service.
    
    Handles encrypted storage and retrieval of OAuth credentials and other
    sensitive authentication data using industry-standard encryption practices.
    """
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize credential manager.
        
        Args:
            encryption_key: Master encryption key (defaults to settings)
        """
        settings = get_settings()
        self.encryption_key = encryption_key or settings.CREDENTIAL_ENCRYPTION_KEY
        
        if not self.encryption_key:
            raise ValueError("Credential encryption key not configured")
        
        # Initialize encryption
        self.cipher_suite = self._create_cipher_suite()
        
        logger.info("CredentialManager initialized with secure encryption")
    
    def _create_cipher_suite(self) -> Fernet:
        """
        Create Fernet cipher suite for encryption/decryption.
        
        Returns:
            Fernet cipher instance
        """
        # Use PBKDF2 to derive encryption key from master key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'ap_intake_credential_salt',  # In production, use unique salt per deployment
            iterations=100000,
            backend=default_backend()
        )
        
        derived_key = kdf.derive(self.encryption_key.encode())
        return Fernet(base64.urlsafe_b64encode(derived_key))
    
    async def store_credentials(
        self,
        db: AsyncSession,
        user_id: str,
        credential_type: CredentialType,
        credentials: Dict[str, Any],
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Securely store credentials for a user.
        
        Args:
            db: Database session
            user_id: User ID
            credential_type: Type of credential
            credentials: Credential data to store
            expires_at: Optional expiration time
            metadata: Additional metadata
            
        Returns:
            True if stored successfully
        """
        try:
            # Encrypt credentials
            encrypted_data = self._encrypt_credentials(credentials)
            
            # Check if credentials already exist
            existing = await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.credential_type == credential_type
                )
            ).scalar_one_or_none()
            
            if existing:
                # Update existing credentials
                await db.execute(
                    update(UserCredential).where(
                        UserCredential.id == existing.id
                    ).values(
                        encrypted_credentials=encrypted_data,
                        expires_at=expires_at,
                        metadata=metadata or {},
                        updated_at=datetime.now(timezone.utc)
                    )
                )
                logger.info(f"Updated {credential_type.value} credentials for user {user_id}")
            else:
                # Create new credentials
                new_credential = UserCredential(
                    user_id=user_id,
                    credential_type=credential_type,
                    encrypted_credentials=encrypted_data,
                    expires_at=expires_at,
                    metadata=metadata or {},
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_credential)
                logger.info(f"Stored {credential_type.value} credentials for user {user_id}")
            
            await db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to store credentials for user {user_id}: {str(e)}")
            await db.rollback()
            return False
    
    async def get_credentials(
        self,
        db: AsyncSession,
        user_id: str,
        credential_type: CredentialType
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and decrypt credentials for a user.
        
        Args:
            db: Database session
            user_id: User ID
            credential_type: Type of credential
            
        Returns:
            Decrypted credentials or None
        """
        try:
            # Get encrypted credentials
            credential = await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.credential_type == credential_type,
                    UserCredential.is_active == True
                )
            ).scalar_one_or_none()
            
            if not credential:
                logger.warning(f"No {credential_type.value} credentials found for user {user_id}")
                return None
            
            # Check if credentials are expired
            if credential.expires_at and datetime.now(timezone.utc) > credential.expires_at:
                logger.warning(f"Credentials expired for user {user_id}")
                await self._deactivate_credentials(db, credential.id)
                return None
            
            # Decrypt credentials
            decrypted_data = self._decrypt_credentials(credential.encrypted_credentials)
            
            if not decrypted_data:
                logger.error(f"Failed to decrypt credentials for user {user_id}")
                return None
            
            # Update last accessed time
            await db.execute(
                update(UserCredential).where(
                    UserCredential.id == credential.id
                ).values(last_accessed_at=datetime.now(timezone.utc))
            )
            await db.commit()
            
            logger.info(f"Retrieved {credential_type.value} credentials for user {user_id}")
            return decrypted_data
            
        except Exception as e:
            logger.error(f"Failed to retrieve credentials for user {user_id}: {str(e)}")
            return None
    
    async def delete_credentials(
        self,
        db: AsyncSession,
        user_id: str,
        credential_type: Optional[CredentialType] = None
    ) -> bool:
        """
        Delete credentials for a user.
        
        Args:
            db: Database session
            user_id: User ID
            credential_type: Type of credential (None for all)
            
        Returns:
            True if deleted successfully
        """
        try:
            query = delete(UserCredential).where(UserCredential.user_id == user_id)
            
            if credential_type:
                query = query.where(UserCredential.credential_type == credential_type)
            
            result = await db.execute(query)
            await db.commit()
            
            logger.info(f"Deleted {result.rowcount} credential records for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete credentials for user {user_id}: {str(e)}")
            await db.rollback()
            return False
    
    async def refresh_credentials(
        self,
        db: AsyncSession,
        user_id: str,
        credential_type: CredentialType,
        new_credentials: Dict[str, Any],
        expires_at: Optional[datetime] = None
    ) -> bool:
        """
        Refresh existing credentials with new data.
        
        Args:
            db: Database session
            user_id: User ID
            credential_type: Type of credential
            new_credentials: New credential data
            expires_at: Optional expiration time
            
        Returns:
            True if refreshed successfully
        """
        try:
            # Encrypt new credentials
            encrypted_data = self._encrypt_credentials(new_credentials)
            
            # Update existing credentials
            await db.execute(
                update(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.credential_type == credential_type
                ).values(
                    encrypted_credentials=encrypted_data,
                    expires_at=expires_at,
                    updated_at=datetime.now(timezone.utc),
                    is_active=True
                )
            )
            
            await db.commit()
            logger.info(f"Refreshed {credential_type.value} credentials for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh credentials for user {user_id}: {str(e)}")
            await db.rollback()
            return False
    
    async def get_active_credentials_count(
        self,
        db: AsyncSession,
        user_id: str
    ) -> Dict[str, int]:
        """
        Get count of active credentials by type for a user.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Dictionary with credential counts
        """
        try:
            # Count credentials by type
            result = await db.execute(
                select(UserCredential.credential_type, UserCredential.id)
                .where(
                    UserCredential.user_id == user_id,
                    UserCredential.is_active == True
                )
            )
            )
            
            credentials = result.all()
            counts = {}
            
            for cred_type, _ in credentials:
                counts[cred_type.value] = counts.get(cred_type.value, 0) + 1
            
            return counts
            
        except Exception as e:
            logger.error(f"Failed to count credentials for user {user_id}: {str(e)}")
            return {}
    
    async def cleanup_expired_credentials(self, db: AsyncSession) -> int:
        """
        Clean up expired credentials.
        
        Args:
            db: Database session
            
        Returns:
            Number of credentials cleaned up
        """
        try:
            # Find expired credentials
            expired_credentials = await db.execute(
                select(UserCredential).where(
                    UserCredential.expires_at < datetime.now(timezone.utc),
                    UserCredential.is_active == True
                )
            ).scalars().all()
            
            if not expired_credentials:
                return 0
            
            # Deactivate expired credentials
            credential_ids = [cred.id for cred in expired_credentials]
            await db.execute(
                update(UserCredential).where(
                    UserCredential.id.in_(credential_ids)
                ).values(
                    is_active=False,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            
            await db.commit()
            
            logger.info(f"Deactivated {len(expired_credentials)} expired credentials")
            return len(expired_credentials)
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired credentials: {str(e)}")
            await db.rollback()
            return 0
    
    def _encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """
        Encrypt credential data.
        
        Args:
            credentials: Credential data to encrypt
            
        Returns:
            Encrypted data as base64 string
        """
        try:
            # Convert to JSON and encrypt
            json_data = json.dumps(credentials)
            encrypted_data = self.cipher_suite.encrypt(json_data.encode())
            return base64.b64encode(encrypted_data).decode()
            
        except Exception as e:
            logger.error(f"Failed to encrypt credentials: {str(e)}")
            raise ValueError(f"Credential encryption failed: {str(e)}")
    
    def _decrypt_credentials(self, encrypted_data: str) -> Optional[Dict[str, Any]]:
        """
        Decrypt credential data.
        
        Args:
            encrypted_data: Encrypted credential data
            
        Returns:
            Decrypted credentials or None
        """
        try:
            # Decode base64 and decrypt
            encrypted_bytes = base64.b64decode(encrypted_data.encode())
            decrypted_data = self.cipher_suite.decrypt(encrypted_bytes)
            return json.loads(decrypted_data.decode())
            
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {str(e)}")
            return None
    
    async def _deactivate_credentials(self, db: AsyncSession, credential_id: str) -> None:
        """
        Deactivate credentials by ID.
        
        Args:
            db: Database session
            credential_id: Credential ID
        """
        try:
            await db.execute(
                update(UserCredential).where(
                    UserCredential.id == credential_id
                ).values(
                    is_active=False,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            await db.commit()
            
        except Exception as e:
            logger.error(f"Failed to deactivate credential {credential_id}: {str(e)}")
    
    def generate_secure_token(self, length: int = 32) -> str:
        """
        Generate a cryptographically secure random token.
        
        Args:
            length: Token length
            
        Returns:
            Secure random token
        """
        return secrets.token_urlsafe(length)
    
    def validate_oauth_state(self, state: str, max_age_minutes: int = 10) -> bool:
        """
        Validate OAuth state parameter for CSRF protection.
        
        Args:
            state: State parameter to validate
            max_age_minutes: Maximum age in minutes
            
        Returns:
            True if state is valid
        """
        try:
            # State should be in format: timestamp:random_string
            parts = state.split(':', 1)
            if len(parts) != 2:
                return False
            
            timestamp_str, random_str = parts
            timestamp = int(timestamp_str)
            
            # Check age
            age_minutes = (datetime.now(timezone.utc).timestamp() - timestamp) / 60
            if age_minutes > max_age_minutes:
                return False
            
            # Check minimum length of random part
            if len(random_str) < 16:
                return False
            
            return True
            
        except Exception:
            return False
    
    def generate_oauth_state(self, user_id: str, additional_data: Optional[Dict[str, str]] = None) -> str:
        """
        Generate secure OAuth state parameter.
        
        Args:
            user_id: User ID
            additional_data: Additional data to include
            
        Returns:
            Secure state parameter
        """
        timestamp = int(datetime.now(timezone.utc).timestamp())
        random_part = self.generate_secure_token(16)
        
        state_parts = [str(timestamp), random_part]
        
        if additional_data:
            for key, value in additional_data.items():
                state_parts.append(f"{key}:{value}")
        
        return ':'.join(state_parts)


# Global credential manager instance
credential_manager = CredentialManager()