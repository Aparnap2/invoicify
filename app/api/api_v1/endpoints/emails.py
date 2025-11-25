"""
API endpoints for email ingestion and management.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1.standards import (
    APIStandardizer,
    EndpointValidator,
    DatabaseHelper,
    StatusCodes,
    ErrorMessages,
    get_db_session,
    get_authenticated_user
)
from app.api.schemas.email import (
    EmailAuthorizationRequest,
    EmailAuthorizationResponse,
    EmailCredentialsCreate,
    EmailCredentialsResponse,
    EmailMonitoringConfigCreate,
    EmailMonitoringConfigResponse,
    EmailSearchRequest,
    EmailSearchResponse,
    EmailIngestionRequest,
    EmailIngestionResponse,
    EmailStatisticsResponse,
)
from app.models.email import Email, EmailCredentials, EmailMonitoringConfig
from app.models.user import User
from app.services.email_ingestion_service import EmailIngestionService
from app.services.gmail_service import GmailService
from app.workers.email_tasks import (
    monitor_gmail_inbox,
    schedule_email_monitoring,
    get_email_monitoring_task_status,
    cancel_email_monitoring,
    get_active_email_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/authorize/gmail")
async def authorize_gmail(
    request: EmailAuthorizationRequest,
    current_user: User = Depends(get_authenticated_user),
) -> EmailAuthorizationResponse:
    """Get Gmail OAuth authorization URL."""
    try:
        gmail_service = GmailService()
        authorization_url, state = await gmail_service.get_authorization_url(
            redirect_uri=request.redirect_uri,
            state=request.state
        )

        response_data = EmailAuthorizationResponse(
            authorization_url=authorization_url,
            state=state,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Gmail authorization URL generated successfully",
            status_code=StatusCodes.OK
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Gmail authorization")


@router.post("/credentials/gmail")
async def store_gmail_credentials(
    request: EmailCredentialsCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Store Gmail OAuth credentials."""
    try:
        gmail_service = GmailService()

        # Exchange authorization code for credentials
        credentials = await gmail_service.exchange_code_for_credentials(
            authorization_code=request.authorization_code,
            redirect_uri=request.redirect_uri
        )

        # Build service to validate credentials and get user info
        await gmail_service.build_service(credentials)
        user_info = await gmail_service.get_user_info()

        # Create credentials record
        db_credentials = EmailCredentials(
            user_id=request.user_id,
            provider="gmail",
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_expiry=credentials.expiry,
            provider_user_id=user_info["email_address"],
            provider_email=user_info["email_address"],
            last_validated=datetime.utcnow()
        )

        db.add(db_credentials)
        await db.commit()
        await db.refresh(db_credentials)

        response_data = EmailCredentialsResponse(
            id=str(db_credentials.id),
            provider="gmail",
            provider_email=user_info["email_address"],
            is_active=True,
            created_at=db_credentials.created_at,
            last_validated=db_credentials.last_validated
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Gmail credentials stored successfully",
            status_code=StatusCodes.CREATED
        )

    except Exception as e:
        await db.rollback()
        return APIStandardizer.handle_exception(e, "Gmail credentials storage")


