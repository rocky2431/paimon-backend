"""Repository for risk event operations."""

from datetime import datetime
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import RiskEvent
from app.repositories.base import BaseRepository


class RiskEventRepository(BaseRepository[RiskEvent]):
    """Repository for RiskEvent database operations.

    Handles risk monitoring queries including:
    - Finding events by severity/type
    - Unresolved event tracking
    - Notification status
    """

    model = RiskEvent

    async def get_unresolved(
        self,
        *,
        severity: str | None = None,
        event_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RiskEvent]:
        """Get unresolved risk events.

        @param severity - Optional severity filter (info/warning/critical)
        @param event_type - Optional event type filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of unresolved events
        """
        stmt = select(self.model).where(self.model.resolved == False)
        if severity:
            stmt = stmt.where(self.model.severity == severity)
        if event_type:
            stmt = stmt.where(self.model.event_type == event_type)
        stmt = stmt.order_by(
            # Critical first, then warning, then info
            self.model.severity.desc(),
            desc(self.model.created_at),
        )
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_critical_unresolved(self) -> Sequence[RiskEvent]:
        """Get all unresolved critical events.

        @returns List of critical unresolved events
        """
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.resolved == False,
                    self.model.severity == "critical",
                )
            )
            .order_by(desc(self.model.created_at))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_severity(
        self,
        severity: str,
        *,
        resolved: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RiskEvent]:
        """Get events by severity level.

        @param severity - Severity level (info/warning/critical)
        @param resolved - Optional resolved status filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of events
        """
        stmt = select(self.model).where(self.model.severity == severity)
        if resolved is not None:
            stmt = stmt.where(self.model.resolved == resolved)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_metric(
        self,
        metric_name: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RiskEvent]:
        """Get events for a specific metric.

        @param metric_name - Metric name
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of events
        """
        stmt = (
            select(self.model)
            .where(self.model.metric_name == metric_name)
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_unnotified(self) -> Sequence[RiskEvent]:
        """Get events that haven't been notified yet.

        @returns List of unnotified events
        """
        stmt = (
            select(self.model)
            .where(self.model.notified == False)
            .order_by(self.model.severity.desc(), self.model.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def resolve(
        self,
        id: int,
        *,
        resolved_by: str,
        resolution_note: str | None = None,
    ) -> RiskEvent | None:
        """Mark event as resolved.

        @param id - Event ID
        @param resolved_by - Address of resolver
        @param resolution_note - Optional resolution notes
        @returns Updated event or None
        """
        return await self.update(
            id,
            {
                "resolved": True,
                "resolved_at": datetime.utcnow(),
                "resolved_by": resolved_by,
                "resolution_note": resolution_note,
            },
        )

    async def mark_notified(
        self, id: int, *, channels: list[str]
    ) -> RiskEvent | None:
        """Mark event as notified.

        @param id - Event ID
        @param channels - Notification channels used
        @returns Updated event or None
        """
        return await self.update(
            id,
            {
                "notified": True,
                "notified_at": datetime.utcnow(),
                "notification_channels": channels,
            },
        )

    async def create_event(
        self,
        *,
        event_type: str,
        severity: str,
        metric_name: str,
        message: str,
        threshold_value: Decimal | None = None,
        actual_value: Decimal | None = None,
        details: dict | None = None,
    ) -> RiskEvent:
        """Create new risk event.

        @param event_type - Type of event
        @param severity - Severity level (info/warning/critical)
        @param metric_name - Name of metric that triggered
        @param message - Human-readable message
        @param threshold_value - Threshold that was breached
        @param actual_value - Actual value that breached threshold
        @param details - Additional details as JSON
        @returns Created event
        """
        return await self.create(
            {
                "event_type": event_type,
                "severity": severity,
                "metric_name": metric_name,
                "message": message,
                "threshold_value": threshold_value,
                "actual_value": actual_value,
                "details": details,
                "resolved": False,
                "notified": False,
            }
        )

    async def get_recent(
        self, *, hours: int = 24, severity: str | None = None
    ) -> Sequence[RiskEvent]:
        """Get events from recent hours.

        @param hours - Number of hours to look back
        @param severity - Optional severity filter
        @returns List of recent events
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        stmt = select(self.model).where(self.model.created_at >= cutoff)
        if severity:
            stmt = stmt.where(self.model.severity == severity)
        stmt = stmt.order_by(desc(self.model.created_at))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_statistics(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get risk event statistics.

        @param start_date - Period start
        @param end_date - Period end
        @returns Statistics dictionary
        """
        # Count by severity
        severity_stmt = (
            select(self.model.severity, func.count(self.model.id))
            .group_by(self.model.severity)
        )
        if start_date:
            severity_stmt = severity_stmt.where(self.model.created_at >= start_date)
        if end_date:
            severity_stmt = severity_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(severity_stmt)
        severity_counts = dict(result.all())

        # Count by event type
        type_stmt = (
            select(self.model.event_type, func.count(self.model.id))
            .group_by(self.model.event_type)
        )
        if start_date:
            type_stmt = type_stmt.where(self.model.created_at >= start_date)
        if end_date:
            type_stmt = type_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(type_stmt)
        type_counts = dict(result.all())

        # Unresolved count
        unresolved_stmt = select(func.count(self.model.id)).where(
            self.model.resolved == False
        )
        result = await self.session.execute(unresolved_stmt)
        unresolved_count = result.scalar() or 0

        # Average resolution time (for resolved events)
        avg_stmt = select(
            func.avg(
                func.extract("epoch", self.model.resolved_at - self.model.created_at)
            )
        ).where(self.model.resolved == True)
        if start_date:
            avg_stmt = avg_stmt.where(self.model.created_at >= start_date)
        if end_date:
            avg_stmt = avg_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(avg_stmt)
        avg_resolution_seconds = result.scalar() or 0

        return {
            "by_severity": severity_counts,
            "by_type": type_counts,
            "total_count": sum(severity_counts.values()),
            "unresolved_count": unresolved_count,
            "avg_resolution_seconds": avg_resolution_seconds,
        }
