"""
Error handling middleware for AP Intake & Validation system.

Provides centralized error handling and consistent error responses.
"""

import logging
import traceback
from typing import Callable, Union
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..api.responses import (
    APIException,
    ValidationError,
    NotFoundError,
    ConflictError,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    ServiceUnavailableError,
    handle_exception,
    ErrorCodes
)


logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Centralized error handling middleware.
    
    Catches and handles all exceptions, providing consistent error responses
    and proper logging.
    """
    
    def __init__(
        self,
        app,
        include_traceback: bool = False,
        log_errors: bool = True
    ):
        """
        Initialize error handling middleware.
        
        Args:
            app: FastAPI application
            include_traceback: Whether to include traceback in error responses
            log_errors: Whether to log errors
        """
        super().__init__(app)
        
        self.include_traceback = include_traceback
        self.log_errors = log_errors
        
        logger.info("ErrorHandlingMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and handle any exceptions.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            return await self._handle_exception(request, e)
    
    async def _handle_exception(self, request: Request, exception: Exception) -> JSONResponse:
        """
        Handle exception and return appropriate response.
        
        Args:
            request: HTTP request
            exception: Exception that occurred
            
        Returns:
            JSON response with error information
        """
        # Log the error
        if self.log_errors:
            await self._log_error(request, exception)
        
        # Handle known exceptions
        if isinstance(exception, APIException):
            return handle_exception(exception)
        
        # Handle HTTP exceptions
        if isinstance(exception, HTTPException):
            return self._handle_http_exception(exception)
        
        # Handle validation errors
        if isinstance(exception, (ValueError, TypeError)):
            return self._handle_validation_error(exception)
        
        # Handle database errors
        if self._is_database_error(exception):
            return self._handle_database_error(exception)
        
        # Handle external service errors
        if self._is_external_service_error(exception):
            return self._handle_external_service_error(exception)
        
        # Handle unknown exceptions
        return self._handle_unknown_error(exception)
    
    async def _log_error(self, request: Request, exception: Exception) -> None:
        """
        Log error with context information.
        
        Args:
            request: HTTP request
            exception: Exception that occurred
        """
        log_data = {
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "url": str(request.url),
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params)
        }
        
        # Add user info if available
        if hasattr(request.state, 'user'):
            log_data["user"] = {
                "user_id": getattr(request.state, 'user_id', None),
                "email": getattr(request.state, 'user_email', None),
                "roles": getattr(request.state, 'user_roles', [])
            }
        
        # Add request ID if available
        if hasattr(request.state, 'request_id'):
            log_data["request_id"] = request.state.request_id
        
        # Log with appropriate level
        if isinstance(exception, (AuthenticationError, AuthorizationError)):
            logger.warning(f"Authentication/Authorization error: {str(exception)}", extra=log_data)
        elif isinstance(exception, (ValidationError, NotFoundError, ConflictError)):
            logger.warning(f"Client error: {str(exception)}", extra=log_data)
        else:
            logger.error(f"Unhandled exception: {str(exception)}", extra=log_data, exc_info=True)
    
    def _handle_http_exception(self, exception: HTTPException) -> JSONResponse:
        """
        Handle FastAPI HTTPException.
        
        Args:
            exception: HTTPException
            
        Returns:
            JSON response
        """
        error_response = {
            "success": False,
            "message": exception.detail,
            "error_code": self._get_error_code_from_status(exception.status_code),
            "status_code": exception.status_code
        }
        
        return JSONResponse(
            content=error_response,
            status_code=exception.status_code
        )
    
    def _handle_validation_error(self, exception: Exception) -> JSONResponse:
        """
        Handle validation errors.
        
        Args:
            exception: Validation exception
            
        Returns:
            JSON response
        """
        error_response = {
            "success": False,
            "message": "Validation failed",
            "error_code": ErrorCodes.VALIDATION_FAILED,
            "errors": [str(exception)]
        }
        
        if self.include_traceback:
            error_response["traceback"] = traceback.format_exc()
        
        return JSONResponse(
            content=error_response,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    
    def _handle_database_error(self, exception: Exception) -> JSONResponse:
        """
        Handle database errors.
        
        Args:
            exception: Database exception
            
        Returns:
            JSON response
        """
        error_response = {
            "success": False,
            "message": "Database operation failed",
            "error_code": ErrorCodes.DATABASE_ERROR,
            "errors": ["A database error occurred while processing your request"]
        }
        
        if self.include_traceback:
            error_response["traceback"] = traceback.format_exc()
        
        return JSONResponse(
            content=error_response,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    def _handle_external_service_error(self, exception: Exception) -> JSONResponse:
        """
        Handle external service errors.
        
        Args:
            exception: External service exception
            
        Returns:
            JSON response
        """
        error_response = {
            "success": False,
            "message": "External service unavailable",
            "error_code": ErrorCodes.EXTERNAL_SERVICE_ERROR,
            "errors": ["An external service is temporarily unavailable"]
        }
        
        if self.include_traceback:
            error_response["traceback"] = traceback.format_exc()
        
        return JSONResponse(
            content=error_response,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    def _handle_unknown_error(self, exception: Exception) -> JSONResponse:
        """
        Handle unknown exceptions.
        
        Args:
            exception: Unknown exception
            
        Returns:
            JSON response
        """
        error_response = {
            "success": False,
            "message": "Internal server error",
            "error_code": ErrorCodes.INTERNAL_ERROR,
            "errors": ["An unexpected error occurred while processing your request"]
        }
        
        if self.include_traceback:
            error_response["traceback"] = traceback.format_exc()
        
        return JSONResponse(
            content=error_response,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    def _get_error_code_from_status(self, status_code: int) -> str:
        """
        Get error code from HTTP status code.
        
        Args:
            status_code: HTTP status code
            
        Returns:
            Error code string
        """
        status_to_error = {
            400: ErrorCodes.INVALID_INPUT,
            401: ErrorCodes.UNAUTHORIZED,
            403: ErrorCodes.FORBIDDEN,
            404: ErrorCodes.NOT_FOUND,
            409: ErrorCodes.CONFLICT,
            422: ErrorCodes.VALIDATION_FAILED,
            429: ErrorCodes.RATE_LIMIT_EXCEEDED,
            500: ErrorCodes.INTERNAL_ERROR,
            503: ErrorCodes.SERVICE_UNAVAILABLE
        }
        
        return status_to_error.get(status_code, ErrorCodes.INTERNAL_ERROR)
    
    def _is_database_error(self, exception: Exception) -> bool:
        """
        Check if exception is a database error.
        
        Args:
            exception: Exception to check
            
        Returns:
            True if database error
        """
        # Check for common database error patterns
        db_error_patterns = [
            'sqlalchemy', 'psycopg2', 'mysql', 'sqlite',
            'database', 'connection', 'timeout'
        ]
        
        exception_str = str(type(exception).__name__).lower() + str(exception).lower()
        return any(pattern in exception_str for pattern in db_error_patterns)
    
    def _is_external_service_error(self, exception: Exception) -> bool:
        """
        Check if exception is an external service error.
        
        Args:
            exception: Exception to check
            
        Returns:
            True if external service error
        """
        # Check for common external service error patterns
        service_error_patterns = [
            'requests', 'httpx', 'aiohttp',
            'connection', 'timeout', 'network',
            'api', 'service'
        ]
        
        exception_str = str(type(exception).__name__).lower() + str(exception).lower()
        return any(pattern in exception_str for pattern in service_error_patterns)


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    """
    Circuit breaker middleware for external service calls.
    
    Prevents cascading failures by detecting when external services
    are failing and temporarily disabling them.
    """
    
    def __init__(
        self,
        app,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker middleware.
        
        Args:
            app: FastAPI application
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to count as failure
        """
        super().__init__(app)
        
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
        logger.info("CircuitBreakerMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with circuit breaker logic.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Check if circuit is open
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                return self._create_circuit_open_response()
        
        try:
            response = await call_next(request)
            
            # Reset on success if in HALF_OPEN state
            if self.state == "HALF_OPEN":
                self._reset()
                logger.info("Circuit breaker reset to CLOSED")
            
            return response
            
        except self.expected_exception as e:
            self._record_failure()
            
            if self.state == "OPEN":
                return self._create_circuit_open_response()
            
            raise
    
    def _should_attempt_reset(self) -> bool:
        """
        Check if circuit breaker should attempt reset.
        
        Returns:
            True if should attempt reset
        """
        import time
        return (
            self.last_failure_time and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _record_failure(self) -> None:
        """
        Record a failure and update circuit state.
        """
        import time
        
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def _reset(self) -> None:
        """
        Reset circuit breaker to closed state.
        """
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
    
    def _create_circuit_open_response(self) -> JSONResponse:
        """
        Create response when circuit is open.
        
        Returns:
            JSON response
        """
        error_response = {
            "success": False,
            "message": "Service temporarily unavailable",
            "error_code": ErrorCodes.SERVICE_UNAVAILABLE,
            "errors": ["Circuit breaker is open - service temporarily unavailable"]
        }
        
        return JSONResponse(
            content=error_response,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


def create_error_handler(
    include_traceback: bool = False,
    log_errors: bool = True
) -> ErrorHandlingMiddleware:
    """
    Create error handling middleware instance.
    
    Args:
        include_traceback: Whether to include traceback in responses
        log_errors: Whether to log errors
        
    Returns:
        ErrorHandlingMiddleware instance
    """
    return ErrorHandlingMiddleware(
        include_traceback=include_traceback,
        log_errors=log_errors
    )


def create_circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception
) -> CircuitBreakerMiddleware:
    """
    Create circuit breaker middleware instance.
    
    Args:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before attempting recovery
        expected_exception: Exception type to count as failure
        
    Returns:
        CircuitBreakerMiddleware instance
    """
    return CircuitBreakerMiddleware(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception
    )