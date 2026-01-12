"""Trust Battery service for tracking agent autonomy."""

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.clients.neo4j_client import get_neo4j_client
from app.config import get_settings

logger = logging.getLogger(__name__)


class TrustLevel(int, Enum):
    """Trust battery levels."""

    PROBATION = 1  # 0-50 consecutive accurate: Review all
    STANDARD = 2  # 50-100 consecutive accurate: Review exceptions
    CORE = 3  # 100+ consecutive accurate: Auto-approve


class TrustBatteryState(BaseModel):
    """Current state of the trust battery for a vendor."""

    vendor_id: str
    trust_level: TrustLevel
    consecutive_accurate: int = 0
    consecutive_errors: int = 0
    total_decisions: int = 0
    accurate_decisions: int = 0
    accuracy_rate: float = 0.0
    auto_approve_threshold: float = 0.0
    last_decision_at: Optional[str] = None


class DecisionOutcome(str, Enum):
    """Outcome of an agent decision."""

    ACCURATE = "accurate"  # Agent decision matched human
    ERROR = "error"  # Agent decision was incorrect


class TrustBatteryService:
    """Service for managing trust battery state and autonomy levels."""

    def __init__(self):
        """Initialize the trust battery service."""
        self.settings = get_settings()
        self.neo4j = get_neo4j_client()

    def get_threshold_for_level(self, level: TrustLevel) -> float:
        """Get auto-approve threshold for a trust level."""
        thresholds = {
            TrustLevel.PROBATION: self.settings.auto_approve_threshold_level1,
            TrustLevel.STANDARD: self.settings.auto_approve_threshold_level2,
            TrustLevel.CORE: self.settings.auto_approve_threshold_level3,
        }
        return thresholds.get(level, 0)

    def get_promotion_threshold(self, current_level: TrustLevel) -> int:
        """Get consecutive accurate decisions needed to promote."""
        if current_level == TrustLevel.PROBATION:
            return self.settings.trust_battery_promotion_threshold
        elif current_level == TrustLevel.STANDARD:
            return self.settings.trust_battery_core_threshold
        return 0  # Already at max

    async def get_vendor_trust(self, vendor_id: str) -> TrustBatteryState:
        """Get the current trust battery state for a vendor."""
        logger.debug(f"Getting trust state for vendor: {vendor_id}")

        # First try to get from Neo4j by id
        vendor = await self.neo4j.get_vendor(vendor_id)

        # If not found by id, try by name
        if vendor is None:
            vendor = await self.neo4j.get_vendor_by_name(vendor_id)

        if vendor and hasattr(vendor, "consecutive_accurate"):
            # Neo4j has trust data
            consecutive_accurate = getattr(vendor, "consecutive_accurate", 0)
            consecutive_errors = getattr(vendor, "consecutive_errors", 0)
            total = getattr(vendor, "total_invoices", 0)

            # Calculate trust level
            trust_level = self._calculate_level(consecutive_accurate)
            # accurate_decisions is stored separately, not derived from total - errors
            accurate_decisions = getattr(vendor, "accurate_decisions", total - consecutive_errors)
            accuracy_rate = accurate_decisions / total if total > 0 else 0.0

            logger.debug(
                f"Vendor {vendor_id}: level={trust_level.value}, "
                f"consecutive_accurate={consecutive_accurate}, total={total}"
            )

            return TrustBatteryState(
                vendor_id=vendor_id,
                trust_level=trust_level,
                consecutive_accurate=consecutive_accurate,
                consecutive_errors=consecutive_errors,
                total_decisions=total,
                accurate_decisions=accurate_decisions,
                accuracy_rate=accuracy_rate,
                auto_approve_threshold=self.get_threshold_for_level(trust_level),
                last_decision_at=datetime.utcnow().isoformat(),
            )

        # Vendor not found - create it
        logger.debug(f"Creating new vendor {vendor_id} in Neo4j")
        try:
            await self.neo4j.create_vendor_simple(
                name=vendor_id,
                industry="Unknown",
                trust_score=0.5,
                total_invoices=0,
                total_payments=0.0,
            )
        except Exception as e:
            logger.warning(f"Failed to create vendor {vendor_id}: {e}")

        # Return default state for new vendor
        logger.debug(f"New vendor {vendor_id}: initializing at PROBATION level")
        return TrustBatteryState(
            vendor_id=vendor_id,
            trust_level=TrustLevel.PROBATION,
            auto_approve_threshold=self.get_threshold_for_level(TrustLevel.PROBATION),
        )

    def _calculate_level(self, consecutive_accurate: int) -> TrustLevel:
        """Calculate trust level based on consecutive accurate decisions."""
        if consecutive_accurate >= self.settings.trust_battery_core_threshold:
            return TrustLevel.CORE
        elif consecutive_accurate >= self.settings.trust_battery_promotion_threshold:
            return TrustLevel.STANDARD
        return TrustLevel.PROBATION

    async def record_decision(
        self,
        vendor_id: str,
        outcome: DecisionOutcome | str,
        was_auto_approved: bool = False,
    ) -> TrustBatteryState:
        """Record a decision outcome and update trust battery."""
        # Convert string to enum if needed
        if isinstance(outcome, str):
            if outcome.upper() in ("APPROVED", "ACCURATE"):
                outcome = DecisionOutcome.ACCURATE
            else:
                outcome = DecisionOutcome.ERROR

        logger.debug(
            f"Recording decision for {vendor_id}: outcome={outcome.value}, "
            f"auto_approved={was_auto_approved}"
        )

        state = await self.get_vendor_trust(vendor_id)

        if outcome == DecisionOutcome.ACCURATE:
            new_consecutive_accurate = state.consecutive_accurate + 1
            new_consecutive_errors = 0
        else:  # ERROR
            new_consecutive_accurate = 0
            new_consecutive_errors = state.consecutive_errors + 1

        new_total = state.total_decisions + 1
        new_accurate = state.accurate_decisions + (1 if outcome == DecisionOutcome.ACCURATE else 0)
        new_accuracy = new_accurate / new_total if new_total > 0 else 0.0

        # Calculate new trust level
        new_trust_level = self._calculate_level(new_consecutive_accurate)

        # Demote on too many errors (battery drains)
        if new_consecutive_errors >= 5 and state.trust_level > TrustLevel.PROBATION:
            new_trust_level = TrustLevel(state.trust_level.value - 1)

        logger.debug(
            f"Updated trust for {vendor_id}: level={new_trust_level.value}, "
            f"consecutive_accurate={new_consecutive_accurate}"
        )

        new_threshold = self.get_threshold_for_level(new_trust_level)

        # Update Neo4j
        await self.neo4j.update_vendor_trust(
            vendor_id=vendor_id,
            trust_score=new_trust_level.value / 3.0,  # Normalize to 0-1
            consecutive_accurate=new_consecutive_accurate,
            consecutive_errors=new_consecutive_errors,
            total_invoices=new_total,
            accurate_decisions=new_accurate,
        )

        return TrustBatteryState(
            vendor_id=vendor_id,
            trust_level=new_trust_level,
            consecutive_accurate=new_consecutive_accurate,
            consecutive_errors=new_consecutive_errors,
            total_decisions=new_total,
            accurate_decisions=new_accurate,
            accuracy_rate=new_accuracy,
            auto_approve_threshold=new_threshold,
            last_decision_at=datetime.utcnow().isoformat(),
        )

    async def can_auto_approve(
        self,
        vendor_id: str,
        amount: float,
    ) -> dict:
        """Check if an invoice can be auto-approved based on trust level."""
        state = await self.get_vendor_trust(vendor_id)

        # Check trust level first (Level 1 always requires review)
        if state.trust_level == TrustLevel.PROBATION:
            return {
                "can_auto_approve": False,
                "reason": "Trust Level 1 (Probation): All decisions require review",
                "trust_level": state.trust_level.value,
                "threshold": state.auto_approve_threshold,
            }

        # Check amount threshold
        if amount > state.auto_approve_threshold:
            return {
                "can_auto_approve": False,
                "reason": f"Amount ${amount} exceeds threshold ${state.auto_approve_threshold}",
                "trust_level": state.trust_level.value,
                "threshold": state.auto_approve_threshold,
            }

        return {
            "can_auto_approve": True,
            "reason": f"Trust Level {state.trust_level.value}: Auto-approved within threshold",
            "trust_level": state.trust_level.value,
            "threshold": state.auto_approve_threshold,
        }

    async def reset_vendor_trust(
        self,
        vendor_id: str,
        level: TrustLevel = TrustLevel.PROBATION,
    ) -> TrustBatteryState:
        """Reset trust battery for a vendor (admin function)."""
        # Update Neo4j
        await self.neo4j.update_vendor_trust(
            vendor_id=vendor_id,
            trust_score=level.value / 3.0,
            consecutive_accurate=0,
        )

        return TrustBatteryState(
            vendor_id=vendor_id,
            trust_level=level,
            consecutive_accurate=0,
            consecutive_errors=0,
            total_decisions=0,
            accurate_decisions=0,
            accuracy_rate=0.0,
            auto_approve_threshold=self.get_threshold_for_level(level),
            last_decision_at=datetime.utcnow().isoformat(),
        )

    async def get_calibration_report(self) -> dict:
        """Get calibration report for all vendors."""
        # This would query all vendors and calculate statistics
        # For now, return a simplified report
        return {
            "total_vendors": 0,
            "level_distribution": {
                "probation": 0,
                "standard": 0,
                "core": 0,
            },
            "avg_accuracy": 0.0,
            "recommendations": [
                "Run in Shadow Mode for 14 days to collect calibration data"
            ],
        }


# Singleton instance
_trust_battery_service: Optional[TrustBatteryService] = None


def get_trust_battery_service() -> TrustBatteryService:
    """Get the singleton Trust Battery service instance."""
    global _trust_battery_service
    if _trust_battery_service is None:
        _trust_battery_service = TrustBatteryService()
    return _trust_battery_service
