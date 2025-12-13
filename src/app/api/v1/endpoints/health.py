"""Health API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.health import (
    ComponentHealth,
    HealthStatus,
    SystemHealth,
    get_health_checker,
)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=SystemHealth)
async def get_system_health() -> SystemHealth:
    """Get overall system health.

    Returns:
        System health status
    """
    checker = get_health_checker()
    return await checker.check_all()


@router.get("/live")
async def liveness_check() -> dict[str, Any]:
    """Kubernetes liveness probe endpoint.

    Returns:
        Simple alive status
    """
    return {"status": "alive"}


@router.get("/ready")
async def readiness_check() -> dict[str, Any]:
    """Kubernetes readiness probe endpoint.

    Returns:
        Ready status based on health checks
    """
    checker = get_health_checker()
    health = await checker.check_all()

    if health.status == HealthStatus.UNHEALTHY:
        raise HTTPException(503, "Service not ready")

    return {
        "status": "ready",
        "overall_health": health.status.value,
    }


@router.get("/components")
async def get_components() -> list[str]:
    """Get list of monitored components.

    Returns:
        Component names
    """
    checker = get_health_checker()
    health = await checker.check_all()
    return [c.name for c in health.components]


@router.get("/components/{component_name}", response_model=ComponentHealth)
async def get_component_health(component_name: str) -> ComponentHealth:
    """Get health of a specific component.

    Args:
        component_name: Component to check

    Returns:
        Component health
    """
    checker = get_health_checker()
    result = await checker.check_component(component_name)

    if not result:
        raise HTTPException(404, f"Component not found: {component_name}")

    return result


@router.get("/uptime")
async def get_uptime() -> dict[str, Any]:
    """Get system uptime.

    Returns:
        Uptime information
    """
    checker = get_health_checker()
    uptime = checker.uptime_seconds

    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)

    return {
        "uptime_seconds": uptime,
        "uptime_formatted": f"{days}d {hours}h {minutes}m {seconds}s",
    }


@router.get("/version")
async def get_version() -> dict[str, Any]:
    """Get application version.

    Returns:
        Version information
    """
    checker = get_health_checker()
    return {"version": checker.version}


@router.get("/summary")
async def get_health_summary() -> dict[str, Any]:
    """Get quick health summary.

    Returns:
        Summary of system health
    """
    checker = get_health_checker()
    health = await checker.check_all()

    healthy_count = sum(1 for c in health.components if c.status == HealthStatus.HEALTHY)
    degraded_count = sum(1 for c in health.components if c.status == HealthStatus.DEGRADED)
    unhealthy_count = sum(1 for c in health.components if c.status == HealthStatus.UNHEALTHY)

    return {
        "status": health.status.value,
        "version": health.version,
        "uptime_seconds": health.uptime_seconds,
        "components": {
            "total": len(health.components),
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count,
        },
    }
