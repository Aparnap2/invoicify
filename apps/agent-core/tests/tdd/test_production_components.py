"""
TDD Tests for QStash, QuickBooks Sync, Cache, and Audit Ledger.

Run:
    uv run pytest tests/tdd/test_production_components.py -v -s
"""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock


class TestQStashPublisher:
    """Test QStash durable queue."""
    
    @pytest.mark.asyncio
    async def test_publish_mock_mode(self):
        """Test publish in mock mode (no token)."""
        from src.queue.qstash_publisher import QStashPublisher
        
        publisher = QStashPublisher(token=None)
        
        result = await publisher.publish(
            url="http://localhost:8000/api/test",
            body={"test": "data"},
            deduplication_id="test-123",
        )
        
        assert result is not None
        assert result.startswith("mock-")
    
    @pytest.mark.asyncio
    async def test_publish_batch(self):
        """Test batch publishing."""
        from src.queue.qstash_publisher import QStashPublisher
        
        publisher = QStashPublisher(token=None)  # Mock mode
        
        batches = [
            {"invoices": [{"id": "1"}, {"id": "2"}]},
            {"invoices": [{"id": "3"}]},
        ]
        
        results = await publisher.publish_batch(
            url="http://localhost:8000/api/batch",
            batches=batches,
            base_deduplication_id="batch-test",
        )
        
        assert len(results) == 2
        assert all(r.startswith("mock-") for r in results)
    
    @pytest.mark.asyncio
    async def test_schedule_cron(self):
        """Test CRON scheduling."""
        from src.queue.qstash_publisher import QStashPublisher
        
        publisher = QStashPublisher(token=None)
        
        result = await publisher.schedule(
            url="http://localhost:8000/api/reconcile",
            body={"type": "reconciliation"},
            cron="30 17 * * *",
            deduplication_id="nightly-reconciliation",
        )
        
        assert result is not None
        assert result.startswith("mock-schedule-")


class TestQuickBooksSync:
    """Test idempotent QuickBooks sync."""
    
    @pytest.mark.asyncio
    async def test_sync_invoice_mock_mode(self):
        """Test sync in mock mode."""
        from src.execution.quickbooks_sync import QuickBooksSync
        
        sync = QuickBooksSync(redis_client=None)
        
        result = await sync.sync_invoice(
            invoice_data={
                "invoice_number": "INV-001",
                "vendor_name": "Test Vendor",
                "total_amount": 1000.0,
                "line_items": [{"description": "Item", "total": 1000.0}],
            },
            invoice_id="test-123",
        )
        
        assert "Bill" in result
        assert result["Bill"]["Id"].startswith("mock-bill-")
    
    @pytest.mark.asyncio
    async def test_idempotency_cache_hit(self):
        """Test idempotency cache prevents duplicate calls."""
        from src.execution.quickbooks_sync import QuickBooksSync, IdempotencyStore
        
        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"Bill": {"Id": "cached-123"}}'
        
        sync = QuickBooksSync(redis_client=mock_redis)
        
        result = await sync.sync_invoice(
            invoice_data={"invoice_number": "INV-001"},
            invoice_id="test-123",
        )
        
        assert result["Bill"]["Id"] == "cached-123"
        mock_redis.get.assert_called_once_with("idempotent:qb-bill-test-123")
    
    @pytest.mark.asyncio
    async def test_format_quickbooks_payload(self):
        """Test QuickBooks payload formatting."""
        from src.execution.quickbooks_sync import QuickBooksSync
        
        sync = QuickBooksSync()
        
        payload = sync._format_quickbooks_payload({
            "vendor_name": "Acme Supplies",
            "invoice_number": "INV-001",
            "total_amount": 3540.0,
            "line_items": [
                {"description": "Chairs", "quantity": 10, "unit_price": 150.0, "total": 1500.0},
            ],
            "vendor_email": "billing@acme.in",
            "invoice_date": "2024-01-15",
            "due_date": "2024-02-15",
        })
        
        assert payload["VendorRef"]["value"] == "Acme Supplies"
        assert payload["TotalAmt"] == 3540.0
        assert len(payload["Line"]) == 1


class TestAuditReceipt:
    """Test cryptographic audit receipts."""
    
    def test_generate_receipt(self):
        """Test receipt generation."""
        from src.audit.ledger import AuditReceiptGenerator
        
        generator = AuditReceiptGenerator()
        
        receipt = generator.generate_receipt(
            file_bytes=b"fake pdf content",
            quickbooks_id="qb-123",
            ai_reasoning="Low risk vendor",
            invoice_id="INV-001",
            tenant_id="tenant-001",
            decision="APPROVED",
        )
        
        assert receipt["invoice_id"] == "INV-001"
        assert receipt["quickbooks_id"] == "qb-123"
        assert receipt["document_hash"]  # SHA-256 hash
        assert receipt["hash_algorithm"] == "SHA-256"
        assert receipt["decision"] == "APPROVED"
    
    @pytest.mark.asyncio
    async def test_verify_receipt(self):
        """Test receipt verification."""
        from src.audit.ledger import AuditReceiptGenerator
        
        generator = AuditReceiptGenerator()
        
        file_bytes = b"fake pdf content"
        
        receipt = generator.generate_receipt(
            file_bytes=file_bytes,
            quickbooks_id="qb-123",
            ai_reasoning="Test",
            invoice_id="INV-001",
            tenant_id="tenant-001",
            decision="APPROVED",
        )
        
        # Verify matching bytes
        assert await generator.verify_receipt(file_bytes, receipt) is True
        
        # Verify non-matching bytes
        assert await generator.verify_receipt(b"different content", receipt) is False


