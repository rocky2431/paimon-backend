"""Rate limiting service using sliding window algorithm."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class RateLimitConfig(BaseModel):
    """Rate limit configuration."""

    requests_per_second: float = Field(default=10, description="Requests per second")
    requests_per_minute: float = Field(default=100, description="Requests per minute")
    requests_per_hour: float = Field(default=1000, description="Requests per hour")
    burst_size: int = Field(default=20, description="Maximum burst size")
    enabled: bool = Field(default=True, description="Enable rate limiting")


class RateLimitResult(BaseModel):
    """Result of rate limit check."""

    allowed: bool = Field(..., description="Whether request is allowed")
    remaining: int = Field(..., description="Remaining requests in window")
    reset_at: float = Field(..., description="Timestamp when limit resets")
    retry_after: float | None = Field(None, description="Seconds to wait before retry")
    limit: int = Field(..., description="Current limit")


@dataclass
class SlidingWindow:
    """Sliding window for rate limiting."""

    window_size_seconds: float
    max_requests: int
    requests: list[float] = field(default_factory=list)

    def add_request(self, timestamp: float) -> bool:
        """Add a request and check if allowed.

        Args:
            timestamp: Current timestamp

        Returns:
            True if request allowed
        """
        # Remove old requests outside window
        window_start = timestamp - self.window_size_seconds
        self.requests = [t for t in self.requests if t > window_start]

        # Check limit
        if len(self.requests) >= self.max_requests:
            return False

        # Add new request
        self.requests.append(timestamp)
        return True

    def remaining(self, timestamp: float) -> int:
        """Get remaining requests in window.

        Args:
            timestamp: Current timestamp

        Returns:
            Remaining request count
        """
        window_start = timestamp - self.window_size_seconds
        current_count = sum(1 for t in self.requests if t > window_start)
        return max(0, self.max_requests - current_count)

    def reset_at(self, timestamp: float) -> float:
        """Get when the window resets.

        Args:
            timestamp: Current timestamp

        Returns:
            Reset timestamp
        """
        if not self.requests:
            return timestamp

        oldest_in_window = min(t for t in self.requests if t > timestamp - self.window_size_seconds)
        return oldest_in_window + self.window_size_seconds


class RateLimiter:
    """Service for rate limiting requests."""

    def __init__(self, config: RateLimitConfig | None = None):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        self._windows: dict[str, dict[str, SlidingWindow]] = defaultdict(dict)

    def _get_windows(self, key: str) -> dict[str, SlidingWindow]:
        """Get or create windows for a key.

        Args:
            key: Identifier (IP, user ID, etc.)

        Returns:
            Dict of windows
        """
        if key not in self._windows:
            self._windows[key] = {
                "second": SlidingWindow(
                    window_size_seconds=1,
                    max_requests=int(self.config.requests_per_second),
                ),
                "minute": SlidingWindow(
                    window_size_seconds=60,
                    max_requests=int(self.config.requests_per_minute),
                ),
                "hour": SlidingWindow(
                    window_size_seconds=3600,
                    max_requests=int(self.config.requests_per_hour),
                ),
            }
        return self._windows[key]

    def check(self, key: str) -> RateLimitResult:
        """Check if request is allowed.

        Args:
            key: Identifier (IP, user ID, etc.)

        Returns:
            Rate limit result
        """
        if not self.config.enabled:
            return RateLimitResult(
                allowed=True,
                remaining=self.config.burst_size,
                reset_at=time.time(),
                limit=self.config.burst_size,
            )

        now = time.time()
        windows = self._get_windows(key)

        # Check all windows
        for window_name, window in windows.items():
            if not window.add_request(now):
                remaining = window.remaining(now)
                reset_at = window.reset_at(now)

                return RateLimitResult(
                    allowed=False,
                    remaining=remaining,
                    reset_at=reset_at,
                    retry_after=reset_at - now,
                    limit=window.max_requests,
                )

        # Find the most restrictive remaining count
        min_remaining = min(w.remaining(now) for w in windows.values())

        return RateLimitResult(
            allowed=True,
            remaining=min_remaining,
            reset_at=now + 1,  # Next second
            limit=int(self.config.requests_per_second),
        )

    def is_allowed(self, key: str) -> bool:
        """Quick check if request is allowed.

        Args:
            key: Identifier

        Returns:
            True if allowed
        """
        return self.check(key).allowed

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for a key.

        Args:
            key: Identifier

        Returns:
            Remaining count
        """
        if key not in self._windows:
            return int(self.config.requests_per_second)

        now = time.time()
        windows = self._windows[key]
        return min(w.remaining(now) for w in windows.values())

    def reset(self, key: str) -> None:
        """Reset rate limit for a key.

        Args:
            key: Identifier
        """
        if key in self._windows:
            del self._windows[key]

    def reset_all(self) -> None:
        """Reset all rate limits."""
        self._windows.clear()

    def update_config(self, config: RateLimitConfig) -> None:
        """Update rate limit configuration.

        Args:
            config: New configuration
        """
        self.config = config
        # Reset all windows with new config
        self._windows.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics.

        Returns:
            Statistics dict
        """
        return {
            "enabled": self.config.enabled,
            "tracked_keys": len(self._windows),
            "config": {
                "requests_per_second": self.config.requests_per_second,
                "requests_per_minute": self.config.requests_per_minute,
                "requests_per_hour": self.config.requests_per_hour,
                "burst_size": self.config.burst_size,
            },
        }


# Singleton instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance.

    Returns:
        The rate limiter
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
