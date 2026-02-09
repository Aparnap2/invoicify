"""
Update Trust Activity
Updates vendor trust battery after payment processing.
"""

import logging
from decimal import Decimal
from typing import Dict, Any

from temporalio import activity

from src.config.factory import get_db
from src.domain.trust_battery import TrustBatteryService
from src.domain.models import TrustOutcome

logger = logging.getLogger(__name__)


@activity.defn
async def update_vendor_trust(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity: Update vendor trust battery after payment.

    Args:
        params: Dict with 'vendor_id', 'outcome', 'amount'

    Returns:
        Updated TrustBattery as dictionary
    """
    vendor_id = params["vendor_id"]
    outcome = TrustOutcome[params["outcome"]]
    amount = Decimal(str(params["amount"]))

    logger.info(
        f"🔋 Updating trust for {vendor_id}: outcome={outcome.name}, amount=${amount}"
    )

    # Get database adapter
    db = get_db()

    # Create service
    service = TrustBatteryService(db)

    # Update trust
    updated_battery = await service.update_trust(
        vendor_id=vendor_id,
        outcome=outcome,
        invoice_amount=amount,
    )

    logger.info(
        f"🔋 Updated trust: level={updated_battery.level.name}, "
        f"payments={updated_battery.successful_payments}"
    )

    return updated_battery.to_dict()
