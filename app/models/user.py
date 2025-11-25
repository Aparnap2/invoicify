"""
User and credential models for AP Intake & Validation system.

Defines user accounts, roles, and secure credential storage
following security best practices and GDPR compliance.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from enum import Enum

from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from ..db.base import BaseModel


logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles for access control."""
    ADMIN = "admin"
    PROCESSOR = "processor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class CredentialType(str, Enum):
    """Types of credentials stored in the system."""
    GMAIL_OAUTH = "gmail_oauth"
    QUICKBOOKS_OAUTH = "quickbooks_oauth"
    SENDGRID_API = "sendgrid_api"
    MAILGUN_API = "mailgun_api"
    CUSTOM_API = "custom_api"


class User(BaseModel):
    """
    User account model.
    
    Represents user accounts with role-based access control
    and audit trail for compliance.
    """
    __tablename__ = "users"
    
    # Primary key is inherited from BaseModel
    
    # User information
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(500), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    
    # Authentication and authorization
    password_hash = Column(String(255), nullable=True)  # For local auth if needed
    role = Column(String(50), nullable=False, default=UserRole.VIEWER)
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    
    # Preferences and metadata
    preferences = Column(JSON, nullable=True, default={})
    timezone = Column(String(50), nullable=True, default="UTC")
    language = Column(String(10), nullable=True, default="en")
    
    # Additional audit fields (created_at, updated_at inherited from BaseModel)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    login_count = Column(String(50), nullable=False, default="0")
    failed_login_attempts = Column(String(50), nullable=False, default="0")
    
    # Relationships
    credentials = relationship("UserCredential", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("UserAuditLog", back_populates="user", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_users_email', 'email'),
        Index('idx_users_role', 'role'),
        Index('idx_users_active', 'is_active'),
        Index('idx_users_last_login', 'last_login_at'),
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
    
    @property
    def display_name(self) -> str:
        """Get user's display name."""
        if self.full_name:
            return self.full_name
        elif self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        else:
            return self.email
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == UserRole.ADMIN
    
    @property
    def can_process_invoices(self) -> bool:
        """Check if user can process invoices."""
        return self.role in [UserRole.ADMIN, UserRole.PROCESSOR]
    
    @property
    def can_review_invoices(self) -> bool:
        """Check if user can review invoices."""
        return self.role in [UserRole.ADMIN, UserRole.PROCESSOR, UserRole.REVIEWER]
    
    def has_permission(self, permission: str) -> bool:
        """
        Check if user has specific permission.
        
        Args:
            permission: Permission to check
            
        Returns:
            True if user has permission
        """
        role_permissions = {
            UserRole.ADMIN: [
                "users.manage", "system.admin", "invoices.all", "exports.all",
                "credentials.manage", "audit.view"
            ],
            UserRole.PROCESSOR: [
                "invoices.create", "invoices.update", "invoices.read",
                "exports.create", "credentials.own"
            ],
            UserRole.REVIEWER: [
                "invoices.read", "invoices.update", "exports.read"
            ],
            UserRole.VIEWER: [
                "invoices.read", "exports.read"
            ]
        }
        
        return permission in role_permissions.get(self.role, [])
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert user to dictionary.
        
        Args:
            include_sensitive: Whether to include sensitive data
            
        Returns:
            User data as dictionary
        """
        data = {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "preferences": self.preferences or {},
            "timezone": self.timezone,
            "language": self.language,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "login_count": self.login_count,
            "display_name": self.display_name,
            "permissions": self._get_all_permissions(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_sensitive:
            data.update({
                "failed_login_attempts": self.failed_login_attempts
            })
        
        return data
    
    def _get_all_permissions(self) -> list:
        """Get all permissions for user's role."""
        role_permissions = {
            UserRole.ADMIN: [
                "users.manage", "system.admin", "invoices.all", "exports.all",
                "credentials.manage", "audit.view"
            ],
            UserRole.PROCESSOR: [
                "invoices.create", "invoices.update", "invoices.read",
                "exports.create", "credentials.own"
            ],
            UserRole.REVIEWER: [
                "invoices.read", "invoices.update", "exports.read"
            ],
            UserRole.VIEWER: [
                "invoices.read", "exports.read"
            ]
        }
        
        return role_permissions.get(self.role, [])


class UserCredential(BaseModel):
    """
    User credential model for secure storage.
    
    Stores encrypted OAuth tokens and API credentials
    with proper security and audit trail.
    """
    __tablename__ = "user_credentials"
    
    # Primary key is inherited from BaseModel
    
    # Foreign key to user
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="credentials")
    
    # Credential information
    credential_type = Column(String(50), nullable=False)
    credential_name = Column(String(255), nullable=True)  # e.g., "Gmail - user@example.com"
    encrypted_credentials = Column(Text, nullable=False)  # Encrypted credential data
    
    # Status and lifecycle
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata and audit
    metadata = Column(JSON, nullable=True, default={})  # Additional credential metadata
    access_count = Column(String(50), nullable=False, default="0")  # Track usage
    
    # Relationships
    audit_logs = relationship("CredentialAuditLog", back_populates="credential", cascade="all, delete-orphan")
    
    # Indexes and constraints
    __table_args__ = (
        Index('idx_user_credentials_user_type', 'user_id', 'credential_type'),
        Index('idx_user_credentials_active', 'is_active'),
        Index('idx_user_credentials_expires', 'expires_at'),
        UniqueConstraint('user_id', 'credential_type', name='uq_user_credential_type'),
    )
    
    def __repr__(self):
        return f"<UserCredential(id={self.id}, user_id={self.user_id}, type={self.credential_type})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if credential is expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def expires_soon(self, days: int = 7) -> bool:
        """
        Check if credential expires within specified days.
        
        Args:
            days: Number of days to check
            
        Returns:
            True if expires within specified days
        """
        if not self.expires_at:
            return False
        expiry_threshold = datetime.now(timezone.utc) + timedelta(days=days)
        return self.expires_at < expiry_threshold
    
    def increment_access_count(self) -> None:
        """Increment access count for audit trail."""
        try:
            current_count = int(self.access_count or "0")
            self.access_count = str(current_count + 1)
            self.last_accessed_at = datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            self.access_count = "1"
            self.last_accessed_at = datetime.now(timezone.utc)
    
    def to_dict(self, include_credentials: bool = False) -> Dict[str, Any]:
        """
        Convert credential to dictionary.
        
        Args:
            include_credentials: Whether to include encrypted credentials
            
        Returns:
            Credential data as dictionary
        """
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "credential_type": self.credential_type,
            "credential_name": self.credential_name,
            "is_active": self.is_active,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "metadata": self.metadata or {},
            "access_count": self.access_count,
            "is_expired": self.is_expired,
            "expires_soon": self.expires_soon(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_credentials:
            data["encrypted_credentials"] = self.encrypted_credentials
        
        return data


class UserAuditLog(BaseModel):
    """
    User audit log for compliance and security monitoring.
    
    Tracks all user actions for audit trail and security analysis.
    """
    __tablename__ = "user_audit_logs"
    
    # Primary key is inherited from BaseModel
    
    # Foreign key to user
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="audit_logs")
    
    # Audit information
    action = Column(String(100), nullable=False)  # e.g., "login", "credential_created", "role_changed"
    resource_type = Column(String(50), nullable=True)  # e.g., "user", "credential", "invoice"
    resource_id = Column(String(255), nullable=True)  # ID of affected resource
    
    # Request information
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Result and details
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True, default={})
    
    # Indexes
    __table_args__ = (
        Index('idx_user_audit_user_action', 'user_id', 'action'),
        Index('idx_user_audit_timestamp', 'created_at'),
        Index('idx_user_audit_ip', 'ip_address'),
    )
    
    def __repr__(self):
        return f"<UserAuditLog(id={self.id}, user_id={self.user_id}, action={self.action})>"


class CredentialAuditLog(BaseModel):
    """
    Credential audit log for security monitoring.
    
    Tracks all credential operations for security analysis
    and compliance requirements.
    """
    __tablename__ = "credential_audit_logs"
    
    # Primary key is inherited from BaseModel
    
    # Foreign key to credential
    credential_id = Column(UUID(as_uuid=True), ForeignKey("user_credentials.id"), nullable=False)
    credential = relationship("UserCredential", back_populates="audit_logs")
    
    # Audit information
    action = Column(String(50), nullable=False)  # e.g., "created", "accessed", "refreshed", "deleted", "expired"
    
    # Request information
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Result and details
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True, default={})
    
    # Indexes
    __table_args__ = (
        Index('idx_credential_audit_credential_action', 'credential_id', 'action'),
        Index('idx_credential_audit_timestamp', 'created_at'),
    )
    
    def __repr__(self):
        return f"<CredentialAuditLog(id={self.id}, credential_id={self.credential_id}, action={self.action})>"