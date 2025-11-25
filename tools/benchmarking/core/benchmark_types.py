"""
Core data types and models for benchmarking operations.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from dataclasses import dataclass, field
from uuid import UUID


class BenchmarkType(Enum):
    """Types of benchmarking operations."""
    PERFORMANCE = "performance"
    LOAD_TEST = "load_test"
    PROFILING = "profiling"
    COMPARISON = "comparison"
    MONITORING = "monitoring"


class MetricCategory(Enum):
    """Categories of performance metrics."""
    THROUGHPUT = "throughput"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    RESOURCE_USAGE = "resource_usage"
    AVAILABILITY = "availability"
    QUALITY = "quality"


class PerformanceTier(Enum):
    """Performance tier classifications."""
    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class PerformanceMetric:
    """Individual performance metric measurement."""
    name: str
    category: MetricCategory
    value: float
    unit: str
    timestamp: datetime
    tier: Optional[PerformanceTier] = None
    threshold_target: Optional[float] = None
    threshold_critical: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Base result type for all benchmarking operations."""
    id: UUID
    benchmark_type: BenchmarkType
    timestamp: datetime
    duration_seconds: float
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfilingResult(BenchmarkResult):
    """Results from performance profiling operations."""
    cpu_profile_path: Optional[str] = None
    memory_profile_path: Optional[str] = None
    flame_graph_path: Optional[str] = None
    memory_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    cpu_usage_samples: List[float] = field(default_factory=list)
    memory_usage_samples: List[float] = field(default_factory=list)
    io_stats: Dict[str, Any] = field(default_factory=dict)
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LoadTestResult(BenchmarkResult):
    """Results from load testing operations."""
    requests_total: int = 0
    requests_successful: int = 0
    requests_failed: int = 0
    avg_response_time_ms: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    requests_per_second: float = 0.0
    throughput_bytes_per_second: float = 0.0
    error_rate: float = 0.0
    concurrent_users: int = 0
    test_duration_seconds: float = 0.0
    response_time_samples: List[float] = field(default_factory=list)
    error_samples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ComparisonResult(BenchmarkResult):
    """Results from industry comparison operations."""
    industry_average: Dict[str, float] = field(default_factory=dict)
    industry_top_percentile: Dict[str, float] = field(default_factory=dict)
    our_metrics: Dict[str, float] = field(default_factory=dict)
    percentile_rankings: Dict[str, float] = field(default_factory=dict)
    performance_gaps: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    competitive_analysis: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSuite:
    """Complete benchmark suite execution results."""
    suite_id: UUID
    timestamp: datetime
    environment: str
    system_info: Dict[str, Any]
    profiling_result: Optional[ProfilingResult] = None
    load_test_result: Optional[LoadTestResult] = None
    comparison_result: Optional[ComparisonResult] = None
    overall_score: float = 0.0
    grade: PerformanceTier = PerformanceTier.AVERAGE
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    executive_summary: str = ""


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark operations."""
    # Environment settings
    environment: str = "development"
    api_base_url: str = "http://localhost:8000"
    database_url: str = ""

    # Load testing settings
    load_test_duration_seconds: int = 300  # 5 minutes
    load_test_virtual_users: int = 10
    load_test_ramp_up_seconds: int = 30

    # Profiling settings
    profiling_duration_seconds: int = 120  # 2 minutes
    profiling_sampling_rate: float = 100.0  # Hz
    memory_profiling_enabled: bool = True
    cpu_profiling_enabled: bool = True

    # Monitoring settings
    monitoring_interval_seconds: int = 5
    monitoring_duration_seconds: int = 300

    # Comparison settings
    industry_benchmarks_enabled: bool = True
    comparison_industry: str = "fintech_ap_automation"

    # Reporting settings
    report_format: str = "json"  # json, html, pdf
    include_charts: bool = True
    save_raw_data: bool = True

    # Threshold settings
    response_time_threshold_ms: float = 500.0
    error_rate_threshold: float = 0.01  # 1%
    cpu_usage_threshold: float = 0.8  # 80%
    memory_usage_threshold: float = 0.85  # 85%