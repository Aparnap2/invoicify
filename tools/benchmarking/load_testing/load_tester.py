"""
Advanced load testing with k6 integration for API performance analysis.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
import aiohttp
import statistics

from ..core.benchmark_types import (
    BenchmarkType, LoadTestResult, PerformanceMetric, PerformanceTier, MetricCategory
)
from ..core.benchmark_config import BenchmarkConfig

logger = logging.getLogger(__name__)


class LoadTester:
    """Advanced load testing tool with k6 integration."""

    def __init__(self, config: BenchmarkConfig):
        """Initialize load tester with configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.results_dir = Path("tools/benchmarking/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Check k6 availability
        self.k6_available = self._check_k6_availability()

    def _check_k6_availability(self) -> bool:
        """Check if k6 is installed and available."""
        try:
            result = subprocess.run(
                ["k6", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.logger.info("k6 is available for load testing")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        self.logger.warning("k6 is not available, falling back to basic HTTP testing")
        return False

    async def run_load_test(
        self,
        test_name: str = "standard_load_test",
        virtual_users: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        ramp_up_seconds: Optional[int] = None,
        endpoints: Optional[List[str]] = None,
        custom_script: Optional[str] = None
    ) -> LoadTestResult:
        """
        Run comprehensive load test.

        Args:
            test_name: Name of the load test
            virtual_users: Number of concurrent virtual users
            duration_seconds: Test duration
            ramp_up_seconds: Ramp-up period
            endpoints: List of endpoints to test
            custom_script: Custom k6 script content

        Returns:
            LoadTestResult with comprehensive metrics
        """
        start_time = datetime.now(timezone.utc)
        benchmark_id = uuid4()

        users = virtual_users or self.config.load_test_virtual_users
        duration = duration_seconds or self.config.load_test_duration_seconds
        ramp_up = ramp_up_seconds or self.config.load_test_ramp_up_seconds

        try:
            self.logger.info(f"Starting load test: {test_name} - {users} users for {duration}s")

            if self.k6_available and not custom_script:
                # Use k6 for advanced load testing
                result = await self._run_k6_load_test(
                    benchmark_id, test_name, users, duration, ramp_up, endpoints
                )
            else:
                # Fall back to basic HTTP testing
                result = await self._run_basic_load_test(
                    benchmark_id, test_name, users, duration, endpoints, custom_script
                )

            self.logger.info(f"Load test completed: {test_name}")
            return result

        except Exception as e:
            self.logger.error(f"Load test failed: {e}")
            return LoadTestResult(
                id=benchmark_id,
                benchmark_type=BenchmarkType.LOAD_TEST,
                timestamp=start_time,
                duration_seconds=time.time() - start_time.timestamp(),
                success=False,
                error_message=str(e),
                concurrent_users=users,
                test_duration_seconds=duration
            )

    async def _run_k6_load_test(
        self,
        benchmark_id: UUID,
        test_name: str,
        virtual_users: int,
        duration_seconds: int,
        ramp_up_seconds: int,
        endpoints: Optional[List[str]]
    ) -> LoadTestResult:
        """Run load test using k6."""
        # Generate k6 script
        k6_script = self._generate_k6_script(
            endpoints or self._get_default_endpoints(),
            virtual_users,
            duration_seconds,
            ramp_up_seconds
        )

        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(k6_script)
            script_path = f.name

        try:
            # Run k6 test
            output_file = self.results_dir / f"k6_results_{benchmark_id}.json"

            cmd = [
                "k6", "run",
                f"--vus={virtual_users}",
                f"--duration={duration_seconds}s",
                f"--rps={max(1, virtual_users * 2)}",  # Target RPS
                f"--out=json={output_file}",
                script_path
            ]

            self.logger.info(f"Running k6: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"k6 failed: {stderr.decode()}")

            # Parse results
            return await self._parse_k6_results(benchmark_id, output_file)

        finally:
            # Cleanup temporary script
            os.unlink(script_path)

    async def _run_basic_load_test(
        self,
        benchmark_id: UUID,
        test_name: str,
        virtual_users: int,
        duration_seconds: int,
        endpoints: Optional[List[str]],
        custom_script: Optional[str]
    ) -> LoadTestResult:
        """Run basic HTTP load test (fallback when k6 not available)."""
        test_endpoints = endpoints or self._get_default_endpoints()
        response_times = []
        errors = []

        start_time = time.time()
        end_time = start_time + duration_seconds

        self.logger.info(f"Running basic load test with {virtual_users} concurrent users")

        async def make_requests():
            """Make requests concurrently."""
            session_timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=session_timeout) as session:
                while time.time() < end_time:
                    endpoint = test_endpoints[hash(str(time.time())) % len(test_endpoints)]
                    url = f"{self.config.api_base_url}{endpoint}"

                    try:
                        request_start = time.time()
                        async with session.get(url) as response:
                            if response.status == 200:
                                response_time = (time.time() - request_start) * 1000
                                response_times.append(response_time)
                            else:
                                errors.append({
                                    "endpoint": endpoint,
                                    "status_code": response.status,
                                    "error": f"HTTP {response.status}"
                                })
                    except Exception as e:
                        errors.append({
                            "endpoint": endpoint,
                            "error": str(e)
                        })

                    # Small delay between requests
                    await asyncio.sleep(0.1)

        # Run concurrent request makers
        tasks = [make_requests() for _ in range(virtual_users)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Calculate metrics
        total_duration = time.time() - start_time
        total_requests = len(response_times) + len(errors)

        return LoadTestResult(
            id=benchmark_id,
            benchmark_type=BenchmarkType.LOAD_TEST,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=total_duration,
            success=True,
            requests_total=total_requests,
            requests_successful=len(response_times),
            requests_failed=len(errors),
            avg_response_time_ms=statistics.mean(response_times) if response_times else 0,
            p50_response_time_ms=statistics.median(response_times) if response_times else 0,
            p95_response_time_ms=self._calculate_percentile(response_times, 95),
            p99_response_time_ms=self._calculate_percentile(response_times, 99),
            requests_per_second=total_requests / total_duration if total_duration > 0 else 0,
            error_rate=len(errors) / total_requests if total_requests > 0 else 0,
            concurrent_users=virtual_users,
            test_duration_seconds=duration_seconds,
            response_time_samples=response_times,
            error_samples=errors
        )

    def _generate_k6_script(
        self,
        endpoints: List[str],
        virtual_users: int,
        duration_seconds: int,
        ramp_up_seconds: int
    ) -> str:
        """Generate k6 JavaScript test script."""
        endpoints_json = json.dumps(endpoints)

        script = f"""
import http from 'k6/http';
import {{ check, sleep }} from 'k6';

const BASE_URL = '{self.config.api_base_url}';
const ENDPOINTS = {endpoints_json};

export let options = {{
    stages: [
        {{ duration: '{ramp_up_seconds}s', target: {virtual_users} }},
        {{ duration: '{duration_seconds - ramp_up_seconds}s', target: {virtual_users} }},
        {{ duration: '10s', target: 0 }}
    ],
    thresholds: {{
        http_req_duration: ['p(95)<500'],
        http_req_failed: ['rate<0.01'],
    }},
}};

export default function () {{
    const endpoint = ENDPOINTS[Math.floor(Math.random() * ENDPOINTS.length)];
    const url = BASE_URL + endpoint;

    let response = http.get(url);

    check(response, {{
        'status is 200': (r) => r.status === 200,
        'response time < 500ms': (r) => r.timings.duration < 500,
    }});

    sleep(0.1);
}}
"""
        return script

    def _get_default_endpoints(self) -> List[str]:
        """Get default endpoints for load testing."""
        return [
            "/health",
            "/metrics",
            "/api/v1/invoices",
            "/api/v1/metrics/slos/dashboard"
        ]

    async def _parse_k6_results(self, benchmark_id: UUID, output_file: Path) -> LoadTestResult:
        """Parse k6 JSON output file."""
        try:
            with open(output_file, 'r') as f:
                data = json.load(f)

            # Extract metrics from k6 results
            metrics = data.get('metrics', {})

            # HTTP request metrics
            http_req_duration = metrics.get('http_req_duration', {})
            http_req_failed = metrics.get('http_req_failed', {})
            http_reqs = metrics.get('http_reqs', {})

            # Parse response times
            response_time_samples = []
            if 'sample' in http_req_duration.get('data', {}):
                for sample in http_req_duration['data']['sample']:
                    response_time_samples.append(sample[1])

            # Calculate derived metrics
            total_requests = http_reqs.get('count', 0)
            failed_requests = http_req_failed.get('count', 0) if http_req_failed.get('rate', 0) > 0 else 0
            successful_requests = total_requests - failed_requests

            return LoadTestResult(
                id=benchmark_id,
                benchmark_type=BenchmarkType.LOAD_TEST,
                timestamp=datetime.now(timezone.utc),
                duration_seconds=data.get('root_group', {}).get('tests', [{}])[0].get('time', 0) / 1000000,
                success=True,
                requests_total=total_requests,
                requests_successful=successful_requests,
                requests_failed=failed_requests,
                avg_response_time_ms=http_req_duration.get('avg', 0),
                p50_response_time_ms=http_req_duration.get('med', 0),
                p95_response_time_ms=http_req_duration.get('p(95)', 0),
                p99_response_time_ms=http_req_duration.get('p(99)', 0),
                requests_per_second=http_reqs.get('rate', 0),
                throughput_bytes_per_second=metrics.get('data_received', {}).get('rate', 0),
                error_rate=http_req_failed.get('rate', 0),
                test_duration_seconds=self.config.load_test_duration_seconds,
                response_time_samples=response_time_samples,
                metadata={
                    "k6_version": data.get("metadata", {}).get("k6_version"),
                    "test_run_id": data.get("metadata", {}).get("test_run_id"),
                    "raw_k6_data": data
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to parse k6 results: {e}")
            raise

    async def run_stress_test(
        self,
        max_users: int = 100,
        duration_per_level: int = 60,
        user_increment: int = 10
    ) -> Dict[str, LoadTestResult]:
        """Run stress test with gradually increasing load."""
        results = {}

        for users in range(user_increment, max_users + 1, user_increment):
            test_name = f"stress_test_{users}_users"
            self.logger.info(f"Running stress test level: {users} users")

            result = await self.run_load_test(
                test_name=test_name,
                virtual_users=users,
                duration_seconds=duration_per_level,
                ramp_up_seconds=min(30, users // 2)
            )

            results[test_name] = result

            # Stop test if failure rate is too high
            if result.error_rate > 0.1:  # 10% error rate
                self.logger.warning(f"High error rate at {users} users: {result.error_rate:.1%}")
                break

        return results

    async def run_endurance_test(
        self,
        duration_hours: int = 8,
        virtual_users: int = 20
    ) -> LoadTestResult:
        """Run endurance test for extended duration."""
        duration_seconds = duration_hours * 3600

        self.logger.info(f"Starting endurance test: {duration_hours} hours, {virtual_users} users")

        return await self.run_load_test(
            test_name="endurance_test",
            virtual_users=virtual_users,
            duration_seconds=duration_seconds,
            ramp_up_seconds=60
        )

    def _calculate_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int((percentile / 100) * len(sorted_values))
        return sorted_values[min(index, len(sorted_values) - 1)]