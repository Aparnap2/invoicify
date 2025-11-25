"""Add predictive analytics models

Revision ID: 003_add_predictive_analytics_models
Revises: 002_normalize_json_fields
Create Date: 2025-11-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_predictive_analytics_models'
down_revision = '002_normalize_json_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add predictive analytics models tables."""

    # Create prediction_executions table
    op.create_table(
        'prediction_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('execution_id', sa.String(length=100), nullable=False),
        sa.Column('prediction_category', sa.Enum('WORKING_CAPITAL', 'VENDOR_PERFORMANCE', 'PAYMENT_OPTIMIZATION', 'FRAUD_DETECTION', 'ANOMALY_DETECTION', 'CASH_FLOW', 'PROCESSING_EFFICIENCY', 'RISK_ASSESSMENT', 'BUSINESS_INTELLIGENCE', name='predictioncategory'), nullable=False),
        sa.Column('model_version', sa.String(length=20), nullable=False),
        sa.Column('execution_status', sa.String(length=20), nullable=False),
        sa.Column('parameters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('lookback_period_days', sa.Integer(), nullable=False),
        sa.Column('prediction_horizon_days', sa.Integer(), nullable=False),
        sa.Column('total_predictions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_predictions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_predictions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('execution_time_seconds', sa.Integer(), nullable=True),
        sa.Column('data_quality_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('model_accuracy', sa.Enum('EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'INSUFFICIENT_DATA', name='modelaccuracy'), nullable=True),
        sa.Column('memory_usage_mb', sa.Integer(), nullable=True),
        sa.Column('cpu_usage_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('data_points_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('execution_id')
    )
    op.create_index('idx_prediction_execution_category', 'prediction_executions', ['prediction_category', 'created_at'], unique=False)
    op.create_index('idx_prediction_execution_status', 'prediction_executions', ['execution_status', 'created_at'], unique=False)
    op.create_index('idx_prediction_execution_model', 'prediction_executions', ['model_version', 'prediction_category'], unique=False)

    # Create prediction_results table
    op.create_table(
        'prediction_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prediction_type', sa.String(length=50), nullable=False),
        sa.Column('target_entity_type', sa.String(length=50), nullable=True),
        sa.Column('target_entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('target_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('target_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('predicted_value', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('predicted_unit', sa.String(length=20), nullable=True),
        sa.Column('confidence_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('accuracy_estimate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('predicted_value_min', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('predicted_value_max', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('prediction_interval', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('model_algorithm', sa.String(length=50), nullable=True),
        sa.Column('model_features', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('feature_importance', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('actual_value', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('prediction_accuracy', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('validation_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('business_impact', sa.Enum('MINIMAL', 'MODERATE', 'SIGNIFICANT', 'CRITICAL', 'STRATEGIC', name='businessimpact'), nullable=True),
        sa.Column('financial_impact_estimate', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('recommended_actions', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('prediction_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('external_factors', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['prediction_executions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_prediction_result_execution', 'prediction_results', ['execution_id', 'prediction_type'], unique=False)
    op.create_index('idx_prediction_result_entity', 'prediction_results', ['target_entity_type', 'target_entity_id'], unique=False)
    op.create_index('idx_prediction_result_confidence', 'prediction_results', ['confidence_score', 'created_at'], unique=False)
    op.create_index('idx_prediction_result_period', 'prediction_results', ['target_period_start', 'target_period_end'], unique=False)
    op.create_index('idx_prediction_result_validation', 'prediction_results', ['validation_status', 'created_at'], unique=False)

    # Create anomaly_detections table
    op.create_table(
        'anomaly_detections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('anomaly_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='anomalyseverity'), nullable=False),
        sa.Column('anomaly_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('confidence_level', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('anomaly_pattern', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('affected_metrics', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('affected_entity_type', sa.String(length=50), nullable=True),
        sa.Column('affected_entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('affected_time_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('affected_time_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('detection_algorithm', sa.String(length=50), nullable=True),
        sa.Column('detection_parameters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('baseline_period', sa.String(length=20), nullable=True),
        sa.Column('statistical_significance', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('business_impact', sa.Enum('MINIMAL', 'MODERATE', 'SIGNIFICANT', 'CRITICAL', 'STRATEGIC', name='businessimpact'), nullable=True),
        sa.Column('financial_impact_estimate', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('operational_impact', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('investigation_priority', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('assigned_to', sa.String(length=100), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('historical_context', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('related_anomalies', postgresql.ARRAY(postgresql.UUID()), nullable=True),
        sa.Column('external_factors', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_anomaly_detection_type_severity', 'anomaly_detections', ['anomaly_type', 'severity'], unique=False)
    op.create_index('idx_anomaly_detection_score', 'anomaly_detections', ['anomaly_score', 'created_at'], unique=False)
    op.create_index('idx_anomaly_detection_status', 'anomaly_detections', ['status', 'created_at'], unique=False)
    op.create_index('idx_anomaly_detection_entity', 'anomaly_detections', ['affected_entity_type', 'affected_entity_id'], unique=False)
    op.create_index('idx_anomaly_detection_priority', 'anomaly_detections', ['investigation_priority', 'created_at'], unique=False)

    # Create fraud_detection_results table
    op.create_table(
        'fraud_detection_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('fraud_pattern', sa.String(length=50), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('confidence_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('detection_method', sa.String(length=50), nullable=False),
        sa.Column('pattern_description', sa.Text(), nullable=False),
        sa.Column('indicators', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('pattern_complexity', sa.String(length=20), nullable=True),
        sa.Column('suspected_entity_type', sa.String(length=50), nullable=True),
        sa.Column('suspected_entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('related_entities', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('estimated_loss', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('estimated_frequency', sa.Integer(), nullable=True),
        sa.Column('financial_exposure', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('investigation_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('investigation_priority', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('assigned_investigator', sa.String(length=100), nullable=True),
        sa.Column('investigation_notes', sa.Text(), nullable=True),
        sa.Column('evidence_collected', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('resolution_status', sa.String(length=20), nullable=True),
        sa.Column('confirmed_amount', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('recovery_amount', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('resolution_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prevention_actions', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('monitoring_required', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('monitoring_period_days', sa.Integer(), nullable=True),
        sa.Column('detection_context', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('historical_patterns', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('external_references', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fraud_detection_pattern_risk', 'fraud_detection_results', ['fraud_pattern', 'risk_level'], unique=False)
    op.create_index('idx_fraud_detection_confidence', 'fraud_detection_results', ['confidence_score', 'created_at'], unique=False)
    op.create_index('idx_fraud_detection_status', 'fraud_detection_results', ['investigation_status', 'created_at'], unique=False)
    op.create_index('idx_fraud_detection_entity', 'fraud_detection_results', ['suspected_entity_type', 'suspected_entity_id'], unique=False)
    op.create_index('idx_fraud_detection_priority', 'fraud_detection_results', ['investigation_priority', 'created_at'], unique=False)

    # Create executive_dashboard_metrics table
    op.create_table(
        'executive_dashboard_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('metric_category', sa.String(length=50), nullable=False),
        sa.Column('dashboard_section', sa.String(length=50), nullable=False),
        sa.Column('metric_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_value', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('previous_value', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('target_value', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('benchmark_value', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('variance_from_target', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('variance_from_benchmark', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('trend_direction', sa.String(length=10), nullable=True),
        sa.Column('trend_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('is_kpi', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('kpi_weight', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('performance_rating', sa.String(length=20), nullable=True),
        sa.Column('chart_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('trend_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('comparison_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('business_impact', sa.Enum('MINIMAL', 'MODERATE', 'SIGNIFICANT', 'CRITICAL', 'STRATEGIC', name='businessimpact'), nullable=True),
        sa.Column('stakeholder_interest', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('action_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('recommended_actions', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('data_quality_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('data_source', sa.String(length=50), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confidence_level', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_executive_metric_name_date', 'executive_dashboard_metrics', ['metric_name', 'metric_date'], unique=False)
    op.create_index('idx_executive_metric_category', 'executive_dashboard_metrics', ['metric_category', 'dashboard_section'], unique=False)
    op.create_index('idx_executive_metric_kpi', 'executive_dashboard_metrics', ['is_kpi', 'metric_date'], unique=False)
    op.create_index('idx_executive_metric_performance', 'executive_dashboard_metrics', ['performance_rating', 'metric_date'], unique=False)
    op.create_index('idx_executive_metric_action', 'executive_dashboard_metrics', ['action_required', 'metric_date'], unique=False)

    # Create predictive_models table
    op.create_table(
        'predictive_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('model_type', sa.String(length=50), nullable=False),
        sa.Column('prediction_category', sa.Enum('WORKING_CAPITAL', 'VENDOR_PERFORMANCE', 'PAYMENT_OPTIMIZATION', 'FRAUD_DETECTION', 'ANOMALY_DETECTION', 'CASH_FLOW', 'PROCESSING_EFFICIENCY', 'RISK_ASSESSMENT', 'BUSINESS_INTELLIGENCE', name='predictioncategory'), nullable=False),
        sa.Column('algorithm', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('business_use_case', sa.Text(), nullable=True),
        sa.Column('target_variable', sa.String(length=100), nullable=False),
        sa.Column('input_features', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('training_data_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('training_data_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('training_data_points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('feature_engineering', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('accuracy_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('precision_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('recall_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('f1_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('mse', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('rmse', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('mae', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='training'),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('is_production', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_trained', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retrain_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hyperparameters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('model_parameters', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('feature_importance', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('validation_method', sa.String(length=50), nullable=True),
        sa.Column('validation_results', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('test_results', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('deployment_environment', sa.String(length=20), nullable=True),
        sa.Column('endpoint_url', sa.String(length=255), nullable=True),
        sa.Column('api_version', sa.String(length=10), nullable=True),
        sa.Column('monitoring_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('drift_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_performance_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('performance_degradation_threshold', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('model_owner', sa.String(length=100), nullable=True),
        sa.Column('data_sensitivity', sa.String(length=20), nullable=True),
        sa.Column('compliance_requirements', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('audit_trail', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_name')
    )
    op.create_index('idx_predictive_model_category', 'predictive_models', ['prediction_category', 'status'], unique=False)
    op.create_index('idx_predictive_model_type', 'predictive_models', ['model_type', 'algorithm'], unique=False)
    op.create_index('idx_predictive_model_status', 'predictive_models', ['status', 'is_production'], unique=False)
    op.create_index('idx_predictive_model_performance', 'predictive_models', ['accuracy_score', 'f1_score'], unique=False)
    op.create_index('idx_predictive_model_owner', 'predictive_models', ['model_owner', 'status'], unique=False)

    # Create business_insights table
    op.create_table(
        'business_insights',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('insight_type', sa.String(length=50), nullable=False),
        sa.Column('insight_category', sa.String(length=50), nullable=False),
        sa.Column('confidence_level', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('impact_level', sa.Enum('MINIMAL', 'MODERATE', 'SIGNIFICANT', 'CRITICAL', 'STRATEGIC', name='businessimpact'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('key_findings', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('supporting_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('visualization_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('analysis_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('analysis_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('data_sources', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('analysis_methods', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('stakeholder_audience', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('business_objectives', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('strategic_alignment', sa.Text(), nullable=True),
        sa.Column('recommended_actions', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('action_priority', sa.String(length=20), nullable=True),
        sa.Column('implementation_timeline', sa.String(length=50), nullable=True),
        sa.Column('resource_requirements', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('expected_benefits', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('success_metrics', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('roi_estimate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('assigned_to', sa.String(length=100), nullable=True),
        sa.Column('follow_up_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('implementation_status', sa.String(length=20), nullable=True),
        sa.Column('outcomes_measured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('related_insights', postgresql.ARRAY(postgresql.UUID()), nullable=True),
        sa.Column('external_references', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_business_insight_type_category', 'business_insights', ['insight_type', 'insight_category'], unique=False)
    op.create_index('idx_business_insight_impact', 'business_insights', ['impact_level', 'created_at'], unique=False)
    op.create_index('idx_business_insight_status', 'business_insights', ['status', 'follow_up_date'], unique=False)
    op.create_index('idx_business_insight_audience', 'business_insights', ['stakeholder_audience', 'created_at'], unique=False)
    op.create_index('idx_business_insight_priority', 'business_insights', ['action_priority', 'impact_level'], unique=False)


def downgrade() -> None:
    """Remove predictive analytics models tables."""

    # Drop tables in reverse order of creation
    op.drop_table('business_insights')
    op.drop_table('predictive_models')
    op.drop_table('executive_dashboard_metrics')
    op.drop_table('fraud_detection_results')
    op.drop_table('anomaly_detections')
    op.drop_table('prediction_results')
    op.drop_table('prediction_executions')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS predictioncategory')
    op.execute('DROP TYPE IF EXISTS modelaccuracy')
    op.execute('DROP TYPE IF EXISTS anomalyseverity')
    op.execute('DROP TYPE IF EXISTS businessimpact')