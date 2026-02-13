"""
Unit Tests for Domain Components
Tests for models, risk scorer, and trust battery.
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.domain.models import (
    InvoiceData,
    LineItem,
    RiskBreakdown,
    RiskScore,
    TrustBattery,
    TrustLevel,
    Decision,
    InvoiceStatus,
)
from src.domain.risk_scorer import InvoiceRiskScorer
from src.domain.trust_battery import TrustBatteryService


class TestInvoiceData:
    """Tests for InvoiceData model."""

    def test_invoice_data_creation(self):
        """Test creating InvoiceData with all fields."""
        invoice = InvoiceData(
            invoice_id="inv-001",
            vendor_id="vendor-001",
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            issue_date=datetime.utcnow(),
            due_date=datetime.utcnow(),
            total_amount=Decimal("1000.00"),
            currency="USD",
            line_items=[
                LineItem("Consulting", 10, Decimal("100.00"), Decimal("1000.00"))
            ],
        )

        assert invoice.invoice_id == "inv-001"
        assert invoice.vendor_name == "Acme Corp"
        assert invoice.total_amount == Decimal("1000.00")

    def test_invoice_data_to_dict(self):
        """Test InvoiceData serialization."""
        invoice = InvoiceData(
            invoice_id="inv-001",
            vendor_id="vendor-001",
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            issue_date=datetime(2024, 1, 1),
            due_date=datetime(2024, 1, 31),
            total_amount=Decimal("1000.00"),
            line_items=[],
        )

        data = invoice.to_dict()

        assert data["invoice_id"] == "inv-001"
        assert data["total_amount"] == "1000.00"
        assert "issue_date" in data


class TestRiskBreakdown:
    """Tests for RiskBreakdown calculations."""

    def test_overall_score_calculation(self):
        """Test overall score is weighted correctly."""
        breakdown = RiskBreakdown(
            amount_anomaly_score=0.8,  # 35% weight
            pattern_anomaly_score=0.2,  # 25% weight
            vendor_trust_penalty=0.1,  # 20% weight
            time_based_risk=0.0,  # 10% weight
            duplicate_risk=0.0,  # 10% weight
        )

        # Expected: (0.8*0.35) + (0.2*0.25) + (0.1*0.20) + 0 + 0
        # = 0.28 + 0.05 + 0.02 = 0.35
        expected = 0.35
        assert abs(breakdown.overall_score - expected) < 0.01

    def test_overall_score_capped_at_1(self):
        """Test overall score is capped at 1.0."""
        breakdown = RiskBreakdown(
            amount_anomaly_score=2.0,  # Would be 0.7 without cap
            pattern_anomaly_score=2.0,
            vendor_trust_penalty=2.0,
            time_based_risk=2.0,
            duplicate_risk=2.0,
        )

        assert breakdown.overall_score == 1.0


class TestRiskScorer:
    """Tests for InvoiceRiskScorer."""

    @pytest.fixture
    def scorer(self):
        """Create risk scorer instance."""
        return InvoiceRiskScorer()

    @pytest.fixture
    def sample_invoice(self):
        """Create sample invoice."""
        return InvoiceData(
            invoice_id="inv-001",
            vendor_id="vendor-001",
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            issue_date=datetime.utcnow(),
            due_date=datetime.utcnow(),
            total_amount=Decimal("1000.00"),
            line_items=[],
        )

    def test_new_vendor_high_penalty(self, scorer, sample_invoice):
        """Test new vendor gets high trust penalty."""
        trust_battery = TrustBattery(
            vendor_id="vendor-001",
            level=TrustLevel.NEW,
        )

        score = scorer.score_invoice(sample_invoice, trust_battery)

        assert score.breakdown.vendor_trust_penalty >= 0.7
        assert any("new" in reason.lower() for reason in score.reasons)

    def test_amount_anomaly_detection(self, scorer, sample_invoice):
        """Test amount anomaly detection."""
        # First, learn some normal amounts
        for _ in range(5):
            scorer.learn_from_payment(sample_invoice, was_successful=True)

        # Now create an anomalous amount
        high_invoice = InvoiceData(
            invoice_id="inv-002",
            vendor_id="vendor-001",  # Same vendor
            vendor_name="Acme Corp",
            invoice_number="INV-002",
            issue_date=datetime.utcnow(),
            due_date=datetime.utcnow(),
            total_amount=Decimal("50000.00"),  # 50x normal
            line_items=[],
        )

        score = scorer.score_invoice(high_invoice)

        assert score.breakdown.amount_anomaly_score > 0.5
        assert score.overall_score > 0.3

    def test_low_risk_auto_approve(self, scorer, sample_invoice):
        """Test low-risk invoice gets APPROVE recommendation."""
        # Trusted vendor
        trust_battery = TrustBattery(
            vendor_id="vendor-001",
            level=TrustLevel.VERIFIED,
            successful_payments=30,
        )

        score = scorer.score_invoice(sample_invoice, trust_battery)

        assert score.overall_score < 0.3
        assert score.recommended_action == Decision.APPROVE

    def test_high_risk_reject(self, scorer):
        """Test high-risk invoice gets REJECT recommendation."""
        # Create suspicious invoice
        suspicious = InvoiceData(
            invoice_id="inv-003",
            vendor_id="vendor-unknown",
            vendor_name="Unknown Vendor",
            invoice_number="INV-003",
            issue_date=datetime.utcnow(),
            due_date=datetime.utcnow(),
            total_amount=Decimal("100000.00"),  # Very high
            line_items=[],
        )

        score = scorer.score_invoice(suspicious, None)

        assert score.overall_score > 0.6
        assert score.recommended_action == Decision.REJECT


class TestTrustBattery:
    """Tests for TrustBattery model."""

    def test_trust_battery_creation(self):
        """Test creating new trust battery."""
        battery = TrustBattery(vendor_id="vendor-001")

        assert battery.vendor_id == "vendor-001"
        assert battery.level == TrustLevel.NEW
        assert battery.successful_payments == 0

    def test_trust_battery_to_dict(self):
        """Test TrustBattery serialization."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            level=TrustLevel.TRUSTED,
            successful_payments=15,
            total_amount_paid=Decimal("25000.00"),
        )

        data = battery.to_dict()

        assert data["vendor_id"] == "vendor-001"
        assert data["level"] == 4  # TRUSTED value
        assert data["level_name"] == "TRUSTED"
        assert data["successful_payments"] == 15


