"""
Authentication and authorization middleware for JWT + RBAC system.

Provides middleware for request authentication, authorization, and security
enforcement for AP Intake & Validation system.
"""

import logging
import time
from typing import Callable, List, Optional, Set

from fastapi import Request, Response, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.security import (
    SecurityContext, verify_token, TokenBlacklist,
    get_current_user, optional_auth
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for JWT token validation.
    
    Automatically validates JWT tokens and sets security context
    in request state for downstream middleware and endpoints.
    """
    
    def __init__(self, app, public_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.public_paths = public_paths or []
        self.security = HTTPBearer(auto_error=False)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and validate authentication.
        
        Args:
            request: HTTP request
            call_next: Next middleware/endpoint
            
        Returns:
            HTTP response
        """
        start_time = time.time()
        
        try:
            # Check if path is public
            if self._is_public_path(request.url.path):
                request.state.security_context = None
                return await call_next(request)
            
            # Extract token from header
            credentials = await self.security(request)
            
            if credentials is None:
                # No token provided - set anonymous context
                request.state.security_context = None
                return await call_next(request)
            
            # Validate token
            token_data = verify_token(credentials.credentials)
            if token_data is None:
                return self._create_unauthorized_response("Invalid token")
            
            # Check if token is blacklisted
            if hasattr(token_data, 'jti') and TokenBlacklist.is_blacklisted(token_data.jti):
                return self._create_unauthorized_response("Token has been revoked")
            
            # Check token type
            if token_data.token_type != "access":
                return self._create_unauthorized_response("Invalid token type")
            
            # Get user from database (simplified - in production, use dependency injection)
            try:
                from app.db.session import get_db
                async for db in get_db():
                    security_context = await get_current_user(request, credentials, db)
                    request.state.security_context = security_context
                    break
            except Exception as e:
                logger.error(f"Failed to get user from database: {str(e)}")
                return self._create_unauthorized_response("Authentication failed")
            
            # Continue processing
            response = await call_next(request)
            
            # Add security headers
            self._add_security_headers(response)
            
            # Log request duration
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except HTTPException as e:
            return self._create_error_response(e.status_code, e.detail)
        except Exception as e:
            logger.error(f"Authentication middleware error: {str(e)}")
            return self._create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal server error"
            )
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require authentication)."""
        for public_path in self.public_paths:
            if path.startswith(public_path):
                return True
        return False
    
    def _add_security_headers(self, response: Response) -> None:
        """Add security headers to response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    def _create_unauthorized_response(self, message: str) -> JSONResponse:
        """Create unauthorized response."""
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": "Unauthorized",
                "message": message,
                "timestamp": time.time()
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    def _create_error_response(self, status_code: int, message: str) -> JSONResponse:
        """Create error response."""
        return JSONResponse(
            status_code=status_code,
            content={
                "error": "Error",
                "message": message,
                "timestamp": time.time()
            }
        )


class AuthorizationMiddleware(BaseHTTPMiddleware):
    """
    Authorization middleware for RBAC enforcement.
    
    Enforces role-based access control based on endpoint
    requirements and user permissions.
    """
    
    def __init__(self, app, permission_map: Optional[dict] = None):
        super().__init__(app)
        self.permission_map = permission_map or {}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and enforce authorization.
        
        Args:
            request: HTTP request
            call_next: Next middleware/endpoint
            
        Returns:
            HTTP response
        """
        try:
            # Get security context from request state
            security_context = getattr(request.state, 'security_context', None)
            
            # Check if endpoint requires specific permissions
            required_permissions = self._get_required_permissions(request)
            
            if not required_permissions:
                # No specific permissions required
                return await call_next(request)
            
            # Check if user is authenticated
            if security_context is None:
                return self._create_forbidden_response(
                    "Authentication required for this endpoint"
                )
            
            # Check if user has required permissions
            user_permissions = security_context.permissions
            missing_permissions = [
                perm for perm in required_permissions 
                if perm not in user_permissions
            ]
            
            if missing_permissions:
                return self._create_forbidden_response(
                    f"Insufficient permissions. Missing: {', '.join(missing_permissions)}"
                )
            
            # Continue processing
            return await call_next(request)
            
        except HTTPException as e:
            return self._create_error_response(e.status_code, e.detail)
        except Exception as e:
            logger.error(f"Authorization middleware error: {str(e)}")
            return self._create_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Internal server error"
            )
    
    def _get_required_permissions(self, request: Request) -> List[str]:
        """Get required permissions for the endpoint."""
        path = request.url.path
        method = request.method
        
        # Check permission map
        for pattern, permissions in self.permission_map.items():
            if self._path_matches_pattern(path, pattern):
                if isinstance(permissions, dict):
                    # Method-specific permissions
                    return permissions.get(method.lower(), [])
                elif isinstance(permissions, list):
                    # General permissions for all methods
                    return permissions
        
        return []
    
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches permission pattern."""
        # Simple pattern matching - can be enhanced with regex
        if pattern.endswith('*'):
            return path.startswith(pattern[:-1])
        return path == pattern
    
    def _create_forbidden_response(self, message: str) -> JSONResponse:
        """Create forbidden response."""
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "Forbidden",
                "message": message,
                "timestamp": time.time()
            }
        )
    
    def _create_error_response(self, status_code: int, message: str) -> JSONResponse:
        """Create error response."""
        return JSONResponse(
            status_code=status_code,
            content={
                "error": "Error",
                "message": message,
                "timestamp": time.time()
            }
        )


