"""
Invoice Get Function - Azure Functions HTTP Trigger

GET /api/invoices/{invoiceId}
Replaces Cloudflare Workers + Hono endpoint with Azure Functions
"""

import azure.functions as func
import json
import structlog

from ..db.sql import execute_query

logger = structlog.get_logger()

app = func.Blueprint()


@app.route(route="invoices/{invoiceId}", methods=[func.HttpMethod.GET])
async def invoice_get(req: func.HttpRequest, invoiceId: str) -> func.HttpResponse:
    """
    Get invoice by ID.
    
    Query params:
    - tenant_id (required)
    
    Response:
    {
        "id": "uuid",
        "tenant_id": "uuid",
        "blob_url": "https://...",
        "status": "PENDING",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }
    """
    try:
        tenant_id = req.params.get("tenant_id")
        
        if not tenant_id:
            return func.HttpResponse(
                json.dumps({"error": "tenant_id query parameter is required"}),
                status_code=400,
                mimetype="application/json",
            )
        
        # Query Azure SQL
        try:
            results = await execute_query(
                """
                SELECT * FROM invoices 
                WHERE id = @id AND tenant_id = @tenant_id
                """,
                {"id": invoiceId, "tenant_id": tenant_id},
            )
            
            if not results:
                return func.HttpResponse(
                    json.dumps({"error": "Invoice not found"}),
                    status_code=404,
                    mimetype="application/json",
                )
            
            invoice = results[0]
            
            # Convert to JSON-serializable format
            invoice["created_at"] = invoice["created_at"].isoformat() if invoice.get("created_at") else None
            invoice["updated_at"] = invoice["updated_at"].isoformat() if invoice.get("updated_at") else None
            
            return func.HttpResponse(
                json.dumps(invoice),
                status_code=200,
                mimetype="application/json",
            )
            
        except Exception as e:
            logger.error("sql_query_failed", error=str(e))
            return func.HttpResponse(
                json.dumps({"error": f"Database error: {str(e)}"}),
                status_code=500,
                mimetype="application/json",
            )
        
    except Exception as e:
        logger.error("invoice_get_error", error=str(e))
        return func.HttpResponse(
            json.dumps({"error": f"Internal server error: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
        )
