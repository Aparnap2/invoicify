"""
FastAPI on Azure Functions

This module enables running FastAPI apps on Azure Functions.
Based on: https://github.com/Azure-Samples/fastapi-on-azure-functions

Usage:
    func start --python
    
Or deploy to Azure:
    func azure functionapp publish <app-name>
"""

import azure.functions as func
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging

# Import function blueprints
from .functions.invoice_ingest import invoice_ingest
from .functions.invoice_get import invoice_get

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Invoicify API",
    description="Azure Functions-based API for invoice processing",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Routes (run on Azure Functions)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "platform": "azure-functions",
        "services": {
            "blob_storage": "configured",
            "sql_database": "configured",
        },
    }


@app.get("/metrics")
async def metrics():
    """Prometheus-style metrics endpoint."""
    return {
        "invoices_total": 0,
        "invoices_pending": 0,
        "timestamp": "2024-01-01T00:00:00Z",
    }


@app.post("/invoices")
async def create_invoice(invoice_data: dict):
    """
    Create invoice (calls Azure Function).
    
    This is a FastAPI wrapper around the Azure Function.
    In production, you'd call the function directly via HTTP trigger.
    """
    # For local dev, this calls the function directly
    # In production, this would be the HTTP trigger endpoint
    from .functions.invoice_ingest import invoice_ingest
    
    # Simulate HTTP request
    req = func.HttpRequest(
        method="POST",
        url="/api/invoices",
        body=json.dumps(invoice_data).encode(),
        headers={"Content-Type": "application/json"},
    )
    
    response = await invoice_ingest(req)
    
    return JSONResponse(
        content=json.loads(response.get_body()),
        status_code=response.status_code,
    )


@app.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, tenant_id: str):
    """
    Get invoice by ID (calls Azure Function).
    """
    from .functions.invoice_get import invoice_get
    
    req = func.HttpRequest(
        method="GET",
        url=f"/api/invoices/{invoice_id}?tenant_id={tenant_id}",
        body=None,
        params={"tenant_id": tenant_id},
    )
    
    response = await invoice_get(req, invoice_id)
    
    return JSONResponse(
        content=json.loads(response.get_body()),
        status_code=response.status_code,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Azure Functions Entry Point
# ─────────────────────────────────────────────────────────────────────────────

# Register function blueprints
app_functions = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Import function routes
app_functions.register_functions(invoice_ingest)
app_functions.register_functions(invoice_get)


# ─────────────────────────────────────────────────────────────────────────────
# WSGI/ASGI Bridge for FastAPI on Functions
# ─────────────────────────────────────────────────────────────────────────────

def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """
    Main Azure Functions entry point.
    
    Routes requests to FastAPI app or function blueprints.
    """
    logger.info(
        "Function invoked",
        invocation_id=context.invocation_id,
        method=req.method,
        url=req.url,
    )
    
    # Run async handler
    return asyncio.run(handle_request(req, context))


async def handle_request(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Handle request asynchronously."""
    
    # Check if request matches function routes
    if req.method == "POST" and "/invoices" in req.url and not req.params.get("invoiceId"):
        return await invoice_ingest(req)
    
    elif req.method == "GET" and "/invoices/" in req.url:
        invoice_id = req.url.split("/invoices/")[-1].split("?")[0]
        return await invoice_get(req, invoice_id)
    
    elif req.method == "GET" and req.url.endswith("/health"):
        return func.HttpResponse(
            json.dumps({"status": "ok", "platform": "azure-functions"}),
            status_code=200,
            mimetype="application/json",
        )
    
    # 404 for unmatched routes
    return func.HttpResponse(
        json.dumps({"error": "Not found"}),
        status_code=404,
        mimetype="application/json",
    )


# Import json for responses
import json
