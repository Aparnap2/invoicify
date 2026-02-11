"""
Unit tests for Critic Agent Activity
Following TDD approach from existing ai/tests/test_comprehensive.py
"""

import pytest
from unittest.mock import patch
from decimal import Decimal
from datetime import datetime, timedelta

from temporal.activities.agents import critic_review, AnalystProposal


class TestCriticReview:
    """Test suite for critic review activity."""

    @pytest.fixture
    def sample_invoice(self):
        """Sample invoice data."""
        return {
            "vendor_name": "AWS",
            "total_amount": 1000.00,
            "invoice_number": "INV-001",
            "due_date": (datetime.now() + timedelta(days=30)).isoformat(),
            "currency": "USD",
            "trust_level": 2,
        }

    @pytest.fixture
    def sample_analyst_proposal(self):
        """Sample analyst proposal."""
        return AnalystProposal(
            proposed_action="AUTO_APPROVE",
            confidence=0.9,
            anomalies=[],
            vendor_patterns=[],
            reasoning=["Normal invoice"],
        )

    @pytest.mark.asyncio
    async def test_critic_returns_review_dict(
        self, sample_invoice, sample_analyst_proposal
    ):
        """Test that critic returns review dictionary."""
        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        assert isinstance(result, dict)
        assert "can_proceed" in result
        assert "blocked" in result
        assert "risk_score" in result
        assert "signals" in result
        assert "reasoning" in result

    @pytest.mark.asyncio
    async def test_critic_allows_safe_payment(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic allows safe payment."""
        # Arrange - set safe financial context
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")
        monkeypatch.setenv("SAFETY_BUFFER", "10000")
        monkeypatch.setenv("STRATEGY_MODE", "OPTIMIZE")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        assert result["can_proceed"] is True
        assert result["blocked"] is False
        assert result["risk_score"] < 0.5

    @pytest.mark.asyncio
    async def test_critic_blocks_payment_below_safety_buffer(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic blocks payment that would go below safety buffer."""
        # Arrange - dangerous financial context
        monkeypatch.setenv("CURRENT_CASH", "10500")  # $1000 payment leaves $9500
        monkeypatch.setenv("SAFETY_BUFFER", "10000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        assert result["blocked"] is True
        assert result["can_proceed"] is False
        assert "below" in result["block_reason"].lower()

    @pytest.mark.asyncio
    async def test_critic_warns_on_low_runway(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic warns when runway drops below 90 days."""
        # Arrange - $6000 payment from $50k leaves $44k = 88 days runway
        sample_invoice["total_amount"] = 6000.00
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")
        monkeypatch.setenv("SAFETY_BUFFER", "10000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        assert result["can_proceed"] is True  # Not blocked, just warning
        runway_signal = next(s for s in result["signals"] if s["type"] == "RUNWAY")
        assert runway_signal["severity"] == "WARNING"

    @pytest.mark.asyncio
    async def test_critic_blocks_in_survival_mode(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic blocks large payments in SURVIVAL mode."""
        # Arrange - $6000 is >10% of $50k cash
        sample_invoice["total_amount"] = 6000.00
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("STRATEGY_MODE", "SURVIVAL")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        assert result["blocked"] is True
        strategy_signal = next(
            s for s in result["signals"] if s["type"] == "STRATEGY"
        )
        assert strategy_signal["severity"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_critic_checks_past_due_invoices(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic flags past due invoices."""
        # Arrange - invoice 5 days past due
        sample_invoice["due_date"] = (
            datetime.now() - timedelta(days=5)
        ).isoformat()
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        contract_signal = next(
            s for s in result["signals"] if s["type"] == "CONTRACT"
        )
        assert contract_signal["severity"] == "CRITICAL"
        assert "past due" in contract_signal["message"].lower()

    @pytest.mark.asyncio
    async def test_critic_checks_trust_level(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic checks vendor trust level."""
        # Arrange - Level 1 vendor (Probation)
        sample_invoice["trust_level"] = 1
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        trust_signal = next(s for s in result["signals"] if s["type"] == "TRUST")
        assert "Probation" in trust_signal["message"]

    @pytest.mark.asyncio
    async def test_critic_checks_budget_limits(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic checks budget category limits."""
        # Arrange - AWS = Infrastructure category
        sample_invoice["vendor_name"] = "AWS"
        sample_invoice["total_amount"] = 6000.00  # Over $5000 limit
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        budget_signal = next(s for s in result["signals"] if s["type"] == "BUDGET")
        assert budget_signal["severity"] in ["WARNING", "CRITICAL"]

    @pytest.mark.asyncio
    async def test_critic_generates_all_five_signals(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic generates all 5 priority matrix signals."""
        # Arrange
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert - Priority Matrix: RUNWAY, STRATEGY, CONTRACT, TRUST, BUDGET
        signal_types = [s["type"] for s in result["signals"]]
        assert "RUNWAY" in signal_types
        assert "STRATEGY" in signal_types
        assert "CONTRACT" in signal_types
        assert "TRUST" in signal_types
        assert "BUDGET" in signal_types
        assert len(result["signals"]) == 5

    @pytest.mark.asyncio
    async def test_critic_includes_reasoning(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic includes reasoning for each check."""
        # Arrange
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        assert len(result["reasoning"]) == 5
        assert any("RUNWAY" in r for r in result["reasoning"])
        assert any("STRATEGY" in r for r in result["reasoning"])
        assert any("CONTRACT" in r for r in result["reasoning"])
        assert any("TRUST" in r for r in result["reasoning"])
        assert any("BUDGET" in r for r in result["reasoning"])

    @pytest.mark.asyncio
    async def test_critic_growth_mode_prioritizes_early_payment(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic in GROWTH mode prioritizes early payment for vendor relationships."""
        # Arrange
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("STRATEGY_MODE", "GROWTH")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        strategy_signal = next(
            s for s in result["signals"] if s["type"] == "STRATEGY"
        )
        assert strategy_signal["severity"] == "INFO"
        assert "early payment" in strategy_signal["message"].lower()
        assert "discount" in strategy_signal["recommendation"].lower()

    @pytest.mark.asyncio
    async def test_critic_warns_near_payroll_date(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic warns when payment is within 3 days of payroll."""
        # Arrange - Set payroll date to 2 days from now
        today = datetime.now().day
        payroll_day = (today + 2) % 30 or 30
        sample_invoice["total_amount"] = 8000.00  # > 50% of payroll
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("PAYROLL_DATE", str(payroll_day))
        monkeypatch.setenv("PAYROLL_AMOUNT", "15000")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        runway_signal = next(s for s in result["signals"] if s["type"] == "RUNWAY")
        assert runway_signal["severity"] == "WARNING"
        assert "payroll" in runway_signal["message"].lower()
        assert "delay" in runway_signal["recommendation"].lower()

    @pytest.mark.asyncio
    async def test_critic_survival_mode_warns_large_payments(
        self, sample_invoice, sample_analyst_proposal, monkeypatch
    ):
        """Test critic in SURVIVAL mode warns about payments over $1,000."""
        # Arrange - $1,500 payment in SURVIVAL mode
        sample_invoice["total_amount"] = 1500.00
        monkeypatch.setenv("CURRENT_CASH", "50000")
        monkeypatch.setenv("STRATEGY_MODE", "SURVIVAL")
        monkeypatch.setenv("MONTHLY_BURN_RATE", "15000")

        # Act
        result = await critic_review(sample_invoice, sample_analyst_proposal)

        # Assert
        strategy_signal = next(
            s for s in result["signals"] if s["type"] == "STRATEGY"
        )
        assert strategy_signal["severity"] == "WARNING"
        assert "$1,000" in strategy_signal["message"]
