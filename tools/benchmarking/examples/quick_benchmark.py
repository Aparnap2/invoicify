#!/usr/bin/env python3
"""
Quick benchmark example for AP Intake system.

This script demonstrates how to use the benchmarking suite programmatically
for quick performance analysis.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tools.benchmarking.core.benchmark_suite import BenchmarkSuite
from tools.benchmarking.core.benchmark_config import BenchmarkConfig


async def quick_performance_check():
    """Run a quick performance check."""
    print("🚀 Starting AP Intake Quick Performance Check")
    print("=" * 50)

    # Configure for quick testing
    config = BenchmarkConfig(
        environment="development",
        api_base_url="http://localhost:8000",
        load_test_duration_seconds=60,    # 1 minute
        load_test_virtual_users=5,       # Low concurrency
        profiling_duration_seconds=30,   # 30 seconds
        include_charts=False,            # Skip charts for speed
        report_format="json"
    )

    # Create benchmark suite
    suite = BenchmarkSuite(config)

    try:
        # Run quick load test
        print("📊 Running quick load test...")
        load_test_result = await suite.run_load_testing()

        if load_test_result.success:
            print(f"✅ Load test completed successfully!")
            print(f"   📈 Requests per Second: {load_test_result.load_test_result.requests_per_second:.1f}")
            print(f"   ⚡ P95 Response Time: {load_test_result.load_test_result.p95_response_time_ms:.0f}ms")
            print(f"   ❌ Error Rate: {load_test_result.load_test_result.error_rate:.2%}")
            print(f"   🎯 Overall Score: {load_test_result.overall_score:.1f}/100")
            print(f"   📊 Grade: {load_test_result.grade.value.upper()}")
        else:
            print(f"❌ Load test failed: {load_test_result.key_findings}")

        # Run quick profiling
        print("\n🔍 Running quick performance profiling...")
        profiling_result = await suite.run_performance_profiling()

        if profiling_result.success and profiling_result.profiling_result.success:
            cpu_samples = profiling_result.profiling_result.cpu_usage_samples
            memory_samples = profiling_result.profiling_result.memory_usage_samples

            avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
            avg_memory = sum(memory_samples) / len(memory_samples) if memory_samples else 0

            print(f"✅ Profiling completed successfully!")
            print(f"   💻 Average CPU Usage: {avg_cpu:.1f}%")
            print(f"   🧠 Average Memory Usage: {avg_memory:.1f}%")
            print(f"   🚨 Bottlenecks Found: {len(profiling_result.profiling_result.bottlenecks)}")

            if profiling_result.profiling_result.bottlenecks:
                print("   ⚠️  Performance Issues:")
                for bottleneck in profiling_result.profiling_result.bottlenecks[:3]:  # Top 3
                    print(f"      • {bottleneck.get('description', 'Unknown issue')}")
        else:
            print(f"❌ Profiling failed")

        # Generate summary report
        print("\n📋 Generating performance summary...")

        # Calculate overall assessment
        load_score = load_test_result.overall_score if load_test_result.success else 0
        prof_score = profiling_result.overall_score if profiling_result.success else 0
        overall_score = (load_score + prof_score) / 2 if load_test_result.success and profiling_result.success else max(load_score, prof_score)

        if overall_score >= 90:
            grade = "EXCELLENT"
            emoji = "🏆"
        elif overall_score >= 75:
            grade = "GOOD"
            emoji = "✅"
        elif overall_score >= 60:
            grade = "AVERAGE"
            emoji = "📊"
        elif overall_score >= 40:
            grade = "POOR"
            emoji = "⚠️"
        else:
            grade = "CRITICAL"
            emoji = "🚨"

        print(f"\n{emoji} PERFORMANCE SUMMARY")
        print(f"   Overall Score: {overall_score:.1f}/100")
        print(f"   Performance Grade: {grade}")

        # Recommendations
        print("\n💡 Quick Recommendations:")
        if overall_score >= 75:
            print("   • Performance is good - continue monitoring")
        elif overall_score >= 60:
            print("   • Consider optimizing identified bottlenecks")
        else:
            print("   • Performance needs immediate attention")
            print("   • Review system resources and configuration")

        print("\n📈 For detailed analysis:")
        print("   python tools/benchmarking/scripts/run_benchmark.py --comprehensive")
        print("   python tools/benchmarking/scripts/run_benchmark.py --monitor")

    except Exception as e:
        print(f"❌ Quick benchmark failed: {e}")
        print("\n💡 Make sure the API server is running:")
        print("   docker-compose up -d")
        print("   or")
        print("   uvicorn app.main:app --reload")

    print("\n✨ Quick benchmark completed!")


if __name__ == "__main__":
    asyncio.run(quick_performance_check())