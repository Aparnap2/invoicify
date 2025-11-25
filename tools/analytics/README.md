# Predictive Analytics Tools

This directory contains a comprehensive suite of predictive analytics tools for the AP Intake & Validation system. These tools extend the existing analytics infrastructure with advanced machine learning capabilities for working capital optimization, anomaly detection, and fraud prevention.

## Overview

The predictive analytics system provides:

- **Working Capital Optimization**: Predict future working capital needs and optimization opportunities
- **Vendor Performance Prediction**: Forecast vendor behavior and identify at-risk suppliers
- **Anomaly Detection**: Identify unusual patterns in processing volumes, times, and exceptions
- **Fraud Detection**: Detect potential fraudulent activities using advanced pattern recognition
- **Payment Optimization**: Recommend optimal payment timing and discount utilization strategies
- **Executive Dashboard**: Comprehensive business intelligence and KPI tracking

## Tools

### 1. Predictive Model Trainer (`predictive_model_trainer.py`)

A comprehensive tool for training and evaluating machine learning models for various prediction tasks.

#### Features:
- Multiple ML algorithms (Random Forest, Linear Regression)
- Automated data preparation and feature engineering
- Model evaluation with comprehensive metrics
- Feature importance analysis
- Model persistence and deployment utilities

#### Usage:

```bash
# Train a working capital optimization model
python predictive_model_trainer.py \
    --model-type working_capital \
    --lookback-days 180 \
    --algorithm random_forest \
    --save-model \
    --output-dir ./models

# Train a vendor performance model
python predictive_model_trainer.py \
    --model-type vendor_performance \
    --lookback-days 90 \
    --algorithm random_forest \
    --test-size 0.25 \
    --save-model

# Train a payment optimization model
python predictive_model_trainer.py \
    --model-type payment_optimization \
    --lookback-days 60 \
    --algorithm linear \
    --save-model
```

#### Supported Model Types:
- `working_capital`: Predicts overall working capital optimization scores
- `vendor_performance`: Predicts vendor payment timeliness and quality scores
- `payment_optimization`: Predicts potential savings from payment optimization
- `processing_time`: Predicts invoice processing times based on characteristics

### 2. Anomaly Detector (`anomaly_detector.py`)

Advanced anomaly detection system using statistical methods and machine learning.

#### Features:
- Multiple detection algorithms (Z-score, IQR, Isolation Forest, Seasonal analysis)
- Configurable sensitivity thresholds
- Comprehensive anomaly classification
- Automated alerting and recommendations
- Historical context and trend analysis

#### Usage:

```bash
# Run comprehensive anomaly detection
python anomaly_detector.py \
    --anomaly-types volume processing_time exception_rate vendor_behavior \
    --lookback-days 30 \
    --sensitivity 2.0 \
    --output-file anomalies_report.json \
    --verbose

# Detect only volume anomalies
python anomaly_detector.py \
    --anomaly-types volume \
    --lookback-days 14 \
    --sensitivity 2.5

# High-sensitivity detection for critical monitoring
python anomaly_detector.py \
    --anomaly-types processing_time exception_rate \
    --lookback-days 7 \
    --sensitivity 1.5 \
    --output-file critical_anomalies.json
```

#### Anomaly Types:
- `volume`: Anomalies in daily invoice volume patterns
- `processing_time`: Anomalies in processing time distributions
- `exception_rate`: Anomalies in validation exception rates
- `vendor_behavior`: Anomalies in vendor invoice patterns and amounts

## Integration with Main System

### API Endpoints

The predictive analytics functionality is integrated into the main application through the `/api/v1/analytics/` endpoints:

#### Predictive Analytics Endpoints:

```bash
# Working capital predictions
GET /api/v1/analytics/predictive/working-capital?prediction_days=30&scenario=realistic

# Vendor performance predictions
GET /api/v1/analytics/predictive/vendor-performance?prediction_period_days=90

# Anomaly detection results
GET /api/v1/analytics/predictive/anomalies?lookback_days=30&sensitivity=2.0

# Fraud detection results
GET /api/v1/analytics/predictive/fraud-detection?analysis_period_days=30

# Payment optimization predictions
GET /api/v1/analytics/predictive/payment-optimization?analysis_period_days=30

# Cash flow forecasting
GET /api/v1/analytics/predictive/cash-flow?forecast_days=90

# Processing time predictions
GET /api/v1/analytics/predictive/processing-times

# Executive dashboard with predictive insights
GET /api/v1/analytics/executive/dashboard?include_predictions=true

# Predictive model performance metrics
GET /api/v1/analytics/predictive/model-performance
```

