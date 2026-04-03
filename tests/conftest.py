"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from llm_monitor.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)
