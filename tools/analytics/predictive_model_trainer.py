#!/usr/bin/env python3
"""
Predictive Model Training Tool

This script provides utilities for training and evaluating predictive models
for the AP Intake & Validation system. It includes:

- Working capital optimization model training
- Vendor performance prediction model training
- Anomaly detection model training
- Fraud detection model training
- Model evaluation and validation
- Model deployment utilities
"""

import asyncio
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, accuracy_score, precision_score, recall_score, f1_score
import joblib

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import AsyncSessionLocal
from app.services.predictive_analytics_service import PredictiveAnalyticsService
from app.models.analytics import PredictiveModel, PredictionCategory, ModelAccuracy
from app.models.invoice import Invoice, InvoiceStatus, InvoiceMetric
from app.models.working_capital import WeeklyMetric

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PredictiveModelTrainer:
    """Class for training and evaluating predictive models."""

    def __init__(self, model_type: str, config: Optional[Dict[str, Any]] = None):
        """Initialize the model trainer."""
        self.model_type = model_type
        self.config = config or {}
        self.model = None
        self.feature_columns = []
        self.target_column = ""
        self.training_data = None
        self.test_data = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None

    async def prepare_data(self, lookback_days: int = 180) -> bool:
        """Prepare training data from the database."""
        try:
            logger.info(f"Preparing data for {self.model_type} model training...")

            async with AsyncSessionLocal() as db:
                if self.model_type == "working_capital":
                    data = await self._prepare_working_capital_data(db, lookback_days)
                elif self.model_type == "vendor_performance":
                    data = await self._prepare_vendor_performance_data(db, lookback_days)
                elif self.model_type == "payment_optimization":
                    data = await self._prepare_payment_optimization_data(db, lookback_days)
                elif self.model_type == "processing_time":
                    data = await self._prepare_processing_time_data(db, lookback_days)
                else:
                    logger.error(f"Unknown model type: {self.model_type}")
                    return False

                if data.empty:
                    logger.error(f"No training data available for {self.model_type}")
                    return False

                self.training_data = data
                logger.info(f"Prepared {len(data)} records for training")
                return True

        except Exception as e:
            logger.error(f"Error preparing training data: {e}")
            return False

    async def _prepare_working_capital_data(self, db: AsyncSessionLocal, lookback_days: int) -> pd.DataFrame:
        """Prepare working capital optimization training data."""
        from sqlalchemy import select

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=lookback_days)

        # Query weekly metrics
        query = select(WeeklyMetric).where(
            WeeklyMetric.week_start_date >= start_date.date()
        ).order_by(WeeklyMetric.week_start_date)

        result = await db.execute(query)
        weekly_metrics = result.scalars().all()

        data = []
        for metric in weekly_metrics:
            data.append({
                "week_start": metric.week_start_date,
                "auto_processing_rate": float(metric.auto_processing_rate),
                "pass_rate_structural": float(metric.pass_rate_structural),
                "pass_rate_math": float(metric.pass_rate_math),
                "avg_processing_time_hours": float(metric.avg_processing_time_hours),
                "total_invoice_amount": float(metric.total_invoice_amount),
                "cost_per_invoice": float(metric.cost_per_invoice),
                "roi_percentage": float(metric.roi_percentage),
                "total_invoices": metric.invoices_processed,
                "auto_processed": metric.auto_processed,
                "exceptions_created": metric.exceptions_created,
                "duplicates_detected": metric.duplicates_detected
            })

        df = pd.DataFrame(data)

        # Create target variable (overall performance score)
        df["target_score"] = (
            df["auto_processing_rate"] * 0.3 +
            df["pass_rate_structural"] * 0.25 +
            df["pass_rate_math"] * 0.25 +
            (100 - df["avg_processing_time_hours"] * 2) * 0.2
        )
        df["target_score"] = df["target_score"].clip(0, 100)

        # Feature engineering
        df["processing_efficiency"] = df["auto_processed"] / df["total_invoices"]
        df["exception_rate"] = df["exceptions_created"] / df["total_invoices"]
        df["duplicate_rate"] = df["duplicates_detected"] / df["total_invoices"]
        df["cost_efficiency"] = df["total_invoice_amount"] / (df["cost_per_invoice"] + 1)  # Avoid division by zero

        # Define feature columns
        self.feature_columns = [
            "auto_processing_rate", "pass_rate_structural", "pass_rate_math",
            "avg_processing_time_hours", "total_invoice_amount", "cost_per_invoice",
            "processing_efficiency", "exception_rate", "duplicate_rate", "cost_efficiency"
        ]
        self.target_column = "target_score"

        return df

    async def _prepare_vendor_performance_data(self, db: AsyncSessionLocal, lookback_days: int) -> pd.DataFrame:
        """Prepare vendor performance training data."""
        from sqlalchemy import select, func
        from app.models.invoice import Invoice, InvoiceStatus
        from app.models.reference import Vendor

        # This is a simplified version - in practice, you'd gather more vendor-specific metrics
        query = select(
            Vendor.id,
            func.count(Invoice.id).label('total_invoices'),
            func.avg(InvoiceMetric.time_to_ready_seconds).label('avg_processing_time'),
            func.sum(func.case([(Invoice.status == InvoiceStatus.DONE, 1)], else_=0)).label('processed_invoices')
        ).join(
            Invoice, Vendor.id == Invoice.vendor_id
        ).join(
            InvoiceMetric, Invoice.id == InvoiceMetric.invoice_id
        ).where(
            Invoice.created_at >= datetime.utcnow() - timedelta(days=lookback_days)
        ).group_by(Vendor.id)

        result = await db.execute(query)
        vendor_data = result.all()

        data = []
        for row in vendor_data:
            data.append({
                "vendor_id": str(row.id),
                "total_invoices": row.total_invoices,
                "avg_processing_time": float(row.avg_processing_time) if row.avg_processing_time else 0,
                "processed_invoices": row.processed_invoices,
                "success_rate": (row.processed_invoices / row.total_invoices * 100) if row.total_invoices > 0 else 0
            })

        df = pd.DataFrame(data)

        # Create target variables
        df["payment_timeliness_score"] = 100 - (df["avg_processing_time"] / 60)  # Convert to hours, inverse relationship
        df["payment_timeliness_score"] = df["payment_timeliness_score"].clip(0, 100)
        df["quality_score"] = df["success_rate"]

        # Feature columns for timeliness prediction
        self.feature_columns = ["total_invoices", "avg_processing_time", "success_rate"]
        self.target_column = "payment_timeliness_score"

        return df

    async def _prepare_payment_optimization_data(self, db: AsyncSessionLocal, lookback_days: int) -> pd.DataFrame:
        """Prepare payment optimization training data."""
        # Placeholder implementation
        # In practice, this would analyze payment timing, discount utilization, etc.
        data = []
        for i in range(100):  # Generate synthetic data for demo
            data.append({
                "invoice_amount": np.random.uniform(100, 10000),
                "payment_terms": np.random.choice([15, 30, 45, 60]),
                "early_payment_discount": np.random.choice([0, 1, 2, 3]),
                "day_of_week": np.random.choice(range(7)),
                "season": np.random.choice([1, 2, 3, 4]),
                "savings": np.random.uniform(0, 500)
            })

        df = pd.DataFrame(data)
        self.feature_columns = ["invoice_amount", "payment_terms", "early_payment_discount", "day_of_week", "season"]
        self.target_column = "savings"

        return df

    async def _prepare_processing_time_data(self, db: AsyncSessionLocal, lookback_days: int) -> pd.DataFrame:
        """Prepare processing time prediction training data."""
        from sqlalchemy import select, func

        query = select(
            InvoiceMetric.file_size_bytes,
            InvoiceMetric.page_count,
            InvoiceMetric.exception_count,
            InvoiceMetric.processing_step_count,
            InvoiceMetric.time_to_ready_seconds,
            func.extract('dow', Invoice.created_at).label('day_of_week'),
            func.extract('hour', Invoice.created_at).label('hour_of_day')
        ).join(
            Invoice, InvoiceMetric.invoice_id == Invoice.id
        ).where(
            and_(
                Invoice.created_at >= datetime.utcnow() - timedelta(days=lookback_days),
                InvoiceMetric.time_to_ready_seconds.isnot(None)
            )
        )

        result = await db.execute(query)
        processing_data = result.all()

        data = []
        for row in processing_data:
            data.append({
                "file_size_bytes": row.file_size_bytes or 0,
                "page_count": row.page_count or 0,
                "exception_count": row.exception_count,
                "processing_step_count": row.processing_step_count,
                "processing_time_seconds": row.time_to_ready_seconds,
                "day_of_week": row.day_of_week,
                "hour_of_day": row.hour_of_day
            })

        df = pd.DataFrame(data)

        # Feature engineering
        df["file_size_mb"] = df["file_size_bytes"] / (1024 * 1024)
        df["complexity_score"] = df["page_count"] + df["exception_count"] + (df["processing_step_count"] / 10)
        df["is_weekend"] = df["day_of_week"].isin([0, 6]).astype(int)
        df["is_business_hours"] = df["hour_of_day"].between(9, 17).astype(int)

        self.feature_columns = [
            "file_size_mb", "page_count", "exception_count", "complexity_score",
            "day_of_week", "hour_of_day", "is_weekend", "is_business_hours"
        ]
        self.target_column = "processing_time_seconds"

        return df

    def split_data(self, test_size: float = 0.2, random_state: int = 42) -> bool:
        """Split data into training and testing sets."""
        try:
            if self.training_data is None or self.training_data.empty:
                logger.error("No training data available")
                return False

            # Handle missing values
            self.training_data = self.training_data.fillna(self.training_data.mean())

            # Split features and target
            X = self.training_data[self.feature_columns]
            y = self.training_data[self.target_column]

            # Split data
            self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state
            )

            logger.info(f"Split data: {len(self.X_train)} training samples, {len(self.X_test)} test samples")
            return True

        except Exception as e:
            logger.error(f"Error splitting data: {e}")
            return False

    def train_model(self, model_type: str = "random_forest") -> bool:
        """Train the predictive model."""
        try:
            if self.X_train is None or self.y_train is None:
                logger.error("Training data not prepared")
                return False

            logger.info(f"Training {model_type} model for {self.model_type}")

            if model_type == "random_forest":
                if self.target_column in ["target_score", "savings", "processing_time_seconds"]:
                    self.model = RandomForestRegressor(
                        n_estimators=100,
                        random_state=42,
                        n_jobs=-1
                    )
                else:
                    self.model = RandomForestClassifier(
                        n_estimators=100,
                        random_state=42,
                        n_jobs=-1
                    )
            elif model_type == "linear":
                if self.target_column in ["target_score", "savings", "processing_time_seconds"]:
                    self.model = LinearRegression()
                else:
                    self.model = LogisticRegression(random_state=42)
            else:
                logger.error(f"Unknown model type: {model_type}")
                return False

            # Train the model
            self.model.fit(self.X_train, self.y_train)
            logger.info(f"Model training completed for {self.model_type}")
            return True

        except Exception as e:
            logger.error(f"Error training model: {e}")
            return False

    def evaluate_model(self) -> Dict[str, float]:
        """Evaluate the trained model."""
        try:
            if self.model is None:
                logger.error("Model not trained")
                return {}

            # Make predictions
            y_pred = self.model.predict(self.X_test)

            # Calculate metrics
            if self.target_column in ["target_score", "savings", "processing_time_seconds"]:
                # Regression metrics
                mse = mean_squared_error(self.y_test, y_pred)
                mae = mean_absolute_error(self.y_test, y_pred)
                r2 = r2_score(self.y_test, y_pred)
                rmse = np.sqrt(mse)

                metrics = {
                    "mse": mse,
                    "mae": mae,
                    "rmse": rmse,
                    "r2_score": r2,
                    "accuracy_score": max(0, r2 * 100)  # Convert R² to accuracy-like score
                }
            else:
                # Classification metrics
                accuracy = accuracy_score(self.y_test, y_pred)
                precision = precision_score(self.y_test, y_pred, average='weighted', zero_division=0)
                recall = recall_score(self.y_test, y_pred, average='weighted', zero_division=0)
                f1 = f1_score(self.y_test, y_pred, average='weighted', zero_division=0)

                metrics = {
                    "accuracy_score": accuracy * 100,
                    "precision_score": precision * 100,
                    "recall_score": recall * 100,
                    "f1_score": f1 * 100
                }

            logger.info(f"Model evaluation completed: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"Error evaluating model: {e}")
            return {}

    def save_model(self, model_path: str) -> bool:
        """Save the trained model to disk."""
        try:
            if self.model is None:
                logger.error("No model to save")
                return False

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(model_path), exist_ok=True)

            # Save model and metadata
            model_data = {
                "model": self.model,
                "feature_columns": self.feature_columns,
                "target_column": self.target_column,
                "model_type": self.model_type,
                "training_date": datetime.utcnow().isoformat(),
                "training_samples": len(self.X_train) if self.X_train is not None else 0
            }

            joblib.dump(model_data, model_path)
            logger.info(f"Model saved to {model_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving model: {e}")
            return False

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from the trained model."""
        try:
            if self.model is None or not hasattr(self.model, 'feature_importances_'):
                return {}

            importance = self.model.feature_importances_
            feature_importance = dict(zip(self.feature_columns, importance))

            # Sort by importance
            feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))

            return feature_importance

        except Exception as e:
            logger.error(f"Error getting feature importance: {e}")
            return {}


async def train_model_workflow(
    model_type: str,
    lookback_days: int,
    test_size: float,
    model_algorithm: str,
    save_model: bool,
    output_dir: str
) -> bool:
    """Complete workflow for training a predictive model."""
    logger.info(f"Starting training workflow for {model_type} model")

    # Initialize trainer
    trainer = PredictiveModelTrainer(model_type)

    # Prepare data
    if not await trainer.prepare_data(lookback_days):
        logger.error("Failed to prepare training data")
        return False

    # Split data
    if not trainer.split_data(test_size=test_size):
        logger.error("Failed to split data")
        return False

    # Train model
    if not trainer.train_model(model_algorithm):
        logger.error("Failed to train model")
        return False

    # Evaluate model
    metrics = trainer.evaluate_model()
    if not metrics:
        logger.error("Failed to evaluate model")
        return False

    # Print results
    print(f"\n{'='*50}")
    print(f"Training Results for {model_type} Model")
    print(f"{'='*50}")
    for metric, value in metrics.items():
        print(f"{metric:25}: {value:.4f}")

    # Feature importance
    feature_importance = trainer.get_feature_importance()
    if feature_importance:
        print(f"\nFeature Importance:")
        for feature, importance in feature_importance.items():
            print(f"{feature:25}: {importance:.4f}")

    # Save model
    if save_model:
        model_filename = f"{model_type}_{model_algorithm}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.joblib"
        model_path = os.path.join(output_dir, model_filename)

        if trainer.save_model(model_path):
            print(f"\nModel saved to: {model_path}")
        else:
            print(f"\nFailed to save model")

    print(f"{'='*50}")

    return True


async def main():
    """Main function for the model training tool."""
    parser = argparse.ArgumentParser(description="Train predictive models for AP Intake system")
    parser.add_argument(
        "--model-type",
        choices=["working_capital", "vendor_performance", "payment_optimization", "processing_time"],
        required=True,
        help="Type of model to train"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=180,
        help="Number of days of historical data to use for training"
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Proportion of data to use for testing (0.0-1.0)"
    )
    parser.add_argument(
        "--algorithm",
        choices=["random_forest", "linear"],
        default="random_forest",
        help="Machine learning algorithm to use"
    )
    parser.add_argument(
        "--save-model",
        action="store_true",
        help="Save the trained model to disk"
    )
    parser.add_argument(
        "--output-dir",
        default="./models",
        help="Directory to save trained models"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.test_size <= 0 or args.test_size >= 1:
        logger.error("Test size must be between 0 and 1")
        return 1

    if args.lookback_days <= 0:
        logger.error("Lookback days must be positive")
        return 1

    # Create output directory if saving model
    if args.save_model:
        os.makedirs(args.output_dir, exist_ok=True)

    # Run training workflow
    success = await train_model_workflow(
        model_type=args.model_type,
        lookback_days=args.lookback_days,
        test_size=args.test_size,
        model_algorithm=args.algorithm,
        save_model=args.save_model,
        output_dir=args.output_dir
    )

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)