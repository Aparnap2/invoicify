"""
Performance Benchmarking Tools for AP Intake & Validation System

This comprehensive benchmarking suite provides:

1. **Performance Profiling** - CPU, memory, I/O profiling with flame graphs
2. **Load Testing** - Automated load testing with k6 integration
3. **Real-time Monitoring** - Live performance dashboards and alerting
4. **Industry Comparison** - Performance benchmarking against industry standards
5. **Automated Reporting** - Scheduled benchmark reports and insights

Usage:
    from tools.benchmarking import BenchmarkSuite

    benchmark = BenchmarkSuite()
    results = await benchmark.run_comprehensive_benchmark()

    # Generate report
    report = await benchmark.generate_report(results)
"""

from .profiling.performance_profiler import PerformanceProfiler
from .load_testing.load_tester import LoadTester
from .monitoring.performance_monitor import PerformanceMonitor
from .reporting.benchmark_reporter import BenchmarkReporter
from .core.benchmark_suite import BenchmarkSuite

__version__ = "1.0.0"
__all__ = [
    "PerformanceProfiler",
    "LoadTester",
    "PerformanceMonitor",
    "BenchmarkReporter",
    "BenchmarkSuite",
]