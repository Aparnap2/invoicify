"""Integration tests for all AI service components."""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import sys
sys.path.insert(0, '/home/aparna/Desktop/invoicify/ai')

from app.config import get_settings
from app.clients.ollama_client import OllamaClient
from app.clients.neo4j_client import Neo4jClient
from app.services.trust_battery import TrustBatteryService, TrustLevel, TrustBatteryState
from app.agents.analyst import AnalystAgent, AnalystProposal
from app.agents.critic import CriticAgent, FinancialContext, CriticReview
from app.services.reconciliation import ReconciliationService
from app.schemas.invoice import InvoiceCreate, InvoiceExtracted, InvoiceStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_ollama_client():
    """Test Ollama client for LLM and embeddings."""
    logger.info("=" * 50)
    logger.info("TEST: Ollama Client")
    logger.info("=" * 50)

    client = OllamaClient()
    models = await client.list_models()
    logger.info(f"Available models: {models}")

    # Test simple ask
    response = await client.ask("What is 2+2? Respond with just the number.")
    logger.info(f"Ask response: {response}")

    # Test embedding
    embedding = await client.embed_single("Hello, world!")
    logger.info(f"Embedding dim: {len(embedding)}")

    logger.info("PASS: Ollama client works!\n")
    return True


async def test_neo4j_client():
    """Test Neo4j client for knowledge graph."""
    logger.info("=" * 50)
    logger.info("TEST: Neo4j Client")
    logger.info("=" * 50)

    client = Neo4jClient()
    await client.initialize_schema()
    logger.info("Schema initialized")

    # Create a test vendor
    test_vendor = f"TestVendor_{uuid4().hex[:8]}"
    await client.create_vendor_simple(
        name=test_vendor,
        industry="Technology",
        trust_score=0.85,
        total_invoices=10,
        total_payments=50000.0,
    )
    logger.info(f"Created vendor: {test_vendor}")

    # Get vendor by name
    vendor = await client.get_vendor_by_name(test_vendor)
    logger.info(f"Retrieved vendor: {vendor}")

    # Create invoice
    invoice_id = str(uuid4())
    await client.create_invoice_simple(
        invoice_id=invoice_id,
        vendor_name=test_vendor,
        amount=1500.0,
        status="PENDING",
        due_date="2024-02-01",
    )
    logger.info(f"Created invoice: {invoice_id}")

    # Get invoices by vendor
    invoices = await client.get_invoices_by_vendor(test_vendor)
    logger.info(f"Found {len(invoices)} invoices for {test_vendor}")

    # Update trust
    await client.update_vendor_trust(vendor.id, trust_score=0.9, consecutive_accurate=5)
    logger.info("Updated trust battery")

    logger.info("PASS: Neo4j client works!\n")
    return True


async def test_trust_battery_service():
    """Test Trust Battery service."""
    logger.info("=" * 50)
    logger.info("TEST: Trust Battery Service")
    logger.info("=" * 50)

    service = TrustBatteryService()
    test_vendor = f"TrustTest_{uuid4().hex[:8]}"

    # Initial trust level
    level = await service.get_vendor_trust(test_vendor)
    logger.info(f"Initial trust level for {test_vendor}: {level.trust_level.value}")

    # Record decisions
    await service.record_decision(test_vendor, "APPROVED", was_auto_approved=True)
    await service.record_decision(test_vendor, "APPROVED", was_auto_approved=True)
    await service.record_decision(test_vendor, "APPROVED", was_auto_approved=True)

    level = await service.get_vendor_trust(test_vendor)
    logger.info(f"Trust level after 3 auto-approvals: {level.trust_level.value}")

    # Check auto-approve
    can_auto = await service.can_auto_approve(test_vendor, 500.0)
    logger.info(f"Can auto-approve $500: {can_auto}")

    # Record a manual review (strings are accepted now)
    await service.record_decision(test_vendor, "REVIEWED", was_auto_approved=False)

    level = await service.get_vendor_trust(test_vendor)
    logger.info(f"Trust level after manual review: {level.trust_level.value}")

    logger.info("PASS: Trust Battery service works!\n")
    return True


async def test_analyst_agent():
    """Test Analyst Agent."""
    logger.info("=" * 50)
    logger.info("TEST: Analyst Agent")
    logger.info("=" * 50)

    agent = AnalystAgent()

    # Create mock invoice
    invoice = InvoiceExtracted(
        vendor_name="AWS",
        vendor_address="Seattle, WA",
        invoice_number="INV-2024-001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("3500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("3500.00"),
        line_items=[],
        payment_terms="Net 30",
        po_number="PO-001",
        overall_confidence=0.95,
        confidence_scores=[],
    )

    # Analyze (signature takes invoice_data and optional vendor_id)
    proposal = await agent.analyze(
        invoice_data=invoice,
        vendor_id=None,  # No vendor history for this test
    )

    logger.info(f"Analyst proposal: {proposal.proposed_action}")
    logger.info(f"Confidence: {proposal.confidence:.0%}")
    logger.info(f"Anomalies detected: {len(proposal.anomalies)}")
    for anomaly in proposal.anomalies:
        logger.info(f"  - [{anomaly.severity}] {anomaly.description}")

    logger.info("PASS: Analyst agent works!\n")
    return True


