"""
Event Grid Publisher for Agent Core.

Publishes events to Azure Event Grid (production) or local emulator (dev).
Uses CloudEvents schema that Azure Event Grid expects.

Usage:
    from src.events.publisher import publish_vendor_call_requested
    
    await publish_vendor_call_requested(
        invoice_id="INV-123",
        vendor_phone="+919876543210"
    )
"""

import os
import httpx
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger()

# Environment configuration
ENV = os.getenv("ENVIRONMENT", "local")

# Local development: Event Grid emulator container
LOCAL_EVENT_GRID_URL = os.getenv(
    "LOCAL_EVENT_GRID_URL", 
    "http://event-grid-emulator:8080/api/events"
)

# Production: Azure Event Grid
AZURE_EVENT_GRID_ENDPOINT = os.getenv("AZURE_EVENT_GRID_ENDPOINT")
AZURE_EVENT_GRID_KEY = os.getenv("AZURE_EVENT_GRID_KEY")


def create_cloud_event(
    event_type: str,
    subject: str,
    data: Dict[str, Any],
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create Azure Event Grid CloudEvent.
    
    Azure Event Grid expects events in CloudEvents v1.0 format:
    https://github.com/cloudevents/spec/blob/v1.0/spec.md
    
    Args:
        event_type: Event type (e.g., "invoice.vendor_call_requested")
        subject: Event subject (e.g., "invoices/INV-123")
        data: Event payload
        event_id: Unique event ID (auto-generated if not provided)
    
    Returns:
        CloudEvent dictionary
    """
    return {
        "id": event_id or str(uuid.uuid4()),
        "eventType": event_type,
        "subject": subject,
        "data": data,
        "eventTime": datetime.now(timezone.utc).isoformat(),
        "dataVersion": "1.0",
        "metadataVersion": None,
    }


async def publish_events(
    events: List[Dict[str, Any]],
    endpoint_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> bool:
    """
    Publish events to Event Grid.
    
    Args:
        events: List of CloudEvents to publish
        endpoint_url: Event Grid endpoint URL
        api_key: Event Grid API key (only for production)
    
    Returns:
        True if events were accepted
    """
    url = endpoint_url or (
        LOCAL_EVENT_GRID_URL if ENV == "local" else AZURE_EVENT_GRID_ENDPOINT
    )
    
    if not url:
        logger.error("event_grid_no_endpoint", environment=ENV)
        return False
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = {"Content-Type": "application/json"}
            
            # Production: Add Event Grid authentication header
            if ENV == "production" and api_key:
                headers["aeg-sas-key"] = api_key
            
            logger.info(
                "publishing_events",
                environment=ENV,
                url=url,
                event_count=len(events),
            )
            
            # Event Grid expects events as an array
            response = await client.post(url, json=events, headers=headers)
            
            # Event Grid returns 202 Accepted on success
            if response.status_code == 202:
                logger.info("events_published_success", count=len(events))
                return True
            elif response.status_code == 200:
                # Local emulator returns 200
                logger.info("events_published_success_local", count=len(events))
                return True
            else:
                logger.error(
                    "events_publish_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return False
                
        except httpx.TimeoutException:
            logger.error("event_grid_timeout", url=url)
            return False
        except Exception as e:
            logger.error("event_grid_error", url=url, error=str(e))
            return False


async def publish_vendor_call_requested(
    invoice_id: str,
    vendor_phone: str,
    vendor_name: Optional[str] = None,
    purpose: str = "missing_details",
    missing_fields: Optional[List[str]] = None,
    language: str = "hi-IN",
) -> bool:
    """
    Publish vendor_call_requested event.
    
    This triggers the Voice Agent to call the vendor and collect missing information.
    
    Args:
        invoice_id: Invoice ID
        vendor_phone: Vendor phone number (E.164 format)
        vendor_name: Vendor name (optional)
        purpose: Call purpose (missing_details, rfp_quote, invoice_followup)
        missing_fields: List of missing fields to collect
        language: Vendor language (hi-IN, en-US, etc.)
    
    Returns:
        True if event was published successfully
    """
    event = create_cloud_event(
        event_type="invoice.vendor_call_requested",
        subject=f"invoices/{invoice_id}",
        data={
            "invoice_id": invoice_id,
            "vendor_phone": vendor_phone,
            "vendor_name": vendor_name or "",
            "purpose": purpose,
            "missing_fields": missing_fields or [],
            "language": language,
        },
    )
    
    return await publish_events([event])


async def publish_invoice_submitted(
    invoice_id: str,
    tenant_id: str,
    r2_url: str,
    vendor_name: Optional[str] = None,
) -> bool:
    """
    Publish invoice_submitted event.
    
    This triggers the invoice processing pipeline.
    
    Args:
        invoice_id: Invoice ID
        tenant_id: Tenant ID
        r2_url: PDF storage URL
        vendor_name: Vendor name (optional)
    
    Returns:
        True if event was published successfully
    """
    event = create_cloud_event(
        event_type="invoice.submitted",
        subject=f"invoices/{invoice_id}",
        data={
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "r2_url": r2_url,
            "vendor_name": vendor_name or "",
        },
    )
    
    return await publish_events([event])


async def publish_call_completed(
    invoice_id: str,
    call_id: str,
    status: str,
    extracted_data: Dict[str, Any],
    transcript: Optional[str] = None,
) -> bool:
    """
    Publish call_completed event.
    
    This notifies Agent Core that the voice call is complete and data was collected.
    
    Args:
        invoice_id: Invoice ID
        call_id: Call ID
        status: Call status (SUCCESS, FAILED, ESCALATED)
        extracted_data: Structured data extracted from call
        transcript: Call transcript (optional)
    
    Returns:
        True if event was published successfully
    """
    event = create_cloud_event(
        event_type="invoice.call_completed",
        subject=f"invoices/{invoice_id}",
        data={
            "invoice_id": invoice_id,
            "call_id": call_id,
            "status": status,
            "extracted_data": extracted_data,
            "transcript": transcript or "",
        },
    )
    
    return await publish_events([event])


# ─────────────────────────────────────────────────────────────────────────────
# Test CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    
    async def test_publish():
        """Test event publishing."""
        print("Testing Event Grid publisher...")
        
        result = await publish_vendor_call_requested(
            invoice_id="TEST-INV-001",
            vendor_phone="+919876543210",
            vendor_name="Test Vendor",
            purpose="missing_details",
            missing_fields=["vendor.tax_id", "payment_terms"],
        )
        
        if result:
            print("✅ Event published successfully")
        else:
            print("❌ Event publish failed")
        
        return result
    
    asyncio.run(test_publish())
