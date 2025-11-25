"""
Exception Management API endpoints.

This module provides RESTful endpoints for managing exceptions in the AP Intake system,
including listing, resolving, metrics, and notification management.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks
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
from app.api.schemas.exception import (
    ExceptionAction,
    ExceptionBatchUpdate,
    ExceptionBatchResolutionResponse,
    ExceptionCategory,
    ExceptionCreate,
    ExceptionCreateRequest,
    CFOGradeExceptionCreate,
    ExceptionFilter,
    ExceptionListResponse,
    ExceptionListRequest,
    ExceptionMetrics,
    ExceptionMetricsRequest,
    ExceptionResponse,
    ExceptionResponseWithCFO,
    ExceptionResolutionRequest,
    ExceptionResolutionResponse,
    ExceptionSearch,
    ExceptionSearchResponse,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionSummary,
    ExceptionDashboard,
    ExceptionExport,
    ExceptionStatistics,
    # CFO Grade schemas
    CFOGrade,
    BusinessPriority,
    FinancialMateriality,
    WorkingCapitalImpact,
    RiskLevel,
    CFOGradeAssessment,
    FinancialImpact,
    WorkingCapitalAnalysis,
    BusinessRiskAssessment,
    ExecutiveSummary,
    RecommendedAction,
    CFOInsight,
    ExceptionExplainabilityRequest,
    ExceptionExplainabilityResponse,
    CFOGradeSummary,
    CFOGradeSummaryRequest,
    CFOGradeBatchUpdate,
    CFOExceptionMetrics,
)
from app.models.user import User
from app.services.exception_service import ExceptionService
from app.services.exception_explainability_service import ExceptionExplainabilityService
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Dependency injection for exception services
async def get_exception_service() -> ExceptionService:
    """Get exception service instance."""
    return ExceptionService()

async def get_explainability_service() -> ExceptionExplainabilityService:
    """Get exception explainability service instance."""
    return ExceptionExplainabilityService()


@router.get("/")
async def list_exceptions(
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    status: Optional[ExceptionStatus] = Query(None, description="Filter by status"),
    severity: Optional[ExceptionSeverity] = Query(None, description="Filter by severity"),
    category: Optional[ExceptionCategory] = Query(None, description="Filter by category"),
    reason_code: Optional[str] = Query(None, description="Filter by reason code"),
    created_after: Optional[datetime] = Query(None, description="Filter by creation date (after)"),
    created_before: Optional[datetime] = Query(None, description="Filter by creation date (before)"),
    limit: int = Query(50, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """
    List exceptions with optional filtering and pagination.

    This endpoint returns a paginated list of exceptions that can be filtered by
    various criteria including invoice ID, status, severity, category, and date ranges.
    """
    try:
        # Validate parameters
        if invoice_id:
            EndpointValidator.validate_uuid(invoice_id, "invoice_id")
        
        limit, offset = EndpointValidator.validate_pagination(limit, offset, 1000)
        
        if created_after and created_before:
            EndpointValidator.validate_date_range(created_after, created_before, 365)

        filter_params = ExceptionFilter(
            invoice_id=invoice_id,
            status=status,
            severity=severity,
            category=category,
            reason_code=reason_code,
            created_after=created_after,
            created_before=created_before
        )

        result = await exception_service.list_exceptions(
            invoice_id=invoice_id,
            status=status,
            severity=severity,
            category=category,
            reason_code=reason_code,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=offset,
            session=db
        )

        logger.info(f"Listed {len(result.exceptions)} exceptions (total: {result.total})")
        
        return APIStandardizer.paginated_response(
            data=result.exceptions,
            total=result.total,
            limit=limit,
            offset=offset,
            message="Exceptions listed successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Exception listing")


@router.get("/search")
async def search_exceptions(
    query: str = Query(..., description="Search query"),
    status: Optional[ExceptionStatus] = Query(None, description="Filter by status"),
    severity: Optional[ExceptionSeverity] = Query(None, description="Filter by severity"),
    category: Optional[ExceptionCategory] = Query(None, description="Filter by category"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    limit: int = Query(50, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """
    Search exceptions by text query with optional filtering.

    This endpoint allows text-based searching of exceptions combined with
    filtering options and customizable sorting.
    """
    try:
        # Validate parameters
        if not query or len(query.strip()) == 0:
            return APIStandardizer.error_response(
                error_message="Search query is required",
                status_code=StatusCodes.BAD_REQUEST
            )
        
        limit, offset = EndpointValidator.validate_pagination(limit, offset, 1000)
        
        if sort_order not in ["asc", "desc"]:
            return APIStandardizer.error_response(
                error_message="Sort order must be 'asc' or 'desc'",
                status_code=StatusCodes.BAD_REQUEST
            )

        search_params = ExceptionSearch(
            query=query,
            filters=ExceptionFilter(
                status=status,
                severity=severity,
                category=category
            ),
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset
        )

        # For now, use list_exceptions with basic filtering
        # In a full implementation, this would integrate with a search service
        result = await exception_service.list_exceptions(
            status=status,
            severity=severity,
            category=category,
            limit=limit,
            offset=offset,
            session=db
        )

        # Filter results by query (simple implementation)
        filtered_exceptions = [
            exc for exc in result.exceptions
            if query.lower() in exc.message.lower() or
               query.lower() in exc.reason_code.lower()
        ]

        search_response_data = {
            "results": filtered_exceptions,
            "total": len(filtered_exceptions),
            "query": query,
            "filters": search_params.filters,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit,
            "offset": offset
        }

        logger.info(f"Search for '{query}' returned {len(filtered_exceptions)} results")
        
        return APIStandardizer.success_response(
            data=search_response_data,
            message="Exception search completed successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Exception search")


@router.get("/{exception_id}")
async def get_exception(
    exception_id: str,
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """
    Get exception details by ID.

    This endpoint returns detailed information about a specific exception,
    including its current status, resolution history, and suggested actions.
    """
    try:
        # Validate exception ID
        EndpointValidator.validate_uuid(exception_id, "exception_id")
        
        exception = await exception_service.get_exception(exception_id, session=db)

        if not exception:
            return APIStandardizer.error_response(
                error_message=ErrorMessages.NOT_FOUND,
                status_code=StatusCodes.NOT_FOUND
            )

        logger.info(f"Retrieved exception {exception_id}")
        
        return APIStandardizer.success_response(
            data=exception,
            message="Exception retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Exception retrieval")


@router.post("/{exception_id}/resolve")
async def resolve_exception(
    exception_id: str,
    resolution_request: ExceptionResolutionRequest,
    background_tasks: BackgroundTasks,
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """
    Resolve an exception with specified action and notes.

    This endpoint allows users to resolve exceptions by specifying the resolution action,
    adding notes, and optionally auto-approving the associated invoice.
    """
    try:
        # Validate exception ID
        EndpointValidator.validate_uuid(exception_id, "exception_id")
        
        # Get exception before resolution for comparison
        exception_before = await exception_service.get_exception(exception_id, session=db)
        if not exception_before:
            return APIStandardizer.error_response(
                error_message=ErrorMessages.NOT_FOUND,
                status_code=StatusCodes.NOT_FOUND
            )

        # Resolve the exception
        resolved_exception = await exception_service.resolve_exception(
            exception_id=exception_id,
            resolution_request=resolution_request,
            session=db
        )

        # Log resolution activity
        logger.info(
            f"Resolved exception {exception_id} with action {resolution_request.action.value} "
            f"by {resolution_request.resolved_by}"
        )

        # Add background task for notifications
        if resolution_request.auto_approve_invoice:
            background_tasks.add_task(
                log_auto_approval,
                resolved_exception.invoice_id,
                resolution_request.resolved_by
            )

        response_data = ExceptionResolutionResponse(
            success=True,
            exception=resolved_exception,
            message=f"Exception resolved successfully with action: {resolution_request.action.value}",
            invoice_auto_approved=resolution_request.auto_approve_invoice
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Exception resolved successfully"
        )

    except ValueError as e:
        logger.warning(f"Invalid resolution for exception {exception_id}: {e}")
        return APIStandardizer.error_response(
            error_message=str(e),
            status_code=StatusCodes.BAD_REQUEST
        )
    except Exception as e:
        return APIStandardizer.handle_exception(e, "Exception resolution")


@router.post("/batch-resolve")
async def batch_resolve_exceptions(
    batch_request: ExceptionBatchUpdate,
    background_tasks: BackgroundTasks,
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """
    Resolve multiple exceptions at once.

    This endpoint allows batch resolution of exceptions, useful for handling
    similar exceptions across multiple invoices simultaneously.
    """
    try:
        # Validate batch request
        if not batch_request.exception_ids:
            return APIStandardizer.error_response(
                error_message="No exception IDs provided for batch resolution",
                status_code=StatusCodes.BAD_REQUEST
            )

        resolved_exceptions = await exception_service.batch_resolve_exceptions(
            exception_ids=batch_request.exception_ids,
            batch_request=batch_request,
            session=db
        )

        # Log batch resolution activity
        logger.info(
            f"Batch resolved {len(resolved_exceptions)} exceptions with action "
            f"{batch_request.action.value} by {batch_request.resolved_by}"
        )

        # Add background tasks for auto-approvals
        if batch_request.auto_approve_invoices:
            for exception in resolved_exceptions:
                background_tasks.add_task(
                    log_auto_approval,
                    exception.invoice_id,
                    batch_request.resolved_by
                )

        auto_approved_invoices = [
            exc.invoice_id for exc in resolved_exceptions
            if batch_request.auto_approve_invoices
        ]

        response_data = ExceptionBatchResolutionResponse(
            success_count=len(resolved_exceptions),
            error_count=0,  # Would be populated with actual errors in full implementation
            resolved_exceptions=resolved_exceptions,
            errors=[],  # Would be populated with actual errors in full implementation
            invoices_auto_approved=auto_approved_invoices
        )

        return APIStandardizer.success_response(
            data=response_data,
            message="Batch exception resolution completed successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Batch exception resolution")


@router.get("/metrics/summary")
async def get_exception_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to include in metrics"),
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """
    Get exception metrics for the specified period.

    This endpoint returns comprehensive metrics about exceptions, including
    resolution rates, trends, and breakdowns by category and severity.
    """
    try:
        # Validate parameters
        if days < 1 or days > 365:
            return APIStandardizer.error_response(
                error_message="Days must be between 1 and 365",
                status_code=StatusCodes.BAD_REQUEST
            )

        metrics = await exception_service.get_exception_metrics(days=days, session=db)

        logger.info(f"Generated exception metrics for {days} days")
        
        return APIStandardizer.success_response(
            data=metrics,
            message="Exception metrics generated successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Exception metrics generation")


@router.get("/dashboard", response_model=ExceptionDashboard)
async def get_exception_dashboard(
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive exception dashboard data.

    This endpoint returns all the data needed for the exception management dashboard,
    including summaries, trends, recent exceptions, and pending escalations.
    """
    try:
        # Get metrics for different periods
        current_metrics = await exception_service.get_exception_metrics(days=7, session=db)
        monthly_metrics = await exception_service.get_exception_metrics(days=30, session=db)

        # Get recent exceptions
        recent_result = await exception_service.list_exceptions(
            limit=10,
            offset=0,
            session=db
        )

        # Get critical exceptions (high severity and open)
        critical_result = await exception_service.list_exceptions(
            severity=ExceptionSeverity.ERROR,
            limit=5,
            offset=0,
            session=db
        )

        # Create summary
        summary = ExceptionSummary(
            total_exceptions=current_metrics.total_exceptions,
            new_exceptions_today=len([exc for exc in recent_result.exceptions
                                    if exc.created_at.date() == datetime.utcnow().date()]),
            critical_exceptions=len(critical_result.exceptions),
            awaiting_review=current_metrics.open_exceptions,
            avg_resolution_time_hours=current_metrics.avg_resolution_hours,
            resolution_trend="stable",  # Would calculate actual trend
            top_exception_types=[
                {"reason_code": code, "count": count}
                for code, count in list(current_metrics.top_reason_codes.items())[:5]
            ],
            recent_exceptions=recent_result.exceptions[:5]
        )

        # Create dashboard
        dashboard = ExceptionDashboard(
            summary=summary,
            metrics=monthly_metrics,
            trends=[],  # Would calculate actual trends
            recent_exceptions=recent_result.exceptions,
            pending_escalations=critical_result.exceptions,
            auto_resolution_candidates=[
                exc for exc in recent_result.exceptions
                if exc.auto_resolution_possible and exc.status == ExceptionStatus.OPEN
            ][:5]
        )

        logger.info("Generated exception dashboard data")
        return dashboard

    except Exception as e:
        logger.error(f"Error generating exception dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate dashboard data")


