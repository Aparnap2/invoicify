#!/usr/bin/env python3
"""
Invoicify End-to-End Full Workflow Test.

Tests the complete invoice processing pipeline:
1. Email ingestion (mocked via Azure Event Grid emulator)
2. PDF upload to Blob Storage (mocked)
3. Azure Document Intelligence OCR extraction (mocked)
4. LLM JSON parsing (OpenRouter free tier or mocked)
5. Trust Battery decision
6. QuickBooks sync (mocked via Mockoon)
7. Salesforce logging (mocked via Mockoon)
8. Audit ledger entry

Requirements:
- Mockoon running with quickbooks-mock.json and salesforce-mock.json
- Python 3.11+
- pytest, pytest-asyncio, httpx

Usage:
    pytest tests/e2e/test_full_workflow.py -v
    pytest tests/e2e/test_full_workflow.py -v --tb=short
    pytest tests/e2e/test_full_workflow.py::test_full_workflow -v -s

Environment Variables:
    MOCKOON_QUICKBOOKS_URL=http://localhost:3010
    MOCKOON_SALESFORCE_URL=http://localhost:3020
    MOCKOON_AUDIT_URL=http://localhost:3050
    INVOICIFY_API_URL=http://localhost:8001
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.e2e.generate_invoice import TestInvoiceData, TestInvoiceGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestConfig:
    """Test configuration from environment variables."""

    mockoon_quickbooks_url: str = "http://localhost:3010"
    mockoon_salesforce_url: str = "http://localhost:3020"
    mockoon_audit_url: str = "http://localhost:3050"
    invoicify_api_url: str = "http://localhost:8001"
    azure_blob_mock_url: str = "http://localhost:3030"
    azure_di_mock_url: str = "http://localhost:3040"

    timeout_seconds: int = 120  # 2 minutes max for full test
    request_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "TestConfig":
        """Load configuration from environment variables."""
        return cls(
            mockoon_quickbooks_url=os.getenv("MOCKOON_QUICKBOOKS_URL", "http://localhost:3010"),
            mockoon_salesforce_url=os.getenv("MOCKOON_SALESFORCE_URL", "http://localhost:3020"),
            mockoon_audit_url=os.getenv("MOCKOON_AUDIT_URL", "http://localhost:3050"),
            invoicify_api_url=os.getenv("INVOICIFY_API_URL", "http://localhost:8001"),
            azure_blob_mock_url=os.getenv("AZURE_BLOB_MOCK_URL", "http://localhost:3030"),
            azure_di_mock_url=os.getenv("AZURE_DI_MOCK_URL", "http://localhost:3040"),
            timeout_seconds=int(os.getenv("E2E_TIMEOUT_SECONDS", "120")),
            request_timeout=float(os.getenv("E2E_REQUEST_TIMEOUT", "30.0")),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test Report Data Structure
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestStepResult:
    """Result of a single test step."""

    step_name: str
    success: bool
    duration_ms: int
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None


@dataclass
class TestReport:
    """Complete test execution report."""

    test_id: str
    test_name: str
    start_time: str
    end_time: Optional[str] = None
    total_duration_ms: int = 0
    success: bool = True
    steps: List[TestStepResult] = field(default_factory=list)
    invoice_data: Optional[Dict[str, Any]] = None
    quickbooks_bill_id: Optional[str] = None
    salesforce_activity_id: Optional[str] = None
    audit_ledger_entries: List[Dict[str, Any]] = field(default_factory=list)

    def add_step(self, result: TestStepResult) -> None:
        """Add a test step result."""
        self.steps.append(result)
        if not result.success:
            self.success = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
            "steps": [
                {
                    "step_name": s.step_name,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "timestamp": s.timestamp,
                    "details": s.details,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "invoice_data": self.invoice_data,
            "quickbooks_bill_id": self.quickbooks_bill_id,
            "salesforce_activity_id": self.salesforce_activity_id,
            "audit_ledger_entries": self.audit_ledger_entries,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def print_summary(self) -> None:
        """Print test summary to console."""
        status = "✅ PASSED" if self.success else "❌ FAILED"
        print("\n" + "=" * 80)
        print(f"E2E TEST REPORT: {self.test_name}")
        print("=" * 80)
        print(f"Test ID:        {self.test_id}")
        print(f"Status:         {status}")
        print(f"Duration:       {self.total_duration_ms}ms")
        print(f"Start Time:     {self.start_time}")
        print(f"End Time:       {self.end_time}")
        print("-" * 80)
        print("STEPS:")
        for i, step in enumerate(self.steps, 1):
            step_status = "✓" if step.success else "✗"
            print(f"  {i}. [{step_status}] {step.step_name} ({step.duration_ms}ms)")
            if step.error:
                print(f"      Error: {step.error}")
        print("-" * 80)
        if self.invoice_data:
            print("INVOICE DATA:")
            print(f"  Number:       {self.invoice_data.get('invoice_number', 'N/A')}")
            print(f"  Vendor:       {self.invoice_data.get('vendor_name', 'N/A')}")
            print(f"  Amount:       ${self.invoice_data.get('total_amount', 0):,.2f}")
        if self.quickbooks_bill_id:
            print(f"QuickBooks ID:  {self.quickbooks_bill_id}")
        if self.salesforce_activity_id:
            print(f"Salesforce ID:  {self.salesforce_activity_id}")
        print(f"Audit Entries:  {len(self.audit_ledger_entries)}")
        print("=" * 80 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Mock Service Clients
# ─────────────────────────────────────────────────────────────────────────────

class MockServiceClient:
    """Base client for mock services."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health_check(self) -> bool:
        """Check if service is healthy."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for {self.base_url}: {e}")
            return False


class QuickBooksMockClient(MockServiceClient):
    """Client for QuickBooks Mockoon mock."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        super().__init__(base_url, timeout)
        self.realm_id = "913035307946357"

    async def get_oauth_token(self) -> Dict[str, Any]:
        """Get OAuth access token."""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "mock_client_id",
                "client_secret": "mock_client_secret",
            },
        )
        response.raise_for_status()
        return response.json()

    async def create_bill(self, bill_data: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
        """Create a bill in QuickBooks."""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v3/company/{self.realm_id}/bill",
            json=bill_data,
            headers={"X-Invoicify-Trace-Id": trace_id},
        )
        response.raise_for_status()
        return response.json()

    async def get_bill(self, bill_id: str) -> Dict[str, Any]:
        """Get a bill by ID."""
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v3/company/{self.realm_id}/bill/{bill_id}"
        )
        response.raise_for_status()
        return response.json()

    async def query_bills(self, doc_number: str) -> Dict[str, Any]:
        """Query bills by document number."""
        client = await self._get_client()
        query = f"SELECT * FROM Bill WHERE DocNumber = '{doc_number}'"
        response = await client.get(
            f"{self.base_url}/v3/company/{self.realm_id}/query",
            params={"query": query},
        )
        response.raise_for_status()
        return response.json()


