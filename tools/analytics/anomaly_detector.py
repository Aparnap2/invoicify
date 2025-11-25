#!/usr/bin/env python3
"""
Anomaly Detection Tool

This script provides utilities for detecting anomalies in the AP Intake system.
It includes various statistical and machine learning approaches for anomaly detection.

Features:
- Volume anomaly detection
- Processing time anomaly detection
- Exception rate anomaly detection
- Vendor behavior anomaly detection
- Payment pattern anomaly detection
- Automated alerting and reporting
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import AsyncSessionLocal
from app.services.predictive_analytics_service import PredictiveAnalyticsService, AnomalyType, AnomalySeverity
from app.models.invoice import Invoice, InvoiceStatus
from app.models.metrics import InvoiceMetric

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Advanced anomaly detection system for AP Intake."""

    def __init__(self, sensitivity: float = 2.0, min_data_points: int = 10):
        """Initialize the anomaly detector."""
        self.sensitivity = sensitivity
        self.min_data_points = min_data_points
        self.detection_methods = {
            "statistical": self._detect_statistical_anomalies,
            "isolation_forest": self._detect_isolation_forest_anomalies,
            "seasonal": self._detect_seasonal_anomalies
        }

    async def detect_volume_anomalies(self, lookback_days: int = 30) -> List[Dict[str, Any]]:
        """Detect anomalies in invoice volume patterns."""
        try:
            logger.info("Detecting volume anomalies...")

            async with AsyncSessionLocal() as db:
                # Get daily invoice counts
                volume_data = await self._get_daily_volume_data(db, lookback_days)

                if len(volume_data) < self.min_data_points:
                    logger.warning("Insufficient data for volume anomaly detection")
                    return []

                # Convert to pandas for analysis
                df = pd.DataFrame(volume_data)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')

                anomalies = []

                # Statistical detection
                statistical_anomalies = self._detect_statistical_anomalies(df, 'count', 'date')
                anomalies.extend(statistical_anomalies)

                # Seasonal detection
                seasonal_anomalies = self._detect_seasonal_anomalies(df, 'count', 'date')
                anomalies.extend(seasonal_anomalies)

                # Isolation forest detection
                if len(df) >= 20:  # Need sufficient data for isolation forest
                    if_anomalies = self._detect_isolation_forest_anomalies(df, 'count')
                    anomalies.extend(if_anomalies)

                # Format results
                formatted_anomalies = []
                for anomaly in anomalies:
                    formatted_anomalies.append({
                        "anomaly_type": AnomalyType.VOLUME_ANOMALY.value,
                        "severity": anomaly.get("severity", AnomalySeverity.MEDIUM.value),
                        "anomaly_score": anomaly.get("score", 0.0),
                        "description": anomaly.get("description", ""),
                        "affected_entities": ["daily_invoice_volume"],
                        "detection_date": datetime.utcnow().isoformat(),
                        "recommended_actions": anomaly.get("recommendations", []),
                        "false_positive_probability": anomaly.get("false_positive_prob", 0.1),
                        "historical_context": {
                            "expected_range": anomaly.get("expected_range"),
                            "actual_value": anomaly.get("actual_value"),
                            "date": anomaly.get("date")
                        }
                    })

                return formatted_anomalies

        except Exception as e:
            logger.error(f"Error detecting volume anomalies: {e}")
            return []

    async def detect_processing_time_anomalies(self, lookback_days: int = 30) -> List[Dict[str, Any]]:
        """Detect anomalies in processing time patterns."""
        try:
            logger.info("Detecting processing time anomalies...")

            async with AsyncSessionLocal() as db:
                # Get processing time data
                processing_data = await self._get_processing_time_data(db, lookback_days)

                if len(processing_data) < self.min_data_points:
                    logger.warning("Insufficient data for processing time anomaly detection")
                    return []

                df = pd.DataFrame(processing_data)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')

                anomalies = []

                # Detect anomalies in average processing time
                statistical_anomalies = self._detect_statistical_anomalies(
                    df, 'avg_processing_time', 'date'
                )
                for anomaly in statistical_anomalies:
                    anomaly["description"] = f"Processing time anomaly: {anomaly['description']}"
                    anomaly["recommendations"] = [
                        "Investigate processing bottlenecks",
                        "Check system resource utilization",
                        "Review recent system changes"
                    ]
                anomalies.extend(statistical_anomalies)

                # Detect anomalies in maximum processing times
                max_time_anomalies = self._detect_statistical_anomalies(
                    df, 'max_processing_time', 'date'
                )
                for anomaly in max_time_anomalies:
                    anomaly["description"] = f"Maximum processing time anomaly: {anomaly['description']}"
                    anomaly["recommendations"] = [
                        "Investigate outlier invoices with long processing times",
                        "Check for complex invoice formats",
                        "Review validation errors"
                    ]
                anomalies.extend(max_time_anomalies)

                # Format results
                formatted_anomalies = []
                for anomaly in anomalies:
                    formatted_anomalies.append({
                        "anomaly_type": AnomalyType.PROCESSING_TIME_ANOMALY.value,
                        "severity": anomaly.get("severity", AnomalySeverity.MEDIUM.value),
                        "anomaly_score": anomaly.get("score", 0.0),
                        "description": anomaly.get("description", ""),
                        "affected_entities": ["invoice_processing_system"],
                        "detection_date": datetime.utcnow().isoformat(),
                        "recommended_actions": anomaly.get("recommendations", []),
                        "false_positive_probability": anomaly.get("false_positive_prob", 0.1),
                        "historical_context": {
                            "expected_range": anomaly.get("expected_range"),
                            "actual_value": anomaly.get("actual_value"),
                            "date": anomaly.get("date")
                        }
                    })

                return formatted_anomalies

        except Exception as e:
            logger.error(f"Error detecting processing time anomalies: {e}")
            return []

    async def detect_exception_rate_anomalies(self, lookback_days: int = 30) -> List[Dict[str, Any]]:
        """Detect anomalies in exception rate patterns."""
        try:
            logger.info("Detecting exception rate anomalies...")

            async with AsyncSessionLocal() as db:
                # Get exception rate data
                exception_data = await self._get_exception_rate_data(db, lookback_days)

                if len(exception_data) < self.min_data_points:
                    logger.warning("Insufficient data for exception rate anomaly detection")
                    return []

                df = pd.DataFrame(exception_data)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')

                anomalies = []

                # Detect anomalies in exception rates
                statistical_anomalies = self._detect_statistical_anomalies(
                    df, 'exception_rate', 'date'
                )
                for anomaly in statistical_anomalies:
                    anomaly["description"] = f"Exception rate anomaly: {anomaly['description']}"
                    anomaly["recommendations"] = [
                        "Review validation rule changes",
                        "Check for data quality issues",
                        "Investigate source of processing errors"
                    ]
                anomalies.extend(statistical_anomalies)

                # Format results
                formatted_anomalies = []
                for anomaly in anomalies:
                    formatted_anomalies.append({
                        "anomaly_type": AnomalyType.EXCEPTION_RATE_ANOMALY.value,
                        "severity": anomaly.get("severity", AnomalySeverity.MEDIUM.value),
                        "anomaly_score": anomaly.get("score", 0.0),
                        "description": anomaly.get("description", ""),
                        "affected_entities": ["validation_system"],
                        "detection_date": datetime.utcnow().isoformat(),
                        "recommended_actions": anomaly.get("recommendations", []),
                        "false_positive_probability": anomaly.get("false_positive_prob", 0.1),
                        "historical_context": {
                            "expected_range": anomaly.get("expected_range"),
                            "actual_value": anomaly.get("actual_value"),
                            "date": anomaly.get("date")
                        }
                    })

                return formatted_anomalies

        except Exception as e:
            logger.error(f"Error detecting exception rate anomalies: {e}")
            return []

    async def detect_vendor_behavior_anomalies(self, lookback_days: int = 30) -> List[Dict[str, Any]]:
        """Detect anomalies in vendor behavior patterns."""
        try:
            logger.info("Detecting vendor behavior anomalies...")

            async with AsyncSessionLocal() as db:
                # Get vendor performance data
                vendor_data = await self._get_vendor_behavior_data(db, lookback_days)

                if vendor_data.empty:
                    logger.warning("No vendor data available for anomaly detection")
                    return []

                anomalies = []

                # Group by vendor and detect anomalies per vendor
                for vendor_id in vendor_data['vendor_id'].unique():
                    vendor_df = vendor_data[vendor_data['vendor_id'] == vendor_id].copy()

                    if len(vendor_df) < 5:  # Need sufficient data per vendor
                        continue

                    vendor_df = vendor_df.sort_values('date')

                    # Detect anomalies in invoice volume
                    volume_anomalies = self._detect_statistical_anomalies(
                        vendor_df, 'invoice_count', 'date'
                    )
                    for anomaly in volume_anomalies:
                        anomaly["description"] = f"Vendor {vendor_id} volume anomaly: {anomaly['description']}"
                        anomaly["affected_entities"] = [f"vendor_{vendor_id}"]
                        anomaly["recommendations"] = [
                            "Contact vendor to verify invoice volume changes",
                            "Check for business relationship changes",
                            "Review contract terms"
                        ]
                    anomalies.extend(volume_anomalies)

                    # Detect anomalies in average invoice amounts
                    amount_anomalies = self._detect_statistical_anomalies(
                        vendor_df, 'avg_amount', 'date'
                    )
                    for anomaly in amount_anomalies:
                        anomaly["description"] = f"Vendor {vendor_id} amount anomaly: {anomaly['description']}"
                        anomaly["affected_entities"] = [f"vendor_{vendor_id}"]
                        anomaly["recommendations"] = [
                            "Verify invoice amounts with vendor",
                            "Check for price changes or new product lines",
                            "Review contract terms for pricing"
                        ]
                    anomalies.extend(amount_anomalies)

                # Format results
                formatted_anomalies = []
                for anomaly in anomalies:
                    formatted_anomalies.append({
                        "anomaly_type": AnomalyType.VENDOR_BEHAVIOR_ANOMALY.value,
                        "severity": anomaly.get("severity", AnomalySeverity.MEDIUM.value),
                        "anomaly_score": anomaly.get("score", 0.0),
                        "description": anomaly.get("description", ""),
                        "affected_entities": anomaly.get("affected_entities", []),
                        "detection_date": datetime.utcnow().isoformat(),
                        "recommended_actions": anomaly.get("recommendations", []),
                        "false_positive_probability": anomaly.get("false_positive_prob", 0.15),
                        "historical_context": {
                            "expected_range": anomaly.get("expected_range"),
                            "actual_value": anomaly.get("actual_value"),
                            "date": anomaly.get("date")
                        }
                    })

                return formatted_anomalies

        except Exception as e:
            logger.error(f"Error detecting vendor behavior anomalies: {e}")
            return []

    def _detect_statistical_anomalies(
        self, df: pd.DataFrame, value_column: str, date_column: str
    ) -> List[Dict[str, Any]]:
        """Detect anomalies using statistical methods (Z-score and IQR)."""
        anomalies = []

        try:
            values = df[value_column].dropna()

            if len(values) < self.min_data_points:
                return anomalies

            # Calculate statistics
            mean = values.mean()
            std = values.std()
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1

            # Define thresholds
            zscore_threshold = self.sensitivity
            iqr_threshold = 1.5

            # Check for anomalies
            for idx, row in df.iterrows():
                value = row[value_column]
                date = row[date_column]

                if pd.isna(value):
                    continue

                # Z-score method
                zscore = abs((value - mean) / std) if std > 0 else 0

                # IQR method
                iqr_score = 0
                if value < (q1 - iqr_threshold * iqr) or value > (q3 + iqr_threshold * iqr):
                    iqr_score = max(abs(value - q1) / iqr, abs(value - q3) / iqr)

                # Combined anomaly score
                anomaly_score = max(zscore, iqr_score)

                if anomaly_score > zscore_threshold:
                    severity = AnomalySeverity.HIGH.value if anomaly_score > 3 else AnomalySeverity.MEDIUM.value
                    if anomaly_score > 4:
                        severity = AnomalySeverity.CRITICAL.value

                    expected_range = f"{(q1 - iqr_threshold * iqr):.2f} - {(q3 + iqr_threshold * iqr):.2f}"

                    anomalies.append({
                        "date": date.isoformat() if hasattr(date, 'isoformat') else str(date),
                        "actual_value": float(value),
                        "expected_range": expected_range,
                        "score": anomaly_score,
                        "zscore": zscore,
                        "iqr_score": iqr_score,
                        "severity": severity,
                        "false_positive_prob": max(0.05, 1.0 - (anomaly_score / 10.0)),
                        "description": f"{value_column} value of {value:.2f} is {anomaly_score:.2f} standard deviations from mean"
                    })

        except Exception as e:
            logger.error(f"Error in statistical anomaly detection: {e}")

        return anomalies

    def _detect_isolation_forest_anomalies(
        self, df: pd.DataFrame, value_column: str
    ) -> List[Dict[str, Any]]:
        """Detect anomalies using Isolation Forest."""
        anomalies = []

        try:
            if len(df) < 20:
                return anomalies

            # Prepare data
            X = df[[value_column]].dropna()

            if len(X) < 20:
                return anomalies

            # Scale the data
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # Train Isolation Forest
            iso_forest = IsolationForest(
                contamination=0.1,  # Expect 10% anomalies
                random_state=42
            )
            anomaly_labels = iso_forest.fit_predict(X_scaled)
            anomaly_scores = iso_forest.decision_function(X_scaled)

            # Find anomalies
            for idx, (label, score) in enumerate(zip(anomaly_labels, anomaly_scores)):
                if label == -1:  # Anomaly
                    row_idx = X.index[idx]
                    value = df.loc[row_idx, value_column]
                    date = df.loc[row_idx, 'date'] if 'date' in df.columns else None

                    anomaly_score = abs(score) * 10  # Scale to 0-10 range
                    severity = (
                        AnomalySeverity.HIGH.value if anomaly_score > 3
                        else AnomalySeverity.MEDIUM.value
                    )

                    anomalies.append({
                        "date": date.isoformat() if date and hasattr(date, 'isoformat') else str(date),
                        "actual_value": float(value),
                        "score": anomaly_score,
                        "severity": severity,
                        "false_positive_prob": max(0.05, 1.0 - (anomaly_score / 10.0)),
                        "description": f"Isolation Forest detected anomaly in {value_column}: {value:.2f}"
                    })

        except Exception as e:
            logger.error(f"Error in isolation forest anomaly detection: {e}")

        return anomalies

    def _detect_seasonal_anomalies(
        self, df: pd.DataFrame, value_column: str, date_column: str
    ) -> List[Dict[str, Any]]:
        """Detect seasonal anomalies using day-of-week patterns."""
        anomalies = []

        try:
            if len(df) < 14:  # Need at least 2 weeks of data
                return anomalies

            # Add day of week
            df_copy = df.copy()
            df_copy['day_of_week'] = pd.to_datetime(df_copy[date_column]).dt.dayofweek

            # Calculate statistics by day of week
            dow_stats = df_copy.groupby('day_of_week')[value_column].agg(['mean', 'std']).reset_index()

            # Detect anomalies for each day
            for _, row in df_copy.iterrows():
                day_of_week = row['day_of_week']
                value = row[value_column]
                date = row[date_column]

                dow_stat = dow_stats[dow_stats['day_of_week'] == day_of_week]
                if dow_stat.empty:
                    continue

                dow_mean = dow_stat['mean'].iloc[0]
                dow_std = dow_stat['std'].iloc[0]

                if dow_std == 0:
                    continue

                # Calculate seasonal Z-score
                seasonal_zscore = abs((value - dow_mean) / dow_std)

                if seasonal_zscore > self.sensitivity:
                    severity = (
                        AnomalySeverity.HIGH.value if seasonal_zscore > 3
                        else AnomalySeverity.MEDIUM.value
                    )

                    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    day_name = day_names[day_of_week]

                    anomalies.append({
                        "date": date.isoformat() if hasattr(date, 'isoformat') else str(date),
                        "actual_value": float(value),
                        "expected_range": f"{(dow_mean - dow_std):.2f} - {(dow_mean + dow_std):.2f}",
                        "score": seasonal_zscore,
                        "severity": severity,
                        "false_positive_prob": max(0.05, 1.0 - (seasonal_zscore / 10.0)),
                        "description": f"Seasonal anomaly: {value_column} of {value:.2f} on {day_name} is {seasonal_zscore:.2f} std from {day_name} mean"
                    })

        except Exception as e:
            logger.error(f"Error in seasonal anomaly detection: {e}")

        return anomalies

    async def _get_daily_volume_data(self, db: AsyncSessionLocal, lookback_days: int) -> List[Dict[str, Any]]:
        """Get daily invoice volume data."""
        from sqlalchemy import select, func, cast, Date

        start_date = datetime.utcnow() - timedelta(days=lookback_days)

        query = select(
            cast(Invoice.created_at, Date).label('date'),
            func.count(Invoice.id).label('count')
        ).where(
            Invoice.created_at >= start_date
        ).group_by(
            cast(Invoice.created_at, Date)
        ).order_by('date')

        result = await db.execute(query)
        return [{"date": row.date, "count": row.count} for row in result]

    async def _get_processing_time_data(self, db: AsyncSessionLocal, lookback_days: int) -> List[Dict[str, Any]]:
        """Get processing time data."""
        from sqlalchemy import select, func, cast, Date

        start_date = datetime.utcnow() - timedelta(days=lookback_days)

        query = select(
            cast(Invoice.created_at, Date).label('date'),
            func.avg(InvoiceMetric.time_to_ready_seconds).label('avg_processing_time'),
            func.max(InvoiceMetric.time_to_ready_seconds).label('max_processing_time'),
            func.min(InvoiceMetric.time_to_ready_seconds).label('min_processing_time'),
            func.count(InvoiceMetric.id).label('sample_count')
        ).join(
            Invoice, InvoiceMetric.invoice_id == Invoice.id
        ).where(
            and_(
                Invoice.created_at >= start_date,
                InvoiceMetric.time_to_ready_seconds.isnot(None)
            )
        ).group_by(
            cast(Invoice.created_at, Date)
        ).order_by('date')

        result = await db.execute(query)
        return [
            {
                "date": row.date,
                "avg_processing_time": float(row.avg_processing_time),
                "max_processing_time": float(row.max_processing_time),
                "min_processing_time": float(row.min_processing_time),
                "sample_count": row.sample_count
            }
            for row in result
        ]

    async def _get_exception_rate_data(self, db: AsyncSessionLocal, lookback_days: int) -> List[Dict[str, Any]]:
        """Get exception rate data."""
        from sqlalchemy import select, func, cast, Date
        from app.models.invoice import Exception as InvoiceException

        start_date = datetime.utcnow() - timedelta(days=lookback_days)

        query = select(
            cast(Invoice.created_at, Date).label('date'),
            func.count(Invoice.id).label('total_invoices'),
            func.count(InvoiceException.id).label('exceptions')
        ).outerjoin(
            InvoiceException, Invoice.id == InvoiceException.invoice_id
        ).where(
            Invoice.created_at >= start_date
        ).group_by(
            cast(Invoice.created_at, Date)
        ).order_by('date')

        result = await db.execute(query)
        return [
            {
                "date": row.date,
                "total_invoices": row.total_invoices,
                "exceptions": row.exceptions,
                "exception_rate": (row.exceptions / row.total_invoices * 100) if row.total_invoices > 0 else 0
            }
            for row in result
        ]

    async def _get_vendor_behavior_data(self, db: AsyncSessionLocal, lookback_days: int) -> pd.DataFrame:
        """Get vendor behavior data."""
        from sqlalchemy import select, func, cast, Date

        start_date = datetime.utcnow() - timedelta(days=lookback_days)

        query = select(
            Invoice.vendor_id,
            cast(Invoice.created_at, Date).label('date'),
            func.count(Invoice.id).label('invoice_count'),
            func.avg(Invoice.total_amount).label('avg_amount'),
            func.sum(Invoice.total_amount).label('total_amount')
        ).where(
            and_(
                Invoice.created_at >= start_date,
                Invoice.vendor_id.isnot(None)
            )
        ).group_by(
            Invoice.vendor_id,
            cast(Invoice.created_at, Date)
        ).order_by(
            Invoice.vendor_id,
            'date'
        )

        result = await db.execute(query)
        data = [
            {
                "vendor_id": str(row.vendor_id),
                "date": row.date,
                "invoice_count": row.invoice_count,
                "avg_amount": float(row.avg_amount) if row.avg_amount else 0,
                "total_amount": float(row.total_amount) if row.total_amount else 0
            }
            for row in result
        ]

        return pd.DataFrame(data)


