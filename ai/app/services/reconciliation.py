"""Cash Reconciliation Service - Bank feed matching and reconciliation."""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from decimal import Decimal

from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)


class BankTransaction(BaseModel):
    """A transaction from the bank feed."""

    id: str
    amount: float
    date: str
    description: str
    type: str  # "debit" or "credit"
    merchant_name: Optional[str] = None


class PaymentMatch(BaseModel):
    """A match between a bank transaction and a scheduled payment."""

    transaction: BankTransaction
    payment_id: str
    invoice_id: str
    confidence: float  # 0-1 match confidence
    match_type: str  # "exact", "fuzzy", "manual"


class ReconciliationResult(BaseModel):
    """Result of a reconciliation batch."""

    matched: list[PaymentMatch] = []
    unmatched_transactions: list[BankTransaction] = []
    orphaned_payments: list[str] = []  # payment_ids
    total_matched_amount: float = 0.0
    timestamp: str = datetime.utcnow().isoformat()


class ReconciliationService:
    """Service for cash reconciliation operations."""

    def __init__(self):
        """Initialize the reconciliation service."""
        self.settings = get_settings()

    async def fetch_bank_transactions(
        self,
        hours_back: int = 24,
    ) -> list[BankTransaction]:
        """Fetch transactions from bank feed.

        In production, this would integrate with:
        - Mercury API
        - Plaid
        - Teller

        For now, returns mock data for testing.
        """
        logger.info(f"Fetching bank transactions for last {hours_back} hours")

        # Mock implementation - in production, call Mercury/Plaid API
        mock_transactions = [
            BankTransaction(
                id="txn_001",
                amount=3500.00,
                date=datetime.now().isoformat(),
                description="AWS WEB SERVICES - Invoice #INV-2024-001",
                type="debit",
                merchant_name="AWS",
            ),
            BankTransaction(
                id="txn_002",
                amount=1200.00,
                date=datetime.now().isoformat(),
                description="STRIPE TRANSFER",
                type="credit",
            ),
            BankTransaction(
                id="txn_003",
                amount=500.00,
                date=(datetime.now() - timedelta(days=1)).isoformat(),
                description="OPENAI LLC - ChatGPT",
                type="debit",
                merchant_name="OpenAI",
            ),
        ]

        return mock_transactions

    async def get_scheduled_payments(
        self,
        days_ahead: int = 7,
    ) -> list[dict]:
        """Get scheduled payments for matching.

        In production, this would query the database.
        For now, returns mock data.
        """
        # Mock implementation
        mock_payments = [
            {
                "payment_id": "pay_001",
                "invoice_id": "inv_001",
                "vendor_name": "AWS",
                "amount": 3500.00,
                "scheduled_date": datetime.now().strftime("%Y-%m-%d"),
                "status": "scheduled",
            },
            {
                "payment_id": "pay_002",
                "invoice_id": "inv_002",
                "vendor_name": "OpenAI",
                "amount": 500.00,
                "scheduled_date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                "status": "scheduled",
            },
        ]

        return mock_payments

    def _normalize_amount(self, amount: float) -> float:
        """Normalize amount for comparison (handle floating point)."""
        return round(amount, 2)

    def _normalize_description(self, description: str) -> str:
        """Normalize description for fuzzy matching."""
        # Remove special characters, lowercase
        normalized = re.sub(r"[^a-zA-Z0-9\s]", "", description.lower())
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        return normalized

    def _calculate_vendor_similarity(
        self,
        transaction_desc: str,
        vendor_name: str,
    ) -> float:
        """Calculate similarity between transaction description and vendor name."""
        tx_normalized = self._normalize_description(transaction_desc)
        vendor_normalized = vendor_name.lower().strip()

        # Direct substring match
        if vendor_normalized in tx_normalized:
            return 1.0

        # Check if any significant words match
        tx_words = set(tx_normalized.split())
        vendor_words = set(vendor_normalized.split())

        # Remove common words
        stop_words = {"llc", "inc", "corp", "ltd", "the", "of", "and", "for", "payment"}
        tx_words = tx_words - stop_words
        vendor_words = vendor_words - stop_words

        if not vendor_words:
            return 0.0

        matches = len(tx_words & vendor_words)
        return matches / len(vendor_words)

    def _calculate_date_similarity(
        self,
        tx_date: str,
        scheduled_date: str,
    ) -> float:
        """Calculate date similarity (0-1)."""
        try:
            tx = datetime.fromisoformat(tx_date.replace("Z", "+00:00").split("+")[0]).date()
            scheduled = datetime.fromisoformat(scheduled_date).date()

            days_diff = abs((tx - scheduled).days)

            if days_diff == 0:
                return 1.0
            elif days_diff == 1:
                return 0.9
            elif days_diff <= 3:
                return 0.7
            elif days_diff <= 7:
                return 0.5
            else:
                return 0.0
        except ValueError:
            return 0.5

    async def match_transactions(
        self,
        transactions: list[BankTransaction],
        payments: list[dict],
    ) -> list[PaymentMatch]:
        """Match bank transactions to scheduled payments."""
        matches: list[PaymentMatch] = []

        for tx in transactions:
            if tx.type != "debit":  # Only match debits (outgoing payments)
                continue

            best_match: Optional[PaymentMatch] = None
            best_score = 0.0

            for payment in payments:
                if payment["status"] != "scheduled":
                    continue

                amount_score = 1.0 if self._normalize_amount(tx.amount) == self._normalize_amount(payment["amount"]) else 0.0

                if amount_score < 0.9:  # Amounts must be very close
                    continue

                # Calculate vendor similarity
                vendor_score = self._calculate_vendor_similarity(
                    tx.description,
                    payment["vendor_name"],
                )

                # Calculate date similarity
                date_score = self._calculate_date_similarity(
                    tx.date,
                    payment["scheduled_date"],
                )

                # Weighted score
                total_score = (amount_score * 0.5) + (vendor_score * 0.3) + (date_score * 0.2)

                if total_score > 0.8 and total_score > best_score:
                    best_score = total_score
                    best_match = PaymentMatch(
                        transaction=tx,
                        payment_id=payment["payment_id"],
                        invoice_id=payment["invoice_id"],
                        confidence=total_score,
                        match_type="exact" if total_score > 0.95 else "fuzzy",
                    )

            if best_match:
                matches.append(best_match)
                logger.info(f"Matched transaction {tx.id} to payment {best_match.payment_id}")

        return matches

    async def reconcile(
        self,
        hours_back: int = 24,
        alert_threshold: float = 1000.0,
    ) -> ReconciliationResult:
        """Run full reconciliation process."""
        logger.info("Starting reconciliation process")

        # Fetch data
        transactions = await self.fetch_bank_transactions(hours_back)
        payments = await self.get_scheduled_payments()

        # Match transactions to payments
        matches = await self.match_transactions(transactions, payments)

        # Find unmatched transactions
        matched_tx_ids = {m.transaction.id for m in matches}
        unmatched_transactions = [tx for tx in transactions if tx.id not in matched_tx_ids]

        # Find orphaned payments (scheduled but not matched)
        matched_payment_ids = {m.payment_id for m in matches}
        orphaned_payments = [
            p["payment_id"]
            for p in payments
            if p["payment_id"] not in matched_payment_ids and p["status"] == "scheduled"
        ]

        # Calculate total matched
        total_matched = sum(m.transaction.amount for m in matches)

        # Check for alerts on unmatched transactions
        large_unmatched = [
            tx for tx in unmatched_transactions
            if tx.type == "debit" and tx.amount > alert_threshold
        ]

        if large_unmatched:
            logger.warning(
                f"Found {len(large_unmatched)} large unmatched transactions: "
                f"{[tx.id for tx in large_unmatched]}"
            )

        return ReconciliationResult(
            matched=matches,
            unmatched_transactions=unmatched_transactions,
            orphaned_payments=orphaned_payments,
            total_matched_amount=total_matched,
        )

    async def mark_as_reconciled(
        self,
        payment_id: str,
        transaction_id: str,
    ) -> dict:
        """Mark a payment as reconciled."""
        logger.info(f"Marking payment {payment_id} as reconciled with transaction {transaction_id}")

        # In production, update the database
        return {
            "payment_id": payment_id,
            "transaction_id": transaction_id,
            "status": "RECONCILED",
            "reconciled_at": datetime.utcnow().isoformat(),
        }

    async def alert_orphaned_transaction(
        self,
        transaction: BankTransaction,
    ) -> dict:
        """Generate alert for orphaned bank transaction."""
        logger.warning(f"Alert: Orphaned transaction {transaction.id} - ${transaction.amount}")

        # In production, send notification to founder
        return {
            "alert_type": "ORPHANED_TRANSACTION",
            "transaction_id": transaction.id,
            "amount": transaction.amount,
            "description": transaction.description,
            "severity": "HIGH" if transaction.amount > 1000 else "MEDIUM",
            "timestamp": datetime.utcnow().isoformat(),
            "action_required": "Review and match to invoice manually",
        }


# Singleton instance
_reconciliation_service: Optional[ReconciliationService] = None


def get_reconciliation_service() -> ReconciliationService:
    """Get the singleton Reconciliation service instance."""
    global _reconciliation_service
    if _reconciliation_service is None:
        _reconciliation_service = ReconciliationService()
    return _reconciliation_service
