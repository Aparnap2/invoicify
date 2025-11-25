"""
User management API endpoints with RBAC enforcement.

Provides CRUD operations for user management with proper
authorization and audit logging for AP Intake & Validation system.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.api.api_v1 import deps
from app.api.responses import APIResponse, create_error_response, create_success_response
from app.core.security import (
    SecurityContext, require_permissions, require_role,
    Permission, UserRole
)
from app.schemas.auth import (
    UserCreateRequest, UserUpdateRequest, UserResponse,
    UserProfileResponse, AuditLogResponse
)
from app.models.user import User, UserRole as UserRoleEnum, UserAuditLog
from app.services.auth.user_service import UserService
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0, description="Number of users to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of users to return"),
    search: Optional[str] = Query(None, description="Search query for email or name"),
    role: Optional[UserRoleEnum] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_READ)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    List users with filtering and pagination.
    
    Requires: users.read permission
    
    Args:
        skip: Number of users to skip
        limit: Maximum number of users to return
        search: Search query for email or name
        role: Filter by role
        is_active: Filter by active status
        security_context: Security context
        db: Database session
        
    Returns:
        List of users
    """
    try:
        user_service = UserService()
        
        # Build query
        query = select(User)
        
        # Apply filters
        filters = []
        
        if search:
            search_filter = or_(
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%")
            )
            filters.append(search_filter)
        
        if role:
            filters.append(User.role == role)
        
        if is_active is not None:
            filters.append(User.is_active == is_active)
        
        if filters:
            query = query.where(and_(*filters))
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        query = query.order_by(User.created_at.desc())
        
        # Execute query
        result = await db.execute(query)
        users = result.scalars().all()
        
        # Convert to response format
        user_list = []
        for user in users:
            user_data = UserResponse(
                id=str(user.id),
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                is_verified=user.is_verified,
                permissions=user._get_all_permissions(),
                last_login_at=user.last_login_at,
                login_count=user.login_count
            )
            user_list.append(user_data)
        
        return create_success_response(
            data=[user.dict() for user in user_list],
            message=f"Retrieved {len(user_list)} users"
        )
        
    except Exception as e:
        logger.error(f"List users error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing users"
        )


