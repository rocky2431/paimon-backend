"""Tests for security services."""

import time
from datetime import datetime, timedelta

import pytest

from app.services.security import (
    IPFilter,
    IPFilterConfig,
    RateLimiter,
    RateLimitConfig,
    get_ip_filter,
    get_rate_limiter,
)


class TestRateLimiter:
    """Tests for rate limiter."""

    @pytest.fixture
    def limiter(self):
        """Create rate limiter."""
        config = RateLimitConfig(
            requests_per_second=5,
            requests_per_minute=20,
            requests_per_hour=100,
        )
        return RateLimiter(config)

    def test_allow_requests_under_limit(self, limiter):
        """Test allowing requests under limit."""
        for _ in range(5):
            result = limiter.check("test-ip")
            assert result.allowed is True

    def test_block_requests_over_limit(self, limiter):
        """Test blocking requests over limit."""
        # Use up the per-second limit
        for _ in range(5):
            limiter.check("test-ip")

        # Next request should be blocked
        result = limiter.check("test-ip")
        assert result.allowed is False
        assert result.retry_after is not None
        assert result.retry_after > 0

    def test_different_keys_independent(self, limiter):
        """Test different keys are independent."""
        # Use up limit for ip1
        for _ in range(5):
            limiter.check("ip1")

        # ip2 should still work
        result = limiter.check("ip2")
        assert result.allowed is True

    def test_remaining_count(self, limiter):
        """Test remaining request count."""
        assert limiter.get_remaining("test-ip") == 5

        limiter.check("test-ip")
        limiter.check("test-ip")

        assert limiter.get_remaining("test-ip") == 3

    def test_reset(self, limiter):
        """Test resetting rate limit."""
        # Use up limit
        for _ in range(5):
            limiter.check("test-ip")

        # Reset
        limiter.reset("test-ip")

        # Should be allowed again
        result = limiter.check("test-ip")
        assert result.allowed is True

    def test_reset_all(self, limiter):
        """Test resetting all limits."""
        limiter.check("ip1")
        limiter.check("ip2")

        limiter.reset_all()

        assert limiter.get_remaining("ip1") == 5
        assert limiter.get_remaining("ip2") == 5

    def test_is_allowed(self, limiter):
        """Test quick allowed check."""
        assert limiter.is_allowed("test-ip") is True

        # Use up limit
        for _ in range(5):
            limiter.check("test-ip")

        assert limiter.is_allowed("test-ip") is False

    def test_disabled_limiter(self):
        """Test disabled rate limiter."""
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config)

        # Should always allow
        for _ in range(100):
            result = limiter.check("test-ip")
            assert result.allowed is True

    def test_update_config(self, limiter):
        """Test updating configuration."""
        new_config = RateLimitConfig(requests_per_second=100)
        limiter.update_config(new_config)

        assert limiter.config.requests_per_second == 100

    def test_get_stats(self, limiter):
        """Test getting statistics."""
        limiter.check("ip1")
        limiter.check("ip2")

        stats = limiter.get_stats()

        assert stats["enabled"] is True
        assert stats["tracked_keys"] == 2


