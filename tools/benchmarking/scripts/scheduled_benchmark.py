#!/usr/bin/env python3
"""
Scheduled benchmark execution script for automated performance monitoring.

This script runs benchmarks on a schedule and sends notifications/alerts
based on performance degradation.

Usage:
    python tools/benchmarking/scripts/scheduled_benchmark.py [options]
"""

import asyncio
import argparse
import json
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tools.benchmarking.core.benchmark_suite import BenchmarkSuite
from tools.benchmarking.core.benchmark_config import BenchmarkConfig, load_config


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScheduledBenchmark:
    """Automated scheduled benchmark execution."""

    def __init__(self, config: BenchmarkConfig):
        """Initialize scheduled benchmark with configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.suite = BenchmarkSuite(config)
        self.previous_results = []
        self.max_history = 10  # Keep last 10 benchmark results for trend analysis

    async def run_scheduled_benchmark(self, benchmark_type: str = "comprehensive"):
        """Run scheduled benchmark and compare with previous results."""
        self.logger.info(f"Running scheduled {benchmark_type} benchmark")

        try:
            # Run benchmark based on type
            if benchmark_type == "comprehensive":
                result = await self.suite.run_comprehensive_benchmark(
                    include_profiling=True,
                    include_load_testing=True,
                    include_comparison=False,  # Skip comparison for scheduled runs
                    test_name=f"scheduled_comprehensive_{datetime.now().strftime('%Y%m%d_%H%M')}"
                )
            elif benchmark_type == "load_test":
                result = await self.suite.run_load_testing(test_type="standard")
            elif benchmark_type == "profiling":
                result = await self.suite.run_performance_profiling()
            else:
                raise ValueError(f"Unknown benchmark type: {benchmark_type}")

            # Store result for trend analysis
            self.previous_results.append(result)
            if len(self.previous_results) > self.max_history:
                self.previous_results.pop(0)

            # Analyze performance trends
            analysis = await self.analyze_performance_trends(result)

            # Generate and save report
            report_path = await self.suite.generate_report(result, format="json")
            self.logger.info(f"Benchmark report saved to: {report_path}")

            # Send alerts if needed
            await self.send_performance_alerts(result, analysis)

            return result, analysis

        except Exception as e:
            self.logger.error(f"Scheduled benchmark failed: {e}")
            raise

    async def analyze_performance_trends(self, current_result):
        """Analyze performance trends compared to previous results."""
        if len(self.previous_results) < 2:
            return {"trend": "insufficient_data", "changes": []}

        previous_result = self.previous_results[-2]  # Compare with immediate previous result

        analysis = {
            "trend": "stable",
            "changes": [],
            "alerts": []
        }

        # Score trend analysis
        score_change = current_result.overall_score - previous_result.overall_score
        if abs(score_change) > 5:  # Significant change
            trend = "improving" if score_change > 0 else "degrading"
            analysis["changes"].append({
                "metric": "overall_score",
                "trend": trend,
                "change": score_change,
                "previous": previous_result.overall_score,
                "current": current_result.overall_score
            })

        # Load test trend analysis
        if (current_result.load_test_result and previous_result.load_test_result and
            current_result.load_test_result.success and previous_result.load_test_result.success):

            rps_change = current_result.load_test_result.requests_per_second - previous_result.load_test_result.requests_per_second
            response_time_change = current_result.load_test_result.p95_response_time_ms - previous_result.load_test_result.p95_response_time_ms

            if abs(rps_change) > 50:  # Significant RPS change
                analysis["changes"].append({
                    "metric": "requests_per_second",
                    "trend": "improving" if rps_change > 0 else "degrading",
                    "change": rps_change,
                    "previous": previous_result.load_test_result.requests_per_second,
                    "current": current_result.load_test_result.requests_per_second
                })

            if abs(response_time_change) > 50:  # Significant response time change
                analysis["changes"].append({
                    "metric": "p95_response_time",
                    "trend": "improving" if response_time_change < 0 else "degrading",
                    "change": response_time_change,
                    "previous": previous_result.load_test_result.p95_response_time_ms,
                    "current": current_result.load_test_result.p95_response_time_ms
                })

        # Determine overall trend
        degrading_changes = [c for c in analysis["changes"] if c["trend"] == "degrading"]
        if len(degrading_changes) > len(analysis["changes"]) / 2:
            analysis["trend"] = "degrading"
        elif any(c["trend"] == "improving" for c in analysis["changes"]):
            analysis["trend"] = "improving"

        return analysis

    async def send_performance_alerts(self, result, analysis):
        """Send performance alerts based on analysis."""
        alerts = []

        # Critical performance degradation
        if result.grade.value in ["poor", "critical"]:
            alerts.append({
                "severity": "critical",
                "title": "Critical Performance Degradation",
                "message": f"Performance grade is {result.grade.value.upper()} with score {result.overall_score:.1f}/100"
            })

        # Performance trend alerts
        if analysis["trend"] == "degrading":
            alerts.append({
                "severity": "warning",
                "title": "Performance Degradation Detected",
                "message": "Performance metrics show degrading trend compared to previous benchmarks"
            })

        # Load test specific alerts
        if (result.load_test_result and result.load_test_result.success):
            if result.load_test_result.error_rate > 0.05:  # 5% error rate
                alerts.append({
                    "severity": "critical",
                    "title": "High Error Rate in Load Test",
                    "message": f"Error rate: {result.load_test_result.error_rate:.2%}"
                })

            if result.load_test_result.p95_response_time_ms > 1000:  # 1 second
                alerts.append({
                    "severity": "warning",
                    "title": "High Response Times",
                    "message": f"P95 response time: {result.load_test_result.p95_response_time_ms:.0f}ms"
                })

        # Send alerts
        for alert in alerts:
            await self.send_alert(alert)

    async def send_alert(self, alert):
        """Send performance alert (placeholder implementation)."""
        self.logger.warning(f"ALERT: {alert['severity'].upper()} - {alert['title']}: {alert['message']}")

        # TODO: Implement actual alert sending
        # - Email notifications
        # - Slack messages
        # - PagerDuty integration
        # - etc.


async def run_daily_benchmark():
    """Run daily scheduled benchmark."""
    logger.info("Starting daily scheduled benchmark")

    config = load_config(environment="production")
    scheduled_benchmark = ScheduledBenchmark(config)

    try:
        result, analysis = await scheduled_benchmark.run_scheduled_benchmark("comprehensive")
        logger.info(f"Daily benchmark completed - Score: {result.overall_score:.1f}/100, Grade: {result.grade.value}")
    except Exception as e:
        logger.error(f"Daily benchmark failed: {e}")


async def run_hourly_health_check():
    """Run hourly health check benchmark."""
    logger.info("Starting hourly health check")

    config = load_config(environment="production")
    scheduled_benchmark = ScheduledBenchmark(config)

    try:
        result, analysis = await scheduled_benchmark.run_scheduled_benchmark("load_test")
        logger.info(f"Health check completed - RPS: {result.load_test_result.requests_per_second:.1f}")
    except Exception as e:
        logger.error(f"Health check failed: {e}")


async def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="AP Intake Scheduled Benchmark Runner")
    parser.add_argument("--type", choices=["daily", "hourly", "manual"], default="manual",
                       help="Type of scheduled benchmark to run")
    parser.add_argument("--benchmark-type", choices=["comprehensive", "load_test", "profiling"],
                       default="comprehensive", help="Type of benchmark to run")
    parser.add_argument("--environment", default="production", help="Environment to benchmark")
    parser.add_argument("--config", help="Path to configuration file")

    args = parser.parse_args()

    try:
        if args.type == "daily":
            await run_daily_benchmark()
        elif args.type == "hourly":
            await run_hourly_health_check()
        else:
            # Manual execution
            config = load_config(args.config, args.environment)
            scheduled_benchmark = ScheduledBenchmark(config)

            result, analysis = await scheduled_benchmark.run_scheduled_benchmark(args.benchmark_type)
            logger.info(f"Manual benchmark completed - Score: {result.overall_score:.1f}/100")

            # Print summary
            print(f"Benchmark completed successfully!")
            print(f"Overall Score: {result.overall_score:.1f}/100")
            print(f"Grade: {result.grade.value}")
            print(f"Trend: {analysis['trend']}")

            if analysis['changes']:
                print("\nSignificant Changes:")
                for change in analysis['changes']:
                    print(f"  {change['metric']}: {change['trend']} ({change['change']:+.1f})")

    except Exception as e:
        logger.error(f"Scheduled benchmark execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())