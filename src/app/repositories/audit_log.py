"""Repository for audit log operations."""

from datetime import datetime
from typing import Sequence, Any

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog database operations.

    Handles audit trail queries including:
    - Finding logs by actor/resource/action
    - Time-based queries
    - Compliance reporting
    """

    model = AuditLog

    async def get_by_actor(
        self,
        actor_address: str,
        *,
        action: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Get logs by actor address.

        @param actor_address - Actor wallet address
        @param action - Optional action filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of audit logs
        """
        stmt = select(self.model).where(
            self.model.actor_address == actor_address.lower()
        )
        if action:
            stmt = stmt.where(self.model.action == action)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_resource(
        self,
        resource_type: str,
        resource_id: str | None = None,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Get logs by resource.

        @param resource_type - Resource type
        @param resource_id - Optional specific resource ID
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of audit logs
        """
        stmt = select(self.model).where(self.model.resource_type == resource_type)
        if resource_id:
            stmt = stmt.where(self.model.resource_id == resource_id)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_action(
        self,
        action: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Get logs by action type.

        @param action - Action type
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of audit logs
        """
        stmt = (
            select(self.model)
            .where(self.model.action == action)
            .order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        *,
        actor_address: str | None = None,
        resource_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Get logs within time range.

        @param start_time - Period start
        @param end_time - Period end
        @param actor_address - Optional actor filter
        @param resource_type - Optional resource type filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of audit logs
        """
        stmt = select(self.model).where(
            and_(
                self.model.created_at >= start_time,
                self.model.created_at <= end_time,
            )
        )
        if actor_address:
            stmt = stmt.where(self.model.actor_address == actor_address.lower())
        if resource_type:
            stmt = stmt.where(self.model.resource_type == resource_type)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent(
        self,
        *,
        hours: int = 24,
        action: str | None = None,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Get recent audit logs.

        @param hours - Hours to look back
        @param action - Optional action filter
        @param limit - Maximum results
        @returns List of recent logs
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        stmt = select(self.model).where(self.model.created_at >= cutoff)
        if action:
            stmt = stmt.where(self.model.action == action)
        stmt = stmt.order_by(desc(self.model.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def log_action(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor_address: str | None = None,
        actor_role: str | None = None,
        actor_ip: str | None = None,
        actor_user_agent: str | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
    ) -> AuditLog:
        """Create audit log entry.

        @param action - Action performed
        @param resource_type - Type of resource affected
        @param resource_id - ID of resource
        @param actor_address - Actor wallet address
        @param actor_role - Actor's role
        @param actor_ip - Actor's IP address
        @param actor_user_agent - Actor's user agent
        @param old_value - Previous value (for updates)
        @param new_value - New value (for creates/updates)
        @returns Created audit log
        """
        return await self.create(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor_address": actor_address.lower() if actor_address else None,
                "actor_role": actor_role,
                "actor_ip": actor_ip,
                "actor_user_agent": actor_user_agent,
                "old_value": old_value,
                "new_value": new_value,
            }
        )

    async def get_change_history(
        self,
        resource_type: str,
        resource_id: str,
    ) -> Sequence[AuditLog]:
        """Get full change history for a resource.

        @param resource_type - Resource type
        @param resource_id - Resource ID
        @returns List of all changes to resource
        """
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.resource_type == resource_type,
                    self.model.resource_id == resource_id,
                )
            )
            .order_by(self.model.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_statistics(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get audit log statistics.

        @param start_date - Period start
        @param end_date - Period end
        @returns Statistics dictionary
        """
        # Count by action
        action_stmt = (
            select(self.model.action, func.count(self.model.id))
            .group_by(self.model.action)
        )
        if start_date:
            action_stmt = action_stmt.where(self.model.created_at >= start_date)
        if end_date:
            action_stmt = action_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(action_stmt)
        action_counts = dict(result.all())

        # Count by resource type
        resource_stmt = (
            select(self.model.resource_type, func.count(self.model.id))
            .group_by(self.model.resource_type)
        )
        if start_date:
            resource_stmt = resource_stmt.where(self.model.created_at >= start_date)
        if end_date:
            resource_stmt = resource_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(resource_stmt)
        resource_counts = dict(result.all())

        # Top actors
        actor_stmt = (
            select(self.model.actor_address, func.count(self.model.id))
            .where(self.model.actor_address.isnot(None))
            .group_by(self.model.actor_address)
            .order_by(desc(func.count(self.model.id)))
            .limit(10)
        )
        if start_date:
            actor_stmt = actor_stmt.where(self.model.created_at >= start_date)
        if end_date:
            actor_stmt = actor_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(actor_stmt)
        top_actors = dict(result.all())

        return {
            "by_action": action_counts,
            "by_resource": resource_counts,
            "top_actors": top_actors,
            "total_count": sum(action_counts.values()),
        }

    async def export_for_compliance(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Sequence[AuditLog]:
        """Export all logs for compliance reporting.

        @param start_date - Period start
        @param end_date - Period end
        @returns All logs in period (ordered by time)
        """
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.created_at >= start_date,
                    self.model.created_at <= end_date,
                )
            )
            .order_by(self.model.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
