"""Repository for approval workflow operations."""

from datetime import datetime
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.approval import ApprovalTicket, ApprovalRecord
from app.repositories.base import BaseRepository


class ApprovalRepository(BaseRepository[ApprovalTicket]):
    """Repository for ApprovalTicket database operations.

    Handles approval workflow queries including:
    - Finding tickets by type/status/requester
    - SLA deadline tracking
    - Escalation management
    - Statistics and reporting
    """

    model = ApprovalTicket

    async def get_with_records(self, ticket_id: str) -> ApprovalTicket | None:
        """Get ticket with all approval records loaded.

        @param ticket_id - Ticket ID
        @returns ApprovalTicket with records or None
        """
        stmt = (
            select(self.model)
            .options(selectinload(self.model.records))
            .where(self.model.id == ticket_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_reference(
        self, reference_type: str, reference_id: str
    ) -> ApprovalTicket | None:
        """Get ticket by reference (e.g., redemption request).

        @param reference_type - Type of reference (REDEMPTION/REBALANCE/etc)
        @param reference_id - ID of referenced entity
        @returns ApprovalTicket or None
        """
        stmt = select(self.model).where(
            and_(
                self.model.reference_type == reference_type,
                self.model.reference_id == reference_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_pending(
        self,
        *,
        ticket_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ApprovalTicket]:
        """Get all pending tickets.

        @param ticket_type - Optional type filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of pending tickets
        """
        stmt = select(self.model).where(
            self.model.status.in_(["PENDING", "PARTIALLY_APPROVED"])
        )
        if ticket_type:
            stmt = stmt.where(self.model.ticket_type == ticket_type)
        stmt = stmt.order_by(self.model.sla_deadline).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_requester(
        self,
        requester: str,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ApprovalTicket]:
        """Get tickets created by a requester.

        @param requester - Requester wallet address
        @param status - Optional status filter
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of tickets
        """
        stmt = select(self.model).where(self.model.requester == requester.lower())
        if status:
            stmt = stmt.where(self.model.status == status)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_expiring_soon(
        self, within_minutes: int = 60
    ) -> Sequence[ApprovalTicket]:
        """Get tickets expiring within specified minutes.

        @param within_minutes - Minutes until deadline
        @returns List of expiring tickets
        """
        from datetime import timedelta

        deadline = datetime.utcnow() + timedelta(minutes=within_minutes)
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.status.in_(["PENDING", "PARTIALLY_APPROVED"]),
                    self.model.sla_deadline <= deadline,
                )
            )
            .order_by(self.model.sla_deadline)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_past_warning(self) -> Sequence[ApprovalTicket]:
        """Get tickets past SLA warning time but not yet escalated.

        @returns List of tickets needing escalation
        """
        now = datetime.utcnow()
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.status.in_(["PENDING", "PARTIALLY_APPROVED"]),
                    self.model.sla_warning <= now,
                    self.model.escalated_at.is_(None),
                )
            )
            .order_by(self.model.sla_warning)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_expired(self) -> Sequence[ApprovalTicket]:
        """Get tickets past SLA deadline.

        @returns List of expired tickets
        """
        now = datetime.utcnow()
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.status.in_(["PENDING", "PARTIALLY_APPROVED"]),
                    self.model.sla_deadline <= now,
                )
            )
            .order_by(self.model.sla_deadline)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_approval(
        self,
        ticket_id: str,
        *,
        increment_approvals: bool = True,
        increment_rejections: bool = False,
    ) -> ApprovalTicket | None:
        """Increment approval or rejection count.

        @param ticket_id - Ticket ID
        @param increment_approvals - Add to approval count
        @param increment_rejections - Add to rejection count
        @returns Updated ticket or None
        """
        ticket = await self.get_by_id(ticket_id)
        if ticket is None:
            return None

        if increment_approvals:
            ticket.current_approvals += 1
        if increment_rejections:
            ticket.current_rejections += 1

        # Check if fully approved
        if ticket.current_approvals >= ticket.required_approvals:
            ticket.status = "APPROVED"
            ticket.result = "APPROVED"
            ticket.resolved_at = datetime.utcnow()

        await self.session.flush()
        await self.session.refresh(ticket)
        return ticket

    async def resolve(
        self,
        ticket_id: str,
        *,
        result: str,
        result_reason: str | None = None,
        resolved_by: str | None = None,
    ) -> ApprovalTicket | None:
        """Resolve ticket with final result.

        @param ticket_id - Ticket ID
        @param result - Final result (APPROVED/REJECTED/EXPIRED/CANCELLED)
        @param result_reason - Reason for result
        @param resolved_by - Address of resolver
        @returns Updated ticket or None
        """
        status_map = {
            "APPROVED": "APPROVED",
            "REJECTED": "REJECTED",
            "EXPIRED": "EXPIRED",
            "CANCELLED": "CANCELLED",
        }
        return await self.update(
            ticket_id,
            {
                "status": status_map.get(result, result),
                "result": result,
                "result_reason": result_reason,
                "resolved_at": datetime.utcnow(),
                "resolved_by": resolved_by,
            },
        )

    async def escalate(
        self, ticket_id: str, escalated_to: list[str]
    ) -> ApprovalTicket | None:
        """Mark ticket as escalated.

        @param ticket_id - Ticket ID
        @param escalated_to - List of addresses to escalate to
        @returns Updated ticket or None
        """
        return await self.update(
            ticket_id,
            {
                "escalated_at": datetime.utcnow(),
                "escalated_to": escalated_to,
            },
        )

    async def get_statistics(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get approval statistics for period.

        @param start_date - Period start
        @param end_date - Period end
        @returns Statistics dictionary
        """
        from sqlalchemy import func

        # Count by status
        count_stmt = select(self.model.status, func.count(self.model.id)).group_by(
            self.model.status
        )
        if start_date:
            count_stmt = count_stmt.where(self.model.created_at >= start_date)
        if end_date:
            count_stmt = count_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(count_stmt)
        status_counts = dict(result.all())

        # Count by type
        type_stmt = select(self.model.ticket_type, func.count(self.model.id)).group_by(
            self.model.ticket_type
        )
        if start_date:
            type_stmt = type_stmt.where(self.model.created_at >= start_date)
        if end_date:
            type_stmt = type_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(type_stmt)
        type_counts = dict(result.all())

        # Average resolution time
        avg_stmt = select(
            func.avg(
                func.extract("epoch", self.model.resolved_at - self.model.created_at)
            )
        ).where(self.model.resolved_at.isnot(None))
        if start_date:
            avg_stmt = avg_stmt.where(self.model.created_at >= start_date)
        if end_date:
            avg_stmt = avg_stmt.where(self.model.created_at <= end_date)

        result = await self.session.execute(avg_stmt)
        avg_resolution_seconds = result.scalar() or 0

        return {
            "by_status": status_counts,
            "by_type": type_counts,
            "total_count": sum(status_counts.values()),
            "avg_resolution_seconds": avg_resolution_seconds,
        }


class ApprovalRecordRepository(BaseRepository[ApprovalRecord]):
    """Repository for ApprovalRecord database operations.

    Handles individual approval/rejection record queries.
    """

    model = ApprovalRecord

    async def get_by_ticket(self, ticket_id: str) -> Sequence[ApprovalRecord]:
        """Get all records for a ticket.

        @param ticket_id - Parent ticket ID
        @returns List of approval records
        """
        stmt = (
            select(self.model)
            .where(self.model.ticket_id == ticket_id)
            .order_by(self.model.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_approver(
        self,
        approver: str,
        *,
        action: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ApprovalRecord]:
        """Get records by approver address.

        @param approver - Approver wallet address
        @param action - Optional action filter (APPROVE/REJECT)
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of approval records
        """
        stmt = select(self.model).where(self.model.approver == approver.lower())
        if action:
            stmt = stmt.where(self.model.action == action)
        stmt = stmt.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def has_already_acted(self, ticket_id: str, approver: str) -> bool:
        """Check if approver has already acted on ticket.

        @param ticket_id - Ticket ID
        @param approver - Approver address
        @returns True if already acted
        """
        return await self.exists(ticket_id=ticket_id, approver=approver.lower())
