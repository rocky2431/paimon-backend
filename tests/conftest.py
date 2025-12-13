"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    """Create FastAPI application for testing."""
    from app.main import create_app

    return create_app()


@pytest.fixture(scope="session")
def client(app):
    """Create test client."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def settings():
    """Create settings instance for testing."""
    from app.core.config import Settings

    return Settings(environment="testing")
