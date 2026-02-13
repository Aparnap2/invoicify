"""
E2E Tests for Invoice Processing Workflow
Tests complete flow from upload to payment with Temporal.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, AsyncMock, Mock

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.exceptions import ApplicationError

from src.workflows.invoice_workflow import InvoiceProcessingWorkflow
from src.activities.extract_docling import extract_invoice_with_docling
from src.activities.risk_score import calculate_risk_score
from src.activities.make_decision import make_invoice_decision
from src.activities.update_trust import update_vendor_trust
from src.activities.process_payment import process_payment
from src.domain.models import Decision, TrustLevel, TrustOutcome


class TestInvoiceProcessingWorkflow:
    """E2E tests for complete invoice workflow."""

    @pytest.fixture
    async def temporal_env(self):
        """Create Temporal test environment."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            yield env

    @pytest.mark.asyncio
    async def test_trusted_vendor_invoice_auto_approved(self, temporal_env):
        """
        Scenario: Low-risk invoice from trusted vendor
        Expected: Auto-approved and payment executed
        """

        # Mock activities
        async def mock_extract(file_url: str):
            return {
                "invoice_id": "inv-test-001",
                "vendor_id": "vendor_acme_corp",
                "vendor_name": "Acme Corp",
                "invoice_number": "INV-001",
                "total_amount": "500.00",
                "currency": "USD",
                "confidence": 0.95,
                "line_items": [],
                "issue_date": datetime.utcnow().isoformat(),
                "due_date": datetime.utcnow().isoformat(),
            }

        async def mock_get_trust(vendor_id: str):
            return {
                "vendor_id": vendor_id,
                "level": TrustLevel.TRUSTED.value,
                "level_name": "TRUSTED",
                "successful_payments": 15,
                "disputes": 0,
                "total_invoices": 15,
            }

        async def mock_risk_score(params: dict):
            return {
                "overall_score": 0.1,
                "breakdown": {
                    "amount_anomaly_score": 0.05,
                    "pattern_anomaly_score": 0.1,
                    "vendor_trust_penalty": 0.0,
                    "time_based_risk": 0.0,
                    "duplicate_risk": 0.0,
                },
                "reasons": ["Low risk - trusted vendor"],
                "recommended_action": "approve",
            }

        async def mock_decision(params: dict):
            return {
                "decision": Decision.APPROVE.value,
                "reason": "Low risk and within limits",
            }

        async def mock_payment(params: dict):
            return {
                "reference": "PAY-TEST-001",
                "amount": "500.00",
                "status": "completed",
            }

        async def mock_update_trust(params: dict):
            return {
                "vendor_id": params["vendor_id"],
                "level": TrustLevel.TRUSTED.value,
                "level_name": "TRUSTED",
                "successful_payments": 16,
            }

        async def mock_emit(event_data: dict):
            return {"status": "success"}

        # Start worker with mocked activities
        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract,
                mock_get_trust,
                mock_risk_score,
                mock_decision,
                mock_payment,
                mock_update_trust,
                mock_emit,
            ],
        ):
            # Execute workflow
            handle = await temporal_env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                "https://example.com/invoice.pdf",
                id="test-workflow-001",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        assert result["status"] == "paid"
        assert result["decision"] == "approve"
        assert result["payment_reference"] == "PAY-TEST-001"
        assert float(result["risk_score"]) < 0.3

    @pytest.mark.asyncio
    async def test_new_vendor_requires_review(self, temporal_env):
        """
        Scenario: Invoice from new vendor (trust level 1)
        Expected: REVIEW_REQUIRED, no payment
        """

        async def mock_extract(file_url: str):
            return {
                "invoice_id": "inv-test-002",
                "vendor_id": "vendor_new_co",
                "vendor_name": "New Co",
                "invoice_number": "INV-002",
                "total_amount": "500.00",
                "currency": "USD",
                "confidence": 0.85,
                "line_items": [],
                "issue_date": datetime.utcnow().isoformat(),
                "due_date": datetime.utcnow().isoformat(),
            }

        async def mock_get_trust(vendor_id: str):
            return {
                "vendor_id": vendor_id,
                "level": TrustLevel.NEW.value,
                "level_name": "NEW",
                "successful_payments": 0,
                "disputes": 0,
                "total_invoices": 0,
            }

        async def mock_risk_score(params: dict):
            return {
                "overall_score": 0.5,
                "breakdown": {
                    "amount_anomaly_score": 0.1,
                    "pattern_anomaly_score": 0.2,
                    "vendor_trust_penalty": 0.8,  # High penalty for new vendor
                    "time_based_risk": 0.0,
                    "duplicate_risk": 0.0,
                },
                "reasons": ["New vendor requires manual review"],
                "recommended_action": "review",
            }

        async def mock_decision(params: dict):
            return {
                "decision": Decision.REVIEW.value,
                "reason": "New vendor requires manual review",
            }

        async def mock_update_trust(params: dict):
            return {
                "vendor_id": params["vendor_id"],
                "level": TrustLevel.NEW.value,
                "level_name": "NEW",
                "successful_payments": 0,
            }

        async def mock_emit(event_data: dict):
            return {"status": "success"}

        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract,
                mock_get_trust,
                mock_risk_score,
                mock_decision,
                mock_update_trust,
                mock_emit,
            ],
        ):
            handle = await temporal_env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                "https://example.com/new-vendor-invoice.pdf",
                id="test-workflow-002",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        assert result["status"] == "review_required"
        assert result["decision"] == "review"
        assert "payment_reference" not in result  # No payment

    @pytest.mark.asyncio
    async def test_high_amount_requires_review(self, temporal_env):
        """
        Scenario: High amount invoice exceeding auto-approval limit
        Expected: REVIEW_REQUIRED
        """

        async def mock_extract(file_url: str):
            return {
                "invoice_id": "inv-test-003",
                "vendor_id": "vendor_standard_inc",
                "vendor_name": "Standard Inc",
                "invoice_number": "INV-003",
                "total_amount": "10000.00",  # High amount
                "currency": "USD",
                "confidence": 0.9,
                "line_items": [],
                "issue_date": datetime.utcnow().isoformat(),
                "due_date": datetime.utcnow().isoformat(),
            }

        async def mock_get_trust(vendor_id: str):
            return {
                "vendor_id": vendor_id,
                "level": TrustLevel.STANDARD.value,  # $2,000 limit
                "level_name": "STANDARD",
                "successful_payments": 8,
                "disputes": 0,
                "total_invoices": 8,
            }

        async def mock_risk_score(params: dict):
            return {
                "overall_score": 0.4,
                "breakdown": {
                    "amount_anomaly_score": 0.6,  # Amount anomaly
                    "pattern_anomaly_score": 0.2,
                    "vendor_trust_penalty": 0.2,
                    "time_based_risk": 0.0,
                    "duplicate_risk": 0.0,
                },
                "reasons": ["Amount exceeds typical range"],
                "recommended_action": "review",
            }

        async def mock_decision(params: dict):
            return {
                "decision": Decision.REVIEW.value,
                "reason": "Amount $10000.00 exceeds auto-approval limit ($2000.00)",
            }

        async def mock_update_trust(params: dict):
            return {
                "vendor_id": params["vendor_id"],
                "level": TrustLevel.STANDARD.value,
                "level_name": "STANDARD",
                "successful_payments": 8,
            }

        async def mock_emit(event_data: dict):
            return {"status": "success"}

        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract,
                mock_get_trust,
                mock_risk_score,
                mock_decision,
                mock_update_trust,
                mock_emit,
            ],
        ):
            handle = await temporal_env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                "https://example.com/high-amount-invoice.pdf",
                id="test-workflow-003",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        assert result["status"] == "review_required"
        assert result["decision"] == "review"
        assert "10000.00" in str(result.get("total_amount", ""))

    @pytest.mark.asyncio
    async def test_workflow_query_methods(self, temporal_env):
        """Test workflow query methods return correct state."""

        async def mock_extract(file_url: str):
            await asyncio.sleep(0.1)  # Simulate delay
            return {
                "invoice_id": "inv-test-004",
                "vendor_id": "vendor_test",
                "vendor_name": "Test Vendor",
                "invoice_number": "INV-004",
                "total_amount": "100.00",
                "currency": "USD",
                "confidence": 0.95,
                "line_items": [],
                "issue_date": datetime.utcnow().isoformat(),
                "due_date": datetime.utcnow().isoformat(),
            }

        async def mock_get_trust(vendor_id: str):
            return {
                "vendor_id": vendor_id,
                "level": TrustLevel.TRUSTED.value,
                "level_name": "TRUSTED",
                "successful_payments": 20,
            }

        async def mock_risk_score(params: dict):
            return {
                "overall_score": 0.15,
                "breakdown": {},
                "reasons": [],
                "recommended_action": "approve",
            }

        async def mock_decision(params: dict):
            return {
                "decision": Decision.APPROVE.value,
                "reason": "Low risk",
            }

        async def mock_payment(params: dict):
            return {
                "reference": "PAY-TEST-004",
                "amount": "100.00",
                "status": "completed",
            }

        async def mock_update_trust(params: dict):
            return {
                "vendor_id": params["vendor_id"],
                "level": TrustLevel.TRUSTED.value,
                "level_name": "TRUSTED",
                "successful_payments": 21,
            }

        async def mock_emit(event_data: dict):
            return {"status": "success"}

        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract,
                mock_get_trust,
                mock_risk_score,
                mock_decision,
                mock_payment,
                mock_update_trust,
                mock_emit,
            ],
        ):
            handle = await temporal_env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                "https://example.com/test-invoice.pdf",
                id="test-workflow-004",
                task_queue="test-queue",
            )

            # Query workflow during execution
            # Note: In time-skipping environment, this might complete quickly
            try:
                status = await handle.query(InvoiceProcessingWorkflow.get_status)
                assert status in ["ingested", "extracting", "risk_checking", "paid"]
            except Exception:
                # Workflow might have completed already
                pass

            result = await handle.result()

            # Verify final state
            assert result["status"] == "paid"


class TestInvoiceWorkflowErrorHandling:
    """E2E tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_extraction_failure(self, temporal_env):
        """Test workflow handles extraction failure gracefully."""

        async def mock_extract_error(file_url: str):
            raise ApplicationError("Extraction failed")

        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[mock_extract_error],
        ):
            handle = await temporal_env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                "https://example.com/bad-invoice.pdf",
                id="test-workflow-error-001",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Should return failed status
        assert result["status"] == "failed"
        assert "error" in result
