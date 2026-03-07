"""
Tests for Redis-backed OAuth token store.

Run with:
    pytest src/db/test_token_store.py -v
"""

import asyncio
import os
import time
import pytest
from token_store import TokenStore


@pytest.fixture
def token_store():
    """Create token store instance."""
    # Use test Redis URL if available, otherwise test will skip Redis tests
    redis_url = os.getenv("REDIS_URL")
    store = TokenStore(redis_url=redis_url)
    yield store


@pytest.mark.asyncio
async def test_token_store_initialization(token_store):
    """Test token store initializes correctly."""
    assert token_store.redis_url is None or isinstance(token_store.redis_url, str)
    assert token_store._client is None


@pytest.mark.asyncio
async def test_token_store_connect_no_redis(token_store):
    """Test connect gracefully handles missing Redis URL."""
    # Should not raise, just log warning
    await token_store.connect()
    # Client should be None when Redis URL not configured
    assert token_store._client is None


@pytest.mark.asyncio
async def test_token_store_set_tokens_no_redis(token_store):
    """Test set_tokens gracefully handles missing Redis."""
    result = await token_store.set_tokens(
        realm_id="123456",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=int(time.time()) + 3600,
    )
    # Should return False when Redis not available
    assert result is False


@pytest.mark.asyncio
async def test_token_store_get_tokens_no_redis(token_store):
    """Test get_tokens gracefully handles missing Redis."""
    result = await token_store.get_tokens(realm_id="123456")
    # Should return None when Redis not available
    assert result is None


@pytest.mark.asyncio
async def test_token_store_delete_tokens_no_redis(token_store):
    """Test delete_tokens gracefully handles missing Redis."""
    result = await token_store.delete_tokens(realm_id="123456")
    # Should return False when Redis not available
    assert result is False


@pytest.mark.asyncio
async def test_token_store_with_redis():
    """Test token store with actual Redis connection."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL not configured")
    
    store = TokenStore(redis_url=redis_url)
    await store.connect()
    
    try:
        # Test set_tokens
        realm_id = "test_realm_123"
        access_token = "test_access_token_xyz"
        refresh_token = "test_refresh_token_abc"
        expires_at = int(time.time()) + 3600
        
        set_result = await store.set_tokens(
            realm_id=realm_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        assert set_result is True
        
        # Test get_tokens
        tokens = await store.get_tokens(realm_id=realm_id)
        assert tokens is not None
        assert tokens["access_token"] == access_token
        assert tokens["refresh_token"] == refresh_token
        assert tokens["expires_at"] == expires_at
        assert "updated_at" in tokens
        
        # Test delete_tokens
        delete_result = await store.delete_tokens(realm_id=realm_id)
        assert delete_result is True
        
        # Verify deletion
        tokens_after_delete = await store.get_tokens(realm_id=realm_id)
        assert tokens_after_delete is None
        
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_token_store_ttl():
    """Test that tokens have proper TTL."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL not configured")
    
    store = TokenStore(redis_url=redis_url)
    await store.connect()
    
    try:
        realm_id = "test_realm_ttl"
        expires_at = int(time.time()) + 3600  # 1 hour from now
        
        await store.set_tokens(
            realm_id=realm_id,
            access_token="token",
            refresh_token="refresh",
            expires_at=expires_at,
        )
        
        # Get TTL from Redis
        key = f"qb:tokens:{realm_id}"
        ttl = await store._client.ttl(key)
        
        # TTL should be approximately expires_at + 300 buffer
        expected_ttl = expires_at - int(time.time()) + 300
        assert ttl > 0
        assert ttl <= expected_ttl + 10  # Allow 10 second variance
        
    finally:
        await store.disconnect()
        # Cleanup
        await store.delete_tokens("test_realm_ttl")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
