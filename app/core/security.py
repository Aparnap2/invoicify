"""
Enhanced security module for JWT + RBAC implementation.

Provides comprehensive authentication, authorization, and security utilities
for the AP Intake & Validation system.
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union, Set
from dataclasses import dataclass

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User, UserRole, UserAuditLog

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Token settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# HTTP Bearer scheme
security = HTTPBearer(auto_error=False)


@dataclass
class TokenData:
    """Token data structure."""
    user_id: str
    email: str
    role: UserRole
    permissions: List[str]
    token_type: str = "access"
    issued_at: datetime = None
    expires_at: datetime = None


@dataclass
class SecurityContext:
    """Security context for authenticated requests."""
    user: User
    token_data: TokenData
    permissions: Set[str]
    is_authenticated: bool = True
    request_id: str = None


class Permission:
    """Permission constants for RBAC."""
    
    # User management
    USER_READ = "users.read"
    USER_CREATE = "users.create"
    USER_UPDATE = "users.update"
    USER_DELETE = "users.delete"
    USER_MANAGE = "users.manage"
    
    # Invoice operations
    INVOICE_READ = "invoices.read"
    INVOICE_CREATE = "invoices.create"
    INVOICE_UPDATE = "invoices.update"
    INVOICE_DELETE = "invoices.delete"
    INVOICE_APPROVE = "invoices.approve"
    INVOICE_EXPORT = "invoices.export"
    INVOICE_ALL = "invoices.all"
    
    # Export operations
    EXPORT_READ = "exports.read"
    EXPORT_CREATE = "exports.create"
    EXPORT_UPDATE = "exports.update"
    EXPORT_DELETE = "exports.delete"
    EXPORT_ALL = "exports.all"
    
    # Credential management
    CREDENTIAL_READ = "credentials.read"
    CREDENTIAL_CREATE = "credentials.create"
    CREDENTIAL_UPDATE = "credentials.update"
    CREDENTIAL_DELETE = "credentials.delete"
    CREDENTIAL_MANAGE = "credentials.manage"
    CREDENTIAL_OWN = "credentials.own"
    
    # System administration
    SYSTEM_ADMIN = "system.admin"
    SYSTEM_MONITOR = "system.monitor"
    AUDIT_VIEW = "audit.view"
    
    # Vendor management
    VENDOR_READ = "vendors.read"
    VENDOR_CREATE = "vendors.create"
    VENDOR_UPDATE = "vendors.update"
    VENDOR_DELETE = "vendors.delete"
    VENDOR_MANAGE = "vendors.manage"


class RolePermissions:
    """Role-based permission mappings."""
    
    PERMISSIONS = {
        UserRole.ADMIN: [
            Permission.USER_MANAGE,
            Permission.SYSTEM_ADMIN,
            Permission.INVOICE_ALL,
            Permission.EXPORT_ALL,
            Permission.CREDENTIAL_MANAGE,
            Permission.AUDIT_VIEW,
            Permission.VENDOR_MANAGE,
        ],
        UserRole.PROCESSOR: [
            Permission.INVOICE_CREATE,
            Permission.INVOICE_UPDATE,
            Permission.INVOICE_READ,
            Permission.INVOICE_EXPORT,
            Permission.EXPORT_CREATE,
            Permission.EXPORT_READ,
            Permission.CREDENTIAL_OWN,
            Permission.VENDOR_READ,
            Permission.VENDOR_CREATE,
            Permission.VENDOR_UPDATE,
        ],
        UserRole.REVIEWER: [
            Permission.INVOICE_READ,
            Permission.INVOICE_UPDATE,
            Permission.INVOICE_APPROVE,
            Permission.EXPORT_READ,
            Permission.VENDOR_READ,
        ],
        UserRole.VIEWER: [
            Permission.INVOICE_READ,
            Permission.EXPORT_READ,
            Permission.VENDOR_READ,
        ]
    }
    
    @classmethod
    def get_permissions(cls, role: UserRole) -> List[str]:
        """Get permissions for a role."""
        return cls.PERMISSIONS.get(role, [])
    
    @classmethod
    def has_permission(cls, role: UserRole, permission: str) -> bool:
        """Check if role has specific permission."""
        return permission in cls.get_permissions(role)


def create_access_token(
    user: User,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Get user permissions
    permissions = RolePermissions.get_permissions(user.role)
    
    to_encode = {
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "permissions": permissions,
        "type": "access",
        "jti": secrets.token_urlsafe(16),  # JWT ID for token tracking
    }
    
    if additional_claims:
        to_encode.update(additional_claims)
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    user: User,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "sub": str(user.id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """Verify a JWT token and return token data."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        permissions = payload.get("permissions", [])
        token_type = payload.get("type", "access")
        iat = payload.get("iat")
        exp = payload.get("exp")
        
        if not all([user_id, email, role]):
            return None
        
        # Convert role string to enum
        if isinstance(role, str):
            try:
                role = UserRole(role)
            except ValueError:
                return None
        
        return TokenData(
            user_id=user_id,
            email=email,
            role=role,
            permissions=permissions,
            token_type=token_type,
            issued_at=datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None,
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        )
        
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a password hash."""
    return pwd_context.hash(password)


def generate_password_reset_token(email: str) -> str:
    """Generate a password reset token."""
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email}, 
        settings.SECRET_KEY, 
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify password reset token."""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token["sub"]
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> SecurityContext:
    """
    Get current authenticated user with full security context.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token
    token_data = verify_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check token type
    if token_data.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    try:
        user = await db.execute(
            select(User).where(
                User.id == token_data.user_id,
                User.is_active == True
            )
        ).scalar_one_or_none()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create security context
        security_context = SecurityContext(
            user=user,
            token_data=token_data,
            permissions=set(token_data.permissions),
            request_id=request.headers.get("X-Request-ID")
        )
        
        # Update last login and create audit log
        await update_user_login(db, user, request)
        
        return security_context
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    security_context: SecurityContext = Depends(get_current_user)
) -> SecurityContext:
    """Get current active user."""
    if not security_context.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return security_context


async def update_user_login(db: AsyncSession, user: User, request: Request) -> None:
    """Update user login information and create audit log."""
    try:
        # Update user login info
        user.last_login_at = datetime.now(timezone.utc)
        user.login_count = str(int(user.login_count or "0") + 1)
        
        # Create audit log
        audit_log = UserAuditLog(
            user_id=user.id,
            action="login",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            success=True,
            details={
                "login_count": user.login_count,
                "request_id": request.headers.get("X-Request-ID")
            }
        )
        
        db.add(audit_log)
        await db.commit()
        
    except Exception as e:
        # Log error but don't fail authentication
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"Failed to update user login: {str(e)}")
        await db.rollback()


def require_permissions(required_permissions: Union[str, List[str]]):
    """
    Dependency decorator to require specific permissions.
    
    Args:
        required_permissions: Permission(s) required to access the endpoint
        
    Usage:
        @router.get("/protected")
        async def protected_endpoint(
            security_context: SecurityContext = Depends(require_permissions("invoices.read"))
        ):
            return {"message": "Access granted"}
    """
    if isinstance(required_permissions, str):
        required_permissions = [required_permissions]
    
    async def permission_checker(
        security_context: SecurityContext = Depends(get_current_active_user)
    ) -> SecurityContext:
        """Check if user has required permissions."""
        user_permissions = security_context.permissions
        
        # Check if user has all required permissions
        missing_permissions = [
            perm for perm in required_permissions 
            if perm not in user_permissions
        ]
        
        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Missing: {', '.join(missing_permissions)}",
                headers={
                    "X-Required-Permissions": ", ".join(required_permissions),
                    "X-User-Permissions": ", ".join(user_permissions)
                }
            )
        
        return security_context
    
    return permission_checker


def require_role(required_roles: Union[UserRole, List[UserRole]]):
    """
    Dependency decorator to require specific roles.
    
    Args:
        required_roles: Role(s) required to access the endpoint
        
    Usage:
        @router.get("/admin")
        async def admin_endpoint(
            security_context: SecurityContext = Depends(require_role(UserRole.ADMIN))
        ):
            return {"message": "Admin access granted"}
    """
    if isinstance(required_roles, UserRole):
        required_roles = [required_roles]
    
    async def role_checker(
        security_context: SecurityContext = Depends(get_current_active_user)
    ) -> SecurityContext:
        """Check if user has required role."""
        if security_context.user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {', '.join([r.value for r in required_roles])}",
                headers={
                    "X-Required-Roles": ", ".join([r.value for r in required_roles]),
                    "X-User-Role": security_context.user.role
                }
            )
        
        return security_context
    
    return role_checker


def optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[SecurityContext]:
    """
    Optional authentication for public endpoints.
    Returns security context if authenticated, None otherwise.
    """
    if credentials is None:
        return None
    
    try:
        token_data = verify_token(credentials.credentials)
        if token_data is None or token_data.token_type != "access":
            return None
        
        user = await db.execute(
            select(User).where(
                User.id == token_data.user_id,
                User.is_active == True
            )
        ).scalar_one_or_none()
        
        if user is None:
            return None
        
        return SecurityContext(
            user=user,
            token_data=token_data,
            permissions=set(token_data.permissions),
            request_id=request.headers.get("X-Request-ID")
        )
        
    except Exception:
        return None


# Development authentication bypass
def get_dev_user() -> SecurityContext:
    """
    Development user for testing purposes.
    This allows bypassing authentication in development mode.
    """
    if settings.ENVIRONMENT.lower() in ["development", "dev"]:
        # Create mock user
        mock_user = User(
            id="dev-user-123",
            email="dev@example.com",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True
        )
        
        # Create token data
        token_data = TokenData(
            user_id="dev-user-123",
            email="dev@example.com",
            role=UserRole.ADMIN,
            permissions=RolePermissions.get_permissions(UserRole.ADMIN),
            token_type="access"
        )
        
        return SecurityContext(
            user=mock_user,
            token_data=token_data,
            permissions=set(token_data.permissions),
            request_id="dev-request"
        )
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Development user only available in development mode"
    )


# Token blacklist utilities
class TokenBlacklist:
    """Simple in-memory token blacklist for development."""
    
    _blacklisted_tokens: Set[str] = set()
    
    @classmethod
    def blacklist_token(cls, token_jti: str) -> None:
        """Add token to blacklist."""
        cls._blacklisted_tokens.add(token_jti)
    
    @classmethod
    def is_blacklisted(cls, token_jti: str) -> bool:
        """Check if token is blacklisted."""
        return token_jti in cls._blacklisted_tokens
    
    @classmethod
    def remove_token(cls, token_jti: str) -> None:
        """Remove token from blacklist."""
        cls._blacklisted_tokens.discard(token_jti)
    
    @classmethod
    def clear_expired(cls) -> None:
        """Clear expired tokens (simplified implementation)."""
        # In production, this would check token expiration times
        pass


# Security utilities
def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return hash_api_key(api_key) == hashed_key


def create_api_key() -> tuple[str, str]:
    """Create a new API key and return (key, hash)."""
    api_key = f"ak_{secrets.token_urlsafe(32)}"
    hashed_key = hash_api_key(api_key)
    return api_key, hashed_key


# Rate limiting with user context
def create_user_rate_limiter(max_requests: int = 100, window_seconds: int = 3600):
    """
    Create a user-based rate limiter.
    
    In production, use Redis-based rate limiting with proper user identification.
    """
    user_requests = {}
    
    def rate_limiter(security_context: SecurityContext = Depends(get_current_active_user)):
        user_id = security_context.user.id
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window_seconds)
        
        # Clean old requests
        user_requests[user_id] = [
            req_time for req_time in user_requests.get(user_id, [])
            if req_time > window_start
        ]
        
        # Check rate limit
        if len(user_requests[user_id]) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(window_seconds),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int((now + timedelta(seconds=window_seconds)).timestamp()))
                }
            )
        
        # Add current request
        user_requests[user_id].append(now)
        
        return security_context
    
    return rate_limiter


# Development token generator
def generate_dev_token() -> str:
    """Generate a development token for testing."""
    mock_user = User(
        id="dev-user-123",
        email="dev@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True
    )
    
    return create_access_token(
        user=mock_user,
        expires_delta=timedelta(days=365)  # Long-lived dev token
    )