"""
Rate limiting middleware for AP Intake & Validation system.

Provides configurable rate limiting to prevent abuse and ensure fair usage.
"""

import logging
import time
from typing import Dict, Optional, Callable
from collections import defaultdict, deque
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from ..api.responses import RateLimitError


logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window algorithm.
    
    Limits requests based on IP address, user ID, or custom identifiers.
    """
    
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        requests_per_day: int = 10000,
        key_func: Optional[Callable] = None,
        exclude_paths: Optional[list] = None
    ):
        """
        Initialize rate limiting middleware.
        
        Args:
            app: FastAPI application
            requests_per_minute: Requests allowed per minute
            requests_per_hour: Requests allowed per hour
            requests_per_day: Requests allowed per day
            key_func: Function to extract rate limit key from request
            exclude_paths: Paths to exclude from rate limiting
        """
        super().__init__(app)
        
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.requests_per_day = requests_per_day
        self.key_func = key_func or self._default_key_func
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics",
            "/favicon.ico"
        ]
        
        # Storage for rate limit data
        self.requests: Dict[str, Dict[str, deque]] = defaultdict(lambda: {
            'minute': deque(),
            'hour': deque(),
            'day': deque()
        })
        
        logger.info("RateLimitMiddleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and apply rate limiting.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Skip rate limiting for excluded paths
        if self._should_exclude_path(request.url.path):
            return await call_next(request)
        
        # Get rate limit key
        key = self.key_func(request)
        
        # Check rate limits
        await self._check_rate_limits(key)
        
        # Record request
        self._record_request(key)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        self._add_rate_limit_headers(response, key)
        
        return response
    
    def _should_exclude_path(self, path: str) -> bool:
        """
        Check if path should be excluded from rate limiting.
        
        Args:
            path: Request path
            
        Returns:
            True if path should be excluded
        """
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    def _default_key_func(self, request: Request) -> str:
        """
        Default function to extract rate limit key from request.
        
        Args:
            request: HTTP request
            
        Returns:
            Rate limit key
        """
        # Use user ID if available, otherwise IP address
        if hasattr(request.state, 'user_id') and request.state.user_id:
            return f"user:{request.state.user_id}"
        
        # Get client IP
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            real_ip = request.headers.get("x-real-ip")
            ip = real_ip if real_ip else request.client.host
        
        return f"ip:{ip}"
    
    async def _check_rate_limits(self, key: str) -> None:
        """
        Check if request exceeds rate limits.
        
        Args:
            key: Rate limit key
            
        Raises:
            RateLimitError: If rate limit exceeded
        """
        current_time = time.time()
        
        # Check minute limit
        minute_requests = self.requests[key]['minute']
        while minute_requests and minute_requests[0] <= current_time - 60:
            minute_requests.popleft()
        
        if len(minute_requests) >= self.requests_per_minute:
            raise RateLimitError(
                "Rate limit exceeded: too many requests per minute",
                retry_after=60,
                limit=self.requests_per_minute,
                window=60
            )
        
        # Check hour limit
        hour_requests = self.requests[key]['hour']
        while hour_requests and hour_requests[0] <= current_time - 3600:
            hour_requests.popleft()
        
        if len(hour_requests) >= self.requests_per_hour:
            raise RateLimitError(
                "Rate limit exceeded: too many requests per hour",
                retry_after=3600,
                limit=self.requests_per_hour,
                window=3600
            )
        
        # Check day limit
        day_requests = self.requests[key]['day']
        while day_requests and day_requests[0] <= current_time - 86400:
            day_requests.popleft()
        
        if len(day_requests) >= self.requests_per_day:
            raise RateLimitError(
                "Rate limit exceeded: too many requests per day",
                retry_after=86400,
                limit=self.requests_per_day,
                window=86400
            )
    
    def _record_request(self, key: str) -> None:
        """
        Record request for rate limiting.
        
        Args:
            key: Rate limit key
        """
        current_time = time.time()
        
        self.requests[key]['minute'].append(current_time)
        self.requests[key]['hour'].append(current_time)
        self.requests[key]['day'].append(current_time)
    
    def _add_rate_limit_headers(self, response: Response, key: str) -> None:
        """
        Add rate limit headers to response.
        
        Args:
            response: HTTP response
            key: Rate limit key
        """
        current_time = time.time()
        
        # Count current requests in each window
        minute_count = len([
            req_time for req_time in self.requests[key]['minute']
            if req_time > current_time - 60
        ])
        hour_count = len([
            req_time for req_time in self.requests[key]['hour']
            if req_time > current_time - 3600
        ])
        day_count = len([
            req_time for req_time in self.requests[key]['day']
            if req_time > current_time - 86400
        ])
        
        # Add headers
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, self.requests_per_minute - minute_count))
        
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, self.requests_per_hour - hour_count))
        
        response.headers["X-RateLimit-Limit-Day"] = str(self.requests_per_day)
        response.headers["X-RateLimit-Remaining-Day"] = str(max(0, self.requests_per_day - day_count))


class UserBasedRateLimitMiddleware(RateLimitMiddleware):
    """
    User-based rate limiting middleware.
    
    Applies different rate limits based on user roles.
    """
    
    def __init__(
        self,
        app,
        role_limits: Optional[dict] = None,
        default_limits: Optional[dict] = None,
        **kwargs
    ):
        """
        Initialize user-based rate limiting middleware.
        
        Args:
            app: FastAPI application
            role_limits: Rate limits by role
            default_limits: Default rate limits
            **kwargs: Additional arguments for RateLimitMiddleware
        """
        self.role_limits = role_limits or self._get_default_role_limits()
        self.default_limits = default_limits or {
            'requests_per_minute': 60,
            'requests_per_hour': 1000,
            'requests_per_day': 10000
        }
        
        # Initialize with default limits
        super().__init__(app, **self.default_limits, **kwargs)
        
        logger.info("UserBasedRateLimitMiddleware initialized")
    
    def _get_default_role_limits(self) -> dict:
        """
        Get default rate limits by role.
        
        Returns:
            Default role limits
        """
        return {
            'admin': {
                'requests_per_minute': 120,
                'requests_per_hour': 2000,
                'requests_per_day': 20000
            },
            'processor': {
                'requests_per_minute': 100,
                'requests_per_hour': 1500,
                'requests_per_day': 15000
            },
            'reviewer': {
                'requests_per_minute': 80,
                'requests_per_hour': 1200,
                'requests_per_day': 12000
            },
            'viewer': {
                'requests_per_minute': 40,
                'requests_per_hour': 600,
                'requests_per_day': 6000
            }
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with user-based rate limiting.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
            
        Returns:
            HTTP response
        """
        # Get user roles if available
        user_roles = getattr(request.state, 'user_roles', [])
        
        # Apply appropriate rate limits
        if user_roles:
            # Use the highest limits among user's roles
            limits = self._get_user_limits(user_roles)
            self.requests_per_minute = limits['requests_per_minute']
            self.requests_per_hour = limits['requests_per_hour']
            self.requests_per_day = limits['requests_per_day']
        else:
            # Use default limits for unauthenticated users
            limits = self.default_limits
            self.requests_per_minute = limits['requests_per_minute']
            self.requests_per_hour = limits['requests_per_hour']
            self.requests_per_day = limits['requests_per_day']
        
        return await super().dispatch(request, call_next)
    
    def _get_user_limits(self, user_roles: list) -> dict:
        """
        Get rate limits for user based on roles.
        
        Args:
            user_roles: List of user roles
            
        Returns:
            Rate limits for user
        """
        max_limits = self.default_limits.copy()
        
        for role in user_roles:
            role_limits = self.role_limits.get(role, {})
            
            # Use the highest limits among all roles
            max_limits['requests_per_minute'] = max(
                max_limits['requests_per_minute'],
                role_limits.get('requests_per_minute', self.default_limits['requests_per_minute'])
            )
            max_limits['requests_per_hour'] = max(
                max_limits['requests_per_hour'],
                role_limits.get('requests_per_hour', self.default_limits['requests_per_hour'])
            )
            max_limits['requests_per_day'] = max(
                max_limits['requests_per_day'],
                role_limits.get('requests_per_day', self.default_limits['requests_per_day'])
            )
        
        return max_limits


