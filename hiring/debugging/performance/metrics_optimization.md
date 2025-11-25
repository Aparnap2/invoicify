# Performance Debugging Challenge: Metrics System Optimization

## 🎯 Challenge Overview

You are tasked with optimizing a production metrics collection system that is experiencing severe performance degradation. The system processes millions of invoice processing events and must maintain high throughput while providing real-time analytics.

## 📋 Problem Context

### Current System Performance Issues

The metrics collection system is showing concerning performance patterns:

- **Response Times**: API endpoints showing P95 > 2s (target: <200ms)
- **Database Load**: CPU usage consistently >80% during peak hours
- **Memory Usage**: Gradual memory leaks causing OOM restarts
- **Throughput**: Processing capacity degraded by 60% over last month
- **Alerting**: Frequent timeout alerts and SLO breaches

### Business Impact

- **SLA Breaches**: Missing 99.9% uptime targets
- **User Experience**: Slow dashboard loading affecting operations
- **Data Quality**: Delayed metrics affecting business decisions
- **Cost Overruns**: Increased infrastructure costs due to scaling issues

## 📊 Current Metrics Data

```json
{
  "system_metrics": {
    "api_response_times": {
      "p50": "450ms",
      "p95": "2.1s",
      "p99": "4.8s",
      "target_p95": "200ms"
    },
    "database_performance": {
      "cpu_utilization": "85%",
      "connection_pool_usage": "95%",
      "query_duration_p95": "1.2s",
      "slow_queries_per_hour": 450
    },
    "memory_usage": {
      "heap_usage": "8.2GB / 10GB",
      "gc_pause_times": "200ms avg",
      "oom_events_per_day": 3
    },
    "throughput_metrics": {
      "events_per_second": "150 (target: 500)",
      "processing_lag": "45 minutes",
      "backlog_size": "1.2M events"
    }
  },
  "recent_incidents": [
    {
      "timestamp": "2024-01-15T14:30:00Z",
      "type": "high_response_time",
      "duration": "45 minutes",
      "impact": "dashboard_unavailable"
    },
    {
      "timestamp": "2024-01-15T16:45:00Z",
      "type": "database_timeout",
      "duration": "12 minutes",
      "impact": "data_processing_halted"
    }
  ]
}
```

## 🔍 Problem Areas to Investigate

### 1. Database Performance Issues
```sql
-- Sample problematic queries (from slow query log)
QUERY 1: SELECT * FROM invoice_metrics
        WHERE created_at >= '2024-01-15 00:00:00'
        AND created_at < '2024-01-16 00:00:00'
        ORDER BY created_at DESC
        LIMIT 1000;

QUERY 2: SELECT
           DATE_TRUNC('hour', created_at) as hour,
           COUNT(*) as count,
           AVG(processing_time) as avg_time
        FROM invoice_metrics
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY DATE_TRUNC('hour', created_at);

QUERY 3: SELECT * FROM system_metrics
        WHERE metric_name IN ('api_latency', 'db_connections')
        AND measurement_timestamp >= NOW() - INTERVAL '1 hour'
        ORDER BY measurement_timestamp DESC;
```

### 2. Application Code Issues
```python
# Current implementation with performance issues (simplified)

class MetricsService:
    def __init__(self):
        self.db_session = None
        self.cache = {}
        self.metrics_buffer = []

    async def record_invoice_metric(self, invoice_id, data):
        """PROBLEM: Synchronous database operations in async context"""
        # Create database connection for each call
        session = create_db_session()

        # Expensive object creation for every metric
        metric = InvoiceMetric(
            invoice_id=invoice_id,
            # ... 20+ fields being set individually
            processing_metadata=json.dumps(data),
            created_at=datetime.utcnow()
        )

        # Synchronous database write
        session.add(metric)
        session.commit()
        session.close()

        # PROBLEM: Expensive calculation in hot path
        await self._calculate_comprehensive_metrics(invoice_id)

    async def get_metrics_dashboard(self, time_range_days=30):
        """PROBLEM: Inefficient data fetching and processing"""

        # PROBLEM: Fetching way more data than needed
        session = create_db_session()

        # Inefficient query - no pagination, no indexing
        all_metrics = session.query(InvoiceMetric).filter(
            InvoiceMetric.created_at >= datetime.utcnow() - timedelta(days=time_range_days)
        ).all()

        # PROBLEM: Processing all data in memory
        dashboard_data = {
            'total_invoices': len(all_metrics),
            'avg_processing_time': sum(m.processing_time for m in all_metrics) / len(all_metrics),
            # ... more expensive in-memory calculations
        }

        session.close()
        return dashboard_data

    async def _calculate_comprehensive_metrics(self, invoice_id):
        """PROBLEM: Complex calculations in request path"""

        # Expensive aggregation queries
        session = create_db_session()

        # Multiple database calls for single calculation
        total_invoices = session.query(func.count(Invoice.id)).scalar()
        successful_invoices = session.query(func.count(Invoice.id)).filter(
            Invoice.status == 'completed'
        ).scalar()

        # Complex business logic calculations
        success_rate = (successful_invoices / total_invoices) * 100 if total_invoices > 0 else 0

        # More expensive calculations...
        hourly_stats = self._calculate_hourly_statistics(session)
        vendor_performance = self._calculate_vendor_performance(session)

        session.close()
```

