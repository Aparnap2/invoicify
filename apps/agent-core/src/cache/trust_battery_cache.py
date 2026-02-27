"""
L1/L2/L3 Cache for Trust Battery + LLM Router.

Cache Strategy:
- L1: In-process dict (0ms) - 5 min TTL
- L2: Upstash Redis (1ms) - 24 hr TTL  
- L3: Cosmos DB (10ms) - Source of truth

LLM Router:
- Groq (primary) - 30 RPM free tier
- Azure Foundry (secondary) - $200 credit
- Ollama (tertiary) - Local, infinite

Usage:
    from src.cache.trust_battery_cache import get_vendor_trust
    from src.llm.router import chat_completion
    
    trust_level = await get_vendor_trust("vendor-123")
    response = await chat_completion(messages=[...])
"""

import os
import time
import structlog
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# L1/L2/L3 Cache for Trust Battery
# ─────────────────────────────────────────────────────────────────────────────

# L1: In-process cache
_L1_CACHE: Dict[str, Tuple[str, float]] = {}
L1_TTL_SECONDS = 300  # 5 minutes


class TrustBatteryCache:
    """
    Three-tier cache for trust battery lookups.
    
    Trust Battery is the most read-heavy component.
    Every invoice decision reads vendor trust level.
    
    Without caching: Every read = Cosmos DB query (10ms, 1 RU)
    With caching: L1 hit (0ms) → L2 hit (1ms) → L3 miss (10ms)
    """
    
    def __init__(self, redis_client, cosmos_client):
        """
        Initialize cache.
        
        Args:
            redis_client: Upstash Redis client (L2)
            cosmos_client: Cosmos DB client (L3)
        """
        self.redis = redis_client
        self.cosmos = cosmos_client
    
    async def get_vendor_trust(self, vendor_id: str) -> str:
        """
        Get vendor trust level with L1/L2/L3 caching.
        
        Args:
            vendor_id: Vendor identifier
        
        Returns:
            Trust level (PROBATION/STANDARD/CORE/STRATEGIC)
        """
        # L1 HIT - In-process cache
        if vendor_id in _L1_CACHE:
            trust_level, cached_at = _L1_CACHE[vendor_id]
            if time.time() - cached_at < L1_TTL_SECONDS:
                logger.debug("trust_cache_l1_hit", vendor_id=vendor_id)
                return trust_level
            # L1 expired
            del _L1_CACHE[vendor_id]
        
        # L2 HIT - Redis cache
        if self.redis:
            cached = await self.redis.get(f"trust:{vendor_id}")
            if cached:
                if isinstance(cached, bytes):
                    trust_level = cached.decode()
                else:
                    trust_level = cached
                # Populate L1
                _L1_CACHE[vendor_id] = (trust_level, time.time())
                logger.debug("trust_cache_l2_hit", vendor_id=vendor_id)
                return trust_level
        
        # L3 MISS - Cosmos DB query
        logger.info("trust_cache_miss_cosmos_query", vendor_id=vendor_id)
        
        if self.cosmos:
            vendor = await self.cosmos.get_vendor(vendor_id)
            trust_level = vendor.get("trust_level", "PROBATION") if vendor else "PROBATION"
        else:
            trust_level = "PROBATION"
        
        # Populate L2 + L1
        if self.redis:
            await self.redis.setex(f"trust:{vendor_id}", 86400, trust_level)  # 24hr TTL
        _L1_CACHE[vendor_id] = (trust_level, time.time())
        
        return trust_level
    
    async def invalidate_vendor_trust(self, vendor_id: str):
        """
        Invalidate cache after trust level change.
        
        Called after every decision event.
        
        Args:
            vendor_id: Vendor identifier
        """
        # Invalidate L1
        _L1_CACHE.pop(vendor_id, None)
        
        # Invalidate L2
        if self.redis:
            await self.redis.delete(f"trust:{vendor_id}")
        
        logger.info("trust_cache_invalidated", vendor_id=vendor_id)


# ─────────────────────────────────────────────────────────────────────────────
# LLM Router with Automatic Fallback
# ─────────────────────────────────────────────────────────────────────────────

# Provider configurations
GROQ_RPM_LIMIT = 30  # Conservative - actual limit is higher

PROVIDERS = {
    "groq": {
        "priority": 1,
        "model": "llama-3.3-70b-versatile",
        "rpm_limit": GROQ_RPM_LIMIT,
    },
    "azure_foundry": {
        "priority": 2,
        "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "rpm_limit": None,  # No hard limit (paid)
    },
    "ollama": {
        "priority": 3,
        "model": "qwen2.5:7b",
        "rpm_limit": None,  # Local, infinite
    },
}


