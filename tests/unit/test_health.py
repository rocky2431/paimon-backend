"""Tests for health checker service."""

import pytest

from app.services.health import (
    ComponentHealth,
    HealthChecker,
    HealthStatus,
    SystemHealth,
    get_health_checker,
)


class TestHealthStatus:
    """Tests for health status enum."""

    def test_health_statuses(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY.value == "HEALTHY"
        assert HealthStatus.DEGRADED.value == "DEGRADED"
        assert HealthStatus.UNHEALTHY.value == "UNHEALTHY"


class TestComponentHealth:
    """Tests for component health schema."""

    def test_component_health_creation(self):
        """Test creating component health."""
        from datetime import datetime

        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="All good",
            last_check=datetime.now(),
        )

        assert health.name == "test"
        assert health.status == HealthStatus.HEALTHY
        assert health.message == "All good"

    def test_component_health_with_details(self):
        """Test component health with details."""
        from datetime import datetime

        health = ComponentHealth(
            name="memory",
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(),
            details={"used_percent": 45.2},
        )

        assert health.details["used_percent"] == 45.2


class TestHealthChecker:
    """Tests for health checker."""

    @pytest.fixture
    def checker(self):
        """Create fresh health checker."""
        return HealthChecker(version="1.0.0-test")

    @pytest.mark.asyncio
    async def test_check_all(self, checker):
        """Test checking all components."""
        health = await checker.check_all()

        assert health.status in HealthStatus
        assert health.version == "1.0.0-test"
        assert health.uptime_seconds >= 0
        assert len(health.components) >= 3  # memory, disk, cpu

    @pytest.mark.asyncio
    async def test_check_memory(self, checker):
        """Test memory check."""
        result = await checker.check_component("memory")

        assert result is not None
        assert result.name == "memory"
        assert result.status in HealthStatus
        assert "used_percent" in result.details

    @pytest.mark.asyncio
    async def test_check_disk(self, checker):
        """Test disk check."""
        result = await checker.check_component("disk")

        assert result is not None
        assert result.name == "disk"
        assert result.status in HealthStatus
        assert "used_percent" in result.details

    @pytest.mark.asyncio
    async def test_check_cpu(self, checker):
        """Test CPU check."""
        result = await checker.check_component("cpu")

        assert result is not None
        assert result.name == "cpu"
        assert result.status in HealthStatus
        assert "usage_percent" in result.details

    @pytest.mark.asyncio
    async def test_check_nonexistent_component(self, checker):
        """Test checking nonexistent component."""
        result = await checker.check_component("nonexistent")

        assert result is None

    def test_register_custom_check(self, checker):
        """Test registering custom health check."""
        from datetime import datetime

        def custom_check() -> ComponentHealth:
            return ComponentHealth(
                name="custom",
                status=HealthStatus.HEALTHY,
                message="Custom check OK",
                last_check=datetime.now(),
            )

        checker.register_check("custom", custom_check)

        assert "custom" in checker._health_checks

    @pytest.mark.asyncio
    async def test_custom_check_execution(self, checker):
        """Test executing custom health check."""
        from datetime import datetime

        def custom_check() -> ComponentHealth:
            return ComponentHealth(
                name="custom",
                status=HealthStatus.HEALTHY,
                message="Custom check OK",
                last_check=datetime.now(),
            )

        checker.register_check("custom", custom_check)
        result = await checker.check_component("custom")

        assert result.name == "custom"
        assert result.status == HealthStatus.HEALTHY

    def test_unregister_check(self, checker):
        """Test unregistering a check."""
        result = checker.unregister_check("memory")

        assert result is True
        assert "memory" not in checker._health_checks

    def test_unregister_nonexistent_check(self, checker):
        """Test unregistering nonexistent check."""
        result = checker.unregister_check("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_overall_status_healthy(self, checker):
        """Test overall status is healthy."""
        health = await checker.check_all()

        # On most systems, all checks should be healthy
        assert health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def test_uptime(self, checker):
        """Test uptime tracking."""
        uptime = checker.uptime_seconds

        assert uptime >= 0

    def test_is_healthy(self, checker):
        """Test quick health check."""
        # Initially healthy (no checks run)
        assert checker.is_healthy() is True

    @pytest.mark.asyncio
    async def test_get_last_result(self, checker):
        """Test getting last result."""
        await checker.check_component("memory")
        result = checker.get_last_result("memory")

        assert result is not None
        assert result.name == "memory"

    def test_get_last_result_no_check(self, checker):
        """Test getting last result when no check run."""
        result = checker.get_last_result("memory")

        assert result is None

    @pytest.mark.asyncio
    async def test_system_info(self, checker):
        """Test system info is included."""
        health = await checker.check_all()

        assert "platform" in health.system_info
        assert "python_version" in health.system_info


class TestFailingChecks:
    """Tests for handling failing checks."""

    @pytest.fixture
    def checker(self):
        """Create fresh health checker."""
        return HealthChecker(version="1.0.0-test")

    @pytest.mark.asyncio
    async def test_failing_check_handled(self, checker):
        """Test failing check is handled gracefully."""

        def failing_check() -> ComponentHealth:
            raise Exception("Check failed")

        checker.register_check("failing", failing_check)
        health = await checker.check_all()

        # Should have a result for failing check
        failing_result = next(
            (c for c in health.components if c.name == "failing"), None
        )

        assert failing_result is not None
        assert failing_result.status == HealthStatus.UNKNOWN


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_health_checker_singleton(self):
        """Test singleton returns same instance."""
        # Reset singleton
        import app.services.health.checker as checker_module

        checker_module._health_checker = None

        checker1 = get_health_checker()
        checker2 = get_health_checker()

        assert checker1 is checker2