def create_rate_limiter(
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
    requests_per_day: int = 10000,
    key_func: Optional[Callable] = None,
    exclude_paths: Optional[list] = None
) -> RateLimitMiddleware:
    """
    Create rate limiting middleware instance.
    
    Args:
        requests_per_minute: Requests allowed per minute
        requests_per_hour: Requests allowed per hour
        requests_per_day: Requests allowed per day
        key_func: Function to extract rate limit key from request
        exclude_paths: Paths to exclude from rate limiting
        
    Returns:
        RateLimitMiddleware instance
    """
    return RateLimitMiddleware(
        requests_per_minute=requests_per_minute,
        requests_per_hour=requests_per_hour,
        requests_per_day=requests_per_day,
        key_func=key_func,
        exclude_paths=exclude_paths
    )


def create_user_based_rate_limiter(
    role_limits: Optional[dict] = None,
    default_limits: Optional[dict] = None,
    exclude_paths: Optional[list] = None
) -> UserBasedRateLimitMiddleware:
    """
    Create user-based rate limiting middleware instance.
    
    Args:
        role_limits: Rate limits by role
        default_limits: Default rate limits
        exclude_paths: Paths to exclude from rate limiting
        
    Returns:
        UserBasedRateLimitMiddleware instance
    """
    return UserBasedRateLimitMiddleware(
        role_limits=role_limits,
        default_limits=default_limits,
        exclude_paths=exclude_paths
    )