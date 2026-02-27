"""
Unit tests for Vendor Calling Agent.

Tests call queuing, execution, and result extraction.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
import sys
from pathlib import Path

# Add agent-core to path for schema imports
agent_core_path = Path(__file__).parent.parent.parent.parent / "agent-core" / "src"
sys.path.insert(0, str(agent_core_path))

from schemas.invoice_v2 import VoiceCallStatus, CallPurpose


# ─────────────────────────────────────────────────────────────────────────────
# CALL CONTEXT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestCallContext:
    """Test CallContext dataclass."""
    
    def test_call_context_creation(self):
        """Test creating call context."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme Supplies",
            purpose=CallPurpose.MISSING_DETAILS,
            language="hi-IN",
            tenant_id="tenant-001",
            missing_fields=["vendor.tax_id", "line_items"],
        )
        
        assert context.invoice_id == "inv-001"
        assert context.purpose == CallPurpose.MISSING_DETAILS
        assert len(context.missing_fields) == 2
    
    def test_call_context_defaults(self):
        """Test call context default values."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme",
            purpose=CallPurpose.RFP_QUOTE,
            language="hi-IN",
            tenant_id="tenant-001",
        )
        
        assert context.missing_fields == []
        assert context.invoice_data is None


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR CALLING AGENT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestVendorCallingAgent:
    """Test VendorCallingAgent."""
    
    @pytest.fixture
    def agent(self):
        """Create calling agent in mock mode."""
        from src.caller import VendorCallingAgent
        
        return VendorCallingAgent(config={"mock_mode": True})
    
    @pytest.mark.asyncio
    async def test_queue_call(self, agent):
        """Test queuing a vendor call."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme Supplies",
            purpose=CallPurpose.MISSING_DETAILS,
            language="hi-IN",
            tenant_id="tenant-001",
        )
        
        call_id = await agent.queue_call(context)
        
        assert call_id is not None
        assert len(call_id) == 36  # UUID length
    
    @pytest.mark.asyncio
    async def test_execute_call_mock(self, agent):
        """Test executing call in mock mode."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme Supplies",
            purpose=CallPurpose.MISSING_DETAILS,
            language="hi-IN",
            tenant_id="tenant-001",
        )
        
        result = await agent._execute_call("test-call-id", context)
        
        assert result.call_id == "test-call-id"
        assert result.status == VoiceCallStatus.COMPLETED
        assert result.transcript is not None
    
    def test_build_system_prompt_rfp(self, agent):
        """Test building system prompt for RFP quote."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme Supplies",
            purpose=CallPurpose.RFP_QUOTE,
            language="hi-IN",
            tenant_id="tenant-001",
        )
        
        prompt = agent._build_system_prompt(context)
        
        assert "RFP" in prompt or "quote" in prompt
        assert "Acme Supplies" in prompt
        assert "Price per unit" in prompt
    
    def test_build_system_prompt_followup(self, agent):
        """Test building system prompt for invoice followup."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme Supplies",
            purpose=CallPurpose.INVOICE_FOLLOWUP,
            language="hi-IN",
            tenant_id="tenant-001",
        )
        
        prompt = agent._build_system_prompt(context)
        
        assert "follow up" in prompt.lower() or "invoice" in prompt
        assert "inv-001" in prompt
    
    def test_build_system_prompt_missing(self, agent):
        """Test building system prompt for missing details."""
        from src.caller import CallContext
        
        context = CallContext(
            invoice_id="inv-001",
            vendor_phone="+919999999999",
            vendor_name="Acme Supplies",
            purpose=CallPurpose.MISSING_DETAILS,
            language="hi-IN",
            tenant_id="tenant-001",
            missing_fields=["vendor.tax_id", "payment_terms"],
        )
        
        prompt = agent._build_system_prompt(context)
        
        assert "missing" in prompt.lower() or "clarification" in prompt.lower()
        assert "vendor.tax_id" in prompt
        assert "payment_terms" in prompt
    
    @pytest.mark.asyncio
    async def test_extract_call_result_rfp(self, agent):
        """Test extracting call result for RFP."""
        transcript = """
Bot: Hi, I'm calling about a quote request. What's your price per unit?
Vendor: Hamara price hai 500 rupaye per unit.
Bot: And delivery timeline?
Vendor: 30 din lagenge.
Bot: Payment terms?
Vendor: 100% advance.
"""
        
        # Mock the LLM client
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"quoted_price": 500, "delivery_days": 30, "payment_terms": "100% advance"}'))]
        )
        agent.service_factory.get_llm = MagicMock(return_value=(mock_llm, "qwen2.5:7b"))
        
        result = await agent._extract_call_result(
            transcript=transcript,
            purpose=CallPurpose.RFP_QUOTE,
        )
        
        assert result is not None
        assert "quoted_price" in result or "payment_terms" in result
    
    @pytest.mark.asyncio
    async def test_extract_call_result_missing_details(self, agent):
        """Test extracting call result for missing details."""
        transcript = """
Bot: Hi, I need clarification on your invoice.
Vendor: Haan boliye.
Bot: What is your tax ID?
Vendor: Hamara GST number hai 27AABCU9603R1ZM.
Bot: And payment terms?
Vendor: Net 30 days.
"""
        
        # Mock the LLM client
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"tax_id": "27AABCU9603R1ZM", "payment_terms": "Net 30"}'))]
        )
        agent.service_factory.get_llm = MagicMock(return_value=(mock_llm, "qwen2.5:7b"))
        
        result = await agent._extract_call_result(
            transcript=transcript,
            purpose=CallPurpose.MISSING_DETAILS,
        )
        
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestConvenienceFunctions:
    """Test convenience functions for calling."""
    
    @pytest.mark.asyncio
    async def test_queue_vendor_call(self):
        """Test queue_vendor_call convenience function."""
        from src.caller import queue_vendor_call
        
        with patch('src.caller.VendorCallingAgent') as MockAgent:
            mock_agent = AsyncMock()
            mock_agent.queue_call.return_value = "test-call-id"
            MockAgent.return_value = mock_agent
            
            call_id = await queue_vendor_call(
                invoice_id="inv-001",
                vendor_phone="+919999999999",
                vendor_name="Acme Supplies",
                purpose="missing_details",
                language="hi-IN",
                tenant_id="tenant-001",
                missing_fields=["vendor.tax_id"],
            )
            
            assert call_id == "test-call-id"


# ─────────────────────────────────────────────────────────────────────────────
# CALL RESULT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestCallResult:
    """Test CallResult dataclass."""
    
    def test_call_result_completed(self):
        """Test call result for completed call."""
        from src.caller import CallResult
        
        result = CallResult(
            call_id="call-001",
            status=VoiceCallStatus.COMPLETED,
            duration_seconds=120,
            transcript="Vendor confirmed details",
            extracted_data={"tax_id": "27AABCU9603R1ZM"},
            total_latency_ms=3500,
            stt_latency_ms=150,
            llm_latency_ms=200,
            tts_latency_ms=180,
        )
        
        assert result.status == VoiceCallStatus.COMPLETED
        assert result.duration_seconds == 120
        assert result.total_latency_ms == 3500
    
    def test_call_result_failed(self):
        """Test call result for failed call."""
        from src.caller import CallResult
        
        result = CallResult(
            call_id="call-001",
            status=VoiceCallStatus.FAILED,
            duration_seconds=None,
            transcript=None,
            extracted_data=None,
            total_latency_ms=None,
            stt_latency_ms=None,
            llm_latency_ms=None,
            tts_latency_ms=None,
        )
        
        assert result.status == VoiceCallStatus.FAILED
        assert result.duration_seconds is None
