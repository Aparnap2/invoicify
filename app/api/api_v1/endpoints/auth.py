"""
Authentication API endpoints for JWT + RBAC system.

Provides login, logout, token refresh, and password management endpoints
for the AP Intake & Validation system.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1 import deps
from app.api.responses import APIResponse, create_error_response, create_success_response
from app.core.security import SecurityContext, get_dev_user
from app.schemas.auth import (
    LoginRequest, LoginResponse, RefreshTokenRequest,
    PasswordResetRequest, PasswordResetConfirm, PasswordChangeRequest,
    UserResponse, TokenResponse
)
from app.services.auth.auth_service import auth_service
from app.services.auth.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Authenticate user and return JWT tokens.
    
    Args:
        request: HTTP request object
        login_data: Login credentials
        db: Database session
        
    Returns:
        JWT tokens and user information
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Authenticate user
        result = await auth_service.authenticate_user(
            db=db,
            email=login_data.email,
            password=login_data.password,
            request_info=request_info
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        user, tokens = result
        
        # Prepare response
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
        
        response_data = LoginResponse(
            user=user_data,
            tokens=TokenResponse(**tokens)
        )
        
        logger.info(f"User logged in successfully: {login_data.email}")
        return create_success_response(
            data=response_data.dict(),
            message="Login successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Refresh access token using refresh token.
    
    Args:
        request: HTTP request object
        refresh_data: Refresh token data
        db: Database session
        
    Returns:
        New JWT tokens
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Refresh token
        tokens = await auth_service.refresh_access_token(
            db=db,
            refresh_token=refresh_data.refresh_token,
            request_info=request_info
        )
        
        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        logger.info("Token refreshed successfully")
        return create_success_response(
            data=TokenResponse(**tokens).dict(),
            message="Token refreshed successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh"
        )


@router.post("/logout")
async def logout(
    request: Request,
    credentials: Optional[Any] = Depends(security),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Logout user and blacklist current token.
    
    Args:
        request: HTTP request object
        credentials: HTTP Bearer credentials
        db: Database session
        
    Returns:
        Logout confirmation
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Logout user
        if credentials and credentials.credentials:
            success = await auth_service.logout_user(
                db=db,
                token=credentials.credentials,
                request_info=request_info
            )
            
            if success:
                logger.info("User logged out successfully")
                return create_success_response(
                    message="Logout successful"
                )
        
        # Even if token is invalid, return success for security
        return create_success_response(
            message="Logout successful"
        )
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during logout"
        )


@router.post("/logout-all")
async def logout_all(
    request: Request,
    security_context: SecurityContext = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Logout user from all sessions.
    
    Args:
        request: HTTP request object
        security_context: Security context
        db: Database session
        
    Returns:
        Logout confirmation
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Logout from all sessions
        success = await auth_service.logout_all_sessions(
            db=db,
            user_id=str(security_context.user.id),
            request_info=request_info
        )
        
        if success:
            logger.info(f"User logged out from all sessions: {security_context.user.email}")
            return create_success_response(
                message="Logged out from all sessions successfully"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to logout from all sessions"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logout all sessions error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during logout"
        )


@router.post("/password-reset-request")
async def request_password_reset(
    request: Request,
    reset_request: PasswordResetRequest,
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Request password reset for user email.
    
    Args:
        request: HTTP request object
        reset_request: Password reset request
        db: Database session
        
    Returns:
        Password reset request confirmation
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Request password reset
        success = await auth_service.request_password_reset(
            db=db,
            email=reset_request.email,
            request_info=request_info
        )
        
        if success:
            logger.info(f"Password reset requested for: {reset_request.email}")
            return create_success_response(
                message="If the email exists, a password reset link has been sent"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process password reset request"
        )
        
    except Exception as e:
        logger.error(f"Password reset request error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during password reset request"
        )


@router.post("/password-reset")
async def reset_password(
    request: Request,
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Reset password with reset token.
    
    Args:
        request: HTTP request object
        reset_data: Password reset confirmation
        db: Database session
        
    Returns:
        Password reset confirmation
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Reset password
        success = await auth_service.reset_password(
            db=db,
            token=reset_data.token,
            new_password=reset_data.new_password,
            request_info=request_info
        )
        
        if success:
            logger.info("Password reset completed successfully")
            return create_success_response(
                message="Password reset successfully"
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during password reset"
        )


@router.post("/change-password")
async def change_password(
    request: Request,
    password_data: PasswordChangeRequest,
    security_context: SecurityContext = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db)
) -> APIResponse:
    """
    Change user password.
    
    Args:
        request: HTTP request object
        password_data: Password change data
        security_context: Security context
        db: Database session
        
    Returns:
        Password change confirmation
    """
    try:
        # Prepare request info for audit logging
        request_info = {
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": request.headers.get("X-Request-ID")
        }
        
        # Change password
        success = await auth_service.change_password(
            db=db,
            user_id=str(security_context.user.id),
            current_password=password_data.current_password,
            new_password=password_data.new_password,
            request_info=request_info
        )
        
        if success:
            logger.info(f"Password changed for user: {security_context.user.email}")
            return create_success_response(
                message="Password changed successfully"
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during password change"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    security_context: SecurityContext = Depends(deps.get_current_active_user)
) -> APIResponse:
    """
    Get current user information.
    
    Args:
        security_context: Security context
        
    Returns:
        Current user information
    """
    try:
        user = security_context.user
        
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
        
        return create_success_response(
            data=user_data.dict(),
            message="User information retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get user info error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving user information"
        )


@router.get("/verify-token")
async def verify_current_token(
    security_context: SecurityContext = Depends(deps.get_current_active_user)
) -> APIResponse:
    """
    Verify current JWT token validity.
    
    Args:
        security_context: Security context
        
    Returns:
        Token verification status
    """
    try:
        return create_success_response(
            data={
                "valid": True,
                "user_id": str(security_context.user.id),
                "email": security_context.user.email,
                "role": security_context.user.role,
                "expires_at": security_context.token_data.expires_at.isoformat() if security_context.token_data.expires_at else None
            },
            message="Token is valid"
        )
        
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return create_error_response(
            message="Token verification failed",
            details={"error": str(e)}
        )


# Development endpoints
@router.post("/dev-login")
async def dev_login() -> APIResponse:
    """
    Development login endpoint for testing.
    Only available in development environment.
    """
    try:
        from app.core.config import settings
        
        if settings.ENVIRONMENT.lower() not in ["development", "dev"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Development login only available in development mode"
            )
        
        # Get development user
        dev_user = get_dev_user()
        
        # Create development tokens
        from app.core.security import generate_dev_token
        dev_token = generate_dev_token()
        
        response_data = {
            "user": {
                "id": dev_user.user.id,
                "email": dev_user.user.email,
                "role": dev_user.user.role,
                "is_active": dev_user.user.is_active,
                "permissions": list(dev_user.permissions)
            },
            "tokens": {
                "access_token": dev_token,
                "token_type": "bearer",
                "expires_in": 365 * 24 * 60 * 60  # 1 year in seconds
            }
        }
        
        logger.info("Development login successful")
        return create_success_response(
            data=response_data,
            message="Development login successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Development login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during development login"
        )


@router.get("/dev-token")
async def get_dev_token() -> APIResponse:
    """
    Get development token for testing.
    Only available in development environment.
    """
    try:
        from app.core.config import settings
        
        if settings.ENVIRONMENT.lower() not in ["development", "dev"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Development token only available in development mode"
            )
        
        from app.core.security import generate_dev_token
        dev_token = generate_dev_token()
        
        return create_success_response(
            data={"token": dev_token},
            message="Development token generated"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Development token error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating development token"
        )