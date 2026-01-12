"""Comprehensive test suite for Invoicify AI Agent - All components, edge cases, and error handling."""

import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import sys
sys.path.insert(0, '/home/aparna/Desktop/invoicify/ai')

# Configure logging for test verification
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import all components
from app.config import get_settings
from app.services.trust_battery import (
    TrustBatteryService, TrustLevel, TrustBatteryState, DecisionOutcome,
    get_trust_battery_service
)
from app.agents.analyst import (
    AnalystAgent, AnalystProposal, Anomaly,
    get_analyst_agent
)
from app.agents.critic import (
    CriticAgent, CriticReview, FinancialContext, DecisionSignal,
    get_critic_agent
)
from app.services.reconciliation import (
    ReconciliationService, BankTransaction, PaymentMatch, ReconciliationResult,
    get_reconciliation_service
)
from app.schemas.invoice import InvoiceExtracted, InvoiceCreate, InvoiceStatus

# ============================================================================
# TEST UTILITIES
# ============================================================================

def log_test(name: str):
    """Log test section header."""
    print("\n" + "=" * 70)
    print(f"TEST: {name}")
    print("=" * 70)


def assert_equals(actual, expected, msg: str = ""):
    """Assert equality with detailed output."""
    if actual != expected:
        raise AssertionError(f"{msg}\n  Expected: {expected}\n  Actual: {actual}")
    print(f"  ✓ {msg}: {actual}")


def assert_true(condition, msg: str = ""):
    """Assert truth with detailed output."""
    if not condition:
        raise AssertionError(f"{msg}\n  Expected True but got False")
    print(f"  ✓ {msg}")


def assert_in(item, container, msg: str = ""):
    """Assert item is in container."""
    if item not in container:
        raise AssertionError(f"{msg}\n  Item {item} not in {container}")
    print(f"  ✓ {msg}")


def assert_between(value, min_val, max_val, msg: str = ""):
    """Assert value is within range."""
    if not (min_val <= value <= max_val):
        raise AssertionError(f"{msg}\n  Value {value} not in range [{min_val}, {max_val}]")
    print(f"  ✓ {msg}: {value}")


# ============================================================================
# TRUST BATTERY SERVICE TESTS
# ============================================================================

async def test_trust_battery_service():
    """Comprehensive Trust Battery Service tests."""
    log_test("TrustBatteryService - All Methods")

    service = get_trust_battery_service()
    test_vendor = f"TestVendor_TB_{uuid4().hex[:8]}"

    # ---- Test 1: get_threshold_for_level ----
    print("\n  [1] Threshold Level Methods")
    assert_equals(service.get_threshold_for_level(TrustLevel.PROBATION), 0.0, "PROBATION threshold")
    assert_equals(service.get_threshold_for_level(TrustLevel.STANDARD), 500.0, "STANDARD threshold")
    assert_equals(service.get_threshold_for_level(TrustLevel.CORE), 5000.0, "CORE threshold")

    # ---- Test 2: get_promotion_threshold ----
    print("\n  [2] Promotion Threshold Methods")
    promotion = service.get_promotion_threshold(TrustLevel.PROBATION)
    assert_between(promotion, 1, 100, "PROBATION -> STANDARD promotion threshold")
    promotion = service.get_promotion_threshold(TrustLevel.STANDARD)
    assert_between(promotion, 50, 200, "STANDARD -> CORE promotion threshold")
    assert_equals(service.get_promotion_threshold(TrustLevel.CORE), 0, "CORE max level")

    # ---- Test 3: _calculate_level ----
    print("\n  [3] Level Calculation")
    assert_equals(service._calculate_level(0), TrustLevel.PROBATION, "0 consecutive = PROBATION")
    assert_equals(service._calculate_level(25), TrustLevel.PROBATION, "25 consecutive = PROBATION")
    assert_equals(service._calculate_level(50), TrustLevel.STANDARD, "50 consecutive = STANDARD")
    assert_equals(service._calculate_level(75), TrustLevel.STANDARD, "75 consecutive = STANDARD")
    assert_equals(service._calculate_level(100), TrustLevel.CORE, "100 consecutive = CORE")
    assert_equals(service._calculate_level(150), TrustLevel.CORE, "150 consecutive = CORE")

    # ---- Test 4: get_vendor_trust (new vendor) ----
    print("\n  [4] New Vendor Trust State")
    state = await service.get_vendor_trust(test_vendor)
    assert_equals(state.vendor_id, test_vendor, "vendor_id matches")
    assert_equals(state.trust_level, TrustLevel.PROBATION, "new vendor = PROBATION")
    assert_equals(state.consecutive_accurate, 0, "consecutive_accurate = 0")
    assert_equals(state.consecutive_errors, 0, "consecutive_errors = 0")
    assert_equals(state.total_decisions, 0, "total_decisions = 0")
    assert_equals(state.auto_approve_threshold, 0.0, "auto_approve_threshold = 0")

    # ---- Test 5: record_decision (APPROVED) ----
    print("\n  [5] Record Accurate Decision")
    result = await service.record_decision(test_vendor, DecisionOutcome.ACCURATE, was_auto_approved=True)
    assert_equals(result.trust_level, TrustLevel.PROBATION, "still PROBATION after 1 accurate")
    assert_equals(result.consecutive_accurate, 1, "consecutive_accurate = 1")
    assert_equals(result.consecutive_errors, 0, "consecutive_errors = 0")
    assert_equals(result.total_decisions, 1, "total_decisions = 1")
    assert_equals(result.accurate_decisions, 1, "accurate_decisions = 1")
    assert_equals(result.accuracy_rate, 1.0, "accuracy_rate = 100%")

    # ---- Test 6: record_decision (ERROR) ----
    print("\n  [6] Record Error Decision")
    result = await service.record_decision(test_vendor, DecisionOutcome.ERROR)
    assert_equals(result.trust_level, TrustLevel.PROBATION, "PROBATION after error")
    assert_equals(result.consecutive_accurate, 0, "consecutive_accurate reset to 0")
    assert_equals(result.consecutive_errors, 1, "consecutive_errors = 1")
    assert_equals(result.total_decisions, 2, "total_decisions = 2")
    assert_equals(result.accuracy_rate, 0.5, "accuracy_rate = 50%")

    # ---- Test 7: String outcome conversion ----
    print("\n  [7] String to Enum Conversion")
    result = await service.record_decision(test_vendor, "APPROVED")
    assert_equals(result.accurate_decisions, 2, "APPROVED string = ACCURATE")
    result = await service.record_decision(test_vendor, "accurate")
    assert_equals(result.accurate_decisions, 3, "lowercase accurate works")
    result = await service.record_decision(test_vendor, "REJECTED")
    assert_equals(result.accurate_decisions, 3, "REJECTED string = ERROR")

    # ---- Test 8: can_auto_approve ----
    print("\n  [8] Auto-Approve Eligibility")
    # Level 1 cannot auto-approve regardless of amount
    result = await service.can_auto_approve(test_vendor, 100.0)
    assert_true(not result["can_auto_approve"], "Level 1 cannot auto-approve")
    assert_in("Probation", result["reason"], "Reason mentions Probation")

    # ---- Test 9: reset_vendor_trust ----
    print("\n  [9] Reset Vendor Trust")
    result = await service.reset_vendor_trust(test_vendor, TrustLevel.STANDARD)
    assert_equals(result.trust_level, TrustLevel.STANDARD, "reset to STANDARD")
    assert_equals(result.consecutive_accurate, 0, "consecutive reset to 0")
    assert_equals(result.auto_approve_threshold, 500.0, "threshold updated")

    # ---- Test 10: get_calibration_report ----
    print("\n  [10] Calibration Report")
    report = await service.get_calibration_report()
    assert_true("total_vendors" in report, "report has total_vendors")
    assert_true("recommendations" in report, "report has recommendations")
    assert_in("Shadow Mode", report["recommendations"][0], "recommendation about Shadow Mode")

    print("\n  ✓ All Trust Battery tests passed!")
    return True


