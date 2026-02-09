"""
Update Trust Activity
Updates vendor trust battery after payment processing.
"""

import logging
from decimal import Decimal, InvalidOperation
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

    Raises:
        ApplicationError: If required parameters are missing or invalid
    """
    # Validate required parameters
    required_keys = ["vendor_id", "outcome", "amount"]
    missing_keys = [key for key in required_keys if key not in params]
    if missing_keys:
        raise activity.ApplicationError(
            f"Missing required parameters: {', '.join(missing_keys)}",
            non_retryable=True,
        )

    vendor_id = params["vendor_id"]

    # Validate outcome is a valid TrustOutcome enum value
    outcome_str = params["outcome"]
    try:
        outcome = TrustOutcome[outcome_str]
    except KeyError:
        valid_outcomes = [o.name for o in TrustOutcome]
        raise activity.ApplicationError(
            f"Invalid outcome '{outcome_str}'. Must be one of: {', '.join(valid_outcomes)}",
            non_retryable=True,
        )

    # Validate amount can be converted to Decimal
    try:
        amount = Decimal(str(params["amount"]))
    except (InvalidOperation, TypeError, ValueError) as e:
        raise activity.ApplicationError(
            f"Invalid amount '{params['amount']}': {str(e)}",
            non_retryable=True,
        ) from e

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