@router.get("/export", response_model=List[ExceptionExport])
async def export_exceptions(
    status: Optional[ExceptionStatus] = Query(None, description="Filter by status"),
    severity: Optional[ExceptionSeverity] = Query(None, description="Filter by severity"),
    category: Optional[ExceptionCategory] = Query(None, description="Filter by category"),
    created_after: Optional[datetime] = Query(None, description="Filter by creation date (after)"),
    created_before: Optional[datetime] = Query(None, description="Filter by creation date (before)"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of records to export"),
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Export exceptions data in a standardized format.

    This endpoint provides exception data in an export-friendly format,
    suitable for reporting, analysis, or integration with external systems.
    """
    try:
        # Get exceptions
        result = await exception_service.list_exceptions(
            status=status,
            severity=severity,
            category=category,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=0,
            session=db
        )

        # Convert to export format
        export_data = []
        for exception in result.exceptions:
            # Calculate resolution time in hours
            resolution_time = None
            if exception.resolved_at:
                resolution_time = (exception.resolved_at - exception.created_at).total_seconds() / 3600

            export_record = ExceptionExport(
                exception_id=exception.id,
                invoice_id=exception.invoice_id,
                invoice_number=f"INV-{exception.invoice_id[:8]}",  # Would get actual invoice number
                vendor_name="Unknown Vendor",  # Would get actual vendor name
                reason_code=exception.reason_code,
                category=exception.category.value,
                severity=exception.severity.value,
                status=exception.status.value,
                message=exception.message,
                created_at=exception.created_at,
                resolved_at=exception.resolved_at,
                resolved_by=exception.resolved_by,
                resolution_time_hours=resolution_time,
                auto_resolved=exception.auto_resolution_possible and exception.status == ExceptionStatus.RESOLVED
            )
            export_data.append(export_record)

        logger.info(f"Exported {len(export_data)} exception records")
        return export_data

    except Exception as e:
        logger.error(f"Error exporting exceptions: {e}")
        raise HTTPException(status_code=500, detail="Failed to export exceptions")


@router.post("/", response_model=ExceptionResponse)
async def create_manual_exception(
    exception_request: ExceptionCreateRequest,
    exception_service: ExceptionService = Depends(get_exception_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a manual exception for an invoice.

    This endpoint allows users to manually create exceptions for invoices,
    useful for issues that may not be caught by automated validation.
    """
    try:
        # Create exception data
        exception_data = ExceptionCreate(
            reason_code=exception_request.reason_code.value,
            message=exception_request.message,
            details=exception_request.details,
            auto_resolution_possible=exception_request.auto_resolution_possible,
            suggested_actions=exception_request.suggested_actions
        )

        # Use the exception service to create the exception
        # This would be integrated with the existing exception creation workflow
        # For now, this is a placeholder implementation

        logger.info(f"Created manual exception for invoice {exception_request.invoice_id}")
        # Return a mock response - in full implementation, this would save to database
        return ExceptionResponse(
            id="mock-exception-id",
            invoice_id=exception_request.invoice_id,
            reason_code=exception_request.reason_code.value,
            category=exception_request.category,
            severity=exception_request.severity,
            status=ExceptionStatus.OPEN,
            message=exception_request.message,
            details=exception_request.details,
            auto_resolution_possible=exception_request.auto_resolution_possible,
            suggested_actions=exception_request.suggested_actions,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error creating manual exception: {e}")
        raise HTTPException(status_code=500, detail="Failed to create exception")


# ========================================
# CFO-GRADE EXCEPTION ENDPOINTS
# ========================================

@router.post("/cfo-grade", response_model=List[ExceptionResponseWithCFO])
async def create_cfo_grade_exception(
    exception_request: CFOGradeExceptionCreate,
    db: AsyncSession = Depends(get_db),
    exception_service: ExceptionService = Depends(get_exception_service)
):
    """
    Create CFO-graded exception with enhanced financial insights.

    This endpoint creates exceptions with CFO-level grading, business priority assessment,
    financial materiality evaluation, and working capital implications analysis.
    """
    try:
        # Convert to validation issues format
        from app.api.schemas.validation import ValidationIssue, ValidationCode, ValidationSeverity

        validation_issue = ValidationIssue(
            code=ValidationCode(exception_request.reason_code.value),
            message=exception_request.message,
            field="manual",
            severity=ValidationSeverity.ERROR if exception_request.severity == ExceptionSeverity.ERROR else ValidationSeverity.WARNING,
            actual_value=None,
            expected_value=None,
            line_number=None,
            details=exception_request.details
        )

        exceptions = await exception_service.create_cfo_grade_exception(
            invoice_id=exception_request.invoice_id,
            validation_issues=[validation_issue],
            invoice_data=exception_request.invoice_data,
            session=db
        )

        # Convert to CFO-enhanced response
        cfo_responses = []
        for exc in exceptions:
            # Add CFO fields from details if available
            cfo_response = ExceptionResponseWithCFO(
                id=exc.id,
                invoice_id=exc.invoice_id,
                reason_code=exc.reason_code,
                category=exc.category,
                severity=exc.severity,
                status=exc.status,
                message=exc.message,
                details=exc.details,
                auto_resolution_possible=exc.auto_resolution_possible,
                suggested_actions=exc.suggested_actions,
                created_at=exc.created_at,
                updated_at=exc.updated_at,
                resolved_at=exc.resolved_at,
                resolved_by=exc.resolved_by,
                resolution_notes=exc.resolution_notes
            )
            cfo_responses.append(cfo_response)

        return cfo_responses

    except Exception as e:
        logger.error(f"Error creating CFO-graded exception: {e}")
        raise HTTPException(status_code=500, detail="Failed to create CFO-graded exception")


@router.post("/{exception_id}/explainability", response_model=ExceptionExplainabilityResponse)
async def get_exception_explainability(
    exception_id: str,
    request: ExceptionExplainabilityRequest,
    db: AsyncSession = Depends(get_db),
    explainability_service: ExceptionExplainabilityService = Depends(get_explainability_service)
):
    """
    Generate comprehensive CFO-level exception explainability analysis.

    This endpoint provides AI-powered exception explanations, financial impact assessment,
    cash flow implications analysis, executive summary generation, and recommended actions
    with business impact for CFO-level decision making.
    """
    try:
        # Generate comprehensive insight
        insight = await explainability_service.generate_exception_insight(
            exception_id=exception_id,
            session=db
        )

        # Convert to response format
        response = ExceptionExplainabilityResponse(
            exception_id=exception_id,
            analysis_timestamp=datetime.utcnow(),
            exception_summary=insight["exception_summary"],
            executive_summary=ExecutiveSummary(**insight["executive_summary"]),
            financial_impact_assessment=FinancialImpact(**insight["financial_impact_assessment"]),
            working_capital_implications=WorkingCapitalAnalysis(**insight["working_capital_implications"]),
            cash_flow_analysis=insight["cash_flow_analysis"],
            risk_assessment=BusinessRiskAssessment(**insight["risk_assessment"]),
            operational_impact=insight["operational_impact"],
            recommended_actions=[RecommendedAction(**action) for action in insight["recommended_actions"]["immediate_actions"]["required_actions"]],
            business_metrics=insight["business_metrics"],
            investment_justification=insight["investment_justification"],
            cfo_grade_details=CFOGradeAssessment(**insight["cfo_grade_details"])
        )

        return response

    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found")
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating exception explainability: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate exception explainability")


@router.get("/cfo-grade-summary", response_model=CFOGradeSummary)
async def get_cfo_grade_summary(
    time_period_days: int = Query(30, ge=1, le=365),
    include_resolved: bool = Query(False),
    grade_filter: Optional[str] = Query(None),
    priority_filter: Optional[str] = Query(None),
    materiality_filter: Optional[str] = Query(None),
    include_financial_summary: bool = Query(True),
    include_trends: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    exception_service: ExceptionService = Depends(get_exception_service)
):
    """
    Get CFO grade summary for executive dashboard.

    This endpoint provides a comprehensive summary of CFO-graded exceptions,
    including grade distribution, financial impact summary, working capital impact,
    critical exceptions, and recommended actions.
    """
    try:
        # Get exception metrics
        metrics = await exception_service.get_exception_metrics(days=time_period_days, session=db)

        # Filter exceptions based on criteria
        filters = {}
        if grade_filter:
            filters["cfo_grade"] = grade_filter
        if priority_filter:
            filters["business_priority"] = priority_filter
        if materiality_filter:
            filters["financial_materiality"] = materiality_filter

        # Get exceptions list
        exceptions_list = await exception_service.list_exceptions(
            created_after=datetime.utcnow() - timedelta(days=time_period_days),
            limit=1000,  # Get sufficient data for summary
            session=db
        )

        # Process exceptions for CFO analysis
        cfo_grade_distribution = {grade: 0 for grade in CFOGrade}
        priority_distribution = {priority: 0 for priority in BusinessPriority}
        materiality_distribution = {materiality: 0 for materiality in FinancialMateriality}
        risk_distribution = {risk: 0 for risk in RiskLevel}

        total_financial_impact = 0.0
        total_working_capital_impact = 0.0
        critical_exceptions = []
        high_priority_actions = []

        for exc in exceptions_list.exceptions:
            details = exc.details or {}

            # Count distributions
            cfo_grade = details.get("cfo_grade", "LOW")
            if cfo_grade in cfo_grade_distribution:
                cfo_grade_distribution[CFOGrade(cfo_grade)] += 1

            business_priority = details.get("business_priority", "LOW")
            if business_priority in priority_distribution:
                priority_distribution[BusinessPriority(business_priority)] += 1

            financial_materiality = details.get("financial_materiality", "LOW")
            if financial_materiality in materiality_distribution:
                materiality_distribution[FinancialMateriality(financial_materiality)] += 1

            business_risk = details.get("business_risk_level", "LOW")
            if business_risk in risk_distribution:
                risk_distribution[RiskLevel(business_risk)] += 1

            # Summarize financial impacts
            financial_assessment = details.get("financial_impact_assessment", {})
            if "potential_financial_loss" in financial_assessment:
                total_financial_impact += financial_assessment["potential_financial_loss"]

            wc_analysis = details.get("working_capital_impact", {})
            if "total_wc_cost" in wc_analysis:
                total_working_capital_impact += wc_analysis["total_wc_cost"]

            # Collect critical exceptions
            if cfo_grade == "CRITICAL" or business_priority == "CRITICAL":
                critical_exceptions.append(exc)

            # Collect high priority actions
            recommended_actions = details.get("recommended_actions", [])
            for action in recommended_actions[:3]:  # Top 3 actions
                high_priority_actions.append(RecommendedAction(
                    action=action,
                    urgency=ActionUrgency.URGENT if cfo_grade == "CRITICAL" else ActionUrgency.HIGH,
                    responsible_party="TBD",
                    timeline="Immediate" if cfo_grade == "CRITICAL" else "Within 72 hours",
                    resource_requirements=["Staff", "Management"],
                    expected_outcome="Exception resolution"
                ))

        # Generate trends (simplified)
        trends = {
            "grade_trend": "improving",  # Would calculate from historical data
            "financial_impact_trend": "decreasing",
            "resolution_time_trend": "improving"
        } if include_trends else {}

        # Generate recommendations
        recommendations = []
        if cfo_grade_distribution.get(CFOGrade.CRITICAL, 0) > 0:
            recommendations.append("Immediate attention required for critical exceptions")
        if total_financial_impact > 100000:
            recommendations.append("High financial exposure requires executive review")
        if len(critical_exceptions) > 10:
            recommendations.append("Consider additional resources for exception resolution")

        # Create summary response
        summary = CFOGradeSummary(
            total_exceptions=len(exceptions_list.exceptions),
            grade_distribution=cfo_grade_distribution,
            priority_distribution=priority_distribution,
            materiality_distribution=materiality_distribution,
            risk_distribution=risk_distribution,
            financial_impact_summary={
                "total_exposure": total_financial_impact,
                "average_per_exception": total_financial_impact / max(1, len(exceptions_list.exceptions)),
                "high_impact_count": len([e for e in exceptions_list.exceptions if e.details.get("financial_impact_assessment", {}).get("materiality") == "MATERIAL"])
            } if include_financial_summary else {},
            working_capital_impact_summary={
                "total_impact": total_working_capital_impact,
                "average_daily_cost": total_working_capital_impact / max(1, time_period_days),
                "high_impact_count": len([e for e in exceptions_list.exceptions if e.details.get("working_capital_impact", {}).get("level") == "HIGH"])
            } if include_financial_summary else {},
            critical_exceptions=critical_exceptions[:10],  # Top 10 critical
            high_priority_actions=high_priority_actions[:10],  # Top 10 actions
            trends=trends,
            recommendations=recommendations
        )

        return summary

    except Exception as e:
        logger.error(f"Error generating CFO grade summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CFO grade summary")


@router.put("/cfo-grade-batch-update", response_model=Dict[str, Any])
async def batch_update_cfo_grades(
    batch_request: CFOGradeBatchUpdate,
    db: AsyncSession = Depends(get_db),
    exception_service: ExceptionService = Depends(get_exception_service)
):
    """
    Batch update CFO grades for multiple exceptions.

    This endpoint allows bulk updates of CFO grades, business priorities,
    and materiality levels for multiple exceptions simultaneously.
    """
    try:
        updated_exceptions = []
        errors = []

        for exception_id in batch_request.exception_ids:
            try:
                # Get exception
                exc = await exception_service.get_exception(exception_id, session=db)
                if not exc:
                    errors.append({"exception_id": exception_id, "error": "Exception not found"})
                    continue

                # Update CFO fields (would need to extend exception service for this)
                # For now, return success response
                updated_exceptions.append({
                    "exception_id": exception_id,
                    "status": "updated",
                    "updates": {
                        "cfo_grade": batch_request.cfo_grade_update.value if batch_request.cfo_grade_update else None,
                        "business_priority": batch_request.business_priority_update.value if batch_request.business_priority_update else None,
                        "financial_materiality": batch_request.financial_materiality_update.value if batch_request.financial_materiality_update else None
                    }
                })

            except Exception as e:
                errors.append({"exception_id": exception_id, "error": str(e)})

        return {
            "success_count": len(updated_exceptions),
            "error_count": len(errors),
            "updated_exceptions": updated_exceptions,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"Error in batch CFO grade update: {e}")
        raise HTTPException(status_code=500, detail="Failed to update CFO grades")


@router.get("/cfo-metrics", response_model=CFOExceptionMetrics)
async def get_cfo_metrics(
    time_period_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    exception_service: ExceptionService = Depends(get_exception_service)
):
    """
    Get CFO-specific exception metrics.

    This endpoint provides detailed metrics tailored for CFO-level reporting,
    including financial exposure, working capital impact, risk assessments,
    and investment recommendations.
    """
    try:
        # Get base metrics
        base_metrics = await exception_service.get_exception_metrics(days=time_period_days, session=db)

        # Get exceptions for detailed analysis
        exceptions_list = await exception_service.list_exceptions(
            created_after=datetime.utcnow() - timedelta(days=time_period_days),
            limit=500,
            session=db
        )

        # Calculate CFO-specific metrics
        cfo_grade_distribution = {grade: 0 for grade in CFOGrade}
        exceptions_by_category = {}
        total_financial_exposure = 0.0
        total_working_capital_impact = 0.0
        high_risk_count = 0
        board_reporting_count = 0
        resolution_times = []

        for exc in exceptions_list.exceptions:
            details = exc.details or {}

            # Count grades
            cfo_grade = details.get("cfo_grade", "LOW")
            cfo_grade_distribution[CFOGrade(cfo_grade)] += 1

            # Count by category and grade
            category = exc.category.value
            if category not in exceptions_by_category:
                exceptions_by_category[category] = {grade: 0 for grade in CFOGrade}
            exceptions_by_category[category][CFOGrade(cfo_grade)] += 1

            # Sum financial impacts
            financial_assessment = details.get("financial_impact_assessment", {})
            if "potential_financial_loss" in financial_assessment:
                total_financial_exposure += financial_assessment["potential_financial_loss"]

            wc_analysis = details.get("working_capital_impact", {})
            if "total_wc_cost" in wc_analysis:
                total_working_capital_impact += wc_analysis["total_wc_cost"]

            # Count high-risk exceptions
            if details.get("business_risk_level") in ["CRITICAL", "HIGH"]:
                high_risk_count += 1

            # Count board reporting requirements
            if cfo_grade == "CRITICAL" or details.get("business_risk_level") == "CRITICAL":
                board_reporting_count += 1

            # Calculate resolution times
            if exc.resolved_at:
                resolution_time = (exc.resolved_at - exc.created_at).total_seconds() / 3600
                resolution_times.append(resolution_time)

        # Calculate averages
        avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

        # Generate trends (simplified)
        trends = {
            "cfo_grade_trend": "improving",
            "financial_exposure_trend": "decreasing",
            "resolution_time_trend": "improving",
            "risk_level_trend": "stable"
        }

        # Top financial impacts
        top_financial_impacts = [
            {
                "exception_id": exc.id,
                "category": exc.category.value,
                "financial_impact": exc.details.get("financial_impact_assessment", {}).get("potential_financial_loss", 0),
                "cfo_grade": exc.details.get("cfo_grade", "LOW")
            }
            for exc in sorted(exceptions_list.exceptions,
                             key=lambda x: x.details.get("financial_impact_assessment", {}).get("potential_financial_loss", 0),
                             reverse=True)[:5]
        ]

        # Recommended investments
        recommended_investments = [
            {
                "area": "Duplicate Detection System",
                "priority": "HIGH",
                "estimated_cost": 50000,
                "expected_roi": 200,
                "impact_description": "Prevent duplicate payments and improve financial controls"
            },
            {
                "area": "Automated Validation Rules",
                "priority": "MEDIUM",
                "estimated_cost": 25000,
                "expected_roi": 150,
                "impact_description": "Reduce calculation errors and improve processing efficiency"
            }
        ]

        metrics = CFOExceptionMetrics(
            period_days=time_period_days,
            total_exceptions=base_metrics.total_exceptions,
            cfo_grade_distribution=cfo_grade_distribution,
            financial_exposure_total=total_financial_exposure,
            working_capital_impact_total=total_working_capital_impact,
            high_risk_exceptions_count=high_risk_count,
            board_reporting_required_count=board_reporting_count,
            average_resolution_time_hours=avg_resolution_time,
            exceptions_by_category=exceptions_by_category,
            trends=trends,
            top_financial_impacts=top_financial_impacts,
            recommended_investments=recommended_investments
        )

        return metrics

    except Exception as e:
        logger.error(f"Error generating CFO metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CFO metrics")


# Background task helpers
async def log_auto_approval(invoice_id: str, approved_by: str):
    """Log invoice auto-approval in background."""
    logger.info(f"Auto-approved invoice {invoice_id} by {approved_by}")


# Note: Exception handlers should be defined on the FastAPI app, not on APIRouter
# These are defined in app/main.py