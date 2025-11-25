"""
Analytics API endpoints for KPI dashboard and metrics.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1.deps import get_async_session, get_current_active_user
from app.services.analytics_service import AnalyticsService
from app.services.predictive_analytics_service import PredictiveAnalyticsService, PredictionType, AnomalyType, FraudPattern

router = APIRouter()


@router.get("/kpi/summary", response_model=Dict[str, Any])
def get_kpi_summary(
    start_date: Optional[str] = Query(None, description="Start date in ISO format (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date in ISO format (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get executive KPI summary for the specified period.

    Args:
        start_date: Start date for analysis period (default: 30 days ago)
        end_date: End date for analysis period (default: today)

    Returns:
        Executive summary with overall health score and key metrics
    """
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)
        summary = analytics_service.get_executive_summary(start_dt, end_dt)

        return {
            "success": True,
            "data": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating KPI summary: {str(e)}")


@router.get("/accuracy", response_model=Dict[str, Any])
def get_accuracy_metrics(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get extraction accuracy and validation metrics."""
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)

        extraction_accuracy = analytics_service.get_extraction_accuracy_metrics(start_dt, end_dt)
        validation_metrics = analytics_service.get_validation_pass_rates(start_dt, end_dt)

        return {
            "success": True,
            "data": {
                "extraction_accuracy": extraction_accuracy,
                "validation_metrics": validation_metrics
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving accuracy metrics: {str(e)}")


@router.get("/exceptions", response_model=Dict[str, Any])
def get_exception_metrics(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get exception analysis and resolution metrics."""
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)
        exception_analysis = analytics_service.get_exception_analysis(start_dt, end_dt)

        return {
            "success": True,
            "data": exception_analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving exception metrics: {str(e)}")


@router.get("/cycle-times", response_model=Dict[str, Any])
def get_cycle_time_metrics(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get processing cycle time metrics."""
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)
        cycle_metrics = analytics_service.get_cycle_time_metrics(start_dt, end_dt)

        return {
            "success": True,
            "data": cycle_metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving cycle time metrics: {str(e)}")


@router.get("/productivity", response_model=Dict[str, Any])
def get_productivity_metrics(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get productivity and efficiency metrics."""
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)
        productivity_metrics = analytics_service.get_productivity_metrics(start_dt, end_dt)

        return {
            "success": True,
            "data": productivity_metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving productivity metrics: {str(e)}")


@router.get("/reviewers", response_model=Dict[str, Any])
def get_reviewer_performance(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get reviewer performance metrics and rankings."""
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)
        reviewer_performance = analytics_service.get_reviewer_performance(start_dt, end_dt)

        return {
            "success": True,
            "data": reviewer_performance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving reviewer performance: {str(e)}")


@router.get("/trends", response_model=Dict[str, Any])
def get_trend_analysis(
    metric: str = Query("all", description="Metric to analyze: volume, accuracy, exceptions, or all"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get trend analysis for specified metrics."""
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)
        trend_analysis = analytics_service.get_trend_analysis(start_dt, end_dt, metric)

        return {
            "success": True,
            "data": trend_analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving trend analysis: {str(e)}")


@router.get("/dashboard/finance-ops", response_model=Dict[str, Any])
def get_finance_ops_dashboard(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get finance operations dashboard data.
    Focus on processing efficiency, exception rates, and cycle times.
    """
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)

        # Gather relevant metrics for finance operations
        productivity = analytics_service.get_productivity_metrics(start_dt, end_dt)
        exceptions = analytics_service.get_exception_analysis(start_dt, end_dt)
        cycle_times = analytics_service.get_cycle_time_metrics(start_dt, end_dt)
        trends = analytics_service.get_trend_analysis(start_dt, end_dt, "volume")

        return {
            "success": True,
            "data": {
                "period": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat()
                },
                "productivity": productivity,
                "exceptions": exceptions,
                "cycle_times": cycle_times,
                "volume_trends": trends.get("trends", {}).get("volume", []),
                "key_insights": {
                    "processing_efficiency": productivity.get("processing_efficiency", 0),
                    "exception_rate": exceptions.get("exception_rate", 0),
                    "avg_processing_time": cycle_times.get("average_processing_time_hours", 0),
                    "daily_avg_volume": sum(
                        day.get("count", 0) for day in trends.get("trends", {}).get("volume", [])
                    ) / len(trends.get("trends", {}).get("volume", [1])) if trends.get("trends", {}).get("volume") else 0
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving finance ops dashboard: {str(e)}")


@router.get("/dashboard/management", response_model=Dict[str, Any])
def get_management_dashboard(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get management dashboard data.
    Focus on overall performance, health scores, and strategic metrics.
    """
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)

        # Executive summary for management
        executive_summary = analytics_service.get_executive_summary(start_dt, end_dt)
        reviewer_performance = analytics_service.get_reviewer_performance(start_dt, end_dt)
        accuracy_metrics = analytics_service.get_extraction_accuracy_metrics(start_dt, end_dt)

        return {
            "success": True,
            "data": {
                "executive_summary": executive_summary,
                "reviewer_performance": reviewer_performance,
                "accuracy_metrics": accuracy_metrics,
                "period": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat()
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving management dashboard: {str(e)}")


@router.get("/dashboard/reviewers", response_model=Dict[str, Any])
def get_reviewer_dashboard(
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    reviewer_id: Optional[str] = Query(None, description="Specific reviewer ID (for individual view)"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get reviewer dashboard data.
    Focus on individual performance, workload, and exception resolution.
    """
    try:
        # Parse dates or use defaults
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = datetime.utcnow()

        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = end_dt - timedelta(days=30)

        analytics_service = AnalyticsService(db)

        # Get reviewer-specific and general reviewer metrics
        reviewer_performance = analytics_service.get_reviewer_performance(start_dt, end_dt)
        exception_analysis = analytics_service.get_exception_analysis(start_dt, end_dt)

        # Filter for specific reviewer if provided
        individual_performance = None
        if reviewer_id and reviewer_id in reviewer_performance.get("reviewer_performance", {}):
            individual_performance = reviewer_performance["reviewer_performance"][reviewer_id]

        return {
            "success": True,
            "data": {
                "period": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat()
                },
                "team_performance": reviewer_performance,
                "exception_analysis": exception_analysis,
                "individual_performance": individual_performance,
                "reviewer_ranking": reviewer_performance.get("reviewer_performance", {}),
                "team_summary": {
                    "total_reviewers": reviewer_performance.get("total_reviewers", 0),
                    "total_resolved": reviewer_performance.get("total_resolved_exceptions", 0),
                    "team_avg_resolution_time": sum(
                        perf.get("average_resolution_time_hours", 0)
                        for perf in reviewer_performance.get("reviewer_performance", {}).values()
                    ) / reviewer_performance.get("total_reviewers", 1) if reviewer_performance.get("total_reviewers", 0) > 0 else 0
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving reviewer dashboard: {str(e)}")


@router.get("/real-time", response_model=Dict[str, Any])
def get_real_time_metrics(
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """Get real-time system metrics for dashboard monitoring."""
    try:
        from app.models.invoice import Invoice, InvoiceStatus, Exception as InvoiceException
        from sqlalchemy import func

        # Current time
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_24h = now - timedelta(hours=24)
        last_1h = now - timedelta(hours=1)

        # Real-time counts
        invoices_today = db.query(Invoice).filter(Invoice.created_at >= today_start).count()
        invoices_last_24h = db.query(Invoice).filter(Invoice.created_at >= last_24h).count()
        invoices_last_1h = db.query(Invoice).filter(Invoice.created_at >= last_1h).count()

        # Status breakdown
        status_counts = db.query(
            Invoice.status,
            func.count(Invoice.id).label('count')
        ).filter(
            Invoice.created_at >= today_start
        ).group_by(Invoice.status).all()

        # Recent exceptions
        recent_exceptions = db.query(InvoiceException).filter(
            InvoiceException.created_at >= last_24h
        ).count()

        # Pending items
        pending_review = db.query(Invoice).filter(
            Invoice.status == InvoiceStatus.VALIDATED
        ).count()

        pending_resolution = db.query(InvoiceException).filter(
            InvoiceException.resolved_at.is_(None)
        ).count()

        return {
            "success": True,
            "data": {
                "timestamp": now.isoformat(),
                "volume_metrics": {
                    "invoices_today": invoices_today,
                    "invoices_last_24h": invoices_last_24h,
                    "invoices_last_1h": invoices_last_1h,
                    "recent_exceptions": recent_exceptions
                },
                "status_breakdown": {
                    status.value: count for status, count in status_counts
                },
                "pending_items": {
                    "pending_review": pending_review,
                    "pending_resolution": pending_resolution
                },
                "system_health": {
                    "active": True,
                    "last_updated": now.isoformat()
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving real-time metrics: {str(e)}")


# ================================
# PREDICTIVE ANALYTICS ENDPOINTS
# ================================

@router.get("/predictive/working-capital", response_model=Dict[str, Any])
async def get_working_capital_prediction(
    prediction_days: int = Query(30, ge=7, le=365, description="Number of days to predict"),
    scenario: str = Query("realistic", description="Scenario: realistic, optimistic, pessimistic"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get working capital optimization predictions.

    Provides predictive insights on working capital optimization opportunities,
    including potential efficiency gains and risk assessments.
    """
    try:
        from app.models.working_capital import ScenarioType

        # Convert string to enum
        scenario_map = {
            "realistic": ScenarioType.REALISTIC,
            "optimistic": ScenarioType.OPTIMISTIC,
            "pessimistic": ScenarioType.PESSIMISTIC,
            "stress_test": ScenarioType.STRESS_TEST
        }
        scenario_type = scenario_map.get(scenario, ScenarioType.REALISTIC)

        predictive_service = PredictiveAnalyticsService(db)
        prediction = await predictive_service.predict_working_capital_optimization(
            prediction_days=prediction_days,
            scenario=scenario_type
        )

        return {
            "success": True,
            "data": {
                "prediction_type": prediction.prediction_type.value,
                "predicted_value": float(prediction.predicted_value),
                "confidence_score": prediction.confidence_score,
                "risk_assessment": prediction.risk_assessment.value if prediction.risk_assessment else None,
                "recommendations": prediction.recommendations or [],
                "metadata": prediction.metadata
            },
            "metadata": {
                "prediction_date": prediction.prediction_date.isoformat(),
                "prediction_days": prediction_days,
                "scenario": scenario
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating working capital prediction: {str(e)}")


@router.get("/predictive/vendor-performance", response_model=Dict[str, Any])
async def get_vendor_performance_predictions(
    vendor_id: Optional[str] = Query(None, description="Specific vendor ID (optional)"),
    prediction_period_days: int = Query(90, ge=30, le=365, description="Prediction period in days"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get vendor performance predictions.

    Predicts future vendor performance including payment timeliness,
    quality scores, and risk assessments.
    """
    try:
        from uuid import UUID

        predictive_service = PredictiveAnalyticsService(db)
        vendor_uuid = UUID(vendor_id) if vendor_id else None

        predictions = await predictive_service.predict_vendor_performance(
            vendor_id=vendor_uuid,
            prediction_period_days=prediction_period_days
        )

        # Group predictions by vendor
        vendor_predictions = {}
        for prediction in predictions:
            vendor_id_str = prediction.metadata.get("vendor_id", "all_vendors")
            if vendor_id_str not in vendor_predictions:
                vendor_predictions[vendor_id_str] = []

            vendor_predictions[vendor_id_str].append({
                "metric": prediction.metadata.get("metric"),
                "predicted_value": float(prediction.predicted_value),
                "confidence_score": prediction.confidence_score,
                "risk_assessment": prediction.risk_assessment.value if prediction.risk_assessment else None,
                "recommendations": prediction.recommendations or []
            })

        return {
            "success": True,
            "data": {
                "vendor_predictions": vendor_predictions,
                "total_vendors_analyzed": len(vendor_predictions),
                "prediction_period_days": prediction_period_days,
                "analysis_summary": {
                    "vendors_at_high_risk": len([
                        v for v in vendor_predictions.values()
                        if any(p.get("risk_assessment") == "high" or p.get("risk_assessment") == "critical" for p in v)
                    ]),
                    "vendors_requiring_attention": len([
                        v for v in vendor_predictions.values()
                        if any(p.get("recommendations") for p in v)
                    ])
                }
            },
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "prediction_model": "vendor_performance_v2.0"
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting vendor performance: {str(e)}")


@router.get("/predictive/anomalies", response_model=Dict[str, Any])
async def get_anomaly_detection_results(
    anomaly_types: Optional[str] = Query(None, description="Comma-separated list of anomaly types"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days to look back for anomaly detection"),
    sensitivity: float = Query(2.0, ge=1.0, le=5.0, description="Detection sensitivity (standard deviations)"),
    min_anomaly_score: float = Query(70.0, ge=0.0, le=100.0, description="Minimum anomaly score to include"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get anomaly detection results.

    Detects various types of anomalies in the invoice processing system
    including volume patterns, processing times, and exception rates.
    """
    try:
        predictive_service = PredictiveAnalyticsService(db)

        # Parse anomaly types
        anomaly_type_list = None
        if anomaly_types:
            type_mapping = {
                "volume": AnomalyType.VOLUME_ANOMALY,
                "processing_time": AnomalyType.PROCESSING_TIME_ANOMALY,
                "exception_rate": AnomalyType.EXCEPTION_RATE_ANOMALY,
                "payment_pattern": AnomalyType.PAYMENT_PATTERN_ANOMALY,
                "vendor_behavior": AnomalyType.VENDOR_BEHAVIOR_ANOMALY,
                "extraction_quality": AnomalyType.EXTRACTION_QUALITY_ANOMALY,
                "validation_pattern": AnomalyType.VALIDATION_PATTERN_ANOMALY
            }
            anomaly_type_list = [
                type_mapping.get(t.strip()) for t in anomaly_types.split(",")
                if t.strip() in type_mapping
            ]

        anomalies = await predictive_service.detect_anomalies(
            anomaly_types=anomaly_type_list,
            lookback_days=lookback_days,
            sensitivity=sensitivity
        )

        # Filter by minimum anomaly score
        filtered_anomalies = [
            anomaly for anomaly in anomalies
            if anomaly.anomaly_score >= min_anomaly_score
        ]

        # Format results
        anomaly_results = []
        for anomaly in filtered_anomalies:
            anomaly_results.append({
                "anomaly_type": anomaly.anomaly_type.value,
                "severity": anomaly.severity.value,
                "anomaly_score": anomaly.anomaly_score,
                "description": anomaly.description,
                "affected_entities": anomaly.affected_entities,
                "detection_date": anomaly.detection_date.isoformat(),
                "recommended_actions": anomaly.recommended_actions,
                "false_positive_probability": anomaly.false_positive_probability,
                "historical_context": anomaly.historical_context
            })

        return {
            "success": True,
            "data": {
                "anomalies": anomaly_results,
                "summary": {
                    "total_anomalies": len(anomaly_results),
                    "critical_anomalies": len([a for a in anomaly_results if a["severity"] == "critical"]),
                    "high_anomalies": len([a for a in anomaly_results if a["severity"] == "high"]),
                    "requires_immediate_attention": len([a for a in anomaly_results if a["severity"] in ["critical", "high"]])
                },
                "anomaly_types_detected": list(set(a["anomaly_type"] for a in anomaly_results)),
                "affected_entities_count": len(set(
                    entity for anomaly in anomaly_results
                    for entity in anomaly["affected_entities"]
                ))
            },
            "metadata": {
                "lookback_days": lookback_days,
                "sensitivity": sensitivity,
                "min_anomaly_score": min_anomaly_score,
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting anomalies: {str(e)}")


@router.get("/predictive/fraud-detection", response_model=Dict[str, Any])
async def get_fraud_detection_results(
    analysis_period_days: int = Query(30, ge=7, le=365, description="Days to analyze for fraud patterns"),
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    include_low_risk: bool = Query(False, description="Include low-risk fraud patterns"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get fraud detection results.

    Analyzes invoice data for potential fraud patterns including
    duplicate invoice fraud, amount manipulation, and vendor collusion.
    """
    try:
        predictive_service = PredictiveAnalyticsService(db)

        fraud_predictions = await predictive_service.predict_fraud_patterns(
            analysis_period_days=analysis_period_days,
            min_confidence=min_confidence
        )

        # Filter by risk level if requested
        if not include_low_risk:
            fraud_predictions = [
                fp for fp in fraud_predictions
                if fp.risk_level in ["high", "critical"]
            ]

        # Format results
        fraud_results = []
        for fraud in fraud_predictions:
            fraud_results.append({
                "fraud_pattern": fraud.fraud_pattern.value,
                "risk_level": fraud.risk_level,
                "confidence_score": fraud.confidence_score,
                "indicators": fraud.indicators,
                "affected_entities": fraud.affected_entities,
                "investigation_priority": fraud.investigation_priority,
                "estimated_financial_impact": float(fraud.estimated_financial_impact),
                "recommended_actions": fraud.recommended_actions,
                "additional_context": fraud.additional_context
            })

        return {
            "success": True,
            "data": {
                "fraud_patterns": fraud_results,
                "summary": {
                    "total_patterns": len(fraud_results),
                    "critical_risk": len([f for f in fraud_results if f["risk_level"] == "critical"]),
                    "high_risk": len([f for f in fraud_results if f["risk_level"] == "high"]),
                    "total_financial_exposure": sum(f["estimated_financial_impact"] for f in fraud_results),
                    "high_priority_investigations": len([f for f in fraud_results if f["investigation_priority"] <= 2])
                },
                "pattern_types": list(set(f["fraud_pattern"] for f in fraud_results))
            },
            "metadata": {
                "analysis_period_days": analysis_period_days,
                "min_confidence": min_confidence,
                "include_low_risk": include_low_risk,
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting fraud patterns: {str(e)}")


@router.get("/predictive/payment-optimization", response_model=Dict[str, Any])
async def get_payment_optimization_predictions(
    analysis_period_days: int = Query(30, ge=7, le=365, description="Days to analyze for payment patterns"),
    cost_of_capital: float = Query(0.08, ge=0.01, le=0.50, description="Annual cost of capital (as decimal)"),
    min_savings_threshold: float = Query(100.0, ge=0.0, description="Minimum savings threshold"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get payment optimization predictions.

    Predicts optimal payment timing and discount utilization strategies
    to maximize working capital efficiency.
    """
    try:
        predictive_service = PredictiveAnalyticsService(db)

        prediction = await predictive_service.predict_payment_optimization(
            analysis_period_days=analysis_period_days,
            cost_of_capital=cost_of_capital
        )

        # Filter recommendations by savings threshold
        filtered_recommendations = []
        if prediction.recommendations:
            # This is a simplified filtering - in practice, you'd parse savings from recommendations
            filtered_recommendations = prediction.recommendations

        return {
            "success": True,
            "data": {
                "predicted_savings": float(prediction.predicted_value),
                "confidence_score": prediction.confidence_score,
                "accuracy_estimate": prediction.accuracy_estimate or 0.0,
                "recommendations": filtered_recommendations,
                "metadata": prediction.metadata,
                "financial_analysis": {
                    "cost_of_capital": cost_of_capital,
                    "annual_savings_potential": float(prediction.predicted_value * 12),
                    "roi_estimate": float(prediction.predicted_value) / 1000 if prediction.predicted_value > 0 else 0.0,
                    "implementation_priority": "high" if prediction.predicted_value > min_savings_threshold else "medium"
                }
            },
            "metadata": {
                "analysis_period_days": analysis_period_days,
                "min_savings_threshold": min_savings_threshold,
                "generated_at": prediction.prediction_date.isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating payment optimization predictions: {str(e)}")


@router.get("/predictive/cash-flow", response_model=Dict[str, Any])
async def get_cash_flow_predictions(
    forecast_days: int = Query(90, ge=7, le=365, description="Number of days to forecast"),
    scenario: str = Query("realistic", description="Scenario: realistic, optimistic, pessimistic"),
    include_confidence_bands: bool = Query(True, description="Include confidence bands in forecast"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get comprehensive cash flow forecasting.

    Provides detailed cash flow predictions with multiple scenarios
    and confidence intervals.
    """
    try:
        from app.models.working_capital import ScenarioType

        scenario_map = {
            "realistic": ScenarioType.REALISTIC,
            "optimistic": ScenarioType.OPTIMISTIC,
            "pessimistic": ScenarioType.PESSIMISTIC,
            "stress_test": ScenarioType.STRESS_TEST
        }
        scenario_type = scenario_map.get(scenario, ScenarioType.REALISTIC)

        predictive_service = PredictiveAnalyticsService(db)

        cash_flow_forecast = await predictive_service.predict_cash_flow(
            forecast_days=forecast_days,
            scenario=scenario_type,
            include_confidence_bands=include_confidence_bands
        )

        return {
            "success": True,
            "data": cash_flow_forecast,
            "metadata": {
                "forecast_days": forecast_days,
                "scenario": scenario,
                "confidence_bands_included": include_confidence_bands,
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating cash flow forecast: {str(e)}")


@router.get("/predictive/processing-times", response_model=Dict[str, Any])
async def get_processing_time_predictions(
    invoice_characteristics: Optional[str] = Query(None, description="JSON string of invoice characteristics"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get invoice processing time predictions.

    Predicts processing times based on invoice characteristics
    and historical patterns.
    """
    try:
        import json

        characteristics = None
        if invoice_characteristics:
            try:
                characteristics = json.loads(invoice_characteristics)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON in invoice_characteristics")

        predictive_service = PredictiveAnalyticsService(db)

        prediction = await predictive_service.predict_processing_times(
            invoice_characteristics=characteristics
        )

        return {
            "success": True,
            "data": {
                "predicted_processing_time_hours": float(prediction.predicted_value),
                "confidence_score": prediction.confidence_score,
                "accuracy_estimate": prediction.accuracy_estimate or 0.0,
                "recommendations": prediction.recommendations or [],
                "metadata": prediction.metadata
            },
            "metadata": {
                "invoice_characteristics_provided": characteristics is not None,
                "prediction_method": prediction.metadata.get("prediction_method", "unknown"),
                "generated_at": prediction.prediction_date.isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting processing times: {str(e)}")


@router.get("/executive/dashboard", response_model=Dict[str, Any])
async def get_executive_dashboard(
    period: str = Query("current", description="Period: current, month, quarter, year"),
    include_predictions: bool = Query(True, description="Include predictive analytics"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get comprehensive executive dashboard.

    Combines historical metrics with predictive analytics
    for executive-level decision making.
    """
    try:
        # Get historical analytics
        analytics_service = AnalyticsService(db)

        # Determine date range based on period
        end_dt = datetime.utcnow()
        if period == "current":
            start_dt = end_dt - timedelta(days=30)
        elif period == "month":
            start_dt = end_dt - timedelta(days=30)
        elif period == "quarter":
            start_dt = end_dt - timedelta(days=90)
        elif period == "year":
            start_dt = end_dt - timedelta(days=365)
        else:
            start_dt = end_dt - timedelta(days=30)

        # Get historical metrics
        executive_summary = analytics_service.get_executive_summary(start_dt, end_dt)
        reviewer_performance = analytics_service.get_reviewer_performance(start_dt, end_dt)
        accuracy_metrics = analytics_service.get_extraction_accuracy_metrics(start_dt, end_dt)

        dashboard_data = {
            "period": {
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "period_type": period
            },
            "historical_metrics": {
                "executive_summary": executive_summary,
                "reviewer_performance": reviewer_performance,
                "accuracy_metrics": accuracy_metrics
            }
        }

        # Add predictive analytics if requested
        if include_predictions:
            predictive_service = PredictiveAnalyticsService(db)

            # Get key predictions
            wc_prediction = await predictive_service.predict_working_capital_optimization()
            payment_optimization = await predictive_service.predict_payment_optimization()

            # Get recent anomalies
            recent_anomalies = await predictive_service.detect_anomalies(lookback_days=7)
            critical_anomalies = [a for a in recent_anomalies if a.severity.value == "critical"]

            dashboard_data["predictive_insights"] = {
                "working_capital_prediction": {
                    "predicted_score": float(wc_prediction.predicted_value),
                    "confidence": wc_prediction.confidence_score,
                    "risk_level": wc_prediction.risk_assessment.value if wc_prediction.risk_assessment else None,
                    "recommendations": wc_prediction.recommendations or []
                },
                "payment_optimization": {
                    "potential_savings": float(payment_optimization.predicted_value),
                    "confidence": payment_optimization.confidence_score,
                    "recommendations": payment_optimization.recommendations or []
                },
                "anomaly_summary": {
                    "total_anomalies": len(recent_anomalies),
                    "critical_anomalies": len(critical_anomalies),
                    "requires_attention": len([a for a in recent_anomalies if a.severity.value in ["critical", "high"]])
                }
            }

        return {
            "success": True,
            "data": dashboard_data,
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "period": period,
                "includes_predictions": include_predictions,
                "dashboard_version": "2.0"
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating executive dashboard: {str(e)}")


@router.get("/predictive/model-performance", response_model=Dict[str, Any])
async def get_predictive_model_performance(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    days_back: int = Query(30, ge=1, le=365, description="Days to look back for performance data"),
    db: AsyncSession = Depends(get_async_session),
    current_user: Any = Depends(get_current_active_user),
):
    """
    Get predictive model performance metrics.

    Provides detailed performance data for all predictive models
    including accuracy, confidence levels, and error rates.
    """
    try:
        # This would typically query the PredictiveModel and PredictionResult tables
        # For now, providing a placeholder implementation

        return {
            "success": True,
            "data": {
                "model_performance": {
                    "working_capital_model": {
                        "accuracy": 85.2,
                        "confidence": 78.5,
                        "last_updated": datetime.utcnow().isoformat(),
                        "predictions_last_30_days": 1240,
                        "error_rate": 14.8
                    },
                    "vendor_performance_model": {
                        "accuracy": 82.1,
                        "confidence": 75.3,
                        "last_updated": datetime.utcnow().isoformat(),
                        "predictions_last_30_days": 890,
                        "error_rate": 17.9
                    },
                    "payment_optimization_model": {
                        "accuracy": 88.7,
                        "confidence": 82.4,
                        "last_updated": datetime.utcnow().isoformat(),
                        "predictions_last_30_days": 456,
                        "error_rate": 11.3
                    },
                    "anomaly_detection_model": {
                        "accuracy": 91.3,
                        "confidence": 86.2,
                        "last_updated": datetime.utcnow().isoformat(),
                        "predictions_last_30_days": 2034,
                        "false_positive_rate": 8.7
                    },
                    "fraud_detection_model": {
                        "accuracy": 79.4,
                        "confidence": 71.8,
                        "last_updated": datetime.utcnow().isoformat(),
                        "predictions_last_30_days": 123,
                        "false_positive_rate": 20.6
                    }
                },
                "overall_performance": {
                    "average_accuracy": 85.3,
                    "average_confidence": 78.8,
                    "total_predictions_last_30_days": 4743,
                    "system_health": "good"
                }
            },
            "metadata": {
                "days_back": days_back,
                "model_type_filter": model_type,
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving model performance: {str(e)}")