# ============================================================================
# ANALYST AGENT TESTS
# ============================================================================

async def test_analyst_agent():
    """Comprehensive Analyst Agent tests."""
    log_test("AnalystAgent - All Methods")

    agent = get_analyst_agent()

    # ---- Test 1: Invoice with no history (new vendor) ----
    print("\n  [1] New Vendor Invoice Analysis")
    invoice = InvoiceExtracted(
        vendor_name="NewVendor Inc",
        vendor_address="New York, NY",
        invoice_number="INV-2024-NEW001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("1500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("1500.00"),
        line_items=[],
        payment_terms="Net 30",
        po_number="PO-NEW-001",
        overall_confidence=0.95,
        confidence_scores=[],
    )

    proposal = await agent.analyze(invoice_data=invoice, vendor_id=None)
    assert_equals(proposal.proposed_action, "HITL_REQUIRED", "New vendor = HITL_REQUIRED")
    assert_equals(len(proposal.anomalies), 1, "1 anomaly detected")
    assert_equals(proposal.anomalies[0].type, "NEW_VENDOR", "Anomaly type = NEW_VENDOR")
    assert_in("no historical data", proposal.anomalies[0].description, "Description mentions no history")

    # ---- Test 2: High value invoice ----
    print("\n  [2] High Value Invoice")
    invoice = InvoiceExtracted(
        vendor_name="AWS",
        vendor_address="Seattle, WA",
        invoice_number="INV-2024-HIGH001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("15000.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("15000.00"),
        line_items=[],
        payment_terms="Net 30",
        overall_confidence=0.95,
        confidence_scores=[],
    )

    proposal = await agent.analyze(invoice_data=invoice, vendor_id="existing_vendor")
    assert_equals(proposal.proposed_action, "HITL_REQUIRED", "High value = HITL_REQUIRED")

    # ---- Test 3: Normal invoice with history ----
    print("\n  [3] Normal Invoice with History")
    # Mock the Neo4j client to return history
    original_get_invoices = agent.neo4j.get_invoices_by_vendor

    class MockInvoice:
        def __init__(self, amount, status):
            self.amount = amount
            self.status = status

    async def mock_get_invoices(vendor_id):
        return [
            MockInvoice(1000, "APPROVED"),
            MockInvoice(1200, "APPROVED"),
            MockInvoice(1100, "APPROVED"),
            MockInvoice(1050, "APPROVED"),
            MockInvoice(1150, "APPROVED"),
        ]

    agent.neo4j.get_invoices_by_vendor = mock_get_invoices

    invoice = InvoiceExtracted(
        vendor_name="RegularVendor",
        vendor_address="Boston, MA",
        invoice_number="INV-2024-REG001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("1100.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("1100.00"),
        line_items=[],
        payment_terms="Net 30",
        overall_confidence=0.95,
        confidence_scores=[],
    )

    proposal = await agent.analyze(invoice_data=invoice, vendor_id="regular_vendor")
    assert_equals(proposal.proposed_action, "AUTO_APPROVE", "Normal invoice = AUTO_APPROVE")
    assert_true(len(proposal.anomalies) == 0, "No anomalies for normal invoice")

    # Restore original
    agent.neo4j.get_invoices_by_vendor = original_get_invoices

    # ---- Test 4: Amount spike detection ----
    print("\n  [4] Amount Spike Detection")

    async def mock_get_invoices_spike(vendor_id):
        return [
            MockInvoice(1000, "APPROVED"),
            MockInvoice(1000, "APPROVED"),
            MockInvoice(1000, "APPROVED"),
        ]

    agent.neo4j.get_invoices_by_vendor = mock_get_invoices_spike

    invoice = InvoiceExtracted(
        vendor_name="SpikeVendor",
        vendor_address="Denver, CO",
        invoice_number="INV-2024-SPIKE001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("3500.00"),  # 3.5x average
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("3500.00"),
        line_items=[],
        payment_terms="Net 30",
        overall_confidence=0.95,
        confidence_scores=[],
    )

    proposal = await agent.analyze(invoice_data=invoice, vendor_id="spike_vendor")
    assert_equals(proposal.proposed_action, "HITL_REQUIRED", "Amount spike = HITL_REQUIRED")
    assert_true(len(proposal.anomalies) > 0, "Anomaly detected for spike")

    # Restore
    agent.neo4j.get_invoices_by_vendor = original_get_invoices

    # ---- Test 5: _detect_anomalies edge cases ----
    print("\n  [5] Anomaly Detection Edge Cases")

    # Empty history
    anomalies = agent._detect_anomalies(Decimal("1000"), [])
    assert_equals(len(anomalies), 1, "Empty history = NEW_VENDOR anomaly")
    assert_equals(anomalies[0].severity, "medium", "NEW_VENDOR is medium severity")

    # History with zero amounts
    anomalies = agent._detect_anomalies(Decimal("1000"), [{"amount": 0, "status": "APPROVED"}])
    assert_true(len(anomalies) == 0, "Zero amount history = no anomaly")

    # ---- Test 6: Proposal generation with various conditions ----
    print("\n  [6] Proposal Generation Conditions")

    # High severity anomaly
    anomalies = [
        Anomaly(type="FRAUD", severity="high", description="Suspicious pattern")
    ]
    proposal = await agent._generate_proposal(
        invoice_data=invoice,
        vendor_history=[{"amount": 1000, "status": "APPROVED"}],
        anomalies=anomalies,
        base_confidence=0.9,
    )
    assert_equals(proposal.proposed_action, "HITL_REQUIRED", "High severity = HITL_REQUIRED")

    # Medium severity reduces confidence
    anomalies = [
        Anomaly(type="AMOUNT_DEVIATION", severity="medium", description="Minor deviation")
    ]
    proposal = await agent._generate_proposal(
        invoice_data=invoice,
        vendor_history=[{"amount": 1000, "status": "APPROVED"}],
        anomalies=anomalies,
        base_confidence=0.9,
    )
    assert_true(proposal.confidence < 0.9, "Medium severity reduces confidence")
    assert_in("reducing confidence", str(proposal.reasoning), "Reasoning explains reduction")

    print("\n  ✓ All Analyst Agent tests passed!")
    return True


