"""Approval workflow engine."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

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
    AuditLogEntry,
    EscalationConfig,
    PaginationMeta,
    SLAConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class InMemoryTicket:
    """In-memory approval ticket."""

    id: str
    ticket_type: ApprovalTicketType
    reference_type: str
    reference_id: str
    requester: str
    amount: Decimal | None
    description: str | None
    request_data: dict[str, Any] | None
    risk_assessment: dict[str, Any] | None
    status: ApprovalTicketStatus
    required_approvals: int
    current_approvals: int
    current_rejections: int
    sla_warning: datetime
    sla_deadline: datetime
    escalated_at: datetime | None
    escalated_to: list[str] | None
    result: ApprovalResult | None
    result_reason: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    approval_records: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class ApprovalWorkflowEngine:
    """Engine for managing approval workflows.

    Features:
    - Multi-level approval support
    - Configurable rules based on amount/type
    - SLA tracking with warnings and deadlines
    - Auto-escalation on SLA breach
    - Complete audit trail
    """

    # Default approval rules
    DEFAULT_RULES: list[ApprovalRuleConfig] = [
        # Small redemptions - single operator approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REDEMPTION,
            max_amount=Decimal("10000000000000000000000"),  # 10000 tokens
            required_approvals=1,
            required_level=ApprovalLevel.OPERATOR,
            sla=SLAConfig(warning_hours=4, deadline_hours=24),
        ),
        # Large redemptions - manager approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REDEMPTION,
            min_amount=Decimal("10000000000000000000000"),
            max_amount=Decimal("100000000000000000000000"),  # 100000 tokens
            required_approvals=2,
            required_level=ApprovalLevel.MANAGER,
            sla=SLAConfig(warning_hours=2, deadline_hours=12),
        ),
        # Very large redemptions - admin approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REDEMPTION,
            min_amount=Decimal("100000000000000000000000"),
            required_approvals=3,
            required_level=ApprovalLevel.ADMIN,
            sla=SLAConfig(warning_hours=1, deadline_hours=8),
        ),
        # Rebalancing - manager approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.REBALANCING,
            required_approvals=2,
            required_level=ApprovalLevel.MANAGER,
            sla=SLAConfig(warning_hours=2, deadline_hours=12),
        ),
        # Emergency - immediate admin approval
        ApprovalRuleConfig(
            ticket_type=ApprovalTicketType.EMERGENCY,
            required_approvals=1,
            required_level=ApprovalLevel.EMERGENCY,
            sla=SLAConfig(warning_hours=0.5, deadline_hours=2),
            escalation=EscalationConfig(
                enabled=True,
                escalate_after_hours=0.5,
                escalate_to_level=ApprovalLevel.EMERGENCY,
            ),
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
        repository: Any = None,
    ):
        """Initialize approval workflow engine.

        Args:
            rules: Custom approval rules (uses defaults if None)
            repository: Optional database repository
        """
        self.rules = rules or self.DEFAULT_RULES
        self.repository = repository
        self._tickets: dict[str, InMemoryTicket] = {}
        self._audit_log: list[AuditLogEntry] = []
        self._approver_levels: dict[str, ApprovalLevel] = {}

    def set_approver_level(self, address: str, level: ApprovalLevel) -> None:
        """Set approval level for an address.

        Args:
            address: Approver wallet address
            level: Approval level
        """
        self._approver_levels[address.lower()] = level
        logger.info(f"Set approval level {level} for {address}")

    def get_approver_level(self, address: str) -> ApprovalLevel | None:
        """Get approval level for an address.

        Args:
            address: Approver wallet address

        Returns:
            Approval level or None if not set
        """
        return self._approver_levels.get(address.lower())

    def _find_rule(
        self,
        ticket_type: ApprovalTicketType,
        amount: Decimal | None,
    ) -> ApprovalRuleConfig:
        """Find matching rule for ticket type and amount.

        Args:
            ticket_type: Type of ticket
            amount: Amount if applicable

        Returns:
            Matching rule configuration
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

        Args:
            approver_level: Approver's level
            required_level: Required level

        Returns:
            True if approver can approve
        """
        return (
            self.LEVEL_HIERARCHY.get(approver_level, 0)
            >= self.LEVEL_HIERARCHY.get(required_level, 0)
        )

    def _log_audit(
        self,
        ticket_id: str,
        action: str,
        actor: str,
        old_status: ApprovalTicketStatus | None = None,
        new_status: ApprovalTicketStatus | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit entry.

        Args:
            ticket_id: Ticket ID
            action: Action type
            actor: Actor address
            old_status: Previous status
            new_status: New status
            details: Additional details
        """
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            action=action,
            actor=actor,
            timestamp=datetime.now(timezone.utc),
            old_status=old_status,
            new_status=new_status,
            details=details,
        )
        self._audit_log.append(entry)

    async def create_ticket(
        self,
        data: ApprovalTicketCreate,
    ) -> str:
        """Create a new approval ticket.

        Args:
            data: Ticket creation data

        Returns:
            Created ticket ID
        """
        # Find applicable rule
        rule = self._find_rule(data.ticket_type, data.amount)

        ticket_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        ticket = InMemoryTicket(
            id=ticket_id,
            ticket_type=data.ticket_type,
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            requester=data.requester,
            amount=data.amount,
            description=data.description,
            request_data=data.request_data,
            risk_assessment=data.risk_assessment,
            status=ApprovalTicketStatus.PENDING,
            required_approvals=rule.required_approvals,
            current_approvals=0,
            current_rejections=0,
            sla_warning=rule.sla.get_warning_time(now),
            sla_deadline=rule.sla.get_deadline_time(now),
            escalated_at=None,
            escalated_to=None,
            result=None,
            result_reason=None,
            resolved_at=None,
            resolved_by=None,
            approval_records=[],
            created_at=now,
            updated_at=now,
        )

        self._tickets[ticket_id] = ticket

        self._log_audit(
            ticket_id=ticket_id,
            action="CREATED",
            actor=data.requester,
            new_status=ApprovalTicketStatus.PENDING,
            details={
                "ticket_type": data.ticket_type.value,
                "amount": str(data.amount) if data.amount else None,
                "required_approvals": rule.required_approvals,
                "required_level": rule.required_level.value,
            },
        )

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

        Args:
            ticket_id: Ticket ID
            request: Action request
            approver: Approver address

        Returns:
            True if action was successful

        Raises:
            ValueError: If ticket not found, invalid state, or insufficient level
        """
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        # Check ticket is pending
        if ticket.status not in [
            ApprovalTicketStatus.PENDING,
            ApprovalTicketStatus.PARTIALLY_APPROVED,
        ]:
            raise ValueError(
                f"Ticket {ticket_id} is not pending (status: {ticket.status})"
            )

        # Check approver hasn't already acted
        for record in ticket.approval_records:
            if record["approver"].lower() == approver.lower():
                raise ValueError(f"Approver {approver} has already acted on this ticket")

        # Get approver level
        approver_level = self.get_approver_level(approver)
        if not approver_level:
            raise ValueError(f"Approver {approver} is not registered")

        # Find rule and check level
        rule = self._find_rule(ticket.ticket_type, ticket.amount)
        if not self._can_approve(approver_level, rule.required_level):
            raise ValueError(
                f"Approver level {approver_level} insufficient "
                f"(required: {rule.required_level})"
            )

        now = datetime.now(timezone.utc)
        old_status = ticket.status

        # Record the action
        record = {
            "id": str(uuid.uuid4()),
            "approver": approver,
            "action": request.action.value,
            "reason": request.reason,
            "signature": request.signature,
            "timestamp": now.isoformat(),
            "level": approver_level.value,
        }
        ticket.approval_records.append(record)
        ticket.updated_at = now

        if request.action == ApprovalAction.APPROVE:
            ticket.current_approvals += 1

            if ticket.current_approvals >= ticket.required_approvals:
                # Ticket approved
                ticket.status = ApprovalTicketStatus.APPROVED
                ticket.result = ApprovalResult.APPROVED
                ticket.resolved_at = now
                ticket.resolved_by = approver
                logger.info(f"Ticket {ticket_id} approved")
            else:
                # Partially approved
                ticket.status = ApprovalTicketStatus.PARTIALLY_APPROVED
                logger.info(
                    f"Ticket {ticket_id} partially approved "
                    f"({ticket.current_approvals}/{ticket.required_approvals})"
                )

        else:  # REJECT
            ticket.current_rejections += 1
            ticket.status = ApprovalTicketStatus.REJECTED
            ticket.result = ApprovalResult.REJECTED
            ticket.result_reason = request.reason
            ticket.resolved_at = now
            ticket.resolved_by = approver
            logger.info(f"Ticket {ticket_id} rejected: {request.reason}")

        self._log_audit(
            ticket_id=ticket_id,
            action=f"ACTION_{request.action.value}",
            actor=approver,
            old_status=old_status,
            new_status=ticket.status,
            details={
                "reason": request.reason,
                "approver_level": approver_level.value,
                "current_approvals": ticket.current_approvals,
                "current_rejections": ticket.current_rejections,
            },
        )

        return True

    async def cancel_ticket(self, ticket_id: str, actor: str, reason: str) -> bool:
        """Cancel an approval ticket.

        Args:
            ticket_id: Ticket ID
            actor: Actor cancelling
            reason: Cancellation reason

        Returns:
            True if cancelled

        Raises:
            ValueError: If ticket not found or already resolved
        """
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        if ticket.status in [
            ApprovalTicketStatus.APPROVED,
            ApprovalTicketStatus.REJECTED,
            ApprovalTicketStatus.EXPIRED,
            ApprovalTicketStatus.CANCELLED,
        ]:
            raise ValueError(f"Ticket {ticket_id} is already resolved")

        old_status = ticket.status
        now = datetime.now(timezone.utc)

        ticket.status = ApprovalTicketStatus.CANCELLED
        ticket.result = ApprovalResult.CANCELLED
        ticket.result_reason = reason
        ticket.resolved_at = now
        ticket.resolved_by = actor
        ticket.updated_at = now

        self._log_audit(
            ticket_id=ticket_id,
            action="CANCELLED",
            actor=actor,
            old_status=old_status,
            new_status=ApprovalTicketStatus.CANCELLED,
            details={"reason": reason},
        )

        logger.info(f"Ticket {ticket_id} cancelled: {reason}")
        return True

    async def check_expired_tickets(self) -> list[str]:
        """Check and expire tickets past SLA deadline.

        Returns:
            List of expired ticket IDs
        """
        expired = []
        now = datetime.now(timezone.utc)

        for ticket_id, ticket in self._tickets.items():
            if ticket.status in [
                ApprovalTicketStatus.PENDING,
                ApprovalTicketStatus.PARTIALLY_APPROVED,
            ]:
                if now > ticket.sla_deadline:
                    old_status = ticket.status
                    ticket.status = ApprovalTicketStatus.EXPIRED
                    ticket.result = ApprovalResult.EXPIRED
                    ticket.result_reason = "SLA deadline exceeded"
                    ticket.resolved_at = now
                    ticket.updated_at = now

                    self._log_audit(
                        ticket_id=ticket_id,
                        action="EXPIRED",
                        actor="SYSTEM",
                        old_status=old_status,
                        new_status=ApprovalTicketStatus.EXPIRED,
                    )

                    expired.append(ticket_id)
                    logger.warning(f"Ticket {ticket_id} expired")

        return expired

    async def check_escalation(self) -> list[str]:
        """Check and escalate tickets past SLA warning.

        Returns:
            List of escalated ticket IDs
        """
        escalated = []
        now = datetime.now(timezone.utc)

        for ticket_id, ticket in self._tickets.items():
            if ticket.status in [
                ApprovalTicketStatus.PENDING,
                ApprovalTicketStatus.PARTIALLY_APPROVED,
            ]:
                if ticket.escalated_at is None and now > ticket.sla_warning:
                    rule = self._find_rule(ticket.ticket_type, ticket.amount)
                    if rule.escalation.enabled:
                        ticket.escalated_at = now
                        ticket.escalated_to = rule.escalation.notify_addresses
                        ticket.updated_at = now

                        self._log_audit(
                            ticket_id=ticket_id,
                            action="ESCALATED",
                            actor="SYSTEM",
                            details={
                                "escalate_to": rule.escalation.notify_addresses,
                                "escalate_level": rule.escalation.escalate_to_level.value,
                            },
                        )

                        escalated.append(ticket_id)
                        logger.warning(
                            f"Ticket {ticket_id} escalated to "
                            f"{rule.escalation.escalate_to_level}"
                        )

        return escalated

    async def get_ticket(self, ticket_id: str) -> ApprovalTicketDetail | None:
        """Get detailed ticket information.

        Args:
            ticket_id: Ticket ID

        Returns:
            Ticket detail or None if not found
        """
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None

        return ApprovalTicketDetail(
            id=ticket.id,
            ticket_type=ticket.ticket_type,
            reference_type=ticket.reference_type,
            reference_id=ticket.reference_id,
            requester=ticket.requester,
            amount=str(ticket.amount) if ticket.amount else None,
            description=ticket.description,
            request_data=ticket.request_data,
            risk_assessment=ticket.risk_assessment,
            status=ticket.status,
            required_approvals=ticket.required_approvals,
            current_approvals=ticket.current_approvals,
            current_rejections=ticket.current_rejections,
            sla_warning=ticket.sla_warning,
            sla_deadline=ticket.sla_deadline,
            escalated_at=ticket.escalated_at,
            escalated_to=ticket.escalated_to,
            result=ticket.result,
            result_reason=ticket.result_reason,
            resolved_at=ticket.resolved_at,
            resolved_by=ticket.resolved_by,
            approval_records=[
                ApprovalRecord(
                    id=r["id"],
                    approver=r["approver"],
                    action=ApprovalAction(r["action"]),
                    reason=r.get("reason"),
                    signature=r.get("signature"),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    level=ApprovalLevel(r["level"]),
                )
                for r in ticket.approval_records
            ],
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

        Args:
            status: Filter by status
            ticket_type: Filter by type
            requester: Filter by requester
            escalated_only: Only show escalated tickets
            page: Page number
            page_size: Items per page

        Returns:
            Paginated ticket list
        """
        filtered = list(self._tickets.values())

        if status:
            filtered = [t for t in filtered if t.status == status]

        if ticket_type:
            filtered = [t for t in filtered if t.ticket_type == ticket_type]

        if requester:
            filtered = [
                t for t in filtered if t.requester.lower() == requester.lower()
            ]

        if escalated_only:
            filtered = [t for t in filtered if t.escalated_at is not None]

        # Sort by created_at descending
        filtered.sort(key=lambda t: t.created_at, reverse=True)

        # Paginate
        total_items = len(filtered)
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered[start_idx:end_idx]

        items = [
            ApprovalTicketListItem(
                id=t.id,
                ticket_type=t.ticket_type,
                reference_type=t.reference_type,
                reference_id=t.reference_id,
                requester=t.requester,
                amount=str(t.amount) if t.amount else None,
                status=t.status,
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

    async def get_pending_for_approver(
        self,
        approver: str,
        page: int = 1,
        page_size: int = 20,
    ) -> ApprovalTicketListResponse:
        """Get pending tickets that an approver can act on.

        Args:
            approver: Approver address
            page: Page number
            page_size: Items per page

        Returns:
            Paginated ticket list
        """
        approver_level = self.get_approver_level(approver)
        if not approver_level:
            return ApprovalTicketListResponse(
                items=[],
                meta=PaginationMeta(
                    page=page, page_size=page_size, total_items=0, total_pages=0
                ),
            )

        filtered = []
        for ticket in self._tickets.values():
            if ticket.status not in [
                ApprovalTicketStatus.PENDING,
                ApprovalTicketStatus.PARTIALLY_APPROVED,
            ]:
                continue

            # Check if approver hasn't already acted
            already_acted = any(
                r["approver"].lower() == approver.lower()
                for r in ticket.approval_records
            )
            if already_acted:
                continue

            # Check if approver has sufficient level
            rule = self._find_rule(ticket.ticket_type, ticket.amount)
            if self._can_approve(approver_level, rule.required_level):
                filtered.append(ticket)

        # Sort by SLA deadline (most urgent first)
        filtered.sort(key=lambda t: t.sla_deadline)

        # Paginate
        total_items = len(filtered)
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered[start_idx:end_idx]

        items = [
            ApprovalTicketListItem(
                id=t.id,
                ticket_type=t.ticket_type,
                reference_type=t.reference_type,
                reference_id=t.reference_id,
                requester=t.requester,
                amount=str(t.amount) if t.amount else None,
                status=t.status,
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

        Returns:
            Approval statistics
        """
        stats = ApprovalStats()
        resolution_times = []

        for ticket in self._tickets.values():
            stats.total_tickets += 1

            if ticket.status == ApprovalTicketStatus.PENDING:
                stats.pending_tickets += 1
            elif ticket.status == ApprovalTicketStatus.PARTIALLY_APPROVED:
                stats.partially_approved += 1
            elif ticket.status == ApprovalTicketStatus.APPROVED:
                stats.approved_tickets += 1
            elif ticket.status == ApprovalTicketStatus.REJECTED:
                stats.rejected_tickets += 1
            elif ticket.status == ApprovalTicketStatus.EXPIRED:
                stats.expired_tickets += 1

            if ticket.escalated_at is not None and ticket.result is None:
                stats.escalated_tickets += 1

            if ticket.resolved_at:
                duration = (ticket.resolved_at - ticket.created_at).total_seconds() / 3600
                resolution_times.append(duration)

        if resolution_times:
            stats.avg_resolution_hours = sum(resolution_times) / len(resolution_times)

        return stats

    def get_audit_log(
        self,
        ticket_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """Get audit log entries.

        Args:
            ticket_id: Filter by ticket ID
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        entries = self._audit_log

        if ticket_id:
            entries = [e for e in entries if e.ticket_id == ticket_id]

        # Return most recent first
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]


# Singleton instance
_workflow_engine: ApprovalWorkflowEngine | None = None


def get_approval_workflow_engine() -> ApprovalWorkflowEngine:
    """Get or create approval workflow engine singleton."""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = ApprovalWorkflowEngine()
    return _workflow_engine
