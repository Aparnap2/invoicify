"""
API Standards and Common Patterns for AP Intake System.

This module defines standardized response patterns, error handling,
authentication dependencies, and common utilities for all API endpoints.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1.deps import get_async_session, get_current_active_user
from app.models.user import User

logger = logging.getLogger(__name__)

# Generic type for response data
T = TypeVar('T')


class StandardResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""
    success: bool = Field(..., description="Whether the operation was successful")
    data: Optional[T] = Field(None, description="Response data payload")
    message: str = Field(..., description="Human-readable message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response wrapper."""
    success: bool = Field(True, description="Whether the operation was successful")
    data: List[T] = Field(..., description="List of items")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")
    message: str = Field(..., description="Human-readable message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = Field(False, description="Always false for errors")
    error: Dict[str, Any] = Field(..., description="Error details")
    message: str = Field(..., description="Human-readable error message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


class APIStandardizer:
    """Utility class for standardizing API responses and error handling."""
    
    @staticmethod
    def success_response(
        data: Optional[T] = None,
        message: str = "Operation successful",
        status_code: int = 200,
        request_id: Optional[str] = None
    ) -> JSONResponse:
        """Create a standardized success response."""
        response = StandardResponse[T](
            success=True,
            data=data,
            message=message,
            request_id=request_id
        )
        return JSONResponse(
            status_code=status_code,
            content=response.model_dump(mode='json')
        )
    
    @staticmethod
    def paginated_response(
        data: List[T],
        total: int,
        limit: int,
        offset: int,
        message: str = "Data retrieved successfully",
        request_id: Optional[str] = None
    ) -> JSONResponse:
        """Create a standardized paginated response."""
        pagination = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(data) < total,
            "returned": len(data)
        }
        
        response = PaginatedResponse[T](
            data=data,
            pagination=pagination,
            message=message,
            request_id=request_id
        )
        return JSONResponse(
            status_code=200,
            content=response.model_dump(mode='json')
        )
    
    @staticmethod
    def error_response(
        error_message: str,
        status_code: int = 500,
        error_details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> JSONResponse:
        """Create a standardized error response."""
        error_data = {
            "code": status_code,
            "message": error_message,
            "details": error_details or {}
        }
        
        response = ErrorResponse(
            error=error_data,
            message=error_message,
            request_id=request_id
        )
        return JSONResponse(
            status_code=status_code,
            content=response.model_dump(mode='json')
        )
    
    @staticmethod
    def handle_exception(
        e: Exception,
        operation: str = "operation",
        request_id: Optional[str] = None
    ) -> JSONResponse:
        """Handle exceptions in a standardized way."""
        logger.error(f"Error during {operation}: {e}", exc_info=True)
        
        if isinstance(e, HTTPException):
            return APIStandardizer.error_response(
                error_message=str(e.detail),
                status_code=e.status_code,
                request_id=request_id
            )
        else:
            return APIStandardizer.error_response(
                error_message=f"Internal server error during {operation}",
                status_code=500,
                error_details={"exception_type": type(e).__name__},
                request_id=request_id
            )


# Standard dependencies
async def get_db_session() -> AsyncSession:
    """Get database session - standardized dependency."""
    return await get_async_session()


async def get_authenticated_user() -> User:
    """Get authenticated user - standardized dependency."""
    return await get_current_active_user()


class EndpointValidator:
    """Common validation utilities for endpoints."""
    
    @staticmethod
    def validate_uuid(uuid_string: str, field_name: str = "ID") -> UUID:
        """Validate UUID string format."""
        try:
            return UUID(uuid_string)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {field_name} format: {uuid_string}"
            )
    
    @staticmethod
    def validate_date_range(
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        max_days: int = 365
    ) -> tuple[datetime, datetime]:
        """Validate date range parameters."""
        now = datetime.utcnow()
        
        if start_date and end_date:
            if start_date > end_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Start date cannot be after end date"
                )
            
            if (end_date - start_date).days > max_days:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Date range cannot exceed {max_days} days"
                )
        
        return start_date or (now - timedelta(days=30)), end_date or now
    
    @staticmethod
    def validate_pagination(
        limit: int,
        offset: int,
        max_limit: int = 1000
    ) -> tuple[int, int]:
        """Validate pagination parameters."""
        if limit < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be at least 1"
            )
        
        if limit > max_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Limit cannot exceed {max_limit}"
            )
        
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Offset cannot be negative"
            )
        
        return limit, offset


class DatabaseHelper:
    """Common database operations for endpoints."""
    
    @staticmethod
    async def get_by_id_or_404(
        session: AsyncSession,
        model_class: Any,
        entity_id: str,
        field_name: str = "id"
    ) -> Any:
        """Get entity by ID or raise 404."""
        from sqlalchemy import select
        
        try:
            uuid_id = UUID(entity_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {field_name} format"
            )
        
        query = select(model_class).where(getattr(model_class, field_name) == uuid_id)
        result = await session.execute(query)
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{model_class.__name__} not found"
            )
        
        return entity
    
    @staticmethod
    async def get_total_count(
        session: AsyncSession,
        model_class: Any,
        filters: Optional[List[Any]] = None
    ) -> int:
        """Get total count of entities with optional filters."""
        from sqlalchemy import select, func
        
        query = select(func.count(model_class.id))
        if filters:
            query = query.where(*filters)
        
        result = await session.execute(query)
        return result.scalar() or 0


# Common response schemas
class HealthResponse(BaseModel):
    """Standard health check response."""
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    components: Dict[str, Any] = Field(default_factory=dict, description="Component health")
    version: Optional[str] = Field(None, description="API version")


class TaskResponse(BaseModel):
    """Standard background task response."""
    task_id: str = Field(..., description="Background task ID")
    status: str = Field(..., description="Task status")
    message: str = Field(..., description="Task description")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Task start time")


# Common error messages
class ErrorMessages:
    """Standard error messages."""
    NOT_FOUND = "Resource not found"
    INVALID_FORMAT = "Invalid data format"
    PERMISSION_DENIED = "Permission denied"
    VALIDATION_ERROR = "Validation failed"
    INTERNAL_ERROR = "Internal server error"
    DUPLICATE_RESOURCE = "Resource already exists"
    RATE_LIMITED = "Rate limit exceeded"
    SERVICE_UNAVAILABLE = "Service temporarily unavailable"


# HTTP status code helpers
class StatusCodes:
    """Common HTTP status codes."""
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503