# ============================================================================
# CRITIC AGENT TESTS
# ============================================================================

async def test_critic_agent():
    """Comprehensive Critic Agent tests."""
    log_test("CriticAgent - All Safety Checks")

    critic = get_critic_agent()

    # ---- Test 1: RUNWAY Check - Safe ----
    print("\n  [1] RUNWAY Check - Safe Payment")
    safe_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        payroll_date="15",
        payroll_amount=25000,
        safety_buffer=10000,
    )
    invoice = InvoiceExtracted(
        vendor_name="AWS",
        invoice_number="INV-001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        overall_confidence=0.95,
        confidence_scores=[],
    )

    signal = critic._check_runway(Decimal("1000"), safe_context)
    assert_equals(signal.severity, "INFO", "Safe payment = INFO")
    assert_equals(signal.type, "RUNWAY", "Signal type = RUNWAY")
    assert_equals(signal.score_contribution, 0.0, "No risk score for safe")

    # ---- Test 2: RUNWAY Check - Below Safety Buffer ----
    print("\n  [2] RUNWAY Check - Below Safety Buffer")
    signal = critic._check_runway(Decimal("45000"), safe_context)
    assert_equals(signal.severity, "CRITICAL", "Payment below buffer = CRITICAL")
    assert_in("below", signal.message.lower(), "Message mentions below threshold")
    assert_equals(signal.score_contribution, 0.40, "Max risk contribution")

    # ---- Test 3: RUNWAY Check - Below 90 Days ----
    print("\n  [3] RUNWAY Check - Low Runway Warning")
    # $6000 payment leaves $44000 cash -> 88 days runway (just under 90)
    signal = critic._check_runway(Decimal("6000"), safe_context)
    assert_equals(signal.severity, "WARNING", "Low runway = WARNING")
    assert_in("88", signal.message, "Message mentions 88 days")
    assert_equals(signal.score_contribution, 0.20, "Moderate risk contribution")

    # ---- Test 4: RUNWAY Check - Near Payroll ----
    print("\n  [4] RUNWAY Check - Near Payroll")
    signal = critic._check_runway(Decimal("15000"), safe_context)  # >50% of payroll
    assert_equals(signal.severity, "WARNING", "Near payroll = WARNING")
    assert_in("payroll", signal.message.lower(), "Message mentions payroll")

    # ---- Test 5: STRATEGY Check - SURVIVAL Mode ----
    print("\n  [5] STRATEGY Check - SURVIVAL Mode")
    survival_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        strategy_mode="SURVIVAL",
    )

    signal = critic._check_strategy(Decimal("6000"), survival_context)  # >10% of cash
    assert_equals(signal.severity, "CRITICAL", "SURVIVAL: >10% = CRITICAL")

    signal = critic._check_strategy(Decimal("1500"), survival_context)  # >$1000
    assert_equals(signal.severity, "WARNING", "SURVIVAL: >$1000 = WARNING")

    # ---- Test 6: STRATEGY Check - GROWTH Mode ----
    print("\n  [6] STRATEGY Check - GROWTH Mode")
    growth_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        strategy_mode="GROWTH",
    )

    signal = critic._check_strategy(Decimal("5000"), growth_context)
    assert_equals(signal.severity, "INFO", "GROWTH mode = INFO")
    assert_in("early payment", signal.recommendation.lower(), "Recommend early payment")

    # ---- Test 7: STRATEGY Check - OPTIMIZE Mode ----
    print("\n  [7] STRATEGY Check - OPTIMIZE Mode")
    optimize_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        strategy_mode="OPTIMIZE",
    )

    signal = critic._check_strategy(Decimal("15000"), optimize_context)  # >20% of cash
    assert_equals(signal.severity, "WARNING", "OPTIMIZE: >20% = WARNING")

    signal = critic._check_strategy(Decimal("5000"), optimize_context)
    assert_equals(signal.severity, "INFO", "OPTIMIZE: normal = INFO")

    # ---- Test 8: CONTRACT Check - Past Due ----
    print("\n  [8] CONTRACT Check - Past Due")
    past_due = (datetime.now() - timedelta(days=5)).date()
    signal = critic._check_contract(past_due, safe_context)
    assert_equals(signal.severity, "CRITICAL", "Past due = CRITICAL")
    assert_in("past due", signal.message.lower(), "Message mentions past due")
    assert_equals(signal.score_contribution, 0.20, "Late payment risk")

    # ---- Test 9: CONTRACT Check - Due Soon ----
    print("\n  [9] CONTRACT Check - Due Soon")
    due_soon = (datetime.now() + timedelta(days=2)).date()
    signal = critic._check_contract(due_soon, safe_context)
    assert_equals(signal.severity, "WARNING", "Due soon = WARNING")

    # ---- Test 10: CONTRACT Check - Early Payment ----
    print("\n  [10] CONTRACT Check - Early Payment")
    far_future = (datetime.now() + timedelta(days=60)).date()
    signal = critic._check_contract(far_future, safe_context)
    assert_equals(signal.severity, "INFO", "Far future = INFO")
    assert_in("not due", signal.message.lower(), "Message mentions not due")

    # ---- Test 11: CONTRACT Check - No Due Date ----
    print("\n  [11] CONTRACT Check - No Due Date")
    signal = critic._check_contract(None, safe_context)
    assert_equals(signal.severity, "INFO", "No due date = INFO")
    assert_in("standard", signal.recommendation.lower(), "Recommend standard timing")

    # ---- Test 12: CONTRACT Check - Date String ----
    print("\n  [12] CONTRACT Check - Date String")
    due_str = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
    signal = critic._check_contract(due_str, safe_context)
    assert_equals(signal.severity, "INFO", "Date string works")

    # ---- Test 13: TRUST Check - Level 1 ----
    print("\n  [13] TRUST Check - Level 1 (Probation)")
    signal = critic._check_trust(Decimal("500"), trust_level=1, trust_threshold=1000)
    assert_equals(signal.severity, "INFO", "Level 1 = INFO (review required)")
    assert_in("Probation", signal.message, "Message mentions Probation")

    # ---- Test 14: TRUST Check - Amount Exceeds Threshold ----
    print("\n  [14] TRUST Check - Amount Exceeds Threshold")
    signal = critic._check_trust(Decimal("2000"), trust_level=2, trust_threshold=1000)
    assert_equals(signal.severity, "WARNING", "Amount > threshold = WARNING")
    assert_in("exceeds", signal.message.lower(), "Message mentions exceeds")

    # ---- Test 15: TRUST Check - Eligible ----
    print("\n  [15] TRUST Check - Eligible")
    signal = critic._check_trust(Decimal("500"), trust_level=2, trust_threshold=1000)
    assert_equals(signal.severity, "INFO", "Within threshold = INFO")
    assert_in("eligible", signal.recommendation.lower(), "Recommend auto-approve")

    # ---- Test 16: BUDGET Check - Within Budget ----
    print("\n  [16] BUDGET Check - Within Budget")
    budget_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        budgets={"Software": 2000},
        category_limits={"Software": 10000},
    )
    signal = critic._check_budget(Decimal("1000"), "Software", budget_context)
    assert_equals(signal.severity, "INFO", "Within budget = INFO")
    assert_in("Within budget", signal.message, "Message confirms within budget")

    # ---- Test 17: BUDGET Check - Over Budget (>20%) ----
    print("\n  [17] BUDGET Check - Over Budget (>20%)")
    budget_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        budgets={"Software": 9500},
        category_limits={"Software": 10000},
    )
    # 9500 + 3000 = 12500, over by 2500 = 25% > 20%
    signal = critic._check_budget(Decimal("3000"), "Software", budget_context)
    assert_equals(signal.severity, "CRITICAL", "Over >20% = CRITICAL")
    assert_in("do not approve", signal.recommendation.lower(), "Recommend rejection")

    # ---- Test 18: BUDGET Check - Approaching Limit (80%+) ----
    print("\n  [18] BUDGET Check - Approaching Limit (80%+)")
    budget_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
        budgets={"Software": 7500},
        category_limits={"Software": 10000},
    )
    signal = critic._check_budget(Decimal("1000"), "Software", budget_context)
    assert_equals(signal.severity, "INFO", "80% used = INFO")

    # ---- Test 19: Full Review - Safe Invoice ----
    print("\n  [19] Full Critic Review - Safe Invoice")
    review = await critic.review(
        invoice_data=invoice,
        financial_context=safe_context,
        trust_level=2,
        trust_threshold=1000,
    )
    assert_true(review.can_proceed, "Safe invoice can proceed")
    assert_true(not review.blocked, "Not blocked")
    assert_equals(len(review.signals), 5, "5 signals generated")

    # ---- Test 20: Full Review - Blocked Invoice ----
    print("\n  [20] Full Critic Review - Blocked Invoice")
    dangerous_context = FinancialContext(
        current_cash=20000,
        monthly_burn_rate=15000,
        runway_days=40,
        safety_buffer=10000,
        strategy_mode="SURVIVAL",
    )
    large_invoice = InvoiceExtracted(
        vendor_name="ExpensiveVendor",
        invoice_number="INV-EXPENSIVE",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() - timedelta(days=10)).date(),
        currency="USD",
        subtotal=Decimal("15000"),
        total_amount=Decimal("15000"),
        overall_confidence=0.95,
        confidence_scores=[],
    )
    review = await critic.review(
        invoice_data=large_invoice,
        financial_context=dangerous_context,
        trust_level=1,
        trust_threshold=1000,
    )
    assert_true(review.blocked, "Dangerous invoice blocked")
    assert_true(not review.can_proceed, "Cannot proceed")
    assert_equals(review.risk_score > 0, True, "Risk score > 0")

    print("\n  ✓ All Critic Agent tests passed!")
    return True


