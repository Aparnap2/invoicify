# AP Intake Performance Benchmarking Suite

Comprehensive performance benchmarking and monitoring tools for the AP Intake & Validation system.

## Overview

The benchmarking suite provides complete performance analysis capabilities including:

- **Performance Profiling** - CPU, memory, and I/O profiling with flame graphs
- **Load Testing** - Automated load testing with k6 integration
- **Real-time Monitoring** - Live performance dashboards with WebSocket support
- **Automated Reporting** - Scheduled benchmark reports and trend analysis
- **Industry Comparison** - Performance benchmarking against industry standards

## Quick Start

### Installation

1. Install required dependencies:
```bash
# For load testing (optional but recommended)
curl -s https://k6.io/release.key | sudo apt-key add -
echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# Python dependencies (already in requirements.txt)
pip install matplotlib seaborn pandas psutil websockets
```

2. Verify installation:
```bash
python tools/benchmarking/scripts/run_benchmark.py --help
```

### Running Benchmarks

#### Quick Comprehensive Benchmark
```bash
# Run full benchmark suite
python tools/benchmarking/scripts/run_benchmark.py --comprehensive

# Run with custom settings
python tools/benchmarking/scripts/run_benchmark.py --comprehensive \
    --users 50 \
    --duration 600 \
    --output-format html
```

#### Load Testing Only
```bash
# Standard load test
python tools/benchmarking/scripts/run_benchmark.py --load-test

# Stress test
python tools/benchmarking/scripts/run_benchmark.py --stress-test --max-users 200

# Custom load test
python tools/benchmarking/scripts/run_benchmark.py --load-test \
    --users 100 \
    --duration 300 \
    --ramp-up 60
```

#### Performance Profiling Only
```bash
# Comprehensive profiling
python tools/benchmarking/scripts/run_benchmark.py --profile

# CPU profiling only
python tools/benchmarking/scripts/run_benchmark.py --profile \
    --cpu-only \
    --profile-duration 300

# Memory profiling only
python tools/benchmarking/scripts/run_benchmark.py --profile \
    --memory-only \
    --profile-duration 300
```

#### Real-time Monitoring
```bash
# Start monitoring dashboard
python tools/benchmarking/scripts/run_benchmark.py --monitor \
    --monitor-port 8765

# Connect to dashboard at ws://localhost:8765
# Use WebSocket client to receive real-time performance updates
```

### Configuration

Configuration files are located in `tools/benchmarking/config/`:

- `default.json` - Development environment settings
- `production.json` - Production environment settings
- `staging.json` - Staging environment settings (create as needed)

#### Custom Configuration
```bash
# Use custom config
python tools/benchmarking/scripts/run_benchmark.py --config my-config.json

# Override specific settings
python tools/benchmarking/scripts/run_benchmark.py \
    --api-url https://api.staging.com \
    --users 25 \
    --duration 180
```

#### Environment Variables
```bash
export BENCHMARK_API_BASE_URL="https://api.company.com"
export BENCHMARK_LOAD_TEST_USERS=50
export BENCHMARK_RESPONSE_TIME_THRESHOLD=300

python tools/benchmarking/scripts/run_benchmark.py --comprehensive
```

## Advanced Usage

### Scheduled Benchmarks

```bash
# Manual scheduled execution
python tools/benchmarking/scripts/scheduled_benchmark.py --type daily

# Hourly health check
python tools/benchmarking/scripts/scheduled_benchmark.py --type hourly

# Custom benchmark type
python tools/benchmarking/scripts/scheduled_benchmark.py \
    --type manual \
    --benchmark-type load_test
```

### Celery Integration

The benchmarking suite integrates with the existing Celery task queue:

```python
# Manual task execution
from app.workers.benchmark_tasks import run_scheduled_benchmark_task

result = run_scheduled_benchmark_task.delay("comprehensive", "production")
```

### Programmatic Usage

```python
import asyncio
from tools.benchmarking.core.benchmark_suite import BenchmarkSuite
from tools.benchmarking.core.benchmark_config import BenchmarkConfig

async def run_custom_benchmark():
    # Load configuration
    config = BenchmarkConfig(
        api_base_url="https://api.company.com",
        load_test_virtual_users=100,
        load_test_duration_seconds=300
    )

    # Create and run benchmark suite
    suite = BenchmarkSuite(config)
    result = await suite.run_comprehensive_benchmark()

    # Generate report
    report_path = await suite.generate_report(result, format="html")

    print(f"Benchmark completed - Score: {result.overall_score:.1f}/100")
    print(f"Report saved to: {report_path}")

# Run benchmark
asyncio.run(run_custom_benchmark())
```

### Real-time Dashboard Client

```javascript
// WebSocket client for real-time monitoring
const ws = new WebSocket('ws://localhost:8765');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    // Handle dashboard updates
    console.log('Performance metrics:', data.metrics);
    console.log('SLO status:', data.slos);
    console.log('Active alerts:', data.alerts);

    // Update UI
    updateDashboard(data);
};

// Request specific data
ws.send(JSON.stringify({
    type: 'get_trends',
    days: 7
}));

// Force refresh
ws.send(JSON.stringify({
    type: 'refresh'
}));
```

