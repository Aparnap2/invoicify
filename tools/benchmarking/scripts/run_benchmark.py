#!/usr/bin/env python3
"""
Automated benchmark execution script for AP Intake system.

This script provides a command-line interface for running comprehensive
performance benchmarks and generating reports.

Usage:
    python tools/benchmarking/scripts/run_benchmark.py [options]

Examples:
    # Run comprehensive benchmark
    python run_benchmark.py --comprehensive

    # Run only load testing
    python run_benchmark.py --load-test --users 50 --duration 300

    # Run profiling only
    python run_benchmark.py --profile --duration 120

    # Run stress test
    python run_benchmark.py --stress-test --max-users 200
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
from tools.benchmarking.monitoring.performance_dashboard import get_performance_monitor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main benchmark execution function."""
    parser = argparse.ArgumentParser(description="AP Intake Performance Benchmark Suite")

    # Benchmark type options
    parser.add_argument("--comprehensive", action="store_true",
                       help="Run comprehensive benchmark suite")
    parser.add_argument("--profile", action="store_true",
                       help="Run performance profiling only")
    parser.add_argument("--load-test", action="store_true",
                       help="Run load testing only")
    parser.add_argument("--stress-test", action="store_true",
                       help="Run stress test")
    parser.add_argument("--monitor", action="store_true",
                       help="Start real-time monitoring dashboard")

    # Configuration options
    parser.add_argument("--config", type=str,
                       help="Path to benchmark configuration file")
    parser.add_argument("--environment", type=str, default="development",
                       help="Environment to benchmark")
    parser.add_argument("--api-url", type=str,
                       help="API base URL for testing")

    # Load testing options
    parser.add_argument("--users", type=int,
                       help="Number of concurrent users for load test")
    parser.add_argument("--duration", type=int,
                       help="Duration in seconds for tests")
    parser.add_argument("--ramp-up", type=int,
                       help="Ramp-up period in seconds")

    # Profiling options
    parser.add_argument("--profile-duration", type=int,
                       help="Duration in seconds for profiling")
    parser.add_argument("--cpu-only", action="store_true",
                       help="Enable CPU profiling only")
    parser.add_argument("--memory-only", action="store_true",
                       help="Enable memory profiling only")

    # Output options
    parser.add_argument("--output-format", type=str, choices=["json", "html", "pdf", "markdown"],
                       default="html", help="Report output format")
    parser.add_argument("--output-dir", type=str,
                       help="Output directory for results")
    parser.add_argument("--save-results", action="store_true",
                       help="Save raw results data")
    parser.add_argument("--no-charts", action="store_true",
                       help="Disable chart generation")

    # Monitoring options
    parser.add_argument("--monitor-port", type=int, default=8765,
                       help="Port for monitoring dashboard")
    parser.add_argument("--monitor-host", type=str, default="localhost",
                       help="Host for monitoring dashboard")

    args = parser.parse_args()

    # Validate arguments
    if not any([args.comprehensive, args.profile, args.load_test, args.stress_test, args.monitor]):
        parser.error("Must specify at least one benchmark type or monitoring")

    try:
        # Load configuration
        config = load_config(args.config, args.environment)

        # Override config with command line arguments
        if args.api_url:
            config.api_base_url = args.api_url
        if args.users:
            config.load_test_virtual_users = args.users
        if args.duration:
            config.load_test_duration_seconds = args.duration
            config.profiling_duration_seconds = args.duration
        if args.profile_duration:
            config.profiling_duration_seconds = args.profile_duration
        if args.ramp_up:
            config.load_test_ramp_up_seconds = args.ramp_up
        if args.cpu_only:
            config.memory_profiling_enabled = False
        if args.memory_only:
            config.cpu_profiling_enabled = False
        if args.no_charts:
            config.include_charts = False

        logger.info(f"Starting benchmark suite for environment: {config.environment}")
        logger.info(f"API URL: {config.api_base_url}")

        # Initialize benchmark suite
        suite = BenchmarkSuite(config)

        # Handle different execution modes
        if args.monitor:
            await run_monitoring_mode(args, suite)
        elif args.comprehensive:
            await run_comprehensive_benchmark(args, suite)
        elif args.profile:
            await run_profiling_benchmark(args, suite)
        elif args.load_test:
            await run_load_test_benchmark(args, suite)
        elif args.stress_test:
            await run_stress_test_benchmark(args, suite)

    except KeyboardInterrupt:
        logger.info("Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)


async def run_monitoring_mode(args, suite):
    """Run real-time monitoring mode."""
    logger.info("Starting real-time monitoring dashboard...")

    monitor = get_performance_monitor()
    await monitor.start_monitoring(
        host=args.monitor_host,
        port=args.monitor_port
    )

    logger.info(f"Monitoring dashboard started at ws://{args.monitor_host}:{args.monitor_port}")
    logger.info("Press Ctrl+C to stop monitoring")

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    finally:
        await monitor.stop_monitoring()


async def run_comprehensive_benchmark(args, suite):
    """Run comprehensive benchmark suite."""
    logger.info("Running comprehensive benchmark suite...")

    result = await suite.run_comprehensive_benchmark(
        include_profiling=True,
        include_load_testing=True,
        include_comparison=True,
        test_name="comprehensive_benchmark"
    )

    await save_results_and_report(suite, result, args)


async def run_profiling_benchmark(args, suite):
    """Run profiling benchmark only."""
    logger.info("Running performance profiling benchmark...")

    result = await suite.run_performance_profiling()

    await save_results_and_report(suite, result, args)


async def run_load_test_benchmark(args, suite):
    """Run load testing benchmark only."""
    logger.info("Running load testing benchmark...")

    result = await suite.run_load_testing(test_type="standard")

    await save_results_and_report(suite, result, args)


async def run_stress_test_benchmark(args, suite):
    """Run stress test benchmark."""
    logger.info("Running stress test benchmark...")

    result = await suite.run_load_testing(test_type="stress")

    await save_results_and_report(suite, result, args)


async def save_results_and_report(suite, result, args):
    """Save results and generate reports."""
    logger.info("Saving results and generating reports...")

    # Save raw results if requested
    if args.save_results:
        results_path = await suite.save_results(result, format="json")
        logger.info(f"Results saved to: {results_path}")

    # Generate report
    report_path = await suite.generate_report(result, format=args.output_format)
    logger.info(f"Report generated: {report_path}")

    # Print summary
    print_summary(result)


def print_summary(result):
    """Print benchmark summary to console."""
    print("\n" + "="*60)
    print("BENCHMARK RESULTS SUMMARY")
    print("="*60)

    print(f"Overall Performance Grade: {result.grade.value.upper()}")
    print(f"Overall Score: {result.overall_score:.1f}/100")
    print(f"Environment: {result.environment}")
    print(f"Timestamp: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    if result.key_findings:
        print("\nKey Findings:")
        for i, finding in enumerate(result.key_findings, 1):
            print(f"  {i}. {finding}")

    if result.recommendations:
        print(f"\nRecommendations ({len(result.recommendations)}):")
        for i, rec in enumerate(result.recommendations, 1):
            print(f"  {i}. {rec}")

    # Performance details
    print("\nPerformance Details:")

    if result.profiling_result and result.profiling_result.success:
        avg_cpu = sum(result.profiling_result.cpu_usage_samples) / len(result.profiling_result.cpu_usage_samples) if result.profiling_result.cpu_usage_samples else 0
        avg_memory = sum(result.profiling_result.memory_usage_samples) / len(result.profiling_result.memory_usage_samples) if result.profiling_result.memory_usage_samples else 0
        print(f"  - Average CPU Usage: {avg_cpu:.1f}%")
        print(f"  - Average Memory Usage: {avg_memory:.1f}%")
        print(f"  - Bottlenecks Found: {len(result.profiling_result.bottlenecks)}")

    if result.load_test_result and result.load_test_result.success:
        print(f"  - Requests per Second: {result.load_test_result.requests_per_second:.1f}")
        print(f"  - P95 Response Time: {result.load_test_result.p95_response_time_ms:.0f}ms")
        print(f"  - Error Rate: {result.load_test_result.error_rate:.2%}")
        print(f"  - Total Requests: {result.load_test_result.requests_total:,}")

    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main())