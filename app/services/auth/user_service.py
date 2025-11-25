"""
User service for managing user operations and authentication.

This service provides high-level operations for user management,
including creation, retrieval, and authentication operations.
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.user import User, UserRole, UserCredential, AuditLog
from app.services.auth.credential_manager import CredentialManager
from app.core.security import get_password_hash, verify_password

logger = logging.getLogger(__name__)


class UserService:
    """Service for managing user operations and authentication."""
    
    def __init__(self):
        self.credential_manager = CredentialManager()
    
    async def get_or_create_user_by_email(
        self,
        db: Session,
        email: str,
        full_name: Optional[str] = None,
        role: str = "processor",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[User]:
        """
        Get an existing user by email or create a new one.
        
        Args:
            db: Database session
            email: User email address
            full_name: User's full name
            role: Default role for new users
            metadata: Additional user metadata
            
        Returns:
            User object or None if creation fails
        """
        try:
            # Check if user already exists
            user = db.query(User).filter(User.email == email).first()
            
            if user:
                logger.info(f"Found existing user: {email}")
                # Update metadata if provided
                if metadata:
                    if not user.metadata:
                        user.metadata = {}
                    user.metadata.update(metadata)
                    user.updated_at = datetime.utcnow()
                    db.commit()
                return user
            
            # Create new user
            user = User(
                email=email,
                full_name=full_name or email.split('@')[0],
                role=UserRole(role),
                is_active=True,
                metadata=metadata or {}
            )
            
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Create audit log
            audit_log = AuditLog(
                user_id=user.id,
                action="user_created",
                resource_type="user",
                resource_id=str(user.id),
                details={
                    "email": email,
                    "role": role,
                    "created_via": "oauth_integration"
                }
            )
            db.add(audit_log)
            db.commit()
            
            logger.info(f"Created new user: {email} with role: {role}")
            return user
            
        except Exception as e:
            logger.error(f"Error creating user {email}: {str(e)}")
            db.rollback()
            return None
    
    async def get_user_by_id(self, db: Session, user_id: uuid.UUID) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            db: Database session
            user_id: User UUID
            
        Returns:
            User object or None
        """
        try:
            return db.query(User).filter(User.id == user_id).first()
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {str(e)}")
            return None
    
    async def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """
        Get user by email.
        
        Args:
            db: Database session
            email: User email
            
        Returns:
            User object or None
        """
        try:
            return db.query(User).filter(User.email == email).first()
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {str(e)}")
            return None
    
    async def update_user(
        self,
        db: Session,
        user_id: uuid.UUID,
        updates: Dict[str, Any]
    ) -> Optional[User]:
        """
        Update user information.
        
        Args:
            db: Database session
            user_id: User UUID
            updates: Dictionary of fields to update
            
        Returns:
            Updated User object or None
        """
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            
            # Update allowed fields
            allowed_fields = ['full_name', 'role', 'is_active', 'metadata']
            for field, value in updates.items():
                if field in allowed_fields:
                    if field == 'role':
                        user.role = UserRole(value)
                    elif field == 'metadata':
                        if not user.metadata:
                            user.metadata = {}
                        user.metadata.update(value)
                    else:
                        setattr(user, field, value)
            
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            
            # Create audit log
            audit_log = AuditLog(
                user_id=user_id,
                action="user_updated",
                resource_type="user",
                resource_id=str(user_id),
                details={"updated_fields": list(updates.keys())}
            )
            db.add(audit_log)
            db.commit()
            
            logger.info(f"Updated user {user_id}")
            return user
            
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {str(e)}")
            db.rollback()
            return None
    
    async def deactivate_user(self, db: Session, user_id: uuid.UUID) -> bool:
        """
        Deactivate a user account.
        
        Args:
            db: Database session
            user_id: User UUID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            user.is_active = False
            user.updated_at = datetime.utcnow()
            db.commit()
            
            # Create audit log
            audit_log = AuditLog(
                user_id=user_id,
                action="user_deactivated",
                resource_type="user",
                resource_id=str(user_id),
                details={}
            )
            db.add(audit_log)
            db.commit()
            
            logger.info(f"Deactivated user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {str(e)}")
            db.rollback()
            return False
    
    async def get_users_by_role(
        self,
        db: Session,
        role: UserRole,
        active_only: bool = True
    ) -> List[User]:
        """
        Get users by role.
        
        Args:
            db: Database session
            role: User role to filter by
            active_only: Whether to only return active users
            
        Returns:
            List of User objects
        """
        try:
            query = db.query(User).filter(User.role == role)
            if active_only:
                query = query.filter(User.is_active == True)
            
            return query.order_by(User.created_at.desc()).all()
            
        except Exception as e:
            logger.error(f"Error getting users by role {role}: {str(e)}")
            return []
    
    async def search_users(
        self,
        db: Session,
        query: str,
        limit: int = 50,
        active_only: bool = True
    ) -> List[User]:
        """
        Search users by email or full name.
        
        Args:
            db: Database session
            query: Search query string
            limit: Maximum number of results
            active_only: Whether to only return active users
            
        Returns:
            List of User objects
        """
        try:
            search_filter = or_(
                User.email.ilike(f"%{query}%"),
                User.full_name.ilike(f"%{query}%")
            )
            
            db_query = db.query(User).filter(search_filter)
            if active_only:
                db_query = db_query.filter(User.is_active == True)
            
            return db_query.limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error searching users with query '{query}': {str(e)}")
            return []
    
    async def get_user_credentials(
        self,
        db: Session,
        user_id: uuid.UUID,
        provider: Optional[str] = None
    ) -> List[UserCredential]:
        """
        Get user credentials.
        
        Args:
            db: Database session
            user_id: User UUID
            provider: Optional provider filter
            
        Returns:
            List of UserCredential objects
        """
        try:
            query = db.query(UserCredential).filter(UserCredential.user_id == user_id)
            if provider:
                query = query.filter(UserCredential.provider == provider)
            
            return query.order_by(UserCredential.created_at.desc()).all()
            
        except Exception as e:
            logger.error(f"Error getting credentials for user {user_id}: {str(e)}")
            return []
    
    async def store_user_credentials(
        self,
        db: Session,
        user_id: uuid.UUID,
        provider: str,
        credentials: Dict[str, Any],
        expires_at: Optional[datetime] = None
    ) -> Optional[UserCredential]:
        """
        Store encrypted credentials for a user.
        
        Args:
            db: Database session
            user_id: User UUID
            provider: Credential provider (e.g., 'gmail', 'quickbooks')
            credentials: Credential data to encrypt and store
            expires_at: Optional expiration time
            
        Returns:
            UserCredential object or None if failed
        """
        try:
            # Use credential manager to store credentials
            credential_id = await self.credential_manager.store_credentials(
                user_id=str(user_id),
                provider=provider,
                credentials=credentials,
                expires_at=expires_at
            )
            
            if not credential_id:
                return None
            
            # Create user credential record
            user_credential = UserCredential(
                user_id=user_id,
                provider=provider,
                credential_id=credential_id,
                expires_at=expires_at
            )
            
            db.add(user_credential)
            db.commit()
            db.refresh(user_credential)
            
            # Create audit log
            audit_log = AuditLog(
                user_id=user_id,
                action="credentials_stored",
                resource_type="user_credential",
                resource_id=str(user_credential.id),
                details={
                    "provider": provider,
                    "expires_at": expires_at.isoformat() if expires_at else None
                }
            )
            db.add(audit_log)
            db.commit()
            
            logger.info(f"Stored credentials for user {user_id}, provider: {provider}")
            return user_credential
            
        except Exception as e:
            logger.error(f"Error storing credentials for user {user_id}: {str(e)}")
            db.rollback()
            return None
    
    async def get_user_audit_logs(
        self,
        db: Session,
        user_id: uuid.UUID,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get audit logs for a user.
        
        Args:
            db: Database session
            user_id: User UUID
            limit: Maximum number of logs to return
            
        Returns:
            List of AuditLog objects
        """
        try:
            return db.query(AuditLog).filter(
                AuditLog.user_id == user_id
            ).order_by(
                AuditLog.created_at.desc()
            ).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error getting audit logs for user {user_id}: {str(e)}")
            return []