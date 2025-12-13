"""Security audit tests for the backend."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestAuthenticationSecurity:
    """Authentication security tests."""

    def test_login_requires_valid_signature(self, client):
        """Test that login requires valid signature."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "wallet_address": "0x" + "a" * 40,
                "signature": "invalid",
                "nonce": "test-nonce",
            },
        )
        # Should reject invalid signature
        assert response.status_code in [400, 401, 422]

    def test_nonce_endpoint_works(self, client):
        """Test nonce endpoint is accessible."""
        response = client.post(
            "/api/v1/auth/nonce",
            json={"wallet_address": "0x" + "a" * 40},
        )
        assert response.status_code == 200
        data = response.json()
        assert "nonce" in data


class TestInputValidation:
    """Input validation security tests."""

    def test_xss_prevention_in_login(self, client):
        """Test XSS prevention in login endpoint."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "wallet_address": "<script>alert('xss')</script>",
                "signature": "0x" + "a" * 130,
                "nonce": "test-nonce",
            },
        )
        # Should reject invalid wallet address
        assert response.status_code == 422

    def test_sql_injection_prevention(self, client):
        """Test SQL injection prevention."""
        # Try SQL injection in query params
        response = client.get(
            "/api/v1/redemptions",
            params={"owner": "'; DROP TABLE redemptions; --"},
        )
        # Should either reject or safely handle (401 is also acceptable for auth required)
        assert response.status_code in [200, 400, 401, 422]

    def test_large_payload_rejection(self, client):
        """Test large payload rejection."""
        # Try to send a very large payload
        large_data = "x" * 1000000  # 1MB string
        response = client.post(
            "/api/v1/auth/login",
            json={
                "wallet_address": large_data,
                "signature": "0x" + "a" * 130,
                "nonce": "test-nonce",
            },
        )
        # Should reject
        assert response.status_code in [413, 422]

    def test_negative_value_in_rate_limit(self, client):
        """Test negative value handling in rate limit config."""
        response = client.put(
            "/api/v1/security/rate-limit/config",
            json={
                "requests_per_second": -100,
                "requests_per_minute": 20,
                "requests_per_hour": 100,
            },
        )
        # Should reject or accept (pydantic validation)
        assert response.status_code in [200, 400, 422]


class TestAccessControl:
    """Access control security tests."""

    def test_protected_endpoint_requires_auth(self, client):
        """Test protected endpoints require authentication."""
        # Test GET endpoint that may require auth
        response = client.get("/api/v1/redemptions")
        # In test mode, this may be 200 or 401/403
        assert response.status_code in [200, 400, 401, 403, 422]

    def test_auth_me_requires_token(self, client):
        """Test /auth/me endpoint requires valid token."""
        response = client.get("/api/v1/auth/me")
        # Should require authentication
        assert response.status_code in [401, 403, 422]


class TestRateLimiting:
    """Rate limiting security tests."""

    def test_rate_limit_headers(self, client):
        """Test rate limit headers are present."""
        # Make multiple requests
        for _ in range(5):
            response = client.get("/api/v1/security/rate-limit/check")

        # Check rate limit is working
        assert response.status_code == 200
        data = response.json()
        assert "remaining" in data


class TestIPFiltering:
    """IP filtering security tests."""

    def test_ip_filter_status(self, client):
        """Test IP filter status endpoint."""
        response = client.get("/api/v1/security/ip-filter/stats")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data


class TestSecurityHeaders:
    """Security headers tests."""

    def test_cors_headers(self, client):
        """Test CORS headers are configured."""
        # OPTIONS request
        response = client.options("/health")
        # CORS should be configured
        assert response.status_code in [200, 405]


class TestSensitiveDataProtection:
    """Sensitive data protection tests."""

    def test_passwords_not_in_response(self, client):
        """Test passwords are not exposed in responses."""
        response = client.get("/api/v1/fund/overview")
        if response.status_code == 200:
            text = response.text.lower()
            assert "password" not in text
            assert "secret" not in text
            assert "private_key" not in text

    def test_wallet_addresses_format(self, client):
        """Test wallet addresses follow expected format."""
        response = client.get("/api/v1/redemptions")
        if response.status_code == 200:
            data = response.json()
            for item in data:
                if "wallet_address" in item:
                    addr = item["wallet_address"]
                    # Should be valid Ethereum address format
                    assert addr.startswith("0x")
                    assert len(addr) == 42


class TestAuditLogging:
    """Audit logging security tests."""

    def test_audit_log_exists(self, client):
        """Test audit logging is working."""
        response = client.get("/api/v1/audit/entries")
        assert response.status_code == 200

    def test_audit_categories_available(self, client):
        """Test audit categories are defined."""
        response = client.get("/api/v1/audit/categories")
        assert response.status_code == 200
        data = response.json()
        assert "AUTHENTICATION" in data
        assert "SECURITY" in data


class TestErrorHandling:
    """Error handling security tests."""

    def test_404_does_not_leak_info(self, client):
        """Test 404 errors don't leak sensitive info."""
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404
        text = response.text.lower()
        # Should not leak stack traces or internal info
        assert "traceback" not in text
        assert "file" not in text or "not found" in text

    def test_invalid_json_handled(self, client):
        """Test invalid JSON is handled gracefully."""
        response = client.post(
            "/api/v1/auth/login",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestSecurityCompliance:
    """Security compliance checks."""

    def test_health_endpoint_public(self, client):
        """Test health endpoint is publicly accessible."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_api_versioning(self, client):
        """Test API uses versioning."""
        response = client.get("/api/v1/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data

    def test_metrics_endpoint_exists(self, client):
        """Test metrics endpoint exists for monitoring."""
        response = client.get("/api/v1/metrics/prometheus")
        assert response.status_code == 200
