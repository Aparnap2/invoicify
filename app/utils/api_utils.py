"""
API utilities for consistent API development and response handling.
"""

from typing import Any, Dict, List, Optional, Union, Type
from datetime import datetime
from fastapi import HTTPException, status, Query, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import uuid

from app.api.api_v1.standards import APIStandardizer, StatusCodes


class APIUtils:
    """Utility class for API operations and response handling."""
    
    @staticmethod
    def create_success_response(data: Any = None, message: str = "Operation successful", 
                              status_code: int = StatusCodes.OK, 
                              metadata: Optional[Dict[str, Any]] = None) -> JSONResponse:
        """Create standardized success response."""
        return APIStandardizer.success_response(
            data=data,
            message=message,
            status_code=status_code,
            metadata=metadata
        )
    
    @staticmethod
    def create_error_response(message: str, error_code: str = "UNKNOWN_ERROR",
                            details: Optional[Dict[str, Any]] = None,
                            status_code: int = StatusCodes.INTERNAL_SERVER_ERROR) -> JSONResponse:
        """Create standardized error response."""
        return APIStandardizer.error_response(
            message=message,
            error_code=error_code,
            details=details,
            status_code=status_code
        )
    
    @staticmethod
    def create_paginated_response(items: List[Any], total: int, page: int = 1, 
                               page_size: int = 20, message: str = "Data retrieved successfully") -> JSONResponse:
        """Create paginated response."""
        return APIStandardizer.paginated_response(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            message=message
        )
    
    @staticmethod
    def handle_validation_error(error: ValidationError) -> JSONResponse:
        """Handle Pydantic validation errors."""
        error_details = {}
        for field_error in error.errors():
            field = '.'.join(str(x) for x in field_error['loc'])
            error_details[field] = field_error['msg']
        
        return APIUtils.create_error_response(
            message="Validation failed",
            error_code="VALIDATION_ERROR",
            details=error_details,
            status_code=StatusCodes.UNPROCESSABLE_ENTITY
        )
    
    @staticmethod
    def handle_not_found_error(resource_name: str = "Resource") -> JSONResponse:
        """Handle not found errors."""
        return APIUtils.create_error_response(
            message=f"{resource_name} not found",
            error_code="NOT_FOUND",
            status_code=StatusCodes.NOT_FOUND
        )
    
    @staticmethod
    def handle_unauthorized_error(message: str = "Unauthorized access") -> JSONResponse:
        """Handle unauthorized errors."""
        return APIUtils.create_error_response(
            message=message,
            error_code="UNAUTHORIZED",
            status_code=StatusCodes.UNAUTHORIZED
        )
    
    @staticmethod
    def handle_forbidden_error(message: str = "Access forbidden") -> JSONResponse:
        """Handle forbidden errors."""
        return APIUtils.create_error_response(
            message=message,
            error_code="FORBIDDEN",
            status_code=StatusCodes.FORBIDDEN
        )
    
    @staticmethod
    def handle_conflict_error(message: str = "Resource conflict") -> JSONResponse:
        """Handle conflict errors."""
        return APIUtils.create_error_response(
            message=message,
            error_code="CONFLICT",
            status_code=StatusCodes.CONFLICT
        )
    
    @staticmethod
    def validate_uuid_path_param(uuid_string: str, field_name: str = "ID") -> uuid.UUID:
        """Validate UUID path parameter."""
        try:
            return uuid.UUID(uuid_string)
        except ValueError:
            raise HTTPException(
                status_code=StatusCodes.BAD_REQUEST,
                detail=f"Invalid {field_name} format"
            )
    
    @staticmethod
    def create_pagination_params(page: int = Query(1, ge=1, description="Page number"),
                               page_size: int = Query(20, ge=1, le=100, description="Items per page")) -> Dict[str, int]:
        """Create pagination parameters."""
        return {"page": page, "page_size": page_size}
    
    @staticmethod
    def create_date_range_params(start_date: Optional[datetime] = Query(None, description="Start date"),
                                end_date: Optional[datetime] = Query(None, description="End date")) -> Dict[str, Optional[datetime]]:
        """Create date range parameters."""
        return {"start_date": start_date, "end_date": end_date}
    
    @staticmethod
    def create_sort_params(sort_by: str = Query("created_at", description="Sort field"),
                          sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order")) -> Dict[str, str]:
        """Create sorting parameters."""
        return {"sort_by": sort_by, "sort_order": sort_order}
    
    @staticmethod
    def create_search_params(search: Optional[str] = Query(None, description="Search term")) -> Dict[str, Optional[str]]:
        """Create search parameters."""
        return {"search": search}
    
    @staticmethod
    def extract_filters_from_query(query_params: Dict[str, Any], 
                                 allowed_filters: List[str]) -> Dict[str, Any]:
        """Extract and validate filters from query parameters."""
        filters = {}
        
        for key, value in query_params.items():
            if key in allowed_filters and value is not None:
                filters[key] = value
        
        return filters
    
    @staticmethod
    def build_hateoas_links(resource_id: Union[str, uuid.UUID], 
                           resource_type: str,
                           base_url: str = "") -> Dict[str, str]:
        """Build HATEOAS links for resource."""
        return {
            "self": f"{base_url}/api/v1/{resource_type}/{resource_id}",
            "collection": f"{base_url}/api/v1/{resource_type}"
        }
    
    @staticmethod
    def add_metadata_to_response(data: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Add metadata to response data."""
        if isinstance(data, dict):
            data["_metadata"] = metadata
        elif isinstance(data, list):
            return {
                "items": data,
                "_metadata": metadata
            }
        else:
            data = {"data": data, "_metadata": metadata}
        
        return data
    
    @staticmethod
    def create_api_key_info(key_id: str, key_name: str, permissions: List[str],
                          created_at: datetime, last_used: Optional[datetime] = None) -> Dict[str, Any]:
        """Create API key information response."""
        return {
            "key_id": key_id,
            "key_name": key_name,
            "permissions": permissions,
            "created_at": created_at.isoformat(),
            "last_used": last_used.isoformat() if last_used else None,
            "status": "active"
        }
    
    @staticmethod
    def create_rate_limit_info(limit: int, remaining: int, reset_time: datetime) -> Dict[str, Any]:
        """Create rate limit information response."""
        return {
            "limit": limit,
            "remaining": remaining,
            "reset_time": reset_time.isoformat(),
            "retry_after": max(0, (reset_time - datetime.utcnow()).total_seconds())
        }
    
    @staticmethod
    def validate_content_type(content_type: str, allowed_types: List[str]) -> bool:
        """Validate content type against allowed types."""
        return content_type in allowed_types
    
    @staticmethod
    def get_client_ip(request) -> str:
        """Get client IP address from request."""
        # Check for forwarded IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to client IP
        return request.client.host if request.client else "unknown"
    
    @staticmethod
    def get_user_agent(request) -> str:
        """Get user agent from request."""
        return request.headers.get("User-Agent", "unknown")
    
    @staticmethod
    def create_audit_log(action: str, resource_type: str, resource_id: Union[str, uuid.UUID],
                       user_id: Optional[Union[str, uuid.UUID]] = None,
                       details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create audit log entry."""
        return {
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "user_id": str(user_id) if user_id else None,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
            "ip_address": None,  # To be filled by middleware
            "user_agent": None   # To be filled by middleware
        }
    
    @staticmethod
    def format_error_for_client(error: Exception, include_traceback: bool = False) -> Dict[str, Any]:
        """Format error for client response."""
        error_response = {
            "error": type(error).__name__,
            "message": str(error),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if include_traceback:
            import traceback
            error_response["traceback"] = traceback.format_exc()
        
        return error_response
    
    @staticmethod
    def create_health_check_response(status: str = "healthy", 
                                  checks: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create health check response."""
        return {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",  # Should be from config
            "checks": checks or {}
        }
    
    @staticmethod
    def validate_api_version(version: str, supported_versions: List[str] = ["v1"]) -> bool:
        """Validate API version."""
        return version in supported_versions
    
    @staticmethod
    def create_cors_headers(allowed_origins: List[str], allowed_methods: List[str],
                           allowed_headers: List[str]) -> Dict[str, str]:
        """Create CORS headers."""
        return {
            "Access-Control-Allow-Origin": ", ".join(allowed_origins),
            "Access-Control-Allow-Methods": ", ".join(allowed_methods),
            "Access-Control-Allow-Headers": ", ".join(allowed_headers),
            "Access-Control-Max-Age": "86400"  # 24 hours
        }
    
    @staticmethod
    def sanitize_response_data(data: Any, exclude_fields: List[str] = None) -> Any:
        """Sanitize response data by excluding sensitive fields."""
        if exclude_fields is None:
            exclude_fields = ["password", "token", "secret", "key"]
        
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in exclude_fields}
        elif isinstance(data, list):
            return [APIUtils.sanitize_response_data(item, exclude_fields) for item in data]
        else:
            return data
    
    @staticmethod
    def create_cache_headers(max_age: int = 3600, etag: Optional[str] = None) -> Dict[str, str]:
        """Create cache control headers."""
        headers = {
            "Cache-Control": f"public, max-age={max_age}"
        }
        
        if etag:
            headers["ETag"] = etag
        
        return headers