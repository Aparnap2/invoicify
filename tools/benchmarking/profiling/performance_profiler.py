"""
Comprehensive performance profiler with CPU, memory, and I/O analysis.
"""

import asyncio
import logging
import time
import psutil
import threading
import os
import subprocess
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import tracemalloc
import cProfile
import pstats
import io

from ..core.benchmark_types import (
    BenchmarkType, ProfilingResult, PerformanceMetric, PerformanceTier, MetricCategory
)
from ..core.benchmark_config import BenchmarkConfig

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Comprehensive performance profiler for AP Intake system."""

    def __init__(self, config: BenchmarkConfig):
        """Initialize profiler with configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.results_dir = Path("tools/benchmarking/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Profiling state
        self.is_profiling = False
        self._stop_event = threading.Event()
        self._profiling_threads: List[threading.Thread] = []
        self._metrics: List[PerformanceMetric] = []
        self._cpu_samples: List[float] = []
        self._memory_samples: List[float] = []
        self._io_stats_samples: List[Dict[str, Any]] = []
        self._memory_snapshots: List[Dict[str, Any]] = []

    async def profile_system(
        self,
        target_function: Optional[Callable] = None,
        duration_seconds: Optional[int] = None,
        profile_api: bool = True
    ) -> ProfilingResult:
        """
        Perform comprehensive system profiling.

        Args:
            target_function: Optional function to profile
            duration_seconds: Override config duration
            profile_api: Whether to profile API endpoints

        Returns:
            ProfilingResult with comprehensive analysis
        """
        duration = duration_seconds or self.config.profiling_duration_seconds
        start_time = datetime.now(timezone.utc)
        benchmark_id = uuid4()

        try:
            self.logger.info(f"Starting comprehensive profiling for {duration}s")

            # Initialize profiling tools
            await self._initialize_profiling()

            # Start background monitoring
            self._start_background_monitoring()

            # Start specific profiling types
            if self.config.cpu_profiling_enabled:
                await self._start_cpu_profiling(benchmark_id, target_function)

            if self.config.memory_profiling_enabled:
                await self._start_memory_profiling()

            if profile_api:
                await self._profile_api_endpoints()

            # Wait for profiling duration
            await asyncio.sleep(duration)

            # Stop all profiling
            await self._stop_profiling()

            # Generate results
            result = await self._generate_profiling_result(
                benchmark_id, start_time, duration
            )

            self.logger.info("Comprehensive profiling completed successfully")
            return result

        except Exception as e:
            self.logger.error(f"Profiling failed: {e}")
            # Ensure cleanup on error
            await self._stop_profiling()

            return ProfilingResult(
                id=benchmark_id,
                benchmark_type=BenchmarkType.PROFILING,
                timestamp=start_time,
                duration_seconds=time.time() - start_time.timestamp(),
                success=False,
                error_message=str(e)
            )

    async def _initialize_profiling(self) -> None:
        """Initialize all profiling components."""
        self.is_profiling = True
        self._stop_event.clear()

        # Initialize memory tracking
        tracemalloc.start()

        # Clear previous results
        self._metrics.clear()
        self._cpu_samples.clear()
        self._memory_samples.clear()
        self._io_stats_samples.clear()
        self._memory_snapshots.clear()

        self.logger.info("Profiling components initialized")

    def _start_background_monitoring(self) -> None:
        """Start background monitoring threads."""
        if self.config.cpu_profiling_enabled:
            cpu_thread = threading.Thread(
                target=self._monitor_cpu_usage,
                daemon=True
            )
            cpu_thread.start()
            self._profiling_threads.append(cpu_thread)

        if self.config.memory_profiling_enabled:
            memory_thread = threading.Thread(
                target=self._monitor_memory_usage,
                daemon=True
            )
            memory_thread.start()
            self._profiling_threads.append(memory_thread)

        io_thread = threading.Thread(
            target=self._monitor_io_stats,
            daemon=True
        )
        io_thread.start()
        self._profiling_threads.append(io_thread)

        self.logger.info("Background monitoring started")

    def _monitor_cpu_usage(self) -> None:
        """Monitor CPU usage in background thread."""
        sampling_interval = 1.0 / self.config.profiling_sampling_rate

        while not self._stop_event.is_set():
            try:
                cpu_percent = psutil.cpu_percent(interval=sampling_interval)
                self._cpu_samples.append(cpu_percent)
            except Exception as e:
                self.logger.warning(f"CPU monitoring error: {e}")

            time.sleep(sampling_interval)

    def _monitor_memory_usage(self) -> None:
        """Monitor memory usage in background thread."""
        sampling_interval = 1.0 / self.config.profiling_sampling_rate

        while not self._stop_event.is_set():
            try:
                memory_info = psutil.virtual_memory()
                self._memory_samples.append(memory_info.percent)

                # Create memory snapshot every 10 seconds
                if len(self._memory_samples) % 10 == 0:
                    snapshot = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "total_bytes": memory_info.total,
                        "available_bytes": memory_info.available,
                        "percent": memory_info.percent,
                        "used_bytes": memory_info.used,
                        "tracemalloc": tracemalloc.get_traced_memory()
                    }
                    self._memory_snapshots.append(snapshot)

            except Exception as e:
                self.logger.warning(f"Memory monitoring error: {e}")

            time.sleep(sampling_interval)

    def _monitor_io_stats(self) -> None:
        """Monitor I/O statistics in background thread."""
        sampling_interval = 1.0

        while not self._stop_event.is_set():
            try:
                io_stats = psutil.disk_io_counters()
                net_io_stats = psutil.net_io_counters()

                sample = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "disk": {
                        "read_bytes": io_stats.read_bytes if io_stats else 0,
                        "write_bytes": io_stats.write_bytes if io_stats else 0,
                        "read_count": io_stats.read_count if io_stats else 0,
                        "write_count": io_stats.write_count if io_stats else 0,
                    },
                    "network": {
                        "bytes_sent": net_io_stats.bytes_sent if net_io_stats else 0,
                        "bytes_recv": net_io_stats.bytes_recv if net_io_stats else 0,
                        "packets_sent": net_io_stats.packets_sent if net_io_stats else 0,
                        "packets_recv": net_io_stats.packets_recv if net_io_stats else 0,
                    }
                }
                self._io_stats_samples.append(sample)

            except Exception as e:
                self.logger.warning(f"I/O monitoring error: {e}")

            time.sleep(sampling_interval)

    async def _start_cpu_profiling(self, benchmark_id: UUID, target_function: Optional[Callable]) -> None:
        """Start CPU profiling with cProfile."""
        if not target_function:
            return

        cpu_profile_path = self.results_dir / f"cpu_profile_{benchmark_id}.prof"

        def profile_function():
            """Run the target function with CPU profiling."""
            profiler = cProfile.Profile()
            profiler.enable()

            try:
                if asyncio.iscoroutinefunction(target_function):
                    asyncio.run(target_function())
                else:
                    target_function()
            finally:
                profiler.disable()
                profiler.dump_stats(str(cpu_profile_path))

        # Run profiling in thread pool
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            await loop.run_in_executor(executor, profile_function)

    async def _start_memory_profiling(self) -> None:
        """Start enhanced memory profiling."""
        # tracemalloc is already started in _initialize_profiling
        self.logger.info("Memory profiling started")

    async def _profile_api_endpoints(self) -> None:
        """Profile API endpoints by making requests."""
        import aiohttp

        endpoints_to_profile = [
            "/health",
            "/metrics",
            "/api/v1/invoices",
            "/api/v1/metrics/slos/dashboard"
        ]

        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints_to_profile:
                try:
                    url = f"{self.config.api_base_url}{endpoint}"
                    start_time = time.time()

                    async with session.get(url) as response:
                        response_time = (time.time() - start_time) * 1000

                        metric = PerformanceMetric(
                            name=f"api_response_time_{endpoint.replace('/', '_')}",
                            category=MetricCategory.LATENCY,
                            value=response_time,
                            unit="ms",
                            timestamp=datetime.now(timezone.utc),
                            metadata={
                                "endpoint": endpoint,
                                "status_code": response.status
                            }
                        )
                        self._metrics.append(metric)

                except Exception as e:
                    self.logger.warning(f"Failed to profile endpoint {endpoint}: {e}")

    async def _stop_profiling(self) -> None:
        """Stop all profiling activities."""
        self._stop_event.set()
        self.is_profiling = False

        # Wait for threads to finish
        for thread in self._profiling_threads:
            thread.join(timeout=5)

        self._profiling_threads.clear()

        # Stop memory tracing
        if tracemalloc.is_tracing():
            tracemalloc.stop()

        self.logger.info("All profiling stopped")

    async def _generate_profiling_result(
        self,
        benchmark_id: UUID,
        start_time: datetime,
        duration_seconds: float
    ) -> ProfilingResult:
        """Generate comprehensive profiling result."""
        end_time = datetime.now(timezone.utc)

        # Analyze CPU usage
        cpu_stats = self._analyze_cpu_samples()

        # Analyze memory usage
        memory_stats = self._analyze_memory_samples()

        # Analyze I/O stats
        io_stats = self._analyze_io_samples()

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(cpu_stats, memory_stats, io_stats)

        # Generate flame graph if data available
        flame_graph_path = None
        if self._cpu_samples:
            flame_graph_path = await self._generate_flame_graph(benchmark_id)

        # Save profile data
        profile_paths = await self._save_profile_data(benchmark_id)

        result = ProfilingResult(
            id=benchmark_id,
            benchmark_type=BenchmarkType.PROFILING,
            timestamp=start_time,
            duration_seconds=duration_seconds,
            success=True,
            cpu_usage_samples=self._cpu_samples,
            memory_usage_samples=self._memory_samples,
            memory_snapshots=self._memory_snapshots,
            io_stats=io_stats,
            bottlenecks=bottlenecks,
            flame_graph_path=str(flame_graph_path) if flame_graph_path else None,
            **profile_paths
        )

        # Add performance metrics
        result.metadata.update({
            "cpu_stats": cpu_stats,
            "memory_stats": memory_stats,
            "analysis_timestamp": end_time.isoformat(),
            "sampling_rate": self.config.profiling_sampling_rate
        })

        return result

    def _analyze_cpu_samples(self) -> Dict[str, float]:
        """Analyze CPU usage samples."""
        if not self._cpu_samples:
            return {}

        return {
            "avg": sum(self._cpu_samples) / len(self._cpu_samples),
            "max": max(self._cpu_samples),
            "min": min(self._cpu_samples),
            "p95": self._calculate_percentile(self._cpu_samples, 95),
            "p99": self._calculate_percentile(self._cpu_samples, 99),
            "sample_count": len(self._cpu_samples)
        }

    def _analyze_memory_samples(self) -> Dict[str, float]:
        """Analyze memory usage samples."""
        if not self._memory_samples:
            return {}

        return {
            "avg": sum(self._memory_samples) / len(self._memory_samples),
            "max": max(self._memory_samples),
            "min": min(self._memory_samples),
            "p95": self._calculate_percentile(self._memory_samples, 95),
            "p99": self._calculate_percentile(self._memory_samples, 99),
            "sample_count": len(self._memory_samples)
        }

    def _analyze_io_samples(self) -> Dict[str, Any]:
        """Analyze I/O statistics samples."""
        if not self._io_stats_samples:
            return {}

        # Calculate I/O rates
        total_disk_read = sum(sample["disk"]["read_bytes"] for sample in self._io_stats_samples)
        total_disk_write = sum(sample["disk"]["write_bytes"] for sample in self._io_stats_samples)
        total_net_sent = sum(sample["network"]["bytes_sent"] for sample in self._io_stats_samples)
        total_net_recv = sum(sample["network"]["bytes_recv"] for sample in self._io_stats_samples)

        duration = len(self._io_stats_samples)  # Assuming 1-second intervals

        return {
            "duration_seconds": duration,
            "disk_read_rate": total_disk_read / duration if duration > 0 else 0,
            "disk_write_rate": total_disk_write / duration if duration > 0 else 0,
            "network_sent_rate": total_net_sent / duration if duration > 0 else 0,
            "network_recv_rate": total_net_recv / duration if duration > 0 else 0,
            "sample_count": len(self._io_stats_samples)
        }

    def _identify_bottlenecks(
        self,
        cpu_stats: Dict[str, float],
        memory_stats: Dict[str, float],
        io_stats: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks."""
        bottlenecks = []

        # CPU bottlenecks
        if cpu_stats.get("avg", 0) > self.config.cpu_usage_threshold * 100:
            bottlenecks.append({
                "type": "cpu",
                "severity": "high" if cpu_stats["avg"] > 90 else "medium",
                "description": f"High CPU usage: {cpu_stats['avg']:.1f}%",
                "recommendation": "Consider scaling horizontally or optimizing CPU-intensive operations"
            })

        # Memory bottlenecks
        if memory_stats.get("avg", 0) > self.config.memory_usage_threshold * 100:
            bottlenecks.append({
                "type": "memory",
                "severity": "high" if memory_stats["avg"] > 90 else "medium",
                "description": f"High memory usage: {memory_stats['avg']:.1f}%",
                "recommendation": "Investigate memory leaks or increase available memory"
            })

        # I/O bottlenecks
        if io_stats.get("disk_read_rate", 0) > 100 * 1024 * 1024:  # 100MB/s
            bottlenecks.append({
                "type": "disk_io",
                "severity": "medium",
                "description": f"High disk read rate: {io_stats['disk_read_rate'] / (1024*1024):.1f} MB/s",
                "recommendation": "Consider adding caching or optimizing database queries"
            })

        return bottlenecks

    async def _generate_flame_graph(self, benchmark_id: UUID) -> Optional[Path]:
        """Generate flame graph from profiling data."""
        try:
            # This would integrate with flame graph generation tools
            # For now, return a placeholder path
            flame_graph_path = self.results_dir / f"flame_graph_{benchmark_id}.svg"

            # TODO: Implement actual flame graph generation using tools like
            # py-spy, flamegraph.pl, or similar
            self.logger.info(f"Flame graph placeholder created: {flame_graph_path}")

            return flame_graph_path

        except Exception as e:
            self.logger.warning(f"Failed to generate flame graph: {e}")
            return None

    async def _save_profile_data(self, benchmark_id: UUID) -> Dict[str, str]:
        """Save profiling data to files."""
        paths = {}

        # Save CPU samples
        cpu_path = self.results_dir / f"cpu_samples_{benchmark_id}.json"
        with open(cpu_path, "w") as f:
            json.dump(self._cpu_samples, f)
        paths["cpu_profile_path"] = str(cpu_path)

        # Save memory samples
        memory_path = self.results_dir / f"memory_samples_{benchmark_id}.json"
        with open(memory_path, "w") as f:
            json.dump(self._memory_samples, f)
        paths["memory_profile_path"] = str(memory_path)

        # Save I/O stats
        io_path = self.results_dir / f"io_stats_{benchmark_id}.json"
        with open(io_path, "w") as f:
            json.dump(self._io_stats_samples, f)
        paths["io_profile_path"] = str(io_path)

        # Save memory snapshots
        snapshots_path = self.results_dir / f"memory_snapshots_{benchmark_id}.json"
        with open(snapshots_path, "w") as f:
            json.dump(self._memory_snapshots, f, indent=2)

        return paths

    def _calculate_percentile(self, samples: List[float], percentile: float) -> float:
        """Calculate percentile of samples."""
        if not samples:
            return 0.0

        sorted_samples = sorted(samples)
        index = int((percentile / 100) * len(sorted_samples))
        return sorted_samples[min(index, len(sorted_samples) - 1)]