## Output and Reports

### Benchmark Results

Results are saved to `tools/benchmarking/results/`:

- JSON files with raw data
- Performance profiles (CPU, memory, I/O)
- Load test metrics and response times
- System information snapshots

### Reports

Reports are generated in `tools/benchmarking/reports/`:

- **HTML Reports** - Interactive reports with charts
- **PDF Reports** - Executive-friendly reports
- **Markdown Reports** - Text-based reports for documentation
- **JSON Data** - Raw data for integration

### Report Structure

```
tools/benchmarking/reports/
├── benchmark_report_20241125_143022.html
├── benchmark_report_20241125_143022.pdf
├── performance_gauge.png
├── response_times.png
├── cpu_usage.png
└── memory_usage.png
```

## Performance Metrics

### Key Performance Indicators

1. **Overall Performance Score** (0-100)
   - Comprehensive score across all metrics
   - Grade: Excellent/Good/Average/Poor/Critical

2. **Load Testing Metrics**
   - Requests per Second (RPS)
   - P95/P99 Response Times
   - Error Rate
   - Throughput

3. **Profiling Metrics**
   - CPU Usage (average, peak, P95)
   - Memory Usage (average, peak, leaks)
   - I/O Statistics
   - Identified Bottlenecks

4. **SLO Metrics**
   - Time-to-Ready Processing
   - Validation Pass Rate
   - System Availability
   - Error Budget Consumption

### Thresholds and Alerts

Default performance thresholds:

```json
{
  "response_time_threshold_ms": 500.0,
  "error_rate_threshold": 0.01,
  "cpu_usage_threshold": 0.8,
  "memory_usage_threshold": 0.85
}
```

Alerts are generated for:
- Critical performance degradation
- High error rates
- Resource exhaustion
- SLO threshold violations

## Integration with Existing Systems

### Metrics Service Integration

The benchmarking suite leverages the existing `metrics_service.py`:

- SLO definitions and measurements
- Historical performance data
- Alert generation and management
- Dashboard data sources

### API Integration

Benchmarking can test any API endpoint:

```python
# Custom endpoints for load testing
endpoints = [
    "/health",
    "/api/v1/invoices",
    "/api/v1/metrics/slos/dashboard",
    "/api/v1/validation/rules"
]
```

### Database Integration

System performance includes database metrics:

- Connection pool efficiency
- Query performance
- Database resource usage
- Transaction throughput

## Troubleshooting

### Common Issues

1. **k6 not found**
   ```bash
   # Install k6 or disable load testing
   python run_benchmark.py --comprehensive --no-load-test
   ```

2. **Permission errors**
   ```bash
   # Ensure write permissions for results directory
   chmod -R 755 tools/benchmarking/
   ```

3. **API connectivity issues**
   ```bash
   # Test API connectivity first
   curl -f http://localhost:8000/health
   ```

4. **Memory profiling errors**
   ```bash
   # Disable memory profiling if issues occur
   python run_benchmark.py --profile --cpu-only
   ```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with verbose output
python tools/benchmarking/scripts/run_benchmark.py --comprehensive --verbose
```

### Performance Analysis

1. **Review benchmark reports** - Check charts and metrics
2. **Examine bottlenecks** - Focus on identified performance issues
3. **Monitor trends** - Look for performance degradation over time
4. **Compare environments** - Validate performance across deployments

## Best Practices

### Benchmark Execution

1. **Use consistent environments** - Same data, same hardware
2. **Run multiple iterations** - Validate results are reproducible
3. **Monitor during benchmarks** - Watch for system issues
4. **Schedule appropriately** - Avoid peak business hours

### Result Analysis

1. **Focus on trends** - Single runs may vary
2. **Compare against baselines** - Track improvements over time
3. **Investigate anomalies** - Unusual results deserve investigation
4. **Document findings** - Maintain performance history

### Production Considerations

1. **Use read-only operations** - Don't modify production data
2. **Limit concurrent users** - Avoid impacting real users
3. **Monitor system health** - Stop if issues occur
4. **Communicate with teams** - Coordinate with operations

## Contributing

### Adding New Benchmark Types

1. Create new benchmark class inheriting from base components
2. Add configuration options to `BenchmarkConfig`
3. Update CLI arguments in `run_benchmark.py`
4. Add Celery task if needed
5. Update documentation

### Extending Reports

1. Modify `BenchmarkReporter` class
2. Add new chart types to `_generate_charts()`
3. Update HTML/markdown templates
4. Test new report formats

### Performance Monitoring

1. Add new metrics to `PerformanceMonitor`
2. Update WebSocket message formats
3. Enhance dashboard client integration
4. Add alerting rules

## Support

For questions or issues:

1. Check this documentation
2. Review existing benchmark results
3. Examine system logs
4. Contact the performance engineering team

---

## Performance Targets

Current system capabilities:

- **Processing Capacity**: 20,000 invoices/month
- **API Response Time**: <200ms (P95)
- **Load Testing**: >5,000 requests/minute
- **System Availability**: >99.5%
- **Automation Rate**: 85%

Use these targets when analyzing benchmark results and planning optimizations.