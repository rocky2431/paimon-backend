"""Repository for redemption request operations."""

from datetime import datetime
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redemption import RedemptionRequest
from app.repositories.base import BaseRepository


class RedemptionRepository(BaseRepository[RedemptionRequest]):
    """Repository for RedemptionRequest database operations.

    Handles all redemption-related queries including:
    - Finding requests by owner/status/channel
    - Settlement window queries
    - Approval workflow integration
    - Statistics and aggregations
    """

    model = RedemptionRequest

    async def get_by_request_id(self, request_id: Decimal) -> RedemptionRequest | None:
        """Get redemption by on-chain request ID.

        @param request_id - On-chain request ID (uint256)
        @returns RedemptionRequest or None
        """
        return await self.get_one_by_filter(request_id=request_id)

    async def get_by_tx_hash(
        self, tx_hash: str, log_index: int
    ) -> RedemptionRequest | None:
        """Get redemption by transaction hash and log index.

        @param tx_hash - Transaction hash
        @param log_index - Log index in transaction
        @returns RedemptionRequest or None
        """
        stmt = select(self.model).where(
            and_(
                self.model.tx_hash == tx_hash,
                self.model.log_index == log_index,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_owner(
        self,
        owner: str,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RedemptionRequest]:
        """Get all redemptions for an owner.

        @param owner - Wallet address of owner
        @param status - Optional status filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of redemption requests
        """
        stmt = select(self.model).where(self.model.owner == owner.lower())
        if status:
            stmt = stmt.where(self.model.status == status)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_pending(
        self,
        *,
        channel: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RedemptionRequest]:
        """Get all pending redemption requests.

        @param channel - Optional channel filter (STANDARD/EMERGENCY/SCHEDULED)
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of pending requests
        """
        stmt = select(self.model).where(
            self.model.status.in_(["PENDING", "PENDING_APPROVAL"])
        )
        if channel:
            stmt = stmt.where(self.model.channel == channel)
        stmt = stmt.order_by(self.model.settlement_time).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_ready_for_settlement(
        self, before_time: datetime | None = None
    ) -> Sequence[RedemptionRequest]:
        """Get requests ready for settlement (approved and past settlement time).

        @param before_time - Settlement time cutoff (default: now)
        @returns List of requests ready for settlement
        """
        if before_time is None:
            before_time = datetime.utcnow()
        stmt = select(self.model).where(
            and_(
                self.model.status == "APPROVED",
                self.model.settlement_time <= before_time,
            )
        )
        stmt = stmt.order_by(self.model.settlement_time)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_pending_approval(
        self, *, skip: int = 0, limit: int = 100
    ) -> Sequence[RedemptionRequest]:
        """Get requests waiting for approval.

        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of requests pending approval
        """
        stmt = (
            select(self.model)
            .where(self.model.status == "PENDING_APPROVAL")
            .order_by(self.model.request_time)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_window_id(
        self, window_id: Decimal
    ) -> Sequence[RedemptionRequest]:
        """Get all requests in a settlement window.

        @param window_id - Window ID from contract
        @returns List of requests in window
        """
        stmt = select(self.model).where(self.model.window_id == window_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_status(
        self,
        id: int,
        status: str,
        *,
        approved_by: str | None = None,
        rejected_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> RedemptionRequest | None:
        """Update redemption status with approval info.

        @param id - Record ID
        @param status - New status
        @param approved_by - Approver address (if approved)
        @param rejected_by - Rejecter address (if rejected)
        @param rejection_reason - Rejection reason
        @returns Updated request or None
        """
        update_data: dict[str, Any] = {"status": status}
        now = datetime.utcnow()

        if status == "APPROVED" and approved_by:
            update_data["approved_by"] = approved_by
            update_data["approved_at"] = now
        elif status == "REJECTED" and rejected_by:
            update_data["rejected_by"] = rejected_by
            update_data["rejected_at"] = now
            update_data["rejection_reason"] = rejection_reason

        return await self.update(id, update_data)

    async def settle(
        self,
        id: int,
        *,
        actual_fee: Decimal,
        net_amount: Decimal,
        settlement_tx_hash: str,
    ) -> RedemptionRequest | None:
        """Mark redemption as settled.

        @param id - Record ID
        @param actual_fee - Actual fee charged
        @param net_amount - Net amount after fees
        @param settlement_tx_hash - Settlement transaction hash
        @returns Updated request or None
        """
        return await self.update(
            id,
            {
                "status": "SETTLED",
                "actual_fee": actual_fee,
                "net_amount": net_amount,
                "settlement_tx_hash": settlement_tx_hash,
                "settled_at": datetime.utcnow(),
            },
        )

    async def get_total_pending_amount(self) -> Decimal:
        """Get total amount of pending redemptions.

        @returns Total pending amount (gross)
        """
        from sqlalchemy import func

        stmt = select(func.coalesce(func.sum(self.model.gross_amount), 0)).where(
            self.model.status.in_(["PENDING", "PENDING_APPROVAL", "APPROVED"])
        )
        result = await self.session.execute(stmt)
        return result.scalar() or Decimal(0)

    async def get_statistics(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get redemption statistics for period.

        @param start_date - Period start
        @param end_date - Period end
        @returns Statistics dictionary
        """
        from sqlalchemy import func

        base_stmt = select(self.model)
        if start_date:
            base_stmt = base_stmt.where(self.model.created_at >= start_date)
        if end_date:
            base_stmt = base_stmt.where(self.model.created_at <= end_date)

        # Count by status
        count_stmt = (
            select(self.model.status, func.count(self.model.id))
            .group_by(self.model.status)
        )
        if start_date:
            count_stmt = count_stmt.where(self.model.created_at >= start_date)
        if end_date:
            count_stmt = count_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(count_stmt)
        status_counts = dict(result.all())

        # Total amounts
        amount_stmt = select(
            func.coalesce(func.sum(self.model.gross_amount), 0),
            func.coalesce(func.sum(self.model.actual_fee), 0),
        )
        if start_date:
            amount_stmt = amount_stmt.where(self.model.created_at >= start_date)
        if end_date:
            amount_stmt = amount_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(amount_stmt)
        total_amount, total_fees = result.first() or (Decimal(0), Decimal(0))

        return {
            "by_status": status_counts,
            "total_amount": total_amount,
            "total_fees": total_fees,
            "total_count": sum(status_counts.values()),
        }
