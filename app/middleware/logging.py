"""
Logging middleware for AP Intake & Validation system.

Provides comprehensive request/response logging for monitoring and debugging.
"""

import logging
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings


logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Request/response logging middleware.
    
    Logs detailed information about each request and response for monitoring
    and debugging purposes.
    """
    
    def __init__(
        self,
        app,
        log_level: str = "INFO",
        log_body: bool = False,
        log_headers: bool = True,
        exclude_paths: list = None
    ):
        """
        Initialize logging middleware.
        
        Args:
            app: FastAPI application
            log_level: Logging level
            log_body: Whether to log request/response body
            log_headers: Whether to log headers
            exclude_paths: Paths to exclude from logging
        """
        super().__init__(app)
        
        settings = get_settings()
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_body = log_body or settings.DEBUG
        self.log_headers = log_headers
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics",
            "/favicon.ico"
        ]
        
        logger.info("LoggingMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log details.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Skip logging for excluded paths
        if self._should_exclude_path(request.url.path):
            return await call_next(request)
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Record start time
        start_time = time.time()
        
        # Log request
        await self._log_request(request, request_id)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            await self._log_response(request, response, request_id, process_time)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # Log error
            process_time = time.time() - start_time
            await self._log_error(request, e, request_id, process_time)
            raise
    
    def _should_exclude_path(self, path: str) -> bool:
        """
        Check if path should be excluded from logging.
        
        Args:
            path: Request path
            
        Returns:
            True if path should be excluded
        """
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    async def _log_request(self, request: Request, request_id: str) -> None:
        """
        Log incoming request details.
        
        Args:
            request: HTTP request
            request_id: Unique request identifier
        """
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "Unknown")
        
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "timestamp": time.time()
        }
        
        # Add headers if enabled
        if self.log_headers:
            log_data["headers"] = dict(request.headers)
        
        # Add body if enabled and available
        if self.log_body and hasattr(request, '_body'):
            try:
                body = await request.body()
                if body:
                    log_data["body"] = body.decode('utf-8', errors='ignore')
            except Exception:
                pass
        
        # Add user info if available
        if hasattr(request.state, 'user'):
            log_data["user"] = {
                "user_id": getattr(request.state, 'user_id', None),
                "email": getattr(request.state, 'user_email', None),
                "roles": getattr(request.state, 'user_roles', [])
            }
        
        logger.info(f"Request started: {request.method} {request.url.path}", extra=log_data)
    
    async def _log_response(
        self, 
        request: Request, 
        response: Response, 
        request_id: str, 
        process_time: float
    ) -> None:
        """
        Log response details.
        
        Args:
            request: HTTP request
            response: HTTP response
            request_id: Unique request identifier
            process_time: Request processing time
        """
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time": process_time,
            "timestamp": time.time()
        }
        
        # Add response headers if enabled
        if self.log_headers:
            log_data["response_headers"] = dict(response.headers)
        
        # Add response body if enabled and available
        if self.log_body and hasattr(response, 'body'):
            try:
                if hasattr(response, 'body') and response.body:
                    log_data["response_body"] = response.body.decode('utf-8', errors='ignore')
            except Exception:
                pass
        
        # Determine log level based on status code
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO
        
        message = f"Request completed: {request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)"
        
        logger.log(log_level, message, extra=log_data)
    
    async def _log_error(
        self, 
        request: Request, 
        error: Exception, 
        request_id: str, 
        process_time: float
    ) -> None:
        """
        Log error details.
        
        Args:
            request: HTTP request
            error: Exception that occurred
            request_id: Unique request identifier
            process_time: Request processing time
        """
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "process_time": process_time,
            "timestamp": time.time()
        }
        
        # Add user info if available
        if hasattr(request.state, 'user'):
            log_data["user"] = {
                "user_id": getattr(request.state, 'user_id', None),
                "email": getattr(request.state, 'user_email', None),
                "roles": getattr(request.state, 'user_roles', [])
            }
        
        logger.error(
            f"Request failed: {request.method} {request.url.path} - {type(error).__name__}: {str(error)}",
            extra=log_data,
            exc_info=True
        )
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address from request.
        
        Args:
            request: HTTP request
            
        Returns:
            Client IP address
        """
        # Check for forwarded IP
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to client IP
        return request.client.host if request.client else "Unknown"


class StructuredLogger:
    """
    Structured logger for consistent log formatting.
    """
    
    def __init__(self, name: str):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)
    
    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        process_time: float,
        user_id: str = None,
        request_id: str = None,
        **kwargs
    ) -> None:
        """
        Log request with structured data.
        
        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            process_time: Processing time
            user_id: User ID
            request_id: Request ID
            **kwargs: Additional log data
        """
        log_data = {
            "event_type": "request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "process_time": process_time,
            "user_id": user_id,
            "request_id": request_id,
            **kwargs
        }
        
        if status_code >= 400:
            self.logger.warning(f"Request: {method} {path} - {status_code}", extra=log_data)
        else:
            self.logger.info(f"Request: {method} {path} - {status_code}", extra=log_data)
    
    def log_error(
        self,
        error: Exception,
        method: str = None,
        path: str = None,
        user_id: str = None,
        request_id: str = None,
        **kwargs
    ) -> None:
        """
        Log error with structured data.
        
        Args:
            error: Exception that occurred
            method: HTTP method
            path: Request path
            user_id: User ID
            request_id: Request ID
            **kwargs: Additional log data
        """
        log_data = {
            "event_type": "error",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "method": method,
            "path": path,
            "user_id": user_id,
            "request_id": request_id,
            **kwargs
        }
        
        self.logger.error(f"Error: {type(error).__name__}: {str(error)}", extra=log_data, exc_info=True)
    
    def log_business_event(
        self,
        event_type: str,
        description: str,
        user_id: str = None,
        request_id: str = None,
        **kwargs
    ) -> None:
        """
        Log business event with structured data.
        
        Args:
            event_type: Type of business event
            description: Event description
            user_id: User ID
            request_id: Request ID
            **kwargs: Additional log data
        """
        log_data = {
            "event_type": "business",
            "business_event": event_type,
            "description": description,
            "user_id": user_id,
            "request_id": request_id,
            **kwargs
        }
        
        self.logger.info(f"Business Event: {event_type} - {description}", extra=log_data)
    
    def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: str = "medium",
        user_id: str = None,
        ip_address: str = None,
        user_agent: str = None,
        **kwargs
    ) -> None:
        """
        Log security event with structured data.
        
        Args:
            event_type: Type of security event
            description: Event description
            severity: Event severity (low, medium, high, critical)
            user_id: User ID
            ip_address: Client IP address
            user_agent: Client user agent
            **kwargs: Additional log data
        """
        log_data = {
            "event_type": "security",
            "security_event": event_type,
            "description": description,
            "severity": severity,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            **kwargs
        }
        
        if severity in ["high", "critical"]:
            self.logger.error(f"Security Event: {event_type} - {description}", extra=log_data)
        else:
            self.logger.warning(f"Security Event: {event_type} - {description}", extra=log_data)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get structured logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)