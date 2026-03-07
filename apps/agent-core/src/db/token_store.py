"""
Redis-backed OAuth token store for stateless environments.

Stores QuickBooks OAuth 2.0 tokens in Redis for:
- Persistence across container restarts
- Shared state across multiple instances
- Proper token rotation handling

Usage:
    from src.db.token_store import get_token_store
    
    token_store = get_token_store()
    await token_store.connect()
    
    # Store tokens
    await token_store.set_tokens(
        realm_id="123456",
        access_token="eyJ...",
        refresh_token="AB12...",
        expires_at=1234567890,
    )
    
    # Retrieve tokens
    tokens = await token_store.get_tokens(realm_id="123456")
    
    # Delete tokens
    await token_store.delete_tokens(realm_id="123456")
    
    await token_store.disconnect()
"""

import json
import os
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import redis.asyncio as redis
from redis.exceptions import RedisError
import structlog

logger = structlog.get_logger()


class TokenStore:
    """Redis-backed OAuth token store."""
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize token store.
        
        Args:
            redis_url: Redis connection URL (REDIS_URL env var)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self._client: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """Connect to Redis."""
        if not self.redis_url:
            logger.warning("redis_url_not_configured_using_memory_store")
            return
        
        try:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # ping() returns Awaitable[bool] in async mode
            ping_result = await self._client.ping()  # type: ignore[misc]
            if ping_result:
                logger.info("redis_token_store_connected")
        except RedisError as e:
            logger.error("redis_connection_failed", error=str(e))
            self._client = None
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.aclose()
            logger.info("redis_token_store_disconnected")
    
    async def get_tokens(self, realm_id: str) -> Optional[Dict[str, Any]]:
        """
        Get OAuth tokens for a realm.
        
        Args:
            realm_id: QuickBooks realm/company ID
        
        Returns:
            Token dict or None if not found
        """
        if not self._client:
            return None
        
        try:
            key = f"qb:tokens:{realm_id}"
            data = await self._client.get(key)
            
            if not data:
                return None
            
            tokens = json.loads(data)
            logger.debug("qb_tokens_retrieved", realm_id=realm_id)
            return tokens
            
        except RedisError as e:
            logger.error("qb_tokens_retrieve_failed", realm_id=realm_id, error=str(e))
            return None
    
    async def set_tokens(
        self,
        realm_id: str,
        access_token: str,
        refresh_token: str,
        expires_at: int,
    ) -> bool:
        """
        Store OAuth tokens.
        
        Args:
            realm_id: QuickBooks realm/company ID
            access_token: OAuth access token
            refresh_token: OAuth refresh token (rotated on each refresh)
            expires_at: Unix timestamp when access token expires
        
        Returns:
            True if successful, False otherwise
        """
        if not self._client:
            return False
        
        try:
            key = f"qb:tokens:{realm_id}"
            tokens = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Store with TTL (expires_at + 5 minute buffer)
            ttl = expires_at - int(datetime.now(timezone.utc).timestamp()) + 300
            
            await self._client.setex(
                key,
                ttl,
                json.dumps(tokens),
            )
            
            logger.info(
                "qb_tokens_stored",
                realm_id=realm_id,
                expires_in_seconds=ttl,
            )
            return True
            
        except RedisError as e:
            logger.error("qb_tokens_store_failed", realm_id=realm_id, error=str(e))
            return False
    
    async def delete_tokens(self, realm_id: str) -> bool:
        """
        Delete stored tokens (e.g., on auth error).
        
        Args:
            realm_id: QuickBooks realm/company ID
        
        Returns:
            True if successful, False otherwise
        """
        if not self._client:
            return False
        
        try:
            key = f"qb:tokens:{realm_id}"
            await self._client.delete(key)
            logger.info("qb_tokens_deleted", realm_id=realm_id)
            return True
            
        except RedisError as e:
            logger.error("qb_tokens_delete_failed", realm_id=realm_id, error=str(e))
            return False


# Global instance
_token_store: Optional[TokenStore] = None


def get_token_store() -> TokenStore:
    """Get or create token store instance."""
    global _token_store
    if _token_store is None:
        _token_store = TokenStore()
    return _token_store
