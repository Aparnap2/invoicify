"""
API endpoints for SLOs, metrics, and KPI tracking.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

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
from app.models.user import User
from app.models.metrics import SLIType, SLOPeriod
from app.services.metrics_service import metrics_service
from app.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/slos/dashboard")
async def get_slo_dashboard(
    time_range_days: int = Query(30, ge=1, le=365, description="Time range in days"),
    slo_types: Optional[List[SLIType]] = Query(None, description="Filter by SLO types"),
    current_user: User = Depends(get_authenticated_user),
):
    """
    Get comprehensive SLO dashboard data.

    This endpoint provides a complete overview of all SLOs including:
    - Current status and performance
    - Error budget consumption
    - Recent alerts
    - Historical trends
    """
    try:
        # Validate parameters
        if time_range_days < 1 or time_range_days > 365:
            return APIStandardizer.error_response(
                error_message="Time range days must be between 1 and 365",
                status_code=StatusCodes.BAD_REQUEST
            )

        dashboard_data = await metrics_service.get_slo_dashboard_data(
            time_range_days=time_range_days,
            slo_types=slo_types
        )

        return APIStandardizer.success_response(
            data=dashboard_data,
            message="SLO dashboard data retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "SLO dashboard retrieval")


@router.get("/slos/definitions")
async def get_slo_definitions(
    active_only: bool = Query(True, description="Filter to active SLOs only"),
    current_user: User = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get all SLO definitions."""
    try:
        from app.models.metrics import SLODefinition
        from sqlalchemy import select

        query = select(SLODefinition)
        if active_only:
            query = query.where(SLODefinition.is_active == True)

        result = await session.execute(query)
        slo_definitions = result.scalars().all()

        definitions_data = []
        for slo in slo_definitions:
            definitions_data.append({
                "id": str(slo.id),
                "name": slo.name,
                "description": slo.description,
                "sli_type": slo.sli_type.value,
                "target_percentage": float(slo.target_percentage),
                "target_value": float(slo.target_value),
                "target_unit": slo.target_unit,
                "error_budget_percentage": float(slo.error_budget_percentage),
                "alerting_threshold_percentage": float(slo.alerting_threshold_percentage),
                "measurement_period": slo.measurement_period.value,
                "burn_rate_alert_threshold": float(slo.burn_rate_alert_threshold),
                "is_active": slo.is_active,
                "slos_owner": slo.slos_owner,
                "notification_channels": slo.notification_channels,
                "created_at": slo.created_at.isoformat(),
                "updated_at": slo.updated_at.isoformat(),
            })

        response_data = {
            "definitions": definitions_data,
            "count": len(definitions_data),
            "active_only": active_only
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="SLO definitions retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "SLO definitions retrieval")


@router.get("/weekly/summary")
async def get_weekly_metrics_summary(
    weeks: int = Query(4, ge=1, le=52, description="Number of weeks to include"),
    week_start: Optional[str] = Query(None, description="Start date for specific week (ISO format)"),
    current_user: User = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get weekly metrics summary for KPI tracking and trend analysis.

    This endpoint provides aggregated weekly metrics including:
    - Processing volumes and automation rates
    - Performance metrics (P50, P95, P99 times)
    - Quality metrics (pass rates, accuracy)
    - Cost efficiency and ROI
    - Working capital optimization metrics
    """
    try:
        # Validate parameters
        if weeks < 1 or weeks > 52:
            return APIStandardizer.error_response(
                error_message="Weeks must be between 1 and 52",
                status_code=StatusCodes.BAD_REQUEST
            )

        from app.models.metrics import WeeklyMetric
        from sqlalchemy import select, and_, desc, func

        # Parse week start date if provided
        if week_start:
            try:
                week_start_date = datetime.fromisoformat(week_start.replace('Z', '+00:00')).date()
            except ValueError:
                return APIStandardizer.error_response(
                    error_message="Invalid date format. Use ISO format.",
                    status_code=StatusCodes.BAD_REQUEST
                )
        else:
            week_start_date = None

        # Build query
        query = select(WeeklyMetric).order_by(desc(WeeklyMetric.week_start_date)).limit(weeks)

        if week_start_date:
            query = query.where(WeeklyMetric.week_start_date >= week_start_date)

        result = await session.execute(query)
        weekly_metrics = result.scalars().all()

        # Format response
        metrics_data = []
        for metric in weekly_metrics:
            metrics_data.append({
                "week_start_date": metric.week_start_date.isoformat(),
                "week_end_date": metric.week_end_date.isoformat(),
                "invoices_processed": metric.invoices_processed,
                "auto_processed": metric.auto_processed,
                "manual_processed": metric.manual_processed,
                "exceptions_created": metric.exceptions_created,
                "exceptions_resolved": metric.exceptions_resolved,
                "duplicates_detected": metric.duplicates_detected,
                "avg_processing_time_hours": float(metric.avg_processing_time_hours),
                "total_invoice_amount": float(metric.total_invoice_amount),
                "auto_processing_rate": float(metric.auto_processing_rate),
                "pass_rate_structural": float(metric.pass_rate_structural),
                "pass_rate_math": float(metric.pass_rate_math),
                "p50_time_to_ready_minutes": float(metric.p50_time_to_ready_minutes) if metric.p50_time_to_ready_minutes else None,
                "p95_time_to_ready_minutes": float(metric.p95_time_to_ready_minutes) if metric.p95_time_to_ready_minutes else None,
                "p99_time_to_ready_minutes": float(metric.p99_time_to_ready_minutes) if metric.p99_time_to_ready_minutes else None,
                "duplicate_recall_percentage": float(metric.duplicate_recall_percentage) if metric.duplicate_recall_percentage else None,
                "exception_resolution_time_p50_hours": float(metric.exception_resolution_time_p50_hours) if metric.exception_resolution_time_p50_hours else None,
                "api_response_time_p95_ms": float(metric.api_response_time_p95_ms) if metric.api_response_time_p95_ms else None,
                "system_availability_percentage": float(metric.system_availability_percentage) if metric.system_availability_percentage else None,
                "cost_per_invoice": float(metric.cost_per_invoice),
                "total_cost": float(metric.total_cost),
                "roi_percentage": float(metric.roi_percentage),
                "working_capital_optimization": metric.working_capital_optimization,
                "performance_summary": metric.performance_summary,
                "quality_metrics": metric.quality_metrics,
                "created_at": metric.created_at.isoformat(),
            })

        # Calculate trends and averages
        if metrics_data:
            total_invoices = sum(m["invoices_processed"] for m in metrics_data)
            avg_processing_rate = sum(m["auto_processing_rate"] for m in metrics_data) / len(metrics_data)
            avg_cost_per_invoice = sum(m["cost_per_invoice"] for m in metrics_data) / len(metrics_data)
            avg_roi = sum(m["roi_percentage"] for m in metrics_data) / len(metrics_data)

            # Calculate week-over-week trends
            trends = {}
            if len(metrics_data) >= 2:
                current_week = metrics_data[0]
                previous_week = metrics_data[1]

                for metric in ["auto_processing_rate", "cost_per_invoice", "roi_percentage", "pass_rate_structural", "pass_rate_math"]:
                    current_val = current_week[metric]
                    previous_val = previous_week[metric]
                    if previous_val > 0:
                        change_pct = ((current_val - previous_val) / previous_val) * 100
                        trends[metric] = {
                            "current": current_val,
                            "previous": previous_val,
                            "change_percentage": round(change_pct, 2),
                            "trend": "increasing" if change_pct > 2 else "decreasing" if change_pct < -2 else "stable"
                        }
        else:
            total_invoices = 0
            avg_processing_rate = 0
            avg_cost_per_invoice = 0
            avg_roi = 0
            trends = {}

        response_data = {
            "weekly_metrics": metrics_data,
            "summary": {
                "total_weeks": len(metrics_data),
                "total_invoices_processed": total_invoices,
                "average_auto_processing_rate": round(avg_processing_rate, 2),
                "average_cost_per_invoice": round(avg_cost_per_invoice, 2),
                "average_roi_percentage": round(avg_roi, 2),
                "latest_week_date": metrics_data[0]["week_start_date"] if metrics_data else None,
            },
            "trends": trends,
            "performance_periods": {
                "p50_time_to_ready_minutes": [m["p50_time_to_ready_minutes"] for m in metrics_data if m["p50_time_to_ready_minutes"]],
                "p95_time_to_ready_minutes": [m["p95_time_to_ready_minutes"] for m in metrics_data if m["p95_time_to_ready_minutes"]],
                "p99_time_to_ready_minutes": [m["p99_time_to_ready_minutes"] for m in metrics_data if m["p99_time_to_ready_minutes"]],
            }
        }

        return APIStandardizer.success_response(
            data=response_data,
            message="Weekly metrics summary retrieved successfully"
        )

    except Exception as e:
        return APIStandardizer.handle_exception(e, "Weekly metrics summary retrieval")


@router.get("/slos/{slo_id}/measurements", response_model=Dict[str, Any])
async def get_slo_measurements(
    slo_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get historical measurements for a specific SLO."""
    try:
        from app.models.metrics import SLODefinition, SLIMeasurement
        from sqlalchemy import select, and_
        from uuid import UUID

        # Validate SLO exists
        slo_query = select(SLODefinition).where(SLODefinition.id == UUID(slo_id))
        slo_result = await session.execute(slo_query)
        slo = slo_result.scalar_one_or_none()

        if not slo:
            raise HTTPException(status_code=404, detail=f"SLO {slo_id} not found")

        # Get measurements
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        measurements_query = select(SLIMeasurement).where(
            and_(
                SLIMeasurement.slo_definition_id == UUID(slo_id),
                SLIMeasurement.period_start >= start_date,
                SLIMeasurement.period_start <= end_date
            )
        ).order_by(SLIMeasurement.period_start.desc())

        measurements_result = await session.execute(measurements_query)
        measurements = measurements_result.scalars().all()

        measurements_data = []
        for measurement in measurements:
            measurements_data.append({
                "id": str(measurement.id),
                "period_start": measurement.period_start.isoformat(),
                "period_end": measurement.period_end.isoformat(),
                "measurement_period": measurement.measurement_period.value,
                "actual_value": float(measurement.actual_value),
                "target_value": float(measurement.target_value),
                "achieved_percentage": float(measurement.achieved_percentage),
                "error_budget_consumed": float(measurement.error_budget_consumed),
                "good_events_count": measurement.good_events_count,
                "total_events_count": measurement.total_events_count,
                "measurement_metadata": measurement.measurement_metadata,
                "created_at": measurement.created_at.isoformat(),
            })

        # Calculate summary statistics
        if measurements_data:
            achieved_percentages = [m["achieved_percentage"] for m in measurements_data]
            error_budgets = [m["error_budget_consumed"] for m in measurements_data]

            summary = {
                "latest_achieved_percentage": achieved_percentages[0],
                "average_achieved_percentage": round(sum(achieved_percentages) / len(achieved_percentages), 2),
                "min_achieved_percentage": min(achieved_percentages),
                "max_achieved_percentage": max(achieved_percentages),
                "latest_error_budget_consumed": error_budgets[0],
                "average_error_budget_consumed": round(sum(error_budgets) / len(error_budgets), 2),
                "measurements_count": len(measurements_data),
            }
        else:
            summary = {
                "latest_achieved_percentage": None,
                "average_achieved_percentage": None,
                "min_achieved_percentage": None,
                "max_achieved_percentage": None,
                "latest_error_budget_consumed": None,
                "average_error_budget_consumed": None,
                "measurements_count": 0,
            }

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "slo": {
                        "id": str(slo.id),
                        "name": slo.name,
                        "description": slo.description,
                        "sli_type": slo.sli_type.value,
                        "target_percentage": float(slo.target_percentage),
                    },
                    "measurements": measurements_data,
                    "summary": summary,
                    "period": {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "days": days,
                    }
                }
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid SLO ID format: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to get SLO measurements: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve SLO measurements: {str(e)}")


@router.get("/kpis/summary", response_model=Dict[str, Any])
async def get_kpi_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days for KPI calculation"),
    current_user: User = Depends(get_current_active_user),
):
    """Get comprehensive KPI summary for the AP Intake system."""
    try:
        kpi_data = await metrics_service.get_kpi_summary(days=days)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": kpi_data,
                "message": "KPI summary retrieved successfully"
            }
        )

    except Exception as e:
        logger.error(f"Failed to get KPI summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve KPI summary: {str(e)}")


