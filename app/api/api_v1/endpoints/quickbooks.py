"""
QuickBooks OAuth and API endpoints for QuickBooks Online integration.

This module provides endpoints for:
- OAuth 2.0 authorization flow
- Invoice export to QuickBooks
- Connection management
- Webhook handling
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from sqlalchemy.orm import Session
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.db.session import get_db
from app.models.quickbooks import QuickBooksConnection, QuickBooksConnectionStatus, QuickBooksExport
from app.services.quickbooks_service import QuickBooksService, QuickBooksServiceException
from app.api.schemas.common import StandardResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request model."""
    code: str
    realm_id: str
    state: str


class QuickBooksConnectRequest(BaseModel):
    """QuickBooks connection request."""
    user_id: str
    auto_export_enabled: bool = False
    webhook_enabled: bool = False


class ExportRequest(BaseModel):
    """Invoice export request."""
    invoice_ids: List[str]
    dry_run: bool = False


class BatchExportRequest(BaseModel):
    """Batch invoice export request."""
    invoice_ids: List[str]
    dry_run: bool = False


@router.get("/authorize", response_model=StandardResponse[Dict[str, str]])
async def quickbooks_authorize(
    user_id: str = Query(..., description="User ID for the connection"),
    db: Session = Depends(get_db)
):
    """
    Initiate QuickBooks OAuth 2.0 authorization flow.

    This endpoint generates an authorization URL and redirects the user to QuickBooks
    for authentication and authorization.
    """
    try:
        logger.info(f"Initiating QuickBooks authorization for user: {user_id}")

        # Check if user already has an active connection
        existing_connection = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.user_id == uuid.UUID(user_id),
            QuickBooksConnection.status == QuickBooksConnectionStatus.CONNECTED
        ).first()

        if existing_connection:
            return StandardResponse.success_response(
                data={"message": "Already connected to QuickBooks"},
                message="QuickBooks connection already exists"
            )

        # Generate authorization URL
        async with QuickBooksService() as qb_service:
            auth_url, state = await qb_service.get_authorization_url()

        response_data = {
            "authorization_url": auth_url,
            "state": state,
            "message": "Navigate to the authorization URL to connect to QuickBooks"
        }

        return StandardResponse.success_response(
            data=response_data,
            message="Authorization URL generated successfully"
        )

    except QuickBooksServiceException as e:
        logger.error(f"QuickBooks service error during authorization: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during authorization: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/callback")
