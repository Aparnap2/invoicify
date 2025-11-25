"""
Analytics models for predictive analytics and business intelligence.

This module extends the existing analytics infrastructure with models for:
- Predictive analytics results storage
- Anomaly detection tracking
- Fraud detection evidence
- Performance prediction models
- Business intelligence insights
- Executive reporting metrics
"""

import enum
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    Integer,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.db.base import TimestampMixin, UUIDMixin
from app.db.session import Base


class PredictionCategory(str, enum.Enum):
    """Categories of predictive analytics."""

    WORKING_CAPITAL = "working_capital"
    VENDOR_PERFORMANCE = "vendor_performance"
    PAYMENT_OPTIMIZATION = "payment_optimization"
    FRAUD_DETECTION = "fraud_detection"
    ANOMALY_DETECTION = "anomaly_detection"
    CASH_FLOW = "cash_flow"
    PROCESSING_EFFICIENCY = "processing_efficiency"
    RISK_ASSESSMENT = "risk_assessment"
    BUSINESS_INTELLIGENCE = "business_intelligence"


class AnomalySeverity(str, enum.Enum):
    """Severity levels for detected anomalies."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ModelAccuracy(str, enum.Enum):
    """Accuracy classification for prediction models."""

    EXCELLENT = "excellent"      # 90%+
    GOOD = "good"               # 75-89%
    FAIR = "fair"               # 60-74%
    POOR = "poor"               # <60%
    INSUFFICIENT_DATA = "insufficient_data"


class BusinessImpact(str, enum.Enum):
    """Business impact assessment levels."""

    MINIMAL = "minimal"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"
    CRITICAL = "critical"
    STRATEGIC = "strategic"


class PredictionExecution(Base, UUIDMixin, TimestampMixin):
    """Execution record for predictive analytics runs."""

    __tablename__ = "prediction_executions"

    # Execution metadata
    execution_id = Column(String(100), nullable=False, unique=True, index=True)
    prediction_category = Column(Enum(PredictionCategory), nullable=False, index=True)
    model_version = Column(String(20), nullable=False)
    execution_status = Column(String(20), nullable=False, default="running", index=True)

    # Execution parameters
    parameters = Column(JSON, nullable=True)
    lookback_period_days = Column(Integer, nullable=False)
    prediction_horizon_days = Column(Integer, nullable=False)

    # Execution results
    total_predictions = Column(Integer, nullable=False, default=0)
    successful_predictions = Column(Integer, nullable=False, default=0)
    failed_predictions = Column(Integer, nullable=False, default=0)

    # Performance metrics
    execution_time_seconds = Column(Integer, nullable=True)
    data_quality_score = Column(Numeric(5, 2), nullable=True)
    model_accuracy = Column(Enum(ModelAccuracy), nullable=True)

    # Resource usage
    memory_usage_mb = Column(Integer, nullable=True)
    cpu_usage_percent = Column(Numeric(5, 2), nullable=True)
    data_points_processed = Column(Integer, nullable=False, default=0)

    # Error handling
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)

    # Performance indexes
    __table_args__ = (
        Index('idx_prediction_execution_category', 'prediction_category', 'created_at'),
        Index('idx_prediction_execution_status', 'execution_status', 'created_at'),
        Index('idx_prediction_execution_model', 'model_version', 'prediction_category'),
        CheckConstraint("lookback_period_days > 0", name='check_lookback_period_positive'),
        CheckConstraint("prediction_horizon_days > 0", name='check_prediction_horizon_positive'),
        CheckConstraint("total_predictions >= 0", name='check_total_predictions_non_negative'),
        CheckConstraint("successful_predictions >= 0 AND successful_predictions <= total_predictions", name='check_successful_predictions_range'),
        CheckConstraint("failed_predictions >= 0 AND failed_predictions <= total_predictions", name='check_failed_predictions_range'),
        CheckConstraint("execution_time_seconds >= 0", name='check_execution_time_non_negative'),
        CheckConstraint("memory_usage_mb >= 0", name='check_memory_usage_non_negative'),
        CheckConstraint("cpu_usage_percent >= 0 AND cpu_usage_percent <= 100", name='check_cpu_usage_range'),
        CheckConstraint("data_points_processed >= 0", name='check_data_points_non_negative'),
    )

    def __repr__(self):
        return f"<PredictionExecution(id={self.execution_id}, category={self.prediction_category}, status={self.execution_status})>"

    def calculate_success_rate(self) -> float:
        """Calculate prediction success rate."""
        if self.total_predictions == 0:
            return 0.0
        return (self.successful_predictions / self.total_predictions) * 100

    def calculate_performance_score(self) -> float:
        """Calculate overall performance score."""
        # Weight factors for different metrics
        success_rate_weight = 0.4
        accuracy_weight = 0.3
        speed_weight = 0.2
        quality_weight = 0.1

        # Normalize each metric to 0-100 scale
        success_rate_score = self.calculate_success_rate()

        accuracy_score = 0
        if self.model_accuracy == ModelAccuracy.EXCELLENT:
            accuracy_score = 95
        elif self.model_accuracy == ModelAccuracy.GOOD:
            accuracy_score = 80
        elif self.model_accuracy == ModelAccuracy.FAIR:
            accuracy_score = 65
        elif self.model_accuracy == ModelAccuracy.POOR:
            accuracy_score = 40
        elif self.model_accuracy == ModelAccuracy.INSUFFICIENT_DATA:
            accuracy_score = 20

        # Speed score (inverse of execution time, normalized)
        speed_score = max(0, min(100, 100 - (self.execution_time_seconds or 0) / 10))

        # Quality score from data quality
        quality_score = float(self.data_quality_score or 0)

        # Calculate weighted average
        performance_score = (
            success_rate_score * success_rate_weight +
            accuracy_score * accuracy_weight +
            speed_score * speed_weight +
            quality_score * quality_weight
        )

        return performance_score


class PredictionResult(Base, UUIDMixin, TimestampMixin):
    """Individual prediction result storage."""

    __tablename__ = "prediction_results"

    # Related execution
    execution_id = Column(UUID(as_uuid=True), ForeignKey("prediction_executions.id"), nullable=False, index=True)

    # Prediction details
    prediction_type = Column(String(50), nullable=False, index=True)
    target_entity_type = Column(String(50), nullable=True)  # vendor, invoice, customer, etc.
    target_entity_id = Column(UUID(as_uuid=True), nullable=True)
    target_period_start = Column(DateTime(timezone=True), nullable=True)
    target_period_end = Column(DateTime(timezone=True), nullable=True)

    # Prediction values
    predicted_value = Column(Numeric(15, 4), nullable=False)
    predicted_unit = Column(String(20), nullable=True)  # percentage, days, dollars, etc.
    confidence_score = Column(Numeric(5, 2), nullable=False)  # 0-100
    accuracy_estimate = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Prediction ranges (for probabilistic predictions)
    predicted_value_min = Column(Numeric(15, 4), nullable=True)
    predicted_value_max = Column(Numeric(15, 4), nullable=True)
    prediction_interval = Column(Numeric(5, 2), nullable=True)  # Confidence interval percentage

    # Model information
    model_algorithm = Column(String(50), nullable=True)
    model_features = Column(JSON, nullable=True)  # Features used for prediction
    feature_importance = Column(JSON, nullable=True)  # Feature importance scores

    # Validation and tracking
    actual_value = Column(Numeric(15, 4), nullable=True)  # For post-prediction validation
    prediction_accuracy = Column(Numeric(5, 2), nullable=True)  # Calculated after actual known
    validation_status = Column(String(20), nullable=False, default="pending")  # pending, validated, expired

    # Business impact
    business_impact = Column(Enum(BusinessImpact), nullable=True)
    financial_impact_estimate = Column(Numeric(15, 2), nullable=True)
    recommended_actions = Column(ARRAY(String), nullable=True)

    # Additional metadata
    prediction_metadata = Column(JSON, nullable=True)
    external_factors = Column(JSON, nullable=True)  # External factors considered

    # Performance indexes
    __table_args__ = (
        Index('idx_prediction_result_execution', 'execution_id', 'prediction_type'),
        Index('idx_prediction_result_entity', 'target_entity_type', 'target_entity_id'),
        Index('idx_prediction_result_confidence', 'confidence_score', 'created_at'),
        Index('idx_prediction_result_period', 'target_period_start', 'target_period_end'),
        Index('idx_prediction_result_validation', 'validation_status', 'created_at'),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name='check_confidence_score_range'),
        CheckConstraint("accuracy_estimate >= 0 AND accuracy_estimate <= 100", name='check_accuracy_estimate_range'),
        CheckConstraint("prediction_interval >= 0 AND prediction_interval <= 100", name='check_prediction_interval_range'),
        CheckConstraint("prediction_accuracy >= 0 AND prediction_accuracy <= 100", name='check_prediction_accuracy_range'),
    )

    # Relationships
    execution = relationship("PredictionExecution", backref="prediction_results")

    def __repr__(self):
        return f"<PredictionResult(type={self.prediction_type}, value={self.predicted_value}, confidence={self.confidence_score}%)>"

    def calculate_prediction_error(self) -> Optional[float]:
        """Calculate prediction error percentage when actual value is known."""
        if self.actual_value is None or self.predicted_value == 0:
            return None

        error_percentage = abs((self.actual_value - self.predicted_value) / self.predicted_value) * 100
        return float(error_percentage)

    def is_high_confidence(self, threshold: float = 80.0) -> bool:
        """Check if prediction has high confidence."""
        return self.confidence_score >= threshold

    def validate_prediction(self, actual_value: Decimal, actual_unit: str = None) -> bool:
        """Validate prediction against actual value."""
        if actual_unit and actual_unit != self.predicted_unit:
            # Unit mismatch - conversion needed
            return False

        self.actual_value = actual_value
        error = self.calculate_prediction_error()

        if error is not None:
            # Map error to accuracy (inverse relationship)
            self.prediction_accuracy = max(0, 100 - error)
            self.validation_status = "validated"

            # Determine if prediction was successful
            return error <= 20.0  # 20% error threshold
        else:
            self.validation_status = "invalid"
            return False


class AnomalyDetection(Base, UUIDMixin, TimestampMixin):
    """Anomaly detection results and tracking."""

    __tablename__ = "anomaly_detections"

    # Anomaly identification
    anomaly_type = Column(String(50), nullable=False, index=True)
    severity = Column(Enum(AnomalySeverity), nullable=False, index=True)
    anomaly_score = Column(Numeric(5, 2), nullable=False)  # 0-100 anomaly score
    confidence_level = Column(Numeric(5, 2), nullable=False)  # 0-100 confidence

    # Anomaly details
    description = Column(Text, nullable=False)
    anomaly_pattern = Column(JSON, nullable=True)  # Detailed pattern description
    affected_metrics = Column(ARRAY(String), nullable=True)  # Metrics affected

    # Scope and impact
    affected_entity_type = Column(String(50), nullable=True)  # vendor, customer, system, etc.
    affected_entity_id = Column(UUID(as_uuid=True), nullable=True)
    affected_time_period_start = Column(DateTime(timezone=True), nullable=True)
    affected_time_period_end = Column(DateTime(timezone=True), nullable=True)

    # Detection context
    detection_algorithm = Column(String(50), nullable=True)
    detection_parameters = Column(JSON, nullable=True)
    baseline_period = Column(String(20), nullable=True)  # e.g., "30_days", "previous_quarter"
    statistical_significance = Column(Numeric(5, 2), nullable=True)

    # Business impact
    business_impact = Column(Enum(BusinessImpact), nullable=True)
    financial_impact_estimate = Column(Numeric(15, 2), nullable=True)
    operational_impact = Column(Text, nullable=True)

    # Resolution tracking
    status = Column(String(20), nullable=False, default="active", index=True)  # active, investigating, resolved, false_positive
    investigation_priority = Column(Integer, nullable=False, default=3)  # 1-5 priority
    assigned_to = Column(String(100), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Additional context
    historical_context = Column(JSON, nullable=True)
    related_anomalies = Column(ARRAY(UUID), nullable=True)  # Related anomaly IDs
    external_factors = Column(JSON, nullable=True)

    # Performance indexes
    __table_args__ = (
        Index('idx_anomaly_detection_type_severity', 'anomaly_type', 'severity'),
        Index('idx_anomaly_detection_score', 'anomaly_score', 'created_at'),
        Index('idx_anomaly_detection_status', 'status', 'created_at'),
        Index('idx_anomaly_detection_entity', 'affected_entity_type', 'affected_entity_id'),
        Index('idx_anomaly_detection_priority', 'investigation_priority', 'created_at'),
        CheckConstraint("anomaly_score >= 0 AND anomaly_score <= 100", name='check_anomaly_score_range'),
        CheckConstraint("confidence_level >= 0 AND confidence_level <= 100", name='check_confidence_level_range'),
        CheckConstraint("statistical_significance >= 0 AND statistical_significance <= 100", name='check_statistical_significance_range'),
        CheckConstraint("investigation_priority >= 1 AND investigation_priority <= 5", name='check_priority_range'),
    )

    def __repr__(self):
        return f"<AnomalyDetection(type={self.anomaly_type}, severity={self.severity}, score={self.anomaly_score})>"

    def is_critical(self) -> bool:
        """Check if anomaly is critical."""
        return self.severity == AnomalySeverity.CRITICAL

    def requires_immediate_attention(self) -> bool:
        """Check if anomaly requires immediate attention."""
        return (
            self.is_critical() or
            self.investigation_priority <= 2 or
            self.business_impact in [BusinessImpact.CRITICAL, BusinessImpact.STRATEGIC]
        )

    def calculate_risk_score(self) -> float:
        """Calculate overall risk score."""
        severity_weight = 0.4
        impact_weight = 0.3
        priority_weight = 0.2
        confidence_weight = 0.1

        # Normalize severity to 0-100
        severity_score = {
            AnomalySeverity.LOW: 25,
            AnomalySeverity.MEDIUM: 50,
            AnomalySeverity.HIGH: 75,
            AnomalySeverity.CRITICAL: 100
        }[self.severity]

        # Normalize business impact to 0-100
        impact_score = {
            BusinessImpact.MINIMAL: 20,
            BusinessImpact.MODERATE: 40,
            BusinessImpact.SIGNIFICANT: 70,
            BusinessImpact.CRITICAL: 90,
            BusinessImpact.STRATEGIC: 100
        }.get(self.business_impact, 50)

        # Normalize priority (inverse - lower priority number = higher urgency)
        priority_score = (6 - self.investigation_priority) * 20

        # Calculate weighted risk score
        risk_score = (
            severity_score * severity_weight +
            impact_score * impact_weight +
            priority_score * priority_weight +
            float(self.confidence_level) * confidence_weight
        )

        return risk_score


class FraudDetectionResult(Base, UUIDMixin, TimestampMixin):
    """Fraud detection results and evidence tracking."""

    __tablename__ = "fraud_detection_results"

    # Detection identification
    fraud_pattern = Column(String(50), nullable=False, index=True)
    risk_level = Column(String(20), nullable=False, index=True)
    confidence_score = Column(Numeric(5, 2), nullable=False)  # 0-100
    detection_method = Column(String(50), nullable=False)

    # Pattern details
    pattern_description = Column(Text, nullable=False)
    indicators = Column(JSON, nullable=True)  # List of fraud indicators
    pattern_complexity = Column(String(20), nullable=True)  # simple, moderate, complex

    # Suspected entities
    suspected_entity_type = Column(String(50), nullable=True)  # vendor, invoice, employee
    suspected_entity_id = Column(UUID(as_uuid=True), nullable=True)
    related_entities = Column(JSON, nullable=True)  # Related entities information

    # Financial impact
    estimated_loss = Column(Numeric(15, 2), nullable=True)
    estimated_frequency = Column(Integer, nullable=True)  # Estimated occurrences
    financial_exposure = Column(Numeric(15, 2), nullable=True)

    # Investigation tracking
    investigation_status = Column(String(20), nullable=False, default="pending", index=True)
    investigation_priority = Column(Integer, nullable=False, default=3)
    assigned_investigator = Column(String(100), nullable=True)
    investigation_notes = Column(Text, nullable=True)
    evidence_collected = Column(JSON, nullable=True)

    # Resolution
    resolution_status = Column(String(20), nullable=True)  # confirmed_fraud, false_positive, inconclusive
    confirmed_amount = Column(Numeric(15, 2), nullable=True)
    recovery_amount = Column(Numeric(15, 2), nullable=True)
    resolution_date = Column(DateTime(timezone=True), nullable=True)

    # Prevention measures
    prevention_actions = Column(ARRAY(String), nullable=True)
    monitoring_required = Column(Boolean, nullable=False, default=True)
    monitoring_period_days = Column(Integer, nullable=True)

    # Additional context
    detection_context = Column(JSON, nullable=True)
    historical_patterns = Column(JSON, nullable=True)
    external_references = Column(JSON, nullable=True)

    # Performance indexes
    __table_args__ = (
        Index('idx_fraud_detection_pattern_risk', 'fraud_pattern', 'risk_level'),
        Index('idx_fraud_detection_confidence', 'confidence_score', 'created_at'),
        Index('idx_fraud_detection_status', 'investigation_status', 'created_at'),
        Index('idx_fraud_detection_entity', 'suspected_entity_type', 'suspected_entity_id'),
        Index('idx_fraud_detection_priority', 'investigation_priority', 'created_at'),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name='check_fraud_confidence_range'),
        CheckConstraint("investigation_priority >= 1 AND investigation_priority <= 5", name='check_fraud_priority_range'),
        CheckConstraint("estimated_frequency >= 0", name='check_estimated_frequency_positive'),
        CheckConstraint("monitoring_period_days >= 0", name='check_monitoring_period_positive'),
    )

    def __repr__(self):
        return f"<FraudDetectionResult(pattern={self.fraud_pattern}, risk_level={self.risk_level}, confidence={self.confidence_score}%)>"

    def is_high_risk(self, threshold: float = 75.0) -> bool:
        """Check if fraud detection is high risk."""
        return self.confidence_score >= threshold or self.risk_level in ["high", "critical"]

    def requires_investigation(self) -> bool:
        """Check if fraud detection requires investigation."""
        return (
            self.is_high_risk() or
            self.investigation_priority <= 2 or
            self.estimated_loss and self.estimated_loss > 10000
        )

    def calculate_prevention_priority(self) -> int:
        """Calculate prevention priority score."""
        factors = [
            self.confidence_score * 0.3,
            (self.estimated_loss or 0) / 1000 * 0.4,  # Scale loss to 0-100 range
            (6 - self.investigation_priority) * 10 * 0.2,
            20 if self.monitoring_required else 0
        ]
        return min(100, sum(factors))


class ExecutiveDashboardMetrics(Base, UUIDMixin, TimestampMixin):
    """Executive dashboard metrics and KPIs."""

    __tablename__ = "executive_dashboard_metrics"

    # Metric identification
    metric_name = Column(String(100), nullable=False, index=True)
    metric_category = Column(String(50), nullable=False, index=True)
    dashboard_section = Column(String(50), nullable=False)  # overview, financial, operational, risk

    # Time period
    metric_date = Column(DateTime(timezone=True), nullable=False, index=True)
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly, quarterly
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Metric values
    current_value = Column(Numeric(15, 4), nullable=False)
    previous_value = Column(Numeric(15, 4), nullable=True)
    target_value = Column(Numeric(15, 4), nullable=True)
    benchmark_value = Column(Numeric(15, 4), nullable=True)

    # Performance calculations
    variance_from_target = Column(Numeric(5, 2), nullable=True)  # Percentage
    variance_from_benchmark = Column(Numeric(5, 2), nullable=True)  # Percentage
    trend_direction = Column(String(10), nullable=True)  # up, down, stable
    trend_percentage = Column(Numeric(5, 2), nullable=True)

    # KPI classification
    is_kpi = Column(Boolean, nullable=False, default=False)
    kpi_weight = Column(Numeric(3, 2), nullable=True)  # Weight in overall KPI calculation
    performance_rating = Column(String(20), nullable=True)  # excellent, good, average, poor

    # Visualization data
    chart_data = Column(JSON, nullable=True)  # Data for charts
    trend_data = Column(JSON, nullable=True)  # Historical trend data
    comparison_data = Column(JSON, nullable=True)  # Comparison data

    # Business context
    business_impact = Column(Enum(BusinessImpact), nullable=True)
    stakeholder_interest = Column(ARRAY(String), nullable=True)  # Interested stakeholders
    action_required = Column(Boolean, nullable=False, default=False)
    recommended_actions = Column(ARRAY(String), nullable=True)

    # Data quality
    data_quality_score = Column(Numeric(5, 2), nullable=True)
    data_source = Column(String(50), nullable=True)
    last_updated = Column(DateTime(timezone=True), nullable=False)
    confidence_level = Column(Numeric(5, 2), nullable=True)

    # Performance indexes
    __table_args__ = (
        Index('idx_executive_metric_name_date', 'metric_name', 'metric_date'),
        Index('idx_executive_metric_category', 'metric_category', 'dashboard_section'),
        Index('idx_executive_metric_kpi', 'is_kpi', 'metric_date'),
        Index('idx_executive_metric_performance', 'performance_rating', 'metric_date'),
        Index('idx_executive_metric_action', 'action_required', 'metric_date'),
        CheckConstraint("kpi_weight >= 0 AND kpi_weight <= 1", name='check_kpi_weight_range'),
        CheckConstraint("variance_from_target >= -100 AND variance_from_target <= 100", name='check_target_variance_range'),
        CheckConstraint("variance_from_benchmark >= -100 AND variance_from_benchmark <= 100", name='check_benchmark_variance_range'),
        CheckConstraint("trend_percentage >= -100 AND trend_percentage <= 100", name='check_trend_percentage_range'),
        CheckConstraint("data_quality_score >= 0 AND data_quality_score <= 100", name='check_executive_data_quality_range'),
        CheckConstraint("confidence_level >= 0 AND confidence_level <= 100", name='check_confidence_level_range'),
    )

    def __repr__(self):
        return f"<ExecutiveDashboardMetrics(name={self.metric_name}, value={self.current_value}, category={self.metric_category})>"

    def calculate_performance_score(self) -> float:
        """Calculate overall performance score for this metric."""
        if not self.target_value:
            return 50.0  # Neutral score if no target

        try:
            target = float(self.target_value)
            current = float(self.current_value)

            if target == 0:
                return 50.0

            # Calculate performance as percentage of target
            performance = (current / target) * 100

            # Cap at 200% to handle overperformance
            return min(200.0, max(0.0, performance))
        except (ValueError, TypeError):
            return 50.0

    def is_performing_well(self, threshold: float = 90.0) -> bool:
        """Check if metric is performing well."""
        return self.calculate_performance_score() >= threshold

    def needs_attention(self) -> bool:
        """Check if metric needs attention."""
        return (
            self.action_required or
            self.performance_rating in ["poor", "average"] or
            (self.variance_from_target and abs(self.variance_from_target) > 20)
        )


class PredictiveModel(Base, UUIDMixin, TimestampMixin):
    """Predictive model definitions and performance tracking."""

    __tablename__ = "predictive_models"

    # Model identification
    model_name = Column(String(100), nullable=False, unique=True, index=True)
    model_type = Column(String(50), nullable=False)  # regression, classification, clustering, etc.
    prediction_category = Column(Enum(PredictionCategory), nullable=False, index=True)
    algorithm = Column(String(50), nullable=False)

    # Model description
    description = Column(Text, nullable=False)
    business_use_case = Column(Text, nullable=True)
    target_variable = Column(String(100), nullable=False)
    input_features = Column(ARRAY(String), nullable=True)

    # Training data
    training_data_period_start = Column(DateTime(timezone=True), nullable=True)
    training_data_period_end = Column(DateTime(timezone=True), nullable=True)
    training_data_points = Column(Integer, nullable=False, default=0)
    feature_engineering = Column(JSON, nullable=True)

    # Model performance
    accuracy_score = Column(Numeric(5, 2), nullable=True)  # 0-100
    precision_score = Column(Numeric(5, 2), nullable=True)
    recall_score = Column(Numeric(5, 2), nullable=True)
    f1_score = Column(Numeric(5, 2), nullable=True)
    mse = Column(Numeric(10, 4), nullable=True)  # Mean squared error
    rmse = Column(Numeric(10, 4), nullable=True)  # Root mean squared error
    mae = Column(Numeric(10, 4), nullable=True)  # Mean absolute error

    # Model status and lifecycle
    status = Column(String(20), nullable=False, default="training")  # training, active, deprecated, retired
    version = Column(String(20), nullable=False)
    is_production = Column(Boolean, nullable=False, default=False)
    last_trained = Column(DateTime(timezone=True), nullable=True)
    next_retrain_date = Column(DateTime(timezone=True), nullable=True)

    # Model parameters and hyperparameters
    hyperparameters = Column(JSON, nullable=True)
    model_parameters = Column(JSON, nullable=True)
    feature_importance = Column(JSON, nullable=True)

    # Validation and testing
    validation_method = Column(String(50), nullable=True)  # cross_validation, holdout, etc.
    validation_results = Column(JSON, nullable=True)
    test_results = Column(JSON, nullable=True)

    # Deployment information
    deployment_environment = Column(String(20), nullable=True)  # development, staging, production
    endpoint_url = Column(String(255), nullable=True)
    api_version = Column(String(10), nullable=True)

    # Monitoring and maintenance
    monitoring_enabled = Column(Boolean, nullable=False, default=True)
    drift_detection_enabled = Column(Boolean, nullable=False, default=True)
    last_performance_check = Column(DateTime(timezone=True), nullable=True)
    performance_degradation_threshold = Column(Numeric(5, 2), nullable=True)

    # Governance and compliance
    model_owner = Column(String(100), nullable=True)
    data_sensitivity = Column(String(20), nullable=True)  # public, internal, confidential, restricted
    compliance_requirements = Column(ARRAY(String), nullable=True)
    audit_trail = Column(JSON, nullable=True)

    # Performance indexes
    __table_args__ = (
        Index('idx_predictive_model_category', 'prediction_category', 'status'),
        Index('idx_predictive_model_type', 'model_type', 'algorithm'),
        Index('idx_predictive_model_status', 'status', 'is_production'),
        Index('idx_predictive_model_performance', 'accuracy_score', 'f1_score'),
        Index('idx_predictive_model_owner', 'model_owner', 'status'),
        CheckConstraint("accuracy_score >= 0 AND accuracy_score <= 100", name='check_accuracy_score_range'),
        CheckConstraint("precision_score >= 0 AND precision_score <= 100", name='check_precision_score_range'),
        CheckConstraint("recall_score >= 0 AND recall_score <= 100", name='check_recall_score_range'),
        CheckConstraint("f1_score >= 0 AND f1_score <= 100", name='check_f1_score_range'),
        CheckConstraint("training_data_points >= 0", name='check_training_data_points_non_negative'),
        CheckConstraint("performance_degradation_threshold >= 0 AND performance_degradation_threshold <= 100", name='check_performance_degradation_range'),
    )

    def __repr__(self):
        return f"<PredictiveModel(name={self.model_name}, type={self.model_type}, status={self.status})>"

    def is_production_ready(self) -> bool:
        """Check if model is ready for production."""
        return (
            self.status == "active" and
            self.is_production and
            self.accuracy_score and self.accuracy_score >= 75.0 and
            self.training_data_points >= 100
        )

    def needs_retraining(self) -> bool:
        """Check if model needs retraining."""
        if not self.next_retrain_date:
            return False
        return datetime.utcnow() >= self.next_retrain_date

    def calculate_overall_score(self) -> float:
        """Calculate overall model performance score."""
        if not self.accuracy_score:
            return 0.0

        # Weight different performance metrics
        accuracy_weight = 0.4
        f1_weight = 0.3
        precision_weight = 0.15
        recall_weight = 0.15

        # Convert all scores to float
        accuracy = float(self.accuracy_score)
        f1 = float(self.f1_score) if self.f1_score else 0.0
        precision = float(self.precision_score) if self.precision_score else 0.0
        recall = float(self.recall_score) if self.recall_score else 0.0

        # Calculate weighted average
        overall_score = (
            accuracy * accuracy_weight +
            f1 * f1_weight +
            precision * precision_weight +
            recall * recall_weight
        )

        return overall_score


class BusinessInsight(Base, UUIDMixin, TimestampMixin):
    """Business insights generated from analytics."""

    __tablename__ = "business_insights"

    # Insight identification
    insight_type = Column(String(50), nullable=False, index=True)
    insight_category = Column(String(50), nullable=False, index=True)
    confidence_level = Column(Numeric(5, 2), nullable=False)  # 0-100
    impact_level = Column(Enum(BusinessImpact), nullable=False)

    # Insight content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    key_findings = Column(ARRAY(String), nullable=True)
    supporting_data = Column(JSON, nullable=True)
    visualization_data = Column(JSON, nullable=True)

    # Analysis context
    analysis_period_start = Column(DateTime(timezone=True), nullable=False)
    analysis_period_end = Column(DateTime(timezone=True), nullable=False)
    data_sources = Column(ARRAY(String), nullable=True)
    analysis_methods = Column(ARRAY(String), nullable=True)

    # Business relevance
    stakeholder_audience = Column(ARRAY(String), nullable=True)
    business_objectives = Column(ARRAY(String), nullable=True)
    strategic_alignment = Column(Text, nullable=True)

    # Recommendations
    recommended_actions = Column(ARRAY(String), nullable=True)
    action_priority = Column(String(20), nullable=True)  # high, medium, low
    implementation_timeline = Column(String(50), nullable=True)
    resource_requirements = Column(JSON, nullable=True)

    # Expected outcomes
    expected_benefits = Column(JSON, nullable=True)
    success_metrics = Column(ARRAY(String), nullable=True)
    roi_estimate = Column(Numeric(5, 2), nullable=True)

    # Tracking and follow-up
    status = Column(String(20), nullable=False, default="new", index=True)
    assigned_to = Column(String(100), nullable=True)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    implementation_status = Column(String(20), nullable=True)
    outcomes_measured = Column(Boolean, nullable=False, default=False)

    # Additional context
    related_insights = Column(ARRAY(UUID), nullable=True)
    external_references = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    # Performance indexes
    __table_args__ = (
        Index('idx_business_insight_type_category', 'insight_type', 'insight_category'),
        Index('idx_business_insight_impact', 'impact_level', 'created_at'),
        Index('idx_business_insight_status', 'status', 'follow_up_date'),
        Index('idx_business_insight_audience', 'stakeholder_audience', 'created_at'),
        Index('idx_business_insight_priority', 'action_priority', 'impact_level'),
        CheckConstraint("confidence_level >= 0 AND confidence_level <= 100", name='check_insight_confidence_range'),
        CheckConstraint("roi_estimate >= -100 AND roi_estimate <= 1000", name='check_roi_estimate_range'),
    )

    def __repr__(self):
        return f"<BusinessInsight(type={self.insight_type}, impact={self.impact_level}, confidence={self.confidence_score}%)>"

    def is_high_priority(self) -> bool:
        """Check if insight is high priority."""
        return (
            self.action_priority == "high" or
            self.impact_level in [BusinessImpact.CRITICAL, BusinessImpact.STRATEGIC] or
            (self.confidence_level and self.confidence_level >= 80)
        )

    def requires_action(self) -> bool:
        """Check if insight requires action."""
        return (
            self.recommended_actions is not None and
            len(self.recommended_actions) > 0 and
            self.status not in ["implemented", "rejected"]
        )

    def is_overdue_for_followup(self) -> bool:
        """Check if insight is overdue for follow-up."""
        if not self.follow_up_date:
            return False
        return datetime.utcnow() > self.follow_up_date and self.status not in ["completed", "rejected"]