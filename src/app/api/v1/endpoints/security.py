"""Security API endpoints for rate limiting and IP filtering."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.services.security import (
    IPFilterConfig,
    RateLimitConfig,
    RateLimitResult,
    get_ip_filter,
    get_rate_limiter,
)

router = APIRouter(prefix="/security", tags=["Security"])


# Rate Limiting Endpoints
@router.get("/rate-limit/check")
async def check_rate_limit(request: Request) -> RateLimitResult:
    """Check rate limit for current IP.

    Args:
        request: The request

    Returns:
        Rate limit status
    """
    limiter = get_rate_limiter()
    client_ip = request.client.host if request.client else "unknown"
    return limiter.check(client_ip)


@router.get("/rate-limit/remaining")
async def get_remaining_requests(request: Request) -> dict[str, Any]:
    """Get remaining requests for current IP.

    Args:
        request: The request

    Returns:
        Remaining count
    """
    limiter = get_rate_limiter()
    client_ip = request.client.host if request.client else "unknown"
    remaining = limiter.get_remaining(client_ip)
    return {"ip": client_ip, "remaining": remaining}


@router.post("/rate-limit/reset/{ip}")
async def reset_rate_limit(ip: str) -> dict[str, Any]:
    """Reset rate limit for an IP.

    Args:
        ip: IP address

    Returns:
        Status
    """
    limiter = get_rate_limiter()
    limiter.reset(ip)
    return {"status": "reset", "ip": ip}


@router.get("/rate-limit/config")
async def get_rate_limit_config() -> dict[str, Any]:
    """Get rate limit configuration.

    Returns:
        Configuration
    """
    limiter = get_rate_limiter()
    return limiter.config.model_dump()


@router.put("/rate-limit/config")
async def update_rate_limit_config(config: RateLimitConfig) -> dict[str, Any]:
    """Update rate limit configuration.

    Args:
        config: New configuration

    Returns:
        Updated configuration
    """
    limiter = get_rate_limiter()
    limiter.update_config(config)
    return {"status": "updated", "config": config.model_dump()}


@router.get("/rate-limit/stats")
async def get_rate_limit_stats() -> dict[str, Any]:
    """Get rate limiter statistics.

    Returns:
        Statistics
    """
    limiter = get_rate_limiter()
    return limiter.get_stats()


# IP Filtering Endpoints
@router.get("/ip-filter/check/{ip}")
async def check_ip(ip: str) -> dict[str, Any]:
    """Check if an IP is allowed.

    Args:
        ip: IP address

    Returns:
        Allow status
    """
    ip_filter = get_ip_filter()
    allowed = ip_filter.is_allowed(ip)
    return {"ip": ip, "allowed": allowed}


@router.get("/ip-filter/whitelist")
async def get_whitelist() -> list[dict[str, Any]]:
    """Get whitelist entries.

    Returns:
        Whitelist
    """
    ip_filter = get_ip_filter()
    entries = ip_filter.get_whitelist()
    return [e.model_dump() for e in entries]


@router.post("/ip-filter/whitelist")
async def add_to_whitelist(
    ip_or_range: str,
    description: str = "",
    added_by: str = "api",
    expires_in_hours: int | None = None,
) -> dict[str, Any]:
    """Add IP to whitelist.

    Args:
        ip_or_range: IP address or CIDR range
        description: Description
        added_by: Who added
        expires_in_hours: Optional expiration hours

    Returns:
        Status
    """
    ip_filter = get_ip_filter()
    expires_at = None
    if expires_in_hours:
        from datetime import timedelta

        expires_at = datetime.now() + timedelta(hours=expires_in_hours)

    success = ip_filter.add_to_whitelist(
        ip_or_range,
        description=description,
        added_by=added_by,
        expires_at=expires_at,
    )

    if not success:
        raise HTTPException(400, "Invalid IP address or range")

    return {"status": "added", "ip_or_range": ip_or_range}


@router.delete("/ip-filter/whitelist/{ip_or_range:path}")
async def remove_from_whitelist(ip_or_range: str) -> dict[str, Any]:
    """Remove IP from whitelist.

    Args:
        ip_or_range: IP or range

    Returns:
        Status
    """
    ip_filter = get_ip_filter()
    success = ip_filter.remove_from_whitelist(ip_or_range)

    if not success:
        raise HTTPException(404, "Entry not found")

    return {"status": "removed", "ip_or_range": ip_or_range}


@router.get("/ip-filter/blacklist")
async def get_blacklist() -> list[dict[str, Any]]:
    """Get blacklist entries.

    Returns:
        Blacklist
    """
    ip_filter = get_ip_filter()
    entries = ip_filter.get_blacklist()
    return [e.model_dump() for e in entries]


@router.post("/ip-filter/blacklist")
async def add_to_blacklist(
    ip_or_range: str,
    description: str = "",
    added_by: str = "api",
    expires_in_hours: int | None = None,
) -> dict[str, Any]:
    """Add IP to blacklist.

    Args:
        ip_or_range: IP address or CIDR range
        description: Description
        added_by: Who added
        expires_in_hours: Optional expiration hours

    Returns:
        Status
    """
    ip_filter = get_ip_filter()
    expires_at = None
    if expires_in_hours:
        from datetime import timedelta

        expires_at = datetime.now() + timedelta(hours=expires_in_hours)

    success = ip_filter.add_to_blacklist(
        ip_or_range,
        description=description,
        added_by=added_by,
        expires_at=expires_at,
    )

    if not success:
        raise HTTPException(400, "Invalid IP address or range")

    return {"status": "added", "ip_or_range": ip_or_range}


@router.delete("/ip-filter/blacklist/{ip_or_range:path}")
async def remove_from_blacklist(ip_or_range: str) -> dict[str, Any]:
    """Remove IP from blacklist.

    Args:
        ip_or_range: IP or range

    Returns:
        Status
    """
    ip_filter = get_ip_filter()
    success = ip_filter.remove_from_blacklist(ip_or_range)

    if not success:
        raise HTTPException(404, "Entry not found")

    return {"status": "removed", "ip_or_range": ip_or_range}


@router.get("/ip-filter/config")
async def get_ip_filter_config() -> dict[str, Any]:
    """Get IP filter configuration.

    Returns:
        Configuration
    """
    ip_filter = get_ip_filter()
    return ip_filter.config.model_dump()


@router.put("/ip-filter/config")
async def update_ip_filter_config(config: IPFilterConfig) -> dict[str, Any]:
    """Update IP filter configuration.

    Args:
        config: New configuration

    Returns:
        Updated configuration
    """
    ip_filter = get_ip_filter()
    ip_filter.update_config(config)
    return {"status": "updated", "config": config.model_dump()}


@router.get("/ip-filter/stats")
async def get_ip_filter_stats() -> dict[str, Any]:
    """Get IP filter statistics.

    Returns:
        Statistics
    """
    ip_filter = get_ip_filter()
    return ip_filter.get_stats()
