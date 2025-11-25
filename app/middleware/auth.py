"""
Authentication and authorization middleware for AP Intake & Validation system.

Provides JWT-based authentication and role-based authorization.
"""

import logging
from typing import Optional, List, Callable
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..api.responses import AuthenticationError, AuthorizationError
from ..config import get_settings


logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    JWT authentication middleware.
    
    Validates JWT tokens and sets user context in request state.
    """
    
    def __init__(
        self,
        app,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        exclude_paths: Optional[List[str]] = None
    ):
        """
        Initialize authentication middleware.
        
        Args:
            app: FastAPI application
            secret_key: JWT secret key
            algorithm: JWT algorithm
            exclude_paths: Paths to exclude from authentication
        """
        super().__init__(app)
        
        settings = get_settings()
        self.secret_key = secret_key or settings.SECRET_KEY
        self.algorithm = algorithm
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/auth/login",
            "/auth/register",
            "/auth/refresh"
        ]
        
        self.security = HTTPBearer(auto_error=False)
        
        logger.info("AuthenticationMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and validate authentication.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Skip authentication for excluded paths
        if self._should_exclude_path(request.url.path):
            return await call_next(request)
        
        try:
            # Extract and validate token
            credentials = await self.security(request)
            
            if not credentials:
                raise AuthenticationError("No authentication token provided")
            
            # Validate JWT token
            payload = self._validate_token(credentials.credentials)
            
            # Set user context
            request.state.user = payload
            request.state.user_id = payload.get('sub')
            request.state.user_email = payload.get('email')
            request.state.user_roles = payload.get('roles', [])
            
            logger.debug(f"Authenticated user: {request.state.user_email}")
            
        except AuthenticationError as e:
            logger.warning(f"Authentication failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise AuthenticationError("Authentication failed")
        
        return await call_next(request)
    
    def _should_exclude_path(self, path: str) -> bool:
        """
        Check if path should be excluded from authentication.
        
        Args:
            path: Request path
            
        Returns:
            True if path should be excluded
        """
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    def _validate_token(self, token: str) -> dict:
        """
        Validate JWT token and return payload.
        
        Args:
            token: JWT token string
            
        Returns:
            Token payload
            
        Raises:
            AuthenticationError: If token is invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            # Check required claims
            if 'sub' not in payload:
                raise AuthenticationError("Invalid token: missing subject")
            
            if 'exp' not in payload:
                raise AuthenticationError("Invalid token: missing expiration")
            
            return payload
            
        except JWTError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")
        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {str(e)}")


