"""
Main benchmark suite that orchestrates all benchmarking components.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from .benchmark_config import BenchmarkConfig
from .benchmark_types import (
    BenchmarkSuite as BenchmarkSuiteResult,
    BenchmarkType,
    PerformanceTier
)
from ..profiling.performance_profiler import PerformanceProfiler
from ..load_testing.load_tester import LoadTester
from ..monitoring.performance_dashboard import PerformanceMonitor
from ..reporting.benchmark_reporter import BenchmarkReporter

logger = logging.getLogger(__name__)


class BenchmarkSuite:
    """Comprehensive benchmark suite for AP Intake system performance analysis."""

    def __init__(self, config: Optional[BenchmarkConfig] = None):
        """Initialize benchmark suite with configuration."""
        self.config = config or BenchmarkConfig()
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.profiler = PerformanceProfiler(self.config)
        self.load_tester = LoadTester(self.config)
        self.monitor = PerformanceMonitor()
        self.reporter = BenchmarkReporter(self.config)

    async def run_comprehensive_benchmark(
        self,
        include_profiling: bool = True,
        include_load_testing: bool = True,
        include_comparison: bool = True,
        test_name: str = "comprehensive_benchmark"
    ) -> BenchmarkSuiteResult:
        """
        Run comprehensive benchmark suite.

        Args:
            include_profiling: Run performance profiling
            include_load_testing: Run load testing
            include_comparison: Run industry comparison
            test_name: Name for this benchmark run

        Returns:
            BenchmarkSuiteResult with comprehensive analysis
        """
        start_time = datetime.now(timezone.utc)
        suite_id = uuid4()

        self.logger.info(f"Starting comprehensive benchmark: {test_name}")

        try:
            # Get system information
            system_info = await self._collect_system_info()

            # Initialize result container
            result = BenchmarkSuiteResult(
                suite_id=suite_id,
                timestamp=start_time,
                environment=self.config.environment,
                system_info=system_info
            )

            # Run profiling if requested
            if include_profiling:
                self.logger.info("Running performance profiling...")
                result.profiling_result = await self.profiler.profile_system(
                    duration_seconds=self.config.profiling_duration_seconds
                )

            # Run load testing if requested
            if include_load_testing:
                self.logger.info("Running load testing...")
                result.load_test_result = await self.load_tester.run_load_test(
                    test_name=f"{test_name}_load_test",
                    virtual_users=self.config.load_test_virtual_users,
                    duration_seconds=self.config.load_test_duration_seconds
                )

            # Run industry comparison if requested
            if include_comparison:
                self.logger.info("Running industry comparison...")
                result.comparison_result = await self._run_industry_comparison()

            # Calculate overall score and grade
            result = await self._calculate_overall_metrics(result)

            # Generate recommendations
            result.key_findings = self._generate_key_findings(result)
            result.recommendations = self._generate_recommendations(result)
            result.executive_summary = self._generate_executive_summary(result)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.info(f"Comprehensive benchmark completed in {duration:.1f}s")

            return result

        except Exception as e:
            self.logger.error(f"Comprehensive benchmark failed: {e}")
            raise

    async def run_performance_profiling(self) -> BenchmarkSuiteResult:
        """Run only performance profiling benchmark."""
        start_time = datetime.now(timezone.utc)
        suite_id = uuid4()

        system_info = await self._collect_system_info()

        result = BenchmarkSuiteResult(
            suite_id=suite_id,
            timestamp=start_time,
            environment=self.config.environment,
            system_info=system_info
        )

        self.logger.info("Running performance profiling benchmark...")
        result.profiling_result = await self.profiler.profile_system()

        # Calculate metrics based on profiling
        result = await self._calculate_overall_metrics(result)
        result.key_findings = self._generate_key_findings(result)
        result.recommendations = self._generate_recommendations(result)

        return result

    async def run_load_testing(
        self,
        test_type: str = "standard"
    ) -> BenchmarkSuiteResult:
        """Run load testing benchmark."""
        start_time = datetime.now(timezone.utc)
        suite_id = uuid4()

        system_info = await self._collect_system_info()

        result = BenchmarkSuiteResult(
            suite_id=suite_id,
            timestamp=start_time,
            environment=self.config.environment,
            system_info=system_info
        )

        if test_type == "standard":
            self.logger.info("Running standard load test...")
            result.load_test_result = await self.load_tester.run_load_test()
        elif test_type == "stress":
            self.logger.info("Running stress test...")
            stress_results = await self.load_tester.run_stress_test()
            # Use the highest stress level that passed
            result.load_test_result = list(stress_results.values())[-1] if stress_results else None
        elif test_type == "endurance":
            self.logger.info("Running endurance test...")
            result.load_test_result = await self.load_tester.run_endurance_test()

        # Calculate metrics based on load testing
        result = await self._calculate_overall_metrics(result)
        result.key_findings = self._generate_key_findings(result)
        result.recommendations = self._generate_recommendations(result)

        return result

    async def _collect_system_info(self) -> Dict[str, Any]:
        """Collect system information for benchmarking."""
        try:
            import platform
            import psutil

            system_info = {
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "python_version": platform.python_version(),
                },
                "hardware": {
                    "cpu_count": psutil.cpu_count(),
                    "cpu_count_logical": psutil.cpu_count(logical=True),
                    "memory_total": psutil.virtual_memory().total,
                    "memory_available": psutil.virtual_memory().available,
                },
                "benchmark_config": {
                    "environment": self.config.environment,
                    "api_base_url": self.config.api_base_url,
                    "profiling_enabled": self.config.cpu_profiling_enabled or self.config.memory_profiling_enabled,
                    "load_test_users": self.config.load_test_virtual_users,
                    "load_test_duration": self.config.load_test_duration_seconds,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Add disk information
            try:
                disk_usage = psutil.disk_usage('/')
                system_info["hardware"]["disk_total"] = disk_usage.total
                system_info["hardware"]["disk_free"] = disk_usage.free
            except Exception:
                pass

            return system_info

        except Exception as e:
            self.logger.error(f"Failed to collect system info: {e}")
            return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}

    async def _run_industry_comparison(self):
        """Run industry comparison benchmark."""
        try:
            # TODO: Implement industry comparison
            # This would compare current performance against industry benchmarks
            self.logger.info("Industry comparison not yet implemented")
            return None
        except Exception as e:
            self.logger.error(f"Industry comparison failed: {e}")
            return None

    async def _calculate_overall_metrics(self, result: BenchmarkSuiteResult) -> BenchmarkSuiteResult:
        """Calculate overall performance metrics from individual results."""
        scores = []

        # Calculate profiling score
        if result.profiling_result and result.profiling_result.success:
            profiling_score = self._calculate_profiling_score(result.profiling_result)
            scores.append(("profiling", profiling_score))

        # Calculate load testing score
        if result.load_test_result and result.load_test_result.success:
            load_test_score = self._calculate_load_test_score(result.load_test_result)
            scores.append(("load_test", load_test_score))

        # Calculate comparison score
        if result.comparison_result and result.comparison_result.success:
            comparison_score = self._calculate_comparison_score(result.comparison_result)
            scores.append(("comparison", comparison_score))

        # Calculate overall score
        if scores:
            result.overall_score = sum(score for _, score in scores) / len(scores)
        else:
            result.overall_score = 0.0

        # Determine performance tier
        if result.overall_score >= 90:
            result.grade = PerformanceTier.EXCELLENT
        elif result.overall_score >= 75:
            result.grade = PerformanceTier.GOOD
        elif result.overall_score >= 60:
            result.grade = PerformanceTier.AVERAGE
        elif result.overall_score >= 40:
            result.grade = PerformanceTier.POOR
        else:
            result.grade = PerformanceTier.CRITICAL

        return result

    def _calculate_profiling_score(self, profiling_result) -> float:
        """Calculate score from profiling results."""
        score = 100.0

        # CPU usage scoring
        if profiling_result.cpu_usage_samples:
            avg_cpu = sum(profiling_result.cpu_usage_samples) / len(profiling_result.cpu_usage_samples)
            if avg_cpu > 80:
                score -= (avg_cpu - 80) * 2
            elif avg_cpu > 60:
                score -= (avg_cpu - 60)

        # Memory usage scoring
        if profiling_result.memory_usage_samples:
            avg_memory = sum(profiling_result.memory_usage_samples) / len(profiling_result.memory_usage_samples)
            if avg_memory > 85:
                score -= (avg_memory - 85) * 3
            elif avg_memory > 70:
                score -= (avg_memory - 70) * 1.5

        # Bottleneck penalties
        for bottleneck in profiling_result.bottlenecks:
            if bottleneck.get("severity") == "high":
                score -= 15
            elif bottleneck.get("severity") == "medium":
                score -= 8

        return max(0.0, min(100.0, score))

    def _calculate_load_test_score(self, load_test_result) -> float:
        """Calculate score from load testing results."""
        score = 100.0

        # Response time scoring
        if load_test_result.p95_response_time_ms > self.config.response_time_threshold_ms:
            penalty = (load_test_result.p95_response_time_ms - self.config.response_time_threshold_ms) / 10
            score -= penalty

        # Error rate scoring
        if load_test_result.error_rate > self.config.error_rate_threshold:
            penalty = (load_test_result.error_rate - self.config.error_rate_threshold) * 1000
            score -= penalty

        # Throughput scoring (bonus points for high throughput)
        if load_test_result.requests_per_second > 1000:
            score += min(10, (load_test_result.requests_per_second - 1000) / 100)

        return max(0.0, min(110.0, score))  # Allow 10% bonus

    def _calculate_comparison_score(self, comparison_result) -> float:
        """Calculate score from industry comparison."""
        # TODO: Implement comparison scoring based on industry benchmarks
        return 85.0  # Placeholder

    def _generate_key_findings(self, result: BenchmarkSuiteResult) -> List[str]:
        """Generate key findings from benchmark results."""
        findings = []

        if result.profiling_result:
            if result.profiling_result.cpu_usage_samples:
                avg_cpu = sum(result.profiling_result.cpu_usage_samples) / len(result.profiling_result.cpu_usage_samples)
                if avg_cpu > 80:
                    findings.append(f"High CPU usage detected: {avg_cpu:.1f}% average")
                elif avg_cpu < 20:
                    findings.append(f"Low CPU utilization: {avg_cpu:.1f}% average (potential over-provisioning)")

            if result.profiling_result.bottlenecks:
                high_severity_bottlenecks = [b for b in result.profiling_result.bottlenecks if b.get("severity") == "high"]
                if high_severity_bottlenecks:
                    findings.append(f"Identified {len(high_severity_bottlenecks)} critical performance bottlenecks")

        if result.load_test_result:
            if result.load_test_result.p95_response_time_ms > 500:
                findings.append(f"P95 response time exceeds SLA: {result.load_test_result.p95_response_time_ms:.0f}ms")
            if result.load_test_result.error_rate > 0.01:
                findings.append(f"High error rate during load test: {result.load_test_result.error_rate:.1%}")
            if result.load_test_result.requests_per_second < 100:
                findings.append(f"Low throughput: {result.load_test_result.requests_per_second:.0f} requests/second")

        findings.append(f"Overall performance grade: {result.grade.value.upper()}")
        findings.append(f"Performance score: {result.overall_score:.1f}/100")

        return findings

    def _generate_recommendations(self, result: BenchmarkSuiteResult) -> List[str]:
        """Generate recommendations based on benchmark results."""
        recommendations = []

        if result.profiling_result:
            for bottleneck in result.profiling_result.bottlenecks:
                if bottleneck.get("recommendation"):
                    recommendations.append(bottleneck["recommendation"])

            if result.profiling_result.cpu_usage_samples:
                avg_cpu = sum(result.profiling_result.cpu_usage_samples) / len(result.profiling_result.cpu_usage_samples)
                if avg_cpu > 80:
                    recommendations.append("Consider horizontal scaling or optimizing CPU-intensive operations")
                elif avg_cpu < 20:
                    recommendations.append("Optimize resource allocation to reduce costs")

        if result.load_test_result:
            if result.load_test_result.p95_response_time_ms > 500:
                recommendations.append("Implement caching strategies to reduce response times")
            if result.load_test_result.error_rate > 0.01:
                recommendations.append("Investigate and fix error conditions to improve reliability")

        # General recommendations based on grade
        if result.grade == PerformanceTier.POOR:
            recommendations.append("Comprehensive performance optimization recommended")
        elif result.grade == PerformanceTier.AVERAGE:
            recommendations.append("Focus on identified bottlenecks for improvement")
        elif result.grade == PerformanceTier.GOOD:
            recommendations.append("Continue monitoring and optimize remaining bottlenecks")
        elif result.grade == PerformanceTier.EXCELLENT:
            recommendations.append("Maintain current performance levels and monitor for regression")

        return recommendations

    def _generate_executive_summary(self, result: BenchmarkSuiteResult) -> str:
        """Generate executive summary of benchmark results."""
        summary_parts = []

        # Overall assessment
        if result.grade == PerformanceTier.EXCELLENT:
            summary_parts.append("System performance is excellent and meets all requirements.")
        elif result.grade == PerformanceTier.GOOD:
            summary_parts.append("System performance is good with room for improvement.")
        elif result.grade == PerformanceTier.AVERAGE:
            summary_parts.append("System performance meets basic requirements but needs optimization.")
        elif result.grade == PerformanceTier.POOR:
            summary_parts.append("System performance requires immediate attention and optimization.")
        else:
            summary_parts.append("System performance is critical and requires urgent intervention.")

        # Key metrics
        if result.load_test_result:
            summary_parts.append(
                f"Load testing achieved {result.load_test_result.requests_per_second:.0f} requests/second "
                f"with {result.load_test_result.p95_response_time_ms:.0f}ms P95 response time."
            )

        if result.profiling_result and result.profiling_result.bottlenecks:
            summary_parts.append(
                f"Identified {len(result.profiling_result.bottlenecks)} performance bottlenecks requiring attention."
            )

        # Recommendations count
        if result.recommendations:
            summary_parts.append(f"{len(result.recommendations)} key recommendations provided for optimization.")

        return " ".join(summary_parts)

    async def save_results(self, result: BenchmarkSuiteResult, format: str = "json") -> str:
        """Save benchmark results to file."""
        return await self.reporter.save_results(result, format)

    async def generate_report(self, result: BenchmarkSuiteResult, format: str = "html") -> str:
        """Generate comprehensive benchmark report."""
        return await self.reporter.generate_report(result, format)