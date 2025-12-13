"""Audit logger service for tracking all system events."""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.services.audit.schemas import (
    AuditAction,
    AuditCategory,
    AuditEntry,
    AuditQuery,
    AuditSeverity,
    AuditStats,
)

logger = logging.getLogger(__name__)


class AuditLogger:
    """Service for audit logging."""

    def __init__(self):
        """Initialize audit logger."""
        self._entries: list[AuditEntry] = []
        self._max_entries = 100000  # In-memory limit

    def log(
        self,
        category: AuditCategory,
        action: AuditAction,
        description: str,
        *,
        severity: AuditSeverity = AuditSeverity.INFO,
        actor_id: str | None = None,
        actor_type: str = "user",
        actor_ip: str | None = None,
        actor_user_agent: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        success: bool = True,
        error_message: str | None = None,
        correlation_id: str | None = None,
        parent_entry_id: str | None = None,
    ) -> AuditEntry:
        """Log an audit event.

        Args:
            category: Event category
            action: Specific action
            description: Human-readable description
            severity: Event severity
            actor_id: ID of actor (user/system)
            actor_type: Type of actor
            actor_ip: IP address
            actor_user_agent: User agent
            resource_type: Type of affected resource
            resource_id: ID of affected resource
            details: Additional event details
            metadata: System metadata
            success: Whether action succeeded
            error_message: Error if failed
            correlation_id: Request correlation ID
            parent_entry_id: Parent entry for chaining

        Returns:
            The created audit entry
        """
        entry = AuditEntry(
            entry_id=str(uuid4()),
            timestamp=datetime.now(),
            category=category,
            action=action,
            severity=severity,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            details=details or {},
            metadata=metadata or {},
            success=success,
            error_message=error_message,
            correlation_id=correlation_id,
            parent_entry_id=parent_entry_id,
        )

        # Store entry
        self._entries.append(entry)

        # Trim if needed
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        # Also log to standard logger
        log_level = {
            AuditSeverity.DEBUG: logging.DEBUG,
            AuditSeverity.INFO: logging.INFO,
            AuditSeverity.WARNING: logging.WARNING,
            AuditSeverity.ERROR: logging.ERROR,
            AuditSeverity.CRITICAL: logging.CRITICAL,
        }.get(severity, logging.INFO)

        logger.log(
            log_level,
            f"[AUDIT] {category.value}/{action.value}: {description}",
            extra={
                "audit_entry_id": entry.entry_id,
                "actor_id": actor_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )

        return entry

    def log_auth(
        self,
        action: AuditAction,
        description: str,
        *,
        actor_id: str | None = None,
        actor_ip: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> AuditEntry:
        """Log authentication event.

        Args:
            action: Auth action
            description: Description
            actor_id: User ID
            actor_ip: IP address
            success: Whether succeeded
            error_message: Error if failed
            **kwargs: Additional parameters

        Returns:
            Audit entry
        """
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
        return self.log(
            AuditCategory.AUTHENTICATION,
            action,
            description,
            severity=severity,
            actor_id=actor_id,
            actor_ip=actor_ip,
            success=success,
            error_message=error_message,
            **kwargs,
        )

    def log_financial(
        self,
        action: AuditAction,
        description: str,
        *,
        resource_type: str,
        resource_id: str,
        actor_id: str | None = None,
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AuditEntry:
        """Log financial transaction.

        Args:
            action: Financial action
            description: Description
            resource_type: Type (redemption, rebalance, etc.)
            resource_id: Transaction ID
            actor_id: User ID
            details: Transaction details
            **kwargs: Additional parameters

        Returns:
            Audit entry
        """
        return self.log(
            AuditCategory.FINANCIAL,
            action,
            description,
            severity=AuditSeverity.INFO,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            **kwargs,
        )

    def log_security(
        self,
        action: AuditAction,
        description: str,
        *,
        severity: AuditSeverity = AuditSeverity.WARNING,
        actor_id: str | None = None,
        actor_ip: str | None = None,
        **kwargs: Any,
    ) -> AuditEntry:
        """Log security event.

        Args:
            action: Security action
            description: Description
            severity: Event severity
            actor_id: User ID
            actor_ip: IP address
            **kwargs: Additional parameters

        Returns:
            Audit entry
        """
        return self.log(
            AuditCategory.SECURITY,
            action,
            description,
            severity=severity,
            actor_id=actor_id,
            actor_ip=actor_ip,
            **kwargs,
        )

    def log_emergency(
        self,
        action: AuditAction,
        description: str,
        *,
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AuditEntry:
        """Log emergency event.

        Args:
            action: Emergency action
            description: Description
            details: Emergency details
            **kwargs: Additional parameters

        Returns:
            Audit entry
        """
        return self.log(
            AuditCategory.EMERGENCY,
            action,
            description,
            severity=AuditSeverity.CRITICAL,
            actor_type="system",
            details=details,
            **kwargs,
        )

    def log_config_change(
        self,
        description: str,
        *,
        actor_id: str,
        resource_type: str,
        old_value: Any = None,
        new_value: Any = None,
        **kwargs: Any,
    ) -> AuditEntry:
        """Log configuration change.

        Args:
            description: Description
            actor_id: User making change
            resource_type: Config type
            old_value: Previous value
            new_value: New value
            **kwargs: Additional parameters

        Returns:
            Audit entry
        """
        return self.log(
            AuditCategory.CONFIGURATION,
            AuditAction.CONFIG_UPDATED,
            description,
            severity=AuditSeverity.WARNING,
            actor_id=actor_id,
            resource_type=resource_type,
            details={"old_value": old_value, "new_value": new_value},
            **kwargs,
        )

    def query(self, query: AuditQuery) -> list[AuditEntry]:
        """Query audit entries.

        Args:
            query: Query parameters

        Returns:
            Matching entries
        """
        results = self._entries.copy()

        # Apply filters
        if query.start_time:
            results = [e for e in results if e.timestamp >= query.start_time]
        if query.end_time:
            results = [e for e in results if e.timestamp <= query.end_time]
        if query.categories:
            results = [e for e in results if e.category in query.categories]
        if query.actions:
            results = [e for e in results if e.action in query.actions]
        if query.severities:
            results = [e for e in results if e.severity in query.severities]
        if query.actor_id:
            results = [e for e in results if e.actor_id == query.actor_id]
        if query.resource_type:
            results = [e for e in results if e.resource_type == query.resource_type]
        if query.resource_id:
            results = [e for e in results if e.resource_id == query.resource_id]
        if query.success is not None:
            results = [e for e in results if e.success == query.success]
        if query.correlation_id:
            results = [e for e in results if e.correlation_id == query.correlation_id]

        # Sort by timestamp descending (newest first)
        results.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        results = results[query.offset : query.offset + query.limit]

        return results

    def get_entry(self, entry_id: str) -> AuditEntry | None:
        """Get entry by ID.

        Args:
            entry_id: Entry ID

        Returns:
            Entry or None
        """
        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def get_recent(
        self,
        limit: int = 50,
        category: AuditCategory | None = None,
    ) -> list[AuditEntry]:
        """Get recent entries.

        Args:
            limit: Max entries
            category: Optional category filter

        Returns:
            Recent entries
        """
        query = AuditQuery(
            limit=limit,
            categories=[category] if category else None,
        )
        return self.query(query)

    def get_by_correlation(self, correlation_id: str) -> list[AuditEntry]:
        """Get all entries for a correlation ID.

        Args:
            correlation_id: Correlation ID

        Returns:
            Related entries
        """
        query = AuditQuery(correlation_id=correlation_id, limit=1000)
        return self.query(query)

    def get_stats(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> AuditStats:
        """Get audit statistics.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Statistics
        """
        entries = self._entries.copy()

        # Filter by time range
        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]

        if not entries:
            return AuditStats(
                total_entries=0,
                entries_by_category={},
                entries_by_severity={},
                entries_by_action={},
                success_rate=100.0,
                unique_actors=0,
            )

        # Calculate stats
        by_category: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)
        by_action: dict[str, int] = defaultdict(int)
        actors: set[str] = set()
        success_count = 0

        for entry in entries:
            by_category[entry.category.value] += 1
            by_severity[entry.severity.value] += 1
            by_action[entry.action.value] += 1
            if entry.actor_id:
                actors.add(entry.actor_id)
            if entry.success:
                success_count += 1

        timestamps = [e.timestamp for e in entries]

        return AuditStats(
            total_entries=len(entries),
            entries_by_category=dict(by_category),
            entries_by_severity=dict(by_severity),
            entries_by_action=dict(by_action),
            success_rate=(success_count / len(entries)) * 100,
            unique_actors=len(actors),
            time_range_start=min(timestamps),
            time_range_end=max(timestamps),
        )

    def clear(self) -> int:
        """Clear all entries.

        Returns:
            Number of entries cleared
        """
        count = len(self._entries)
        self._entries = []
        return count


# Singleton instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get singleton audit logger instance.

    Returns:
        The audit logger
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
