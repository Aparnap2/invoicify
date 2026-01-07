"""FastAPI routes for AI service."""

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents.extractor import get_extractor_agent, InvoiceExtractionResult
from app.config import get_settings
from app.graphs.invoice_workflow import get_invoice_workflow
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceExtracted,
    InvoiceStatus,
    ProcessingResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Invoice AI"])


class ExtractionRequest(BaseModel):
    """Request for invoice extraction."""

    raw_content: str
    source_file_name: str = "invoice.txt"
    source_file_type: str = "txt"


class ExtractionResponse(BaseModel):
    """Response for invoice extraction."""

    success: bool
    invoice_id: Optional[str] = None
    data: Optional[InvoiceExtracted] = None
    confidence: float = 0.0
    notes: list[str] = []
    error: Optional[str] = None


class ProcessingRequest(BaseModel):
    """Request for full invoice processing."""

    raw_content: str
    source_file_name: str = "invoice.txt"
    source_file_type: str = "txt"


class ProcessingResponse(BaseModel):
    """Response for full invoice processing."""

    success: bool
    thread_id: str
    result: Optional[ProcessingResult] = None
    error: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Request to submit approval decision."""

    thread_id: str
    action: str  # "approve" or "reject"
    comments: Optional[str] = None
    approver_id: str
    approver_email: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    model: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        model=settings.llm_model,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_invoice(request: ExtractionRequest) -> ExtractionResponse:
    """Extract structured data from invoice content."""
    logger.info(f"Extracting invoice from {request.source_file_name}")

    try:
        extractor = get_extractor_agent()
        invoice_data = InvoiceCreate(
            vendor_name="",  # Will be extracted
            invoice_number="",  # Will be extracted
            invoice_date=date.today(),
            due_date=date.today(),
            subtotal=Decimal("0"),
            total_amount=Decimal("0"),
            source_file_name=request.source_file_name,
            source_file_type=request.source_file_type,
        )

        result = await extractor.extract_from_text(request.raw_content)

        if result.success and result.data:
            return ExtractionResponse(
                success=True,
                invoice_id=str(uuid4()),
                data=result.data,
                confidence=result.confidence,
                notes=result.notes,
            )
        else:
            return ExtractionResponse(
                success=False,
                error=result.error or "Extraction failed",
            )

    except Exception as e:
        logger.error(f"Extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=ProcessingResponse)
async def process_invoice(request: ProcessingRequest) -> ProcessingResponse:
    """Process invoice through full workflow."""
    logger.info(f"Processing invoice through workflow: {request.source_file_name}")

    try:
        workflow = get_invoice_workflow()

        invoice_data = InvoiceCreate(
            vendor_name="",  # Will be extracted
            invoice_number="",
            invoice_date=date.today(),
            due_date=date.today(),
            subtotal=Decimal("0"),
            total_amount=Decimal("0"),
            source_file_name=request.source_file_name,
            source_file_type=request.source_file_type,
        )

        result = await workflow.process_invoice(
            invoice_data=invoice_data,
            raw_content=request.raw_content,
        )

        return ProcessingResponse(
            success=result.status not in (InvoiceStatus.EXCEPTION,),
            thread_id=str(uuid4()),
            result=result,
        )

    except Exception as e:
        logger.error(f"Processing error: {e}")
        return ProcessingResponse(
            success=False,
            thread_id=str(uuid4()),
            error=str(e),
        )


@router.post("/upload")
async def upload_invoice(file: UploadFile = File(...)) -> ExtractionResponse:
    """Upload and extract invoice from file."""
    logger.info(f"Uploading invoice: {file.filename}")

    try:
        content = await file.read()
        raw_content = content.decode("utf-8")

        extractor = get_extractor_agent()
        result = await extractor.extract_from_text(raw_content)

        if result.success and result.data:
            return ExtractionResponse(
                success=True,
                invoice_id=str(uuid4()),
                data=result.data,
                confidence=result.confidence,
                notes=result.notes,
            )
        else:
            return ExtractionResponse(
                success=False,
                error=result.error or "Extraction failed",
            )

    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve")
async def submit_approval(request: ApprovalRequest) -> ProcessingResponse:
    """Submit approval decision for an interrupted workflow."""
    logger.info(f"Submitting approval for thread: {request.thread_id}")

    try:
        workflow = get_invoice_workflow()

        decision = {
            "action": request.action,
            "comments": request.comments,
            "approver_id": request.approver_id,
            "approver_email": request.approver_email,
        }

        result = await workflow.resume_with_approval(
            thread_id=request.thread_id,
            decision=decision,
        )

        return ProcessingResponse(
            success=result is not None,
            thread_id=request.thread_id,
            result=result,
        )

    except Exception as e:
        logger.error(f"Approval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{thread_id}")
async def get_processing_status(thread_id: str) -> dict:
    """Get processing status for a thread."""
    try:
        workflow = get_invoice_workflow()
        config = {"configurable": {"thread_id": thread_id}}

        state = workflow.graph.get_state(config)

        if state is None:
            return {"status": "not_found", "thread_id": thread_id}

        return {
            "status": "running",
            "thread_id": thread_id,
            "next": state.next,
            "values": {
                "status": str(state.values.get("status", "unknown")),
            }
            if state.values
            else None,
        }

    except Exception as e:
        logger.error(f"Status error: {e}")
        return {"status": "error", "error": str(e)}