class SalesforceMockClient(MockServiceClient):
    """Client for Salesforce Mockoon mock."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        super().__init__(base_url, timeout)
        self.api_version = "v58.0"

    async def get_oauth_token(self) -> Dict[str, Any]:
        """Get OAuth access token."""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/services/oauth2/token",
            data={
                "grant_type": "password",
                "username": "mock@invoicify.test",
                "password": "mock_password",
                "client_id": "mock_client_id",
                "client_secret": "mock_client_secret",
            },
        )
        response.raise_for_status()
        return response.json()

    async def create_activity_log(
        self,
        activity_data: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Create an Activity Log record."""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/services/data/{self.api_version}/sobjects/ActivityLog__c",
            json=activity_data,
            headers={
                "Authorization": "Bearer mock_token",
                "X-Invoicify-Trace-Id": trace_id,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_activity_log(self, activity_id: str) -> Dict[str, Any]:
        """Get an Activity Log by ID."""
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/services/data/{self.api_version}/sobjects/ActivityLog__c/{activity_id}",
            headers={"Authorization": "Bearer mock_token"},
        )
        response.raise_for_status()
        return response.json()

    async def query_activity_logs(self, invoice_id: str) -> Dict[str, Any]:
        """Query Activity Logs by invoice ID."""
        client = await self._get_client()
        query = f"SELECT Id, Invoice_ID__c, Trace_ID__c, Action_Type__c FROM ActivityLog__c WHERE Invoice_ID__c = '{invoice_id}'"
        response = await client.get(
            f"{self.base_url}/services/data/{self.api_version}/query",
            params={"q": query},
            headers={"Authorization": "Bearer mock_token"},
        )
        response.raise_for_status()
        return response.json()


