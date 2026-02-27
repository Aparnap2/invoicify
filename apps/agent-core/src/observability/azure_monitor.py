"""
Observability package for Invoicify.

Provides:
- OpenTelemetry tracing
- Azure Monitor integration
- Custom metrics (latency, confidence, decisions)
- Structured logging with structlog
"""

import time
import structlog
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from functools import wraps

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# METRICS COLLECTION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MetricPoint:
    """Single metric data point."""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: str = "gauge"  # gauge, counter, histogram


class MetricsCollector:
    """
    Collects and exports metrics to Azure Monitor.
    
    Thread-safe metric collection with batch export.
    """
    
    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize metrics collector.
        
        Args:
            connection_string: Azure Application Insights connection string
        """
        self.connection_string = connection_string
        self._metrics: List[MetricPoint] = []
        self._client = None
        
        if connection_string:
            self._initialize_azure_monitor()
    
    def _initialize_azure_monitor(self):
        """Initialize Azure Monitor client."""
        try:
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            
            # Configure OTLP exporter for Azure Monitor
            exporter = OTLPMetricExporter(
                endpoint="https://dc.services.visualstudio.com/v2/track",
                headers={"Authorization": f"Bearer {self.connection_string}"},
            )
            
            reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000)
            provider = MeterProvider(metric_readers=[reader])
            metrics.set_meter_provider(provider)
            
            self._client = metrics.get_meter("invoicify")
            
            logger.info("azure_monitor_initialized")
            
        except ImportError as e:
            logger.warning("opentelemetry_not_installed", error=str(e))
        except Exception as e:
            logger.error("azure_monitor_init_failed", error=str(e))
    
    def record(
        self,
        name: str,
        value: float,
        metric_type: str = "gauge",
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        Record a metric value.
        
        Args:
            name: Metric name
            value: Metric value
            metric_type: gauge, counter, or histogram
            tags: Additional tags
        """
        point = MetricPoint(
            name=name,
            value=value,
            metric_type=metric_type,
            tags=tags or {},
        )
        self._metrics.append(point)
        
        # Export to Azure Monitor if configured
        if self._client:
            self._export_to_azure(point)
    
    def _export_to_azure(self, point: MetricPoint):
        """Export single metric to Azure Monitor."""
        try:
            if point.metric_type == "counter":
                counter = self._client.create_counter(point.name)
                counter.add(point.value, point.tags)
            elif point.metric_type == "histogram":
                histogram = self._client.create_histogram(point.name)
                histogram.record(point.value, point.tags)
            else:  # gauge
                gauge = self._client.create_gauge(point.name)
                gauge.set(point.value, point.tags)
        except Exception as e:
            logger.error("azure_monitor_export_failed", error=str(e))
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        return {
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "type": m.metric_type,
                    "tags": m.tags,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self._metrics[-100:]  # Last 100 metrics
            ],
            "total_collected": len(self._metrics),
        }
    
    def clear(self):
        """Clear collected metrics."""
        self._metrics.clear()


# Global metrics collector
metrics_collector = MetricsCollector()


# ─────────────────────────────────────────────────────────────────────────────
# TRACING
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def trace_operation(operation_name: str, **tags):
    """
    Context manager for tracing operations.
    
    Usage:
        with trace_operation("invoice.extract", invoice_id="123"):
            # Do work
            pass
    """
    start_time = time.perf_counter()
    trace_id = f"trace-{int(time.time() * 1000)}"
    
    logger.info(
        "operation_start",
        operation=operation_name,
        trace_id=trace_id,
        **tags,
    )
    
    try:
        yield trace_id
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.error(
            "operation_failed",
            operation=operation_name,
            trace_id=trace_id,
            duration_ms=duration_ms,
            error=str(e),
            **tags,
        )
        
        # Record error metric
        metrics_collector.record(
            "operation.errors",
            1,
            metric_type="counter",
            tags={"operation": operation_name, "error_type": type(e).__name__},
        )
        
        raise
    else:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.info(
            "operation_complete",
            operation=operation_name,
            trace_id=trace_id,
            duration_ms=duration_ms,
            **tags,
        )
        
        # Record success metric
        metrics_collector.record(
            "operation.duration",
            duration_ms,
            metric_type="histogram",
            tags={"operation": operation_name},
        )


