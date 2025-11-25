"""
Standard API response patterns for AP Intake & Validation system.

Provides consistent response formats, error handling, and status codes
following REST API best practices.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class APIResponse(BaseModel):
    """
    Standard API response structure.
    """
    success: bool = Field(description="Whether the request was successful")
    message: str = Field(description="Human-readable message")
    data: Optional[Any] = Field(default=None, description="Response data")
    errors: Optional[List[str]] = Field(default=None, description="Error messages")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Response metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class PaginatedResponse(BaseModel):
    """
    Paginated response structure.
    """
    success: bool = Field(description="Whether the request was successful")
    message: str = Field(description="Human-readable message")
    data: List[Any] = Field(description="Response data items")
    pagination: Dict[str, Any] = Field(description="Pagination information")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Response metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class ErrorResponse(BaseModel):
    """
    Error response structure.
    """
    success: bool = Field(default=False, description="Always false for errors")
    message: str = Field(description="Error message")
    error_code: str = Field(description="Machine-readable error code")
    errors: Optional[List[str]] = Field(default=None, description="Detailed error messages")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


class ResponseBuilder:
    """
    Builder for creating consistent API responses.
    """
    
    @staticmethod
    def success(
        message: str = "Operation successful",
        data: Any = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> APIResponse:
        """
        Create a successful response.
        
        Args:
            message: Success message
            data: Response data
            metadata: Additional metadata
            
        Returns:
            APIResponse object
        """
        return APIResponse(
            success=True,
            message=message,
            data=data,
            metadata=metadata
        )
    
    @staticmethod
    def error(
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        errors: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> ErrorResponse:
        """
        Create an error response.
        
        Args:
            message: Error message
            error_code: Machine-readable error code
            errors: Detailed error messages
            details: Additional error details
            
        Returns:
            ErrorResponse object
        """
        return ErrorResponse(
            message=message,
            error_code=error_code,
            errors=errors,
            details=details
        )
    
    @staticmethod
    def paginated(
        data: List[Any],
        page: int,
        page_size: int,
        total: int,
        message: str = "Data retrieved successfully",
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaginatedResponse:
        """
        Create a paginated response.
        
        Args:
            data: List of data items
            page: Current page number
            page_size: Number of items per page
            total: Total number of items
            message: Success message
            metadata: Additional metadata
            
        Returns:
            PaginatedResponse object
        """
        total_pages = (total + page_size - 1) // page_size
        
        pagination = {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
            'next_page': page + 1 if page < total_pages else None,
            'prev_page': page - 1 if page > 1 else None
        }
        
        return PaginatedResponse(
            success=True,
            message=message,
            data=data,
            pagination=pagination,
            metadata=metadata
        )


class APIException(HTTPException):
    """
    Custom API exception with structured error information.
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "API_ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        errors: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize API exception.
        
        Args:
            message: Error message
            error_code: Machine-readable error code
            status_code: HTTP status code
            errors: Detailed error messages
            details: Additional error details
        """
        self.error_code = error_code
        self.errors = errors
        self.details = details
        
        super().__init__(
            status_code=status_code,
            detail=message
        )


class ValidationError(APIException):
    """
    Validation error exception.
    """
    
    def __init__(
        self,
        message: str = "Validation failed",
        errors: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            errors=errors,
            details=details
        )


class NotFoundError(APIException):
    """
    Resource not found error exception.
    """
    
    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: str = "resource",
        resource_id: Optional[str] = None
    ):
        details = {'resource_type': resource_type}
        if resource_id:
            details['resource_id'] = resource_id
            
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class ConflictError(APIException):
    """
    Resource conflict error exception.
    """
    
    def __init__(
        self,
        message: str = "Resource conflict",
        resource_type: str = "resource",
        conflict_details: Optional[Dict[str, Any]] = None
    ):
        details = {'resource_type': resource_type}
        if conflict_details:
            details.update(conflict_details)
            
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class AuthenticationError(APIException):
    """
    Authentication error exception.
    """
    
    def __init__(
        self,
        message: str = "Authentication failed",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class AuthorizationError(APIException):
    """
    Authorization error exception.
    """
    
    def __init__(
        self,
        message: str = "Access denied",
        required_permission: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = {}
        if required_permission:
            error_details['required_permission'] = required_permission
        if details:
            error_details.update(details)
            
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN,
            details=error_details
        )


class RateLimitError(APIException):
    """
    Rate limit exceeded error exception.
    """
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        window: Optional[int] = None
    ):
        details = {}
        if retry_after:
            details['retry_after'] = retry_after
        if limit:
            details['limit'] = limit
        if window:
            details['window'] = window
            
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details
        )


class ServiceUnavailableError(APIException):
    """
    Service unavailable error exception.
    """
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        service_name: Optional[str] = None,
        retry_after: Optional[int] = None
    ):
        details = {}
        if service_name:
            details['service_name'] = service_name
        if retry_after:
            details['retry_after'] = retry_after
            
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details
        )


def create_response(
    response_model: Union[APIResponse, ErrorResponse, PaginatedResponse],
    status_code: int = status.HTTP_200_OK
) -> JSONResponse:
    """
    Create a JSON response with proper status code.
    
    Args:
        response_model: Response model instance
        status_code: HTTP status code
        
    Returns:
        JSONResponse object
    """
    return JSONResponse(
        content=response_model.dict(),
        status_code=status_code
    )


def handle_exception(exc: Exception) -> JSONResponse:
    """
    Handle exceptions and return appropriate error response.
    
    Args:
        exc: Exception to handle
        
    Returns:
        JSONResponse with error information
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    if isinstance(exc, APIException):
        error_response = ResponseBuilder.error(
            message=exc.detail,
            error_code=exc.error_code,
            errors=exc.errors,
            details=exc.details
        )
        return create_response(error_response, exc.status_code)
    
    # Handle other exceptions
    error_response = ResponseBuilder.error(
        message="Internal server error",
        error_code="INTERNAL_ERROR",
        details={'exception_type': type(exc).__name__}
    )
    
    return create_response(
        error_response,
        status.HTTP_500_INTERNAL_SERVER_ERROR
    )


