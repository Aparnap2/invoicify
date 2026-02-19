"""
Unit tests for pipeline stages (Extractor, Critic, Analyst).

Tests each agent in isolation with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal

from src.schemas.invoice_v2 import (
    ExtractedInvoice,
    VendorInfo,
    LineItem,
    RiskAnalysis,
    RiskDecision,
    TrustLevel,
)


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTOR AGENT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractorAgent:
    """Test ExtractorAgent extraction logic."""
    
    @pytest.fixture
    def extractor(self):
        """Create extractor agent."""
        from src.agents.extractor_agent import ExtractorAgent
        return ExtractorAgent(config={"llm_provider": "ollama", "mock_mode": True})
    
    @pytest.mark.asyncio
    async def test_normalize_extraction_basic(self, extractor):
        """Test extraction normalization."""
        raw_result = {
            "invoice_number": "INV-001",
            "vendor": {"name": "Acme Supplies"},
            "line_items": [
                {"description": "Chairs", "quantity": 10, "unit_price": 150.0, "total": 1500.0}
            ],
            "subtotal": 1500.0,
            "tax_amount": 0.0,
            "total_amount": 1500.0,
            "invoice_date": "2024-01-15",
        }
        
        normalized = extractor._normalize_extraction(raw_result)
        
        assert normalized["invoice_number"] == "INV-001"
        assert normalized["extraction_confidence"] == 0.85  # Default
        assert "extraction_latency_ms" not in normalized  # Added later
    
    @pytest.mark.asyncio
    async def test_normalize_extraction_calculates_totals(self, extractor):
        """Test that totals are calculated if missing."""
        raw_result = {
            "invoice_number": "INV-001",
            "vendor": {"name": "Acme"},
            "line_items": [
                {"description": "Item1", "quantity": 5, "unit_price": 100.0, "total": 500.0},
                {"description": "Item2", "quantity": 3, "unit_price": 200.0, "total": 600.0},
            ],
            "invoice_date": "2024-01-15",
        }
        
        normalized = extractor._normalize_extraction(raw_result)
        
        assert normalized["subtotal"] == 1100.0
        assert normalized["tax_amount"] == 0.0
        assert normalized["total_amount"] == 1100.0
    
    @pytest.mark.asyncio
    async def test_normalize_extraction_vendor_string(self, extractor):
        """Test vendor as string is normalized."""
        raw_result = {
            "invoice_number": "INV-001",
            "vendor": "Acme Supplies Inc",
            "line_items": [],
            "subtotal": 0.0,
            "tax_amount": 0.0,
            "total_amount": 0.0,
            "invoice_date": "2024-01-15",
        }
        
        normalized = extractor._normalize_extraction(raw_result)
        
        assert normalized["vendor"] == {"name": "Acme Supplies Inc"}


# ─────────────────────────────────────────────────────────────────────────────
# CRITIC AGENT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestCriticAgent:
    """Test CriticAgent validation logic."""
    
    @pytest.fixture
    def critic(self):
        """Create critic agent."""
        from src.agents.critic_agent import CriticAgent
        return CriticAgent()
    
    @pytest.fixture
    def valid_invoice(self):
        """Create a valid extracted invoice."""
        return ExtractedInvoice(
            invoice_number="INV-001",
            vendor=VendorInfo(name="Acme Supplies"),
            line_items=[
                LineItem(description="Chairs", quantity=10, unit_price=150.0, total=1500.0),
                LineItem(description="Desks", quantity=5, unit_price=300.0, total=1500.0),
            ],
            subtotal=3000.0,
            tax_amount=540.0,
            total_amount=3540.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.95,
            extraction_model="gpt-4o",
            extraction_latency_ms=2340,
        )
    
    @pytest.mark.asyncio
    async def test_validate_math_correct(self, critic, valid_invoice):
        """Test validation with correct math."""
        result = await critic.validate(valid_invoice)
        
        assert result["math_valid"] is True
        assert result["math_errors"] == []
    
    @pytest.mark.asyncio
    async def test_validate_math_error_line_item(self, critic):
        """Test validation with line item math error."""
        # Create invoice with correct data first
        invoice = ExtractedInvoice(
            invoice_number="INV-001",
            vendor=VendorInfo(name="Acme"),
            line_items=[
                LineItem(description="Widget", quantity=10, unit_price=100.0, total=1000.0),
            ],
            subtotal=1000.0,
            tax_amount=0.0,
            total_amount=1000.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.95,
            extraction_model="gpt-4o",
            extraction_latency_ms=1000,
        )
        
        # Now modify the line item total to create an error
        invoice.line_items[0].total = 999.0
        
        result = await critic.validate(invoice)
        
        assert result["math_valid"] is False
        assert len(result["math_errors"]) > 0
        assert "Line item" in result["math_errors"][0]
    
    @pytest.mark.asyncio
    async def test_validate_math_error_total(self, critic):
        """Test validation with total amount error."""
        # Create invoice with correct data first
        invoice = ExtractedInvoice(
            invoice_number="INV-001",
            vendor=VendorInfo(name="Acme"),
            line_items=[
                LineItem(description="Widget", quantity=10, unit_price=100.0, total=1000.0),
            ],
            subtotal=1000.0,
            tax_amount=180.0,
            total_amount=1180.0,  # Correct: 1000 + 180
            invoice_date="2024-01-15",
            extraction_confidence=0.95,
            extraction_model="gpt-4o",
            extraction_latency_ms=1000,
        )
        
        # Now modify the total amount to create an error
        invoice.total_amount = 9999.0
        
        result = await critic.validate(invoice)
        
        assert result["math_valid"] is False
        assert any("Total amount" in err for err in result["math_errors"])


# ─────────────────────────────────────────────────────────────────────────────
# ANALYST AGENT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalystAgent:
    """Test AnalystAgent risk analysis logic."""
    
    @pytest.fixture
    def analyst(self):
        """Create analyst agent with mocked dependencies."""
        from src.agents.analyst_agent import AnalystAgent
        
        # Mock Redis and Cosmos clients
        mock_redis = AsyncMock()
        mock_cosmos = AsyncMock()
        
        config = {
            "redis_client": mock_redis,
            "cosmos_client": mock_cosmos,
        }
        return AnalystAgent(config=config)
    
    @pytest.fixture
    def sample_invoice(self):
        """Create sample invoice for testing."""
        return ExtractedInvoice(
            invoice_number="INV-001",
            vendor=VendorInfo(name="Acme Supplies"),
            line_items=[
                LineItem(description="Chairs", quantity=10, unit_price=150.0, total=1500.0),
            ],
            subtotal=1500.0,
            tax_amount=270.0,
            total_amount=1770.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.95,
            extraction_model="gpt-4o",
            extraction_latency_ms=2340,
        )
    
    @pytest.mark.asyncio
    async def test_analyze_core_vendor_auto_approve(self, analyst, sample_invoice):
        """Test AUTO_APPROVE for CORE vendor with low risk."""
        # Mock trust battery manager
        with patch.object(analyst.trust_manager, 'get_battery') as mock_get:
            from src.trust.battery import TrustBattery
            from datetime import datetime
            
            mock_battery = TrustBattery(
                vendor_id="acme",
                tenant_id="tenant-001",
                invoice_count=150,
                accurate_count=150,
                last_invoice_at=datetime.utcnow(),
            )
            mock_get.return_value = mock_battery
            
            result = await analyst.analyze(
                extracted=sample_invoice,
                tenant_id="tenant-001",
                metadata={"vendor_name": "Acme Supplies"},
            )
            
            assert result.decision == RiskDecision.AUTO_APPROVE
            assert result.trust_level == TrustLevel.CORE
            assert result.risk_score < 0.3
    
    @pytest.mark.asyncio
    async def test_analyze_probation_vendor_hitl(self, analyst, sample_invoice):
        """Test HITL_REQUIRED for PROBATION vendor."""
        with patch.object(analyst.trust_manager, 'get_battery') as mock_get:
            from src.trust.battery import TrustBattery
            
            mock_battery = TrustBattery(
                vendor_id="new-vendor",
                tenant_id="tenant-001",
                invoice_count=5,
                accurate_count=5,
            )
            mock_get.return_value = mock_battery
            
            result = await analyst.analyze(
                extracted=sample_invoice,
                tenant_id="tenant-001",
                metadata={"vendor_name": "New Vendor"},
            )
            
            assert result.decision == RiskDecision.HITL_REQUIRED
            assert result.trust_level == TrustLevel.PROBATION
    
    @pytest.mark.asyncio
    async def test_analyze_amount_exceeds_limit_hitl(self, analyst, sample_invoice):
        """Test HITL_REQUIRED when amount exceeds limit."""
        with patch.object(analyst.trust_manager, 'get_battery') as mock_get:
            from src.trust.battery import TrustBattery
            
            # CORE vendor but amount > $5000
            mock_battery = TrustBattery(
                vendor_id="acme",
                tenant_id="tenant-001",
                invoice_count=150,
                accurate_count=150,
            )
            mock_get.return_value = mock_battery
            
            # Create high-amount invoice
            high_invoice = ExtractedInvoice(
                invoice_number="INV-HIGH",
                vendor=VendorInfo(name="Acme Supplies"),
                line_items=[
                    LineItem(description="Equipment", quantity=10, unit_price=1000.0, total=10000.0),
                ],
                subtotal=10000.0,
                tax_amount=1800.0,
                total_amount=11800.0,
                invoice_date="2024-01-15",
                extraction_confidence=0.95,
                extraction_model="gpt-4o",
                extraction_latency_ms=2340,
            )
            
            result = await analyst.analyze(
                extracted=high_invoice,
                tenant_id="tenant-001",
                metadata={"vendor_name": "Acme Supplies"},
            )
            
            assert result.decision == RiskDecision.HITL_REQUIRED
            assert result.amount_vs_limit == "EXCEEDS"
    
    @pytest.mark.asyncio
    async def test_calculate_risk_score_weights(self, analyst):
        """Test risk score calculation with different weights."""
        signals = {
            "is_duplicate": False,
            "price_anomaly": False,
            "math_errors": [],
            "fraud_signals": [],
        }
        
        from src.trust.battery import TrustBattery
        
        # High trust vendor (low risk)
        high_trust_battery = TrustBattery(
            vendor_id="trusted",
            tenant_id="tenant-001",
            invoice_count=200,
            accurate_count=200,
        )
        
        risk_score = analyst._calculate_risk_score(signals, high_trust_battery)
        assert risk_score < 0.3  # Low risk for trusted vendor
        
        # Low trust vendor (higher risk)
        low_trust_battery = TrustBattery(
            vendor_id="newbie",
            tenant_id="tenant-001",
            invoice_count=0,
            accurate_count=0,
        )
        
        risk_score_low = analyst._calculate_risk_score(signals, low_trust_battery)
        assert risk_score_low > risk_score  # Higher risk for new vendor
    
    @pytest.mark.asyncio
    async def test_make_decision_blocked_high_risk(self, analyst):
        """Test BLOCKED decision for high risk."""
        decision, reason = analyst._make_decision(
            risk_score=0.85,
            trust_level=TrustLevel.PROBATION,
            amount=1000.0,
            auto_approve_limit=0.0,
            risk_signals={"fraud_signals": ["suspicious_pattern"]},
        )
        
        assert decision == RiskDecision.BLOCKED
        assert "High risk" in reason or "Fraud" in reason
    
    @pytest.mark.asyncio
    async def test_make_decision_blocked_duplicate(self, analyst):
        """Test BLOCKED decision for duplicate."""
        decision, reason = analyst._make_decision(
            risk_score=0.50,
            trust_level=TrustLevel.CORE,
            amount=1000.0,
            auto_approve_limit=5000.0,
            risk_signals={
                "is_duplicate": True,
                "duplicate_invoice_id": "inv-dup-001",
            },
        )
        
        assert decision == RiskDecision.BLOCKED
        assert "Duplicate" in reason


# ─────────────────────────────────────────────────────────────────────────────
# DECISION MATRIX PARAMETERIZED TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionMatrix:
    """Test decision matrix with various scenarios."""
    
    @pytest.fixture
    def analyst(self):
        """Create analyst agent."""
        from src.agents.analyst_agent import AnalystAgent
        return AnalystAgent(config={})
    
    @pytest.mark.parametrize("trust_level,amount,risk_score,expected_decision", [
        (TrustLevel.CORE,       400.0,   0.20, RiskDecision.AUTO_APPROVE),
        (TrustLevel.CORE,       6000.0,  0.20, RiskDecision.HITL_REQUIRED),  # Exceeds limit
        (TrustLevel.STANDARD,   400.0,   0.20, RiskDecision.HITL_REQUIRED),  # Not CORE
        (TrustLevel.STANDARD,   600.0,   0.20, RiskDecision.HITL_REQUIRED),  # Not CORE + exceeds
        (TrustLevel.PROBATION,  10.0,    0.20, RiskDecision.HITL_REQUIRED),  # PROBATION
        (TrustLevel.STRATEGIC,  49000.0, 0.20, RiskDecision.AUTO_APPROVE),
        (TrustLevel.CORE,       1000.0,  0.85, RiskDecision.BLOCKED),  # High risk
    ])
    def test_decision_matrix_scenarios(
        self,
        analyst,
        trust_level,
        amount,
        risk_score,
        expected_decision,
    ):
        """Test various decision scenarios."""
        decision, reason = analyst._make_decision(
            risk_score=risk_score,
            trust_level=trust_level,
            amount=amount,
            auto_approve_limit={
                TrustLevel.PROBATION: 0.0,
                TrustLevel.STANDARD: 500.0,
                TrustLevel.CORE: 5000.0,
                TrustLevel.STRATEGIC: 50000.0,
            }[trust_level],
            risk_signals={},
        )
        
        assert decision == expected_decision, f"Failed for {trust_level.value}, ${amount}, risk={risk_score}"
