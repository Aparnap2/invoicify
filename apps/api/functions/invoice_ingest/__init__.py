"""
Invoice Ingest Function - Azure Functions HTTP Trigger

POST /api/invoices
Replaces Cloudflare Workers + Hono endpoint with Azure Functions

Flow:
1. Validate request (file type, size, tenant)
2. Upload PDF to Azure Blob Storage
3. Store metadata in Azure SQL
4. Publish event to Event Grid
"""

import azure.functions as func
import json
import os
from datetime import datetime
from uuid import uuid4
import base64
import structlog

from ..storage.blob import BlobStorageClient
from ..db.sql import execute_command, execute_query

logger = structlog.get_logger()

app = func.Blueprint()


@app.route(route="invoices", methods=[func.HttpMethod.POST])
async def invoice_ingest(req: func.HttpRequest) -> func.HttpResponse:
    """
    Ingest invoice PDF for processing.
    
    Request body (JSON):
    {
        "tenant_id": "uuid",
        "file_name": "invoice.pdf",
        "file_content": "base64-encoded-pdf",
        "vendor_phone": "+91...",  // optional
        "language": "hi-IN"  // optional
    }
    
    Response:
    {
        "invoice_id": "uuid",
        "status": "PROCESSING",
        "message": "Invoice received and queued for processing"
    }
    """
    try:
        # Parse request
        try:
            req_body = req.get_json()
        except json.JSONDecodeError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON"}),
                status_code=400,
                mimetype="application/json",
            )
        
        tenant_id = req_body.get("tenant_id")
        file_name = req_body.get("file_name")
        file_content = req_body.get("file_content")  # base64
        vendor_phone = req_body.get("vendor_phone")
        language = req_body.get("language", "hi-IN")
        
        # Validate required fields
        if not tenant_id or not file_name or not file_content:
            return func.HttpResponse(
                json.dumps({"error": "tenant_id, file_name, and file_content are required"}),
                status_code=400,
                mimetype="application/json",
            )
        
        # Validate file type
        if not file_name.lower().endswith(".pdf"):
            return func.HttpResponse(
                json.dumps({"error": "Only PDF files are accepted"}),
                status_code=400,
                mimetype="application/json",
            )
        
        # Decode and validate file size
        try:
            pdf_bytes = base64.b64decode(file_content)
        except Exception:
            return func.HttpResponse(
                json.dumps({"error": "Invalid base64 encoding"}),
                status_code=400,
                mimetype="application/json",
            )
        
        # 10MB limit
        if len(pdf_bytes) > 10 * 1024 * 1024:
            return func.HttpResponse(
                json.dumps({"error": "File size exceeds 10MB limit"}),
                status_code=400,
                mimetype="application/json",
            )
        
        # Generate IDs
        invoice_id = str(uuid4())
        trace_id = str(uuid4())
        
        # Upload to Azure Blob Storage
        try:
            storage_client = BlobStorageClient()
            blob_name = f"{tenant_id}/{invoice_id}.pdf"
            
            blob_url = await storage_client.upload_blob(
                blob_name,
                pdf_bytes,
                "application/pdf",
                metadata={
                    "tenant_id": tenant_id,
                    "invoice_id": invoice_id,
                    "trace_id": trace_id,
                    "vendor_phone": vendor_phone or "",
                    "language": language,
                },
            )
            
            logger.info(
                "blob_uploaded",
                invoice_id=invoice_id,
                blob_name=blob_name,
                size=len(pdf_bytes),
            )
            
        except Exception as e:
            logger.error("blob_upload_failed", error=str(e))
            return func.HttpResponse(
                json.dumps({"error": f"Failed to upload file: {str(e)}"}),
                status_code=500,
                mimetype="application/json",
            )
        
        # Store metadata in Azure SQL
        try:
            await execute_command(
                """
                INSERT INTO invoices (id, tenant_id, blob_url, status, created_at, updated_at)
                VALUES (@id, @tenant_id, @blob_url, 'PENDING', @created_at, @updated_at)
                """,
                {
                    "id": invoice_id,
                    "tenant_id": tenant_id,
                    "blob_url": blob_url,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            )
            
            logger.info("invoice_metadata_stored", invoice_id=invoice_id)
            
        except Exception as e:
            logger.error("sql_insert_failed", error=str(e))
            # Clean up blob
            try:
                await storage_client.delete_blob(blob_name)
            except:
                pass
            
            return func.HttpResponse(
                json.dumps({"error": f"Failed to store metadata: {str(e)}"}),
                status_code=500,
                mimetype="application/json",
            )
        
        # Publish to Event Grid (optional - can be done asynchronously)
        try:
            await publish_event("invoice.submitted", {
                "invoice_id": invoice_id,
                "tenant_id": tenant_id,
                "blob_url": blob_url,
                "trace_id": trace_id,
            })
        except Exception as e:
            logger.warning("event_grid_publish_failed", error=str(e))
            # Don't fail the request - event grid is best-effort
        
        # Return success
        return func.HttpResponse(
            json.dumps({
                "invoice_id": invoice_id,
                "trace_id": trace_id,
                "status": "PROCESSING",
                "message": "Invoice received and queued for processing",
            }),
            status_code=202,
            mimetype="application/json",
        )
        
    except Exception as e:
        logger.error("invoice_ingest_error", error=str(e))
        return func.HttpResponse(
            json.dumps({"error": f"Internal server error: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
        )


async def publish_event(event_type: str, data: dict):
    """
    Publish event to Azure Event Grid.
    
    Args:
        event_type: Event type (e.g., "invoice.submitted")
        data: Event data
    """
    event_grid_endpoint = os.getenv("EVENT_GRID_ENDPOINT")
    event_grid_key = os.getenv("EVENT_GRID_KEY")
    
    if not event_grid_endpoint or not event_grid_key:
        logger.debug("event_grid_not_configured")
        return
    
    import aiohttp
    
    event = {
        "id": str(uuid4()),
        "subject": f"invoices/{data.get('invoice_id')}",
        "event_type": event_type,
        "data_version": "1.0",
        "data": data,
        "event_time": datetime.utcnow().isoformat(),
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            event_grid_endpoint,
            headers={
                "aeg-sas-key": event_grid_key,
                "Content-Type": "application/json",
            },
            json=[event],
        ) as response:
            if response.status == 200:
                logger.info("event_published", event_type=event_type)
            else:
                logger.warning("event_publish_failed", event_type=event_type, status=response.status)
