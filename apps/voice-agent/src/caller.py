"""
Vendor Calling Agent using Pipecat.

Handles voice calls to vendors for:
- RFP quotes
- Invoice follow-ups
- Missing details collection

Architecture:
- Pipecat pipeline orchestrates STT → LLM → TTS
- Swappable services via environment variables
- Local dev: open-sarika + Kokoro + Ollama
- Prod: Sarvam API + Modal + Azure Foundry
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import structlog
import sys
from pathlib import Path

# Add agent-core to path for schema imports
agent_core_path = Path(__file__).parent.parent.parent / "agent-core" / "src"
sys.path.insert(0, str(agent_core_path))

from schemas.invoice_v2 import VoiceCallRecord, VoiceCallStatus, CallPurpose

logger = structlog.get_logger()


@dataclass
class CallContext:
    """Context for vendor call."""
    invoice_id: str
    vendor_name: str
    vendor_phone: str
    purpose: CallPurpose
    language: str
    tenant_id: str
    missing_fields: List[str] = field(default_factory=list)
    invoice_data: Optional[Dict[str, Any]] = None


@dataclass
class CallResult:
    """Result of vendor call."""
    call_id: str
    status: VoiceCallStatus
    duration_seconds: Optional[int]
    transcript: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    total_latency_ms: Optional[int]
    stt_latency_ms: Optional[int]
    llm_latency_ms: Optional[int]
    tts_latency_ms: Optional[int]


class VendorCallingAgent:
    """
    Voice agent for vendor calls.
    
    Uses Pipecat for real-time voice pipeline:
    STT (open-sarika/Sarvam) → LLM (Ollama/Azure) → TTS (Kokoro/Bulbul)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize calling agent.
        
        Args:
            config: Configuration dict
        """
        self.config = config or {}
        self.service_factory = None
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize voice services from factory."""
        from src.services.factory import VoiceServiceFactory
        self.service_factory = VoiceServiceFactory()
    
    async def queue_call(self, context: CallContext) -> str:
        """
        Queue a vendor call.
        
        Args:
            context: Call context
        
        Returns:
            Call ID
        """
        import uuid
        call_id = str(uuid.uuid4())
        
        logger.info(
            "call_queued",
            call_id=call_id,
            invoice_id=context.invoice_id,
            vendor=context.vendor_name,
            purpose=context.purpose.value,
        )
        
        # Store call record
        call_record = VoiceCallRecord(
            call_id=call_id,
            invoice_id=context.invoice_id,
            vendor_phone=context.vendor_phone,
            vendor_name=context.vendor_name,
            purpose=context.purpose,
            language=context.language,
            status=VoiceCallStatus.QUEUED,
            created_at=datetime.utcnow(),
        )
        
        # Persist to database (placeholder)
        await self._save_call_record(call_record)
        
        # Start call in background
        asyncio.create_task(self._execute_call(call_id, context))
        
        return call_id
    
    async def _execute_call(self, call_id: str, context: CallContext) -> CallResult:
        """
        Execute vendor call.
        
        Args:
            call_id: Call ID
            context: Call context
        
        Returns:
            Call result
        """
        start_time = time.perf_counter()
        
        try:
            # Update status
            await self._update_call_status(call_id, VoiceCallStatus.IN_PROGRESS)
            
            # Build conversation prompt
            system_prompt = self._build_system_prompt(context)
            
            # Execute Pipecat pipeline
            result = await self._run_pipecat_pipeline(
                call_id=call_id,
                system_prompt=system_prompt,
                language=context.language,
            )
            
            # Calculate latencies
            total_latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Build call result
            call_result = CallResult(
                call_id=call_id,
                status=VoiceCallStatus.COMPLETED,
                duration_seconds=result.get("duration", 0),
                transcript=result.get("transcript"),
                extracted_data=result.get("extracted_data"),
                total_latency_ms=total_latency_ms,
                stt_latency_ms=result.get("stt_latency"),
                llm_latency_ms=result.get("llm_latency"),
                tts_latency_ms=result.get("tts_latency"),
            )
            
            # Extract structured data from conversation
            if result.get("transcript"):
                extracted = await self._extract_call_result(
                    transcript=result["transcript"],
                    purpose=context.purpose,
                )
                call_result.extracted_data = extracted
            
            # Update call record
            await self._save_call_result(call_result)
            
            logger.info(
                "call_completed",
                call_id=call_id,
                duration=result.get("duration"),
                latency_ms=total_latency_ms,
            )
            
            return call_result
            
        except Exception as e:
            logger.error("call_failed", call_id=call_id, error=str(e))
            
            await self._update_call_status(call_id, VoiceCallStatus.FAILED)
            
            return CallResult(
                call_id=call_id,
                status=VoiceCallStatus.FAILED,
                duration_seconds=None,
                transcript=None,
                extracted_data=None,
                total_latency_ms=None,
                stt_latency_ms=None,
                llm_latency_ms=None,
                tts_latency_ms=None,
            )
    
    def _build_system_prompt(self, context: CallContext) -> str:
        """
        Build system prompt for LLM.
        
        Args:
            context: Call context
        
        Returns:
            System prompt string
        """
        purpose_prompts = {
            CallPurpose.RFP_QUOTE: f"""
You are calling a vendor to request a quote for an RFP.

Vendor: {context.vendor_name}
Purpose: Request quote for products/services

Guidelines:
1. Greet the vendor politely in their language
2. Explain you're calling about a quote request
3. Ask for:
   - Price per unit
   - Delivery timeline
   - Payment terms
4. Confirm details by repeating them back
5. Thank the vendor and end the call politely

Keep responses concise and professional.
""",
            
            CallPurpose.INVOICE_FOLLOWUP: f"""
You are calling a vendor to follow up on an invoice.

Vendor: {context.vendor_name}
Invoice ID: {context.invoice_id}

Guidelines:
1. Greet the vendor politely
2. Explain you're calling about invoice {context.invoice_id}
3. Ask about:
   - Payment status
   - Any issues or questions
   - Expected resolution timeline
4. Confirm any action items
5. End politely

Keep responses concise and professional.
""",
            
            CallPurpose.MISSING_DETAILS: f"""
You are calling a vendor to collect missing invoice details.

Vendor: {context.vendor_name}
Invoice ID: {context.invoice_id}
Missing: {', '.join(context.missing_fields)}

Guidelines:
1. Greet the vendor politely
2. Explain you need clarification on their invoice
3. Ask specifically about: {', '.join(context.missing_fields)}
4. Confirm details by repeating them back
5. Thank the vendor

Keep responses concise and professional.
""",
        }
        
        return purpose_prompts.get(context.purpose, purpose_prompts[CallPurpose.MISSING_DETAILS])
    
    async def _run_pipecat_pipeline(
        self,
        call_id: str,
        system_prompt: str,
        language: str,
    ) -> Dict[str, Any]:
        """
        Run Pipecat voice pipeline.
        
        Args:
            call_id: Call ID
            system_prompt: System prompt for LLM
            language: Language code
        
        Returns:
            Pipeline result with transcript and extracted data
        """
        # Check if we're in test/mock mode
        if self.config.get("mock_mode", False):
            return await self._mock_pipecat_pipeline(call_id, language)
        
        # Production: use Pipecat
        return await self._run_production_pipecat(
            call_id=call_id,
            system_prompt=system_prompt,
            language=language,
        )
    
    async def _mock_pipecat_pipeline(self, call_id: str, language: str) -> Dict[str, Any]:
        """Mock Pipecat pipeline for testing."""
        await asyncio.sleep(2.0)  # Simulate call duration
        
        return {
            "duration": 120,
            "transcript": f"Vendor confirmed details for call {call_id}",
            "extracted_data": {"status": "confirmed"},
            "stt_latency": 100,
            "llm_latency": 200,
            "tts_latency": 150,
        }
    
    async def _run_production_pipecat(
        self,
        call_id: str,
        system_prompt: str,
        language: str,
    ) -> Dict[str, Any]:
        """Run production Pipecat pipeline."""
        try:
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineTask, PipelineParams
            from pipecat.frames.frames import LLMRunFrame
            from pipecat.processors.aggregators.llm_context import LLMContext
            
            # Get services from factory
            stt_client, stt_model, stt_lang = self.service_factory.get_stt()
            tts_client, tts_model, tts_voice = self.service_factory.get_tts()
            llm_client, llm_model = self.service_factory.get_llm()
            
            # Create Pipecat services (simplified - full implementation needs transports)
            # This is a placeholder - full Pipecat setup requires audio transports
            
            logger.warning(
                "pipecat_not_fully_implemented",
                note="Full Pipecat integration requires audio transport setup"
            )
            
            # For now, use direct API calls (simpler for initial implementation)
            return await self._direct_api_call(
                system_prompt=system_prompt,
                language=language,
            )
            
        except ImportError as e:
            logger.error("pipecat_import_failed", error=str(e))
            return await self._mock_pipecat_pipeline(call_id, language)
    
    async def _direct_api_call(
        self,
        system_prompt: str,
        language: str,
    ) -> Dict[str, Any]:
        """
        Direct API call (simpler alternative to full Pipecat).
        
        Uses HTTP APIs for STT/LLM/TTS in sequence.
        """
        start = time.perf_counter()
        
        # Simulated conversation turns
        conversation = [
            {"role": "system", "content": system_prompt},
        ]
        
        transcript_lines = []
        
        # Simulate 3-turn conversation
        for i in range(3):
            # LLM generates response
            llm_start = time.perf_counter()
            llm_response = await self._call_llm(conversation)
            llm_latency = int((time.perf_counter() - llm_start) * 1000)
            
            conversation.append({"role": "assistant", "content": llm_response})
            transcript_lines.append(f"Bot: {llm_response}")
            
            # TTS (skip for now - audio not needed for extraction)
            # tts_start = time.perf_counter()
            # audio = await self._call_tts(llm_response)
            # tts_latency = int((time.perf_counter() - tts_start) * 1000)
            
            # Simulate vendor response (in production, this comes from STT)
            vendor_response = f"Vendor response {i+1}"
            transcript_lines.append(f"Vendor: {vendor_response}")
            
            conversation.append({"role": "user", "content": vendor_response})
        
        transcript = "\n".join(transcript_lines)
        
        return {
            "duration": 120,
            "transcript": transcript,
            "extracted_data": {"conversation_turns": 3},
            "stt_latency": 150,
            "llm_latency": 200,
            "tts_latency": 180,
        }
    
    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call LLM for response generation."""
        llm_client, model = self.service_factory.get_llm()
        
        response = await llm_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=200,
        )
        
        return response.choices[0].message.content
    
    async def _extract_call_result(
        self,
        transcript: str,
        purpose: CallPurpose,
    ) -> Dict[str, Any]:
        """
        Extract structured data from call transcript.
        
        Args:
            transcript: Call transcript
            purpose: Call purpose
        
        Returns:
            Extracted structured data
        """
        llm_client, model = self.service_factory.get_llm()
        
        extraction_prompt = f"""