class TestIPFilter:
    """Tests for IP filter."""

    @pytest.fixture
    def ip_filter(self):
        """Create IP filter."""
        config = IPFilterConfig(
            enabled=True,
            mode="whitelist",
            allow_private=True,
            allow_localhost=True,
        )
        return IPFilter(config)

    def test_allow_localhost(self, ip_filter):
        """Test allowing localhost."""
        assert ip_filter.is_allowed("127.0.0.1") is True
        assert ip_filter.is_allowed("::1") is True

    def test_allow_private_ips(self, ip_filter):
        """Test allowing private IPs."""
        assert ip_filter.is_allowed("192.168.1.1") is True
        assert ip_filter.is_allowed("10.0.0.1") is True
        assert ip_filter.is_allowed("172.16.0.1") is True

    def test_whitelist_mode(self, ip_filter):
        """Test whitelist mode."""
        # Add to whitelist
        ip_filter.add_to_whitelist("8.8.8.8")

        # Only whitelisted IPs allowed
        assert ip_filter.is_allowed("8.8.8.8") is True
        assert ip_filter.is_allowed("1.1.1.1") is False

    def test_blacklist_mode(self):
        """Test blacklist mode."""
        config = IPFilterConfig(mode="blacklist", allow_private=False, allow_localhost=False)
        ip_filter = IPFilter(config)

        ip_filter.add_to_blacklist("1.1.1.1")

        assert ip_filter.is_allowed("8.8.8.8") is True
        assert ip_filter.is_allowed("1.1.1.1") is False

    def test_cidr_range_whitelist(self, ip_filter):
        """Test CIDR range in whitelist."""
        ip_filter.add_to_whitelist("203.0.113.0/24")

        assert ip_filter.is_allowed("203.0.113.1") is True
        assert ip_filter.is_allowed("203.0.113.254") is True
        assert ip_filter.is_allowed("203.0.114.1") is False

    def test_cidr_range_blacklist(self):
        """Test CIDR range in blacklist."""
        config = IPFilterConfig(mode="blacklist", allow_private=False, allow_localhost=False)
        ip_filter = IPFilter(config)

        ip_filter.add_to_blacklist("192.0.2.0/24")

        assert ip_filter.is_allowed("192.0.2.1") is False
        assert ip_filter.is_allowed("192.0.3.1") is True

    def test_add_invalid_ip(self, ip_filter):
        """Test adding invalid IP."""
        success = ip_filter.add_to_whitelist("invalid-ip")
        assert success is False

    def test_remove_from_whitelist(self, ip_filter):
        """Test removing from whitelist."""
        ip_filter.add_to_whitelist("8.8.8.8")
        ip_filter.add_to_whitelist("1.1.1.1")

        ip_filter.remove_from_whitelist("8.8.8.8")

        assert len(ip_filter.get_whitelist()) == 1

    def test_remove_from_blacklist(self):
        """Test removing from blacklist."""
        config = IPFilterConfig(mode="blacklist")
        ip_filter = IPFilter(config)

        ip_filter.add_to_blacklist("8.8.8.8")
        ip_filter.remove_from_blacklist("8.8.8.8")

        assert len(ip_filter.get_blacklist()) == 0

    def test_entry_expiration(self, ip_filter):
        """Test entry expiration."""
        # Add with past expiration
        expires_at = datetime.now() - timedelta(hours=1)
        ip_filter._whitelist.append(
            type(ip_filter._whitelist[0] if ip_filter._whitelist else None) or
            type("IPEntry", (), {
                "ip_or_range": "8.8.8.8",
                "description": "",
                "added_at": datetime.now(),
                "added_by": "test",
                "expires_at": expires_at,
            })
        )

        # Expired entry should not match
        from app.services.security.ip_filter import IPEntry

        ip_filter._whitelist = [
            IPEntry(ip_or_range="8.8.8.8", expires_at=expires_at)
        ]

        entries = ip_filter.get_whitelist()
        assert len(entries) == 0

    def test_clear_whitelist(self, ip_filter):
        """Test clearing whitelist."""
        ip_filter.add_to_whitelist("8.8.8.8")
        ip_filter.add_to_whitelist("1.1.1.1")

        count = ip_filter.clear_whitelist()

        assert count == 2
        assert len(ip_filter.get_whitelist()) == 0

    def test_clear_blacklist(self):
        """Test clearing blacklist."""
        config = IPFilterConfig(mode="blacklist")
        ip_filter = IPFilter(config)

        ip_filter.add_to_blacklist("8.8.8.8")

        count = ip_filter.clear_blacklist()

        assert count == 1
        assert len(ip_filter.get_blacklist()) == 0

    def test_disabled_filter(self):
        """Test disabled IP filter."""
        config = IPFilterConfig(enabled=False)
        ip_filter = IPFilter(config)

        # Should allow all
        assert ip_filter.is_allowed("8.8.8.8") is True
        assert ip_filter.is_allowed("1.2.3.4") is True

    def test_update_config(self, ip_filter):
        """Test updating configuration."""
        new_config = IPFilterConfig(mode="blacklist")
        ip_filter.update_config(new_config)

        assert ip_filter.config.mode == "blacklist"

    def test_get_stats(self, ip_filter):
        """Test getting statistics."""
        ip_filter.add_to_whitelist("8.8.8.8")

        stats = ip_filter.get_stats()

        assert stats["enabled"] is True
        assert stats["mode"] == "whitelist"
        assert stats["whitelist_count"] == 1


class TestSingletons:
    """Tests for singleton patterns."""

    def test_get_rate_limiter_singleton(self):
        """Test rate limiter singleton."""
        import app.services.security.rate_limiter as rate_limiter_module

        rate_limiter_module._rate_limiter = None

        r1 = get_rate_limiter()
        r2 = get_rate_limiter()

        assert r1 is r2

    def test_get_ip_filter_singleton(self):
        """Test IP filter singleton."""
        import app.services.security.ip_filter as ip_filter_module

        ip_filter_module._ip_filter = None

        f1 = get_ip_filter()
        f2 = get_ip_filter()

        assert f1 is f2