async def quickbooks_callback(
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State parameter"),
    realm_id: str = Query(..., description="QuickBooks company ID"),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth 2.0 callback from QuickBooks.

    This endpoint processes the authorization callback, exchanges the code for tokens,
    and creates a connection record.
    """
    try:
        logger.info(f"Processing QuickBooks callback with state: {state}, realm: {realm_id}")

        # Exchange code for tokens
        async with QuickBooksService() as qb_service:
            token_response = await qb_service.exchange_code_for_tokens(code, state, realm_id)

        # Get user and company info
        user_info = await qb_service.get_user_info(token_response["access_token"])
        company_info = await qb_service.get_company_info(token_response["access_token"], realm_id)

        # Extract user_id from state parameter
        user_uuid = None
        if state:
            try:
                # State format: timestamp:random_string:user_id:additional_data
                state_parts = state.split(':')
                if len(state_parts) >= 3:
                    user_uuid = uuid.UUID(state_parts[2])
                elif len(state_parts) >= 2:
                    # Try to parse as user_id only
                    try:
                        user_uuid = uuid.UUID(state_parts[1])
                    except ValueError:
                        pass
            except (ValueError, IndexError) as e:
                logger.warning(f"Could not extract user_id from state: {state}, error: {str(e)}")
        
        if not user_uuid:
            # Create or get user from email if available
            if 'email' in user_info:
                from app.services.auth.user_service import UserService
                
                user_service = UserService()
                user = await user_service.get_or_create_user_by_email(
                    db=db,
                    email=user_info['email'],
                    full_name=user_info.get('givenName', '') + ' ' + user_info.get('familyName', ''),
                    role='processor'  # Default role for QuickBooks users
                )
                if user:
                    user_uuid = user.id
                else:
                    # Fallback to creating a new user
                    user_uuid = uuid.uuid4()
                    logger.warning(f"Created fallback user for QuickBooks integration: {user_uuid}")
            else:
                # Last resort - create a new user
                user_uuid = uuid.uuid4()
                logger.warning(f"Created new user for QuickBooks integration: {user_uuid}")

        # Create or update connection
        connection = QuickBooksConnection(
            user_id=user_uuid,
            realm_id=realm_id,
            company_name=company_info.get("CompanyInfo", {}).get("CompanyName", ""),
            access_token=token_response["access_token"],
            refresh_token=token_response["refresh_token"],
            token_expires_at=datetime.utcnow() + timedelta(seconds=token_response["expires_in"]),
            status=QuickBooksConnectionStatus.CONNECTED,
            user_info=user_info,
            company_info=company_info
        )

        # Check if connection already exists
        existing_connection = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.user_id == user_uuid,
            QuickBooksConnection.realm_id == realm_id
        ).first()

        if existing_connection:
            # Update existing connection
            existing_connection.access_token = token_response["access_token"]
            existing_connection.refresh_token = token_response["refresh_token"]
            existing_connection.token_expires_at = connection.token_expires_at
            existing_connection.status = QuickBooksConnectionStatus.CONNECTED
            existing_connection.user_info = user_info
            existing_connection.company_info = company_info
            existing_connection.last_sync_at = datetime.utcnow()
            db.commit()
        else:
            # Create new connection
            db.add(connection)
            db.commit()

        # Redirect to frontend with success message
        redirect_url = f"{settings.UI_HOST}/quickbooks/success?realm_id={realm_id}"
        return RedirectResponse(url=redirect_url)

    except QuickBooksServiceException as e:
        logger.error(f"QuickBooks service error during callback: {str(e)}")
        # Redirect to frontend with error message
        redirect_url = f"{settings.UI_HOST}/quickbooks/error?error={str(e)}"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        logger.error(f"Unexpected error during callback: {str(e)}")
        redirect_url = f"{settings.UI_HOST}/quickbooks/error?error=Internal server error"
        return RedirectResponse(url=redirect_url)


@router.get("/connections", response_model=StandardResponse[List[Dict[str, Any]]])
async def get_connections(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Get QuickBooks connections.

    Returns a list of QuickBooks connections, optionally filtered by user ID and status.
    """
    try:
        query = db.query(QuickBooksConnection)

        if user_id:
            query = query.filter(QuickBooksConnection.user_id == uuid.UUID(user_id))

        if status:
            try:
                status_enum = QuickBooksConnectionStatus(status)
                query = query.filter(QuickBooksConnection.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        connections = query.order_by(QuickBooksConnection.created_at.desc()).all()

        connection_data = []
        for connection in connections:
            connection_data.append({
                "id": str(connection.id),
                "user_id": str(connection.user_id),
                "realm_id": connection.realm_id,
                "company_name": connection.company_name,
                "status": connection.status.value,
                "created_at": connection.created_at.isoformat(),
                "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
                "is_connected": connection.is_connected,
                "auto_export_enabled": connection.auto_export_enabled,
                "webhook_enabled": connection.webhook_enabled
            })

        return StandardResponse.success_response(
            data=connection_data,
            message=f"Retrieved {len(connection_data)} connections"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving connections: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/export/invoice/{invoice_id}", response_model=StandardResponse[Dict[str, Any]])
async def export_invoice_to_quickbooks(
    invoice_id: str,
    dry_run: bool = Query(False, description="Validate without creating"),
    user_id: str = Query(..., description="User ID for the connection"),
    db: Session = Depends(get_db)
):
    """
    Export a single invoice to QuickBooks.

    This endpoint exports an invoice from the AP intake system to QuickBooks as a bill.
    """
    try:
        logger.info(f"Exporting invoice {invoice_id} to QuickBooks for user {user_id}")

        # Get user's QuickBooks connection
        connection = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.user_id == uuid.UUID(user_id),
            QuickBooksConnection.status == QuickBooksConnectionStatus.CONNECTED
        ).first()

        if not connection:
            raise HTTPException(status_code=404, detail="No active QuickBooks connection found")

        # Check if token is expired and refresh if needed
        if connection.is_token_expired:
            async with QuickBooksService() as qb_service:
                token_response = await qb_service.refresh_access_token(
                    connection.refresh_token,
                    connection.realm_id
                )

            # Update connection with new tokens
            connection.access_token = token_response["access_token"]
            connection.refresh_token = token_response["refresh_token"]
            connection.token_expires_at = datetime.utcnow() + timedelta(
                seconds=token_response["expires_in"]
            )
            db.commit()

        # Get invoice data
        from app.models.invoice import Invoice, InvoiceExtraction
        invoice_uuid = uuid.UUID(invoice_id)
        invoice = db.query(Invoice).filter(Invoice.id == invoice_uuid).first()

        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        extraction = db.query(InvoiceExtraction).filter(
            InvoiceExtraction.invoice_id == invoice_uuid
        ).order_by(InvoiceExtraction.created_at.desc()).first()

        if not extraction:
            raise HTTPException(status_code=404, detail="No extraction found for this invoice")

        # Prepare invoice data for QuickBooks
        invoice_data = {
            "header": extraction.header_json,
            "lines": extraction.lines_json,
            "metadata": {
                "invoice_id": invoice_id,
                "vendor_id": str(invoice.vendor_id),
                "processed_at": invoice.updated_at.isoformat(),
                "confidence": extraction.confidence_json,
            }
        }

        # Export to QuickBooks
        async with QuickBooksService() as qb_service:
            result = await qb_service.create_bill(
                connection.access_token,
                connection.realm_id,
                invoice_data,
                dry_run
            )

        # Create export record
        from app.models.quickbooks import QuickBooksExport
        export_record = QuickBooksExport(
            connection_id=connection.id,
            invoice_id=invoice_uuid,
            quickbooks_bill_id=result.get("Id") if not dry_run else None,
            export_type="bill",
            status="success" if result.get("Bill") or dry_run else "failed",
            dry_run=dry_run,
            request_payload=invoice_data,
            response_payload=result
        )
        db.add(export_record)
        db.commit()

        return StandardResponse.success_response(
            data={
                "invoice_id": invoice_id,
                "bill_id": result.get("Id"),
                "total_amount": result.get("TotalAmt"),
                "dry_run": dry_run,
                "export_id": str(export_record.id)
            },
            message=f"Invoice {'validated' if dry_run else 'exported'} successfully"
        )

    except QuickBooksServiceException as e:
        logger.error(f"QuickBooks service error during export: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during export: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/export/batch", response_model=StandardResponse[Dict[str, Any]])
async def batch_export_invoices(
    request: BatchExportRequest = Body(...),
    user_id: str = Query(..., description="User ID for the connection"),
    db: Session = Depends(get_db)
):
    """
    Export multiple invoices to QuickBooks in a batch.

    This endpoint exports multiple invoices using batch operations for better performance.
    """
    try:
        logger.info(f"Batch exporting {len(request.invoice_ids)} invoices to QuickBooks for user {user_id}")

        # Get user's QuickBooks connection
        connection = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.user_id == uuid.UUID(user_id),
            QuickBooksConnection.status == QuickBooksConnectionStatus.CONNECTED
        ).first()

        if not connection:
            raise HTTPException(status_code=404, detail="No active QuickBooks connection found")

        # Check if token is expired and refresh if needed
        if connection.is_token_expired:
            async with QuickBooksService() as qb_service:
                token_response = await qb_service.refresh_access_token(
                    connection.refresh_token,
                    connection.realm_id
                )

            # Update connection with new tokens
            connection.access_token = token_response["access_token"]
            connection.refresh_token = token_response["refresh_token"]
            connection.token_expires_at = datetime.utcnow() + timedelta(
                seconds=token_response["expires_in"]
            )
            db.commit()

        # Get invoice data for all invoices
        from app.models.invoice import Invoice, InvoiceExtraction
        invoices_data = []

        for invoice_id in request.invoice_ids:
            invoice_uuid = uuid.UUID(invoice_id)
            invoice = db.query(Invoice).filter(Invoice.id == invoice_uuid).first()

            if not invoice:
                logger.warning(f"Invoice {invoice_id} not found, skipping")
                continue

            extraction = db.query(InvoiceExtraction).filter(
                InvoiceExtraction.invoice_id == invoice_uuid
            ).order_by(InvoiceExtraction.created_at.desc()).first()

            if not extraction:
                logger.warning(f"No extraction found for invoice {invoice_id}, skipping")
                continue

            invoice_data = {
                "header": extraction.header_json,
                "lines": extraction.lines_json,
                "metadata": {
                    "invoice_id": invoice_id,
                    "vendor_id": str(invoice.vendor_id),
                    "processed_at": invoice.updated_at.isoformat(),
                    "confidence": extraction.confidence_json,
                }
            }
            invoices_data.append(invoice_data)

        if not invoices_data:
            raise HTTPException(status_code=400, detail="No valid invoices found for export")

        # Export to QuickBooks using batch operation
        async with QuickBooksService() as qb_service:
            result = await qb_service.export_multiple_bills(
                connection.access_token,
                connection.realm_id,
                invoices_data,
                request.dry_run
            )

        return StandardResponse.success_response(
            data=result,
            message=f"Batch export completed: {result['success']} success, {result['failed']} failed"
        )

    except QuickBooksServiceException as e:
        logger.error(f"QuickBooks service error during batch export: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during batch export: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/webhook", response_model=StandardResponse[Dict[str, Any]])
async def quickbooks_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle webhooks from QuickBooks.

    This endpoint processes webhook notifications from QuickBooks for data changes.
    """
    try:
        # Get webhook data from request
        webhook_data = await request.json()

        # Get signature from headers if available
        signature = request.headers.get("intuit-signature")

        # Process webhook
        async with QuickBooksService() as qb_service:
            result = await qb_service.handle_webhook(webhook_data, signature)

        return StandardResponse.success_response(
            data=result,
            message="Webhook processed successfully"
        )

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/disconnect/{connection_id}", response_model=StandardResponse[Dict[str, str]])
async def disconnect_quickbooks(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """
    Disconnect a QuickBooks connection.

    This endpoint disconnects the app from QuickBooks and removes the connection.
    """
    try:
        logger.info(f"Disconnecting QuickBooks connection: {connection_id}")

        # Get connection
        connection = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.id == uuid.UUID(connection_id)
        ).first()

        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        # Disconnect from QuickBooks
        async with QuickBooksService() as qb_service:
            success = await qb_service.disconnect_app(
                connection.access_token,
                connection.realm_id
            )

        if success:
            # Update connection status
            connection.status = QuickBooksConnectionStatus.DISCONNECTED
            db.commit()

            return StandardResponse.success_response(
                data={"connection_id": connection_id},
                message="Successfully disconnected from QuickBooks"
            )
        else:
            # Still mark as disconnected in our system even if QuickBooks disconnection failed
            connection.status = QuickBooksConnectionStatus.ERROR
            connection.last_error = "Failed to disconnect from QuickBooks API"
            db.commit()

            return StandardResponse.success_response(
                data={"connection_id": connection_id},
                message="Disconnected locally (QuickBooks API disconnection failed)"
            )

    except QuickBooksServiceException as e:
        logger.error(f"QuickBooks service error during disconnection: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during disconnection: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/exports", response_model=StandardResponse[List[Dict[str, Any]]])
async def get_export_history(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    connection_id: Optional[str] = Query(None, description="Filter by connection ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, le=100, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    db: Session = Depends(get_db)
):
    """
    Get export history.

    Returns a list of QuickBooks exports with optional filtering.
    """
    try:
        query = db.query(QuickBooksExport)

        # Apply filters
        if user_id:
            # Join with QuickBooksConnection to filter by user_id
            from sqlalchemy import and_
            query = query.join(QuickBooksConnection).filter(
                QuickBooksConnection.user_id == uuid.UUID(user_id)
            )

        if connection_id:
            query = query.filter(QuickBooksExport.connection_id == uuid.UUID(connection_id))

        if status:
            query = query.filter(QuickBooksExport.status == status)

        # Apply pagination and ordering
        exports = query.order_by(QuickBooksExport.created_at.desc()).offset(offset).limit(limit).all()

        export_data = []
        for export in exports:
            export_data.append({
                "id": str(export.id),
                "connection_id": str(export.connection_id),
                "invoice_id": str(export.invoice_id),
                "quickbooks_bill_id": export.quickbooks_bill_id,
                "export_type": export.export_type,
                "status": export.status,
                "dry_run": export.dry_run,
                "error_message": export.error_message,
                "processing_time_ms": export.processing_time_ms,
                "created_at": export.created_at.isoformat(),
                "updated_at": export.updated_at.isoformat()
            })

        return StandardResponse.success_response(
            data=export_data,
            message=f"Retrieved {len(export_data)} export records"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving export history: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")