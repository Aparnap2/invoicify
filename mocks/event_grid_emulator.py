"""
Azure Event Grid Emulator for Local Development.

Mimics Azure Event Grid behavior:
1. Accepts events via HTTP POST (CloudEvents schema)
2. Returns 202 Accepted immediately
3. Asynchronously pushes events to subscribed webhooks
4. Handles SubscriptionValidationEvent for Azure handshake

Usage:
    docker run -p 8080:8080 \
      -e WEBHOOK_SUBSCRIBERS=http://voice-agent:8001/api/events \
      event-grid-emulator
"""

import os
import asyncio
import httpx
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime
import uuid

logger = structlog.get_logger()
app = FastAPI(title="Local Azure Event Grid Emulator")

# Comma-separated list of webhook URLs to push events to
SUBSCRIBERS = os.getenv("WEBHOOK_SUBSCRIBERS", "").split(",")

# Store events for debugging/inspection
events_store: List[Dict[str, Any]] = []


class CloudEvent(BaseModel):
    """Azure Event Grid CloudEvents schema."""
    id: str
    eventType: str
    subject: str
    data: Dict[str, Any]
    eventTime: str
    dataVersion: str
    metadataVersion: Optional[str] = None


async def push_to_subscriber(url: str, payload: List[Dict]) -> bool:
    """
    Fires the webhook exactly like Azure Event Grid does.
    
    Azure Event Grid:
    - Sends events as an array
    - Expects 200 OK within timeout
    - Retries on failure with exponential backoff
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            logger.info("event_grid_pushing", target=url, event_count=len(payload))
            
            # Event Grid always sends events as an array
            response = await client.post(
                url, 
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "aeg-event-type": "Notification",
                }
            )
            
            if response.status_code == 200:
                logger.info("event_grid_delivery_success", target=url)
                return True
            else:
                logger.warning(
                    "event_grid_delivery_failed", 
                    target=url, 
                    status=response.status_code
                )
                return False
                
        except httpx.TimeoutException:
            logger.error("event_grid_timeout", target=url)
            return False
        except Exception as e:
            logger.error("event_grid_delivery_error", target=url, error=str(e))
            return False


@app.post("/api/events")
async def receive_and_dispatch(request: Request):
    """
    Agent Core sends events here. We accept, then push to subscribers asynchronously.
    
    This mimics Azure Event Grid's behavior:
    1. Validate CloudEvents schema
    2. Handle SubscriptionValidationEvent (Azure handshake)
    3. Return 202 Accepted immediately
    4. Dispatch to subscribers in background
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("event_grid_invalid_json", error=str(e))
        return Response(status_code=400, content="Invalid JSON")
    
    # Event Grid sends events as an array
    if not isinstance(payload, list):
        payload = [payload]
    
    # Store events for debugging
    events_store.extend(payload)
    
    # Process each event
    for event in payload:
        event_type = event.get("eventType", "")
        data = event.get("data", {})
        
        # 1. Azure Event Grid Handshake Validation
        # Azure sends this when you first create a subscription
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = data.get("validationCode")
            logger.info("event_grid_validation_received", code=validation_code[:20] if validation_code else None)
            
            # Must echo back the validation code to prove we own the endpoint
            return {"validationResponse": validation_code}
        
        # 2. Handle our Custom Business Events
        logger.info(
            "event_grid_event_received",
            event_id=event.get("id"),
            event_type=event_type,
            subject=event.get("subject"),
        )
    
    # 3. Return 202 Accepted immediately (Azure behavior)
    # 4. Dispatch to subscribers asynchronously (don't block the response)
    for sub in SUBSCRIBERS:
        if sub.strip():
            # Fire and forget - exactly like Azure Event Grid
            asyncio.create_task(push_to_subscriber(sub.strip(), payload))
    
    return Response(status_code=202)


@app.get("/api/events")
async def list_events():
    """Debug endpoint to see all events received."""
    return {
        "total_events": len(events_store),
        "events": events_store[-100:],  # Last 100 events
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "subscribers": SUBSCRIBERS,
        "events_received": len(events_store),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI for testing
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
