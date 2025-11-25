"""
Invoice management endpoints.
"""

import hashlib
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, UploadFile, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.api.api_v1.standards import (
    APIStandardizer,
    EndpointValidator,
    DatabaseHelper,
    StatusCodes,
    ErrorMessages,
    get_db_session,
    get_authenticated_user
)
from app.api.schemas import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceUpdate,
    InvoiceListResponse,
)
from app.core.config import settings
from app.core.exceptions import APIntakeException, StorageException
from app.models.invoice import Invoice, InvoiceStatus, InvoiceExtraction, Validation
from app.models.user import User
from app.services.storage_service import StorageService
from app.workers.invoice_tasks import process_invoice_task

logger = logging.getLogger(__name__)
router = APIRouter()


def transform_invoice_with_extraction(invoice: Invoice, extraction: Optional[InvoiceExtraction] = None, validation: Optional[Validation] = None) -> InvoiceResponse:
    """Transform invoice database record with extraction data into frontend-friendly format."""

    # Start with basic invoice data
    invoice_dict = {
        "id": invoice.id,
        "vendor_id": str(invoice.vendor_id) if invoice.vendor_id else None,
        "file_name": invoice.file_name,
        "file_size": invoice.file_size,
        "file_hash": invoice.file_hash,
        "file_url": invoice.file_url,
        "status": invoice.status,
        "workflow_state": invoice.workflow_state,
        "requires_human_review": invoice.status == InvoiceStatus.EXCEPTION or (
            validation and not validation.passed
        ),
        "created_at": invoice.created_at,
        "updated_at": invoice.updated_at,
        "uploaded_at": invoice.created_at,  # Alias for frontend compatibility
    }

    # Add extraction data if available
    if extraction:
        header_data = extraction.header_json or {}
        confidence_data = extraction.confidence_json or {}

        # Parse total amount
        total_amount = _parse_decimal_field(header_data.get("total_amount"))

        # Map extraction data to frontend fields
        invoice_dict.update({
            "invoice_number": header_data.get("invoice_number"),
            "vendor_name": header_data.get("vendor_name"),
            "invoice_date": _parse_date_field(header_data.get("invoice_date")),
            "due_date": _parse_date_field(header_data.get("due_date")),
            "total_amount": total_amount,
            "amount": float(total_amount) if total_amount else None,  # Alias for frontend
            "currency": header_data.get("currency", "USD"),
            "confidence": _parse_confidence_field(confidence_data.get("overall")),
        })

    # Add validation data if available
    if validation:
        validation_checks = validation.checks_json or {}
        issues_count = len([check for check in validation_checks.values() if not check.get("passed", True)])

        invoice_dict.update({
            "validation_issues": issues_count,
            "priority": _determine_priority(validation, extraction),
        })
    else:
        invoice_dict.update({
            "validation_issues": 0,
            "priority": "medium",
        })

    return InvoiceResponse(**invoice_dict)


