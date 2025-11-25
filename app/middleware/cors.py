"""
CORS middleware for AP Intake & Validation system.

Provides Cross-Origin Resource Sharing configuration.
"""

import logging
from typing import List, Optional, Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware as StarletteCORSMiddleware


logger = logging.getLogger(__name__)


class CORSMiddleware(BaseHTTPMiddleware):
    """
    Custom CORS middleware with enhanced configuration options.
    
    Provides fine-grained control over CORS policies including
    dynamic origins and environment-specific settings.
    """
    
    def __init__(
        self,
        app,
        allow_origins: List[str] = None,
        allow_methods: List[str] = None,
        allow_headers: List[str] = None,
        allow_credentials: bool = True,
        expose_headers: List[str] = None,
        max_age: int = 600,
        vary_header: bool = True
    ):
        """
        Initialize CORS middleware.
        
        Args:
            app: FastAPI application
            allow_origins: List of allowed origins
            allow_methods: List of allowed HTTP methods
            allow_headers: List of allowed headers
            allow_credentials: Whether to allow credentials
            expose_headers: List of headers to expose
            max_age: Maximum age for preflight requests
            vary_header: Whether to add Vary header
        """
        super().__init__(app)
        
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age
        self.vary_header = vary_header
        
        logger.info("CORSMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add CORS headers.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response with CORS headers
        """
        # Get origin from request
        origin = request.headers.get("origin")
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            return await self._handle_preflight(request, origin)
        
        # Process request
        response = await call_next(request)
        
        # Add CORS headers to actual response
        self._add_cors_headers(response, origin)
        
        return response
    
    async def _handle_preflight(self, request: Request, origin: str) -> Response:
        """
        Handle CORS preflight requests.
        
        Args:
            request: HTTP request
            origin: Request origin
            
        Returns:
            CORS preflight response
        """
        response = Response()
        
        # Check if origin is allowed
        if self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            
            if self.allow_credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
            
            response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
            response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
            response.headers["Access-Control-Max-Age"] = str(self.max_age)
            
            if self.expose_headers:
                response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        
        if self.vary_header:
            response.headers["Vary"] = "Origin"
        
        return response
    
    def _add_cors_headers(self, response: Response, origin: str) -> None:
        """
        Add CORS headers to response.
        
        Args:
            response: HTTP response
            origin: Request origin
        """
        if self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            
            if self.allow_credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
            
            if self.expose_headers:
                response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        
        if self.vary_header:
            response.headers["Vary"] = "Origin"
    
    def _is_origin_allowed(self, origin: str) -> bool:
        """
        Check if origin is allowed.
        
        Args:
            origin: Request origin
            
        Returns:
            True if origin is allowed
        """
        if not origin:
            return False
        
        if "*" in self.allow_origins:
            return True
        
        return origin in self.allow_origins


class EnvironmentAwareCORSMiddleware(CORSMiddleware):
    """
    Environment-aware CORS middleware.
    
    Automatically configures CORS based on environment.
    """
    
    def __init__(self, app, environment: str = "development"):
        """
        Initialize environment-aware CORS middleware.
        
        Args:
            app: FastAPI application
            environment: Current environment (development, staging, production)
        """
        self.environment = environment
        
        # Get CORS configuration based on environment
        cors_config = self._get_cors_config(environment)
        
        super().__init__(app, **cors_config)
        
        logger.info(f"EnvironmentAwareCORSMiddleware initialized for {environment}")
    
    def _get_cors_config(self, environment: str) -> dict:
        """
        Get CORS configuration based on environment.
        
        Args:
            environment: Environment name
            
        Returns:
            CORS configuration dictionary
        """
        configs = {
            "development": {
                "allow_origins": ["*"],
                "allow_methods": ["*"],
                "allow_headers": ["*"],
                "allow_credentials": True,
                "max_age": 600
            },
            "staging": {
                "allow_origins": [
                    "http://localhost:3000",
                    "http://localhost:8080",
                    "https://staging.apintake.com"
                ],
                "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["*"],
                "allow_credentials": True,
                "max_age": 600
            },
            "production": {
                "allow_origins": [
                    "https://app.apintake.com",
                    "https://dashboard.apintake.com"
                ],
                "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": [
                    "Content-Type",
                    "Authorization",
                    "X-Requested-With",
                    "X-Request-ID"
                ],
                "allow_credentials": True,
                "max_age": 86400
            }
        }
        
        return configs.get(environment, configs["development"])


def create_cors_middleware(
    app,
    environment: str = "development",
    **kwargs
) -> CORSMiddleware:
    """
    Create CORS middleware instance.
    
    Args:
        app: FastAPI application
        environment: Environment name
        **kwargs: Additional CORS configuration
        
    Returns:
        CORSMiddleware instance
    """
    if kwargs:
        # Use custom configuration
        return CORSMiddleware(app, **kwargs)
    else:
        # Use environment-aware configuration
        return EnvironmentAwareCORSMiddleware(app, environment)


def create_starlette_cors_middleware(
    app,
    allow_origins: List[str] = None,
    allow_methods: List[str] = None,
    allow_headers: List[str] = None,
    allow_credentials: bool = True,
    expose_headers: List[str] = None,
    max_age: int = 600
) -> StarletteCORSMiddleware:
    """
    Create Starlette CORS middleware instance.
    
    Args:
        app: FastAPI application
        allow_origins: List of allowed origins
        allow_methods: List of allowed HTTP methods
        allow_headers: List of allowed headers
        allow_credentials: Whether to allow credentials
        expose_headers: List of headers to expose
        max_age: Maximum age for preflight requests
        
    Returns:
        StarletteCORSMiddleware instance
    """
    return StarletteCORSMiddleware(
        app,
        allow_origins=allow_origins or ["*"],
        allow_methods=allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=allow_headers or ["*"],
        allow_credentials=allow_credentials,
        expose_headers=expose_headers or [],
        max_age=max_age
    )