class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """
    Security logging middleware for audit trail.
    
    Logs security-related events and requests for
    compliance and monitoring purposes.
    """
    
    def __init__(self, app, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = log_level.upper()
        self.logger = logging.getLogger("security_audit")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log security events.
        
        Args:
            request: HTTP request
            call_next: Next middleware/endpoint
            
        Returns:
            HTTP response
        """
        start_time = time.time()
        
        try:
            # Get security context
            security_context = getattr(request.state, 'security_context', None)
            
            # Log request
            self._log_request(request, security_context)
            
            # Process request
            response = await call_next(request)
            
            # Log response
            self._log_response(request, response, security_context, start_time)
            
            return response
            
        except Exception as e:
            self._log_error(request, e)
            raise
    
    def _log_request(self, request: Request, security_context: Optional[SecurityContext]) -> None:
        """Log incoming request."""
        user_info = "anonymous"
        if security_context and security_context.user:
            user_info = f"user:{security_context.user.email}"
        
        log_data = {
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query) if request.url.query else None,
            "user": user_info,
            "ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "timestamp": time.time()
        }
        
        if self.log_level == "DEBUG":
            self.logger.debug(f"Security request: {log_data}")
        elif self.log_level == "INFO":
            self.logger.info(f"Request: {request.method} {request.url.path} - {user_info}")
    
    def _log_response(
        self, 
        request: Request, 
        response: Response, 
        security_context: Optional[SecurityContext],
        start_time: float
    ) -> None:
        """Log response."""
        process_time = time.time() - start_time
        status_code = response.status_code
        
        # Log security-relevant status codes
        if status_code >= 400:
            user_info = "anonymous"
            if security_context and security_context.user:
                user_info = f"user:{security_context.user.email}"
            
            log_data = {
                "event": "response_error",
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "user": user_info,
                "ip": request.client.host if request.client else None,
                "process_time": process_time,
                "timestamp": time.time()
            }
            
            self.logger.warning(f"Security response error: {log_data}")
    
    def _log_error(self, request: Request, error: Exception) -> None:
        """Log error."""
        log_data = {
            "event": "error",
            "method": request.method,
            "path": request.url.path,
            "error": str(error),
            "ip": request.client.host if request.client else None,
            "timestamp": time.time()
        }
        
        self.logger.error(f"Security error: {log_data}")


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for API protection.
    
    Implements rate limiting based on user ID or IP address
    to prevent abuse and ensure fair usage.
    """
    
    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis_client = redis_client
        self.requests = {}  # Fallback to memory if no Redis
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and enforce rate limits.
        
        Args:
            request: HTTP request
            call_next: Next middleware/endpoint
            
        Returns:
            HTTP response
        """
        try:
            # Get identifier (user ID or IP)
            identifier = self._get_identifier(request)
            
            # Check rate limit
            if not self._check_rate_limit(identifier, request):
                return self._create_rate_limit_response()
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            self._add_rate_limit_headers(response, identifier)
            
            return response
            
        except Exception as e:
            logger.error(f"Rate limiting middleware error: {str(e)}")
            return await call_next(request)
    
    def _get_identifier(self, request: Request) -> str:
        """Get rate limit identifier (user ID or IP)."""
        security_context = getattr(request.state, 'security_context', None)
        
        if security_context and security_context.user:
            return f"user:{security_context.user.id}"
        
        return f"ip:{request.client.host if request.client else 'unknown'}"
    
    def _check_rate_limit(self, identifier: str, request: Request) -> bool:
        """Check if request is within rate limits."""
        # Simplified rate limiting - in production, use Redis with proper algorithms
        current_time = time.time()
        window_start = current_time - 3600  # 1 hour window
        
        # Get existing requests for identifier
        requests = self.requests.get(identifier, [])
        
        # Clean old requests
        requests = [req_time for req_time in requests if req_time > window_start]
        
        # Check limit (100 requests per hour)
        if len(requests) >= 100:
            return False
        
        # Add current request
        requests.append(current_time)
        self.requests[identifier] = requests
        
        return True
    
    def _add_rate_limit_headers(self, response: Response, identifier: str) -> None:
        """Add rate limit headers to response."""
        requests = self.requests.get(identifier, [])
        remaining = max(0, 100 - len(requests))
        
        response.headers["X-RateLimit-Limit"] = "100"
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + 3600))
    
    def _create_rate_limit_response(self) -> JSONResponse:
        """Create rate limit response."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate Limit Exceeded",
                "message": "Too many requests. Please try again later.",
                "timestamp": time.time()
            },
            headers={
                "Retry-After": "3600",
                "X-RateLimit-Limit": "100",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + 3600))
            }
        )


