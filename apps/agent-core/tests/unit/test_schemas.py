"""
Unit tests for invoice schemas (Pydantic v2).

Tests validation, serialization, and edge cases for all schema models.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.schemas.invoice_v2 import (
    TrustLevel,
    RiskDecision,
    InvoiceStatus,
    LineItem,
    VendorInfo,
    ExtractedInvoice,
    RiskAnalysis,
    VoiceCallRecord,
    InvoiceDocument,
    AuditLogEntry,
    TrustBatteryState,
    ProcessRequest,
    ProcessResponse,
    HITLDecisionRequest,
    VoiceQueueRequest,
    CallPurpose,
    VoiceCallStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# LINE ITEM TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestLineItem:
    """Test LineItem schema validation."""
    
    def test_valid_line_item(self):
        """Test creation of valid line item."""
        item = LineItem(
            description="Office Chairs",
            quantity=10,
            unit_price=150.0,
            total=1500.0,
        )
        assert item.description == "Office Chairs"
        assert item.quantity == 10
        assert item.unit_price == 150.0
        assert item.total == 1500.0
    
    def test_line_item_with_tax(self):
        """Test line item with tax rate."""
        item = LineItem(
            description="Desk",
            quantity=5,
            unit_price=300.0,
            total=1500.0,
            tax_rate=0.18,
        )
        assert item.tax_rate == 0.18
    
    def test_line_item_total_mismatch(self):
        """Test that total mismatch raises error."""
        with pytest.raises(ValueError, match="Line item total mismatch"):
            LineItem(
                description="Widget",
                quantity=10,
                unit_price=100.0,
                total=999.0,  # Wrong: should be 1000.0
            )
    
    def test_line_item_quantity_must_be_positive(self):
        """Test that quantity must be positive."""
        with pytest.raises(ValueError):
            LineItem(
                description="Invalid",
                quantity=0,
                unit_price=100.0,
                total=0.0,
            )
    
    def test_line_item_unit_price_cannot_be_negative(self):
        """Test that unit price cannot be negative."""
        with pytest.raises(ValueError):
            LineItem(
                description="Invalid",
                quantity=10,
                unit_price=-100.0,
                total=-1000.0,
            )
    
    def test_line_item_description_required(self):
        """Test that description is required."""
        with pytest.raises(ValueError):
            LineItem(
                description="",
                quantity=10,
                unit_price=100.0,
                total=1000.0,
            )


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR INFO TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestVendorInfo:
    """Test VendorInfo schema validation."""
    
    def test_minimal_vendor_info(self):
        """Test vendor with only required name field."""
        vendor = VendorInfo(name="Acme Supplies")
        assert vendor.name == "Acme Supplies"
        assert vendor.address is None
        assert vendor.tax_id is None
    
    def test_complete_vendor_info(self):
        """Test vendor with all fields populated."""
        vendor = VendorInfo(
            name="Acme Supplies Pvt Ltd",
            address="123 Business Park, Mumbai 400001",
            tax_id="27AABCU9603R1ZM",
            phone="+91-22-12345678",
            email="billing@acme.in",
            bank_account_last4="1234",
        )
        assert vendor.name == "Acme Supplies Pvt Ltd"
        assert vendor.tax_id == "27AABCU9603R1ZM"
    
    def test_vendor_name_required(self):
        """Test that vendor name is required."""
        with pytest.raises(ValueError):
            VendorInfo(name="")


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTED INVOICE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractedInvoice:
    """Test ExtractedInvoice schema validation."""
    
    def test_valid_extracted_invoice(self):
        """Test creation of valid extracted invoice."""
        invoice = ExtractedInvoice(
            invoice_number="INV-2024-001",
            vendor=VendorInfo(name="Acme Supplies"),
            line_items=[
                LineItem(
                    description="Office Chairs",
                    quantity=10,
                    unit_price=150.0,
                    total=1500.0,
                )
            ],
            subtotal=3000.0,
            tax_amount=540.0,
            total_amount=3540.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.97,
            extraction_model="gpt-4o",
            extraction_latency_ms=2340,
        )
        assert invoice.invoice_number == "INV-2024-001"
        assert invoice.total_amount == 3540.0
        assert invoice.extraction_confidence == 0.97
        assert len(invoice.line_items) == 1
    
    def test_total_amount_validation(self):
        """Test that total_amount = subtotal + tax_amount."""
        # This should pass
        invoice = ExtractedInvoice(
            invoice_number="INV-001",
            vendor=VendorInfo(name="Test"),
            subtotal=1000.0,
            tax_amount=180.0,
            total_amount=1180.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.95,
            extraction_model="gpt-4o",
            extraction_latency_ms=1000,
        )
        assert invoice.total_amount == 1180.0
    
    def test_low_confidence_flagged(self):
        """Test that low confidence is allowed but flagged."""
        invoice = ExtractedInvoice(
            invoice_number="INV-001",
            vendor=VendorInfo(name="Test"),
            subtotal=1000.0,
            tax_amount=0.0,
            total_amount=1000.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.60,  # Below 0.75 threshold
            extraction_model="gpt-4o",
            extraction_latency_ms=1000,
            missing_fields=["vendor.tax_id", "line_items"],
        )
        assert invoice.extraction_confidence < 0.75
        assert "line_items" in invoice.missing_fields
    
    def test_invoice_date_format(self):
        """Test that invoice_date must be YYYY-MM-DD format."""
        with pytest.raises(ValueError):
            ExtractedInvoice(
                invoice_number="INV-001",
                vendor=VendorInfo(name="Test"),
                subtotal=1000.0,
                tax_amount=0.0,
                total_amount=1000.0,
                invoice_date="01-15-2024",  # Wrong format
                extraction_confidence=0.95,
                extraction_model="gpt-4o",
                extraction_latency_ms=1000,
            )


# ─────────────────────────────────────────────────────────────────────────────
# RISK ANALYSIS TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskAnalysis:
    """Test RiskAnalysis schema validation."""
    
    def test_auto_approve_decision(self):
        """Test AUTO_APPROVE decision."""
        risk = RiskAnalysis(
            risk_score=0.25,
            decision=RiskDecision.AUTO_APPROVE,
            decision_reason="CORE vendor, risk < 0.3, amount within limit",
            confidence=0.92,
            trust_level=TrustLevel.CORE,
            trust_score=0.85,
            auto_approve_limit=5000.0,
            amount_vs_limit="WITHIN",
            similar_invoices_found=12,
            rag_retrieval_latency_ms=234,
        )
        assert risk.decision == RiskDecision.AUTO_APPROVE
        assert risk.risk_score == 0.25
    
    def test_blocked_for_duplicate(self):
        """Test BLOCKED decision for duplicate."""
        risk = RiskAnalysis(
            risk_score=0.85,
            decision=RiskDecision.BLOCKED,
            decision_reason="Duplicate invoice detected",
            confidence=0.98,
            trust_level=TrustLevel.STANDARD,
            trust_score=0.70,
            is_duplicate=True,
            duplicate_invoice_id="inv-duplicate-001",
            auto_approve_limit=500.0,
            amount_vs_limit="WITHIN",
            similar_invoices_found=1,
            rag_retrieval_latency_ms=150,
        )
        assert risk.decision == RiskDecision.BLOCKED
        assert risk.is_duplicate is True
        assert risk.duplicate_invoice_id == "inv-duplicate-001"
    
    def test_fraud_signals(self):
        """Test fraud signals tracking."""
        risk = RiskAnalysis(
            risk_score=0.92,
            decision=RiskDecision.BLOCKED,
            decision_reason="Multiple fraud signals detected",
            confidence=0.95,
            trust_level=TrustLevel.PROBATION,
            trust_score=0.30,
            fraud_signals=[
                "vendor_address_matches_known_fraud",
                "bank_account_changed_recently",
                "invoice_amount_anomaly",
            ],
            auto_approve_limit=0.0,
            amount_vs_limit="EXCEEDS",
            similar_invoices_found=0,
            rag_retrieval_latency_ms=120,
        )
        assert len(risk.fraud_signals) == 3
        assert risk.decision == RiskDecision.BLOCKED


# ─────────────────────────────────────────────────────────────────────────────
# INVOICE DOCUMENT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestInvoiceDocument:
    """Test InvoiceDocument schema validation."""
    
    def test_new_invoice(self):
        """Test new invoice in SUBMITTED status."""
        doc = InvoiceDocument(
            id="inv-001",
            partition_key="Acme Supplies",
            tenant_id="tenant-001",
            trace_id="trace-abc123",
            r2_url="https://r2.cloudflarestorage.com/bucket/invoice.pdf",
            status=InvoiceStatus.SUBMITTED,
        )
        assert doc.status == InvoiceStatus.SUBMITTED
        assert doc.extracted is None
        assert doc.risk is None
    
    def test_approved_invoice(self):
        """Test approved invoice with all fields."""
        doc = InvoiceDocument(
            id="inv-001",
            partition_key="Acme Supplies",
            tenant_id="tenant-001",
            trace_id="trace-abc123",
            r2_url="https://r2.cloudflarestorage.com/bucket/invoice.pdf",
            status=InvoiceStatus.APPROVED,
            quickbooks_bill_id="qb-123",
            processing_latency_ms=5230,
        )
        assert doc.status == InvoiceStatus.APPROVED
        assert doc.quickbooks_bill_id == "qb-123"


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG ENTRY TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditLogEntry:
    """Test AuditLogEntry schema validation."""
    
    def test_auto_approve_audit(self):
        """Test audit log for AUTO_APPROVE action."""
        entry = AuditLogEntry(
            partition_key="inv-001",
            invoice_id="inv-001",
            tenant_id="tenant-001",
            actor="agent",
            action="AUTO_APPROVE",
            previous_status="ANALYZING",
            new_status="APPROVED",
            reason="CORE vendor, risk < 0.3, amount within limit",
            metadata={"risk_score": 0.25, "trust_level": "CORE"},
        )
        assert entry.actor == "agent"
        assert entry.action == "AUTO_APPROVE"
    
    def test_human_reviewer_audit(self):
        """Test audit log with human reviewer."""
        entry = AuditLogEntry(
            partition_key="inv-001",
            invoice_id="inv-001",
            tenant_id="tenant-001",
            actor="human:reviewer-123",
            action="APPROVED",
            previous_status="PENDING_REVIEW",
            new_status="APPROVED",
            reason="Verified with PO #12345",
        )
        assert entry.actor == "human:reviewer-123"
    
    def test_invalid_actor_format(self):
        """Test that actor must match pattern."""
        with pytest.raises(ValueError):
            AuditLogEntry(
                partition_key="inv-001",
                invoice_id="inv-001",
                tenant_id="tenant-001",
                actor="invalid_actor",
                action="APPROVED",
                previous_status="PENDING_REVIEW",
                new_status="APPROVED",
                reason="Test",
            )


# ─────────────────────────────────────────────────────────────────────────────
# API SCHEMA TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessRequest:
    """Test ProcessRequest schema."""
    
    def test_valid_process_request(self):
        """Test valid process request."""
        req = ProcessRequest(
            trace_id="trace-abc123",
            invoice_id="inv-001",
            r2_url="https://r2.cloudflarestorage.com/bucket/invoice.pdf",
            tenant_id="tenant-001",
            metadata={"vendor_name": "Acme Supplies"},
        )
        assert req.trace_id == "trace-abc123"
        assert req.metadata["vendor_name"] == "Acme Supplies"


class TestProcessResponse:
    """Test ProcessResponse schema."""
    
    def test_auto_approve_response(self):
        """Test response for AUTO_APPROVE."""
        resp = ProcessResponse(
            trace_id="trace-abc123",
            invoice_id="inv-001",
            status="APPROVED",
            decision="AUTO_APPROVE",
            risk_score=0.25,
            extraction_confidence=0.97,
            processing_latency_ms=5230,
            quickbooks_bill_id="qb-123",
        )
        assert resp.decision == "AUTO_APPROVE"
        assert resp.quickbooks_bill_id == "qb-123"


class TestHITLDecisionRequest:
    """Test HITLDecisionRequest schema."""
    
    def test_approve_decision(self):
        """Test APPROVE decision."""
        req = HITLDecisionRequest(
            invoice_id="inv-001",
            decision="APPROVED",
            reviewer_id="reviewer-123",
            notes="Verified with PO #12345",
        )
        assert req.decision == "APPROVED"
    
    def test_reject_decision(self):
        """Test REJECT decision."""
        req = HITLDecisionRequest(
            invoice_id="inv-001",
            decision="REJECTED",
            reviewer_id="reviewer-123",
            notes="Vendor not found in approved list",
        )
        assert req.decision == "REJECTED"


class TestVoiceQueueRequest:
    """Test VoiceQueueRequest schema."""
    
    def test_missing_details_call(self):
        """Test call for missing details."""
        req = VoiceQueueRequest(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Rajesh Kumar",
            purpose=CallPurpose.MISSING_DETAILS,
            language="hi-IN",
            tenant_id="tenant-001",
            context={"missing_fields": ["vendor.tax_id", "line_items"]},
        )
        assert req.purpose == CallPurpose.MISSING_DETAILS
        assert req.language == "hi-IN"


# ─────────────────────────────────────────────────────────────────────────────
# SERIALIZATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestSerialization:
    """Test JSON serialization of schemas."""
    
    def test_extracted_invoice_serialization(self):
        """Test ExtractedInvoice JSON serialization."""
        invoice = ExtractedInvoice(
            invoice_number="INV-2024-001",
            vendor=VendorInfo(name="Acme Supplies"),
            line_items=[
                LineItem(
                    description="Office Chairs",
                    quantity=10,
                    unit_price=150.0,
                    total=1500.0,
                )
            ],
            subtotal=3000.0,
            tax_amount=540.0,
            total_amount=3540.0,
            invoice_date="2024-01-15",
            extraction_confidence=0.97,
            extraction_model="gpt-4o",
            extraction_latency_ms=2340,
        )
        
        # Serialize to JSON
        data = invoice.model_dump(mode="json")
        
        assert data["invoice_number"] == "INV-2024-001"
        assert data["vendor"]["name"] == "Acme Supplies"
        assert len(data["line_items"]) == 1
        assert data["total_amount"] == 3540.0
    
    def test_risk_analysis_serialization(self):
        """Test RiskAnalysis JSON serialization."""
        risk = RiskAnalysis(
            risk_score=0.25,
            decision=RiskDecision.AUTO_APPROVE,
            decision_reason="Test",
            confidence=0.92,
            trust_level=TrustLevel.CORE,
            trust_score=0.85,
            auto_approve_limit=5000.0,
            amount_vs_limit="WITHIN",
            similar_invoices_found=12,
            rag_retrieval_latency_ms=234,
        )
        
        data = risk.model_dump(mode="json")
        
        assert data["decision"] == "AUTO_APPROVE"
        assert data["trust_level"] == "CORE"
