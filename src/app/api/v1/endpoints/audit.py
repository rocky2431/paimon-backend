"""Audit API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.audit import (
    AuditAction,
    AuditCategory,
    AuditEntry,
    AuditQuery,
    AuditSeverity,
    get_audit_logger,
)

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/entries", response_model=list[AuditEntry])
async def list_audit_entries(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    category: AuditCategory | None = None,
    action: AuditAction | None = None,
    severity: AuditSeverity | None = None,
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    success: bool | None = None,
    correlation_id: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditEntry]:
    """List audit entries with filters.

    Args:
        start_time: Start of time range
        end_time: End of time range
        category: Filter by category
        action: Filter by action
        severity: Filter by severity
        actor_id: Filter by actor
        resource_type: Filter by resource type
        resource_id: Filter by resource ID
        success: Filter by success/failure
        correlation_id: Filter by correlation ID
        limit: Max results
        offset: Pagination offset

    Returns:
        Matching audit entries
    """
    logger = get_audit_logger()

    query = AuditQuery(
        start_time=start_time,
        end_time=end_time,
        categories=[category] if category else None,
        actions=[action] if action else None,
        severities=[severity] if severity else None,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        success=success,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset,
    )

    return logger.query(query)


@router.get("/entries/{entry_id}", response_model=AuditEntry)
async def get_audit_entry(entry_id: str) -> AuditEntry:
    """Get a specific audit entry.

    Args:
        entry_id: Entry ID

    Returns:
        The audit entry
    """
    logger = get_audit_logger()
    entry = logger.get_entry(entry_id)

    if not entry:
        raise HTTPException(404, "Audit entry not found")

    return entry


@router.get("/entries/recent", response_model=list[AuditEntry])
async def get_recent_entries(
    limit: int = Query(default=50, le=100),
    category: AuditCategory | None = None,
) -> list[AuditEntry]:
    """Get recent audit entries.

    Args:
        limit: Max entries
        category: Optional category filter

    Returns:
        Recent entries
    """
    logger = get_audit_logger()
    return logger.get_recent(limit=limit, category=category)


@router.get("/correlation/{correlation_id}", response_model=list[AuditEntry])
async def get_by_correlation(correlation_id: str) -> list[AuditEntry]:
    """Get all entries for a correlation ID.

    Args:
        correlation_id: Correlation ID

    Returns:
        Related entries
    """
    logger = get_audit_logger()
    return logger.get_by_correlation(correlation_id)


@router.get("/stats")
async def get_audit_stats(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    """Get audit statistics.

    Args:
        start_time: Start of time range
        end_time: End of time range

    Returns:
        Statistics
    """
    logger = get_audit_logger()
    stats = logger.get_stats(start_time, end_time)
    return stats.model_dump()


@router.get("/categories")
async def get_categories() -> list[str]:
    """Get available audit categories.

    Returns:
        List of categories
    """
    return [c.value for c in AuditCategory]


@router.get("/actions")
async def get_actions() -> list[str]:
    """Get available audit actions.

    Returns:
        List of actions
    """
    return [a.value for a in AuditAction]


@router.get("/severities")
async def get_severities() -> list[str]:
    """Get available severity levels.

    Returns:
        List of severities
    """
    return [s.value for s in AuditSeverity]


@router.get("/by-actor/{actor_id}", response_model=list[AuditEntry])
async def get_by_actor(
    actor_id: str,
    limit: int = Query(default=100, le=1000),
) -> list[AuditEntry]:
    """Get entries by actor.

    Args:
        actor_id: Actor ID
        limit: Max entries

    Returns:
        Actor's entries
    """
    logger = get_audit_logger()
    query = AuditQuery(actor_id=actor_id, limit=limit)
    return logger.query(query)


@router.get("/by-resource/{resource_type}/{resource_id}", response_model=list[AuditEntry])
async def get_by_resource(
    resource_type: str,
    resource_id: str,
    limit: int = Query(default=100, le=1000),
) -> list[AuditEntry]:
    """Get entries by resource.

    Args:
        resource_type: Resource type
        resource_id: Resource ID
        limit: Max entries

    Returns:
        Resource's entries
    """
    logger = get_audit_logger()
    query = AuditQuery(resource_type=resource_type, resource_id=resource_id, limit=limit)
    return logger.query(query)


@router.get("/failures", response_model=list[AuditEntry])
async def get_failures(
    limit: int = Query(default=100, le=1000),
    start_time: datetime | None = None,
) -> list[AuditEntry]:
    """Get failed operations.

    Args:
        limit: Max entries
        start_time: Start of time range

    Returns:
        Failed entries
    """
    logger = get_audit_logger()
    query = AuditQuery(success=False, limit=limit, start_time=start_time)
    return logger.query(query)


@router.get("/security", response_model=list[AuditEntry])
async def get_security_events(
    limit: int = Query(default=100, le=1000),
) -> list[AuditEntry]:
    """Get security-related events.

    Args:
        limit: Max entries

    Returns:
        Security events
    """
    logger = get_audit_logger()
    return logger.get_recent(limit=limit, category=AuditCategory.SECURITY)


@router.get("/emergencies", response_model=list[AuditEntry])
async def get_emergency_events(
    limit: int = Query(default=50, le=500),
) -> list[AuditEntry]:
    """Get emergency events.

    Args:
        limit: Max entries

    Returns:
        Emergency events
    """
    logger = get_audit_logger()
    return logger.get_recent(limit=limit, category=AuditCategory.EMERGENCY)