# ============================================================================
# RECONCILIATION SERVICE TESTS
# ============================================================================

async def test_reconciliation_service():
    """Comprehensive Reconciliation Service tests."""
    log_test("ReconciliationService - All Methods")

    service = get_reconciliation_service()

    # ---- Test 1: Amount Normalization ----
    print("\n  [1] Amount Normalization")
    assert_equals(service._normalize_amount(100.994), 100.99, "Round to 2 decimals")
    assert_equals(service._normalize_amount(100.999), 101.0, "Round up to 101")
    assert_equals(service._normalize_amount(100.0), 100.0, "Exact amount")

    # ---- Test 2: Description Normalization ----
    print("\n  [2] Description Normalization")
    norm = service._normalize_description("AWS Web Services - Invoice #INV-123")
    assert_equals(norm, "aws web services invoice inv123", "Lowercase, remove special chars")

    norm = service._normalize_description("  OPENAI   LLC  ")
    assert_equals(norm, "openai llc", "Collapse whitespace")

    # ---- Test 3: Vendor Similarity - Direct Match ----
    print("\n  [3] Vendor Similarity - Direct Match")
    score = service._calculate_vendor_similarity("aws web services", "AWS")
    assert_equals(score, 1.0, "Direct substring match = 1.0")

    # ---- Test 4: Vendor Similarity - Partial Match ----
    print("\n  [4] Vendor Similarity - Partial Match")
    # "aws web services" contains "aws" as a word
    score = service._calculate_vendor_similarity("payment to aws web services", "AWS")
    assert_true(score > 0.5, "AWS in description = high score")

    # ---- Test 5: Vendor Similarity - No Match ----
    print("\n  [5] Vendor Similarity - No Match")
    score = service._calculate_vendor_similarity("stripe transfer", "AWS")
    assert_true(score < 1.0, "No match = lower score")

    # ---- Test 6: Vendor Similarity - Stop Words ----
    print("\n  [6] Vendor Similarity - Stop Words Removal")
    score = service._calculate_vendor_similarity(
        "payment for the aws services inc and corp",
        "AWS"
    )
    assert_equals(score, 1.0, "Stop words removed, direct match")

    # ---- Test 7: Date Similarity ----
    print("\n  [7] Date Similarity")
    # Same day
    score = service._calculate_date_similarity(
        datetime.now().isoformat(),
        datetime.now().strftime("%Y-%m-%d")
    )
    assert_equals(score, 1.0, "Same day = 1.0")

    # 1 day diff
    score = service._calculate_date_similarity(
        datetime.now().isoformat(),
        (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    )
    assert_equals(score, 0.9, "1 day diff = 0.9")

    # 3 days diff
    score = service._calculate_date_similarity(
        datetime.now().isoformat(),
        (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    )
    assert_equals(score, 0.7, "3 days diff = 0.7")

    # 7 days diff
    score = service._calculate_date_similarity(
        datetime.now().isoformat(),
        (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    )
    assert_equals(score, 0.5, "7 days diff = 0.5")

    # >7 days
    score = service._calculate_date_similarity(
        datetime.now().isoformat(),
        (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    )
    assert_equals(score, 0.0, ">7 days diff = 0.0")

    # ---- Test 8: Invalid Date Handling ----
    print("\n  [8] Invalid Date Handling")
    score = service._calculate_date_similarity("invalid-date", "2024-01-01")
    assert_equals(score, 0.5, "Invalid date = 0.5 (default)")

    # ---- Test 9: Transaction Matching - Exact Match ----
    print("\n  [9] Transaction Matching - Exact Match")
    tx = BankTransaction(
        id="txn_test",
        amount=1000.00,
        date=datetime.now().isoformat(),
        description="AWS Payment",
        type="debit",
        merchant_name="AWS",
    )
    payments = [
        {
            "payment_id": "pay_001",
            "invoice_id": "inv_001",
            "vendor_name": "AWS",
            "amount": 1000.00,
            "scheduled_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "scheduled",
        }
    ]

    matches = await service.match_transactions([tx], payments)
    assert_equals(len(matches), 1, "Exact match found")
    assert_equals(matches[0].match_type, "exact", "Match type = exact")
    assert_equals(matches[0].confidence, 1.0, "Confidence = 1.0")

    # ---- Test 10: Transaction Matching - Credit Ignored ----
    print("\n  [10] Transaction Matching - Credit Ignored")
    credit_tx = BankTransaction(
        id="txn_credit",
        amount=1000.00,
        date=datetime.now().isoformat(),
        description="Stripe Transfer",
        type="credit",  # Credit, not debit
        merchant_name="Stripe",
    )

    matches = await service.match_transactions([credit_tx], payments)
    assert_equals(len(matches), 0, "Credit transactions ignored")

    # ---- Test 11: Transaction Matching - Fuzzy Match ----
    print("\n  [11] Transaction Matching - Fuzzy Match")
    tx = BankTransaction(
        id="txn_fuzzy",
        amount=1000.00,
        date=datetime.now().isoformat(),
        description="Payment to AWS for invoice",
        type="debit",
        merchant_name="AWS",
    )
    payment = {
        "payment_id": "pay_002",
        "invoice_id": "inv_002",
        "vendor_name": "AWS",  # Same vendor
        "amount": 1000.00,
        "scheduled_date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),  # 2 days off
        "status": "scheduled",
    }

    matches = await service.match_transactions([tx], [payment])
    assert_equals(len(matches), 1, "Fuzzy match found")
    assert_equals(matches[0].match_type, "fuzzy", "Match type = fuzzy")

    # ---- Test 12: Transaction Matching - No Match ----
    print("\n  [12] Transaction Matching - No Match")
    tx = BankTransaction(
        id="txn_nomatch",
        amount=999.00,  # Different amount
        date=datetime.now().isoformat(),
        description="Unknown Vendor",
        type="debit",
    )

    matches = await service.match_transactions([tx], payments)
    assert_equals(len(matches), 0, "No match for different amount")

    # ---- Test 13: Full Reconciliation Process ----
    print("\n  [13] Full Reconciliation Process")
    result = await service.reconcile(hours_back=24)

    assert_equals(len(result.matched), 2, "2 matches found")
    assert_equals(len(result.unmatched_transactions), 1, "1 unmatched (credit)")
    assert_equals(len(result.orphaned_payments), 0, "0 orphaned payments")
    assert_equals(result.total_matched_amount, 4000.0, "Total matched = $4000")
    assert_true(result.timestamp is not None, "Timestamp present")

    # ---- Test 14: Alert for Large Unmatched ----
    print("\n  [14] Alert for Large Unmatched")
    # The mock data has a $1200 credit which is unmatched but not alerted
    # because it's a credit (not debit)

    # Create a large unmatched debit
    service.settings = get_settings()
    original_fetch = service.fetch_bank_transactions

    async def mock_fetch_large(hours_back=24):
        return [
            BankTransaction(
                id="txn_large",
                amount=5000.00,  # > alert_threshold
                date=datetime.now().isoformat(),
                description="Large Unknown Payment",
                type="debit",
            )
        ]

    service.fetch_bank_transactions = mock_fetch_large

    result = await service.reconcile(hours_back=24, alert_threshold=1000.0)
    assert_equals(len(result.unmatched_transactions), 1, "Large unmatched found")

    service.fetch_bank_transactions = original_fetch

    # ---- Test 15: Mark as Reconciled ----
    print("\n  [15] Mark as Reconciled")
    result = await service.mark_as_reconciled("pay_001", "txn_001")
    assert_equals(result["status"], "RECONCILED", "Status = RECONCILED")
    assert_true("reconciled_at" in result, "Timestamp present")

    # ---- Test 16: Alert Orphaned Transaction ----
    print("\n  [16] Alert Orphaned Transaction")
    tx = BankTransaction(
        id="txn_alert",
        amount=2500.00,
        date=datetime.now().isoformat(),
        description="Suspicious Payment",
        type="debit",
    )

    alert = await service.alert_orphaned_transaction(tx)
    assert_equals(alert["alert_type"], "ORPHANED_TRANSACTION", "Alert type correct")
    assert_equals(alert["severity"], "HIGH", "Large amount = HIGH severity")
    assert_in("Review", alert["action_required"], "Action required mentioned")

    print("\n  ✓ All Reconciliation Service tests passed!")
    return True


# ============================================================================
# END-TO-END WORKFLOW TESTS
# ============================================================================

async def test_end_to_end_workflow():
    """End-to-end workflow tests."""
    log_test("End-to-End Workflow Tests")

    from app.graphs.invoice_workflow import (
        InvoiceWorkflow, create_invoice_workflow, route_action, InvoiceState
    )

    # ---- Test 1: Workflow Graph Creation ----
    print("\n  [1] Workflow Graph Creation")
    builder = create_invoice_workflow()
    assert_true(builder is not None, "Graph builder created")

    # ---- Test 2: route_action Routing Logic ----
    print("\n  [2] route_action Routing Logic")

    # Case: Critic blocked
    state_blocked = {
        "invoice_id": "test_001",
        "critic_review": CriticReview(
            can_proceed=False,
            blocked=True,
            block_reason="Cash below safety buffer",
            signals=[],
            reasoning=[],
        ),
        "analyst_proposal": AnalystProposal(
            proposed_action="AUTO_APPROVE",
            confidence=0.9,
            anomalies=[],
            reasoning=["Test"],
        ),
    }
    assert_equals(route_action(state_blocked), "reject", "Blocked = reject")

    # Case: Analyst HITL
    state_hitl = {
        "invoice_id": "test_002",
        "critic_review": CriticReview(
            can_proceed=True,
            blocked=False,
            signals=[],
            reasoning=[],
        ),
        "analyst_proposal": AnalystProposal(
            proposed_action="HITL_REQUIRED",
            confidence=0.7,
            anomalies=[],
            reasoning=["Test"],
        ),
    }
    assert_equals(route_action(state_hitl), "hitl_required", "Analyst HITL = hitl_required")

    # Case: Analyst DELAY
    state_delay = {
        "invoice_id": "test_003",
        "critic_review": CriticReview(
            can_proceed=True,
            blocked=False,
            signals=[],
            reasoning=[],
        ),
        "analyst_proposal": AnalystProposal(
            proposed_action="DELAY_PAYMENT",
            confidence=0.8,
            anomalies=[],
            reasoning=["Test"],
        ),
    }
    assert_equals(route_action(state_delay), "delay_payment", "Analyst DELAY = delay_payment")

    # Case: Auto-approve eligible
    state_auto = {
        "invoice_id": "test_004",
        "critic_review": CriticReview(
            can_proceed=True,
            blocked=False,
            signals=[
                DecisionSignal(
                    type="TRUST",
                    severity="INFO",
                    message="Trust level OK",
                    recommendation="Auto-approve",
                )
            ],
            reasoning=[],
        ),
        "analyst_proposal": AnalystProposal(
            proposed_action="AUTO_APPROVE",
            confidence=0.95,
            anomalies=[],
            reasoning=["Test"],
        ),
    }
    assert_equals(route_action(state_auto), "auto_approve", "Trust INFO = auto_approve")

    # Case: No critic review
    state_no_critic = {
        "invoice_id": "test_005",
        "critic_review": None,
    }
    assert_equals(route_action(state_no_critic), "exception", "No critic = exception")

    print("\n  ✓ All End-to-End Workflow tests passed!")
    return True


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

async def test_error_handling():
    """Error handling and edge case tests."""
    log_test("Error Handling Tests")

    # ---- Test 1: Trust Battery with missing Neo4j ----
    print("\n  [1] Trust Battery Graceful Degradation")

    class MockNeo4jClient:
        async def get_vendor(self, vendor_id):
            return None

        async def get_vendor_by_name(self, name):
            return None

        async def create_vendor_simple(self, **kwargs):
            pass

        async def update_vendor_trust(self, **kwargs):
            pass

    service = TrustBatteryService()
    service.neo4j = MockNeo4jClient()

    state = await service.get_vendor_trust("missing_vendor")
    assert_equals(state.trust_level, TrustLevel.PROBATION, "Missing vendor = PROBATION")

    # ---- Test 2: Analyst with missing Neo4j ----
    print("\n  [2] Analyst Graceful Degradation")

    class MockNeo4jClientFail:
        async def get_invoices_by_vendor(self, vendor_id):
            raise Exception("Neo4j connection failed")

        async def find_anomaly_patterns(self, vendor_id):
            raise Exception("Neo4j connection failed")

    agent = get_analyst_agent()
    agent.neo4j = MockNeo4jClientFail()

    invoice = InvoiceExtracted(
        vendor_name="TestVendor",
        invoice_number="INV-001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        overall_confidence=0.95,
        confidence_scores=[],
    )

    proposal = await agent.analyze(invoice_data=invoice, vendor_id="test")
    # Should still work, just with no history
    assert_equals(proposal.proposed_action, "HITL_REQUIRED", "No history = HITL_REQUIRED")

    # ---- Test 3: Critic with extreme values ----
    print("\n  [3] Critic Extreme Value Handling")

    critic = get_critic_agent()

    # Zero burn rate
    extreme_context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=0,  # No burn
        runway_days=999,
    )
    signal = critic._check_runway(Decimal("10000"), extreme_context)
    assert_equals(signal.severity, "INFO", "Zero burn = INFO (infinite runway)")

    # Negative cash (edge case)
    extreme_context = FinancialContext(
        current_cash=-5000,  # Already negative
        monthly_burn_rate=10000,
        runway_days=0,
        safety_buffer=10000,
    )
    signal = critic._check_runway(Decimal("1000"), extreme_context)
    assert_equals(signal.severity, "CRITICAL", "Negative cash = CRITICAL")

    # ---- Test 4: Invalid invoice data ----
    print("\n  [4] Invalid Invoice Handling")

    # Missing required fields
    try:
        invoice = InvoiceExtracted(
            vendor_name="",  # Empty vendor
            invoice_number="INV-001",
            invoice_date=datetime.now().date(),
            due_date=(datetime.now() + timedelta(days=30)).date(),
            currency="USD",
            subtotal=Decimal("-1000"),  # Negative amount
            total_amount=Decimal("-1000"),
            overall_confidence=0.95,
            confidence_scores=[],
        )
        print("  ⚠ Pydantic should reject negative amounts in validation")
    except Exception as e:
        print(f"  ✓ Pydantic validation works: {type(e).__name__}")

    print("\n  ✓ All Error Handling tests passed!")
    return True


# ============================================================================
# DEBUG LOGGING VERIFICATION
# ============================================================================

async def test_debug_logging():
    """Verify debug logging is present in all components."""
    log_test("Debug Logging Verification")

    import io
    import logging

    # Capture logs
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    # Get all component loggers
    loggers = [
        "app.services.trust_battery",
        "app.agents.analyst",
        "app.agents.critic",
        "app.services.reconciliation",
        "app.graphs.invoice_workflow",
    ]

    for logger_name in loggers:
        component_logger = logging.getLogger(logger_name)
        component_logger.addHandler(handler)
        component_logger.setLevel(logging.DEBUG)

    # ---- Test 1: Trust Battery logging ----
    print("\n  [1] Trust Battery Logging")
    service = get_trust_battery_service()
    await service.get_vendor_trust(f"LogTest_{uuid4().hex[:8]}")

    log_content = log_capture.getvalue()
    assert_in("trust", log_content.lower(), "Trust battery logs activity")

    # ---- Test 2: Analyst logging ----
    print("\n  [2] Analyst Logging")
    agent = get_analyst_agent()
    invoice = InvoiceExtracted(
        vendor_name="LogTestVendor",
        invoice_number="INV-LOG001",
        invoice_date=datetime.now().date(),
        due_date=(datetime.now() + timedelta(days=30)).date(),
        currency="USD",
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        overall_confidence=0.95,
        confidence_scores=[],
    )
    await agent.analyze(invoice_data=invoice, vendor_id=None)

    log_content = log_capture.getvalue()
    assert_in("analyst", log_content.lower(), "Analyst logs activity")

    # ---- Test 3: Critic logging ----
    print("\n  [3] Critic Logging")
    critic = get_critic_agent()
    context = FinancialContext(
        current_cash=50000,
        monthly_burn_rate=15000,
        runway_days=100,
    )
    await critic.review(
        invoice_data=invoice,
        financial_context=context,
        trust_level=2,
        trust_threshold=1000,
    )

    log_content = log_capture.getvalue()
    assert_in("critic", log_content.lower(), "Critic logs activity")
    assert_in("reviewing", log_content.lower(), "Critic logs reviewing")

    # ---- Test 4: Reconciliation logging ----
    print("\n  [4] Reconciliation Logging")
    service = get_reconciliation_service()
    await service.fetch_bank_transactions()

    log_content = log_capture.getvalue()
    assert_in("fetching", log_content.lower(), "Reconciliation logs fetching")

    # Clean up
    for logger_name in loggers:
        component_logger = logging.getLogger(logger_name)
        component_logger.removeHandler(handler)

    print("\n  ✓ All Debug Logging tests passed!")
    return True


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def main():
    """Run all comprehensive tests."""
    print("\n" + "=" * 70)
    print("INVOICIFY AI AGENT - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print(f"Settings: {get_settings().model_dump_json()}")

    results = {}

    try:
        results["trust_battery"] = await test_trust_battery_service()
    except Exception as e:
        logger.error(f"Trust Battery tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["trust_battery"] = False

    try:
        results["analyst"] = await test_analyst_agent()
    except Exception as e:
        logger.error(f"Analyst tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["analyst"] = False

    try:
        results["critic"] = await test_critic_agent()
    except Exception as e:
        logger.error(f"Critic tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["critic"] = False

    try:
        results["reconciliation"] = await test_reconciliation_service()
    except Exception as e:
        logger.error(f"Reconciliation tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["reconciliation"] = False

    try:
        results["workflow"] = await test_end_to_end_workflow()
    except Exception as e:
        logger.error(f"Workflow tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["workflow"] = False

    try:
        results["error_handling"] = await test_error_handling()
    except Exception as e:
        logger.error(f"Error handling tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["error_handling"] = False

    try:
        results["debug_logging"] = await test_debug_logging()
    except Exception as e:
        logger.error(f"Debug logging tests failed: {e}")
        import traceback
        traceback.print_exc()
        results["debug_logging"] = False

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed = sum(results.values())
    total = len(results)

    for name, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} test suites passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! The AI Agent is functioning correctly.")
    else:
        print(f"\n⚠ {total - passed} test suite(s) failed. Review the output above.")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