async def test_critic_agent():
    """Test Critic Agent."""
    logger.info("=" * 50)
    logger.info("TEST: Critic Agent")
    logger.info("=" * 50)

    agent = CriticAgent()

    # Create mock invoice
    invoice = InvoiceExtracted(
        vendor_name="AWS",
        vendor_address="Seattle, WA",
        invoice_number="INV-2024-001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("3500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("3500.00"),
        line_items=[],
        payment_terms="Net 30",
        overall_confidence=0.95,
        confidence_scores=[],
    )

    # Mock financial context
    financial_context = FinancialContext(
        current_cash=50000.0,
        monthly_burn_rate=15000.0,
        runway_days=100.0,
        payroll_date="15",
        payroll_amount=25000.0,
        safety_buffer=10000.0,
        strategy_mode="OPTIMIZE",
        auto_approve_threshold=1000.0,
    )

    # Review
    review = await agent.review(
        invoice_data=invoice,
        financial_context=financial_context,
        trust_level=2,
        trust_threshold=1000.0,
    )

    logger.info(f"Critic can proceed: {review.can_proceed}")
    logger.info(f"Risk score: {review.risk_score:.0%}")
    logger.info(f"Signals: {len(review.signals)}")
    for signal in review.signals:
        logger.info(f"  - [{signal.type}] {signal.severity}: {signal.message}")
        logger.info(f"    -> {signal.recommendation}")

    logger.info("PASS: Critic agent works!\n")
    return True


async def test_reconciliation_service():
    """Test Cash Reconciliation service."""
    logger.info("=" * 50)
    logger.info("TEST: Reconciliation Service")
    logger.info("=" * 50)

    service = ReconciliationService()

    # Fetch transactions
    transactions = await service.fetch_bank_transactions()
    logger.info(f"Fetched {len(transactions)} bank transactions")
    for tx in transactions:
        logger.info(f"  - {tx.id}: ${tx.amount} ({tx.type}) - {tx.description[:50]}")

    # Fetch payments
    payments = await service.get_scheduled_payments()
    logger.info(f"Fetched {len(payments)} scheduled payments")
    for pay in payments:
        logger.info(f"  - {pay['payment_id']}: ${pay['amount']} - {pay['vendor_name']}")

    # Reconcile
    result = await service.reconcile(hours_back=24)
    logger.info(f"Matched: {len(result.matched)}")
    logger.info(f"Unmatched transactions: {len(result.unmatched_transactions)}")
    logger.info(f"Orphaned payments: {len(result.orphaned_payments)}")
    logger.info(f"Total matched: ${result.total_matched_amount}")

    logger.info("PASS: Reconciliation service works!\n")
    return True


async def main():
    """Run all integration tests."""
    logger.info("=" * 60)
    logger.info("INVOICIFY AI SERVICE - INTEGRATION TESTS")
    logger.info("=" * 60)
    logger.info(f"Settings: {get_settings().model_dump_json()}")
    logger.info("")

    results = {}

    try:
        results["ollama"] = await test_ollama_client()
    except Exception as e:
        logger.error(f"FAIL: Ollama client - {e}")
        import traceback
        traceback.print_exc()
        results["ollama"] = False

    try:
        results["neo4j"] = await test_neo4j_client()
    except Exception as e:
        logger.error(f"FAIL: Neo4j client - {e}")
        import traceback
        traceback.print_exc()
        results["neo4j"] = False

    try:
        results["trust_battery"] = await test_trust_battery_service()
    except Exception as e:
        logger.error(f"FAIL: Trust Battery - {e}")
        import traceback
        traceback.print_exc()
        results["trust_battery"] = False

    try:
        results["analyst"] = await test_analyst_agent()
    except Exception as e:
        logger.error(f"FAIL: Analyst agent - {e}")
        import traceback
        traceback.print_exc()
        results["analyst"] = False

    try:
        results["critic"] = await test_critic_agent()
    except Exception as e:
        logger.error(f"FAIL: Critic agent - {e}")
        import traceback
        traceback.print_exc()
        results["critic"] = False

    try:
        results["reconciliation"] = await test_reconciliation_service()
    except Exception as e:
        logger.error(f"FAIL: Reconciliation - {e}")
        import traceback
        traceback.print_exc()
        results["reconciliation"] = False

    # Summary
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    passed = sum(results.values())
    total = len(results)
    for name, success in results.items():
        status = "PASS" if success else "FAIL"
        logger.info(f"  {name}: {status}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
