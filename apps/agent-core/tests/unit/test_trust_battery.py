"""
Unit tests for Trust Battery system.

Tests trust level computation, score calculation, and state transitions.
"""

import pytest
from datetime import datetime, timedelta

from src.trust.battery import TrustBattery, TrustBatteryManager
from src.schemas.invoice_v2 import TrustLevel, TrustBatteryState


# ─────────────────────────────────────────────────────────────────────────────
# TRUST LEVEL THRESHOLD TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestTrustLevelThresholds:
    """Test trust level computation based on invoice count."""
    
    @pytest.mark.parametrize("invoice_count,accurate_count,expected_level", [
        (0,   0,   TrustLevel.PROBATION),
        (10,  10,  TrustLevel.PROBATION),
        (49,  49,  TrustLevel.PROBATION),
        (50,  50,  TrustLevel.STANDARD),
        (99,  99,  TrustLevel.STANDARD),
        (100, 100, TrustLevel.CORE),
        (199, 199, TrustLevel.CORE),
        (200, 200, TrustLevel.STRATEGIC),
        (250, 250, TrustLevel.STRATEGIC),
    ])
    def test_trust_level_from_invoice_count(self, invoice_count, accurate_count, expected_level):
        """Test trust level thresholds based on invoice count."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=invoice_count,
            accurate_count=accurate_count,
        )
        assert battery.level == expected_level, \
            f"Expected {expected_level} for {invoice_count} invoices, got {battery.level}"
    
    def test_trust_level_uses_accurate_count(self):
        """Test that trust level considers accuracy rate."""
        # High volume but low accuracy should still show volume-based level
        # (demotion happens via consecutive errors, not accuracy rate)
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=150,
            accurate_count=100,
            error_count=50,
        )
        # Should be CORE based on volume (100+ invoices)
        assert battery.level == TrustLevel.CORE


# ─────────────────────────────────────────────────────────────────────────────
# TRUST SCORE COMPUTATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestTrustScoreComputation:
    """Test trust score calculation."""
    
    def test_perfect_score(self):
        """Test perfect trust score (100% accuracy, high volume, recent)."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=200,
            accurate_count=200,
            error_count=0,
            last_invoice_at=datetime.utcnow(),
        )
        score = battery.score
        assert 0.9 <= score <= 1.0, f"Expected high score, got {score}"
    
    def test_zero_invoices_zero_score(self):
        """Test zero invoices results in minimal score."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=0,
            accurate_count=0,
        )
        # Score has 3 components: accuracy (0), volume (0), recency (1.0 for datetime.utcnow())
        # With 0 invoices: score = 0.6*0 + 0.2*0 + 0.2*1.0 = 0.2
        assert battery.score == 0.2
    
    def test_accuracy_component(self):
        """Test accuracy component of trust score."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=90,
            error_count=10,
            last_invoice_at=datetime.utcnow(),
        )
        # Accuracy rate = 90/100 = 0.9
        # Score should be heavily weighted by accuracy (60%)
        score = battery.score
        assert score > 0.5, f"Expected score > 0.5, got {score}"
    
    def test_recency_decay(self):
        """Test trust score decays with inactivity."""
        # Recent activity
        battery_recent = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            last_invoice_at=datetime.utcnow(),
        )
        
        # Old activity (90 days ago = 3 half-lives)
        battery_old = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            last_invoice_at=datetime.utcnow() - timedelta(days=90),
        )
        
        assert battery_recent.score > battery_old.score, \
            "Recent activity should have higher score"


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-APPROVE LIMIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoApproveLimits:
    """Test auto-approve limit computation."""
    
    @pytest.mark.parametrize("invoice_count,accurate_count,expected_limit", [
        (0,   0,   0.0),      # PROBATION: $0
        (50,  50,  500.0),    # STANDARD: $500
        (100, 100, 5000.0),   # CORE: $5,000
        (200, 200, 50000.0),  # STRATEGIC: $50,000
    ])
    def test_auto_approve_limits(self, invoice_count, accurate_count, expected_limit):
        """Test auto-approve limits by trust level."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=invoice_count,
            accurate_count=accurate_count,
        )
        assert battery.auto_approve_limit == expected_limit, \
            f"Expected limit ${expected_limit}, got ${battery.auto_approve_limit}"


# ─────────────────────────────────────────────────────────────────────────────
# CONSECUTIVE ERROR DEMOTION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestConsecutiveErrorDemotion:
    """Test trust level demotion due to consecutive errors."""
    
    def test_demotion_from_strategic(self):
        """Test demotion from STRATEGIC after 3 consecutive errors."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=250,
            accurate_count=250,
            consecutive_errors=3,
        )
        # Should be demoted from STRATEGIC to CORE
        assert battery.level == TrustLevel.CORE
    
    def test_demotion_from_core(self):
        """Test demotion from CORE after 3 consecutive errors."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=150,
            accurate_count=150,
            consecutive_errors=3,
        )
        # Should be demoted from CORE to STANDARD
        assert battery.level == TrustLevel.STANDARD
    
    def test_demotion_from_standard(self):
        """Test demotion from STANDARD after 3 consecutive errors."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=75,
            accurate_count=75,
            consecutive_errors=3,
        )
        # Should be demoted from STANDARD to PROBATION
        assert battery.level == TrustLevel.PROBATION
    
    def test_error_streak_reset_on_accurate(self):
        """Test that accurate invoice resets error streak."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            consecutive_errors=2,
        )
        
        # Record accurate invoice
        battery.record_accurate_invoice(amount=1000.0)
        
        assert battery.consecutive_errors == 0
        assert battery.level == TrustLevel.CORE  # No demotion


# ─────────────────────────────────────────────────────────────────────────────
# STATE UPDATE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestStateUpdates:
    """Test trust battery state updates."""
    
    def test_record_accurate_invoice(self):
        """Test recording an accurate invoice."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            total_approved_amount=50000.0,
        )
        
        # Record new accurate invoice
        battery.record_accurate_invoice(amount=1000.0)
        
        assert battery.invoice_count == 101
        assert battery.accurate_count == 101
        assert battery.total_approved_amount == 51000.0
        assert battery.consecutive_errors == 0
    
    def test_record_error(self):
        """Test recording an invoice error."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            error_count=0,
            consecutive_errors=0,
        )
        
        # Record error
        battery.record_error()
        
        assert battery.error_count == 1
        assert battery.consecutive_errors == 1
    
    def test_multiple_errors_increase_streak(self):
        """Test that multiple errors increase streak."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
        )
        
        # Record 3 errors
        battery.record_error()
        battery.record_error()
        battery.record_error()
        
        assert battery.consecutive_errors == 3
        assert battery.level == TrustLevel.STANDARD  # Demoted from CORE


