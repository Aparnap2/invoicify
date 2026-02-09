# Quick Start Guide

# # 🚀 Getting Started in 5 Minutes

## # 1. Start Test Infrastructure

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Start all services
./scripts/test-all.sh
```text
This will start:
- Temporal Server (port 7233)
- Redpanda Kafka (port 19092)
- Mockoon API Mocks (port 3000)
- MinIO (IBM COS compatible) (port 9000)

## # 2. Run Tests

```bash
# Run all tests
./scripts/test-all.sh

# Run unit tests only
./scripts/test-unit.sh

# Run integration tests
./scripts/test-integration.sh

# Run specific test
pytest temporal/tests/unit/test_anomaly_unit.py -v
```text
## # 3. Watch Mode (TDD)

```bash
# Auto-run tests on file changes
./scripts/test-watch.sh

# Watch specific pattern
./scripts/test-watch.sh test_anomaly
```text
## # 4. Access Services

| Service | URL | Credentials |
| --------- | ----- | ------------- |
| Temporal UI | http://localhost:8233 | - |
| Redpanda Console | http://localhost:8080 | - |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Mockoon | http://localhost:3000 | - |


## # 5. Stop Everything

```bash
docker-compose -f docker-compose.test.yml down -v
```text
# # 🧪 Test-Driven Development Workflow

## # Example: Adding a New Activity

```bash
# 1. Write the test first (RED)
# temporal/tests/unit/test_my_activity.py

async def test_my_activity_returns_correct_result():
    result = await my_activity(input_data)
    assert result['status'] == 'success'

# 2. Run the test (should fail)
pytest temporal/tests/unit/test_my_activity.py -v

# 3. Implement the activity (GREEN)
# temporal/activities/my_activity.py

async def my_activity(data: dict) -> dict:
    return {'status': 'success', 'data': process(data)}

# 4. Run the test (should pass)
pytest temporal/tests/unit/test_my_activity.py -v

# 5. Refactor and improve
# Add error handling, logging, etc.

# 6. Re-run all tests
./scripts/test-all.sh
```text
# # 📁 Project Structure

```text
invoicify/
├── docker-compose.test.yml    # Test infrastructure
├── Dockerfile.test            # Test runner image
├── requirements-test.txt      # Test dependencies
├── TDD_GUIDE.md              # Detailed TDD guide
├── scripts/
│   ├── test-all.sh           # Run all tests
│   ├── test-unit.sh          # Unit tests only
│   ├── test-integration.sh   # Integration tests
│   ├── test-e2e.sh          # E2E tests
│   └── test-watch.sh        # Watch mode
├── mocks/
│   └── groq-api.json        # Mockoon mock definitions
├── temporal/
│   ├── activities/          # Temporal activities
│   │   ├── anomaly.py       # River ML anomaly detection
│   │   ├── agents.py        # Analyst & Critic agents
│   │   └── __init__.py
│   ├── workflows/           # Temporal workflows
│   │   ├── invoice.py       # Main invoice workflow
│   │   └── __init__.py
│   ├── infrastructure/      # Infrastructure clients
│   │   ├── neo4j.py        # Neo4j client
│   │   └── __init__.py
│   ├── schemas.py          # Pydantic schemas
│   └── tests/
│       ├── unit/           # Unit tests
│       ├── integration/    # Integration tests
│       └── conftest.py     # Pytest config
```text
# # 🎯 Test Categories

## # Unit Tests
- Fast (< 100ms each)
- Isolated (mocked dependencies)
- Test single function/method
- File pattern: `test_*_unit.py`

## # Integration Tests
- Medium speed (< 1s each)
- Test with real services (Neo4j, Kafka)
- Test component interactions
- File pattern: `test_*_integration.py`

## # E2E Tests
- Slow (< 10s each)
- Full system flow
- Test from user perspective
- File pattern: `test_*_e2e.py`

# # 🔧 Common Commands

```bash
# Run with coverage
pytest --cov=temporal --cov=ai --cov-report=html

# Run with debug output
pytest -v --log-cli-level=DEBUG

# Run parallel (faster)
pytest -n auto

# Run specific test class
pytest temporal/tests/unit/test_anomaly_unit.py::TestAnomalyDetection -v

# Run with pdb on failure
pytest --pdb

# Run failed tests only
pytest --lf

# Run 10 times (flaky test check)
pytest --count=10 temporal/tests/unit/test_anomaly_unit.py
```text
# # 🐛 Troubleshooting

## # Tests failing with "Connection refused"
```bash
# Check if services are running
docker-compose -f docker-compose.test.yml ps

# Restart services
docker-compose -f docker-compose.test.yml restart
```text
## # Neo4j connection issues
```bash
# Check Neo4j is running on host

|  |


# Test connection
curl -v http://localhost:7687
```text
## # Import errors
```bash
# Rebuild test runner
docker-compose -f docker-compose.test.yml build test-runner
```text
# # 📊 Coverage Report

After running tests:

```bash
# Open coverage report
open htmlcov/index.html

# Or on Linux
xdg-open htmlcov/index.html
```text
# # 🎓 Learn More

- [TDD_GUIDE.md](TDD_GUIDE.md) - Detailed TDD documentation
- [DEV_PLAN.md](DEV_PLAN.md) - Development phases
- [ENTERPRISE_ARCHITECTURE.md](ENTERPRISE_ARCHITECTURE.md) - System design

# # 💡 Tips

1. **Write tests first** - Red, Green, Refactor
2. **One assertion per test** - Easier to debug
3. **Use descriptive names** - `test_anomaly_detector_flags_high_amounts`
4. **Mock external services** - Keep unit tests fast
5. **Run tests frequently** - Catch issues early
6. **Use watch mode** - Immediate feedback

Happy testing! 🧪