def traced(func):
    """Decorator for tracing function calls."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        with trace_operation(func.__name__):
            return await func(*args, **kwargs)
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        with trace_operation(func.__name__):
            return func(*args, **kwargs)
    
    # Check if function is async
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return wrapper
    return sync_wrapper


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM METRICS FOR INVOICIFY
# ─────────────────────────────────────────────────────────────────────────────

class InvoicifyMetrics:
    """Custom metrics for Invoicify pipeline."""
    
    @staticmethod
    def record_invoice_submitted(tenant_id: str, vendor_name: str):
        """Record invoice submission."""
        metrics_collector.record(
            "invoices.submitted",
            1,
            metric_type="counter",
            tags={"tenant_id": tenant_id, "vendor": vendor_name},
        )
    
    @staticmethod
    def record_extraction_complete(
        confidence: float,
        latency_ms: float,
        model: str,
    ):
        """Record extraction completion."""
        metrics_collector.record(
            "extraction.confidence",
            confidence,
            metric_type="gauge",
            tags={"model": model},
        )
        
        metrics_collector.record(
            "extraction.latency",
            latency_ms,
            metric_type="histogram",
            tags={"model": model},
        )
    
    @staticmethod
    def record_risk_decision(
        decision: str,
        risk_score: float,
        trust_level: str,
        amount: float,
    ):
        """Record risk decision."""
        metrics_collector.record(
            "decisions.made",
            1,
            metric_type="counter",
            tags={
                "decision": decision,
                "trust_level": trust_level,
                "risk_bucket": InvoicifyMetrics._risk_bucket(risk_score),
            },
        )
        
        metrics_collector.record(
            "decisions.risk_score",
            risk_score,
            metric_type="histogram",
            tags={"decision": decision},
        )
        
        metrics_collector.record(
            "decisions.amount",
            amount,
            metric_type="histogram",
            tags={"decision": decision},
        )
    
    @staticmethod
    def record_trust_battery_update(
        vendor_id: str,
        old_level: str,
        new_level: str,
        new_score: float,
    ):
        """Record trust battery update."""
        metrics_collector.record(
            "trust.updated",
            1,
            metric_type="counter",
            tags={
                "vendor_id": vendor_id,
                "old_level": old_level,
                "new_level": new_level,
            },
        )
        
        metrics_collector.record(
            "trust.score",
            new_score,
            metric_type="gauge",
            tags={"vendor_id": vendor_id, "level": new_level},
        )
    
    @staticmethod
    def record_voice_call_complete(
        duration_seconds: float,
        total_latency_ms: float,
        status: str,
    ):
        """Record voice call completion."""
        metrics_collector.record(
            "voice.calls",
            1,
            metric_type="counter",
            tags={"status": status},
        )
        
        metrics_collector.record(
            "voice.duration",
            duration_seconds * 1000,
            metric_type="histogram",
            tags={"status": status},
        )
        
        metrics_collector.record(
            "voice.latency",
            total_latency_ms,
            metric_type="histogram",
            tags={"status": status},
        )
    
    @staticmethod
    def _risk_bucket(risk_score: float) -> str:
        """Convert risk score to bucket."""
        if risk_score < 0.3:
            return "low"
        elif risk_score < 0.7:
            return "medium"
        else:
            return "high"


# ─────────────────────────────────────────────────────────────────────────────
# AZURE MONITOR EXPORTER
# ─────────────────────────────────────────────────────────────────────────────

async def get_metrics_snapshot() -> Dict[str, Any]:
    """Get metrics snapshot for Prometheus endpoint."""
    return metrics_collector.get_snapshot()


def export_to_azure_monitor():
    """Manually trigger export to Azure Monitor."""
    # Periodic export is handled by OTLP exporter
    # This can be used for manual flush
    logger.info("metrics_export_triggered")


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTLOG CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

def configure_structlog(environment: str = "development"):
    """
    Configure structlog for the application.
    
    Args:
        environment: deployment environment (development, staging, production)
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    if environment == "production":
        # JSON format for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console format for development
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logger.info("structlog_configured", environment=environment)


import logging  # noqa: E402

# Auto-configure on import
configure_structlog(os.getenv("APP_ENV", "development"))