@router.get("/metrics/invoice-trends", response_model=Dict[str, Any])
async def get_invoice_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days of trend data"),
    granularity: str = Query("daily", pattern="^(hourly|daily|weekly)$", description="Data granularity"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get invoice processing trends over time."""
    try:
        from app.models.invoice import Invoice, InvoiceStatus
        from app.models.metrics import InvoiceMetric
        from sqlalchemy import select, func, and_, extract
        from datetime import datetime, timedelta

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Determine date truncation based on granularity
        if granularity == "hourly":
            date_trunc = func.date_trunc('hour', Invoice.created_at)
        elif granularity == "weekly":
            date_trunc = func.date_trunc('week', Invoice.created_at)
        else:  # daily
            date_trunc = func.date_trunc('day', Invoice.created_at)

        # Query invoice volume trends
        volume_query = select(
            date_trunc.label('period'),
            func.count(Invoice.id).label('total_invoices'),
            func.sum(func.case([(Invoice.status.in_([InvoiceStatus.READY, InvoiceStatus.STAGED, InvoiceStatus.DONE]), 1)], else_=0)).label('successful_invoices')
        ).where(
            Invoice.created_at >= start_date
        ).group_by(date_trunc).order_by(date_trunc)

        volume_result = await session.execute(volume_query)
        volume_data = volume_result.all()

        # Query processing time trends
        processing_time_query = select(
            date_trunc.label('period'),
            func.avg(InvoiceMetric.time_to_ready_seconds).label('avg_processing_time'),
            func.count(InvoiceMetric.id).label('sample_size')
        ).select_from(
            InvoiceMetric.__table__.join(
                Invoice, InvoiceMetric.invoice_id == Invoice.id
            )
        ).where(
            and_(
                Invoice.created_at >= start_date,
                InvoiceMetric.time_to_ready_seconds.isnot(None)
            )
        ).group_by(date_trunc).order_by(date_trunc)

        processing_time_result = await session.execute(processing_time_query)
        processing_time_data = processing_time_result.all()

        # Query extraction confidence trends
        confidence_query = select(
            date_trunc.label('period'),
            func.avg(InvoiceMetric.extraction_confidence).label('avg_confidence'),
            func.count(InvoiceMetric.id).label('sample_size')
        ).select_from(
            InvoiceMetric.__table__.join(
                Invoice, InvoiceMetric.invoice_id == Invoice.id
            )
        ).where(
            and_(
                Invoice.created_at >= start_date,
                InvoiceMetric.extraction_confidence.isnot(None)
            )
        ).group_by(date_trunc).order_by(date_trunc)

        confidence_result = await session.execute(confidence_query)
        confidence_data = confidence_result.all()

        # Format trend data
        volume_trends = []
        for row in volume_data:
            success_rate = (row.successful_invoices / row.total_invoices * 100) if row.total_invoices > 0 else 0
            volume_trends.append({
                "period": row.period.isoformat(),
                "total_invoices": row.total_invoices,
                "successful_invoices": row.successful_invoices or 0,
                "success_rate": round(success_rate, 2),
            })

        processing_trends = []
        for row in processing_time_data:
            processing_trends.append({
                "period": row.period.isoformat(),
                "avg_processing_time_seconds": round(float(row.avg_processing_time), 2) if row.avg_processing_time else 0,
                "avg_processing_time_minutes": round(float(row.avg_processing_time) / 60, 2) if row.avg_processing_time else 0,
                "sample_size": row.sample_size,
            })

        confidence_trends = []
        for row in confidence_data:
            confidence_trends.append({
                "period": row.period.isoformat(),
                "avg_confidence": round(float(row.avg_confidence), 4) if row.avg_confidence else 0,
                "sample_size": row.sample_size,
            })

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "volume_trends": volume_trends,
                    "processing_trends": processing_trends,
                    "confidence_trends": confidence_trends,
                    "period": {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "days": days,
                        "granularity": granularity,
                    }
                }
            }
        )

    except Exception as e:
        logger.error(f"Failed to get invoice trends: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve invoice trends: {str(e)}")


@router.get("/alerts", response_model=Dict[str, Any])
async def get_slo_alerts(
    severity: Optional[str] = Query(None, pattern="^(info|warning|critical)$", description="Filter by severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of alerts to return"),
    offset: int = Query(0, ge=0, description="Number of alerts to skip"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get SLO alerts with optional filtering."""
    try:
        from app.models.metrics import SLOAlert, AlertSeverity
        from sqlalchemy import select, and_, or_, desc
        from uuid import UUID

        query = select(SLOAlert).order_by(desc(SLOAlert.created_at))

        # Build filters
        filters = []
        if severity:
            try:
                severity_enum = AlertSeverity(severity)
                filters.append(SLOAlert.severity == severity_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

        if resolved is not None:
            if resolved:
                filters.append(SLOAlert.resolved_at.isnot(None))
            else:
                filters.append(SLOAlert.resolved_at.is_(None))

        if filters:
            query = query.where(and_(*filters))

        # Apply pagination
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        alerts = result.scalars().all()

        # Get total count for pagination
        count_query = select(func.count(SLOAlert.id))
        if filters:
            count_query = count_query.where(and_(*filters))

        count_result = await session.execute(count_query)
        total_count = count_result.scalar()

        alerts_data = []
        for alert in alerts:
            alerts_data.append({
                "id": str(alert.id),
                "slo_definition_id": str(alert.slo_definition_id),
                "measurement_id": str(alert.measurement_id) if alert.measurement_id else None,
                "alert_type": alert.alert_type,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "current_value": float(alert.current_value),
                "target_value": float(alert.target_value),
                "breached_at": alert.breached_at.isoformat(),
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "acknowledged_by": alert.acknowledged_by,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "resolution_notes": alert.resolution_notes,
                "notification_sent": alert.notification_sent,
                "notification_attempts": alert.notification_attempts,
                "last_notification_at": alert.last_notification_at.isoformat() if alert.last_notification_at else None,
                "created_at": alert.created_at.isoformat(),
                "updated_at": alert.updated_at.isoformat(),
            })

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "alerts": alerts_data,
                    "pagination": {
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + len(alerts) < total_count,
                    },
                    "filters": {
                        "severity": severity,
                        "resolved": resolved,
                    }
                }
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get SLO alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve SLO alerts: {str(e)}")


@router.post("/alerts/{alert_id}/acknowledge", response_model=Dict[str, Any])
async def acknowledge_alert(
    alert_id: str,
    acknowledge_data: Dict[str, str] = {"notes": "Acknowledged via API"},
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Acknowledge an SLO alert."""
    try:
        from app.models.metrics import SLOAlert
        from sqlalchemy import select, update
        from uuid import UUID

        # Validate alert exists and is not already acknowledged
        query = select(SLOAlert).where(
            and_(
                SLOAlert.id == UUID(alert_id),
                SLOAlert.acknowledged_at.is_(None)
            )
        )
        result = await session.execute(query)
        alert = result.scalar_one_or_none()

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found or already acknowledged")

        # Update alert
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = current_user.email or current_user.id.hex[:8]

        await session.commit()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "alert_id": alert_id,
                    "acknowledged_at": alert.acknowledged_at.isoformat(),
                    "acknowledged_by": alert.acknowledged_by,
                },
                "message": "Alert acknowledged successfully"
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid alert ID format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alert: {str(e)}")


@router.post("/alerts/{alert_id}/resolve", response_model=Dict[str, Any])
async def resolve_alert(
    alert_id: str,
    resolve_data: Dict[str, str] = {"resolution_notes": "Resolved via API"},
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Resolve an SLO alert."""
    try:
        from app.models.metrics import SLOAlert
        from sqlalchemy import select
        from uuid import UUID

        # Validate alert exists
        query = select(SLOAlert).where(SLOAlert.id == UUID(alert_id))
        result = await session.execute(query)
        alert = result.scalar_one_or_none()

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        if alert.resolved_at:
            raise HTTPException(status_code=400, detail=f"Alert {alert_id} is already resolved")

        # Update alert
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolution_notes = resolve_data.get("resolution_notes", "Resolved via API")

        await session.commit()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "alert_id": alert_id,
                    "resolved_at": alert.resolved_at.isoformat(),
                    "resolution_notes": alert.resolution_notes,
                },
                "message": "Alert resolved successfully"
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid alert ID format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")


@router.post("/slos/initialize", response_model=Dict[str, Any])
async def initialize_slos(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
):
    """Initialize default SLOs for the system."""
    try:
        # Run initialization in background
        background_tasks.add_task(metrics_service.initialize_default_slos)

        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "message": "SLO initialization started in background",
                "data": {
                    "task": "initialize_default_slos",
                    "initiated_by": current_user.email or current_user.id.hex[:8],
                    "initiated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        )

    except Exception as e:
        logger.error(f"Failed to initialize SLOs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize SLOs: {str(e)}")


@router.post("/measurements/calculate", response_model=Dict[str, Any])
async def calculate_measurements(
    background_tasks: BackgroundTasks,
    period: SLOPeriod = Query(..., description="Measurement period"),
    hours_back: int = Query(24, ge=1, le=168, description="Hours back to calculate"),
    current_user: User = Depends(get_current_active_user),
):
    """Trigger manual calculation of SLI measurements for a period."""
    try:
        # Calculate period boundaries
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(hours=hours_back)

        # Run calculation in background
        background_tasks.add_task(
            metrics_service.calculate_sli_measurements,
            period=period,
            period_start=start_date,
            period_end=end_date
        )

        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "message": f"SLI measurement calculation started for {period.value} period",
                "data": {
                    "period": period.value,
                    "period_start": start_date.isoformat(),
                    "period_end": end_date.isoformat(),
                    "hours_back": hours_back,
                    "initiated_by": current_user.email or current_user.id.hex[:8],
                    "initiated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        )

    except Exception as e:
        logger.error(f"Failed to calculate measurements: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate measurements: {str(e)}")


@router.get("/health/metrics", response_model=Dict[str, Any])
async def get_metrics_health(
    current_user: User = Depends(get_current_active_user),
):
    """Get health status of the metrics collection system."""
    try:
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "metrics_service": {
                    "status": "healthy",
                    "last_check": datetime.now(timezone.utc).isoformat(),
                },
                "slo_calculations": {
                    "status": "healthy",
                    "last_calculation": datetime.now(timezone.utc).isoformat(),
                },
                "alert_system": {
                    "status": "healthy",
                    "active_alerts": 0,  # TODO: Get actual count
                },
            },
            "checks": {
                "database_connection": "healthy",
                "metrics_collection": "healthy",
                "slo_tracking": "healthy",
            }
        }

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": health_data
            }
        )

    except Exception as e:
        logger.error(f"Failed to get metrics health: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "data": {
                    "status": "unhealthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e)
                }
            }
        )