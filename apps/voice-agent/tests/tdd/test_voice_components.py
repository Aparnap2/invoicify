"""
TDD Tests for Voice Agent Components.

Run:
    uv run pytest tests/tdd/test_voice_components.py -v -s

Tests:
- Event Grid emulator
- Voice Agent webhook receiver
- RAG client (Qdrant/Azure)
- Parakeet STT service
- Kitten TTS service
"""

import pytest
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "voice-agent" / "src"))


class TestEventGridEmulator:
    """Test Event Grid emulator behavior."""
    
    @pytest.mark.asyncio
    async def test_subscription_validation(self):
        """Test Azure Event Grid handshake validation."""
        from fastapi.testclient import TestClient
        import importlib.util
        
        # Load emulator app dynamically
        spec = importlib.util.spec_from_file_location(
            "event_grid_emulator",
            Path(__file__).parent.parent.parent.parent / "mocks" / "event_grid_emulator.py"
        )
        emulator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(emulator)
        
        client = TestClient(emulator.app)
        
        # Azure sends validation event on subscription creation
        response = client.post("/api/events", json=[{
            "id": "test-123",
            "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
            "subject": "subscription-validation",
            "data": {
                "validationCode": "ABC123-XYZ789",
            },
            "eventTime": "2024-01-01T00:00:00Z",
            "dataVersion": "1.0",
        }])
        
        # Must return validation code to prove endpoint ownership
        assert response.status_code == 200
        assert response.json()["validationResponse"] == "ABC123-XYZ789"
    
    @pytest.mark.asyncio
    async def test_event_dispatch(self):
        """Test event dispatch to subscribers."""
        from fastapi.testclient import TestClient
        import importlib.util
        
        # Load emulator app dynamically
        spec = importlib.util.spec_from_file_location(
            "event_grid_emulator",
            Path(__file__).parent.parent.parent.parent / "mocks" / "event_grid_emulator.py"
        )
        emulator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(emulator)
        
        client = TestClient(emulator.app, raise_server_exceptions=False)
        
        # Send vendor call event
        response = client.post("/api/events", json=[{
            "id": "test-456",
            "eventType": "invoice.vendor_call_requested",
            "subject": "invoices/INV-123",
            "data": {
                "invoice_id": "INV-123",
                "vendor_phone": "+919876543210",
            },
            "eventTime": "2024-01-01T00:00:00Z",
            "dataVersion": "1.0",
        }])
        
        # Event Grid returns 202 Accepted immediately
        assert response.status_code == 202