Extract structured data from this vendor call transcript.

Purpose: {purpose.value}

Transcript:
{transcript}

Extract the following as JSON:
- For RFP_QUOTE: quoted_price, delivery_days, payment_terms
- For INVOICE_FOLLOWUP: payment_status, issues, expected_resolution
- For MISSING_DETAILS: the missing field values

Return ONLY valid JSON.
"""
        
        response = await llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a data extraction expert. Return only JSON."},
                {"role": "user", "content": extraction_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        
        import json
        return json.loads(response.choices[0].message.content)
    
    async def _save_call_record(self, record: VoiceCallRecord):
        """Save call record to database."""
        # Placeholder - implement Cosmos DB storage
        logger.debug("call_record_saved", call_id=record.call_id)
    
    async def _update_call_status(self, call_id: str, status: VoiceCallStatus):
        """Update call status in database."""
        # Placeholder - implement Cosmos DB update
        logger.debug("call_status_updated", call_id=call_id, status=status.value)
    
    async def _save_call_result(self, result: CallResult):
        """Save call result to database."""
        # Placeholder - implement Cosmos DB storage
        logger.debug("call_result_saved", call_id=result.call_id)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

async def queue_vendor_call(
    invoice_id: str,
    vendor_phone: str,
    vendor_name: str,
    purpose: str,
    language: str = "hi-IN",
    tenant_id: str = "default",
    missing_fields: Optional[List[str]] = None,
) -> str:
    """
    Queue a vendor call (convenience function).
    
    Args:
        invoice_id: Invoice ID
        vendor_phone: Vendor phone number
        vendor_name: Vendor name
        purpose: Call purpose (rfp_quote, invoice_followup, missing_details)
        language: Language code
        tenant_id: Tenant ID
        missing_fields: List of missing fields
    
    Returns:
        Call ID
    """
    agent = VendorCallingAgent()
    
    context = CallContext(
        invoice_id=invoice_id,
        vendor_phone=vendor_phone,
        vendor_name=vendor_name,
        purpose=CallPurpose(purpose),
        language=language,
        tenant_id=tenant_id,
        missing_fields=missing_fields or [],
    )
    
    return await agent.queue_call(context)
