"""
Process Payment Activity
Executes payment for approved invoices.
"""

import logging
import uuid
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

from temporalio import activity

logger = logging.getLogger(__name__)


class PaymentProcessingError(Exception):
    """Custom exception for payment processing failures."""

    pass


@activity.defn
async def process_payment(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity: Process payment for approved invoice.

    In production, this would integrate with:
    - Stripe (for ACH/Card payments)
    - Plaid (for bank transfers)
    - ERP systems (NetSuite, QuickBooks)

    For now, simulates payment processing.

    Args:
        params: Dict with 'invoice_id', 'vendor_id', 'amount', 'currency'

    Returns:
        Dict with payment reference and status
    """
    invoice_id = params["invoice_id"]
    vendor_id = params["vendor_id"]
    amount = Decimal(str(params["amount"]))
    currency = params.get("currency", "USD")

    logger.info(
        f"💳 Processing payment: invoice={invoice_id}, "
        f"vendor={vendor_id}, amount=${amount} {currency}"
    )

    try:
        # In production, integrate with payment provider here
        # For now, generate mock payment reference
        payment_reference = f"PAY-{uuid.uuid4().hex[:12].upper()}"

        # Simulate payment processing delay
        await asyncio.sleep(0.5)

        logger.info(
            f"✅ Payment processed: {payment_reference} for invoice {invoice_id}"
        )

        return {
            "reference": payment_reference,
            "amount": str(amount),
            "currency": currency,
            "status": "completed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ Payment failed for invoice {invoice_id}: {e}")
        raise PaymentProcessingError(f"Payment failed: {e}") from e