class AuditLedgerClient(MockServiceClient):
    """Client for Audit Ledger mock service."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        super().__init__(base_url, timeout)
        self._entries: List[Dict[str, Any]] = []

    async def record_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Record an audit event."""
        # In a real implementation, this would POST to the audit service
        # For testing, we store in memory
        entry = {
            "id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event_data,
        }
        self._entries.append(entry)
        logger.info(f"Audit event recorded: {entry['id']}")
        return {"success": True, "event_id": entry["id"]}

    def get_entries(self) -> List[Dict[str, Any]]:
        """Get all recorded audit entries."""
        return self._entries.copy()

    def get_entries_for_invoice(self, invoice_id: str) -> List[Dict[str, Any]]:
        """Get audit entries for a specific invoice."""
        return [e for e in self._entries if e.get("invoice_id") == invoice_id]


# ─────────────────────────────────────────────────────────────────────────────
# Trust Battery Simulation
# ─────────────────────────────────────────────────────────────────────────────

class TrustBatterySimulator:
    """Simulates trust battery decision logic."""

    PROBATION_LIMIT = 0.0
    STANDARD_LIMIT = 500.0
    CORE_LIMIT = 5000.0
    STRATEGIC_LIMIT = 50000.0

    def __init__(self):
        self.vendor_trust_levels: Dict[str, str] = {}

    def set_trust_level(self, vendor_id: str, level: str) -> None:
        """Set trust level for a vendor."""
        self.vendor_trust_levels[vendor_id] = level

    def get_auto_approve_limit(self, vendor_id: str) -> float:
        """Get auto-approve limit for a vendor."""
        level = self.vendor_trust_levels.get(vendor_id, "PROBATION")
        limits = {
            "PROBATION": self.PROBATION_LIMIT,
            "STANDARD": self.STANDARD_LIMIT,
            "CORE": self.CORE_LIMIT,
            "STRATEGIC": self.STRATEGIC_LIMIT,
        }
        return limits.get(level, self.PROBATION_LIMIT)

    def make_decision(
        self,
        vendor_id: str,
        amount: float,
        confidence: float,
    ) -> Dict[str, Any]:
        """
        Make approval decision based on trust battery.

        Returns:
            Decision dict with action, reason, and metadata.
        """
        limit = self.get_auto_approve_limit(vendor_id)
        level = self.vendor_trust_levels.get(vendor_id, "PROBATION")

        if confidence < 0.75:
            return {
                "action": "HITL_REQUIRED",
                "reason": "Low extraction confidence",
                "trust_level": level,
                "auto_approve_limit": limit,
            }

        if amount > limit:
            return {
                "action": "HITL_REQUIRED",
                "reason": f"Amount ${amount:,.2f} exceeds auto-approve limit ${limit:,.2f}",
                "trust_level": level,
                "auto_approve_limit": limit,
            }

        return {
            "action": "AUTO_APPROVE",
            "reason": f"Vendor trust level {level}, amount within limit",
            "trust_level": level,
            "auto_approve_limit": limit,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main E2E Test Class
# ─────────────────────────────────────────────────────────────────────────────

class TestFullWorkflow:
    """
    End-to-end test for complete invoice processing workflow.

    Tests all 8 steps of the pipeline with mocked external services.
    """

    @pytest.fixture
    def config(self) -> TestConfig:
        """Get test configuration."""
        return TestConfig.from_env()

    @pytest.fixture
    async def quickbooks_client(self, config: TestConfig) -> QuickBooksMockClient:
        """Get QuickBooks mock client."""
        client = QuickBooksMockClient(config.mockoon_quickbooks_url)
        yield client
        await client.close()

    @pytest.fixture
    async def salesforce_client(self, config: TestConfig) -> SalesforceMockClient:
        """Get Salesforce mock client."""
        client = SalesforceMockClient(config.mockoon_salesforce_url)
        yield client
        await client.close()

    @pytest.fixture
    def audit_client(self, config: TestConfig) -> AuditLedgerClient:
        """Get Audit Ledger client."""
        return AuditLedgerClient(config.mockoon_audit_url)

    @pytest.fixture
    def trust_battery(self) -> TrustBatterySimulator:
        """Get trust battery simulator."""
        return TrustBatterySimulator()

    @pytest.fixture
    def invoice_generator(self, tmp_path: Path) -> TestInvoiceGenerator:
        """Get invoice PDF generator."""
        return TestInvoiceGenerator(output_dir=str(tmp_path))

    @pytest.mark.asyncio
    async def test_mock_services_health(
        self,
        config: TestConfig,
        quickbooks_client: QuickBooksMockClient,
        salesforce_client: SalesforceMockClient,
    ) -> None:
        """Test that all mock services are running and healthy."""
        # Check QuickBooks mock
        qb_healthy = await quickbooks_client.health_check()
        assert qb_healthy, "QuickBooks mock service is not healthy"

        # Check Salesforce mock
        sf_healthy = await salesforce_client.health_check()
        assert sf_healthy, "Salesforce mock service is not healthy"

        logger.info("All mock services are healthy")

    @pytest.mark.asyncio
    async def test_full_workflow(
        self,
        config: TestConfig,
        quickbooks_client: QuickBooksMockClient,
        salesforce_client: SalesforceMockClient,
        audit_client: AuditLedgerClient,
        trust_battery: TrustBatterySimulator,
        invoice_generator: TestInvoiceGenerator,
    ) -> None:
        """
        Test complete invoice processing workflow.

        Steps:
        1. Generate test invoice PDF
        2. Mock email ingestion (Event Grid)
        3. Mock PDF upload to Blob Storage
        4. Mock Azure Document Intelligence OCR
        5. LLM JSON parsing
        6. Trust Battery decision
        7. QuickBooks sync
        8. Salesforce logging
        9. Audit ledger entry
        """
        # Initialize test report
        report = TestReport(
            test_id=str(uuid4()),
            test_name="test_full_workflow",
            start_time=datetime.now(timezone.utc).isoformat(),
        )

        test_start = time.perf_counter()

        try:
            # ─────────────────────────────────────────────────────────────
            # Step 1: Generate Test Invoice PDF
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                invoice_data = TestInvoiceData(
                    vendor_name="Acme Corporation",
                    invoice_number=f"INV-E2E-{int(time.time())}",
                    line_items=[
                        InvoiceLineItem("Professional Services", 10, 150.00),
                    ],
                    tax_rate=0.08,
                    trust_level="STANDARD",
                    test_id=report.test_id,
                )

                pdf_path = invoice_generator.generate(invoice_data=invoice_data)

                # Read PDF bytes for hash
                pdf_bytes = pdf_path.read_bytes()
                pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="1. Generate Test Invoice PDF",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={
                            "pdf_path": str(pdf_path),
                            "pdf_hash": pdf_hash[:16] + "...",
                            "invoice_number": invoice_data.invoice_number,
                            "total_amount": invoice_data.total_amount,
                        },
                    )
                )

                report.invoice_data = {
                    "invoice_number": invoice_data.invoice_number,
                    "vendor_name": invoice_data.vendor_name,
                    "total_amount": invoice_data.total_amount,
                    "invoice_date": invoice_data.invoice_date.isoformat(),
                    "due_date": invoice_data.due_date.isoformat(),
                    "currency": invoice_data.currency,
                    "pdf_hash": pdf_hash,
                }

                logger.info(f"Generated invoice PDF: {pdf_path}")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="1. Generate Test Invoice PDF",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 2: Mock Email Ingestion (Event Grid)
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Simulate Event Grid event
                event_grid_event = {
                    "id": str(uuid4()),
                    "topic": "/invoice-ingestion",
                    "subject": f"/invoices/{invoice_data.invoice_number}",
                    "event_type": "Microsoft.Storage.BlobCreated",
                    "event_time": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "api": "PutBlob",
                        "clientRequestId": str(uuid4()),
                        "requestId": str(uuid4()),
                        "eTag": f'"{pdf_hash}"',
                        "contentType": "application/pdf",
                        "contentLength": len(pdf_bytes),
                        "blobType": "BlockBlob",
                        "url": f"http://localhost:3030/invoices/{invoice_data.invoice_number}.pdf",
                    },
                }

                # Record audit event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "EMAIL_INGESTED",
                    "actor": "system",
                    "details": event_grid_event,
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="2. Email Ingestion (Event Grid)",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"event_id": event_grid_event["id"]},
                    )
                )

                logger.info(f"Simulated email ingestion: {event_grid_event['id']}")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="2. Email Ingestion (Event Grid)",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 3: Mock PDF Upload to Blob Storage
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                blob_url = f"http://localhost:3030/invoices/{invoice_data.invoice_number}.pdf"

                # Record audit event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "BLOB_UPLOADED",
                    "actor": "system",
                    "details": {"blob_url": blob_url, "content_length": len(pdf_bytes)},
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="3. PDF Upload to Blob Storage",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"blob_url": blob_url},
                    )
                )

                logger.info(f"Simulated blob upload: {blob_url}")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="3. PDF Upload to Blob Storage",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 4: Mock Azure Document Intelligence OCR
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Simulated OCR extraction result
                ocr_result = {
                    "vendor_name": invoice_data.vendor_name,
                    "vendor_address": invoice_data.vendor_address,
                    "invoice_number": invoice_data.invoice_number,
                    "invoice_date": invoice_data.invoice_date.isoformat(),
                    "due_date": invoice_data.due_date.isoformat(),
                    "total_amount": invoice_data.total_amount,
                    "subtotal": invoice_data.subtotal,
                    "tax_amount": invoice_data.tax_amount,
                    "currency": invoice_data.currency,
                    "line_items": [
                        {
                            "description": item.description,
                            "quantity": item.quantity,
                            "unit_price": item.unit_price,
                            "total": item.total,
                        }
                        for item in invoice_data.line_items
                    ],
                    "confidence": 0.95,
                    "extraction_model": "azure-document-intelligence-mock",
                }

                # Record audit event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "OCR_EXTRACTED",
                    "actor": "azure_di",
                    "details": {
                        "confidence": ocr_result["confidence"],
                        "model": ocr_result["extraction_model"],
                    },
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="4. Azure Document Intelligence OCR",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"confidence": ocr_result["confidence"]},
                    )
                )

                logger.info(f"Simulated OCR extraction: {ocr_result['confidence']:.2f} confidence")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="4. Azure Document Intelligence OCR",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 5: LLM JSON Parsing
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Simulated LLM parsing (in real implementation, this calls OpenRouter)
                llm_parsed_data = {
                    "vendor_name": ocr_result["vendor_name"],
                    "invoice_number": ocr_result["invoice_number"],
                    "invoice_date": ocr_result["invoice_date"],
                    "due_date": ocr_result["due_date"],
                    "total_amount": ocr_result["total_amount"],
                    "currency": ocr_result["currency"],
                    "line_items": ocr_result["line_items"],
                    "parsing_confidence": 0.98,
                    "model": "openrouter-mock",
                }

                # Record audit event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "LLM_PARSED",
                    "actor": "llm",
                    "details": {
                        "parsing_confidence": llm_parsed_data["parsing_confidence"],
                        "model": llm_parsed_data["model"],
                    },
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="5. LLM JSON Parsing",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"parsing_confidence": llm_parsed_data["parsing_confidence"]},
                    )
                )

                logger.info(f"Simulated LLM parsing: {llm_parsed_data['parsing_confidence']:.2f} confidence")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="5. LLM JSON Parsing",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 6: Trust Battery Decision
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Set vendor trust level for testing
                vendor_id = f"vendor-{invoice_data.vendor_name.lower().replace(' ', '-')}"
                trust_battery.set_trust_level(vendor_id, invoice_data.trust_level)

                # Make decision
                decision = trust_battery.make_decision(
                    vendor_id=vendor_id,
                    amount=invoice_data.total_amount,
                    confidence=0.95,
                )

                # Record audit event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "TRUST_DECISION",
                    "actor": "trust_battery",
                    "details": decision,
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="6. Trust Battery Decision",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details=decision,
                    )
                )

                logger.info(f"Trust decision: {decision['action']} - {decision['reason']}")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="6. Trust Battery Decision",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 7: QuickBooks Sync
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Only sync if AUTO_APPROVE
                if decision["action"] == "AUTO_APPROVE":
                    # Prepare QuickBooks bill data
                    bill_data = {
                        "VendorRef": {
                            "value": "56",
                            "name": invoice_data.vendor_name,
                        },
                        "TxnDate": invoice_data.invoice_date.isoformat(),
                        "DueDate": invoice_data.due_date.isoformat(),
                        "DocNumber": invoice_data.invoice_number,
                        "PrivateNote": f"Processed by Invoicify - {report.test_id}",
                        "Line": [
                            {
                                "Id": str(i + 1),
                                "LineNum": i + 1,
                                "Description": item.description,
                                "Amount": item.total,
                                "DetailType": "AccountBasedExpenseLineDetail",
                                "AccountBasedExpenseLineDetail": {
                                    "AccountRef": {"value": "60", "name": "Professional Fees"},
                                    "BillableStatus": "NotBillable",
                                    "TaxCodeRef": {"value": "NON"},
                                },
                            }
                            for i, item in enumerate(invoice_data.line_items)
                        ],
                        "TotalAmt": invoice_data.total_amount,
                    }

                    # Create bill in QuickBooks mock
                    qb_response = await quickbooks_client.create_bill(
                        bill_data=bill_data,
                        trace_id=report.test_id,
                    )

                    bill_id = qb_response.get("Bill", {}).get("Id")
                    report.quickbooks_bill_id = bill_id

                    # Record audit event
                    await audit_client.record_event({
                        "invoice_id": invoice_data.invoice_number,
                        "event_type": "QUICKBOOKS_SYNCED",
                        "actor": "quickbooks_integration",
                        "details": {"bill_id": bill_id, "response": qb_response},
                    })
                else:
                    bill_id = None
                    logger.info("Skipping QuickBooks sync - not AUTO_APPROVE")

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="7. QuickBooks Sync",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"bill_id": bill_id, "action": decision["action"]},
                    )
                )

                logger.info(f"QuickBooks sync complete: {bill_id}")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="7. QuickBooks Sync",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 8: Salesforce Logging
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Prepare Salesforce Activity Log data
                activity_data = {
                    "Name": f"Invoice Processing - {invoice_data.invoice_number}",
                    "Invoice_ID__c": invoice_data.invoice_number,
                    "Trace_ID__c": report.test_id,
                    "Action_Type__c": decision["action"],
                    "QuickBooks_Bill_ID__c": report.quickbooks_bill_id,
                    "Processing_Status__c": "COMPLETED" if decision["action"] == "AUTO_APPROVE" else "PENDING_REVIEW",
                    "Notes__c": f"Automated processing via Invoicify. {decision['reason']}",
                }

                # Create Activity Log in Salesforce mock
                sf_response = await salesforce_client.create_activity_log(
                    activity_data=activity_data,
                    trace_id=report.test_id,
                )

                activity_id = sf_response.get("id")
                report.salesforce_activity_id = activity_id

                # Record audit event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "SALESFORCE_LOGGED",
                    "actor": "salesforce_integration",
                    "details": {"activity_id": activity_id, "response": sf_response},
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="8. Salesforce Logging",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"activity_id": activity_id},
                    )
                )

                logger.info(f"Salesforce logging complete: {activity_id}")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="8. Salesforce Logging",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

            # ─────────────────────────────────────────────────────────────
            # Step 9: Audit Ledger Finalization
            # ─────────────────────────────────────────────────────────────
            step_start = time.perf_counter()
            try:
                # Get all audit entries for this invoice
                audit_entries = audit_client.get_entries_for_invoice(invoice_data.invoice_number)
                report.audit_ledger_entries = audit_entries

                # Record final completion event
                await audit_client.record_event({
                    "invoice_id": invoice_data.invoice_number,
                    "event_type": "WORKFLOW_COMPLETED",
                    "actor": "system",
                    "details": {
                        "total_steps": 9,
                        "quickbooks_bill_id": report.quickbooks_bill_id,
                        "salesforce_activity_id": report.salesforce_activity_id,
                        "decision": decision["action"],
                    },
                })

                step_duration = int((time.perf_counter() - step_start) * 1000)

                report.add_step(
                    TestStepResult(
                        step_name="9. Audit Ledger Finalization",
                        success=True,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        details={"total_entries": len(audit_entries) + 1},
                    )
                )

                logger.info(f"Audit ledger finalized: {len(audit_entries) + 1} entries")

            except Exception as e:
                step_duration = int((time.perf_counter() - step_start) * 1000)
                report.add_step(
                    TestStepResult(
                        step_name="9. Audit Ledger Finalization",
                        success=False,
                        duration_ms=step_duration,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        error=str(e),
                    )
                )
                raise

        finally:
            # Finalize report
            report.end_time = datetime.now(timezone.utc).isoformat()
            report.total_duration_ms = int((time.perf_counter() - test_start) * 1000)

            # Print report
            report.print_summary()

            # Save report to file
            report_path = Path(__file__).parent / f"test_report_{report.test_id}.json"
            with open(report_path, "w") as f:
                f.write(report.to_json())

            logger.info(f"Test report saved to: {report_path}")

        # ─────────────────────────────────────────────────────────────
        # Assertions
        # ─────────────────────────────────────────────────────────────

        # Assert overall success
        assert report.success, f"E2E test failed. Report: {report.to_json()}"

        # Assert all steps passed
        failed_steps = [s for s in report.steps if not s.success]
        assert len(failed_steps) == 0, f"Failed steps: {[s.step_name for s in failed_steps]}"

        # Assert duration is within limit
        assert report.total_duration_ms < config.timeout_seconds * 1000, (
            f"Test took {report.total_duration_ms}ms, exceeded limit of {config.timeout_seconds * 1000}ms"
        )

        # Assert invoice data is present
        assert report.invoice_data is not None, "Invoice data is missing"
        assert report.invoice_data["invoice_number"] == invoice_data.invoice_number

        # Assert QuickBooks bill was created (for AUTO_APPROVE)
        if decision["action"] == "AUTO_APPROVE":
            assert report.quickbooks_bill_id is not None, "QuickBooks bill ID is missing"

        # Assert Salesforce activity was logged
        assert report.salesforce_activity_id is not None, "Salesforce activity ID is missing"

        # Assert audit ledger has entries
        assert len(report.audit_ledger_entries) > 0, "Audit ledger entries are missing"

        logger.info("All assertions passed!")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone Test Runner (for script execution)