class TestLLMRouter:
    """Test LLM router with fallback."""
    
    @pytest.mark.asyncio
    async def test_select_provider_groq_available(self):
        """Test Groq selection when under limit."""
        from src.llm.router import LLMRouter
        
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "10"  # Under 30 RPM limit
        
        router = LLMRouter(redis_client=mock_redis)
        
        provider = await router.select_provider()
        
        assert provider == "groq"
    
    @pytest.mark.asyncio
    async def test_select_provider_groq_exceeded(self):
        """Test fallback when Groq limit exceeded."""
        from src.llm.router import LLMRouter
        
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "50"  # Over 30 RPM limit
        
        # No Azure key
        with patch.dict(os.environ, {}, clear=True):
            router = LLMRouter(redis_client=mock_redis)
            provider = await router.select_provider()
            
            # Falls back to Ollama
            assert provider == "ollama"
    
    @pytest.mark.asyncio
    async def test_chat_completion_mock(self):
        """Test chat completion (mocked)."""
        from src.llm.router import LLMRouter
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Hello!"))],
            usage=MagicMock(total_tokens=10),
        )
        
        router = LLMRouter()
        router._clients["ollama"] = mock_client
        
        # Force Ollama selection
        router.select_provider = AsyncMock(return_value="ollama")
        
        response = await router.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        assert response == "Hello!"


class TestTrustBatteryCache:
    """Test L1/L2/L3 cache for trust battery."""
    
    @pytest.mark.asyncio
    async def test_l1_cache_hit(self):
        """Test L1 in-process cache hit."""
        from src.cache.trust_battery_cache import TrustBatteryCache, _L1_CACHE
        
        # Clear cache
        _L1_CACHE.clear()
        
        # Populate L1 with current timestamp
        import time
        _L1_CACHE["vendor-123"] = ("CORE", time.time())
        
        cache = TrustBatteryCache(redis_client=None, cosmos_client=None)
        
        # Should hit L1
        trust_level = await cache.get_vendor_trust("vendor-123")
        
        assert trust_level == "CORE"
    
    @pytest.mark.asyncio
    async def test_l2_cache_hit(self):
        """Test L2 Redis cache hit."""
        from src.cache.trust_battery_cache import TrustBatteryCache, _L1_CACHE
        
        # Clear L1
        _L1_CACHE.clear()
        
        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"STANDARD"
        
        cache = TrustBatteryCache(redis_client=mock_redis, cosmos_client=None)
        
        trust_level = await cache.get_vendor_trust("vendor-456")
        
        assert trust_level == "STANDARD"
        mock_redis.get.assert_called_once_with("trust:vendor-456")
    
    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        """Test cache invalidation."""
        from src.cache.trust_battery_cache import TrustBatteryCache, _L1_CACHE
        
        # Populate L1
        _L1_CACHE["vendor-789"] = ("CORE", 0)
        
        # Mock Redis
        mock_redis = AsyncMock()
        
        cache = TrustBatteryCache(redis_client=mock_redis, cosmos_client=None)
        
        await cache.invalidate_vendor_trust("vendor-789")
        
        # L1 should be cleared
        assert "vendor-789" not in _L1_CACHE
        
        # L2 should be deleted
        mock_redis.delete.assert_called_once_with("trust:vendor-789")


class TestDataMinimization:
    """Test data minimization policy."""
    
    def test_retention_policy(self):
        """Test retention policy values."""
        from src.audit.ledger import DataMinimizationPolicy
        
        policy = DataMinimizationPolicy()
        retention = policy.get_retention_policy()
        
        assert retention["pdf_blob"] == 259200  # 3 days
        assert retention["extracted_json"] == 604800  # 7 days
        assert retention["audit_receipt"] == 31536000  # 1 year
    
    def test_should_not_store_pdf(self):
        """Test PDF is not stored permanently."""
        from src.audit.ledger import DataMinimizationPolicy
        
        policy = DataMinimizationPolicy()
        
        assert policy.should_store_pdf() is False
    
    def test_required_fields(self):
        """Test minimum required fields."""
        from src.audit.ledger import DataMinimizationPolicy
        
        policy = DataMinimizationPolicy()
        fields = policy.get_required_fields()
        
        assert "invoice_id" in fields
        assert "document_hash" in fields
        assert "decision" in fields
        assert "timestamp" in fields