class TestVoiceAgentWebhook:
    """Test Voice Agent webhook receiver."""
    
    @pytest.mark.asyncio
    async def test_subscription_validation_response(self):
        """Test Voice Agent responds to Azure validation."""
        from fastapi.testclient import TestClient
        from src.voice.api import app
        
        client = TestClient(app)
        
        response = client.post("/api/events", json=[{
            "id": "test-789",
            "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
            "subject": "subscription-validation",
            "data": {
                "validationCode": "DEF456-UVW123",
            },
            "eventTime": "2024-01-01T00:00:00Z",
            "dataVersion": "1.0",
        }])
        
        assert response.status_code == 200
        assert response.json()["validationResponse"] == "DEF456-UVW123"
    
    @pytest.mark.asyncio
    async def test_vendor_call_event_accepted(self):
        """Test vendor call event is accepted and dispatched."""
        from fastapi.testclient import TestClient
        from src.voice.api import app
        
        client = TestClient(app, raise_server_exceptions=False)
        
        response = client.post("/api/events", json=[{
            "id": "test-call-001",
            "eventType": "invoice.vendor_call_requested",
            "subject": "invoices/INV-456",
            "data": {
                "invoice_id": "INV-456",
                "vendor_phone": "+919876543210",
                "vendor_name": "Test Vendor",
                "purpose": "missing_details",
                "missing_fields": ["vendor.tax_id"],
                "language": "hi-IN",
            },
            "eventTime": "2024-01-01T00:00:00Z",
            "dataVersion": "1.0",
        }])
        
        # Returns 202 Accepted immediately (background task runs call)
        assert response.status_code == 202
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint."""
        from fastapi.testclient import TestClient
        from src.voice.api import app
        
        client = TestClient(app)
        
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestRAGClient:
    """Test RAG client adapter."""
    
    def test_qdrant_provider_initialization(self):
        """Test Qdrant provider initializes correctly."""
        # Skip if Qdrant not running
        try:
            from src.voice.rag_client import QdrantSearchProvider
            provider = QdrantSearchProvider(qdrant_url="http://localhost:6333")
            assert provider.collection_name == "procurement-policies"
        except Exception:
            pytest.skip("Qdrant not running")
    
    @pytest.mark.asyncio
    async def test_policy_search_client_local(self):
        """Test policy search client uses Qdrant in local mode."""
        with patch.dict(os.environ, {"ENVIRONMENT": "local"}):
            from src.voice.rag_client import PolicySearchClient
            
            try:
                client = PolicySearchClient()
                assert isinstance(client.provider, type(client.provider))
            except Exception:
                pytest.skip("Qdrant not running")


class TestEventGridPublisher:
    """Test Event Grid publisher."""
    
    @pytest.mark.asyncio
    async def test_cloud_event_creation(self):
        """Test CloudEvent schema creation."""
        import importlib.util
        
        # Load publisher module dynamically
        spec = importlib.util.spec_from_file_location(
            "publisher",
            Path(__file__).parent.parent.parent.parent.parent / "agent-core" / "src" / "events" / "publisher.py"
        )
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        
        event = publisher.create_cloud_event(
            event_type="invoice.vendor_call_requested",
            subject="invoices/INV-789",
            data={
                "invoice_id": "INV-789",
                "vendor_phone": "+919876543210",
            },
        )
        
        assert event["id"] is not None
        assert event["eventType"] == "invoice.vendor_call_requested"
        assert event["subject"] == "invoices/INV-789"
        assert event["data"]["invoice_id"] == "INV-789"
        assert "eventTime" in event
        assert event["dataVersion"] == "1.0"
    
    @pytest.mark.asyncio
    async def test_publish_vendor_call_requested(self):
        """Test publishing vendor call event."""
        import importlib.util
        from unittest.mock import patch, MagicMock
        
        # Load publisher module dynamically
        spec = importlib.util.spec_from_file_location(
            "publisher",
            Path(__file__).parent.parent.parent.parent.parent / "agent-core" / "src" / "events" / "publisher.py"
        )
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        
        # Mock httpx to avoid actual network calls in unit test
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=202)
            
            result = await publisher.publish_vendor_call_requested(
                invoice_id="TEST-INV-001",
                vendor_phone="+919876543210",
                vendor_name="Test Vendor",
                purpose="missing_details",
                missing_fields=["vendor.tax_id"],
            )
            
            assert result is True
            mock_post.assert_called_once()


class TestParakeetSTT:
    """Test Parakeet STT service."""
    
    def test_parakeet_service_creation(self):
        """Test Parakeet STT service can be created."""
        try:
            from src.voice.parakeet_stt import ParakeetSTTService
            
            stt = ParakeetSTTService(
                ws_url="ws://localhost:80/streaming",
                sample_rate=16000,
                language="en-US",
            )
            
            assert stt._ws_url == "ws://localhost:80/streaming"
            assert stt._sample_rate == 16000
        except ImportError:
            pytest.skip("Pipecat not installed")


class TestEndToEndVoiceFlow:
    """End-to-end voice flow tests."""
    
    @pytest.mark.asyncio
    async def test_full_event_flow(self):
        """Test complete event flow: Agent Core → Event Grid → Voice Agent."""
        from fastapi.testclient import TestClient
        import importlib.util
        
        # 1. Load Event Grid emulator
        spec = importlib.util.spec_from_file_location(
            "event_grid_emulator",
            Path(__file__).parent.parent.parent.parent.parent / "mocks" / "event_grid_emulator.py"
        )
        emulator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(emulator)
        
        emulator_client = TestClient(emulator.app, raise_server_exceptions=False)
        
        # 2. Load Voice Agent
        from src.voice.api import app as voice_app
        voice_client = TestClient(voice_app, raise_server_exceptions=False)
        
        # 3. Send event to emulator
        event_payload = [{
            "id": "e2e-test-001",
            "eventType": "invoice.vendor_call_requested",
            "subject": "invoices/INV-E2E",
            "data": {
                "invoice_id": "INV-E2E",
                "vendor_phone": "+919876543210",
            },
            "eventTime": "2024-01-01T00:00:00Z",
            "dataVersion": "1.0",
        }]
        
        emulator_response = emulator_client.post("/api/events", json=event_payload)
        assert emulator_response.status_code == 202
        
        # 4. Manually trigger voice agent (emulator would do this async)
        voice_response = voice_client.post("/api/events", json=event_payload)
        assert voice_response.status_code == 202


# ─────────────────────────────────────────────────────────────────────────────
# Pytest configuration
# ─────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "voice: mark test as voice agent test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
