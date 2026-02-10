"""Pytest configuration for Temporal tests."""

import pytest
import asyncio
from typing import Generator


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow tests")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temporal_client():
    """Temporal client fixture."""
    from temporalio.client import Client

    client = await Client.connect("temporal:7233", namespace="default")
    yield client


@pytest.fixture
async def neo4j_client():
    """Neo4j client fixture."""
    from temporal.infrastructure.neo4j import Neo4jClient

    client = Neo4jClient()
    yield client
    await client.close()


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set default environment variables for tests."""
    monkeypatch.setenv("TEMPORAL_HOST", "temporal:7233")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "default")
    monkeypatch.setenv("REDPANDA_HOST", "redpanda:9092")
    monkeypatch.setenv("MOCKOON_HOST", "mockoon:3000")
    monkeypatch.setenv("IBM_COS_BUCKET", "nivi-lake-prod")
    monkeypatch.setenv("NEO4J_URI", "bolt://host.docker.internal:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "founderos_secret")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_BASE_URL", "http://mockoon:3000/openai/v1")
