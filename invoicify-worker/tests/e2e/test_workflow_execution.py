"""
E2E tests for Temporal Workflow (TDD - Step 5)
RED phase: Tests will fail until implementation is written
"""

import pytest
import asyncio
from datetime import timedelta
from unittest.mock import patch, AsyncMock

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.invoice_processing import InvoiceProcessingWorkflow
from src.activities.extract import extract_invoice_data, VisionAPIError
from src.activities.anomaly import AnomalyDetector


class TestInvoiceProcessingWorkflow:
    """E2E tests for invoice processing workflow."""

    @pytest.fixture(scope="class")
    async def env(self):
        """Create test environment."""
        async with await WorkflowEnvironment.start_time_skipping() as e:
            yield e

    @pytest.mark.asyncio
    async def test_workflow_completes_successfully(self, env):
        """RED: Test that workflow completes with APPROVED status for low-risk invoice."""
        # Arrange
        file_url = "https://example.com/low-risk-invoice.pdf"

        # Mock the activities
        async def mock_extract(file_url: str):
            return {
                "vendor_name": "Trusted Vendor",
                "total_amount": 100.00,
                "invoice_number": "INV-001",
                "due_date": "2025-01-01",
                "currency": "USD",
                "confidence": 0.95,
            }

        async def mock_emit_event(data: dict):
            return {"status": "emitted"}

        # Act
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract,
                AnomalyDetector("test-vendor").is_anomaly,
                mock_emit_event,
            ],
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                file_url,
                id="test-workflow-001",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        assert result is not None
        assert isinstance(result, dict)
        assert "status" in result
        assert "risk_score" in result
        assert result["status"] == "APPROVED"  # Low amount = low risk

    @pytest.mark.asyncio
    async def test_workflow_returns_review_for_high_risk(self, env):
        """RED: Test that workflow returns REVIEW_REQUIRED for high-risk invoice."""
        # Arrange
        file_url = "https://example.com/high-risk-invoice.pdf"

        # Mock extraction with high amount
        async def mock_extract_high_amount(file_url: str):
            return {
                "vendor_name": "New Vendor",
                "total_amount": 50000.00,  # High amount
                "invoice_number": "INV-002",
                "due_date": "2025-01-01",
                "currency": "USD",
                "confidence": 0.95,
            }

        async def mock_emit_event(data: dict):
            return {"status": "emitted"}

        # Act
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract_high_amount,
                AnomalyDetector("test-vendor").is_anomaly,
                mock_emit_event,
            ],
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                file_url,
                id="test-workflow-002",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        assert result["status"] == "REVIEW_REQUIRED"
        assert result["risk_score"] > 0.8

    @pytest.mark.asyncio
    async def test_workflow_handles_extraction_error(self, env):
        """RED: Test that workflow handles Vision API errors gracefully."""
        # Arrange
        file_url = "https://example.com/bad-invoice.pdf"

        # Mock extraction failure
        async def mock_extract_error(file_url: str):
            raise VisionAPIError("Vision API failed")

        # Act & Assert
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[mock_extract_error],
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                file_url,
                id="test-workflow-003",
                task_queue="test-queue",
            )

            # Should fail after retries
            with pytest.raises(Exception):
                await handle.result()

    @pytest.mark.asyncio
    async def test_workflow_result_contains_all_fields(self, env):
        """RED: Test that workflow result contains all expected fields."""
        # Arrange
        file_url = "https://example.com/invoice.pdf"

        async def mock_extract(file_url: str):
            return {
                "vendor_name": "Test Vendor",
                "total_amount": 500.00,
                "invoice_number": "INV-003",
                "due_date": "2025-01-01",
                "currency": "USD",
                "confidence": 0.95,
            }

        async def mock_emit_event(data: dict):
            return {"status": "emitted"}

        # Act
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                mock_extract,
                AnomalyDetector("test-vendor").is_anomaly,
                mock_emit_event,
            ],
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                file_url,
                id="test-workflow-004",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        required_fields = [
            "status",
            "risk_score",
            "vendor_name",
            "total_amount",
            "invoice_number",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_workflow_activities_have_timeouts(self, env):
        """RED: Test that workflow activities have appropriate timeouts."""
        # This test verifies the workflow definition has timeouts set
        # We'll check by inspecting the workflow code

        import inspect

        source = inspect.getsource(InvoiceProcessingWorkflow.run)

        # Assert timeouts are configured
        assert "start_to_close_timeout" in source
        assert "timedelta" in source