### Database Schema

The predictive analytics system extends the database with several new tables:

- `prediction_executions`: Track model training and execution metadata
- `prediction_results`: Store individual prediction results with confidence scores
- `anomaly_detections`: Record detected anomalies with severity and context
- `fraud_detection_results`: Store fraud detection analysis and evidence
- `executive_dashboard_metrics`: KPI and business intelligence data
- `predictive_models`: Model definitions and performance tracking
- `business_insights`: Generated insights and recommendations

## Configuration

### Environment Variables

```bash
# Predictive Analytics Configuration
PREDICTIVE_ANALYTICS_ENABLED=true
PREDICTION_CONFIDENCE_THRESHOLD=0.7
ANOMALY_DETECTION_SENSITIVITY=2.0
FRAUD_DETECTION_SENSITIVITY=0.8
MODEL_CACHE_TTL_MINUTES=60
PREDICTION_BATCH_SIZE=100

# Model Training Configuration
DEFAULT_TRAINING_LOOKBACK_DAYS=180
MODEL_TEST_SIZE=0.2
MIN_TRAINING_SAMPLES=100
MODEL_RETRAIN_INTERVAL_DAYS=30
PERFORMANCE_DEGRADATION_THRESHOLD=10

# Feature Engineering
FEATURE_SCALING_ENABLED=true
SEASONAL_DETECTION_ENABLED=true
OUTLIER_DETECTION_ENABLED=true
DATA_QUALITY_THRESHOLD=0.8
```

### Model Configuration

Model parameters can be configured in `app/config/predictive_models.py`:

```python
WORKING_CAPITAL_MODEL_CONFIG = {
    "algorithm": "random_forest",
    "n_estimators": 100,
    "max_depth": 10,
    "features": [
        "auto_processing_rate",
        "pass_rate_structural",
        "pass_rate_math",
        "avg_processing_time_hours",
        "exception_rate"
    ]
}

ANOMALY_DETECTION_CONFIG = {
    "statistical_threshold": 2.0,
    "isolation_forest_contamination": 0.1,
    "seasonal_periods": 7,  # weekly seasonality
    "min_data_points": 10
}
```

## Deployment

### Model Training Pipeline

1. **Data Collection**: Gather historical data from the database
2. **Feature Engineering**: Create predictive features from raw data
3. **Model Training**: Train multiple algorithms and select best performer
4. **Validation**: Evaluate model performance on test data
5. **Deployment**: Save model and update prediction service
6. **Monitoring**: Track model performance and retrain when needed

### Scheduled Tasks

Set up cron jobs or scheduled tasks for:

```bash
# Daily anomaly detection
0 8 * * * cd /app && python tools/analytics/anomaly_detector.py --anomaly-types volume processing_time exception_rate

# Weekly model retraining
0 2 * * 0 cd /app && python tools/analytics/predictive_model_trainer.py --model-type working_capital --save-model

# Monthly comprehensive analysis
0 3 1 * * cd /app && python tools/analytics/predictive_model_trainer.py --model-type all --save-model
```

### Docker Integration

Add to your Docker services:

```yaml
analytics-trainer:
  build: .
  command: python tools/analytics/predictive_model_trainer.py --model-type working_capital
  environment:
    - DATABASE_URL=postgresql+asyncpg://...
    - PREDICTIVE_ANALYTICS_ENABLED=true
  volumes:
    - ./models:/app/models
  depends_on:
    - db

anomaly-detector:
  build: .
  command: python tools/analytics/anomaly_detector.py --lookback-days 7
  environment:
    - DATABASE_URL=postgresql+asyncpg://...
  depends_on:
    - db
```

## Monitoring and Maintenance

### Model Performance Monitoring

