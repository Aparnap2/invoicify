import httpx
import os
import structlog
import json
from enum import IntEnum
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from functools import lru_cache
import redis.asyncio as redis
from src.utils.timing import timed

logger = structlog.get_logger()

# Optional Redis connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class TrustLevel(IntEnum):
    PROBATION = 1  # 0-50 consecutive accurate: Review all
    STANDARD = 2   # 50-100 consecutive accurate: Review exceptions
    CORE = 3       # 100+ consecutive accurate: Auto-approve

# Thresholds from PRD / trust-battery.ts
THRESHOLD_PROBATION_TO_STANDARD = 50
THRESHOLD_STANDARD_TO_CORE = 100

TRUST_THRESHOLDS = {
    TrustLevel.PROBATION: 0.0,      # $0 - review everything
    TrustLevel.STANDARD: 500.0,     # $500 - approve under $500
    TrustLevel.CORE: 5000.0,        # $5000 - approve under $5000
}

@dataclass
class TrustBatteryState:
    vendor_id: str
    trust_level: TrustLevel
    consecutive_accurate: int
    consecutive_errors: int
    total_decisions: int
    accurate_decisions: int
    auto_approve_threshold: float

class TrustBatteryManager:
    """Manages vendor trust scoring by communicating with Edge API."""
    
    def __init__(self):
        self.base_url = os.getenv("EDGE_API_BASE_URL", "http://host.docker.internal:8787")
        self.internal_url = f"{self.base_url}/internal"

    async def get_trust_battery(self, vendor_id: str) -> TrustBatteryState:
        """Fetch trust battery state for vendor. Checks Redis cache first."""
        cache_key = f"vendor:trust:{vendor_id}"
        
        async with timed("get_trust_battery", vendor_id):
            try:
                # 1. Try Redis
                cached = await redis_client.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return TrustBatteryState(**data)
            except Exception as e:
                logger.warning("redis_cache_error", error=str(e))

            try:
                # 2. Try D1 via Edge API
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{self.internal_url}/trust-battery/{vendor_id}")
                    response.raise_for_status()
                    record = response.json()
                
                if not record:
                    state = TrustBatteryState(
                        vendor_id=vendor_id,
                        trust_level=TrustLevel.PROBATION,
                        consecutive_accurate=0,
                        consecutive_errors=0,
                        total_decisions=0,
                        accurate_decisions=0,
                        auto_approve_threshold=TRUST_THRESHOLDS[TrustLevel.PROBATION],
                    )
                else:
                    state = TrustBatteryState(
                        vendor_id=record["vendor_id"],
                        trust_level=TrustLevel(record["trust_level"]),
                        consecutive_accurate=record["consecutive_accurate"],
                        consecutive_errors=record["consecutive_errors"],
                        total_decisions=record["total_decisions"],
                        accurate_decisions=record["accurate_decisions"],
                        auto_approve_threshold=record["auto_approve_threshold"],
                    )
                
                # 3. Update Redis
                try:
                    await redis_client.setex(cache_key, 300, json.dumps(asdict(state)))
                except Exception as e:
                    logger.warning("redis_update_error", error=str(e))
                
                return state

            except Exception as e:
                logger.error("fetch_trust_battery_failed", vendor_id=vendor_id, error=str(e))
                return TrustBatteryState(
                    vendor_id=vendor_id,
                    trust_level=TrustLevel.PROBATION,
                    consecutive_accurate=0,
                    consecutive_errors=0,
                    total_decisions=0,
                    accurate_decisions=0,
                    auto_approve_threshold=0.0
                )

    async def update_outcome(self, vendor_id: str, is_accurate: bool) -> TrustBatteryState:
        """Update trust battery with historical accuracy outcome."""
        state = await self.get_trust_battery(vendor_id)
        
        new_consecutive_accurate = state.consecutive_accurate + 1 if is_accurate else 0
        new_consecutive_errors = 0 if is_accurate else state.consecutive_errors + 1
        
        # Calculate new trust level
        new_trust_level = state.trust_level
        
        if new_consecutive_accurate >= THRESHOLD_STANDARD_TO_CORE:
            new_trust_level = TrustLevel.CORE
        elif new_consecutive_accurate >= THRESHOLD_PROBATION_TO_STANDARD:
            new_trust_level = TrustLevel.STANDARD
            
        # Demote on errors (Simple logic: demote if errors > 3)
        if new_consecutive_errors >= 3 and state.trust_level > TrustLevel.PROBATION:
            new_trust_level = TrustLevel(state.trust_level - 1)
            
        payload = {
            "vendor_id": vendor_id,
            "trust_level": new_trust_level.value,
            "consecutive_accurate": new_consecutive_accurate,
            "consecutive_errors": new_consecutive_errors,
            "total_decisions": state.total_decisions + 1,
            "accurate_decisions": state.accurate_decisions + (1 if is_accurate else 0),
            "auto_approve_threshold": TRUST_THRESHOLDS[new_trust_level]
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{self.internal_url}/trust-battery", json=payload)
            
        return await self.get_trust_battery(vendor_id)

    async def check_auto_approve_eligibility(self, vendor_id: str, amount: float) -> Dict[str, Any]:
        """Verify if amount is within vendor's auto-approval limit."""
        trust = await self.get_trust_battery(vendor_id)
        
        eligible = (trust.trust_level > TrustLevel.PROBATION) and (amount <= trust.auto_approve_threshold)
        
        return {
            "eligible": eligible,
            "trust_level": trust.trust_level.name,
            "threshold": trust.auto_approve_threshold,
            "reason": None if eligible else f"Amount {amount} exceeds threshold {trust.auto_approve_threshold} for level {trust.trust_level.name}"
        }
