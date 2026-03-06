"""Pytest configuration and fixtures for agent-core tests.

Sets up Python path and common fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

# Add src to Python path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"
