"""
Caching utilities for consistent cache operations across the application.
"""

import json
import pickle
from typing import Any, Optional, Union, Callable, Dict, List
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import redis
from abc import ABC, abstractmethod


class CacheBackend(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cache entries."""
        pass
    
    @abstractmethod
    def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for key."""
        pass


class RedisCacheBackend(CacheBackend):
    """Redis cache backend implementation."""
    
    def __init__(self, redis_client: redis.Redis, key_prefix: str = "ap_intake:"):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.key_prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            value = self.redis.get(self._make_key(key))
            if value is None:
                return None
            return pickle.loads(value)
        except (pickle.PickleError, redis.RedisError):
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        try:
            serialized = pickle.dumps(value)
            return self.redis.setex(self._make_key(key), ttl or 3600, serialized)
        except (pickle.PickleError, redis.RedisError):
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            return bool(self.redis.delete(self._make_key(key)))
        except redis.RedisError:
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            return bool(self.redis.exists(self._make_key(key)))
        except redis.RedisError:
            return False
    
    def clear(self) -> bool:
        """Clear all cache entries with prefix."""
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis.keys(pattern)
            if keys:
                return bool(self.redis.delete(*keys))
            return True
        except redis.RedisError:
            return False
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for key."""
        try:
            ttl = self.redis.ttl(self._make_key(key))
            return ttl if ttl > 0 else None
        except redis.RedisError:
            return None


class MemoryCacheBackend(CacheBackend):
    """In-memory cache backend implementation."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def _cleanup_expired(self):
        """Remove expired entries."""
        now = datetime.utcnow()
        expired_keys = []
        
        for key, data in self._cache.items():
            if data['expires_at'] and data['expires_at'] < now:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        self._cleanup_expired()
        
        if key in self._cache:
            data = self._cache[key]
            if not data['expires_at'] or data['expires_at'] > datetime.utcnow():
                return data['value']
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        expires_at = None
        if ttl:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        self._cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'created_at': datetime.utcnow()
        }
        return True
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        return bool(self._cache.pop(key, None))
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        self._cleanup_expired()
        return key in self._cache
    
    def clear(self) -> bool:
        """Clear all cache entries."""
        self._cache.clear()
        return True
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for key."""
        if key in self._cache:
            data = self._cache[key]
            if data['expires_at']:
                remaining = data['expires_at'] - datetime.utcnow()
                return max(0, int(remaining.total_seconds()))
        return None


class CacheUtils:
    """Utility class for caching operations."""
    
    def __init__(self, backend: CacheBackend):
        self.backend = backend
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache with default."""
        value = self.backend.get(key)
        return value if value is not None else default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache."""
        return self.backend.set(key, value, ttl)
    
    def get_or_set(self, key: str, factory: Callable[[], Any], 
                   ttl: Optional[int] = None) -> Any:
        """Get value from cache or set using factory function."""
        value = self.backend.get(key)
        if value is not None:
            return value
        
        value = factory()
        self.backend.set(key, value, ttl)
        return value
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        return self.backend.delete(key)
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self.backend.exists(key)
    
    def clear(self) -> bool:
        """Clear all cache."""
        return self.backend.clear()
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for key."""
        return self.backend.get_ttl(key)
    
    def cache_result(self, ttl: int = 3600, key_prefix: str = ""):
        """Decorator to cache function results."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self._generate_cache_key(func, args, kwargs, key_prefix)
                
                # Try to get from cache
                result = self.backend.get(cache_key)
                if result is not None:
                    return result
                
                # Execute function and cache result
                result = func(*args, **kwargs)
                self.backend.set(cache_key, result, ttl)
                return result
            
            return wrapper
        return decorator
    
    def cache_method_result(self, ttl: int = 3600, key_prefix: str = ""):
        """Decorator to cache method results."""
        def decorator(func):
            @wraps(func)
            def wrapper(self_instance, *args, **kwargs):
                # Generate cache key including instance
                cache_key = self._generate_cache_key(
                    func, args, kwargs, key_prefix, str(id(self_instance))
                )
                
                # Try to get from cache
                result = self.backend.get(cache_key)
                if result is not None:
                    return result
                
                # Execute method and cache result
                result = func(self_instance, *args, **kwargs)
                self.backend.set(cache_key, result, ttl)
                return result
            
            return wrapper
        return decorator
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern."""
        if isinstance(self.backend, RedisCacheBackend):
            try:
                full_pattern = f"{self.backend.key_prefix}{pattern}"
                keys = self.backend.redis.keys(full_pattern)
                if keys:
                    return self.backend.redis.delete(*keys)
                return 0
            except redis.RedisError:
                return 0
        else:
            # For memory cache, we need to iterate through keys
            keys_to_delete = []
            for key in self.backend._cache.keys():
                if pattern.replace('*', '') in key:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                self.backend.delete(key)
            
            return len(keys_to_delete)
    
    def _generate_cache_key(self, func: Callable, args: tuple, kwargs: dict,
                           prefix: str = "", instance_id: str = "") -> str:
        """Generate cache key for function call."""
        # Create key components
        components = [prefix, instance_id, func.__module__, func.__name__]
        
        # Add args to key
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                components.append(str(arg))
            else:
                # For complex objects, use hash
                try:
                    arg_hash = hashlib.md5(str(arg).encode()).hexdigest()[:8]
                    components.append(arg_hash)
                except:
                    components.append("complex")
        
        # Add sorted kwargs to key
        for key in sorted(kwargs.keys()):
            components.append(key)
            value = kwargs[key]
            if isinstance(value, (str, int, float, bool)):
                components.append(str(value))
            else:
                try:
                    value_hash = hashlib.md5(str(value).encode()).hexdigest()[:8]
                    components.append(value_hash)
                except:
                    components.append("complex")
        
        # Join components and hash if too long
        cache_key = ":".join(components)
        if len(cache_key) > 200:
            cache_key = hashlib.md5(cache_key.encode()).hexdigest()
        
        return cache_key
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if isinstance(self.backend, MemoryCacheBackend):
            return {
                'backend': 'memory',
                'total_keys': len(self.backend._cache),
                'keys': list(self.backend._cache.keys())
            }
        elif isinstance(self.backend, RedisCacheBackend):
            try:
                info = self.backend.redis.info()
                return {
                    'backend': 'redis',
                    'total_keys': info.get('db0', {}).get('keys', 0),
                    'memory_usage': info.get('used_memory_human', 'unknown'),
                    'connected_clients': info.get('connected_clients', 0)
                }
            except redis.RedisError:
                return {'backend': 'redis', 'error': 'Unable to get stats'}
        else:
            return {'backend': 'unknown', 'error': 'Stats not available'}
    
    def warm_cache(self, data: Dict[str, Any], ttl: Optional[int] = None) -> int:
        """Warm cache with predefined data."""
        success_count = 0
        for key, value in data.items():
            if self.backend.set(key, value, ttl):
                success_count += 1
        return success_count
    
    def export_cache(self, pattern: str = "*") -> Dict[str, Any]:
        """Export cache data for backup/migration."""
        if isinstance(self.backend, RedisCacheBackend):
            try:
                full_pattern = f"{self.backend.key_prefix}{pattern}"
                keys = self.backend.redis.keys(full_pattern)
                export_data = {}
                
                for key in keys:
                    value = self.backend.get(key.replace(self.backend.key_prefix, ''))
                    if value is not None:
                        export_data[key.decode()] = value
                
                return export_data
            except redis.RedisError:
                return {}
        else:
            # For memory cache
            export_data = {}
            for key, data in self.backend._cache.items():
                if pattern == "*" or pattern.replace('*', '') in key:
                    export_data[key] = data['value']
            
            return export_data
    
    def import_cache(self, data: Dict[str, Any], ttl: Optional[int] = None) -> int:
        """Import cache data from backup/migration."""
        success_count = 0
        for key, value in data.items():
            if self.backend.set(key, value, ttl):
                success_count += 1
        return success_count