async def main():
    """Main function for the anomaly detection tool."""
    parser = argparse.ArgumentParser(description="Detect anomalies in AP Intake system")
    parser.add_argument(
        "--anomaly-types",
        nargs="+",
        choices=["volume", "processing_time", "exception_rate", "vendor_behavior"],
        default=["volume", "processing_time", "exception_rate", "vendor_behavior"],
        help="Types of anomalies to detect"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Number of days to look back for anomaly detection"
    )
    parser.add_argument(
        "--sensitivity",
        type=float,
        default=2.0,
        help="Sensitivity threshold for anomaly detection (standard deviations)"
    )
    parser.add_argument(
        "--output-file",
        help="Output file to save anomaly results (JSON format)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Starting anomaly detection with sensitivity {args.sensitivity}")

    # Initialize detector
    detector = AnomalyDetector(sensitivity=args.sensitivity)

    # Detect anomalies
    all_anomalies = []

    if "volume" in args.anomaly_types:
        volume_anomalies = await detector.detect_volume_anomalies(args.lookback_days)
        all_anomalies.extend(volume_anomalies)
        logger.info(f"Found {len(volume_anomalies)} volume anomalies")

    if "processing_time" in args.anomaly_types:
        processing_anomalies = await detector.detect_processing_time_anomalies(args.lookback_days)
        all_anomalies.extend(processing_anomalies)
        logger.info(f"Found {len(processing_anomalies)} processing time anomalies")

    if "exception_rate" in args.anomaly_types:
        exception_anomalies = await detector.detect_exception_rate_anomalies(args.lookback_days)
        all_anomalies.extend(exception_anomalies)
        logger.info(f"Found {len(exception_anomalies)} exception rate anomalies")

    if "vendor_behavior" in args.anomaly_types:
        vendor_anomalies = await detector.detect_vendor_behavior_anomalies(args.lookback_days)
        all_anomalies.extend(vendor_anomalies)
        logger.info(f"Found {len(vendor_anomalies)} vendor behavior anomalies")

    # Sort anomalies by severity and score
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_anomalies.sort(key=lambda x: (
        severity_order.get(x["severity"], 3),
        -x["anomaly_score"]
    ))

    # Generate summary
    summary = {
        "total_anomalies": len(all_anomalies),
        "critical_anomalies": len([a for a in all_anomalies if a["severity"] == "critical"]),
        "high_anomalies": len([a for a in all_anomalies if a["severity"] == "high"]),
        "medium_anomalies": len([a for a in all_anomalies if a["severity"] == "medium"]),
        "low_anomalies": len([a for a in all_anomalies if a["severity"] == "low"]),
        "by_type": {}
    }

    for anomaly_type in args.anomaly_types:
        type_anomalies = [a for a in all_anomalies if anomaly_type in a["anomaly_type"]]
        summary["by_type"][anomaly_type] = len(type_anomalies)

    # Prepare results
    results = {
        "scan_metadata": {
            "timestamp": datetime.utcnow().isoformat(),
            "lookback_days": args.lookback_days,
            "sensitivity": args.sensitivity,
            "anomaly_types_scanned": args.anomaly_types
        },
        "summary": summary,
        "anomalies": all_anomalies
    }

    # Display results
    print(f"\n{'='*60}")
    print("ANOMALY DETECTION RESULTS")
    print(f"{'='*60}")
    print(f"Total anomalies found: {summary['total_anomalies']}")
    print(f"Critical: {summary['critical_anomalies']}")
    print(f"High: {summary['high_anomalies']}")
    print(f"Medium: {summary['medium_anomalies']}")
    print(f"Low: {summary['low_anomalies']}")

    print(f"\nBy type:")
    for anomaly_type, count in summary["by_type"].items():
        print(f"  {anomaly_type}: {count}")

    # Show top 10 anomalies
    if all_anomalies:
        print(f"\nTop 10 anomalies:")
        for i, anomaly in enumerate(all_anomalies[:10], 1):
            print(f"{i:2d}. [{anomaly['severity'].upper()}] {anomaly['description'][:80]}...")

    # Save to file if specified
    if args.output_file:
        with open(args.output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output_file}")

    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)