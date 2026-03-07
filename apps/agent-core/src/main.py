from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import structlog
import httpx
import os
import asyncio
import json
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from src.db.status import update_invoice_status
from src.queue.azure_queue import AzureQueueConsumer

# Configure Structured Logging
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

app = FastAPI(title="Invoicify Agent Core")

# ─────────────────────────────────────────────────────────────────────────────
# Queue Consumer Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

_queue_consumer: Optional[AzureQueueConsumer] = None


@app.on_event("startup")
async def startup_event():
    """Start Azure Storage Queue consumer on app startup."""
    global _queue_consumer
    _queue_consumer = AzureQueueConsumer(pipeline_fn=run_pipeline)
    # Run as background task — doesn't block FastAPI
    asyncio.create_task(_queue_consumer.start())
    logger.info("queue_consumer_started")


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown of queue consumer."""
    global _queue_consumer
    if _queue_consumer:
        await _queue_consumer.stop()
    logger.info("queue_consumer_stopped")

# --- Models ---

class ProcessInvoiceRequest(BaseModel):
    trace_id: str
    r2_key: str
    r2_presigned_url: str

# --- Helpers ---

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def fetch_invoice_from_edge(trace_id: str) -> dict:
    """Fetch invoice data from Edge API for HITL approval."""
    edge_api_base = os.getenv("EDGE_API_BASE_URL", "http://host.docker.internal:8787")
    
    async with timed("fetch_invoice_from_edge", trace_id):
        response = await http_client.get(f"{edge_api_base}/api/v1/invoices/{trace_id}")
        response.raise_for_status()
        data = response.json()
        return data["invoice"]

# --- Initializations ---
from src.utils.http import http_client
from src.utils.timing import timed

async def run_pipeline(trace_id: str, r2_key: str, r2_presigned_url: str):
    """
    Optimized pipeline with Phase 1 Parallelization.
    """
    log = logger.bind(trace_id=trace_id)
    log.info("pipeline_started")

    async with timed("full_pipeline_duration", trace_id):
        try:
            from src.activities.extraction import extract_invoice
            from src.activities.analysis import analyze_invoice
            from src.activities.execution import post_to_quickbooks
            from src.agents.trust_manager import TrustBatteryManager

            # 1. Parallel Step: Extraction + Initial Vendor Lookup (if possible)
            # For now, extraction is primary. 
            # If we had a pre-extraction vendor hint (e.g. from filename), we'd run it here.
            log.info("step_extract")
            invoice_data = await extract_invoice(r2_presigned_url)
            vendor_name = invoice_data.get("vendor_name")
            log.info("extracted", vendor=vendor_name)

            # 2. Parallel Step: Analysis + QuickBooks Vendor Sync
            # We can start checking if vendor exists in QB while analyzing risk.
            log.info("step_analyze_parallel")
            
            async def get_qb_precheck(name):
                # Placeholder for QB vendor existence check
                await asyncio.sleep(0.1) 
                return {"exists": True}

            analysis_task = analyze_invoice(invoice_data)
            qb_sync_task = get_qb_precheck(vendor_name)

            analysis, qb_hint = await asyncio.gather(
                analysis_task,
                qb_sync_task
            )
            
            decision = analysis.get("decision", "HITL_REQUIRED")
            log.info("decision_made", decision=decision)

            trust_manager = TrustBatteryManager()

            # 3. Decision Routing (Single Batch Update to Edge)
            async with timed("edge_callback", trace_id):
                if decision == "AUTO_APPROVE":
                    log.info("step_execute_auto")
                    qb_result = await post_to_quickbooks(invoice_data)
                    
                    # Successfully auto-approved -> Update Trust Battery (+)
                    await trust_manager.update_outcome(vendor_name, is_accurate=True)
                    
                    await update_invoice_status(
                        trace_id=trace_id,
                        status="PAID",
                        quickbooks_bill_id=qb_result.get("id"),
                        extracted_data=invoice_data
                    )
                    
                elif decision == "REJECT":
                    log.info("step_reject")
                    await update_invoice_status(
                        trace_id=trace_id,
                        status="REJECTED",
                        error_message=analysis.get("reasoning"),
                        extracted_data=invoice_data
                    )
                    
                else: # HITL_REQUIRED
                    log.info("step_await_hitl")
                    await update_invoice_status(
                        trace_id=trace_id,
                        status="AWAITING_APPROVAL",
                        extracted_data=invoice_data
                    )

        except Exception as e:
            log.error("pipeline_failed", error=str(e))
            await update_invoice_status(
                trace_id=trace_id,
                status="ERROR",
                error_message=str(e)
            )

# --- Endpoints ---

@app.post("/process-invoice")
async def process_invoice(req: ProcessInvoiceRequest, background_tasks: BackgroundTasks):
    """Async endpoint to trigger the processing pipeline."""
    background_tasks.add_task(run_pipeline, req.trace_id, req.r2_key, req.r2_presigned_url)
    return {"status": "ACCEPTED", "trace_id": req.trace_id}

@app.post("/approve-invoice/{trace_id}")
async def approve_invoice(trace_id: str, payload: Dict[str, Any]):
    """Called after HITL approval to trigger execution."""
    user_id = payload.get("user_id", "unknown")
    logger.info("hitl_approval_received", trace_id=trace_id, user_id=user_id)
    
    try:
        from src.activities.execution import post_to_quickbooks
        from src.agents.trust_manager import TrustBatteryManager
        import json
        
        # Load invoice from Edge API D1
        invoice_record = await fetch_invoice_from_edge(trace_id)
        
        # Parse extracted_data
        extracted_data_raw = invoice_record.get("extracted_data")
        if not extracted_data_raw:
            raise ValueError(f"No extracted data found for invoice {trace_id}")
        
        invoice_data = json.loads(extracted_data_raw)
        vendor_name = invoice_data.get("vendor_name")
        
        # Execute payment
        qb_result = await post_to_quickbooks(invoice_data)
        
        # Manual approval successful -> Update Trust Battery (+)
        trust_manager = TrustBatteryManager()
        await trust_manager.update_outcome(vendor_name, is_accurate=True)
        
        await update_invoice_status(
            trace_id=trace_id,
            status="PAID",
            quickbooks_bill_id=qb_result.get("id"),
        )
        
        return {"status": "SUCCESS", "trace_id": trace_id, "quickbooks_id": qb_result.get("id")}
    
    except Exception as e:
        logger.error("approval_failed", trace_id=trace_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