### 3. System Configuration Issues
```yaml
# Current problematic configuration
database:
  max_connections: 20  # Too low for concurrent load
  connection_timeout: 5s  # Too aggressive
  query_timeout: 30s  # Too long for user-facing APIs

application:
  worker_processes: 2  # Under-provisioned
  max_memory_usage: 1GB  # Too small
  buffer_size: 1000  # Too small for burst traffic

cache:
  ttl: 300s  # Too short for frequently accessed data
  max_memory: 100MB  # Too small

monitoring:
  metrics_retention: 90d  # Too long, causing storage bloat
  sampling_rate: 100%  # Too high for production
```

## 🎯 Your Optimization Tasks

### Task 1: Database Optimization (30 points)

**Identify and fix database performance issues:**

1. **Query Optimization**
   - Analyze slow queries and add proper indexes
   - Implement query result pagination
   - Optimize JOIN operations and subqueries
   - Add database connection pooling

2. **Schema Optimization**
   - Review table structures for efficiency
   - Implement proper partitioning strategies
   - Optimize data types and constraints
   - Add appropriate indexes

3. **Connection Management**
   - Implement connection pooling with proper sizing
   - Add connection health checks
   - Optimize transaction scope and duration
   - Implement read/write splitting if applicable

### Task 2: Application Code Optimization (30 points)

**Optimize the Python application code:**

1. **Async/Await Optimization**
   - Fix blocking calls in async contexts
   - Implement proper async database operations
   - Optimize concurrent processing patterns
   - Add proper error handling and cancellation

2. **Memory Management**
   - Identify and fix memory leaks
   - Optimize object creation and garbage collection
   - Implement efficient data structures
   - Add memory usage monitoring

3. **Caching Strategy**
   - Implement multi-level caching
   - Add cache warming and invalidation
   - Optimize cache hit ratios
   - Implement cache-aside patterns

### Task 3: System Architecture Optimization (25 points)

**Optimize the overall system architecture:**

1. **Scaling Strategy**
   - Implement horizontal scaling
   - Add load balancing and distribution
   - Optimize resource allocation
   - Implement auto-scaling policies

2. **Data Processing Pipeline**
   - Implement streaming data processing
   - Add batch processing optimization
   - Optimize data serialization/deserialization
   - Implement backpressure handling

3. **Monitoring and Observability**
   - Add comprehensive performance monitoring
   - Implement distributed tracing
   - Optimize metrics collection overhead
   - Add automated alerting

### Task 4: Performance Testing and Validation (15 points)

**Validate your optimizations:**

1. **Load Testing**
   - Create realistic load testing scenarios
   - Measure performance improvements
   - Validate scaling behavior
   - Test failure scenarios

2. **Benchmarking**
   - Establish performance baselines
   - Measure optimization impact
   - Create performance regression tests
   - Document performance characteristics

## 📊 Success Metrics

Your optimizations should achieve:

- **API Response Times**: P95 < 200ms (from 2.1s)
- **Database CPU**: < 60% (from 85%)
- **Throughput**: 500+ events/second (from 150)
- **Memory Usage**: Stable without leaks
- **System Uptime**: >99.9%

## 🛠️ Available Tools

- **Database**: PostgreSQL with EXPLAIN ANALYZE
- **Monitoring**: Prometheus metrics and Grafana dashboards
- **Profiling**: Python cProfile and memory profilers
- **Load Testing**: Locust or k6
- **Tracing**: OpenTelemetry instrumentation

## 💡 Hints and Considerations

### Database Optimization
- Look for missing indexes on frequently queried columns
- Consider materialized views for complex aggregations
- Implement proper connection pooling (pgbouncer)
- Use database partitioning for large time-series data

### Application Optimization
- Use async database drivers (asyncpg)
- Implement connection pooling at application level
- Consider Redis for caching frequently accessed data
- Use generator patterns for large result sets

### Architecture Patterns
- Implement write-behind patterns for metric writes
- Use message queues for asynchronous processing
- Consider CQRS for read/write separation
- Implement circuit breakers for external dependencies

## 🧪 Testing Requirements

Validate your optimizations with:

1. **Performance Tests**: Load testing with realistic traffic patterns
2. **Memory Tests**: Long-running tests for leak detection
3. **Database Tests**: Query performance and connection pool testing
4. **Integration Tests**: End-to-end performance validation
5. **Regression Tests**: Ensure optimizations don't break functionality

## 📚 Reference Materials

- [Database Performance Tuning](https://www.postgresql.org/docs/current/performance-tips.html)
- [Async Python Best Practices](https://docs.python.org/3/library/asyncio.html)
- [System Performance Tuning](https://sre.google/resources/practical-guide-to-sre/)
- [Performance Testing Patterns](https://loadtesting.pub/)

---

**Time Limit**: 3 hours
**Difficulty**: 🔴 Expert
**Focus**: Performance engineering and system optimization