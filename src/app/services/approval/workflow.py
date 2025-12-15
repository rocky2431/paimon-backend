"""Approval workflow engine with database persistence.

Features:
- Multi-level approval support
- Configurable rules based on amount/type
- SLA tracking with warnings and deadlines
- Auto-escalation on SLA breach
- Complete audit trail in database
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import AsyncSessionLocal
from app.models.approval import ApprovalTicket, ApprovalRecord as ApprovalRecordModel
from app.repositories.approval import ApprovalRepository, ApprovalRecordRepository
from app.repositories.audit_log import AuditLogRepository
from app.services.approval.schemas import (
    ApprovalAction,
    ApprovalActionRequest,
    ApprovalLevel,
    ApprovalRecord,
    ApprovalResult,
    ApprovalRuleConfig,
    ApprovalStats,
    ApprovalTicketCreate,
    ApprovalTicketDetail,
    ApprovalTicketListItem,
    ApprovalTicketListResponse,
    ApprovalTicketStatus,
    ApprovalTicketType,
    EscalationConfig,
    PaginationMeta,
    SLAConfig,
)

logger = logging.getLogger(__name__)


class ApprovalWorkflowEngine:
    """Engine for managing approval workflows with database persistence.

    Features:
    - Multi-level approval support
    - Configurable rules based on amount/type
    - SLA tracking with warnings and deadlines
    - Auto-escalation on SLA breach
    - Complete audit trail

    Uses Repository pattern for database operations.
    """

    # Default approval rules - aligned with product specs
    # Emergency: >30K USDC needs approval
    # Standard: >100K USDC needs approval
    DEFAULT_RULES: list[ApprovalRuleConfig] = [
        # Standard redemptions (30K-100K) - single operator approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REDEMPTION,
            min_amount=Decimal("30000000000"),  # 30K USDC (6 decimals)
            max_amount=Decimal("100000000000"),  # 100K USDC
            required_approvals=1,
            required_level=ApprovalLevel.OPERATOR,
            sla=SLAConfig(warning_hours=4, deadline_hours=24),
        ),
        # Large redemptions (>100K) - manager approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REDEMPTION,
            min_amount=Decimal("100000000000"),  # 100K USDC
            required_approvals=2,
            required_level=ApprovalLevel.MANAGER,
            sla=SLAConfig(warning_hours=2, deadline_hours=12),
        ),
        # Emergency redemptions (>30K) - urgent admin approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.EMERGENCY,
            min_amount=Decimal("30000000000"),  # 30K USDC
            required_approvals=1,
            required_level=ApprovalLevel.EMERGENCY,
            sla=SLAConfig(warning_hours=0.5, deadline_hours=2),
            escalation=EscalationConfig(
                enabled=True,
                escalate_after_hours=0.5,
                escalate_to_level=ApprovalLevel.EMERGENCY,
            ),
        ),
        # Rebalancing - manager approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REBALANCING,
            required_approvals=2,
            required_level=ApprovalLevel.MANAGER,
            sla=SLAConfig(warning_hours=2, deadline_hours=12),
        ),
        # Asset changes - admin approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.ASSET_ADD,
            required_approvals=2,
            required_level=ApprovalLevel.ADMIN,
            sla=SLAConfig(warning_hours=12, deadline_hours=48),
        ),
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.ASSET_REMOVE,
            required_approvals=3,
            required_level=ApprovalLevel.ADMIN,
            sla=SLAConfig(warning_hours=12, deadline_hours=48),
        ),
        # Config changes - admin approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.CONFIG_CHANGE,
            required_approvals=2,
            required_level=ApprovalLevel.ADMIN,
            sla=SLAConfig(warning_hours=4, deadline_hours=24),
        ),
    ]

    # Approver level hierarchy
    LEVEL_HIERARCHY = {
        ApprovalLevel.OPERATOR: 1,
        ApprovalLevel.MANAGER: 2,
        ApprovalLevel.ADMIN: 3,
        ApprovalLevel.EMERGENCY: 4,
    }

    def __init__(
        self,
        rules: list[ApprovalRuleConfig] | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
    ):
        """Initialize approval workflow engine.

        @param rules - Custom approval rules (uses defaults if None)
        @param session_factory - Optional factory for creating database sessions
        """
        self.rules = rules or self.DEFAULT_RULES
        self._session_factory = session_factory or AsyncSessionLocal
        # Cache for approver levels (can be loaded from database or RBAC service)
        self._approver_levels: dict[str, ApprovalLevel] = {}

    def set_approver_level(self, address: str, level: ApprovalLevel) -> None:
        """Set approval level for an address.

        @param address - Approver wallet address
        @param level - Approval level
        """
        self._approver_levels[address.lower()] = level
        logger.info(f"Set approval level {level} for {address}")

    def get_approver_level(self, address: str) -> ApprovalLevel | None:
        """Get approval level for an address.

        @param address - Approver wallet address
        @returns Approval level or None if not set
        """
        return self._approver_levels.get(address.lower())

    def _find_rule(
        self,
        ticket_type: ApprovalTicketType,
        amount: Decimal | None,
    ) -> ApprovalRuleConfig:
        """Find matching rule for ticket type and amount.

        @param ticket_type - Type of ticket
        @param amount - Amount if applicable
        @returns Matching rule configuration
        """
        matching_rules = []
        for rule in self.rules:
            if rule.ticket_type != ticket_type:
                continue

            if amount is not None:
                if rule.min_amount is not None and amount < rule.min_amount:
                    continue
                if rule.max_amount is not None and amount > rule.max_amount:
                    continue

            matching_rules.append(rule)

        if not matching_rules:
            # Return default rule
            return ApprovalRuleConfig(
                ticket_type=ticket_type,
                required_approvals=1,
                required_level=ApprovalLevel.OPERATOR,
            )

        # Return most specific rule (highest min_amount)
        return max(
            matching_rules,
            key=lambda r: (r.min_amount or Decimal(0), r.required_approvals),
        )

    def _can_approve(
        self,
        approver_level: ApprovalLevel,
        required_level: ApprovalLevel,
    ) -> bool:
        """Check if approver has sufficient level.

        @param approver_level - Approver's level
        @param required_level - Required level
        @returns True if approver can approve
        """
        return (
            self.LEVEL_HIERARCHY.get(approver_level, 0)
            >= self.LEVEL_HIERARCHY.get(required_level, 0)
        )

    async def _log_audit(
        self,
        session: AsyncSession,
        ticket_id: str,
        action: str,
        actor: str,
        old_status: str | None = None,
        new_status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit entry to database.

        @param session - Database session
        @param ticket_id - Ticket ID
        @param action - Action type
        @param actor - Actor address
        @param old_status - Previous status
        @param new_status - New status
        @param details - Additional details
        """
        audit_repo = AuditLogRepository(session)
        await audit_repo.create({
            "action": f"approval.{action.lower()}",
            "resource_type": "approval_ticket",
            "resource_id": ticket_id,
            "actor_address": actor.lower() if actor and actor != "SYSTEM" else None,
            "old_value": {"status": old_status} if old_status else None,
            "new_value": {
                "status": new_status,
                **(details or {}),
            },
        })

    async def create_ticket(
        self,
        data: ApprovalTicketCreate,
    ) -> str:
        """Create a new approval ticket in database.

        @param data - Ticket creation data
        @returns Created ticket ID
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)

            # Check for existing ticket for same reference
            existing = await repo.get_by_reference(
                data.reference_type, data.reference_id
            )
            if existing:
                logger.warning(
                    f"Ticket already exists for {data.reference_type}:{data.reference_id}"
                )
                return existing.id

            # Find applicable rule
            rule = self._find_rule(data.ticket_type, data.amount)

            ticket_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(timezone.utc)

            # Create ticket record
            await repo.create({
                "id": ticket_id,
                "ticket_type": data.ticket_type.value,
                "reference_type": data.reference_type,
                "reference_id": data.reference_id,
                "requester": data.requester.lower(),
                "amount": data.amount,
                "description": data.description,
                "request_data": data.request_data,
                "risk_assessment": data.risk_assessment,
                "status": ApprovalTicketStatus.PENDING.value,
                "required_approvals": rule.required_approvals,
                "current_approvals": 0,
                "current_rejections": 0,
                "sla_warning": rule.sla.get_warning_time(now),
                "sla_deadline": rule.sla.get_deadline_time(now),
            })

            # Audit log
            await self._log_audit(
                session,
                ticket_id=ticket_id,
                action="CREATED",
                actor=data.requester,
                new_status=ApprovalTicketStatus.PENDING.value,
                details={
                    "ticket_type": data.ticket_type.value,
                    "amount": str(data.amount) if data.amount else None,
                    "required_approvals": rule.required_approvals,
                    "required_level": rule.required_level.value,
                },
            )

            await session.commit()
            logger.info(
                f"Created ticket {ticket_id} type={data.ticket_type} "
                f"required_approvals={rule.required_approvals}"
            )

            return ticket_id

    async def process_action(
        self,
        ticket_id: str,
        request: ApprovalActionRequest,
        approver: str,
    ) -> bool:
        """Process an approval or rejection action.

        @param ticket_id - Ticket ID
        @param request - Action request
        @param approver - Approver address
        @returns True if action was successful
        @raises ValueError if ticket not found, invalid state, or insufficient level
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)
            record_repo = ApprovalRecordRepository(session)

            ticket = await repo.get_with_records(ticket_id)
            if not ticket:
                raise ValueError(f"Ticket {ticket_id} not found")

            # Check ticket is pending
            if ticket.status not in [
                ApprovalTicketStatus.PENDING.value,
                ApprovalTicketStatus.PARTIALLY_APPROVED.value,
            ]:
                raise ValueError(
                    f"Ticket {ticket_id} is not pending (status: {ticket.status})"
                )

            # Check approver hasn't already acted
            already_acted = await record_repo.has_already_acted(ticket_id, approver)
            if already_acted:
                raise ValueError(f"Approver {approver} has already acted on this ticket")

            # Get approver level
            approver_level = self.get_approver_level(approver)
            if not approver_level:
                raise ValueError(f"Approver {approver} is not registered")

            # Find rule and check level
            ticket_type = ApprovalTicketType(ticket.ticket_type)
            rule = self._find_rule(ticket_type, ticket.amount)
            if not self._can_approve(approver_level, rule.required_level):
                raise ValueError(
                    f"Approver level {approver_level} insufficient "
                    f"(required: {rule.required_level})"
                )

            now = datetime.now(timezone.utc)
            old_status = ticket.status
            record_id = str(uuid.uuid4())

            # Create approval record
            await record_repo.create({
                "id": record_id,
                "ticket_id": ticket_id,
                "approver": approver.lower(),
                "action": request.action.value,
                "reason": request.reason,
                "signature": request.signature,
            })

            # Update ticket based on action
            if request.action == ApprovalAction.APPROVE:
                new_approvals = ticket.current_approvals + 1
                update_data: dict[str, Any] = {"current_approvals": new_approvals}

                if new_approvals >= ticket.required_approvals:
                    # Ticket approved
                    update_data["status"] = ApprovalTicketStatus.APPROVED.value
                    update_data["result"] = ApprovalResult.APPROVED.value
                    update_data["resolved_at"] = now
                    update_data["resolved_by"] = approver.lower()
                    logger.info(f"Ticket {ticket_id} approved")
                else:
                    # Partially approved
                    update_data["status"] = ApprovalTicketStatus.PARTIALLY_APPROVED.value
                    logger.info(
                        f"Ticket {ticket_id} partially approved "
                        f"({new_approvals}/{ticket.required_approvals})"
                    )

                await repo.update(ticket_id, update_data)

            else:  # REJECT
                await repo.update(ticket_id, {
                    "current_rejections": ticket.current_rejections + 1,
                    "status": ApprovalTicketStatus.REJECTED.value,
                    "result": ApprovalResult.REJECTED.value,
                    "result_reason": request.reason,
                    "resolved_at": now,
                    "resolved_by": approver.lower(),
                })
                logger.info(f"Ticket {ticket_id} rejected: {request.reason}")

            # Audit log
            await self._log_audit(
                session,
                ticket_id=ticket_id,
                action=f"ACTION_{request.action.value}",
                actor=approver,
                old_status=old_status,
                new_status=update_data.get("status") if request.action == ApprovalAction.APPROVE else ApprovalTicketStatus.REJECTED.value,
                details={
                    "reason": request.reason,
                    "approver_level": approver_level.value,
                    "record_id": record_id,
                },
            )

            await session.commit()
            return True

    async def cancel_ticket(self, ticket_id: str, actor: str, reason: str) -> bool:
        """Cancel an approval ticket.

        @param ticket_id - Ticket ID
        @param actor - Actor cancelling
        @param reason - Cancellation reason
        @returns True if cancelled
        @raises ValueError if ticket not found or already resolved
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)

            ticket = await repo.get_by_id(ticket_id)
            if not ticket:
                raise ValueError(f"Ticket {ticket_id} not found")

            resolved_statuses = [
                ApprovalTicketStatus.APPROVED.value,
                ApprovalTicketStatus.REJECTED.value,
                ApprovalTicketStatus.EXPIRED.value,
                ApprovalTicketStatus.CANCELLED.value,
            ]
            if ticket.status in resolved_statuses:
                raise ValueError(f"Ticket {ticket_id} is already resolved")

            old_status = ticket.status
            now = datetime.now(timezone.utc)

            await repo.resolve(
                ticket_id,
                result=ApprovalResult.CANCELLED.value,
                result_reason=reason,
                resolved_by=actor.lower(),
            )

            # Audit log
            await self._log_audit(
                session,
                ticket_id=ticket_id,
                action="CANCELLED",
                actor=actor,
                old_status=old_status,
                new_status=ApprovalTicketStatus.CANCELLED.value,
                details={"reason": reason},
            )

            await session.commit()
            logger.info(f"Ticket {ticket_id} cancelled: {reason}")
            return True

    async def check_expired_tickets(self) -> list[str]:
        """Check and expire tickets past SLA deadline.

        @returns List of expired ticket IDs
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)

            expired_tickets = await repo.get_expired()
            expired_ids = []

            for ticket in expired_tickets:
                old_status = ticket.status

                await repo.resolve(
                    ticket.id,
                    result=ApprovalResult.EXPIRED.value,
                    result_reason="SLA deadline exceeded",
                )

                # Audit log
                await self._log_audit(
                    session,
                    ticket_id=ticket.id,
                    action="EXPIRED",
                    actor="SYSTEM",
                    old_status=old_status,
                    new_status=ApprovalTicketStatus.EXPIRED.value,
                )

                expired_ids.append(ticket.id)
                logger.warning(f"Ticket {ticket.id} expired")

            await session.commit()
            return expired_ids

    async def check_escalation(self) -> list[str]:
        """Check and escalate tickets past SLA warning.

        @returns List of escalated ticket IDs
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)

            need_escalation = await repo.get_past_warning()
            escalated_ids = []

            for ticket in need_escalation:
                ticket_type = ApprovalTicketType(ticket.ticket_type)
                rule = self._find_rule(ticket_type, ticket.amount)

                if not rule.escalation.enabled:
                    continue

                await repo.escalate(ticket.id, rule.escalation.notify_addresses or [])

                # Audit log
                await self._log_audit(
                    session,
                    ticket_id=ticket.id,
                    action="ESCALATED",
                    actor="SYSTEM",
                    details={
                        "escalate_to": rule.escalation.notify_addresses,
                        "escalate_level": rule.escalation.escalate_to_level.value
                        if rule.escalation.escalate_to_level else None,
                    },
                )

                escalated_ids.append(ticket.id)
                logger.warning(
                    f"Ticket {ticket.id} escalated to "
                    f"{rule.escalation.escalate_to_level}"
                )

            await session.commit()
            return escalated_ids

    async def get_ticket(self, ticket_id: str) -> ApprovalTicketDetail | None:
        """Get detailed ticket information.

        @param ticket_id - Ticket ID
        @returns Ticket detail or None if not found
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)
            ticket = await repo.get_with_records(ticket_id)

            if not ticket:
                return None

            # Convert records to schema
            records = [
                ApprovalRecord(
                    id=r.id,
                    approver=r.approver,
                    action=ApprovalAction(r.action),
                    reason=r.reason,
                    signature=r.signature,
                    timestamp=r.created_at,
                    level=self.get_approver_level(r.approver),
                )
                for r in ticket.records
            ]

            return ApprovalTicketDetail(
                id=ticket.id,
                ticket_type=ApprovalTicketType(ticket.ticket_type),
                reference_type=ticket.reference_type,
                reference_id=ticket.reference_id,
                requester=ticket.requester,
                amount=str(ticket.amount) if ticket.amount else None,
                description=ticket.description,
                request_data=ticket.request_data,
                risk_assessment=ticket.risk_assessment,
                status=ApprovalTicketStatus(ticket.status),
                required_approvals=ticket.required_approvals,
                current_approvals=ticket.current_approvals,
                current_rejections=ticket.current_rejections,
                sla_warning=ticket.sla_warning,
                sla_deadline=ticket.sla_deadline,
                escalated_at=ticket.escalated_at,
                escalated_to=ticket.escalated_to,
                result=ApprovalResult(ticket.result) if ticket.result else None,
                result_reason=ticket.result_reason,
                resolved_at=ticket.resolved_at,
                resolved_by=ticket.resolved_by,
                approval_records=records,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
            )

    async def list_tickets(
        self,
        status: ApprovalTicketStatus | None = None,
        ticket_type: ApprovalTicketType | None = None,
        requester: str | None = None,
        escalated_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> ApprovalTicketListResponse:
        """List approval tickets with filters.

        @param status - Filter by status
        @param ticket_type - Filter by type
        @param requester - Filter by requester
        @param escalated_only - Only show escalated tickets
        @param page - Page number
        @param page_size - Items per page
        @returns Paginated ticket list
        """
        async with self._session_factory() as session:
            from sqlalchemy import select, func, and_, desc

            # Build query
            conditions = []

            if status:
                conditions.append(ApprovalTicket.status == status.value)

            if ticket_type:
                conditions.append(ApprovalTicket.ticket_type == ticket_type.value)

            if requester:
                conditions.append(ApprovalTicket.requester == requester.lower())

            if escalated_only:
                conditions.append(ApprovalTicket.escalated_at.isnot(None))

            # Base query
            base_query = select(ApprovalTicket)
            if conditions:
                base_query = base_query.where(and_(*conditions))

            # Count total
            count_query = select(func.count()).select_from(base_query.subquery())
            total_result = await session.execute(count_query)
            total_items = total_result.scalar() or 0

            # Paginate
            offset = (page - 1) * page_size
            base_query = (
                base_query.order_by(desc(ApprovalTicket.created_at))
                .offset(offset)
                .limit(page_size)
            )

            result = await session.execute(base_query)
            tickets = result.scalars().all()

            total_pages = (
                (total_items + page_size - 1) // page_size if total_items > 0 else 0
            )

            items = [
                ApprovalTicketListItem(
                    id=t.id,
                    ticket_type=ApprovalTicketType(t.ticket_type),
                    reference_type=t.reference_type,
                    reference_id=t.reference_id,
                    requester=t.requester,
                    amount=str(t.amount) if t.amount else None,
                    status=ApprovalTicketStatus(t.status),
                    required_approvals=t.required_approvals,
                    current_approvals=t.current_approvals,
                    current_rejections=t.current_rejections,
                    sla_warning=t.sla_warning,
                    sla_deadline=t.sla_deadline,
                    escalated=t.escalated_at is not None,
                    created_at=t.created_at,
                )
                for t in tickets
            ]

            return ApprovalTicketListResponse(
                items=items,
                meta=PaginationMeta(
                    page=page,
                    page_size=page_size,
                    total_items=total_items,
                    total_pages=total_pages,
                ),
            )

    async def get_pending_for_approver(
        self,
        approver: str,
        page: int = 1,
        page_size: int = 20,
    ) -> ApprovalTicketListResponse:
        """Get pending tickets that an approver can act on.

        @param approver - Approver address
        @param page - Page number
        @param page_size - Items per page
        @returns Paginated ticket list
        """
        approver_level = self.get_approver_level(approver)
        if not approver_level:
            return ApprovalTicketListResponse(
                items=[],
                meta=PaginationMeta(
                    page=page, page_size=page_size, total_items=0, total_pages=0
                ),
            )

        async with self._session_factory() as session:
            repo = ApprovalRepository(session)
            record_repo = ApprovalRecordRepository(session)

            # Get pending tickets
            pending_tickets = await repo.get_pending()

            # Filter by level and not already acted
            filtered = []
            for ticket in pending_tickets:
                already_acted = await record_repo.has_already_acted(
                    ticket.id, approver
                )
                if already_acted:
                    continue

                ticket_type = ApprovalTicketType(ticket.ticket_type)
                rule = self._find_rule(ticket_type, ticket.amount)
                if self._can_approve(approver_level, rule.required_level):
                    filtered.append(ticket)

            # Sort by SLA deadline (most urgent first)
            filtered.sort(key=lambda t: t.sla_deadline)

            # Paginate
            total_items = len(filtered)
            total_pages = (
                (total_items + page_size - 1) // page_size if total_items > 0 else 0
            )
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_items = filtered[start_idx:end_idx]

            items = [
                ApprovalTicketListItem(
                    id=t.id,
                    ticket_type=ApprovalTicketType(t.ticket_type),
                    reference_type=t.reference_type,
                    reference_id=t.reference_id,
                    requester=t.requester,
                    amount=str(t.amount) if t.amount else None,
                    status=ApprovalTicketStatus(t.status),
                    required_approvals=t.required_approvals,
                    current_approvals=t.current_approvals,
                    current_rejections=t.current_rejections,
                    sla_warning=t.sla_warning,
                    sla_deadline=t.sla_deadline,
                    escalated=t.escalated_at is not None,
                    created_at=t.created_at,
                )
                for t in page_items
            ]

            return ApprovalTicketListResponse(
                items=items,
                meta=PaginationMeta(
                    page=page,
                    page_size=page_size,
                    total_items=total_items,
                    total_pages=total_pages,
                ),
            )

    async def get_stats(self) -> ApprovalStats:
        """Get approval workflow statistics.

        @returns Approval statistics
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)
            stats_data = await repo.get_statistics()

            status_counts = stats_data.get("by_status", {})
            avg_resolution_seconds = stats_data.get("avg_resolution_seconds", 0)

            # Count escalated tickets
            from sqlalchemy import select, func, and_

            escalated_query = (
                select(func.count(ApprovalTicket.id))
                .where(
                    and_(
                        ApprovalTicket.escalated_at.isnot(None),
                        ApprovalTicket.result.is_(None),
                    )
                )
            )
            result = await session.execute(escalated_query)
            escalated_count = result.scalar() or 0

            return ApprovalStats(
                total_tickets=stats_data.get("total_count", 0),
                pending_tickets=status_counts.get("PENDING", 0),
                partially_approved=status_counts.get("PARTIALLY_APPROVED", 0),
                approved_tickets=status_counts.get("APPROVED", 0),
                rejected_tickets=status_counts.get("REJECTED", 0),
                expired_tickets=status_counts.get("EXPIRED", 0),
                escalated_tickets=escalated_count,
                avg_resolution_hours=avg_resolution_seconds / 3600.0 if avg_resolution_seconds else 0.0,
            )

    async def get_ticket_by_reference(
        self, reference_type: str, reference_id: str
    ) -> ApprovalTicketDetail | None:
        """Get ticket by reference.

        @param reference_type - Type of reference
        @param reference_id - ID of referenced entity
        @returns Ticket detail or None if not found
        """
        async with self._session_factory() as session:
            repo = ApprovalRepository(session)
            ticket = await repo.get_by_reference(reference_type, reference_id)

            if not ticket:
                return None

            return await self.get_ticket(ticket.id)


# Singleton instance
_workflow_engine: ApprovalWorkflowEngine | None = None


def get_approval_workflow_engine() -> ApprovalWorkflowEngine:
    """Get or create approval workflow engine singleton.

    @returns ApprovalWorkflowEngine instance
    """
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = ApprovalWorkflowEngine()
    return _workflow_engine


def reset_approval_workflow_engine() -> None:
    """Reset approval workflow engine singleton (for testing)."""
    global _workflow_engine
    _workflow_engine = None