@router.post("/ingest/gmail")
async def ingest_gmail_emails(
    request: EmailIngestionRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Manually trigger Gmail email ingestion."""
    try:
        # Get credentials from database
        credentials = await DatabaseHelper.get_by_id_or_404(
            db, EmailCredentials, request.credentials_id
        )

        # Convert to GmailCredentials format
        from app.services.gmail_service import GmailCredentials
        gmail_creds = GmailCredentials(
            token=credentials.access_token,
            refresh_token=credentials.refresh_token,
            client_id="",  # These would come from settings
            client_secret="",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"]
        )

        # Trigger background task
        task = monitor_gmail_inbox.delay(
            user_id=str(credentials.user_id),
            credentials_data=gmail_creds.model_dump(),
            days_back=request.days_back,
            max_emails=request.max_emails,
            auto_process=request.auto_process
        )

        response_data = EmailIngestionResponse(
            task_id=task.id,
            status="started",
            user_id=str(credentials.user_id),
            estimated_emails=request.max_emails,
            started_at=datetime.utcnow()
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Gmail ingestion started successfully",
            status_code=StatusCodes.ACCEPTED
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Gmail email ingestion")


@router.post("/monitoring/config")
async def create_monitoring_config(
    request: EmailMonitoringConfigCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Create email monitoring configuration."""
    try:
        # Validate credentials exist
        credentials = await DatabaseHelper.get_by_id_or_404(
            db, EmailCredentials, request.credentials_id
        )

        # Create monitoring config
        config = EmailMonitoringConfig(
            user_id=request.user_id,
            credentials_id=request.credentials_id,
            is_active=request.is_active,
            monitoring_interval_minutes=request.monitoring_interval_minutes,
            days_back_to_process=request.days_back_to_process,
            max_emails_per_run=request.max_emails_per_run,
            email_filters=request.email_filters,
            trusted_senders=request.trusted_senders,
            blocked_senders=request.blocked_senders,
            auto_process_invoices=request.auto_process_invoices,
            security_validation_enabled=request.security_validation_enabled
        )

        db.add(config)
        await db.commit()
        await db.refresh(config)

        # Schedule monitoring task if active
        if request.is_active:
            from app.services.gmail_service import GmailCredentials
            gmail_creds = GmailCredentials(
                token=credentials.access_token,
                refresh_token=credentials.refresh_token,
                client_id="",
                client_secret="",
                scopes=["https://www.googleapis.com/auth/gmail.readonly"]
            )

            schedule_task = schedule_email_monitoring.delay(
                user_id=str(request.user_id),
                credentials_data=gmail_creds.model_dump(),
                schedule_minutes=request.monitoring_interval_minutes
            )

            logger.info(f"Scheduled monitoring task {schedule_task.id} for user {request.user_id}")

        response_data = EmailMonitoringConfigResponse(
            id=str(config.id),
            user_id=str(config.user_id),
            is_active=config.is_active,
            monitoring_interval_minutes=config.monitoring_interval_minutes,
            created_at=config.created_at,
            last_run_at=config.last_run_at,
            next_run_at=config.next_run_at
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Email monitoring configuration created successfully",
            status_code=StatusCodes.CREATED
        )

    except Exception as e:
        await db.rollback()
        return APIStandardizer.handle_exception(e, "Email monitoring configuration creation")


@router.get("/monitoring/status/{user_id}")
async def get_monitoring_status(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Get monitoring status for a user."""
    try:
        # Validate user ID format
        EndpointValidator.validate_uuid(user_id, "user_id")

        # Get task status
        task_status = get_email_monitoring_task_status(user_id)

        # Get monitoring configs
        result = await db.execute(
            "SELECT * FROM email_monitoring_configs WHERE user_id = :user_id",
            {"user_id": user_id}
        )
        configs = result.fetchall()

        response_data = {
            "user_id": user_id,
            "task_status": task_status,
            "monitoring_configs": len(configs),
            "active_configs": sum(1 for c in configs if c.is_active),
            "checked_at": datetime.utcnow().isoformat()
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="Email monitoring status retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Email monitoring status retrieval")


@router.delete("/monitoring/{user_id}")
async def stop_monitoring(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Stop email monitoring for a user."""
    try:
        # Validate user ID format
        EndpointValidator.validate_uuid(user_id, "user_id")

        # Cancel scheduled task
        cancelled = cancel_email_monitoring(user_id)

        # Deactivate monitoring configs
        await db.execute(
            "UPDATE email_monitoring_configs SET is_active = false WHERE user_id = :user_id",
            {"user_id": user_id}
        )
        await db.commit()

        response_data = {
            "user_id": user_id,
            "cancelled": cancelled,
            "stopped_at": datetime.utcnow().isoformat()
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="Email monitoring stopped successfully"
        )

    except Exception as e:
        await db.rollback()
        return APIStandardizer.handle_exception(e, "Email monitoring stop")


@router.get("/search")
async def search_emails(
    user_id: str = Query(..., description="User ID"),
    query: str = Query(None, description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Search for processed emails."""
    try:
        # Validate parameters
        EndpointValidator.validate_uuid(user_id, "user_id")
        limit, offset = EndpointValidator.validate_pagination(limit, offset, 100)

        # Build search query
        sql = """
            SELECT e.*, COUNT(a.id) as attachment_count
            FROM emails e
            LEFT JOIN email_attachments a ON e.id = a.email_id
            WHERE e.user_id = :user_id
        """
        params = {"user_id": user_id}

        if query:
            sql += " AND (e.subject ILIKE :query OR e.from_email ILIKE :query)"
            params["query"] = f"%{query}%"

        sql += " GROUP BY e.id ORDER BY e.date_sent DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = await db.execute(sql, params)
        emails = result.fetchall()

        # Get total count
        count_sql = "SELECT COUNT(*) FROM emails WHERE user_id = :user_id"
        if query:
            count_sql += " AND (subject ILIKE :query OR from_email ILIKE :query)"

        count_result = await db.execute(count_sql, params)
        total = count_result.scalar()

        email_data = [{
            "id": str(email.id),
            "subject": email.subject,
            "from_email": email.from_email,
            "date_sent": email.date_sent,
            "status": email.status,
            "attachment_count": email.attachment_count,
            "security_flags": email.security_flags
        } for email in emails]

        return APIStandardizer.paginated_response(
            data=email_data,
            total=total,
            limit=limit,
            offset=offset,
            message="Email search completed successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Email search")


@router.get("/statistics/{user_id}")
async def get_email_statistics(
    user_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """Get email processing statistics."""
    try:
        # Validate parameters
        EndpointValidator.validate_uuid(user_id, "user_id")
        if days < 1 or days > 365:
            raise HTTPException(
                status_code=StatusCodes.BAD_REQUEST,
                detail="Days must be between 1 and 365"
            )

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get statistics
        stats_sql = """
            SELECT
                COUNT(*) as total_emails,
                COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed_emails,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_emails,
                COUNT(CASE WHEN status = 'blocked' THEN 1 END) as blocked_emails,
                AVG(CASE WHEN status = 'processed' THEN
                    EXTRACT(EPOCH FROM (processed_at - created_at)) * 1000
                END) as avg_processing_time_ms
            FROM emails
            WHERE user_id = :user_id AND created_at >= :cutoff_date
        """

        result = await db.execute(stats_sql, {"user_id": user_id, "cutoff_date": cutoff_date})
        stats = result.fetchone()

        # Get attachment statistics
        attachment_sql = """
            SELECT
                COUNT(*) as total_attachments,
                COUNT(CASE WHEN is_pdf THEN 1 END) as pdf_attachments,
                COUNT(CASE WHEN is_processed THEN 1 END) as processed_attachments
            FROM email_attachments a
            JOIN emails e ON a.email_id = e.id
            WHERE e.user_id = :user_id AND a.created_at >= :cutoff_date
        """

        attachment_result = await db.execute(attachment_sql, {"user_id": user_id, "cutoff_date": cutoff_date})
        attachment_stats = attachment_result.fetchone()

        response_data = EmailStatisticsResponse(
            user_id=user_id,
            period_days=days,
            total_emails=stats.total_emails or 0,
            processed_emails=stats.processed_emails or 0,
            failed_emails=stats.failed_emails or 0,
            blocked_emails=stats.blocked_emails or 0,
            total_attachments=attachment_stats.total_attachments or 0,
            pdf_attachments=attachment_stats.pdf_attachments or 0,
            processed_attachments=attachment_stats.processed_attachments or 0,
            avg_processing_time_ms=int(stats.avg_processing_time_ms or 0),
            success_rate=(
                (stats.processed_emails / stats.total_emails * 100) if stats.total_emails > 0 else 0
            ),
            generated_at=datetime.utcnow()
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Email statistics retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Email statistics retrieval")


@router.get("/health")
async def email_health_check():
    """Health check for email services."""
    try:
        ingestion_service = EmailIngestionService()
        health_status = await ingestion_service.health_check()

        response_data = {
            "status": "healthy",
            "services": health_status,
            "timestamp": datetime.utcnow().isoformat()
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="Email services health check completed"
        )

    except Exception as e:
        return APIStandardizer.error_response(
            error_message="Email services health check failed",
            status_code=StatusCodes.SERVICE_UNAVAILABLE,
            error_details={"error": str(e)}
        )


@router.get("/tasks/active")
async def get_active_tasks(
    current_user: User = Depends(get_authenticated_user),
):
    """Get list of active email monitoring tasks."""
    try:
        active_tasks = get_active_email_tasks()

        response_data = {
            "active_tasks": active_tasks,
            "total_active": len(active_tasks),
            "timestamp": datetime.utcnow().isoformat()
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="Active email tasks retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Active email tasks retrieval")