class TestTrustBatteryService:
    """Tests for TrustBatteryService."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database adapter."""
        from unittest.mock import AsyncMock, Mock

        mock = AsyncMock()
        mock.get_vendor_history = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def service(self, mock_db):
        """Create trust battery service."""
        return TrustBatteryService(mock_db)

    @pytest.mark.asyncio
    async def test_get_vendor_trust_creates_new(self, service):
        """Test getting trust for new vendor creates battery."""
        battery = await service.get_vendor_trust("vendor-new")

        assert battery.vendor_id == "vendor-new"
        assert battery.level == TrustLevel.NEW

    def test_auto_approval_limits(self, service):
        """Test auto-approval limits by trust level."""
        limits = {
            TrustLevel.NEW: Decimal("0.00"),
            TrustLevel.LIMITED: Decimal("500.00"),
            TrustLevel.STANDARD: Decimal("2000.00"),
            TrustLevel.TRUSTED: Decimal("5000.00"),
            TrustLevel.VERIFIED: Decimal("20000.00"),
        }

        for level, expected_limit in limits.items():
            limit = service.get_auto_approval_limit(level)
            assert limit == expected_limit

    def test_can_auto_approve(self, service):
        """Test auto-approval logic."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            level=TrustLevel.TRUSTED,  # $5,000 limit
        )

        # Can auto-approve under limit
        assert service.can_auto_approve(battery, Decimal("4000.00"))

        # Cannot auto-approve over limit
        assert not service.can_auto_approve(battery, Decimal("6000.00"))

    @pytest.mark.asyncio
    async def test_trust_progression(self, service):
        """Test trust level progression on successful payments."""
        vendor_id = "vendor-001"

        # Start at NEW
        battery = await service.get_vendor_trust(vendor_id)
        assert battery.level == TrustLevel.NEW

        # Add 3 successful payments
        for i in range(3):
            battery = await service.update_trust(
                vendor_id,
                TrustOutcome.PAYMENT_SUCCESS,
                Decimal("1000.00"),
            )

        # Should progress to LIMITED
        assert battery.level == TrustLevel.LIMITED

    @pytest.mark.asyncio
    async def test_trust_regression_on_failure(self, service):
        """Test trust drops to NEW on payment failure."""
        vendor_id = "vendor-001"

        # Start at TRUSTED
        battery = TrustBattery(
            vendor_id=vendor_id,
            level=TrustLevel.TRUSTED,
            successful_payments=15,
        )

        # Simulate payment failure
        battery = await service.update_trust(
            vendor_id,
            TrustOutcome.PAYMENT_FAILED,
            Decimal("1000.00"),
        )

        # Should drop to NEW
        assert battery.level == TrustLevel.NEW

    @pytest.mark.asyncio
    async def test_trust_regression_on_dispute(self, service):
        """Test trust drops one level on dispute."""
        vendor_id = "vendor-001"

        # Start at TRUSTED
        battery = TrustBattery(
            vendor_id=vendor_id,
            level=TrustLevel.TRUSTED,
            successful_payments=15,
        )

        # Record dispute
        battery = await service.update_trust(
            vendor_id,
            TrustOutcome.DISPUTE_UNRESOLVED,
            Decimal("1000.00"),
        )

        # Should drop one level to STANDARD
        assert battery.level == TrustLevel.STANDARD
        assert battery.disputes == 1


class TestDecisionEnum:
    """Tests for Decision enum."""

    def test_decision_values(self):
        """Test decision enum values."""
        assert Decision.APPROVE.value == "approve"
        assert Decision.REVIEW.value == "review"
        assert Decision.REJECT.value == "reject"


class TestInvoiceStatus:
    """Tests for InvoiceStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert InvoiceStatus.INGESTED.value == "ingested"
        assert InvoiceStatus.PAID.value == "paid"
        assert InvoiceStatus.REVIEW_REQUIRED.value == "review_required"
