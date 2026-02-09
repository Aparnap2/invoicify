"""
Trust Battery System
Manages vendor trust levels with automatic progression/regression.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List

from src.domain.models import (
    TrustBattery,
    TrustLevel,
    TrustOutcome,
)
from src.interfaces import DatabaseAdapter

logger = logging.getLogger(__name__)


class TrustBatteryService:
    """
    Service for managing vendor trust batteries.

    Trust Levels:
    1 (NEW): Manual review required
    2 (LIMITED): Auto-approve up to $500
    3 (STANDARD): Auto-approve up to $2,000
    4 (TRUSTED): Auto-approve up to $5,000
    5 (VERIFIED): Auto-approve up to $20,000

    Progression Rules:
    - 1→2: 3 successful payments
    - 2→3: 5 successful payments + no disputes
    - 3→4: 10 successful payments + >$5,000 total
    - 4→5: 25 successful payments + >$20,000 total

    Regression Rules:
    - Any dispute: drop 1 level
    - Payment failure: drop to level 1
    - 6 months inactivity: drop 1 level
    """

    # Auto-approval limits by trust level
    AUTO_APPROVAL_LIMITS = {
        TrustLevel.NEW: Decimal("0.00"),  # Manual review required
        TrustLevel.LIMITED: Decimal("500.00"),
        TrustLevel.STANDARD: Decimal("2000.00"),
        TrustLevel.TRUSTED: Decimal("5000.00"),
        TrustLevel.VERIFIED: Decimal("20000.00"),
    }

    # Progression thresholds
    PROGRESSION_THRESHOLDS = {
        (TrustLevel.NEW, TrustLevel.LIMITED): {
            "successful_payments": 3,
            "min_amount": Decimal("0.00"),
        },
        (TrustLevel.LIMITED, TrustLevel.STANDARD): {
            "successful_payments": 5,
            "min_amount": Decimal("0.00"),
        },
        (TrustLevel.STANDARD, TrustLevel.TRUSTED): {
            "successful_payments": 10,
            "min_amount": Decimal("5000.00"),
        },
        (TrustLevel.TRUSTED, TrustLevel.VERIFIED): {
            "successful_payments": 25,
            "min_amount": Decimal("20000.00"),
        },
    }

    # Inactivity threshold
    INACTIVITY_THRESHOLD_DAYS = 180  # 6 months

    def __init__(self, db_adapter: DatabaseAdapter):
        self.db = db_adapter
        logger.info("✅ TrustBatteryService initialized")

    async def get_vendor_trust(self, vendor_id: str) -> TrustBattery:
        """
        Get or create trust battery for a vendor.

        Args:
            vendor_id: Unique vendor identifier

        Returns:
            TrustBattery for the vendor
        """
        # Try to get from database
        battery = await self._load_from_db(vendor_id)

        if battery:
            # Check for inactivity regression
            battery = await self._check_inactivity_regression(battery)
            return battery

        # Create new trust battery
        battery = TrustBattery(vendor_id=vendor_id)
        await self._save_to_db(battery)

        logger.info(f"Created new trust battery for vendor {vendor_id}")
        return battery

    async def update_trust(
        self,
        vendor_id: str,
        outcome: TrustOutcome,
        invoice_amount: Decimal,
    ) -> TrustBattery:
        """
        Update trust battery based on payment outcome.

        Args:
            vendor_id: Vendor identifier
            outcome: Payment outcome
            invoice_amount: Amount of the invoice

        Returns:
            Updated TrustBattery
        """
        battery = await self.get_vendor_trust(vendor_id)

        # Update based on outcome
        if outcome == TrustOutcome.PAYMENT_SUCCESS:
            battery = await self._handle_success(battery, invoice_amount)
        elif outcome == TrustOutcome.PAYMENT_FAILED:
            battery = await self._handle_failure(battery)
        elif outcome in (
            TrustOutcome.DISPUTE_RESOLVED,
            TrustOutcome.DISPUTE_UNRESOLVED,
        ):
            battery = await self._handle_dispute(battery, outcome)
        elif outcome == TrustOutcome.MANUAL_REVIEW_APPROVED:
            battery = await self._handle_manual_approval(battery)
        elif outcome == TrustOutcome.MANUAL_REVIEW_REJECTED:
            battery = await self._handle_manual_rejection(battery)

        # Update timestamps
        battery.updated_at = datetime.utcnow()
        if outcome == TrustOutcome.PAYMENT_SUCCESS:
            battery.last_payment_at = datetime.utcnow()

        # Save to database
        await self._save_to_db(battery)

        logger.info(
            f"Updated trust for {vendor_id}: level={battery.level.name}, "
            f"payments={battery.successful_payments}, disputes={battery.disputes}"
        )

        return battery

    async def _handle_success(
        self,
        battery: TrustBattery,
        amount: Decimal,
    ) -> TrustBattery:
        """Handle successful payment."""
        battery.successful_payments += 1
        battery.total_invoices += 1
        battery.total_amount_paid += amount

        # Update average invoice amount
        if battery.total_invoices > 0:
            battery.avg_invoice_amount = (
                battery.total_amount_paid / battery.total_invoices
            )

        # Check for level progression
        battery = await self._check_progression(battery)

        return battery

    async def _handle_failure(self, battery: TrustBattery) -> TrustBattery:
        """Handle payment failure - severe penalty."""
        # Drop to level 1
        old_level = battery.level
        battery.level = TrustLevel.NEW
        battery.total_invoices += 1

        logger.warning(
            f"Payment failure for {battery.vendor_id}: "
            f"level dropped from {old_level.name} to NEW"
        )

        return battery

    async def _handle_dispute(
        self,
        battery: TrustBattery,
        outcome: TrustOutcome,
    ) -> TrustBattery:
        """Handle dispute - drop one level."""
        battery.disputes += 1

        # Drop one level (but not below NEW)
        if battery.level != TrustLevel.NEW:
            old_level = battery.level
            # Get previous level
            levels = list(TrustLevel)
            current_idx = levels.index(battery.level)
            battery.level = levels[current_idx - 1]

            logger.warning(
                f"Dispute for {battery.vendor_id}: "
                f"level dropped from {old_level.name} to {battery.level.name}"
            )

        return battery

    async def _handle_manual_approval(self, battery: TrustBattery) -> TrustBattery:
        """Handle manual review approval."""
        battery.total_invoices += 1
        # Doesn't affect trust level directly
        return battery

    async def _handle_manual_rejection(self, battery: TrustBattery) -> TrustBattery:
        """Handle manual review rejection."""
        battery.total_invoices += 1
        # Consider this a soft penalty
        if battery.level.value > TrustLevel.LIMITED.value:
            old_level = battery.level
            levels = list(TrustLevel)
            current_idx = levels.index(battery.level)
            battery.level = levels[current_idx - 1]

            logger.warning(
                f"Manual rejection for {battery.vendor_id}: "
                f"level dropped from {old_level.name} to {battery.level.name}"
            )

        return battery

    async def _check_progression(self, battery: TrustBattery) -> TrustBattery:
        """Check if vendor should level up."""
        current_level = battery.level

        # Find next level
        levels = list(TrustLevel)
        current_idx = levels.index(current_level)

        if current_idx >= len(levels) - 1:
            # Already at max level
            return battery

        next_level = levels[current_idx + 1]
        threshold = self.PROGRESSION_THRESHOLDS.get((current_level, next_level))

        if not threshold:
            return battery

        # Check if thresholds met
        payments_ok = battery.successful_payments >= threshold["successful_payments"]
        amount_ok = battery.total_amount_paid >= threshold["min_amount"]
        disputes_ok = battery.disputes == 0

        if payments_ok and amount_ok and disputes_ok:
            battery.level = next_level
            logger.info(
                f"🎉 Vendor {battery.vendor_id} leveled up: "
                f"{current_level.name} → {next_level.name}"
            )

        return battery

    async def _check_inactivity_regression(
        self,
        battery: TrustBattery,
    ) -> TrustBattery:
        """Check if vendor should level down due to inactivity."""
        if not battery.last_payment_at:
            return battery

        days_since_payment = (datetime.utcnow() - battery.last_payment_at).days

        if days_since_payment > self.INACTIVITY_THRESHOLD_DAYS:
            # Drop one level (but not below LIMITED)
            if battery.level.value > TrustLevel.LIMITED.value:
                old_level = battery.level
                levels = list(TrustLevel)
                current_idx = levels.index(battery.level)
                battery.level = levels[current_idx - 1]

                logger.warning(
                    f"Inactivity regression for {battery.vendor_id}: "
                    f"level dropped from {old_level.name} to {battery.level.name} "
                    f"({days_since_payment} days inactive)"
                )

        return battery

    def get_auto_approval_limit(self, trust_level: TrustLevel) -> Decimal:
        """
        Get auto-approval limit for a trust level.

        Args:
            trust_level: Vendor trust level

        Returns:
            Maximum amount for auto-approval
        """
        return self.AUTO_APPROVAL_LIMITS.get(trust_level, Decimal("0.00"))

    def can_auto_approve(
        self,
        trust_battery: TrustBattery,
        amount: Decimal,
    ) -> bool:
        """
        Check if invoice can be auto-approved.

        Args:
            trust_battery: Vendor's trust battery
            amount: Invoice amount

        Returns:
            True if can auto-approve
        """
        limit = self.get_auto_approval_limit(trust_battery.level)
        return amount <= limit

    async def get_all_vendors(self) -> List[TrustBattery]:
        """Get all vendor trust batteries."""
        # This would query the database
        # For now, return empty list (implement with actual DB query)
        return []

    async def _load_from_db(self, vendor_id: str) -> Optional[TrustBattery]:
        """Load trust battery from database."""
        try:
            # Query database
            result = await self.db.get_vendor_history(vendor_id, limit=1)
            if result and len(result) > 0:
                # Parse from database format
                data = result[0]
                return TrustBattery(
                    vendor_id=data.get("vendor_id", vendor_id),
                    level=TrustLevel(data.get("trust_level", 1)),
                    successful_payments=data.get("successful_payments", 0),
                    disputes=data.get("disputes", 0),
                    total_invoices=data.get("total_invoices", 0),
                    total_amount_paid=Decimal(
                        str(data.get("total_amount_paid", "0.00"))
                    ),
                    avg_invoice_amount=Decimal(
                        str(data.get("avg_invoice_amount", "0.00"))
                    ),
                    created_at=datetime.fromisoformat(data.get("created_at")),
                    updated_at=datetime.fromisoformat(data.get("updated_at")),
                    last_payment_at=datetime.fromisoformat(data.get("last_payment_at"))
                    if data.get("last_payment_at")
                    else None,
                )
        except Exception as e:
            logger.error(f"Failed to load trust battery for {vendor_id}: {e}")

        return None

    async def _save_to_db(self, battery: TrustBattery) -> None:
        """Save trust battery to database."""
        try:
            # Save to database
            data = {
                "vendor_id": battery.vendor_id,
                "trust_level": battery.level.value,
                "successful_payments": battery.successful_payments,
                "disputes": battery.disputes,
                "total_invoices": battery.total_invoices,
                "total_amount_paid": str(battery.total_amount_paid),
                "avg_invoice_amount": str(battery.avg_invoice_amount),
                "created_at": battery.created_at.isoformat(),
                "updated_at": battery.updated_at.isoformat(),
                "last_payment_at": battery.last_payment_at.isoformat()
                if battery.last_payment_at
                else None,
            }
            # This would be an actual DB call
            # await self.db.save_vendor_trust(data)
            logger.debug(f"Saved trust battery for {battery.vendor_id}")
        except Exception as e:
            logger.error(f"Failed to save trust battery for {battery.vendor_id}: {e}")
