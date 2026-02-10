"""
Integration tests for Temporal Workflow
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import timedelta

from temporalio.testing import WorkflowEnvironment
from temporalio.client import Client
from temporalio.worker import Worker, UnsandboxedWorkflowRunner
from temporalio import activity

from temporal.workflows.invoice import InvoiceProcessingWorkflow
from temporal.activities.agents import analyst_evaluate, critic_review
from temporal.activities.anomaly import detect_anomaly
from temporal.schemas import InvoiceInput


# Create activity definitions for testing
@activity.defn
async def _test_analyst_evaluate(invoice_data):
    """Test wrapper for analyst_evaluate."""
    return await analyst_evaluate(invoice_data)


@activity.defn
async def _test_critic_review(invoice_data, analyst_proposal):
    """Test wrapper for critic_review."""
    return await critic_review(invoice_data, analyst_proposal)


@activity.defn
async def _test_detect_anomaly(invoice_data):
    """Test wrapper for detect_anomaly."""
    return await detect_anomaly(invoice_data)


@pytest_asyncio.fixture
async def env():
    """Create test environment."""
    async with await WorkflowEnvironment.start_time_skipping() as e:
        yield e


class TestTemporalWorkflow:
    """Integration tests for Temporal workflows."""

    @pytest.mark.skip(reason="Temporal workflow tests require real Temporal server - TODO: Fix sandbox issues")
    @pytest.mark.asyncio
    async def test_workflow_executes_successfully(self, env):
        """Test that workflow completes without errors."""
        # Arrange - Use a trusted vendor with history to avoid HITL
        invoice_input = InvoiceInput(
            invoice_id="test-001",
            vendor_name="Trusted Vendor",  # Will have history in mocked activity
            total_amount=100.0,
            invoice_number="INV-001",
        )

        # Mock the analyst_evaluate to return auto-approve
        @activity.defn
        async def _mock_analyst_evaluate(invoice_data):
            from temporal.activities.agents import AnalystProposal
            return AnalystProposal(
                proposed_action="AUTO_APPROVE",
                confidence=0.95,
                anomalies=[],
                vendor_patterns=[],
                reasoning=["Trusted vendor with normal amount"],
            )

        # Mock the critic_review to allow payment
        @activity.defn
        async def _mock_critic_review(invoice_data, analyst_proposal):
            return {
                "can_proceed": True,
                "blocked": False,
                "block_reason": None,
                "risk_score": 0.1,
                "signals": [],
                "reasoning": ["All checks passed"],
            }

        # Mock detect_anomaly
        @activity.defn
        async def _mock_detect_anomaly(invoice_data):
            return {"score": 0.1, "is_anomaly": False}

        # Act
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[_mock_analyst_evaluate, _mock_critic_review, _mock_detect_anomaly],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                invoice_input,
                id="test-workflow-001",
                task_queue="test-queue",
            )

            result = await handle.result()

        # Assert
        assert result is not None
        assert result.invoice_id == "test-001"
        assert result.status == "AUTO_APPROVE"

    @pytest.mark.skip(reason="Temporal workflow tests require real Temporal server - TODO: Fix sandbox issues")
    @pytest.mark.asyncio
    async def test_workflow_retries_failed_activity(self, env):
        """Test that workflow retries failed activities."""
        # This tests Temporal's built-in retry behavior
        # Arrange
        call_count = 0

        @activity.defn
        async def flaky_activity(invoice_data):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return {"status": "success"}

        # Act & Assert
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[flaky_activity],
            disable_eager_activity_execution=True,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                InvoiceInput(invoice_id="test-retry"),
                id="test-retry-workflow",
                task_queue="test-queue",
            )

            result = await handle.result()
            assert call_count == 3  # Retried twice

    @pytest.mark.skip(reason="Temporal workflow tests require real Temporal server - TODO: Fix sandbox issues")
    @pytest.mark.asyncio
    async def test_workflow_handles_signal(self, env):
        """Test that workflow can receive and handle signals."""
        # Arrange
        invoice_input = InvoiceInput(
            invoice_id="test-signal",
            vendor_name="Test Vendor",
            total_amount=100.0,
            invoice_number="INV-001",
        )

        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[_test_analyst_evaluate, _test_critic_review],
            disable_eager_activity_execution=True,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                invoice_input,
                id="test-signal-workflow",
                task_queue="test-queue",
            )

            # Wait for workflow to reach approval stage
            await asyncio.sleep(1)

            # Send approval signal
            await handle.signal(
                InvoiceProcessingWorkflow.approval_response,
                approved=True,
                comments="Approved by test",
            )

            result = await handle.result()

        # Assert
        assert result.approved is True

    @pytest.mark.skip(reason="Temporal workflow tests require real Temporal server - TODO: Fix sandbox issues")
    @pytest.mark.asyncio
    async def test_workflow_timeout(self, env):
        """Test workflow execution timeout."""

        # Arrange
        @activity.defn
        async def slow_activity(*args):
            await asyncio.sleep(10)
            return {}

        # Act & Assert
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[slow_activity],
            disable_eager_activity_execution=True,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                InvoiceInput(invoice_id="test-timeout"),
                id="test-timeout-workflow",
                task_queue="test-queue",
                execution_timeout=timedelta(seconds=2),
            )

            with pytest.raises(Exception):
                await handle.result()

    @pytest.mark.skip(reason="Temporal workflow tests require real Temporal server - TODO: Fix sandbox issues")
    @pytest.mark.asyncio
    async def test_workflow_query(self, env):
        """Test querying workflow state."""
        # Arrange
        invoice_input = InvoiceInput(
            invoice_id="test-query",
            vendor_name="Test Vendor",
            total_amount=100.0,
            invoice_number="INV-001",
        )

        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[_test_analyst_evaluate],
            disable_eager_activity_execution=True,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                invoice_input,
                id="test-query-workflow",
                task_queue="test-queue",
            )

            # Query workflow state
            status = await handle.query(InvoiceProcessingWorkflow.get_status)

            await handle.result()

        # Assert
        assert status is not None