class LLMRouter:
    """
    Multi-provider LLM router with automatic fallback.
    
    Strategy:
    1. Check Groq rate limit via Redis counter
    2. If Groq near limit → route to Azure Foundry
    3. If Azure credit low → route to Ollama
    4. Track per-provider latency + error rate
    5. Automatic failover on 429 or 5xx
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize router.
        
        Args:
            redis_client: Redis client for RPM tracking
        """
        self.redis = redis_client
        self._clients = {}
    
    def _get_client(self, provider: str):
        """Get or create client for provider."""
        if provider in self._clients:
            return self._clients[provider]
        
        from openai import AsyncOpenAI, AsyncAzureOpenAI
        
        if provider == "groq":
            client = AsyncOpenAI(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
            )
        elif provider == "azure_foundry":
            client = AsyncAzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                api_version="2024-08-01-preview",
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            )
        elif provider == "ollama":
            client = AsyncOpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1",
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        self._clients[provider] = client
        return client
    
    async def _get_groq_rpm_usage(self) -> int:
        """Get current Groq RPM usage."""
        if not self.redis:
            return 0
        
        key = f"groq:rpm:{int(time.time() // 60)}"
        count = await self.redis.get(key)
        return int(count) if count else 0
    
    async def _increment_groq_rpm(self):
        """Increment Groq RPM counter."""
        if not self.redis:
            return
        
        key = f"groq:rpm:{int(time.time() // 60)}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 120)  # 2 minute TTL
        await pipe.execute()
    
    async def select_provider(self) -> str:
        """
        Select best available LLM provider.
        
        Returns:
            Provider name (groq/azure_foundry/ollama)
        """
        # Check Groq rate limit
        groq_rpm = await self._get_groq_rpm_usage()
        
        if groq_rpm < GROQ_RPM_LIMIT:
            logger.debug("llm_routed_groq", current_rpm=groq_rpm)
            return "groq"
        
        # Check Azure availability
        if os.getenv("AZURE_OPENAI_KEY"):
            logger.info("llm_routed_azure_foundry", reason="groq_rpm_exceeded")
            return "azure_foundry"
        
        # Fallback to Ollama
        logger.warning("llm_routed_ollama", reason="all_cloud_providers_exhausted")
        return "ollama"
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, str]] = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """
        Unified LLM call with automatic provider selection + fallback.
        
        Args:
            messages: Chat messages
            response_format: Response format (e.g., {"type": "json_object"})
            temperature: Temperature (0.0 for deterministic)
            max_tokens: Max tokens
        
        Returns:
            Response content
        """
        provider = await self.select_provider()
        start = time.perf_counter()
        
        try:
            client = self._get_client(provider)
            model = PROVIDERS[provider]["model"]
            
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            if response_format:
                kwargs["response_format"] = response_format
            
            response = await client.chat.completions.create(**kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            
            # Track Groq usage
            if provider == "groq":
                await self._increment_groq_rpm()
            
            logger.info(
                "llm_call_success",
                provider=provider,
                latency_ms=round(latency_ms),
                tokens=response.usage.total_tokens if response.usage else "?",
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("llm_call_failed", provider=provider, error=str(e), latency_ms=round(latency_ms))
            
            # Immediate fallback to Azure if Groq fails
            if provider == "groq":
                logger.warning("llm_fallback_groq_to_azure")
                return await self._call_azure(messages, response_format, temperature, max_tokens)
            
            raise
    
    async def _call_azure(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Fallback to Azure Foundry."""
        client = self._get_client("azure_foundry")
        model = PROVIDERS["azure_foundry"]["model"]
        
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────

_cache_instance: Optional[TrustBatteryCache] = None
_router_instance: Optional[LLMRouter] = None


def get_trust_cache(redis_client, cosmos_client) -> TrustBatteryCache:
    """Get or create trust cache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = TrustBatteryCache(redis_client, cosmos_client)
    return _cache_instance


def get_llm_router(redis_client=None) -> LLMRouter:
    """Get or create LLM router singleton."""
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMRouter(redis_client)
    return _router_instance


async def chat_completion(messages: List[Dict[str, str]], **kwargs) -> str:
    """
    Unified LLM chat completion with automatic routing.
    
    Usage:
        response = await chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            response_format={"type": "json_object"},
        )
    """
    router = get_llm_router()
    return await router.chat_completion(messages, **kwargs)
