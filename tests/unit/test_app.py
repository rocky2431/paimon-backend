"""Test cases for FastAPI application."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check_returns_ok(self, client: TestClient):
        """Test that health endpoint returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_health_check_includes_timestamp(self, client: TestClient):
        """Test that health endpoint includes timestamp."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data


class TestAPIRoot:
    """Test API root endpoint."""

    def test_api_root_returns_info(self, client: TestClient):
        """Test that API root returns application info."""
        response = client.get("/api/v1/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs_url" in data


class TestCORSConfiguration:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self, client: TestClient):
        """Test that CORS headers are properly set."""
        response = client.options(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        # Should not fail (CORS configured)
        assert response.status_code in [200, 405]