class CORSMiddleware(BaseHTTPMiddleware):
    """
    CORS middleware for cross-origin requests.
    
    Handles Cross-Origin Resource Sharing headers
    for API access from web applications.
    """
    
    def __init__(self, app, allowed_origins: List[str] = None):
        super().__init__(app)
        self.allowed_origins = allowed_origins or ["*"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add CORS headers.
        
        Args:
            request: HTTP request
            call_next: Next middleware/endpoint
            
        Returns:
            HTTP response
        """
        response = await call_next(request)
        
        # Add CORS headers
        origin = request.headers.get("Origin")
        
        if origin and self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"
        
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Request-ID"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "86400"
        
        return response
    
    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed."""
        if "*" in self.allowed_origins:
            return True
        
        return origin in self.allowed_origins


# Middleware factory functions
def create_auth_middleware(public_paths: Optional[List[str]] = None) -> AuthenticationMiddleware:
    """Create authentication middleware."""
    return AuthenticationMiddleware(
        app=None,  # Will be set when added to app
        public_paths=public_paths or [
            "/health",
            "/metrics",
            "/api/v1/auth/login",
            "/api/v1/auth/password-reset-request",
            "/api/v1/auth/password-reset",
            "/docs",
            "/openapi.json"
        ]
    )


def create_authz_middleware(permission_map: Optional[dict] = None) -> AuthorizationMiddleware:
    """Create authorization middleware."""
    default_permissions = {
        # Admin endpoints
        "/api/v1/admin/*": ["system.admin"],
        
        # User management
        "/api/v1/users": {
            "get": ["users.read"],
            "post": ["users.create"]
        },
        "/api/v1/users/{user_id}": {
            "get": ["users.read"],
            "put": ["users.update"],
            "delete": ["users.delete"]
        },
        
        # Invoice operations
        "/api/v1/invoices": {
            "get": ["invoices.read"],
            "post": ["invoices.create"]
        },
        "/api/v1/invoices/{invoice_id}": {
            "get": ["invoices.read"],
            "put": ["invoices.update"],
            "delete": ["invoices.delete"]
        },
        
        # Export operations
        "/api/v1/exports": {
            "get": ["exports.read"],
            "post": ["exports.create"]
        },
        "/api/v1/exports/{export_id}": {
            "get": ["exports.read"],
            "put": ["exports.update"],
            "delete": ["exports.delete"]
        }
    }
    
    return AuthorizationMiddleware(
        app=None,
        permission_map=permission_map or default_permissions
    )


def create_security_logging_middleware(log_level: str = "INFO") -> SecurityLoggingMiddleware:
    """Create security logging middleware."""
    return SecurityLoggingMiddleware(app=None, log_level=log_level)


def create_rate_limiting_middleware(redis_client=None) -> RateLimitingMiddleware:
    """Create rate limiting middleware."""
    return RateLimitingMiddleware(app=None, redis_client=redis_client)


def create_cors_middleware(allowed_origins: List[str] = None) -> CORSMiddleware:
    """Create CORS middleware."""
    return CORSMiddleware(
        app=None,
        allowed_origins=allowed_origins or [
            "http://localhost:3000",
            "http://localhost:8000",
            "https://ap-intake.example.com"
        ]
    )