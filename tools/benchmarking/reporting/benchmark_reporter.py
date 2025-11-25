"""
Benchmark reporting and analysis tools.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import UUID

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from ..core.benchmark_config import BenchmarkConfig
from ..core.benchmark_types import (
    BenchmarkSuite, PerformanceTier, MetricCategory
)

logger = logging.getLogger(__name__)


class BenchmarkReporter:
    """Comprehensive benchmark reporting with multiple output formats."""

    def __init__(self, config: BenchmarkConfig):
        """Initialize reporter with configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.results_dir = Path("tools/benchmarking/reports")
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Configure matplotlib for server environments
        plt.switch_backend('Agg')
        sns.set_style("whitegrid")
        sns.set_palette("husl")

    async def save_results(self, result: BenchmarkSuite, format: str = "json") -> str:
        """Save benchmark results to file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_results_{timestamp}.{format}"
        filepath = self.results_dir / filename

        if format == "json":
            await self._save_json_results(result, filepath)
        elif format == "csv":
            await self._save_csv_results(result, filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")

        self.logger.info(f"Results saved to: {filepath}")
        return str(filepath)

    async def _save_json_results(self, result: BenchmarkSuite, filepath: Path) -> None:
        """Save results as JSON."""
        # Convert result to dictionary
        result_dict = {
            "suite_id": str(result.suite_id),
            "timestamp": result.timestamp.isoformat(),
            "environment": result.environment,
            "overall_score": result.overall_score,
            "grade": result.grade.value,
            "system_info": result.system_info,
            "key_findings": result.key_findings,
            "recommendations": result.recommendations,
            "executive_summary": result.executive_summary,
        }

        # Add individual results
        if result.profiling_result:
            result_dict["profiling_result"] = self._profiling_result_to_dict(result.profiling_result)

        if result.load_test_result:
            result_dict["load_test_result"] = self._load_test_result_to_dict(result.load_test_result)

        if result.comparison_result:
            result_dict["comparison_result"] = self._comparison_result_to_dict(result.comparison_result)

        with open(filepath, 'w') as f:
            json.dump(result_dict, f, indent=2, default=str)

    async def _save_csv_results(self, result: BenchmarkSuite, filepath: Path) -> None:
        """Save key metrics as CSV."""
        data = []

        # Add overall metrics
        data.append({
            "metric": "overall_score",
            "value": result.overall_score,
            "category": "overall",
            "timestamp": result.timestamp.isoformat()
        })

        # Add profiling metrics
        if result.profiling_result and result.profiling_result.success:
            if result.profiling_result.cpu_usage_samples:
                avg_cpu = sum(result.profiling_result.cpu_usage_samples) / len(result.profiling_result.cpu_usage_samples)
                data.append({
                    "metric": "avg_cpu_usage",
                    "value": avg_cpu,
                    "category": "profiling",
                    "timestamp": result.profiling_result.timestamp.isoformat()
                })

            if result.profiling_result.memory_usage_samples:
                avg_memory = sum(result.profiling_result.memory_usage_samples) / len(result.profiling_result.memory_usage_samples)
                data.append({
                    "metric": "avg_memory_usage",
                    "value": avg_memory,
                    "category": "profiling",
                    "timestamp": result.profiling_result.timestamp.isoformat()
                })

        # Add load test metrics
        if result.load_test_result and result.load_test_result.success:
            data.extend([
                {
                    "metric": "requests_per_second",
                    "value": result.load_test_result.requests_per_second,
                    "category": "load_test",
                    "timestamp": result.load_test_result.timestamp.isoformat()
                },
                {
                    "metric": "p95_response_time_ms",
                    "value": result.load_test_result.p95_response_time_ms,
                    "category": "load_test",
                    "timestamp": result.load_test_result.timestamp.isoformat()
                },
                {
                    "metric": "error_rate",
                    "value": result.load_test_result.error_rate,
                    "category": "load_test",
                    "timestamp": result.load_test_result.timestamp.isoformat()
                }
            ])

        # Save to CSV
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)

    async def generate_report(self, result: BenchmarkSuite, format: str = "html") -> str:
        """Generate comprehensive benchmark report."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_report_{timestamp}.{format}"
        filepath = self.results_dir / filename

        if format == "html":
            await self._generate_html_report(result, filepath)
        elif format == "pdf":
            await self._generate_pdf_report(result, filepath)
        elif format == "markdown":
            await self._generate_markdown_report(result, filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")

        self.logger.info(f"Report generated: {filepath}")
        return str(filepath)

    async def _generate_html_report(self, result: BenchmarkSuite, filepath: Path) -> None:
        """Generate HTML report with charts."""
        # Generate charts
        charts = {}
        if self.config.include_charts:
            charts = await self._generate_charts(result)

        # HTML template
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>AP Intake Performance Benchmark Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ text-align: center; margin-bottom: 40px; }}
        .metric-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 10px 0; }}
        .grade-excellent {{ border-left: 5px solid #28a745; }}
        .grade-good {{ border-left: 5px solid #17a2b8; }}
        .grade-average {{ border-left: 5px solid #ffc107; }}
        .grade-poor {{ border-left: 5px solid #fd7e14; }}
        .grade-critical {{ border-left: 5px solid #dc3545; }}
        .chart {{ margin: 20px 0; text-align: center; }}
        .findings {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .recommendation {{ background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AP Intake Performance Benchmark Report</h1>
        <p>Generated on {result.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        <p>Environment: <strong>{result.environment}</strong></p>
    </div>

    <div class="metric-card grade-{result.grade.value}">
        <h2>Overall Performance Assessment</h2>
        <h3>Grade: {result.grade.value.upper()}</h3>
        <h4>Score: {result.overall_score:.1f}/100</h4>
        <p>{result.executive_summary}</p>
    </div>

    <div class="findings">
        <h2>Key Findings</h2>
        <ul>
            {''.join(f'<li>{finding}</li>' for finding in result.key_findings)}
        </ul>
    </div>

    {self._generate_profiling_section(result.profiling_result) if result.profiling_result else ''}

    {self._generate_load_test_section(result.load_test_result) if result.load_test_result else ''}

    {self._generate_system_info_section(result.system_info)}

    <div class="findings">
        <h2>Recommendations</h2>
        {"".join(f'<div class="recommendation">{rec}</div>' for rec in result.recommendations)}
    </div>

    {self._generate_charts_section(charts) if charts else ''}

    <footer>
        <p>Report generated by AP Intake Benchmarking Suite v1.0.0</p>
    </footer>
</body>
</html>
"""

        with open(filepath, 'w') as f:
            f.write(html_content)

    async def _generate_markdown_report(self, result: BenchmarkSuite, filepath: Path) -> None:
        """Generate Markdown report."""
        md_content = f"""# AP Intake Performance Benchmark Report

**Generated on:** {result.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
**Environment:** {result.environment}
**Suite ID:** {result.suite_id}

## Executive Summary

**Performance Grade:** {result.grade.value.upper()}
**Overall Score:** {result.overall_score:.1f}/100

{result.executive_summary}

## Key Findings

{chr(10).join(f"- {finding}" for finding in result.key_findings)}

## Recommendations

{chr(10).join(f"1. {rec}" for rec in result.recommendations)}

"""

        if result.profiling_result:
            md_content += self._generate_profiling_markdown(result.profiling_result)

        if result.load_test_result:
            md_content += self._generate_load_test_markdown(result.load_test_result)

        md_content += self._generate_system_info_markdown(result.system_info)

        md_content += "\n---\n\n*Report generated by AP Intake Benchmarking Suite v1.0.0*"

        with open(filepath, 'w') as f:
            f.write(md_content)

    async def _generate_charts(self, result: BenchmarkSuite) -> Dict[str, str]:
        """Generate performance charts."""
        charts = {}

        try:
            # Overall performance gauge
            charts["performance_gauge"] = self._create_performance_gauge(result.overall_score)

            # Response time distribution
            if result.load_test_result and result.load_test_result.response_time_samples:
                charts["response_times"] = self._create_response_time_chart(result.load_test_result)

            # Resource usage charts
            if result.profiling_result:
                if result.profiling_result.cpu_usage_samples:
                    charts["cpu_usage"] = self._create_cpu_usage_chart(result.profiling_result)
                if result.profiling_result.memory_usage_samples:
                    charts["memory_usage"] = self._create_memory_usage_chart(result.profiling_result)

        except Exception as e:
            self.logger.error(f"Failed to generate charts: {e}")

        return charts

    def _create_performance_gauge(self, score: float) -> str:
        """Create performance gauge chart."""
        fig, ax = plt.subplots(figsize=(8, 4))

        # Create gauge visualization
        categories = ['Critical', 'Poor', 'Average', 'Good', 'Excellent']
        colors = ['#dc3545', '#fd7e14', '#ffc107', '#17a2b8', '#28a745']
        thresholds = [20, 40, 60, 75, 100]

        # Create gradient background
        for i, (cat, color, thresh) in enumerate(zip(categories, colors, thresholds)):
            start = thresholds[i-1] if i > 0 else 0
            ax.barh(0, thresh - start, left=start, color=color, alpha=0.3, height=0.5)

        # Add score indicator
        ax.barh(0, score, color='red', alpha=0.8, height=0.3)
        ax.text(score, 0.15, f'{score:.1f}', ha='center', va='bottom', fontweight='bold')

        ax.set_xlim(0, 100)
        ax.set_ylim(-0.5, 0.5)
        ax.set_yticks([])
        ax.set_xlabel('Performance Score')
        ax.set_title('Overall Performance Score')

        # Add category labels
        for cat, thresh in zip(categories, thresholds):
            ax.axvline(x=thresh, color='gray', linestyle='--', alpha=0.5)

        plt.tight_layout()

        # Save chart
        chart_path = self.results_dir / "performance_gauge.png"
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(chart_path)

    def _create_response_time_chart(self, load_test_result) -> str:
        """Create response time distribution chart."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Response time distribution
        response_times = load_test_result.response_time_samples
        if response_times:
            ax1.hist(response_times, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
            ax1.axvline(load_test_result.p95_response_time_ms, color='red', linestyle='--',
                       label=f'P95: {load_test_result.p95_response_time_ms:.0f}ms')
            ax1.axvline(load_test_result.avg_response_time_ms, color='green', linestyle='--',
                       label=f'Avg: {load_test_result.avg_response_time_ms:.0f}ms')
            ax1.set_xlabel('Response Time (ms)')
            ax1.set_ylabel('Frequency')
            ax1.set_title('Response Time Distribution')
            ax1.legend()

        # Percentile chart
        percentiles = [50, 75, 90, 95, 99]
        values = [load_test_result.p50_response_time_ms,
                  self._calculate_percentile(response_times, 75),
                  self._calculate_percentile(response_times, 90),
                  load_test_result.p95_response_time_ms,
                  load_test_result.p99_response_time_ms]

        ax2.bar([f'P{p}' for p in percentiles], values, color='lightcoral')
        ax2.set_ylabel('Response Time (ms)')
        ax2.set_title('Response Time Percentiles')

        plt.tight_layout()

        chart_path = self.results_dir / "response_times.png"
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(chart_path)

    def _create_cpu_usage_chart(self, profiling_result) -> str:
        """Create CPU usage time series chart."""
        fig, ax = plt.subplots(figsize=(12, 6))

        cpu_samples = profiling_result.cpu_usage_samples
        time_points = list(range(len(cpu_samples)))

        ax.plot(time_points, cpu_samples, color='red', alpha=0.7, linewidth=1)
        ax.axhline(y=80, color='orange', linestyle='--', label='Warning Threshold (80%)')
        ax.axhline(y=90, color='red', linestyle='--', label='Critical Threshold (90%)')

        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        ax.axhline(y=avg_cpu, color='green', linestyle='-', label=f'Average: {avg_cpu:.1f}%')

        ax.set_xlabel('Time (seconds)')
        ax.set_ylabel('CPU Usage (%)')
        ax.set_title('CPU Usage Over Time')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        chart_path = self.results_dir / "cpu_usage.png"
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(chart_path)

    def _create_memory_usage_chart(self, profiling_result) -> str:
        """Create memory usage time series chart."""
        fig, ax = plt.subplots(figsize=(12, 6))

        memory_samples = profiling_result.memory_usage_samples
        time_points = list(range(len(memory_samples)))

        ax.plot(time_points, memory_samples, color='blue', alpha=0.7, linewidth=1)
        ax.axhline(y=85, color='orange', linestyle='--', label='Warning Threshold (85%)')
        ax.axhline(y=95, color='red', linestyle='--', label='Critical Threshold (95%)')

        avg_memory = sum(memory_samples) / len(memory_samples)
        ax.axhline(y=avg_memory, color='green', linestyle='-', label=f'Average: {avg_memory:.1f}%')

        ax.set_xlabel('Time (seconds)')
        ax.set_ylabel('Memory Usage (%)')
        ax.set_title('Memory Usage Over Time')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        chart_path = self.results_dir / "memory_usage.png"
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()

        return str(chart_path)

    def _calculate_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int((percentile / 100) * len(sorted_values))
        return sorted_values[min(index, len(sorted_values) - 1)]

    def _profiling_result_to_dict(self, profiling_result) -> Dict[str, Any]:
        """Convert profiling result to dictionary."""
        return {
            "id": str(profiling_result.id),
            "timestamp": profiling_result.timestamp.isoformat(),
            "duration_seconds": profiling_result.duration_seconds,
            "success": profiling_result.success,
            "cpu_avg": sum(profiling_result.cpu_usage_samples) / len(profiling_result.cpu_usage_samples) if profiling_result.cpu_usage_samples else None,
            "memory_avg": sum(profiling_result.memory_usage_samples) / len(profiling_result.memory_usage_samples) if profiling_result.memory_usage_samples else None,
            "bottlenecks_count": len(profiling_result.bottlenecks),
        }

    def _load_test_result_to_dict(self, load_test_result) -> Dict[str, Any]:
        """Convert load test result to dictionary."""
        return {
            "id": str(load_test_result.id),
            "timestamp": load_test_result.timestamp.isoformat(),
            "duration_seconds": load_test_result.duration_seconds,
            "success": load_test_result.success,
            "requests_total": load_test_result.requests_total,
            "requests_successful": load_test_result.requests_successful,
            "requests_failed": load_test_result.requests_failed,
            "avg_response_time_ms": load_test_result.avg_response_time_ms,
            "p95_response_time_ms": load_test_result.p95_response_time_ms,
            "requests_per_second": load_test_result.requests_per_second,
            "error_rate": load_test_result.error_rate,
            "concurrent_users": load_test_result.concurrent_users,
        }

    def _comparison_result_to_dict(self, comparison_result) -> Dict[str, Any]:
        """Convert comparison result to dictionary."""
        return {
            "id": str(comparison_result.id),
            "timestamp": comparison_result.timestamp.isoformat(),
            "duration_seconds": comparison_result.duration_seconds,
            "success": comparison_result.success,
            "performance_gaps": comparison_result.performance_gaps,
            "recommendations_count": len(comparison_result.recommendations),
        }

    def _generate_profiling_section(self, profiling_result) -> str:
        """Generate HTML profiling section."""
        if not profiling_result or not profiling_result.success:
            return ""

        avg_cpu = sum(profiling_result.cpu_usage_samples) / len(profiling_result.cpu_usage_samples) if profiling_result.cpu_usage_samples else 0
        avg_memory = sum(profiling_result.memory_usage_samples) / len(profiling_result.memory_usage_samples) if profiling_result.memory_usage_samples else 0

        return f"""
        <div class="metric-card">
            <h2>Performance Profiling Results</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Average CPU Usage</td><td>{avg_cpu:.1f}%</td></tr>
                <tr><td>Average Memory Usage</td><td>{avg_memory:.1f}%</td></tr>
                <tr><td>Duration</td><td>{profiling_result.duration_seconds:.1f} seconds</td></tr>
                <tr><td>Bottlenecks Found</td><td>{len(profiling_result.bottlenecks)}</td></tr>
            </table>
            {self._generate_bottlenecks_table(profiling_result.bottlenecks) if profiling_result.bottlenecks else ''}
        </div>
        """

    def _generate_load_test_section(self, load_test_result) -> str:
        """Generate HTML load test section."""
        if not load_test_result or not load_test_result.success:
            return ""

        return f"""
        <div class="metric-card">
            <h2>Load Testing Results</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Total Requests</td><td>{load_test_result.requests_total:,}</td></tr>
                <tr><td>Successful Requests</td><td>{load_test_result.requests_successful:,}</td></tr>
                <tr><td>Failed Requests</td><td>{load_test_result.requests_failed:,}</td></tr>
                <tr><td>Requests per Second</td><td>{load_test_result.requests_per_second:.1f}</td></tr>
                <tr><td>Average Response Time</td><td>{load_test_result.avg_response_time_ms:.0f} ms</td></tr>
                <tr><td>P95 Response Time</td><td>{load_test_result.p95_response_time_ms:.0f} ms</td></tr>
                <tr><td>P99 Response Time</td><td>{load_test_result.p99_response_time_ms:.0f} ms</td></tr>
                <tr><td>Error Rate</td><td>{load_test_result.error_rate:.2%}</td></tr>
                <tr><td>Concurrent Users</td><td>{load_test_result.concurrent_users}</td></tr>
            </table>
        </div>
        """

    def _generate_system_info_section(self, system_info: Dict[str, Any]) -> str:
        """Generate HTML system info section."""
        platform = system_info.get("platform", {})
        hardware = system_info.get("hardware", {})

        return f"""
        <div class="metric-card">
            <h2>System Information</h2>
            <table>
                <tr><th>Property</th><th>Value</th></tr>
                <tr><td>System</td><td>{platform.get('system', 'Unknown')}</td></tr>
                <tr><td>Release</td><td>{platform.get('release', 'Unknown')}</td></tr>
                <tr><td>Python Version</td><td>{platform.get('python_version', 'Unknown')}</td></tr>
                <tr><td>CPU Cores</td><td>{hardware.get('cpu_count', 'Unknown')}</td></tr>
                <tr><td>Total Memory</td><td>{hardware.get('memory_total', 0) / (1024**3):.1f} GB</td></tr>
            </table>
        </div>
        """

    def _generate_charts_section(self, charts: Dict[str, str]) -> str:
        """Generate HTML charts section."""
        chart_html = "<div class='charts'><h2>Performance Charts</h2>"

        chart_titles = {
            "performance_gauge": "Overall Performance Score",
            "response_times": "Response Time Analysis",
            "cpu_usage": "CPU Usage Over Time",
            "memory_usage": "Memory Usage Over Time"
        }

        for chart_key, chart_path in charts.items():
            title = chart_titles.get(chart_key, chart_key.replace("_", " ").title())
            chart_filename = Path(chart_path).name
            chart_html += f'<div class="chart"><h3>{title}</h3><img src="{chart_filename}" alt="{title}" /></div>'

        chart_html += "</div>"
        return chart_html

    def _generate_bottlenecks_table(self, bottlenecks: List[Dict[str, Any]]) -> str:
        """Generate HTML bottlenecks table."""
        if not bottlenecks:
            return ""

        table_html = "<h3>Performance Bottlenecks</h3><table>"
        table_html += "<tr><th>Type</th><th>Severity</th><th>Description</th><th>Recommendation</th></tr>"

        for bottleneck in bottlenecks:
            table_html += f"""
            <tr>
                <td>{bottleneck.get('type', 'Unknown')}</td>
                <td>{bottleneck.get('severity', 'Unknown')}</td>
                <td>{bottleneck.get('description', 'No description')}</td>
                <td>{bottleneck.get('recommendation', 'No recommendation')}</td>
            </tr>
            """

        table_html += "</table>"
        return table_html

    def _generate_profiling_markdown(self, profiling_result) -> str:
        """Generate Markdown profiling section."""
        if not profiling_result or not profiling_result.success:
            return ""

        avg_cpu = sum(profiling_result.cpu_usage_samples) / len(profiling_result.cpu_usage_samples) if profiling_result.cpu_usage_samples else 0
        avg_memory = sum(profiling_result.memory_usage_samples) / len(profiling_result.memory_usage_samples) if profiling_result.memory_usage_samples else 0

        md = f"""
## Performance Profiling

- **Average CPU Usage:** {avg_cpu:.1f}%
- **Average Memory Usage:** {avg_memory:.1f}%
- **Duration:** {profiling_result.duration_seconds:.1f} seconds
- **Bottlenecks Found:** {len(profiling_result.bottlenecks)}

"""

        if profiling_result.bottlenecks:
            md += "### Performance Bottlenecks\n\n"
            for bottleneck in profiling_result.bottlenecks:
                md += f"- **{bottleneck.get('type', 'Unknown').title()}** ({bottleneck.get('severity', 'unknown')}): {bottleneck.get('description', 'No description')}\n"
                if bottleneck.get('recommendation'):
                    md += f"  - Recommendation: {bottleneck['recommendation']}\n"

        return md

    def _generate_load_test_markdown(self, load_test_result) -> str:
        """Generate Markdown load test section."""
        if not load_test_result or not load_test_result.success:
            return ""

        return f"""
## Load Testing Results

- **Total Requests:** {load_test_result.requests_total:,}
- **Successful Requests:** {load_test_result.requests_successful:,}
- **Failed Requests:** {load_test_result.requests_failed:,}
- **Requests per Second:** {load_test_result.requests_per_second:.1f}
- **Average Response Time:** {load_test_result.avg_response_time_ms:.0f} ms
- **P95 Response Time:** {load_test_result.p95_response_time_ms:.0f} ms
- **P99 Response Time:** {load_test_result.p99_response_time_ms:.0f} ms
- **Error Rate:** {load_test_result.error_rate:.2%}
- **Concurrent Users:** {load_test_result.concurrent_users}

"""

    def _generate_system_info_markdown(self, system_info: Dict[str, Any]) -> str:
        """Generate Markdown system info section."""
        platform = system_info.get("platform", {})
        hardware = system_info.get("hardware", {})

        return f"""
## System Information

- **System:** {platform.get('system', 'Unknown')}
- **Release:** {platform.get('release', 'Unknown')}
- **Python Version:** {platform.get('python_version', 'Unknown')}
- **CPU Cores:** {hardware.get('cpu_count', 'Unknown')}
- **Total Memory:** {hardware.get('memory_total', 0) / (1024**3):.1f} GB

"""