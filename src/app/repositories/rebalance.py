"""Repository for rebalance history operations."""

from datetime import datetime
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rebalance import RebalanceHistory
from app.repositories.base import BaseRepository


class RebalanceRepository(BaseRepository[RebalanceHistory]):
    """Repository for RebalanceHistory database operations.

    Handles rebalancing operation queries including:
    - Finding operations by status/trigger type
    - Execution tracking
    - Historical analysis
    """

    model = RebalanceHistory

    async def get_pending(
        self,
        *,
        trigger_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RebalanceHistory]:
        """Get pending rebalance operations.

        @param trigger_type - Optional trigger type filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of pending operations
        """
        stmt = select(self.model).where(
            self.model.status.in_(["PENDING", "PENDING_APPROVAL", "APPROVED"])
        )
        if trigger_type:
            stmt = stmt.where(self.model.trigger_type == trigger_type)
        stmt = stmt.order_by(self.model.created_at).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_executing(self) -> Sequence[RebalanceHistory]:
        """Get currently executing rebalance operations.

        @returns List of executing operations
        """
        stmt = (
            select(self.model)
            .where(self.model.status == "EXECUTING")
            .order_by(self.model.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_trigger_type(
        self,
        trigger_type: str,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RebalanceHistory]:
        """Get operations by trigger type.

        @param trigger_type - Trigger type (SCHEDULED/THRESHOLD/LIQUIDITY/EVENT/MANUAL)
        @param status - Optional status filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of operations
        """
        stmt = select(self.model).where(self.model.trigger_type == trigger_type)
        if status:
            stmt = stmt.where(self.model.status == status)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent(
        self, *, limit: int = 10, completed_only: bool = False
    ) -> Sequence[RebalanceHistory]:
        """Get recent rebalance operations.

        @param limit - Maximum results
        @param completed_only - Only include completed operations
        @returns List of recent operations
        """
        stmt = select(self.model)
        if completed_only:
            stmt = stmt.where(self.model.status == "COMPLETED")
        stmt = stmt.order_by(desc(self.model.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_approval_ticket(
        self, approval_ticket_id: str
    ) -> RebalanceHistory | None:
        """Get operation by approval ticket ID.

        @param approval_ticket_id - Associated approval ticket ID
        @returns RebalanceHistory or None
        """
        return await self.get_one_by_filter(approval_ticket_id=approval_ticket_id)

    async def start_execution(
        self, id: str, *, executed_by: str
    ) -> RebalanceHistory | None:
        """Mark operation as executing.

        @param id - Record ID
        @param executed_by - Address of executor
        @returns Updated operation or None
        """
        return await self.update(
            id,
            {
                "status": "EXECUTING",
                "executed_by": executed_by,
            },
        )

    async def complete(
        self,
        id: str,
        *,
        post_state: dict,
        execution_results: dict,
        actual_gas_cost: Decimal | None = None,
        actual_slippage: Decimal | None = None,
    ) -> RebalanceHistory | None:
        """Mark operation as completed.

        @param id - Record ID
        @param post_state - State after rebalancing
        @param execution_results - Execution details
        @param actual_gas_cost - Actual gas used
        @param actual_slippage - Actual slippage incurred
        @returns Updated operation or None
        """
        return await self.update(
            id,
            {
                "status": "COMPLETED",
                "post_state": post_state,
                "execution_results": execution_results,
                "executed_at": datetime.utcnow(),
                "actual_gas_cost": actual_gas_cost,
                "actual_slippage": actual_slippage,
            },
        )

    async def fail(
        self, id: str, *, error_message: str, execution_results: dict | None = None
    ) -> RebalanceHistory | None:
        """Mark operation as failed.

        @param id - Record ID
        @param error_message - Failure reason
        @param execution_results - Partial results if any
        @returns Updated operation or None
        """
        results = execution_results or {}
        results["error"] = error_message
        return await self.update(
            id,
            {
                "status": "FAILED",
                "execution_results": results,
            },
        )

    async def cancel(
        self, id: str, *, reason: str | None = None
    ) -> RebalanceHistory | None:
        """Cancel pending operation.

        @param id - Record ID
        @param reason - Cancellation reason
        @returns Updated operation or None
        """
        results = {"cancelled_reason": reason} if reason else {}
        return await self.update(
            id,
            {
                "status": "CANCELLED",
                "execution_results": results,
            },
        )

    async def get_statistics(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get rebalancing statistics for period.

        @param start_date - Period start
        @param end_date - Period end
        @returns Statistics dictionary
        """
        from sqlalchemy import func

        # Count by status
        status_stmt = (
            select(self.model.status, func.count(self.model.id))
            .group_by(self.model.status)
        )
        if start_date:
            status_stmt = status_stmt.where(self.model.created_at >= start_date)
        if end_date:
            status_stmt = status_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(status_stmt)
        status_counts = dict(result.all())

        # Count by trigger type
        trigger_stmt = (
            select(self.model.trigger_type, func.count(self.model.id))
            .group_by(self.model.trigger_type)
        )
        if start_date:
            trigger_stmt = trigger_stmt.where(self.model.created_at >= start_date)
        if end_date:
            trigger_stmt = trigger_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(trigger_stmt)
        trigger_counts = dict(result.all())

        # Total gas cost for completed
        gas_stmt = select(
            func.coalesce(func.sum(self.model.actual_gas_cost), 0)
        ).where(self.model.status == "COMPLETED")
        if start_date:
            gas_stmt = gas_stmt.where(self.model.created_at >= start_date)
        if end_date:
            gas_stmt = gas_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(gas_stmt)
        total_gas = result.scalar() or Decimal(0)

        return {
            "by_status": status_counts,
            "by_trigger": trigger_counts,
            "total_count": sum(status_counts.values()),
            "total_gas_cost": total_gas,
        }