@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreateRequest,
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_CREATE)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Create a new user.
    
    Requires: users.create permission
    
    Args:
        user_data: User creation data
        security_context: Security context
        db: Database session
        
    Returns:
        Created user information
    """
    try:
        user_service = UserService()
        
        # Check if user already exists
        existing_user = await user_service.get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists"
            )
        
        # Create new user
        user = await user_service.get_or_create_user_by_email(
            db=db,
            email=user_data.email,
            full_name=user_data.full_name,
            role=user_data.role.value,
            metadata={
                "created_by": str(security_context.user.id),
                "creation_method": "admin_panel"
            }
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        
        # Set password if provided
        if user_data.password:
            user.password_hash = get_password_hash(user_data.password)
            await db.commit()
        
        # Prepare response
        response_data = UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            permissions=user._get_all_permissions(),
            last_login_at=user.last_login_at,
            login_count=user.login_count
        )
        
        logger.info(f"User created: {user_data.email} by {security_context.user.email}")
        return create_success_response(
            data=response_data.dict(),
            message="User created successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating user"
        )


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user(
    user_id: str,
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_READ)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Get user by ID.
    
    Requires: users.read permission
    
    Args:
        user_id: User ID
        security_context: Security context
        db: Database session
        
    Returns:
        User information
    """
    try:
        user_service = UserService()
        
        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prepare response
        response_data = UserProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            permissions=user._get_all_permissions(),
            timezone=user.timezone,
            language=user.language,
            preferences=user.preferences or {},
            last_login_at=user.last_login_at,
            login_count=user.login_count,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        
        return create_success_response(
            data=response_data.dict(),
            message="User retrieved successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving user"
        )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdateRequest,
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_UPDATE)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Update user information.
    
    Requires: users.update permission
    
    Args:
        user_id: User ID
        user_data: User update data
        security_context: Security context
        db: Database session
        
    Returns:
        Updated user information
    """
    try:
        user_service = UserService()
        
        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if user is trying to update their own role without admin permission
        if (str(user.id) == str(security_context.user.id) and 
            user_data.role is not None and 
            user_data.role != user.role and
            not security_context.user.has_permission(Permission.USER_MANAGE)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify your own role without admin permission"
            )
        
        # Prepare update data
        update_data = {}
        for field, value in user_data.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields to update"
            )
        
        # Update user
        updated_user = await user_service.update_user(db, user_id, update_data)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user"
            )
        
        # Prepare response
        response_data = UserResponse(
            id=str(updated_user.id),
            email=updated_user.email,
            full_name=updated_user.full_name,
            role=updated_user.role,
            is_active=updated_user.is_active,
            is_verified=updated_user.is_verified,
            permissions=updated_user._get_all_permissions(),
            last_login_at=updated_user.last_login_at,
            login_count=updated_user.login_count
        )
        
        logger.info(f"User updated: {user_id} by {security_context.user.email}")
        return create_success_response(
            data=response_data.dict(),
            message="User updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating user"
        )


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_DELETE)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Delete user.
    
    Requires: users.delete permission
    
    Args:
        user_id: User ID
        security_context: Security context
        db: Database session
        
    Returns:
        Deletion confirmation
    """
    try:
        user_service = UserService()
        
        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-deletion
        if str(user.id) == str(security_context.user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Deactivate user (soft delete)
        success = await user_service.deactivate_user(db, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user"
            )
        
        logger.info(f"User deleted: {user_id} by {security_context.user.email}")
        return create_success_response(
            message="User deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting user"
        )


@router.get("/{user_id}/audit-logs", response_model=List[AuditLogResponse])
async def get_user_audit_logs(
    user_id: str,
    skip: int = Query(0, ge=0, description="Number of logs to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of logs to return"),
    security_context: SecurityContext = Depends(require_permissions(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Get audit logs for a user.
    
    Requires: audit.view permission
    
    Args:
        user_id: User ID
        skip: Number of logs to skip
        limit: Maximum number of logs to return
        security_context: Security context
        db: Database session
        
    Returns:
        List of audit logs
    """
    try:
        user_service = UserService()
        
        # Check if user exists
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get audit logs
        audit_logs = await user_service.get_user_audit_logs(db, user_id, limit + skip)
        
        # Apply pagination
        paginated_logs = audit_logs[skip:skip + limit]
        
        # Convert to response format
        log_list = []
        for log in paginated_logs:
            log_data = AuditLogResponse(
                id=str(log.id),
                user_id=str(log.user_id) if log.user_id else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                success=log.success,
                error_message=log.error_message,
                details=log.details or {},
                created_at=log.created_at
            )
            log_list.append(log_data)
        
        return create_success_response(
            data=[log.dict() for log in log_list],
            message=f"Retrieved {len(log_list)} audit logs"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get audit logs error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving audit logs"
        )


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: str,
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_MANAGE)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Activate user account.
    
    Requires: users.manage permission
    
    Args:
        user_id: User ID
        security_context: Security context
        db: Database session
        
    Returns:
        Activation confirmation
    """
    try:
        user_service = UserService()
        
        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Activate user
        update_data = {"is_active": True}
        updated_user = await user_service.update_user(db, user_id, update_data)
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to activate user"
            )
        
        logger.info(f"User activated: {user_id} by {security_context.user.email}")
        return create_success_response(
            message="User activated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while activating user"
        )


@router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_MANAGE)),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Deactivate user account.
    
    Requires: users.manage permission
    
    Args:
        user_id: User ID
        security_context: Security context
        db: Database session
        
    Returns:
        Deactivation confirmation
    """
    try:
        user_service = UserService()
        
        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-deactivation
        if str(user.id) == str(security_context.user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account"
            )
        
        # Deactivate user
        success = await user_service.deactivate_user(db, user_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate user"
            )
        
        logger.info(f"User deactivated: {user_id} by {security_context.user.email}")
        return create_success_response(
            message="User deactivated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate user error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deactivating user"
        )


@router.get("/roles/permissions", response_model=Dict[str, List[str]])
async def get_role_permissions(
    security_context: SecurityContext = Depends(require_permissions(Permission.USER_READ))
) -> APIResponse:
    """
    Get permissions for all roles.
    
    Requires: users.read permission
    
    Args:
        security_context: Security context
        
    Returns:
        Role permissions mapping
    """
    try:
        from app.core.security import RolePermissions
        
        role_permissions = {}
        for role in UserRoleEnum:
            permissions = RolePermissions.get_permissions(role)
            role_permissions[role.value] = permissions
        
        return create_success_response(
            data=role_permissions,
            message="Role permissions retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get role permissions error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving role permissions"
        )


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    security_context: SecurityContext = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Get current user's profile.
    
    Args:
        security_context: Security context
        db: Database session
        
    Returns:
        Current user profile
    """
    try:
        user = security_context.user
        
        # Prepare response
        response_data = UserProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            permissions=user._get_all_permissions(),
            timezone=user.timezone,
            language=user.language,
            preferences=user.preferences or {},
            last_login_at=user.last_login_at,
            login_count=user.login_count,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        
        return create_success_response(
            data=response_data.dict(),
            message="Profile retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving profile"
        )


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_data: UserUpdateRequest,
    security_context: SecurityContext = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Update current user's profile.
    
    Args:
        user_data: User update data
        security_context: Security context
        db: Database session
        
    Returns:
        Updated user information
    """
    try:
        user_service = UserService()
        
        # Prepare update data (exclude role for self-update)
        update_data = {}
        for field, value in user_data.dict(exclude_unset=True).items():
            if field != 'role' and value is not None:
                update_data[field] = value
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields to update"
            )
        
        # Update user
        updated_user = await user_service.update_user(
            db, str(security_context.user.id), update_data
        )
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile"
            )
        
        # Prepare response
        response_data = UserResponse(
            id=str(updated_user.id),
            email=updated_user.email,
            full_name=updated_user.full_name,
            role=updated_user.role,
            is_active=updated_user.is_active,
            is_verified=updated_user.is_verified,
            permissions=updated_user._get_all_permissions(),
            last_login_at=updated_user.last_login_at,
            login_count=updated_user.login_count
        )
        
        logger.info(f"Profile updated: {security_context.user.email}")
        return create_success_response(
            data=response_data.dict(),
            message="Profile updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update profile error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating profile"
        )