"""
Unit tests for Analyst Agent Activity
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal

from temporal.activities.agents import analyst_evaluate, AnalystProposal
from temporal.schemas import InvoiceExtracted, FinancialContext


class TestAnalystEvaluate:
    """Test suite for analyst evaluation activity."""

    @pytest.fixture
    def sample_invoice(self):
        """Sample invoice data."""
        return {
            "vendor_name": "Acme Corp",
            "total_amount": 100.00,
            "invoice_number": "INV-001",
            "due_date": "2025-03-15",
            "currency": "USD",
            "overall_confidence": 0.95,
        }

    @pytest.fixture
    def sample_financial_context(self):
        """Sample financial context."""
        return FinancialContext(
            current_cash=50000.0,
            monthly_burn_rate=15000.0,
            runway_days=100.0,
            safety_buffer=10000.0,
            strategy_mode="OPTIMIZE",
        )

    @pytest.mark.asyncio
    async def test_analyst_returns_proposal_object(self, sample_invoice):
        """Test that analyst returns AnalystProposal."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = []

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert isinstance(result, AnalystProposal)
        assert hasattr(result, "proposed_action")
        assert hasattr(result, "confidence")
        assert hasattr(result, "anomalies")

    @pytest.mark.asyncio
    async def test_analyst_proposes_hitl_for_new_vendor(self, sample_invoice):
        """Test that new vendors require HITL."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = []

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert result.proposed_action == "HITL_REQUIRED"
        assert any(a.type == "NEW_VENDOR" for a in result.anomalies)

    @pytest.mark.asyncio
    async def test_analyst_proposes_hitl_for_high_amount(self, sample_invoice):
        """Test that amounts > $10k require HITL."""
        # Arrange
        sample_invoice["total_amount"] = 15000.00

        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [{"amount": 10000, "status": "APPROVED"}]

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert result.proposed_action == "HITL_REQUIRED"

    @pytest.mark.asyncio
    async def test_analyst_detects_amount_spike(self, sample_invoice):
        """Test detection of amounts 2x above average."""
        # Arrange
        sample_invoice["total_amount"] = 500.00

        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [
                {"amount": 100, "status": "APPROVED"},
                {"amount": 105, "status": "APPROVED"},
                {"amount": 98, "status": "APPROVED"},
            ]

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert any(a.type == "AMOUNT_SPIKE" for a in result.anomalies)
        assert any(a.severity == "high" for a in result.anomalies)

    @pytest.mark.asyncio
    async def test_analyst_detects_amount_deviation(self, sample_invoice):
        """Test detection of amounts 1.5x above average."""
        # Arrange
        sample_invoice["total_amount"] = 350.00  # 1.6x average of 133.33, but < 1.5x max

        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [
                {"amount": 100, "status": "APPROVED"},
                {"amount": 100, "status": "APPROVED"},
                {"amount": 200, "status": "APPROVED"},  # Max is 200, so 350 > 200 * 1.5 = 300 (will create UNUSUAL_HIGH too)
            ]

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert - should have both AMOUNT_DEVIATION and UNUSUAL_HIGH
        assert any(a.type == "AMOUNT_DEVIATION" for a in result.anomalies)

    @pytest.mark.asyncio
    async def test_analyst_proposes_auto_approve_for_trusted_vendor(
        self, sample_invoice
    ):
        """Test auto-approve for trusted vendor with normal amount."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [
                {"amount": 95, "status": "APPROVED"},
                {"amount": 105, "status": "APPROVED"},
                {"amount": 100, "status": "APPROVED"},
            ]

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert result.proposed_action == "AUTO_APPROVE"
        assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_analyst_handles_neo4j_error_gracefully(self, sample_invoice):
        """Test graceful handling of Neo4j errors."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.side_effect = Exception("Neo4j connection failed")

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert - should still return proposal with safe defaults
        assert isinstance(result, AnalystProposal)
        assert result.proposed_action == "HITL_REQUIRED"

    @pytest.mark.asyncio
    async def test_analyst_includes_reasoning(self, sample_invoice):
        """Test that proposal includes reasoning."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = []

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert len(result.reasoning) > 0
        assert any("new vendor" in r.lower() for r in result.reasoning)

    @pytest.mark.asyncio
    async def test_analyst_includes_suggested_amount(self, sample_invoice):
        """Test that analyst includes suggested amount."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [
                {"amount": 100, "status": "APPROVED"},
            ]

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert result.suggested_amount == 100.00

    @pytest.mark.asyncio
    async def test_analyst_includes_suggested_due_date(self, sample_invoice):
        """Test that analyst includes suggested due date."""
        # Arrange
        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = []

            # Act
            result = await analyst_evaluate(sample_invoice)

        # Assert
        assert result.suggested_due_date == "2025-03-15"


class TestAnalystAnomalyDetection:
    """Test analyst anomaly detection logic."""

    @pytest.mark.asyncio
    async def test_analyst_detects_unusual_high_invoice(self):
        """Test detection of highest ever invoice from vendor."""
        # Arrange
        invoice = {
            "vendor_name": "Test Vendor",
            "total_amount": 500.00,
            "invoice_number": "INV-001",
            "overall_confidence": 0.95,
        }

        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [
                {"amount": 100, "status": "APPROVED"},
                {"amount": 200, "status": "APPROVED"},
                {"amount": 150, "status": "APPROVED"},
            ]

            # Act
            result = await analyst_evaluate(invoice)

        # Assert - 500 is 2.5x the previous max of 200
        assert any(a.type == "UNUSUAL_HIGH" for a in result.anomalies)

    @pytest.mark.asyncio
    async def test_analyst_reduces_confidence_for_medium_anomalies(self):
        """Test confidence reduction for medium severity anomalies."""
        # Arrange
        invoice = {
            "vendor_name": "Test Vendor",
            "total_amount": 350.00,  # 1.6x average of 133.33, but > 1.5x max
            "invoice_number": "INV-001",
            "overall_confidence": 0.95,
        }

        with patch("temporal.activities.agents._get_vendor_history") as mock_get_history:
            mock_get_history.return_value = [
                {"amount": 100, "status": "APPROVED"},
                {"amount": 100, "status": "APPROVED"},
                {"amount": 200, "status": "APPROVED"},  # Max is 200, so 350 > 200 * 1.5 = 300
            ]

            # Act
            result = await analyst_evaluate(invoice)

        # Assert - should have reduced confidence due to medium anomaly even with high severity
        assert result.confidence < 0.95  # Reduced due to medium anomaly
