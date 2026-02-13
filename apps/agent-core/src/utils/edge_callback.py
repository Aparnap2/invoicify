"""Utility to update Edge API status via HTTP callback."""
import httpx
import os
import structlog

logger = structlog.get_logger()

from tenacity import retry, stop_after_attempt, wait_exponential

EDGE_API_BASE_URL = os.getenv("EDGE_API_BASE_URL", "http://host.docker.internal:8787")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def update_invoice_status(
    trace_id: str,
    status: str,
    quickbooks_bill_id: str | None = None,
    error_message: str | None = None,
    extracted_data: dict | None = None,
) -> bool:
    """
    Update invoice status in Edge API D1 database.
    
    Args:
        trace_id: Invoice trace ID
        status: New status (APPROVED, REJECTED, AWAITING_APPROVAL, ERROR, PAID)
        quickbooks_bill_id: QuickBooks bill ID if posted
        error_message: Error message if failed
        extracted_data: Extracted invoice data
    
    Returns:
        True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{EDGE_API_BASE_URL}/internal/update-status",
                json={
                    "trace_id": trace_id,
                    "status": status,
                    "quickbooks_bill_id": quickbooks_bill_id,
                    "error_message": error_message,
                    "extracted_data": extracted_data,
                },
            )
            response.raise_for_status()
            
            logger.info(
                "edge_status_updated",
                trace_id=trace_id,
                status=status,
                success=True,
            )
            return True
            
    except Exception as e:
        logger.error(
            "edge_status_update_failed",
            trace_id=trace_id,
            status=status,
            error=str(e),
        )
        return False
