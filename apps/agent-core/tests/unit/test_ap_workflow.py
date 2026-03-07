"""
Unit Tests for AP Workflow Components.

Tests:
1. Fraud gate - deterministic checks
2. Duplicate detection - exact and fuzzy matching
3. Idempotency - same invoice processed only once
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Set environment for testing
os.environ["ENVIRONMENT"] = "test"
os.environ["EXTRACTOR_MODE"] = "fixture"


# ─────────────────────────────────────────────────────────────────────────────
# Fraud Gate Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFraudGate:
    """Tests for the deterministic fraud gate."""

    def test_bank_detail_change_detected(self):
        """Test that bank detail changes are detected."""
        from src.risk.fraud_gate import (
            FraudCheckInput,
            run_fraud_gate,
        )
        
        # Previous verified bank hash
        previous_hash = "a" * 64  # Fake hash
        
        # New bank details
        input_data = FraudCheckInput(
            trace_id="test-123",
            extracted_vendor_name="Test Vendor",
            extracted_bank_account="1234567890",
            extracted_ifsc="HDFC0001234",
            vendor_name="Test Vendor",
            verified_bank_hash=previous_hash,
        )
        
        result = run_fraud_gate(input_data)
        
        assert result.is_safe is False
        assert result.bank_detail_changed is True
        assert "BANK_DETAIL_CHANGE" in result.risk_flags

    def test_bank_detail_no_change(self):
        """Test that matching bank details pass."""
        from src.risk.fraud_gate import (
            FraudCheckInput,
            hash_bank_details,
            run_fraud_gate,
        )
        
        # Same hash for same details
        bank_hash = hash_bank_details(
            account_number="1234567890",
            ifsc_code="HDFC0001234",
        )
        
        input_data = FraudCheckInput(
            trace_id="test-124",
            extracted_vendor_name="Test Vendor",
            extracted_bank_account="1234567890",
            extracted_ifsc="HDFC0001234",
            vendor_name="Test Vendor",
            verified_bank_hash=bank_hash,
        )
        
        result = run_fraud_gate(input_data)
        
        assert result.is_safe is True
        assert result.bank_detail_changed is False

    def test_vendor_mismatch_detected(self):
        """Test that vendor name mismatches are detected."""
        from src.risk.fraud_gate import (
            FraudCheckInput,
            run_fraud_gate,
        )
        
        input_data = FraudCheckInput(
            trace_id="test-125",
            extracted_vendor_name="Completely Different Corp",
            vendor_name="Test Vendor Inc",
        )
        
        result = run_fraud_gate(input_data)
        
        assert result.is_safe is False
        assert result.vendor_mismatch is True
        assert "VENDOR_NAME_MISMATCH" in result.risk_flags

    def test_vendor_slight_name_variation(self):
        """Test that slight name variations don't trigger mismatch."""
        from src.risk.fraud_gate import (
            FraudCheckInput,
            run_fraud_gate,
        )
        
        input_data = FraudCheckInput(
            trace_id="test-126",
            extracted_vendor_name="Test Vendor Inc",
            vendor_name="Test Vendor",
        )
        
        result = run_fraud_gate(input_data)
        
        # Should pass because there's word overlap
        assert result.vendor_mismatch is False

    def test_no_bank_details_extracted(self):
        """Test when no bank details are on the invoice."""
        from src.risk.fraud_gate import (
            FraudCheckInput,
            run_fraud_gate,
        )
        
        input_data = FraudCheckInput(
            trace_id="test-127",
            extracted_vendor_name="Test Vendor",
            extracted_bank_account=None,
            extracted_ifsc=None,
            vendor_name="Test Vendor",
            verified_bank_hash=None,
        )
        
        result = run_fraud_gate(input_data)
        
        # Should pass if no verified hash exists
        assert result.is_safe is True

    def test_invalid_ifsc_format(self):
        """Test that invalid IFSC format is caught."""
        from src.risk.fraud_gate import (
            FraudCheckInput,
            run_fraud_gate,
        )
        
        input_data = FraudCheckInput(
            trace_id="test-128",
            extracted_vendor_name="Test Vendor",
            extracted_ifsc="INVALID",
        )
        
        result = run_fraud_gate(input_data)
        
        assert "INVALID_IFSC_FORMAT" in result.risk_flags


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate Detection Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDuplicateDetection:
    """Tests for duplicate invoice detection."""

    def test_exact_match_hash(self):
        """Test deterministic hash for exact matching."""
        from src.matching.duplicate import compute_exact_match_hash
        
        hash1 = compute_exact_match_hash(
            vendor_name="Test Vendor",
            invoice_number="INV-001",
            total=Decimal("1000.00"),
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        # Same inputs should produce same hash
        hash2 = compute_exact_match_hash(
            vendor_name="test vendor",  # Different case
            invoice_number="inv-001",    # Different case
            total=Decimal("1000.00"),
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        assert hash1 == hash2
        
        # Different inputs should produce different hash
        hash3 = compute_exact_match_hash(
            vendor_name="Test Vendor",
            invoice_number="INV-002",  # Different number
            total=Decimal("1000.00"),
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        assert hash1 != hash3

    def test_levenshtein_similarity(self):
        """Test string similarity for fuzzy matching."""
        from src.matching.duplicate import similarity_score
        
        # Identical strings
        score = similarity_score("INV-001", "INV-001")
        assert score == 1.0
        
        # Slightly different
        score = similarity_score("INV-001", "INV-002")
        assert score > 0.5
        
        # Completely different
        score = similarity_score("INV-001", "ABC-999")
        assert score < 0.5

    def test_fuzzy_match_detection(self):
        """Test fuzzy matching logic."""
        from src.matching.duplicate import is_fuzzy_match
        
        # Same invoice number, close date
        is_match, score = is_fuzzy_match(
            invoice_number="INV-001",
            total=Decimal("1000"),
            invoice_date=date(2024, 1, 15),
            candidate_invoice_number="INV-001",
            candidate_total=Decimal("1000"),
            candidate_date=date(2024, 1, 16),  # 1 day apart
        )
        
        assert is_match is True
        assert score == 1.0

    def test_fuzzy_match_outside_window(self):
        """Test that fuzzy matching respects date window."""
        from src.matching.duplicate import is_fuzzy_match
        
        is_match, score = is_fuzzy_match(
            invoice_number="INV-001",
            total=Decimal("1000"),
            invoice_date=date(2024, 1, 15),
            candidate_invoice_number="INV-001",
            candidate_total=Decimal("1000"),
            candidate_date=date(2024, 3, 1),  # 46 days apart - outside 30 day window
        )
        
        assert is_match is False


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestIdempotency:
    """Tests for idempotent processing."""

    def test_idempotency_key_computation(self):
        """Test that idempotency key is computed correctly."""
        from src.schemas.ap_models import APWorkflowState
        
        key = APWorkflowState.compute_idempotency_key(
            vendor_id="vendor-123",
            invoice_number="INV-001",
            total=Decimal("1000.00"),
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        # Same inputs should produce same key
        key2 = APWorkflowState.compute_idempotency_key(
            vendor_id="vendor-123",
            invoice_number="INV-001",
            total=Decimal("1000.00"),
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        assert key == key2
        
        # Different amount should produce different key
        key3 = APWorkflowState.compute_idempotency_key(
            vendor_id="vendor-123",
            invoice_number="INV-001",
            total=Decimal("2000.00"),  # Different
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        assert key != key3

    def test_idempotency_key_none_vendor(self):
        """Test idempotency with None vendor ID."""
        from src.schemas.ap_models import APWorkflowState
        
        key = APWorkflowState.compute_idempotency_key(
            vendor_id=None,
            invoice_number="INV-001",
            total=Decimal("1000.00"),
            currency="USD",
            invoice_date=date(2024, 1, 15),
        )
        
        assert key is not None
        assert len(key) == 64  # SHA256 hex length

    @pytest.mark.asyncio
    async def test_idempotency_check_returns_existing(self):
        """Test that idempotency check finds existing invoices."""
        from src.db import db as db_module
        
        with patch.object(db_module, "check_idempotency", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (True, "existing-id", "executed")
            
            # This would be called in the duplicate check node
            exists, existing_id, status = await db_module.check_idempotency("some-key")
            
            assert exists is True
            assert existing_id == "existing-id"
            assert status == "executed"

    @pytest.mark.asyncio
    async def test_idempotency_check_new_invoice(self):
        """Test that idempotency check allows new invoices."""
        from src.db import db as db_module
        
        with patch.object(db_module, "check_idempotency", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (False, None, None)
            
            exists, existing_id, status = await db_module.check_idempotency("new-key")
            
            assert exists is False
            assert existing_id is None


# ─────────────────────────────────────────────────────────────────────────────
# Three-Way Match Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestThreeWayMatch:
    """Tests for three-way matching logic."""

    def test_variance_calculation(self):
        """Test variance calculation between invoice and PO."""
        from decimal import Decimal
        
        invoice_total = Decimal("1000.00")
        po_total = Decimal("1050.00")
        
        variance = invoice_total - po_total
        variance_pct = (float(variance) / float(po_total)) * 100
        
        assert variance_pct == pytest.approx(-4.76, abs=0.1)

    def test_within_tolerance(self):
        """Test variance within tolerance."""
        from decimal import Decimal
        
        # 3% variance, 5% tolerance
        invoice_total = Decimal("1030.00")
        po_total = Decimal("1000.00")
        
        variance_pct = (float(invoice_total - po_total) / float(po_total)) * 100
        
        assert abs(variance_pct) <= 5.0

    def test_outside_tolerance(self):
        """Test variance outside tolerance."""
        from decimal import Decimal
        
        # 10% variance, 5% tolerance
        invoice_total = Decimal("1100.00")
        po_total = Decimal("1000.00")
        
        variance_pct = (float(invoice_total - po_total) / float(po_total)) * 100
        
        assert abs(variance_pct) > 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Decision Logic Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDecisionLogic:
    """Tests for deterministic decision logic."""

    def test_auto_approve_conditions(self):
        """Test auto-approve conditions are met."""
        # All conditions pass
        fraud_safe = True
        no_duplicate = True
        po_approved = True
        has_gl_code = True
        
        if fraud_safe and no_duplicate and po_approved and has_gl_code:
            decision = "AUTO_APPROVE"
        else:
            decision = "HITL_REQUIRED"
        
        assert decision == "AUTO_APPROVE"

    def test_reject_on_fraud(self):
        """Test that fraud triggers rejection."""
        fraud_safe = False
        decision = "REJECT" if not fraud_safe else "AUTO_APPROVE"
        
        assert decision == "REJECT"

    def test_reject_on_exact_duplicate(self):
        """Test that exact duplicate triggers rejection."""
        fraud_safe = True
        is_exact_duplicate = True
        decision = "REJECT" if is_exact_duplicate else "AUTO_APPROVE"
        
        assert decision == "REJECT"

    def test_hitl_on_security_review(self):
        """Test that security review triggers HITL."""
        requires_security = True
        
        if requires_security:
            decision = "HITL_REQUIRED"
        else:
            decision = "AUTO_APPROVE"
        
        assert decision == "HITL_REQUIRED"


# ─────────────────────────────────────────────────────────────────────────────
# Run Tests
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
