"""
E2E test for full Invoice Processing Workflow (Step 3)
Tests complete flow: Event -> Workflow -> Vision -> ML -> Decision
"""

import sys
import os
import pytest
import subprocess
import time
import signal

# Add src to path
sys.path.insert(0, "/home/aparna/Desktop/invoicify/python-worker/src")

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.invoice_processing import InvoiceProcessingWorkflow
from activities.extract import extract_invoice_data
from activities.anomaly import (
    AnomalyDetector,
    detect_anomaly_activity,
    learn_anomaly_activity,
)


@pytest.fixture(scope="module")
def mock_server():
    """Start mock server for testing."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "/home/aparna/Desktop/invoicify/python-worker/tests/mock_server.py",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)
    yield proc
    proc.send_signal(signal.SIGTERM)
    proc.wait()


@pytest.mark.asyncio
async def test_full_invoice_flow(mock_server):
    """Test complete workflow with real activities."""
    # Set environment for mock server
    os.environ["VISION_API_URL"] = "http://localhost:3000/extract"
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:19092"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Create detector
        detector = AnomalyDetector(vendor_id="test-vendor")

        async with Worker(
            env.client,
            task_queue="invoice-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                extract_invoice_data,
                detect_anomaly_activity,
            ],
        ):
            # Execute workflow
            result = await env.client.execute_workflow(
                InvoiceProcessingWorkflow.run,
                "http://test.com/invoice.pdf",
                id="test-invoice-1",
                task_queue="invoice-queue",
            )

            # Verify result structure
            assert "status" in result
            assert "risk_score" in result
            assert "vendor_name" in result
            assert "total_amount" in result
            assert "invoice_number" in result

            # Verify values from mock
            assert result["vendor_name"] == "Acme Corporation"
            assert result["total_amount"] == 1500.00
            assert result["invoice_number"] == "INV-2025-001"

            # Verify risk score is calculated
            assert isinstance(result["risk_score"], float)
            assert 0.0 <= result["risk_score"] <= 1.0

            # Verify status is set
            assert result["status"] in ["APPROVED", "REVIEW_REQUIRED", "REJECTED"]


@pytest.mark.asyncio
async def test_workflow_with_high_risk(mock_server):
    """Test workflow with high-risk invoice detection."""
    os.environ["VISION_API_URL"] = "http://localhost:3000/extract"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Train default detector on low amounts before workflow
        detector = AnomalyDetector(vendor_id="default")
        for _ in range(10):
            detector.learn(100.0)

        async with Worker(
            env.client,
            task_queue="invoice-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                extract_invoice_data,
                detect_anomaly_activity,
            ],
        ):
            result = await env.client.execute_workflow(
                InvoiceProcessingWorkflow.run,
                "http://test.com/invoice.pdf",
                id="test-invoice-high-risk",
                task_queue="invoice-queue",
            )

            # 1500 should be flagged for review
            assert result["status"] in ["REVIEW_REQUIRED", "REJECTED"]


@pytest.mark.asyncio
async def test_workflow_query_status(mock_server):
    """Test workflow status query."""
    os.environ["VISION_API_URL"] = "http://localhost:3000/extract"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="invoice-queue",
            workflows=[InvoiceProcessingWorkflow],
            activities=[
                extract_invoice_data,
                detect_anomaly_activity,
            ],
        ):
            handle = await env.client.start_workflow(
                InvoiceProcessingWorkflow.run,
                "http://test.com/invoice.pdf",
                id="test-invoice-query",
                task_queue="invoice-queue",
            )

            # Query status during execution
            status = await handle.query(InvoiceProcessingWorkflow.get_status)
            assert status in [
                "STARTED",
                "EXTRACTING",
                "ANALYZING",
                "DECIDING",
                "COMPLETED",
            ]

            # Wait for completion
            result = await handle.result()
            assert result["status"] is not None
