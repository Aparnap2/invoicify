"""
Authentication service for JWT + RBAC implementation.

Handles user authentication, token management, and security operations
for the AP Intake & Validation system.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.core.security import (
    create_access_token, create_refresh_token, verify_token,
    get_password_hash, verify_password, generate_password_reset_token,
    verify_password_reset_token, TokenBlacklist, SecurityContext
)
from app.models.user import User, UserRole, UserAuditLog
from app.services.auth.user_service import UserService

logger = logging.getLogger(__name__)


class AuthenticationService:
    """
    Authentication service for managing user authentication and tokens.
    
    Provides comprehensive authentication operations including login, logout,
    token management, and password reset functionality.
    """
    
    def __init__(self):
        self.user_service = UserService()
    
    async def authenticate_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Tuple[User, Dict[str, str]]]:
        """
        Authenticate user with email and password.
        
        Args:
            db: Database session
            email: User email
            password: User password
            request_info: Request information for audit logging
            
        Returns:
            Tuple of (user, tokens) or None if authentication fails
        """
        try:
            # Get user by email
            user = await self.user_service.get_user_by_email(db, email)
            
            if not user:
                await self._log_failed_login(db, email, "user_not_found", request_info)
                return None
            
            # Check if user is active
            if not user.is_active:
                await self._log_failed_login(db, email, "user_inactive", request_info)
                return None
            
            # Verify password
            if not user.password_hash:
                await self._log_failed_login(db, email, "no_password", request_info)
                return None
            
            if not verify_password(password, user.password_hash):
                await self._log_failed_login(db, email, "invalid_password", request_info)
                # Update failed login attempts
                await self._update_failed_attempts(db, user)
                return None
            
            # Reset failed attempts on successful login
            await self._reset_failed_attempts(db, user)
            
            # Create tokens
            tokens = await self._create_user_tokens(user)
            
            # Log successful login
            await self._log_successful_login(db, user, request_info)
            
            logger.info(f"User authenticated successfully: {email}")
            return user, tokens
            
        except Exception as e:
            logger.error(f"Authentication error for {email}: {str(e)}")
            return None
    
    async def authenticate_with_token(
        self,
        db: AsyncSession,
        token: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> Optional[SecurityContext]:
        """
        Authenticate user with JWT token.
        
        Args:
            db: Database session
            token: JWT token
            request_info: Request information for audit logging
            
        Returns:
            Security context or None if authentication fails
        """
        try:
            # Verify token
            token_data = verify_token(token)
            if not token_data:
                return None
            
            # Check if token is blacklisted
            if hasattr(token_data, 'jti') and TokenBlacklist.is_blacklisted(token_data.jti):
                return None
            
            # Get user
            user = await self.user_service.get_user_by_id(db, token_data.user_id)
            if not user or not user.is_active:
                return None
            
            # Create security context
            security_context = SecurityContext(
                user=user,
                token_data=token_data,
                permissions=set(token_data.permissions),
                request_id=request_info.get('request_id') if request_info else None
            )
            
            return security_context
            
        except Exception as e:
            logger.error(f"Token authentication error: {str(e)}")
            return None
    
    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, str]]:
        """
        Refresh access token using refresh token.
        
        Args:
            db: Database session
            refresh_token: Refresh token
            request_info: Request information for audit logging
            
        Returns:
            New tokens or None if refresh fails
        """
        try:
            # Verify refresh token
            token_data = verify_token(refresh_token)
            if not token_data or token_data.token_type != "refresh":
                return None
            
            # Check if token is blacklisted
            if hasattr(token_data, 'jti') and TokenBlacklist.is_blacklisted(token_data.jti):
                return None
            
            # Get user
            user = await self.user_service.get_user_by_id(db, token_data.user_id)
            if not user or not user.is_active:
                return None
            
            # Blacklist old refresh token
            if hasattr(token_data, 'jti'):
                TokenBlacklist.blacklist_token(token_data.jti)
            
            # Create new tokens
            tokens = await self._create_user_tokens(user)
            
            # Log token refresh
            await self._log_token_refresh(db, user, request_info)
            
            logger.info(f"Token refreshed for user: {user.email}")
            return tokens
            
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return None
    
    async def logout_user(
        self,
        db: AsyncSession,
        token: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Logout user by blacklisting token.
        
        Args:
            db: Database session
            token: JWT token to blacklist
            request_info: Request information for audit logging
            
        Returns:
            True if logout successful
        """
        try:
            # Verify token
            token_data = verify_token(token)
            if not token_data:
                return False
            
            # Blacklist token
            if hasattr(token_data, 'jti'):
                TokenBlacklist.blacklist_token(token_data.jti)
            
            # Get user for audit logging
            user = await self.user_service.get_user_by_id(db, token_data.user_id)
            if user:
                await self._log_logout(db, user, request_info)
            
            logger.info(f"User logged out: {token_data.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return False
    
    async def logout_all_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Logout user from all sessions by updating password hash version.
        
        Args:
            db: Database session
            user_id: User ID
            request_info: Request information for audit logging
            
        Returns:
            True if logout successful
        """
        try:
            # Get user
            user = await self.user_service.get_user_by_id(db, user_id)
            if not user:
                return False
            
            # Update user to invalidate all tokens (by updating a version field)
            # This is a simplified approach - in production, you might want
            # a token version field in the user model
            await db.execute(
                update(User).where(User.id == user_id).values(
                    updated_at=datetime.now(timezone.utc)
                )
            )
            await db.commit()
            
            # Log logout all sessions
            await self._log_logout_all_sessions(db, user, request_info)
            
            logger.info(f"User logged out from all sessions: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Logout all sessions error: {str(e)}")
            await db.rollback()
            return False
    
    async def request_password_reset(
        self,
        db: AsyncSession,
        email: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Request password reset for user.
        
        Args:
            db: Database session
            email: User email
            request_info: Request information for audit logging
            
        Returns:
            True if reset request processed
        """
        try:
            # Get user
            user = await self.user_service.get_user_by_email(db, email)
            if not user:
                # Don't reveal if user exists or not
                return True
            
            # Generate reset token
            reset_token = generate_password_reset_token(email)
            
            # Store reset token (you might want to add a reset_tokens table)
            # For now, we'll just log it
            await self._log_password_reset_request(db, user, reset_token, request_info)
            
            # TODO: Send email with reset token
            # await self.email_service.send_password_reset_email(email, reset_token)
            
            logger.info(f"Password reset requested for: {email}")
            return True
            
        except Exception as e:
            logger.error(f"Password reset request error: {str(e)}")
            return False
    
    async def reset_password(
        self,
        db: AsyncSession,
        token: str,
        new_password: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Reset user password with reset token.
        
        Args:
            db: Database session
            token: Password reset token
            new_password: New password
            request_info: Request information for audit logging
            
        Returns:
            True if password reset successful
        """
        try:
            # Verify reset token
            email = verify_password_reset_token(token)
            if not email:
                return False
            
            # Get user
            user = await self.user_service.get_user_by_email(db, email)
            if not user:
                return False
            
            # Update password
            user.password_hash = get_password_hash(new_password)
            user.updated_at = datetime.now(timezone.utc)
            
            # Reset failed attempts
            user.failed_login_attempts = "0"
            
            await db.commit()
            
            # Log password reset
            await self._log_password_reset(db, user, request_info)
            
            logger.info(f"Password reset completed for: {email}")
            return True
            
        except Exception as e:
            logger.error(f"Password reset error: {str(e)}")
            await db.rollback()
            return False
    
    async def change_password(
        self,
        db: AsyncSession,
        user_id: str,
        current_password: str,
        new_password: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Change user password.
        
        Args:
            db: Database session
            user_id: User ID
            current_password: Current password
            new_password: New password
            request_info: Request information for audit logging
            
        Returns:
            True if password change successful
        """
        try:
            # Get user
            user = await self.user_service.get_user_by_id(db, user_id)
            if not user:
                return False
            
            # Verify current password
            if not user.password_hash or not verify_password(current_password, user.password_hash):
                return False
            
            # Update password
            user.password_hash = get_password_hash(new_password)
            user.updated_at = datetime.now(timezone.utc)
            
            await db.commit()
            
            # Log password change
            await self._log_password_change(db, user, request_info)
            
            logger.info(f"Password changed for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            await db.rollback()
            return False
    
    async def _create_user_tokens(self, user: User) -> Dict[str, str]:
        """Create access and refresh tokens for user."""
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,  # 30 minutes in seconds
            "refresh_expires_in": 7 * 24 * 60 * 60  # 7 days in seconds
        }
    
    async def _log_successful_login(
        self,
        db: AsyncSession,
        user: User,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log successful login."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="login_success",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "login_count": user.login_count,
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_failed_login(
        self,
        db: AsyncSession,
        email: str,
        reason: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log failed login attempt."""
        audit_log = UserAuditLog(
            user_id=None,  # User not found
            action="login_failed",
            resource_type="user",
            resource_id=email,
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=False,
            error_message=reason,
            details={
                "email": email,
                "reason": reason,
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_logout(
        self,
        db: AsyncSession,
        user: User,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log user logout."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="logout",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_logout_all_sessions(
        self,
        db: AsyncSession,
        user: User,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log logout from all sessions."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="logout_all_sessions",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_token_refresh(
        self,
        db: AsyncSession,
        user: User,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log token refresh."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="token_refresh",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_password_reset_request(
        self,
        db: AsyncSession,
        user: User,
        token: str,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log password reset request."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="password_reset_request",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "token": token[:10] + "...",  # Log partial token for security
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_password_reset(
        self,
        db: AsyncSession,
        user: User,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log password reset completion."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="password_reset_completed",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _log_password_change(
        self,
        db: AsyncSession,
        user: User,
        request_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log password change."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="password_changed",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request_info.get("ip_address") if request_info else None,
            user_agent=request_info.get("user_agent") if request_info else None,
            success=True,
            details={
                "request_id": request_info.get("request_id") if request_info else None
            }
        )
        db.add(audit_log)
        await db.commit()
    
    async def _update_failed_attempts(self, db: AsyncSession, user: User) -> None:
        """Update failed login attempts."""
        try:
            current_attempts = int(user.failed_login_attempts or "0")
            user.failed_login_attempts = str(current_attempts + 1)
            
            # Lock account after too many failed attempts
            if current_attempts + 1 >= 5:
                user.is_active = False
                await self._log_account_locked(db, user)
            
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to update failed attempts: {str(e)}")
    
    async def _reset_failed_attempts(self, db: AsyncSession, user: User) -> None:
        """Reset failed login attempts."""
        try:
            user.failed_login_attempts = "0"
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to reset failed attempts: {str(e)}")
    
    async def _log_account_locked(self, db: AsyncSession, user: User) -> None:
        """Log account lockout."""
        audit_log = UserAuditLog(
            user_id=user.id,
            action="account_locked",
            resource_type="user",
            resource_id=str(user.id),
            success=False,
            error_message="Too many failed login attempts",
            details={
                "failed_attempts": user.failed_login_attempts
            }
        )
        db.add(audit_log)
        await db.commit()


# Global authentication service instance
auth_service = AuthenticationService()