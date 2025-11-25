"""
Authentication schemas for JWT + RBAC system.

Defines request and response models for authentication endpoints
in the AP Intake & Validation system.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, validator
from app.models.user import UserRole


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")
    remember_me: Optional[bool] = Field(False, description="Remember me for extended session")
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class TokenResponse(BaseModel):
    """Token response schema."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="JWT refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration time in seconds")
    refresh_expires_in: Optional[int] = Field(None, description="Refresh token expiration time in seconds")


class UserResponse(BaseModel):
    """User response schema."""
    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="User full name")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="User active status")
    is_verified: bool = Field(..., description="User verification status")
    permissions: List[str] = Field(..., description="User permissions")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    login_count: Optional[str] = Field(None, description="Login count")
    
    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response schema."""
    user: UserResponse = Field(..., description="User information")
    tokens: TokenResponse = Field(..., description="JWT tokens")


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str = Field(..., description="JWT refresh token")


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: EmailStr = Field(..., description="User email address")


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password")
    confirm_password: str = Field(..., min_length=8, description="Confirm new password")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")
    confirm_password: str = Field(..., min_length=8, description="Confirm new password")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserCreateRequest(BaseModel):
    """User creation request schema."""
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="User full name")
    password: str = Field(..., min_length=8, description="User password")
    role: UserRole = Field(UserRole.VIEWER, description="User role")
    is_active: bool = Field(True, description="User active status")
    
    @validator('password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserUpdateRequest(BaseModel):
    """User update request schema."""
    full_name: Optional[str] = Field(None, description="User full name")
    role: Optional[UserRole] = Field(None, description="User role")
    is_active: Optional[bool] = Field(None, description="User active status")
    timezone: Optional[str] = Field(None, description="User timezone")
    language: Optional[str] = Field(None, description="User language")
    preferences: Optional[Dict[str, Any]] = Field(None, description="User preferences")


class UserProfileResponse(BaseModel):
    """User profile response schema."""
    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="User full name")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="User active status")
    is_verified: bool = Field(..., description="User verification status")
    permissions: List[str] = Field(..., description="User permissions")
    timezone: Optional[str] = Field(None, description="User timezone")
    language: Optional[str] = Field(None, description="User language")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    login_count: Optional[str] = Field(None, description="Login count")
    created_at: Optional[datetime] = Field(None, description="Account creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    class Config:
        from_attributes = True


class TokenVerificationResponse(BaseModel):
    """Token verification response schema."""
    valid: bool = Field(..., description="Token validity status")
    user_id: Optional[str] = Field(None, description="User ID if valid")
    email: Optional[str] = Field(None, description="User email if valid")
    role: Optional[UserRole] = Field(None, description="User role if valid")
    expires_at: Optional[datetime] = Field(None, description="Token expiration time")
    permissions: Optional[List[str]] = Field(None, description="User permissions if valid")


class PermissionCheckRequest(BaseModel):
    """Permission check request schema."""
    permission: str = Field(..., description="Permission to check")
    resource_id: Optional[str] = Field(None, description="Resource ID for context")


class PermissionCheckResponse(BaseModel):
    """Permission check response schema."""
    has_permission: bool = Field(..., description="Whether user has permission")
    permission: str = Field(..., description="Checked permission")
    resource_id: Optional[str] = Field(None, description="Resource ID if provided")
    reason: Optional[str] = Field(None, description="Reason for denial if applicable")


class RolePermissionResponse(BaseModel):
    """Role permissions response schema."""
    role: UserRole = Field(..., description="User role")
    permissions: List[str] = Field(..., description="Role permissions")
    description: Optional[str] = Field(None, description="Role description")


class AuditLogResponse(BaseModel):
    """Audit log response schema."""
    id: str = Field(..., description="Log ID")
    user_id: Optional[str] = Field(None, description="User ID")
    action: str = Field(..., description="Action performed")
    resource_type: Optional[str] = Field(None, description="Resource type")
    resource_id: Optional[str] = Field(None, description="Resource ID")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="User agent")
    success: bool = Field(..., description="Action success status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")
    created_at: datetime = Field(..., description="Log timestamp")
    
    class Config:
        from_attributes = True


class SessionInfoResponse(BaseModel):
    """Session information response schema."""
    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="User agent")
    created_at: datetime = Field(..., description="Session creation time")
    last_accessed: datetime = Field(..., description="Last access time")
    expires_at: datetime = Field(..., description="Session expiration time")
    is_active: bool = Field(..., description="Session active status")
    
    class Config:
        from_attributes = True


class SecurityConfigResponse(BaseModel):
    """Security configuration response schema."""
    password_min_length: int = Field(..., description="Minimum password length")
    password_require_uppercase: bool = Field(..., description="Require uppercase letters")
    password_require_lowercase: bool = Field(..., description="Require lowercase letters")
    password_require_digits: bool = Field(..., description="Require digits")
    password_require_special: bool = Field(..., description="Require special characters")
    session_timeout_minutes: int = Field(..., description="Session timeout in minutes")
    max_login_attempts: int = Field(..., description="Maximum login attempts")
    lockout_duration_minutes: int = Field(..., description="Account lockout duration")
    enable_2fa: bool = Field(..., description="Two-factor authentication enabled")
    enable_oauth: bool = Field(..., description="OAuth authentication enabled")


class ApiKeyResponse(BaseModel):
    """API key response schema."""
    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key_prefix: str = Field(..., description="API key prefix (first 8 characters)")
    permissions: List[str] = Field(..., description="API key permissions")
    is_active: bool = Field(..., description="API key active status")
    expires_at: Optional[datetime] = Field(None, description="API key expiration")
    last_used: Optional[datetime] = Field(None, description="Last usage timestamp")
    created_at: datetime = Field(..., description="API key creation timestamp")
    
    class Config:
        from_attributes = True


class ApiKeyCreateRequest(BaseModel):
    """API key creation request schema."""
    name: str = Field(..., description="API key name")
    permissions: List[str] = Field(..., description="API key permissions")
    expires_at: Optional[datetime] = Field(None, description="API key expiration")
    
    @validator('permissions')
    def validate_permissions(cls, v):
        if not v:
            raise ValueError('At least one permission is required')
        return v


class ApiKeyCreateResponse(BaseModel):
    """API key creation response schema."""
    api_key: str = Field(..., description="Full API key (only shown once)")
    key_info: ApiKeyResponse = Field(..., description="API key information")


class SecurityEventResponse(BaseModel):
    """Security event response schema."""
    id: str = Field(..., description="Event ID")
    event_type: str = Field(..., description="Event type")
    severity: str = Field(..., description="Event severity")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="User agent")
    description: str = Field(..., description="Event description")
    details: Dict[str, Any] = Field(default_factory=dict, description="Event details")
    created_at: datetime = Field(..., description="Event timestamp")
    resolved: bool = Field(False, description="Event resolved status")
    resolved_at: Optional[datetime] = Field(None, description="Event resolution timestamp")
    
    class Config:
        from_attributes = True


class PasswordStrengthResponse(BaseModel):
    """Password strength response schema."""
    is_strong: bool = Field(..., description="Password strength status")
    score: int = Field(..., description="Password strength score (0-100)")
    feedback: List[str] = Field(..., description="Password improvement suggestions")
    requirements_met: Dict[str, bool] = Field(..., description="Password requirements met")


class TwoFactorSetupResponse(BaseModel):
    """Two-factor authentication setup response schema."""
    secret: str = Field(..., description="TOTP secret")
    qr_code: str = Field(..., description="QR code for setup")
    backup_codes: List[str] = Field(..., description="Backup codes")
    instructions: str = Field(..., description="Setup instructions")


class TwoFactorVerifyRequest(BaseModel):
    """Two-factor verification request schema."""
    code: str = Field(..., description="TOTP code")
    backup_code: Optional[str] = Field(None, description="Backup code")


class TwoFactorEnableResponse(BaseModel):
    """Two-factor enable response schema."""
    enabled: bool = Field(..., description="2FA enabled status")
    recovery_codes: List[str] = Field(..., description="New recovery codes")


class OAuthProviderResponse(BaseModel):
    """OAuth provider response schema."""
    provider: str = Field(..., description="OAuth provider name")
    display_name: str = Field(..., description="Provider display name")
    auth_url: str = Field(..., description="Authorization URL")
    client_id: str = Field(..., description="Client ID")
    scopes: List[str] = Field(..., description="Requested scopes")
    enabled: bool = Field(..., description="Provider enabled status")


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request schema."""
    code: str = Field(..., description="Authorization code")
    state: str = Field(..., description="State parameter")
    provider: str = Field(..., description="OAuth provider")


class OAuthTokenResponse(BaseModel):
    """OAuth token response schema."""
    access_token: str = Field(..., description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    token_type: str = Field(..., description="Token type")
    expires_in: Optional[int] = Field(None, description="Token expiration in seconds")
    scope: Optional[str] = Field(None, description="Token scope")
    provider: str = Field(..., description="OAuth provider")