def _parse_date_field(date_value: Any) -> Optional[datetime]:
    """Parse date field from various possible formats."""
    if date_value is None:
        return None

    if isinstance(date_value, datetime):
        return date_value

    if isinstance(date_value, str):
        try:
            # Try ISO format first
            return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
        except ValueError:
            try:
                # Try common formats
                return datetime.strptime(date_value, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Could not parse date: {date_value}")
                return None

    return None


def _parse_decimal_field(decimal_value: Any) -> Optional[Decimal]:
    """Parse decimal field from various possible formats."""
    if decimal_value is None:
        return None

    if isinstance(decimal_value, Decimal):
        return decimal_value

    if isinstance(decimal_value, (int, float)):
        return Decimal(str(decimal_value))

    if isinstance(decimal_value, str):
        try:
            # Remove currency symbols and commas
            cleaned = decimal_value.replace('$', '').replace(',', '').strip()
            return Decimal(cleaned)
        except ValueError:
            logger.warning(f"Could not parse decimal: {decimal_value}")
            return None

    return None


def _parse_confidence_field(confidence_value: Any) -> float:
    """Parse confidence field from various possible formats."""
    if confidence_value is None:
        return 0.0

    if isinstance(confidence_value, (int, float)):
        # Convert from 0-1 range to 0-100 range for frontend
        return float(confidence_value)

    if isinstance(confidence_value, str):
        try:
            # Handle percentage strings
            if confidence_value.endswith('%'):
                return float(confidence_value.rstrip('%')) / 100.0
            # Handle decimal strings
            return float(confidence_value)
        except ValueError:
            logger.warning(f"Could not parse confidence: {confidence_value}")
            return 0.0

    return 0.0


def _determine_priority(validation: Optional[Validation], extraction: Optional[InvoiceExtraction]) -> str:
    """Determine invoice priority based on validation and extraction results."""

    # High priority if validation failed
    if validation and not validation.passed:
        return "high"

    # Urgent if there are exceptions
    if validation and any(
        issue.get("severity") == "error"
        for issue in validation.checks_json.values()
        if isinstance(issue, dict)
    ):
        return "urgent"

    # Low priority if confidence is very high and no issues
    if extraction:
        confidence_data = extraction.confidence_json or {}
        overall_confidence = _parse_confidence_field(confidence_data.get("overall"))
        if overall_confidence >= 0.95:
            return "low"

    return "medium"


@router.post("/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Upload and process an invoice file."""
    logger.info(f"Uploading invoice file: {file.filename}")

    try:
        # Validate file type
        if not file.filename:
            return APIStandardizer.error_response(
                error_message="No filename provided",
                status_code=StatusCodes.BAD_REQUEST
            )

        file_extension = file.filename.lower().split('.')[-1]
        if file_extension not in settings.ALLOWED_FILE_TYPES:
            return APIStandardizer.error_response(
                error_message=f"File type '{file_extension}' not allowed. Allowed types: {settings.ALLOWED_FILE_TYPES}",
                status_code=StatusCodes.BAD_REQUEST
            )

        # Validate file size
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > settings.MAX_FILE_SIZE_MB:
            return APIStandardizer.error_response(
                error_message=f"File size {file_size_mb:.1f}MB exceeds maximum {settings.MAX_FILE_SIZE_MB}MB",
                status_code=StatusCodes.BAD_REQUEST
            )

        # Calculate file hash
        file_hash = hashlib.sha256(content).hexdigest()

        # Check for duplicate files
        result = await db.execute(select(Invoice).where(Invoice.file_hash == file_hash))
        existing_invoice = result.scalar_one_or_none()
        if existing_invoice:
            logger.warning(f"Duplicate file detected: {file.filename} (hash: {file_hash})")
            return APIStandardizer.error_response(
                error_message=f"Duplicate file detected. Existing invoice ID: {existing_invoice.id}",
                status_code=StatusCodes.CONFLICT
            )

        # Store file
        storage_service = StorageService()
        storage_info = await storage_service.store_file(
            content,
            file.filename,
            content_type=file.content_type
        )

        # Create invoice record
        invoice = Invoice(
            vendor_id=None,  # Will be determined from extraction during processing
            file_url=storage_info["file_path"],
            file_hash=file_hash,
            file_name=file.filename,
            file_size=f"{file_size_mb:.1f}MB",
            status=InvoiceStatus.RECEIVED,
            workflow_state="uploaded",
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)

        # Queue processing task
        process_invoice_task.delay(
            str(invoice.id),
            storage_info["file_path"],
            file_hash
        )

        logger.info(f"Successfully uploaded and queued invoice {invoice.id}")
        response_data = InvoiceResponse.from_orm(invoice)

        return APIStandardizer.success_response(
            data=response_data,
            message="Invoice uploaded and queued for processing successfully",
            status_code=StatusCodes.CREATED
        )

    except StorageException as e:
        logger.error(f"Storage error during upload: {e}")
        return APIStandardizer.error_response(
            error_message="Storage service error",
            status_code=StatusCodes.INTERNAL_SERVER_ERROR,
            error_details={"storage_error": str(e)}
        )
    except Exception as e:
        return APIStandardizer.handle_exception(e, "Invoice upload")


@router.get("/")
async def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """List invoices with optional filtering and rich extraction data."""
    try:
        # Validate pagination
        limit, skip = EndpointValidator.validate_pagination(limit, skip, 1000)

        # Build the base query with joins to get extraction and validation data
        query = (
            select(Invoice)
            .options(
                selectinload(Invoice.extractions),
                selectinload(Invoice.validations)
            )
        )

        # Apply filters
        conditions = []
        if status:
            try:
                status_enum = InvoiceStatus[status.upper()]
                conditions.append(Invoice.status == status_enum)
            except KeyError:
                return APIStandardizer.error_response(
                    error_message=f"Invalid status: {status}",
                    status_code=StatusCodes.BAD_REQUEST
                )

        if vendor_id:
            try:
                vendor_uuid = EndpointValidator.validate_uuid(vendor_id, "vendor_id")
                conditions.append(Invoice.vendor_id == vendor_uuid)
            except ValueError:
                return APIStandardizer.error_response(
                    error_message="Invalid vendor_id format",
                    status_code=StatusCodes.BAD_REQUEST
                )

        # Apply conditions to query
        if conditions:
            query = query.where(*conditions)

        # Order by creation date (newest first)
        query = query.order_by(Invoice.created_at.desc())

        # Get total count
        total = await DatabaseHelper.get_total_count(db, Invoice, conditions)

        # Apply pagination
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        invoices = result.scalars().all()

        # Transform invoices with extraction data
        enriched_invoices = []
        for invoice in invoices:
            # Get the latest extraction (there should typically be only one)
            latest_extraction = None
            if invoice.extractions:
                latest_extraction = max(
                    invoice.extractions,
                    key=lambda x: x.created_at
                )

            # Get the latest validation
            latest_validation = None
            if invoice.validations:
                latest_validation = max(
                    invoice.validations,
                    key=lambda x: x.created_at
                )

            # Transform the invoice with rich data
            enriched_invoice = transform_invoice_with_extraction(
                invoice, latest_extraction, latest_validation
            )
            enriched_invoices.append(enriched_invoice)

        return APIStandardizer.paginated_response(
            data=enriched_invoices,
            total=total,
            limit=limit,
            offset=skip,
            message="Invoices retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Invoice listing")


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Get invoice details by ID with rich extraction data."""
    try:
        # Validate invoice ID
        invoice_uuid = EndpointValidator.validate_uuid(invoice_id, "invoice_id")

        result = await db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.extractions),
                selectinload(Invoice.validations)
            )
            .where(Invoice.id == invoice_uuid)
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            return APIStandardizer.error_response(
                error_message=ErrorMessages.NOT_FOUND,
                status_code=StatusCodes.NOT_FOUND
            )

        # Get the latest extraction and validation
        latest_extraction = None
        if invoice.extractions:
            latest_extraction = max(
                invoice.extractions,
                key=lambda x: x.created_at
            )

        latest_validation = None
        if invoice.validations:
            latest_validation = max(
                invoice.validations,
                key=lambda x: x.created_at
            )

        # Transform the invoice with rich data
        response_data = transform_invoice_with_extraction(
            invoice, latest_extraction, latest_validation
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Invoice retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Invoice retrieval")


@router.put("/{invoice_id}/review")
async def review_invoice(
    invoice_id: str,
    invoice_update: InvoiceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Update invoice after human review."""
    try:
        # Validate invoice ID
        invoice_uuid = EndpointValidator.validate_uuid(invoice_id, "invoice_id")
        
        result = await db.execute(select(Invoice).where(Invoice.id == invoice_uuid))
        invoice = result.scalar_one_or_none()

        if not invoice:
            return APIStandardizer.error_response(
                error_message=ErrorMessages.NOT_FOUND,
                status_code=StatusCodes.NOT_FOUND
            )

        # Update invoice fields
        update_data = invoice_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(invoice, field):
                setattr(invoice, field, value)

        await db.commit()
        await db.refresh(invoice)

        logger.info(f"Invoice {invoice_id} updated after review")
        response_data = InvoiceResponse.model_validate(invoice)

        return APIStandardizer.success_response(
            data=response_data,
            message="Invoice review updated successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Invoice review update")


@router.post("/{invoice_id}/approve")
async def approve_invoice(
    invoice_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Approve invoice and stage for export."""
    try:
        # Validate invoice ID
        invoice_uuid = EndpointValidator.validate_uuid(invoice_id, "invoice_id")
        
        result = await db.execute(select(Invoice).where(Invoice.id == invoice_uuid))
        invoice = result.scalar_one_or_none()

        if not invoice:
            return APIStandardizer.error_response(
                error_message=ErrorMessages.NOT_FOUND,
                status_code=StatusCodes.NOT_FOUND
            )

        if invoice.status != InvoiceStatus.READY:
            return APIStandardizer.error_response(
                error_message=f"Invoice must be in 'ready' status to approve. Current status: {invoice.status}",
                status_code=StatusCodes.BAD_REQUEST
            )

        # Update invoice status
        invoice.status = InvoiceStatus.STAGED
        invoice.workflow_state = "approved"
        await db.commit()

        # Queue export task
        from app.workers.invoice_tasks import export_invoice_task
        export_invoice_task.delay(str(invoice.id))

        logger.info(f"Invoice {invoice_id} approved and queued for export")
        response_data = {
            "message": "Invoice approved and queued for export",
            "invoice_id": invoice_id,
            "status": invoice.status.value,
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="Invoice approved successfully",
            status_code=StatusCodes.ACCEPTED
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Invoice approval")