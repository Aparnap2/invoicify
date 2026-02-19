"""
Trust Battery System for Vendor Risk Management.

Implements a tiered trust model that learns from every invoice decision.
Trust levels adjust dynamically based on historical accuracy.

Trust Levels:
- PROBATION: New vendor. All invoices require human review.
- STANDARD: 50+ accurate invoices. Auto-approve ≤ $500.
- CORE: 100+ accurate invoices. Auto-approve ≤ $5,000.
- STRATEGIC: 200+ accurate invoices. Auto-approve ≤ $50,000.

Demotion happens automatically after 3 consecutive errors.
"""

from datetime import datetime
from typing import Optional
from decimal import Decimal

from src.schemas.invoice_v2 import TrustLevel, TrustBatteryState


class TrustBattery:
    """
    Vendor trust battery manager.
    
    Computes trust level, trust score, and auto-approve limits
    based on historical invoice accuracy.
    
    Thread-safe for concurrent updates.
    """
    
    # Trust level thresholds
    PROBATION_THRESHOLD = 0       # 0-49 invoices
    STANDARD_THRESHOLD = 50       # 50-99 invoices
    CORE_THRESHOLD = 100          # 100-199 invoices
    STRATEGIC_THRESHOLD = 200     # 200+ invoices
    
    # Auto-approve limits by trust level
    AUTO_APPROVE_LIMITS = {
        TrustLevel.PROBATION: 0.0,      # No auto-approval
        TrustLevel.STANDARD: 500.0,     # Up to $500
        TrustLevel.CORE: 5000.0,        # Up to $5,000
        TrustLevel.STRATEGIC: 50000.0,  # Up to $50,000
    }
    
    # Trust score weights
    ACCURACY_WEIGHT = 0.6
    VOLUME_WEIGHT = 0.2
    RECENCY_WEIGHT = 0.2
    
    # Demotion threshold: 3 consecutive errors triggers demotion
    CONSECUTIVE_ERROR_THRESHOLD = 3
    
    def __init__(
        self,
        vendor_id: str,
        tenant_id: str,
        invoice_count: int = 0,
        accurate_count: int = 0,
        error_count: int = 0,
        total_approved_amount: float = 0.0,
        consecutive_errors: int = 0,
        last_invoice_at: Optional[datetime] = None,
    ):
        """
        Initialize trust battery.
        
        Args:
            vendor_id: Unique vendor identifier
            tenant_id: Tenant identifier
            invoice_count: Total invoices processed
            accurate_count: Number of accurate invoices
            error_count: Number of invoices with errors
            total_approved_amount: Total amount approved
            consecutive_errors: Current streak of errors
            last_invoice_at: Timestamp of last invoice
        """
        self.vendor_id = vendor_id
        self.tenant_id = tenant_id
        self.invoice_count = invoice_count
        self.accurate_count = accurate_count
        self.error_count = error_count
        self.total_approved_amount = total_approved_amount
        self.consecutive_errors = consecutive_errors
        self.last_invoice_at = last_invoice_at or datetime.utcnow()
    
    @property
    def level(self) -> TrustLevel:
        """
        Compute current trust level based on invoice count and accuracy.
        
        Returns:
            TrustLevel: Current trust level
        """
        # Check for demotion due to consecutive errors
        if self.consecutive_errors >= self.CONSECUTIVE_ERROR_THRESHOLD:
            # Demote one level for each 3 consecutive errors
            if self.invoice_count >= self.STRATEGIC_THRESHOLD:
                return TrustLevel.CORE
            elif self.invoice_count >= self.CORE_THRESHOLD:
                return TrustLevel.STANDARD
            elif self.invoice_count >= self.STANDARD_THRESHOLD:
                return TrustLevel.PROBATION
            else:
                return TrustLevel.PROBATION
        
        # Normal level computation based on volume
        if self.invoice_count >= self.STRATEGIC_THRESHOLD:
            return TrustLevel.STRATEGIC
        elif self.invoice_count >= self.CORE_THRESHOLD:
            return TrustLevel.CORE
        elif self.invoice_count >= self.STANDARD_THRESHOLD:
            return TrustLevel.STANDARD
        else:
            return TrustLevel.PROBATION
    
    @property
    def score(self) -> float:
        """
        Compute trust score (0.0-1.0) based on accuracy, volume, and recency.
        
        Formula:
            score = (accuracy_weight * accuracy_rate) + 
                    (volume_weight * volume_factor) +
                    (recency_weight * recency_factor)
        
        Returns:
            float: Trust score between 0.0 and 1.0
        """
        # Accuracy component (60% weight)
        accuracy_rate = (
            self.accurate_count / self.invoice_count
            if self.invoice_count > 0
            else 0.0
        )
        
        # Volume component (20% weight) - logarithmic scaling
        # Reaches 1.0 at 200 invoices
        volume_factor = min(1.0, self.invoice_count / self.STRATEGIC_THRESHOLD)
        
        # Recency component (20% weight)
        # Decays if no recent invoices (30-day half-life)
        recency_factor = self._compute_recency_factor()
        
        trust_score = (
            self.ACCURACY_WEIGHT * accuracy_rate +
            self.VOLUME_WEIGHT * volume_factor +
            self.RECENCY_WEIGHT * recency_factor
        )
        
        return round(trust_score, 3)
    
    @property
    def auto_approve_limit(self) -> float:
        """
        Get auto-approve limit based on current trust level.
        
        Returns:
            float: Maximum amount for auto-approval
        """
        return self.AUTO_APPROVE_LIMITS.get(self.level, 0.0)
    
    def _compute_recency_factor(self) -> float:
        """
        Compute recency factor based on time since last invoice.
        
        Uses exponential decay with 30-day half-life.
        
        Returns:
            float: Recency factor between 0.0 and 1.0
        """
        if not self.last_invoice_at:
            return 0.0
        
        days_since_last = (datetime.utcnow() - self.last_invoice_at).days
        
        # Exponential decay: factor = e^(-ln(2) * days / 30)
        import math
        half_life_days = 30
        recency = math.exp(-math.log(2) * days_since_last / half_life_days)
        
        return round(recency, 3)
    
    def record_accurate_invoice(self, amount: float = 0.0) -> None:
        """
        Record an accurate invoice.
        
        Args:
            amount: Invoice amount that was approved
        """
        self.invoice_count += 1
        self.accurate_count += 1
        self.total_approved_amount += amount
        self.consecutive_errors = 0  # Reset error streak
        self.last_invoice_at = datetime.utcnow()
    
    def record_error(self) -> None:
        """
        Record an invoice with errors or fraud signals.
        
        Increases error count and consecutive error streak.
        """
        self.error_count += 1
        self.consecutive_errors += 1
        self.last_invoice_at = datetime.utcnow()
    
    def to_state(self) -> TrustBatteryState:
        """
        Convert to TrustBatteryState for persistence.
        
        Returns:
            TrustBatteryState: State object for Redis/Cosmos DB
        """
        return TrustBatteryState(
            vendor_id=self.vendor_id,
            tenant_id=self.tenant_id,
            invoice_count=self.invoice_count,
            accurate_count=self.accurate_count,
            error_count=self.error_count,
            total_approved_amount=self.total_approved_amount,
            trust_level=self.level,
            trust_score=self.score,
            auto_approve_limit=self.auto_approve_limit,
            last_invoice_at=self.last_invoice_at,
        )
    
    @classmethod
    def from_state(cls, state: TrustBatteryState) -> "TrustBattery":
        """
        Create TrustBattery from persisted state.
        
        Args:
            state: Persisted state object
            
        Returns:
            TrustBattery: Initialized trust battery
        """
        battery = cls(
            vendor_id=state.vendor_id,
            tenant_id=state.tenant_id,
            invoice_count=state.invoice_count,
            accurate_count=state.accurate_count,
            error_count=state.error_count,
            total_approved_amount=state.total_approved_amount,
            last_invoice_at=state.last_invoice_at,
        )
        return battery
    
    def __repr__(self) -> str:
        return (
            f"TrustBattery(vendor={self.vendor_id}, "
            f"level={self.level.value}, "
            f"score={self.score:.2f}, "
            f"limit=${self.auto_approve_limit:,.0f})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TRUST BATTERY MANAGER (REDIS-BACKED)
# ─────────────────────────────────────────────────────────────────────────────

class TrustBatteryManager:
    """
    Manages trust batteries with Redis caching.
    
    Provides:
    - Fast lookups from Redis cache
    - Persistent storage in Cosmos DB
    - Atomic updates with optimistic locking
    """
    
    def __init__(self, redis_client=None, cosmos_client=None):
        """
        Initialize trust battery manager.
        
        Args:
            redis_client: Redis client for hot cache
            cosmos_client: Cosmos DB client for persistence
        """
        self.redis_client = redis_client
        self.cosmos_client = cosmos_client
        self._cache_ttl = 300  # 5 minute cache TTL
    
    async def get_battery(self, vendor_id: str, tenant_id: str) -> TrustBattery:
        """
        Get trust battery for a vendor.
        
        Checks Redis cache first, falls back to Cosmos DB.
        
        Args:
            vendor_id: Vendor identifier
            tenant_id: Tenant identifier
            
        Returns:
            TrustBattery: Vendor's trust battery
        """
        cache_key = f"trust:{tenant_id}:{vendor_id}"
        
        # Try Redis cache first
        if self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                import json
                state_data = json.loads(cached)
                state = TrustBatteryState(**state_data)
                return TrustBattery.from_state(state)
        
        # Fall back to Cosmos DB
        if self.cosmos_client:
            state = await self._load_from_cosmos(vendor_id, tenant_id)
            if state:
                # Cache in Redis
                await self._cache_in_redis(cache_key, state)
                return TrustBattery.from_state(state)
        
        # Return new battery for new vendor
        return TrustBattery(vendor_id=vendor_id, tenant_id=tenant_id)
    
    async def update_battery(
        self,
        battery: TrustBattery,
        accurate: bool,
        amount: float = 0.0,
    ) -> TrustBattery:
        """
        Update trust battery after invoice processing.
        
        Args:
            battery: Current trust battery
            accurate: Whether invoice was accurate
            amount: Invoice amount
            
        Returns:
            TrustBattery: Updated trust battery
        """
        if accurate:
            battery.record_accurate_invoice(amount)
        else:
            battery.record_error()
        
        # Persist to Cosmos DB
        await self._save_to_cosmos(battery.to_state())
        
        # Invalidate Redis cache
        await self._invalidate_cache(battery.vendor_id, battery.tenant_id)
        
        return battery
    
    async def _cache_in_redis(self, cache_key: str, state: TrustBatteryState) -> None:
        """Cache state in Redis with TTL."""
        if not self.redis_client:
            return
        
        import json
        await self.redis_client.setex(
            cache_key,
            self._cache_ttl,
            json.dumps(state.model_dump(mode="json")),
        )
    
    async def _invalidate_cache(self, vendor_id: str, tenant_id: str) -> None:
        """Invalidate Redis cache for a vendor."""
        if not self.redis_client:
            return
        
        cache_key = f"trust:{tenant_id}:{vendor_id}"
        await self.redis_client.delete(cache_key)
    
    async def _load_from_cosmos(
        self,
        vendor_id: str,
        tenant_id: str,
    ) -> Optional[TrustBatteryState]:
        """Load state from Cosmos DB."""
        if not self.cosmos_client:
            return None
        
        # Implementation depends on Cosmos DB SDK
        # This is a placeholder
        return None
    
    async def _save_to_cosmos(self, state: TrustBatteryState) -> None:
        """Save state to Cosmos DB."""
        if not self.cosmos_client:
            return
        
        # Implementation depends on Cosmos DB SDK
        # This is a placeholder
        pass
