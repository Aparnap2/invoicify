"""
Security headers middleware for AP Intake & Validation system.

Adds security-related HTTP headers to prevent common web vulnerabilities.
"""

import logging
from typing import Callable, Dict, List, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Security headers middleware.
    
    Adds various security headers to HTTP responses to prevent
    common web vulnerabilities like XSS, clickjacking, etc.
    """
    
    def __init__(
        self,
        app,
        enable_hsts: bool = True,
        enable_csp: bool = True,
        enable_xss_protection: bool = True,
        enable_content_type_options: bool = True,
        enable_frame_options: bool = True,
        enable_referrer_policy: bool = True,
        custom_headers: Optional[Dict[str, str]] = None,
        exclude_paths: Optional[List[str]] = None
    ):
        """
        Initialize security headers middleware.
        
        Args:
            app: FastAPI application
            enable_hsts: Whether to enable HSTS header
            enable_csp: Whether to enable CSP header
            enable_xss_protection: Whether to enable XSS protection header
            enable_content_type_options: Whether to enable content type options header
            enable_frame_options: Whether to enable frame options header
            enable_referrer_policy: Whether to enable referrer policy header
            custom_headers: Custom headers to add
            exclude_paths: Paths to exclude from security headers
        """
        super().__init__(app)
        
        self.enable_hsts = enable_hsts
        self.enable_csp = enable_csp
        self.enable_xss_protection = enable_xss_protection
        self.enable_content_type_options = enable_content_type_options
        self.enable_frame_options = enable_frame_options
        self.enable_referrer_policy = enable_referrer_policy
        self.custom_headers = custom_headers or {}
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics"
        ]
        
        logger.info("SecurityHeadersMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add security headers.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response with security headers
        """
        # Process request
        response = await call_next(request)
        
        # Skip security headers for excluded paths
        if self._should_exclude_path(request.url.path):
            return response
        
        # Add security headers
        self._add_security_headers(response)
        
        return response
    
    def _should_exclude_path(self, path: str) -> bool:
        """
        Check if path should be excluded from security headers.
        
        Args:
            path: Request path
            
        Returns:
            True if path should be excluded
        """
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    def _add_security_headers(self, response: Response) -> None:
        """
        Add security headers to response.
        
        Args:
            response: HTTP response
        """
        # HTTP Strict Transport Security (HSTS)
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        # Content Security Policy (CSP)
        if self.enable_csp:
            response.headers["Content-Security-Policy"] = self._get_csp_header()
        
        # XSS Protection
        if self.enable_xss_protection:
            response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Content Type Options
        if self.enable_content_type_options:
            response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Frame Options
        if self.enable_frame_options:
            response.headers["X-Frame-Options"] = "DENY"
        
        # Referrer Policy
        if self.enable_referrer_policy:
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Additional security headers
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["X-Download-Options"] = "noopen"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        
        # Remove server information
        response.headers["Server"] = "AP-Intake"
        
        # Add custom headers
        for header_name, header_value in self.custom_headers.items():
            response.headers[header_name] = header_value
    
    def _get_csp_header(self) -> str:
        """
        Get Content Security Policy header value.
        
        Returns:
            CSP header value
        """
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "upgrade-insecure-requests"
        ]
        
        return "; ".join(csp_directives)