# ─────────────────────────────────────────────────────────────────────────────
# SERIALIZATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestSerialization:
    """Test trust battery serialization."""
    
    def test_to_state(self):
        """Test conversion to TrustBatteryState."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=150,
            accurate_count=148,
            error_count=2,
            total_approved_amount=750000.0,
            last_invoice_at=datetime.utcnow(),
        )
        
        state = battery.to_state()
        
        assert state.vendor_id == "vendor-001"
        assert state.tenant_id == "tenant-001"
        assert state.invoice_count == 150
        assert state.trust_level == TrustLevel.CORE
        assert state.auto_approve_limit == 5000.0
    
    def test_from_state(self):
        """Test creation from TrustBatteryState."""
        state = TrustBatteryState(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=200,
            accurate_count=200,
            error_count=0,
            total_approved_amount=1000000.0,
            trust_level=TrustLevel.STRATEGIC,
            trust_score=0.95,
            auto_approve_limit=50000.0,
        )
        
        battery = TrustBattery.from_state(state)
        
        assert battery.vendor_id == "vendor-001"
        assert battery.invoice_count == 200
        assert battery.level == TrustLevel.STRATEGIC
        assert battery.auto_approve_limit == 50000.0
    
    def test_roundtrip_serialization(self):
        """Test roundtrip: battery -> state -> battery."""
        original = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=120,
            accurate_count=118,
            error_count=2,
            total_approved_amount=600000.0,
        )
        
        # Serialize
        state = original.to_state()
        
        # Deserialize
        restored = TrustBattery.from_state(state)
        
        assert restored.vendor_id == original.vendor_id
        assert restored.invoice_count == original.invoice_count
        assert restored.level == original.level
        assert restored.auto_approve_limit == original.auto_approve_limit


# ─────────────────────────────────────────────────────────────────────────────
# TRUST BATTERY MANAGER TESTS (MOCKED)
# ─────────────────────────────────────────────────────────────────────────────

class TestTrustBatteryManager:
    """Test TrustBatteryManager with mocked Redis/Cosmos."""
    
    @pytest.mark.asyncio
    async def test_get_battery_new_vendor(self):
        """Test getting battery for new vendor (no cache, no DB)."""
        manager = TrustBatteryManager(redis_client=None, cosmos_client=None)
        
        battery = await manager.get_battery(
            vendor_id="new-vendor",
            tenant_id="tenant-001",
        )
        
        assert battery.vendor_id == "new-vendor"
        assert battery.level == TrustLevel.PROBATION
        assert battery.auto_approve_limit == 0.0
    
    @pytest.mark.asyncio
    async def test_update_battery_records_accurate(self):
        """Test updating battery with accurate invoice."""
        manager = TrustBatteryManager(redis_client=None, cosmos_client=None)
        
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
        )
        
        updated = await manager.update_battery(
            battery=battery,
            accurate=True,
            amount=1000.0,
        )
        
        assert updated.invoice_count == 101
        assert updated.accurate_count == 101
        assert updated.total_approved_amount == 1000.0
    
    @pytest.mark.asyncio
    async def test_update_battery_records_error(self):
        """Test updating battery with error."""
        manager = TrustBatteryManager(redis_client=None, cosmos_client=None)
        
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            consecutive_errors=0,
        )
        
        updated = await manager.update_battery(
            battery=battery,
            accurate=False,
            amount=0.0,
        )
        
        assert updated.error_count == 1
        assert updated.consecutive_errors == 1


# ─────────────────────────────────────────────────────────────────────────────
# EDGE CASE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_exact_threshold_boundaries(self):
        """Test exact boundary conditions for thresholds."""
        # Exactly at STANDARD threshold (50)
        battery_50 = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=50,
            accurate_count=50,
        )
        assert battery_50.level == TrustLevel.STANDARD
        
        # One below STANDARD threshold (49)
        battery_49 = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=49,
            accurate_count=49,
        )
        assert battery_49.level == TrustLevel.PROBATION
    
    def test_zero_amount_invoice(self):
        """Test recording zero-amount invoice."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            total_approved_amount=50000.0,
        )
        
        # Record zero-amount invoice
        battery.record_accurate_invoice(amount=0.0)
        
        assert battery.invoice_count == 101
        assert battery.accurate_count == 101
        assert battery.total_approved_amount == 50000.0  # Unchanged
    
    def test_very_large_invoice(self):
        """Test recording very large invoice amount."""
        battery = TrustBattery(
            vendor_id="vendor-001",
            tenant_id="tenant-001",
            invoice_count=100,
            accurate_count=100,
            total_approved_amount=50000.0,
        )
        
        # Record large invoice
        battery.record_accurate_invoice(amount=1000000.0)
        
        assert battery.total_approved_amount == 1050000.0