class AuthorizationMiddleware(BaseHTTPMiddleware):
    """
    Role-based authorization middleware.
    
    Checks if authenticated user has required permissions.
    """
    
    def __init__(
        self,
        app,
        role_permissions: Optional[dict] = None,
        exclude_paths: Optional[List[str]] = None
    ):
        """
        Initialize authorization middleware.
        
        Args:
            app: FastAPI application
            role_permissions: Role to permissions mapping
            exclude_paths: Paths to exclude from authorization
        """
        super().__init__(app)
        
        self.role_permissions = role_permissions or self._get_default_permissions()
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/auth/login",
            "/auth/register",
            "/auth/refresh",
            "/profile"
        ]
        
        logger.info("AuthorizationMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and validate authorization.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Skip authorization for excluded paths
        if self._should_exclude_path(request.url.path):
            return await call_next(request)
        
        # Check if user is authenticated
        if not hasattr(request.state, 'user'):
            raise AuthenticationError("User not authenticated")
        
        # Get required permission for this path
        required_permission = self._get_required_permission(request)
        
        if required_permission:
            # Check if user has required permission
            user_roles = getattr(request.state, 'user_roles', [])
            
            if not self._has_permission(user_roles, required_permission):
                logger.warning(
                    f"Access denied for user {request.state.user_email}: "
                    f"missing permission {required_permission}"
                )
                raise AuthorizationError(
                    "Access denied",
                    required_permission=required_permission
                )
            
            logger.debug(f"User {request.state.user_email} authorized for {required_permission}")
        
        return await call_next(request)
    
    def _should_exclude_path(self, path: str) -> bool:
        """
        Check if path should be excluded from authorization.
        
        Args:
            path: Request path
            
        Returns:
            True if path should be excluded
        """
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    def _get_required_permission(self, request: Request) -> Optional[str]:
        """
        Get required permission for the request path.
        
        Args:
            request: HTTP request
            
        Returns:
            Required permission or None
        """
        path = request.url.path
        method = request.method
        
        # Define path-permission mappings
        path_permissions = {
            # Admin endpoints
            "/admin": "admin.access",
            "/admin/users": "admin.users.manage",
            "/admin/system": "admin.system.manage",
            
            # Invoice endpoints
            "/invoices": {
                "GET": "invoices.read",
                "POST": "invoices.create",
                "PUT": "invoices.update",
                "DELETE": "invoices.delete"
            },
            "/invoices/": {
                "GET": "invoices.read",
                "POST": "invoices.create",
                "PUT": "invoices.update",
                "DELETE": "invoices.delete"
            },
            
            # Email endpoints
            "/emails": "emails.manage",
            "/emails/": "emails.manage",
            
            # Dashboard endpoints
            "/dashboard": "dashboard.access",
            "/dashboard/": "dashboard.access",
            
            # Reports endpoints
            "/reports": "reports.read",
            "/reports/": "reports.read",
            
            # Export endpoints
            "/exports": "exports.create",
            "/exports/": "exports.create"
        }
        
        # Check exact path matches
        if path in path_permissions:
            permission = path_permissions[path]
            return permission if isinstance(permission, str) else None
        
        # Check path prefixes with method-specific permissions
        for path_prefix, permissions in path_permissions.items():
            if isinstance(permissions, dict) and path.startswith(path_prefix):
                return permissions.get(method)
        
        return None
    
    def _has_permission(self, user_roles: List[str], required_permission: str) -> bool:
        """
        Check if user roles contain the required permission.
        
        Args:
            user_roles: List of user roles
            required_permission: Required permission
            
        Returns:
            True if user has permission
        """
        for role in user_roles:
            role_perms = self.role_permissions.get(role, [])
            if required_permission in role_perms:
                return True
        
        return False
    
    def _get_default_permissions(self) -> dict:
        """
        Get default role permissions mapping.
        
        Returns:
            Default permissions dictionary
        """
        return {
            "admin": [
                "admin.access",
                "admin.users.manage",
                "admin.system.manage",
                "invoices.read",
                "invoices.create",
                "invoices.update",
                "invoices.delete",
                "emails.manage",
                "dashboard.access",
                "reports.read",
                "exports.create"
            ],
            "processor": [
                "invoices.read",
                "invoices.create",
                "invoices.update",
                "emails.manage",
                "dashboard.access",
                "reports.read"
            ],
            "reviewer": [
                "invoices.read",
                "invoices.update",
                "dashboard.access",
                "reports.read"
            ],
            "viewer": [
                "invoices.read",
                "dashboard.access",
                "reports.read"
            ]
        }


def create_jwt_token(
    user_id: str,
    email: str,
    roles: List[str],
    expires_delta: Optional[int] = None,
    secret_key: Optional[str] = None
) -> str:
    """
    Create JWT token for user.
    
    Args:
        user_id: User ID
        email: User email
        roles: List of user roles
        expires_delta: Token expiration in seconds
        secret_key: JWT secret key
        
    Returns:
        JWT token string
    """
    from datetime import datetime, timedelta
    
    settings = get_settings()
    secret_key = secret_key or settings.SECRET_KEY
    
    now = datetime.utcnow()
    expires_delta = expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    exp = now + timedelta(seconds=expires_delta)
    
    payload = {
        'sub': user_id,
        'email': email,
        'roles': roles,
        'iat': now,
        'exp': exp
    }
    
    return jwt.encode(payload, secret_key, algorithm="HS256")


def verify_jwt_token(token: str, secret_key: Optional[str] = None) -> dict:
    """
    Verify and decode JWT token.
    
    Args:
        token: JWT token string
        secret_key: JWT secret key
        
    Returns:
        Token payload
        
    Raises:
        AuthenticationError: If token is invalid
    """
    settings = get_settings()
    secret_key = secret_key or settings.SECRET_KEY
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")