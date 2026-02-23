"""
Voice Agent API - Azure Event Grid Webhook Receiver.

Receives events from Azure Event Grid (production) or local emulator (dev).
Handles:
1. SubscriptionValidationEvent (Azure handshake)
2. invoice.vendor_call_requested (trigger voice call)
3. invoice.call_completed (result callback)

Zero code changes between local and production.
"""

import os
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, BackgroundTasks, Response, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()
app = FastAPI(title="Invoicify Voice Agent Webhook")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

class CloudEvent(BaseModel):
    """Azure Event Grid CloudEvents schema."""
    id: str
    eventType: str
    subject: str
    data: Dict[str, Any]
    eventTime: str
    dataVersion: str


class VendorCallData(BaseModel):
    """Data for vendor_call_requested event."""
    invoice_id: str
    vendor_phone: str
    vendor_name: str = ""
    purpose: str = "missing_details"
    missing_fields: List[str] = []
    language: str = "hi-IN"


# ─────────────────────────────────────────────────────────────────────────────
# Voice Call Execution
# ─────────────────────────────────────────────────────────────────────────────

async def execute_voice_call(
    invoice_id: str,
    vendor_phone: str,
    vendor_name: str = "",
    purpose: str = "missing_details",
    missing_fields: Optional[List[str]] = None,
    language: str = "hi-IN",
):
    """
    Execute the voice call pipeline.
    
    This runs in a background task so we can return 202 immediately.
    
    Flow:
    1. Initialize Pipecat transport (Twilio/SignalWire WebSocket)
    2. Initialize STT (Parakeet local / Sarvam prod)
    3. Initialize LLM (Groq)
    4. Initialize TTS (Kitten local / Sarvam prod)
    5. Run PipelineTask
    6. Extract structured data via LLM
    7. Publish call_completed event back to Event Grid
    
    Args:
        invoice_id: Invoice ID
        vendor_phone: Vendor phone number
        vendor_name: Vendor name
        purpose: Call purpose
        missing_fields: Fields to collect
        language: Vendor language
    """
    logger.info(
        "voice_call_starting",
        invoice_id=invoice_id,
        vendor_phone=vendor_phone,
        purpose=purpose,
    )
    
    try:
        # TODO: Implement full Pipecat pipeline here
        # For now, mock the call execution
        
        # Mock call duration (5-30 seconds for testing)
        await asyncio.sleep(5)
        
        # Mock extracted data
        extracted_data = {
            "status": "SUCCESS",
            "items_quoted": [],
            "delivery_timeline_days": None,
            "payment_terms": None,
            "escalation_reason": None,
            "collected_fields": missing_fields or [],
        }
        
        logger.info(
            "voice_call_completed",
            invoice_id=invoice_id,
            status=extracted_data["status"],
        )
        
        # TODO: Publish call_completed event back to Event Grid
        # from src.events.publisher import publish_call_completed
        # await publish_call_completed(
        #     invoice_id=invoice_id,
        #     call_id=f"call-{invoice_id}",
        #     status=extracted_data["status"],
        #     extracted_data=extracted_data,
        # )
        
    except Exception as e:
        logger.error("voice_call_failed", invoice_id=invoice_id, error=str(e))
        
        # TODO: Publish failure event
        # await publish_call_completed(
        #     invoice_id=invoice_id,
        #     call_id=f"call-{invoice_id}",
        #     status="FAILED",
        #     extracted_data={"error": str(e)},
        # )


# ─────────────────────────────────────────────────────────────────────────────
# Event Grid Webhook Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/events")
async def event_grid_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Azure Event Grid webhook receiver.
    
    Handles:
    1. SubscriptionValidationEvent (Azure handshake)
    2. invoice.vendor_call_requested (trigger voice call)
    3. Other events (logged and ignored)
    
    Returns 202 Accepted immediately and processes calls in background.
    """
    try:
        events = await request.json()
    except Exception as e:
        logger.error("event_grid_invalid_json", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Event Grid sends events as an array
    if not isinstance(events, list):
        events = [events]
    
    for event in events:
        event_type = event.get("eventType", "")
        data = event.get("data", {})
        event_id = event.get("id", "unknown")
        
        logger.info(
            "event_grid_event_received",
            event_id=event_id,
            event_type=event_type,
            subject=event.get("subject"),
        )
        
        # 1. Azure Event Grid Handshake Validation
        # Azure sends this when you first create a subscription
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = data.get("validationCode")
            logger.info("event_grid_validation_received", event_id=event_id)
            
            # Must echo back the validation code to prove we own the endpoint
            return {"validationResponse": validation_code}
        
        # 2. Handle vendor_call_requested event
        if event_type == "invoice.vendor_call_requested":
            try:
                call_data = VendorCallData(**data)
                
                logger.info(
                    "vendor_call_event_received",
                    invoice_id=call_data.invoice_id,
                    vendor_phone=call_data.vendor_phone,
                )
                
                # Dispatch to background task!
                # We MUST return HTTP 202 immediately so Event Grid doesn't timeout
                background_tasks.add_task(
                    execute_voice_call,
                    invoice_id=call_data.invoice_id,
                    vendor_phone=call_data.vendor_phone,
                    vendor_name=call_data.vendor_name,
                    purpose=call_data.purpose,
                    missing_fields=call_data.missing_fields,
                    language=call_data.language,
                )
                
            except Exception as e:
                logger.error(
                    "vendor_call_invalid_data",
                    event_id=event_id,
                    error=str(e),
                )
                # Don't fail the whole request - just log and continue
        
        # 3. Handle call_completed event (result callback)
        elif event_type == "invoice.call_completed":
            logger.info(
                "call_completed_event_received",
                invoice_id=data.get("invoice_id"),
                status=data.get("status"),
            )
            # TODO: Update database with call results
        
        # 4. Other events (log and ignore)
        else:
            logger.debug("event_grid_event_ignored", event_type=event_type)
    
    # Return 202 Accepted (Azure Event Grid expects this)
    return Response(status_code=202)


# ─────────────────────────────────────────────────────────────────────────────
# Health & Debug Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "voice-agent",
        "environment": os.getenv("ENVIRONMENT", "local"),
    }


@app.get("/api/events")
async def list_events():
    """Debug endpoint - list recent events (for testing)."""
    # TODO: Implement event logging/storage
    return {
        "message": "Event logging not implemented yet",
        "events": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("VOICE_AGENT_PORT", "8001"))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
