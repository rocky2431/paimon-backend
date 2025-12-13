"""System health checker service."""

import asyncio
import logging
import platform
import psutil
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class ComponentHealth(BaseModel):
    """Health status of a component."""

    name: str = Field(..., description="Component name")
    status: HealthStatus = Field(..., description="Health status")
    message: str | None = Field(None, description="Status message")
    latency_ms: float | None = Field(None, description="Response latency in ms")
    last_check: datetime = Field(..., description="Last check timestamp")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional details")


class SystemHealth(BaseModel):
    """Overall system health."""

    status: HealthStatus = Field(..., description="Overall status")
    version: str = Field(..., description="Application version")
    uptime_seconds: float = Field(..., description="Uptime in seconds")
    timestamp: datetime = Field(..., description="Check timestamp")
    components: list[ComponentHealth] = Field(..., description="Component statuses")
    system_info: dict[str, Any] = Field(default_factory=dict, description="System info")


class HealthChecker:
    """Service for checking system health."""

    def __init__(self, version: str = "1.0.0"):
        """Initialize health checker.

        Args:
            version: Application version
        """
        self.version = version
        self._start_time = time.time()
        self._health_checks: dict[str, Callable] = {}
        self._last_results: dict[str, ComponentHealth] = {}

        # Register default checks
        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Register default health checks."""
        self.register_check("memory", self._check_memory)
        self.register_check("disk", self._check_disk)
        self.register_check("cpu", self._check_cpu)

    def register_check(
        self,
        name: str,
        check_fn: Callable[[], ComponentHealth],
    ) -> None:
        """Register a health check.

        Args:
            name: Check name
            check_fn: Function that returns ComponentHealth
        """
        self._health_checks[name] = check_fn

    def unregister_check(self, name: str) -> bool:
        """Unregister a health check.

        Args:
            name: Check name

        Returns:
            True if removed
        """
        if name in self._health_checks:
            del self._health_checks[name]
            return True
        return False

    async def check_all(self) -> SystemHealth:
        """Run all health checks.

        Returns:
            System health status
        """
        components: list[ComponentHealth] = []
        overall_status = HealthStatus.HEALTHY

        for name, check_fn in self._health_checks.items():
            try:
                start = time.time()
                result = check_fn()
                result.latency_ms = (time.time() - start) * 1000
                components.append(result)
                self._last_results[name] = result

                # Determine overall status
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status != HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.DEGRADED

            except Exception as e:
                logger.error(f"Health check {name} failed: {e}")
                component = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message=str(e),
                    last_check=datetime.now(),
                )
                components.append(component)
                overall_status = HealthStatus.DEGRADED

        return SystemHealth(
            status=overall_status,
            version=self.version,
            uptime_seconds=time.time() - self._start_time,
            timestamp=datetime.now(),
            components=components,
            system_info=self._get_system_info(),
        )

    async def check_component(self, name: str) -> ComponentHealth | None:
        """Check a specific component.

        Args:
            name: Component name

        Returns:
            Component health or None
        """
        check_fn = self._health_checks.get(name)
        if not check_fn:
            return None

        try:
            start = time.time()
            result = check_fn()
            result.latency_ms = (time.time() - start) * 1000
            self._last_results[name] = result
            return result
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=str(e),
                last_check=datetime.now(),
            )

    def get_last_result(self, name: str) -> ComponentHealth | None:
        """Get last check result for component.

        Args:
            name: Component name

        Returns:
            Last result or None
        """
        return self._last_results.get(name)

    def _check_memory(self) -> ComponentHealth:
        """Check memory usage."""
        memory = psutil.virtual_memory()
        percent_used = memory.percent

        if percent_used > 90:
            status = HealthStatus.UNHEALTHY
            message = f"Critical memory usage: {percent_used}%"
        elif percent_used > 80:
            status = HealthStatus.DEGRADED
            message = f"High memory usage: {percent_used}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Memory usage: {percent_used}%"

        return ComponentHealth(
            name="memory",
            status=status,
            message=message,
            last_check=datetime.now(),
            details={
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": percent_used,
            },
        )

    def _check_disk(self) -> ComponentHealth:
        """Check disk usage."""
        disk = psutil.disk_usage("/")
        percent_used = disk.percent

        if percent_used > 95:
            status = HealthStatus.UNHEALTHY
            message = f"Critical disk usage: {percent_used}%"
        elif percent_used > 85:
            status = HealthStatus.DEGRADED
            message = f"High disk usage: {percent_used}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk usage: {percent_used}%"

        return ComponentHealth(
            name="disk",
            status=status,
            message=message,
            last_check=datetime.now(),
            details={
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": percent_used,
            },
        )

    def _check_cpu(self) -> ComponentHealth:
        """Check CPU usage."""
        cpu_percent = psutil.cpu_percent(interval=0.1)

        if cpu_percent > 90:
            status = HealthStatus.DEGRADED
            message = f"High CPU usage: {cpu_percent}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"CPU usage: {cpu_percent}%"

        return ComponentHealth(
            name="cpu",
            status=status,
            message=message,
            last_check=datetime.now(),
            details={
                "usage_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "load_avg": list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [],
            },
        )

    def _get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
        }

    @property
    def uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self._start_time

    def is_healthy(self) -> bool:
        """Quick health check.

        Returns:
            True if all recent checks are healthy
        """
        if not self._last_results:
            return True

        return all(
            r.status in (HealthStatus.HEALTHY, HealthStatus.UNKNOWN)
            for r in self._last_results.values()
        )


# Singleton instance
_health_checker: HealthChecker | None = None


def get_health_checker() -> HealthChecker:
    """Get singleton health checker instance.

    Returns:
        The health checker
    """
    global _health_checker
    if _health_checker is None:
        from app import __version__

        _health_checker = HealthChecker(version=__version__)
    return _health_checker
