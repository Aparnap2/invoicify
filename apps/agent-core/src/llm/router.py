"""
LLM Router - Multi-provider with automatic fallback.

Separate module for clean imports.
"""

from src.cache.trust_battery_cache import (
    LLMRouter,
    get_llm_router,
    chat_completion,
    PROVIDERS,
    GROQ_RPM_LIMIT,
)

__all__ = [
    "LLMRouter",
    "get_llm_router",
    "chat_completion",
    "PROVIDERS",
    "GROQ_RPM_LIMIT",
]
