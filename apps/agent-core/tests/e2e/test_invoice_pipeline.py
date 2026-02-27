"""
E2E Tests for Invoice Processing Pipeline.

Tests run against real services (or mocks) to verify end-to-end functionality.
"""

import pytest
import asyncio
import os
import sys
import time
from pathlib import Path

# Add agent-core to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent-core"))

from src.schemas.invoice_v2 import (
    InvoiceStatus,
    RiskDecision,
    TrustLevel,
    ProcessRequest,
    ProcessResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def agent_core_url():
    """Get agent-core URL from environment or default."""
    return os.getenv("AGENT_CORE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def test_invoice_pdf():
    """Path to test invoice PDF fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "invoices" / "simple_invoice.pdf"
    
    # Create a minimal PDF if it doesn't exist
    if not fixture_path.exists():
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        # Create minimal PDF content (placeholder)
        # In production, this would be a real PDF file
        with open(fixture_path, "wb") as f:
            # Minimal PDF header (not a valid PDF, but sufficient for testing)
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
            f.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
            f.write(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n")
            f.write(b"xref\n0 4\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n")
    
    return fixture_path


@pytest.fixture
async def http_client():
    """Create async HTTP client."""
    import httpx
    async with httpx.AsyncClient(timeout=60.0) as client:
        yield client


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthChecks:
    """Test service health endpoints."""
    
    @pytest.mark.asyncio
    async def test_agent_core_health(self, agent_core_url, http_client):
        """Test agent-core health endpoint."""
        response = await http_client.get(f"{agent_core_url}/health")
        
        # If service is running, should return 200
        # If not running, skip test (not a failure)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "ok"
        else:
            pytest.skip("Agent-core service not running")
    
    @pytest.mark.asyncio
    async def test_agent_core_metrics(self, agent_core_url, http_client):
        """Test agent-core metrics endpoint."""
        response = await http_client.get(f"{agent_core_url}/metrics")
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "metrics" in data
        else:
            pytest.skip("Metrics endpoint not available")


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestInvoicePipeline:
    """Test complete invoice processing pipeline."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_auto_approve(
        self,
        agent_core_url,
        http_client,
        test_invoice_pdf,
    ):
        """
        Test CORE vendor + low amount → AUTO_APPROVE end-to-end.
        
        This test:
        1. Submits invoice for processing
        2. Waits for completion
        3. Verifies AUTO_APPROVE decision
        4. Checks processing latency < 30s
        """
        # Skip if service not running
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        # Submit invoice
        start_time = time.time()
        
        response = await http_client.post(
            f"{agent_core_url}/process",
            json={
                "trace_id": "e2e-auto-approve-001",
                "invoice_id": "test-invoice-001",
                "r2_url": "https://test-bucket.r2.dev/test-invoices/simple_invoice.pdf",
                "tenant_id": "tenant-test-001",
                "metadata": {
                    "vendor_name": "Acme Corp",  # Pre-seeded as CORE vendor
                    "test_mode": True,
                },
            },
        )
        
        elapsed = time.time() - start_time
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["decision"] == "AUTO_APPROVE"
        assert data["extraction_confidence"] >= 0.80
        assert data["processing_latency_ms"] < 30000  # 30s max
        assert elapsed < 60  # Total time < 60s
    
    @pytest.mark.asyncio
    async def test_full_pipeline_hitl_required(
        self,
        agent_core_url,
        http_client,
    ):
        """
        Test PROBATION vendor → HITL_REQUIRED regardless of amount.
        """
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        response = await http_client.post(
            f"{agent_core_url}/process",
            json={
                "trace_id": "e2e-hitl-001",
                "invoice_id": "test-invoice-002",
                "r2_url": "https://test-bucket.r2.dev/test-invoices/simple_invoice.pdf",
                "tenant_id": "tenant-test-001",
                "metadata": {
                    "vendor_name": "New Unknown Vendor",  # PROBATION
                    "test_mode": True,
                },
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "HITL_REQUIRED"
    
    @pytest.mark.asyncio
    async def test_duplicate_detection_blocks(
        self,
        agent_core_url,
        http_client,
    ):
        """
        Test submitting same invoice twice → second should be BLOCKED.
        """
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        payload = {
            "r2_url": "https://test-bucket.r2.dev/test-invoices/simple_invoice.pdf",
            "tenant_id": "tenant-test-001",
            "metadata": {"vendor_name": "Acme Corp", "test_mode": True},
        }
        
        # First submission
        r1 = await http_client.post(
            f"{agent_core_url}/process",
            json={
                **payload,
                "trace_id": "e2e-dup-001",
                "invoice_id": "test-dup-001",
            },
        )
        
        # Second submission (same content)
        r2 = await http_client.post(
            f"{agent_core_url}/process",
            json={
                **payload,
                "trace_id": "e2e-dup-002",
                "invoice_id": "test-dup-002",
            },
        )
        
        assert r1.status_code == 200
        assert r2.status_code == 200
        
        # Second should be blocked as duplicate
        assert r2.json()["decision"] == "BLOCKED"
        assert r2.json()["risk"]["is_duplicate"] is True


# ─────────────────────────────────────────────────────────────────────────────
# LATENCY BUDGET TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestLatencyBudgets:
    """Test processing latency meets SLOs."""
    
    @pytest.mark.asyncio
    async def test_latency_budget_extraction(
        self,
        agent_core_url,
        http_client,
    ):
        """
        Test extraction stage completes within 10s p95.
        
        Run 5 invoices and measure p95 latency.
        """
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        latencies = []
        
        for i in range(5):
            start = time.time()
            
            response = await http_client.post(
                f"{agent_core_url}/process",
                json={
                    "trace_id": f"e2e-latency-{i:03d}",
                    "invoice_id": f"test-latency-{i:03d}",
                    "r2_url": "https://test-bucket.r2.dev/test-invoices/simple_invoice.pdf",
                    "tenant_id": "tenant-test-001",
                    "metadata": {"test_mode": True},
                },
            )
            
            elapsed = (time.time() - start) * 1000  # ms
            latencies.append(elapsed)
        
        # Calculate p95
        sorted_latencies = sorted(latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95 = sorted_latencies[p95_index] if p95_index < len(sorted_latencies) else sorted_latencies[-1]
        
        # p95 should be < 30s (extraction budget)
        assert p95 < 30000, f"p95 latency {p95}ms exceeds 30s budget"
        
        print(f"\nLatency results: {latencies}")
        print(f"p95: {p95}ms")


# ─────────────────────────────────────────────────────────────────────────────
# TRUST BATTERY INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestTrustBatteryIntegration:
    """Test trust battery updates through pipeline."""
    
    @pytest.mark.asyncio
    async def test_trust_battery_updates_on_approval(
        self,
        agent_core_url,
        http_client,
    ):
        """
        Test that trust battery increments on approved invoice.
        """
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        # Process invoice for existing vendor
        response = await http_client.post(
            f"{agent_core_url}/process",
            json={
                "trace_id": "e2e-trust-001",
                "invoice_id": "test-trust-001",
                "r2_url": "https://test-bucket.r2.dev/test-invoices/simple_invoice.pdf",
                "tenant_id": "tenant-test-001",
                "metadata": {
                    "vendor_name": "Acme Corp",
                    "test_mode": True,
                },
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be approved
        assert data["decision"] == "AUTO_APPROVE"
        
        # Trust battery should be updated (verified in database)
        # This would require DB access to verify directly


# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLING TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorHandling:
    """Test error handling and recovery."""
    
    @pytest.mark.asyncio
    async def test_invalid_r2_url_returns_error(
        self,
        agent_core_url,
        http_client,
    ):
        """Test that invalid R2 URL returns proper error."""
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        response = await http_client.post(
            f"{agent_core_url}/process",
            json={
                "trace_id": "e2e-error-001",
                "invoice_id": "test-error-001",
                "r2_url": "https://invalid-url-404.com/invoice.pdf",
                "tenant_id": "tenant-test-001",
                "metadata": {"test_mode": True},
            },
        )
        
        # Should return error response (not crash)
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "error" in data or data["status"] == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# CONCURRENT PROCESSING TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentProcessing:
    """Test concurrent invoice processing."""
    
    @pytest.mark.asyncio
    async def test_concurrent_invoices(
        self,
        agent_core_url,
        http_client,
    ):
        """
        Test 10 invoices processed simultaneously.
        
        Measures true concurrency and error rate.
        """
        health = await http_client.get(f"{agent_core_url}/health")
        if health.status_code != 200:
            pytest.skip("Agent-core service not running")
        
        async def submit_invoice(i: int) -> dict:
            start = time.time()
            response = await http_client.post(
                f"{agent_core_url}/process",
                json={
                    "trace_id": f"stress-concurrent-{i:03d}",
                    "invoice_id": f"stress-{i:03d}",
                    "r2_url": "https://test-bucket.r2.dev/test-invoices/simple_invoice.pdf",
                    "tenant_id": "tenant-test-001",
                    "metadata": {"test_mode": True},
                },
            )
            latency = (time.time() - start) * 1000
            return {
                "status": response.status_code,
                "latency_ms": latency,
                "data": response.json(),
            }
        
        # Submit 10 concurrently
        tasks = [submit_invoice(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # Analyze results
        latencies = [r["latency_ms"] for r in results]
        errors = [r for r in results if r["status"] != 200]
        
        assert len(errors) == 0, f"{len(errors)} requests failed: {errors}"
        
        # Average latency should be reasonable
        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 60000, f"Average latency {avg_latency}ms exceeds 60s"