# ─────────────────────────────────────────────────────────────────────────────

async def run_standalone_test() -> int:
    """
    Run E2E test as standalone script (not via pytest).

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    config = TestConfig.from_env()
    quickbooks_client = QuickBooksMockClient(config.mockoon_quickbooks_url)
    salesforce_client = SalesforceMockClient(config.mockoon_salesforce_url)
    audit_client = AuditLedgerClient(config.mockoon_audit_url)
    trust_battery = TrustBatterySimulator()
    invoice_generator = TestInvoiceGenerator()

    test = TestFullWorkflow()

    try:
        # Check health first
        print("\nChecking mock service health...")
        qb_healthy = await quickbooks_client.health_check()
        sf_healthy = await salesforce_client.health_check()

        if not qb_healthy:
            print(f"❌ QuickBooks mock not healthy at {config.mockoon_quickbooks_url}")
            return 1
        if not sf_healthy:
            print(f"❌ Salesforce mock not healthy at {config.mockoon_salesforce_url}")
            return 1

        print("✅ All mock services healthy\n")

        # Run the test
        await test.test_full_workflow(
            config=config,
            quickbooks_client=quickbooks_client,
            salesforce_client=salesforce_client,
            audit_client=audit_client,
            trust_battery=trust_battery,
            invoice_generator=invoice_generator,
        )

        return 0

    except Exception as e:
        logger.error(f"E2E test failed: {e}")
        return 1

    finally:
        await quickbooks_client.close()
        await salesforce_client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(run_standalone_test())
    sys.exit(exit_code)