class EnvironmentAwareSecurityMiddleware(SecurityHeadersMiddleware):
    """
    Environment-aware security headers middleware.
    
    Automatically configures security headers based on environment.
    """
    
    def __init__(self, app, environment: str = "development"):
        """
        Initialize environment-aware security middleware.
        
        Args:
            app: FastAPI application
            environment: Current environment (development, staging, production)
        """
        self.environment = environment
        
        # Get security configuration based on environment
        security_config = self._get_security_config(environment)
        
        super().__init__(app, **security_config)
        
        logger.info(f"EnvironmentAwareSecurityMiddleware initialized for {environment}")
    
    def _get_security_config(self, environment: str) -> dict:
        """
        Get security configuration based on environment.
        
        Args:
            environment: Environment name
            
        Returns:
            Security configuration dictionary
        """
        configs = {
            "development": {
                "enable_hsts": False,  # Disabled for HTTP in development
                "enable_csp": True,
                "enable_xss_protection": True,
                "enable_content_type_options": True,
                "enable_frame_options": True,
                "enable_referrer_policy": True,
                "custom_headers": {
                    "X-Environment": "development"
                }
            },
            "staging": {
                "enable_hsts": True,
                "enable_csp": True,
                "enable_xss_protection": True,
                "enable_content_type_options": True,
                "enable_frame_options": True,
                "enable_referrer_policy": True,
                "custom_headers": {
                    "X-Environment": "staging"
                }
            },
            "production": {
                "enable_hsts": True,
                "enable_csp": True,
                "enable_xss_protection": True,
                "enable_content_type_options": True,
                "enable_frame_options": True,
                "enable_referrer_policy": True,
                "custom_headers": {
                    "X-Environment": "production",
                    "X-Content-Security-Policy-Report-Only": "false"
                }
            }
        }
        
        return configs.get(environment, configs["development"])
    
    def _get_csp_header(self) -> str:
        """
        Get Content Security Policy header value based on environment.
        
        Returns:
            CSP header value
        """
        if self.environment == "development":
            # More permissive CSP for development
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:*",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https: http:",
                "font-src 'self' data:",
                "connect-src 'self' ws: wss:",
                "frame-ancestors 'self'",
                "base-uri 'self'",
                "form-action 'self'"
            ]
        elif self.environment == "staging":
            # Moderately restrictive CSP for staging
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https:",
                "font-src 'self' data:",
                "connect-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'"
            ]
        else:
            # Strict CSP for production
            csp_directives = [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self'",
                "img-src 'self' data: https:",
                "font-src 'self'",
                "connect-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "upgrade-insecure-requests"
            ]
        
        return "; ".join(csp_directives)


class CustomSecurityMiddleware(SecurityHeadersMiddleware):
    """
    Custom security middleware with configurable CSP.
    
    Allows fine-tuned control over Content Security Policy.
    """
    
    def __init__(
        self,
        app,
        csp_directives: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialize custom security middleware.
        
        Args:
            app: FastAPI application
            csp_directives: Custom CSP directives
            **kwargs: Additional security configuration
        """
        self.csp_directives = csp_directives
        
        super().__init__(app, **kwargs)
        
        logger.info("CustomSecurityMiddleware initialized")
    
    def _get_csp_header(self) -> str:
        """
        Get custom Content Security Policy header value.
        
        Returns:
            CSP header value
        """
        if self.csp_directives:
            return "; ".join(self.csp_directives)
        
        return super()._get_csp_header()


def create_security_middleware(
    app,
    environment: str = "development",
    csp_directives: Optional[List[str]] = None,
    **kwargs
) -> SecurityHeadersMiddleware:
    """
    Create security middleware instance.
    
    Args:
        app: FastAPI application
        environment: Environment name
        csp_directives: Custom CSP directives
        **kwargs: Additional security configuration
        
    Returns:
        SecurityHeadersMiddleware instance
    """
    if csp_directives:
        # Use custom CSP
        return CustomSecurityMiddleware(
            app,
            csp_directives=csp_directives,
            **kwargs
        )
    else:
        # Use environment-aware configuration
        return EnvironmentAwareSecurityMiddleware(app, environment)


def get_default_security_headers() -> Dict[str, str]:
    """
    Get default security headers.
    
    Returns:
        Dictionary of default security headers
    """
    return {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "upgrade-insecure-requests"
        ),
        "X-XSS-Protection": "1; mode=block",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Permitted-Cross-Domain-Policies": "none",
        "X-Download-Options": "noopen",
        "X-Robots-Tag": "noindex, nofollow",
        "Server": "AP-Intake"
    }