# Common error codes and messages
class ErrorCodes:
    """Standard error codes."""
    
    # Validation errors
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    
    # Authentication/Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    
    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    
    # Business logic errors
    INVALID_STATE = "INVALID_STATE"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    
    # System errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"


# Success messages
class SuccessMessages:
    """Standard success messages."""
    
    CREATED = "Resource created successfully"
    UPDATED = "Resource updated successfully"
    DELETED = "Resource deleted successfully"
    RETRIEVED = "Data retrieved successfully"
    PROCESSED = "Request processed successfully"
    UPLOADED = "File uploaded successfully"
    SENT = "Message sent successfully"
    COMPLETED = "Operation completed successfully"


# Response decorators
def api_response(success_message: str = SuccessMessages.RETRIEVED):
    """
    Decorator for standardizing API responses.
    
    Args:
        success_message: Default success message
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                
                if isinstance(result, tuple):
                    data, message = result
                else:
                    data = result
                    message = success_message
                
                response = ResponseBuilder.success(
                    message=message,
                    data=data
                )
                
                return create_response(response)
                
            except Exception as e:
                return handle_exception(e)
        
        return wrapper
    return decorator


def paginated_response(default_page_size: int = 20):
    """
    Decorator for paginated responses.
    
    Args:
        default_page_size: Default number of items per page
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                # Extract pagination parameters
                page = kwargs.pop('page', 1)
                page_size = kwargs.pop('page_size', default_page_size)
                
                # Call the function
                result = await func(*args, **kwargs)
                
                if isinstance(result, tuple):
                    data, total = result
                else:
                    data = result.get('data', [])
                    total = result.get('total', len(data))
                
                response = ResponseBuilder.paginated(
                    data=data,
                    page=page,
                    page_size=page_size,
                    total=total
                )
                
                return create_response(response)
                
            except Exception as e:
                return handle_exception(e)
        
        return wrapper
    return decorator