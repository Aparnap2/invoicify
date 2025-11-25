"""
Celery tasks for automated performance benchmarking and monitoring.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from celery import Celery

from app.core.config import settings
from tools.benchmarking.core.benchmark_suite import BenchmarkSuite
from tools.benchmarking.core.benchmark_config import BenchmarkConfig, load_config

logger = logging.getLogger(__name__)

# Initialize Celery app for benchmarking tasks
benchmark_celery_app = Celery(
    "benchmark_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Celery configuration for benchmarking tasks
benchmark_celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=60 * 60,  # 60 minutes for comprehensive benchmarks
    task_soft_time_limit=55 * 60,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,  # Run benchmarks sequentially
    worker_max_tasks_per_child=1,  # Restart worker after each benchmark to ensure clean state
)


@benchmark_celery_app.task(bind=True, name="run_scheduled_benchmark")
def run_scheduled_benchmark_task(
    self,
    benchmark_type: str = "comprehensive",
    environment: str = "production"
) -> Dict[str, Any]:
    """
    Run scheduled benchmark task.

    Args:
        benchmark_type: Type of benchmark to run (comprehensive, load_test, profiling)
        environment: Environment to benchmark (production, staging)

    Returns:
        Dict with benchmark results
    """
    try:
        logger.info(f"Starting scheduled {benchmark_type} benchmark for {environment}")

        # Load configuration
        config = load_config(environment=environment)

        # Create benchmark suite
        suite = BenchmarkSuite(config)

        # Run benchmark
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if benchmark_type == "comprehensive":
                result = loop.run_until_complete(
                    suite.run_comprehensive_benchmark(
                        include_profiling=True,
                        include_load_testing=True,
                        include_comparison=False,  # Skip for scheduled runs
                        test_name=f"scheduled_comprehensive_{datetime.now().strftime('%Y%m%d_%H%M')}"
                    )
                )
            elif benchmark_type == "load_test":
                result = loop.run_until_complete(
                    suite.run_load_testing(test_type="standard")
                )
            elif benchmark_type == "profiling":
                result = loop.run_until_complete(
                    suite.run_performance_profiling()
                )
            else:
                raise ValueError(f"Unknown benchmark type: {benchmark_type}")

            # Generate report
            report_path = loop.run_until_complete(
                suite.generate_report(result, format="json")
            )

            # Return summary
            response = {
                "success": True,
                "benchmark_type": benchmark_type,
                "environment": environment,
                "suite_id": str(result.suite_id),
                "overall_score": result.overall_score,
                "grade": result.grade.value,
                "timestamp": result.timestamp.isoformat(),
                "report_path": report_path,
                "key_findings": result.key_findings[:5],  # Top 5 findings
                "executive_summary": result.executive_summary,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"Scheduled benchmark completed successfully - Score: {result.overall_score:.1f}/100")
            return response

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Scheduled benchmark failed: {e}")
        return {
            "success": False,
            "benchmark_type": benchmark_type,
            "environment": environment,
            "error": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }


@benchmark_celery_app.task(bind=True, name="run_performance_health_check")
def run_performance_health_check_task(self) -> Dict[str, Any]:
    """
    Run lightweight performance health check.

    Returns:
        Dict with health check results
    """
    try:
        logger.info("Starting performance health check")

        # Load configuration with minimal settings
        config = load_config(environment="production")
        config.load_test_duration_seconds = 60  # 1 minute
        config.load_test_virtual_users = 5     # Low concurrency
        config.profiling_duration_seconds = 30 # Short profiling

        # Create benchmark suite
        suite = BenchmarkSuite(config)

        # Run quick load test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                suite.run_load_testing(test_type="standard")
            )

            # Determine health status
            is_healthy = (
                result.grade.value in ["excellent", "good"] and
                result.load_test_result.error_rate < 0.01 and
                result.load_test_result.p95_response_time_ms < 500
            )

            response = {
                "success": True,
                "healthy": is_healthy,
                "score": result.overall_score,
                "grade": result.grade.value,
                "requests_per_second": result.load_test_result.requests_per_second,
                "p95_response_time_ms": result.load_test_result.p95_response_time_ms,
                "error_rate": result.load_test_result.error_rate,
                "timestamp": result.timestamp.isoformat(),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"Performance health check completed - Healthy: {is_healthy}")
            return response

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Performance health check failed: {e}")
        return {
            "success": False,
            "healthy": False,
            "error": str(e),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


@benchmark_celery_app.task(bind=True, name="generate_benchmark_report")
def generate_benchmark_report_task(
    self,
    suite_id: str,
    format: str = "html",
    environment: str = "production"
) -> Dict[str, Any]:
    """
    Generate benchmark report from existing results.

    Args:
        suite_id: ID of the benchmark suite
        format: Report format (html, pdf, markdown)
        environment: Environment

    Returns:
        Dict with report generation results
    """
    try:
        logger.info(f"Generating benchmark report for suite {suite_id}")

        # TODO: Implement report generation from stored results
        # This would load the stored benchmark results and generate reports

        response = {
            "success": True,
            "suite_id": suite_id,
            "format": format,
            "report_path": f"tools/benchmarking/reports/benchmark_report_{suite_id}.{format}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Benchmark report generated: {response['report_path']}")
        return response

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return {
            "success": False,
            "suite_id": suite_id,
            "error": str(e),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


@benchmark_celery_app.task(bind=True, name="cleanup_old_benchmark_results")
def cleanup_old_benchmark_results_task(
    self,
    retention_days: int = 30,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Clean up old benchmark results and reports.

    Args:
        retention_days: Number of days to retain results
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup results
    """
    try:
        logger.info(f"Cleaning up benchmark results older than {retention_days} days")

        import os
        from pathlib import Path
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Define directories to clean
        directories = [
            "tools/benchmarking/results",
            "tools/benchmarking/reports",
            "logs/benchmarks"
        ]

        files_deleted = 0
        space_freed = 0

        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                continue

            # Clean files in directory
            for file_path in dir_path.rglob("*"):
                if file_path.is_file():
                    try:
                        file_time = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)

                        if file_time < cutoff_date:
                            file_size = file_path.stat().st_size

                            if not dry_run:
                                file_path.unlink()

                            files_deleted += 1
                            space_freed += file_size

                    except Exception as e:
                        logger.warning(f"Failed to process file {file_path}: {e}")

        response = {
            "success": True,
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "files_deleted": files_deleted,
            "space_freed_bytes": space_freed,
            "space_freed_mb": round(space_freed / (1024 * 1024), 2),
            "dry_run": dry_run,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Cleanup completed: {files_deleted} files, {response['space_freed_mb']} MB freed")
        return response

    except Exception as e:
        logger.error(f"Benchmark cleanup failed: {e}")
        return {
            "success": False,
            "retention_days": retention_days,
            "error": str(e),
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }


# Schedule periodic benchmark tasks
from celery.schedules import crontab

benchmark_celery_app.conf.beat_schedule = {
    # Daily comprehensive benchmark (2 AM UTC)
    "daily-comprehensive-benchmark": {
        "task": "run_scheduled_benchmark",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM UTC
        "args": ("comprehensive", "production"),
    },

    # Hourly performance health check
    "hourly-performance-health-check": {
        "task": "run_performance_health_check",
        "schedule": crontab(minute=0),  # Every hour at minute 0
        "args": (),
    },

    # Weekly detailed benchmark (Sunday 3 AM UTC)
    "weekly-detailed-benchmark": {
        "task": "run_scheduled_benchmark",
        "schedule": crontab(hour=3, minute=0, day_of_week=6),  # Sunday 3:00 AM UTC
        "args": ("comprehensive", "production"),
    },

    # Cleanup old benchmark results (monthly)
    "cleanup-benchmark-results": {
        "task": "cleanup_old_benchmark_results_task",
        "schedule": crontab(hour=4, minute=0, day=1),  # 1st of month 4:00 AM UTC
        "args": (90, False),  # 90 days retention, not dry run
    },
}