- Track prediction accuracy over time
- Monitor model drift and degradation
- Set up alerts for performance threshold breaches
- Regular model retraining schedules

### Data Quality Monitoring

- Monitor data availability and completeness
- Track feature distributions for drift detection
- Validate data quality scores
- Handle missing or corrupted data

### System Health Monitoring

- Monitor prediction service response times
- Track anomaly detection accuracy
- Monitor fraud detection false positive rates
- System resource utilization

## Security and Compliance

### Data Privacy

- All prediction data is anonymized where appropriate
- Access controls on sensitive predictions
- Audit logging for all model training activities
- Data retention policies for prediction results

### Model Governance

- Model versioning and rollback capabilities
- Model validation before production deployment
- Documentation for all model decisions
- Regular model performance reviews

### Compliance

- GDPR compliance for data processing
- SOC 2 controls for model management
- Audit trails for all predictions
- Explainability for model decisions

## Troubleshooting

### Common Issues

#### Model Training Fails
```bash
# Check data availability
python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.invoice import Invoice
async def check_data():
    async with AsyncSessionLocal() as db:
        count = await db.execute(select(func.count(Invoice.id)))
        print(f'Total invoices: {count.scalar()}')
asyncio.run(check_data())
"

# Check feature quality
python tools/analytics/predictive_model_trainer.py --model-type working_capital --verbose
```

#### Anomaly Detection Not Working
```bash
# Check minimum data requirements
python tools/analytics/anomaly_detector.py --anomaly-types volume --lookback-days 30 --verbose

# Test with different sensitivity
python tools/analytics/anomaly_detector.py --sensitivity 1.5
```

#### API Endpoints Not Responding
```bash
# Check service health
curl http://localhost:8000/api/v1/analytics/predictive/model-performance

# Check database connection
python -c "
import asyncio
from app.db.session import engine
async def test_db():
    async with engine.begin() as conn:
        result = await conn.execute('SELECT 1')
        print('Database connection OK')
asyncio.run(test_db())
"
```

### Performance Optimization

#### Model Training Performance
- Use appropriate batch sizes for large datasets
- Implement incremental training for continuous learning
- Cache feature engineering results
- Use GPU acceleration for deep learning models

#### API Response Times
- Implement prediction result caching
- Use async processing for long-running predictions
- Batch multiple predictions when possible
- Optimize database queries for feature extraction

## Extending the System

### Adding New Prediction Types

1. Define prediction category in `PredictionType` enum
2. Add data preparation method in `PredictiveAnalyticsService`
3. Implement prediction logic
4. Add API endpoint for new prediction type
5. Update model trainer to support new type

### Adding New Anomaly Detection Methods

1. Implement detection method in `AnomalyDetector`
2. Add configuration options
3. Update CLI interface
4. Add tests for new method

### Custom Model Algorithms

1. Implement custom algorithm class
2. Integrate with model trainer interface
3. Add hyperparameter tuning
4. Update model persistence logic

## API Examples

### Working Capital Prediction

```bash
curl "http://localhost:8000/api/v1/analytics/predictive/working-capital?prediction_days=60&scenario=optimistic" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "success": true,
  "data": {
    "prediction_type": "working_capital",
    "predicted_value": 85.7,
    "confidence_score": 0.82,
    "risk_assessment": "low",
    "recommendations": [
      "Focus on improving collection efficiency",
      "Consider early payment discount optimization"
    ]
  }
}
```

### Anomaly Detection

```bash
curl "http://localhost:8000/api/v1/analytics/predictive/anomalies?anomaly_types=volume,processing_time&sensitivity=2.5" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "success": true,
  "data": {
    "anomalies": [
      {
        "anomaly_type": "volume_anomaly",
        "severity": "high",
        "anomaly_score": 3.2,
        "description": "Unusual spike in invoice volume",
        "recommended_actions": ["Investigate source of volume increase"]
      }
    ]
  }
}
```

## Contributing

When contributing to the predictive analytics system:

1. Follow the existing code style and patterns
2. Add comprehensive tests for new functionality
3. Update documentation for new features
4. Ensure all models have proper validation
5. Include performance benchmarks for new algorithms

## License

This predictive analytics system is part of the AP Intake & Validation system and follows the same licensing terms.