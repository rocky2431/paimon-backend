"""Tests for approval workflow engine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.approval import (
    ApprovalAction,
    ApprovalLevel,
    ApprovalResult,
    ApprovalRuleConfig,
    ApprovalTicketCreate,
    ApprovalTicketStatus,
    ApprovalTicketType,
    ApprovalWorkflowEngine,
    EscalationConfig,
    SLAConfig,
)
from app.services.approval.schemas import ApprovalActionRequest


class TestApprovalWorkflowEngine:
    """Tests for ApprovalWorkflowEngine."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        # Register some approvers
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)
        self.engine.set_approver_level("0x" + "2" * 40, ApprovalLevel.MANAGER)
        self.engine.set_approver_level("0x" + "3" * 40, ApprovalLevel.ADMIN)
        self.engine.set_approver_level("0x" + "4" * 40, ApprovalLevel.EMERGENCY)

    @pytest.mark.asyncio
    async def test_create_ticket(self):
        """Test creating an approval ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
            description="Test redemption",
        )

        ticket_id = await self.engine.create_ticket(data)

        assert ticket_id.startswith("APR-")
        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket is not None
        assert ticket.status == ApprovalTicketStatus.PENDING
        assert ticket.ticket_type == ApprovalTicketType.REDEMPTION

    @pytest.mark.asyncio
    async def test_create_ticket_rule_matching(self):
        """Test that tickets get correct rules based on amount."""
        # Small redemption
        small_data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="1",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),  # 1 token
        )
        small_id = await self.engine.create_ticket(small_data)
        small_ticket = await self.engine.get_ticket(small_id)
        assert small_ticket.required_approvals == 1

        # Large redemption
        large_data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="2",
            requester="0x" + "a" * 40,
            amount=Decimal("50000000000000000000000"),  # 50000 tokens
        )
        large_id = await self.engine.create_ticket(large_data)
        large_ticket = await self.engine.get_ticket(large_id)
        assert large_ticket.required_approvals == 2

    @pytest.mark.asyncio
    async def test_approve_ticket(self):
        """Test approving a ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(
            action=ApprovalAction.APPROVE,
            reason="Verified",
        )
        result = await self.engine.process_action(
            ticket_id, request, "0x" + "1" * 40  # Operator
        )

        assert result is True
        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.APPROVED
        assert ticket.result == ApprovalResult.APPROVED

    @pytest.mark.asyncio
    async def test_reject_ticket(self):
        """Test rejecting a ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(
            action=ApprovalAction.REJECT,
            reason="Suspicious activity",
        )
        result = await self.engine.process_action(
            ticket_id, request, "0x" + "1" * 40
        )

        assert result is True
        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.REJECTED
        assert ticket.result == ApprovalResult.REJECTED
        assert ticket.result_reason == "Suspicious activity"

    @pytest.mark.asyncio
    async def test_multi_level_approval(self):
        """Test multi-level approval requiring multiple approvers."""
        # Large redemption requiring 2 approvals
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("50000000000000000000000"),  # 50000 tokens
        )
        ticket_id = await self.engine.create_ticket(data)

        # First approval
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(
            ticket_id, request, "0x" + "2" * 40  # Manager
        )

        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.PARTIALLY_APPROVED
        assert ticket.current_approvals == 1

        # Second approval
        await self.engine.process_action(
            ticket_id, request, "0x" + "3" * 40  # Admin
        )

        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.APPROVED
        assert ticket.current_approvals == 2

    @pytest.mark.asyncio
    async def test_insufficient_level(self):
        """Test that insufficient level is rejected."""
        # Large redemption requiring manager level
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("50000000000000000000000"),  # Requires manager
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)

        with pytest.raises(ValueError, match="insufficient"):
            await self.engine.process_action(
                ticket_id, request, "0x" + "1" * 40  # Operator - too low
            )

    @pytest.mark.asyncio
    async def test_double_approval_prevented(self):
        """Test that same approver cannot approve twice."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("50000000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(ticket_id, request, "0x" + "2" * 40)

        with pytest.raises(ValueError, match="already acted"):
            await self.engine.process_action(ticket_id, request, "0x" + "2" * 40)

    @pytest.mark.asyncio
    async def test_cancel_ticket(self):
        """Test cancelling a ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        result = await self.engine.cancel_ticket(
            ticket_id, "0x" + "a" * 40, "Request withdrawn"
        )

        assert result is True
        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.CANCELLED
        assert ticket.result == ApprovalResult.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_resolved_ticket_fails(self):
        """Test that resolved tickets cannot be cancelled."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        # Approve it first
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        with pytest.raises(ValueError, match="already resolved"):
            await self.engine.cancel_ticket(ticket_id, "0x" + "a" * 40, "Too late")

    @pytest.mark.asyncio
    async def test_ticket_not_found(self):
        """Test handling of non-existent ticket."""
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)

        with pytest.raises(ValueError, match="not found"):
            await self.engine.process_action("APR-INVALID", request, "0x" + "1" * 40)

    @pytest.mark.asyncio
    async def test_unregistered_approver(self):
        """Test that unregistered approvers are rejected."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)

        with pytest.raises(ValueError, match="not registered"):
            await self.engine.process_action(
                ticket_id, request, "0x" + "9" * 40  # Not registered
            )


class TestSLAAndEscalation:
    """Tests for SLA tracking and escalation."""

    def setup_method(self):
        """Set up test fixtures with custom SLA rules."""
        self.rules = [
            ApprovalRuleConfig(
                ticket_type=ApprovalTicketType.REDEMPTION,
                required_approvals=1,
                required_level=ApprovalLevel.OPERATOR,
                sla=SLAConfig(warning_hours=1, deadline_hours=2),
                escalation=EscalationConfig(
                    enabled=True,
                    escalate_after_hours=0.5,
                    escalate_to_level=ApprovalLevel.ADMIN,
                    notify_addresses=["0x" + "9" * 40],
                ),
            ),
        ]
        self.engine = ApprovalWorkflowEngine(rules=self.rules)
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)

    @pytest.mark.asyncio
    async def test_sla_times_calculated(self):
        """Test that SLA times are calculated correctly."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.sla_warning > ticket.created_at
        assert ticket.sla_deadline > ticket.sla_warning

    @pytest.mark.asyncio
    async def test_check_escalation(self):
        """Test escalation on SLA warning by manipulating ticket times."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        # Manually set the warning time to the past to trigger escalation
        ticket = self.engine._tickets[ticket_id]
        ticket.sla_warning = datetime.now(timezone.utc) - timedelta(hours=1)

        escalated = await self.engine.check_escalation()

        assert ticket_id in escalated
        updated_ticket = await self.engine.get_ticket(ticket_id)
        assert updated_ticket.escalated_at is not None
        assert updated_ticket.escalated_to == ["0x" + "9" * 40]

    @pytest.mark.asyncio
    async def test_check_expired(self):
        """Test expiration on SLA deadline by manipulating ticket times."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        # Manually set the deadline to the past to trigger expiration
        ticket = self.engine._tickets[ticket_id]
        ticket.sla_deadline = datetime.now(timezone.utc) - timedelta(hours=1)

        expired = await self.engine.check_expired_tickets()

        assert ticket_id in expired
        updated_ticket = await self.engine.get_ticket(ticket_id)
        assert updated_ticket.status == ApprovalTicketStatus.EXPIRED
        assert updated_ticket.result == ApprovalResult.EXPIRED


class TestApprovalListing:
    """Tests for ticket listing and filtering."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)
        self.engine.set_approver_level("0x" + "2" * 40, ApprovalLevel.MANAGER)
        self.engine.set_approver_level("0x" + "3" * 40, ApprovalLevel.ADMIN)

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """Test listing when empty."""
        result = await self.engine.list_tickets()

        assert result.items == []
        assert result.meta.total_items == 0

    @pytest.mark.asyncio
    async def test_list_with_filters(self):
        """Test listing with filters."""
        # Create multiple tickets with small amounts (operator level)
        for i in range(3):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
                amount=Decimal("1000000000000000000"),  # Small amount for operator
            )
            await self.engine.create_ticket(data)

        # Approve one
        tickets = await self.engine.list_tickets()
        ticket_id = tickets.items[0].id
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        # Filter by status
        pending = await self.engine.list_tickets(status=ApprovalTicketStatus.PENDING)
        assert len(pending.items) == 2

        approved = await self.engine.list_tickets(status=ApprovalTicketStatus.APPROVED)
        assert len(approved.items) == 1

    @pytest.mark.asyncio
    async def test_list_pagination(self):
        """Test pagination."""
        for i in range(25):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
            )
            await self.engine.create_ticket(data)

        # Page 1
        result = await self.engine.list_tickets(page=1, page_size=10)
        assert len(result.items) == 10
        assert result.meta.total_items == 25
        assert result.meta.total_pages == 3

        # Page 3
        result = await self.engine.list_tickets(page=3, page_size=10)
        assert len(result.items) == 5

    @pytest.mark.asyncio
    async def test_get_pending_for_approver(self):
        """Test getting pending tickets for an approver."""
        # Create tickets with small amounts (operator can approve)
        for i in range(3):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
                amount=Decimal("1000000000000000000"),  # Small amount
            )
            await self.engine.create_ticket(data)

        result = await self.engine.get_pending_for_approver("0x" + "1" * 40)
        assert len(result.items) == 3

        # After acting on one, it should be excluded
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(
            result.items[0].id, request, "0x" + "1" * 40
        )

        result = await self.engine.get_pending_for_approver("0x" + "1" * 40)
        assert len(result.items) == 2


class TestApprovalStats:
    """Tests for approval statistics."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)
        self.engine.set_approver_level("0x" + "3" * 40, ApprovalLevel.ADMIN)

    @pytest.mark.asyncio
    async def test_empty_stats(self):
        """Test stats when empty."""
        stats = await self.engine.get_stats()

        assert stats.total_tickets == 0
        assert stats.pending_tickets == 0
        assert stats.approved_tickets == 0

    @pytest.mark.asyncio
    async def test_stats_calculation(self):
        """Test stats are calculated correctly."""
        # Create tickets with small amounts (operator can approve)
        for i in range(5):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
                amount=Decimal("1000000000000000000"),  # Small amount
            )
            await self.engine.create_ticket(data)

        # Approve 2
        tickets = await self.engine.list_tickets()
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(tickets.items[0].id, request, "0x" + "1" * 40)
        await self.engine.process_action(tickets.items[1].id, request, "0x" + "1" * 40)

        # Reject 1
        request = ApprovalActionRequest(action=ApprovalAction.REJECT, reason="Test")
        await self.engine.process_action(tickets.items[2].id, request, "0x" + "1" * 40)

        stats = await self.engine.get_stats()

        assert stats.total_tickets == 5
        assert stats.pending_tickets == 2
        assert stats.approved_tickets == 2
        assert stats.rejected_tickets == 1


class TestAuditLog:
    """Tests for audit logging."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)
        self.engine.set_approver_level("0x" + "3" * 40, ApprovalLevel.ADMIN)

    @pytest.mark.asyncio
    async def test_audit_log_on_create(self):
        """Test audit log entry on ticket creation."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        audit_log = self.engine.get_audit_log(ticket_id)

        assert len(audit_log) == 1
        assert audit_log[0].action == "CREATED"
        assert audit_log[0].actor == "0x" + "a" * 40

    @pytest.mark.asyncio
    async def test_audit_log_on_approve(self):
        """Test audit log entry on approval."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),  # Small amount for operator
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(action=ApprovalAction.APPROVE, reason="OK")
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        audit_log = self.engine.get_audit_log(ticket_id)

        assert len(audit_log) == 2
        # Most recent first
        assert audit_log[0].action == "ACTION_APPROVE"
        assert audit_log[0].actor == "0x" + "1" * 40
        assert audit_log[0].old_status == ApprovalTicketStatus.PENDING
        assert audit_log[0].new_status == ApprovalTicketStatus.APPROVED

    @pytest.mark.asyncio
    async def test_audit_log_on_cancel(self):
        """Test audit log entry on cancellation."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        await self.engine.cancel_ticket(ticket_id, "0x" + "a" * 40, "Withdrawn")

        audit_log = self.engine.get_audit_log(ticket_id)

        assert len(audit_log) == 2
        assert audit_log[0].action == "CANCELLED"
        assert audit_log[0].details == {"reason": "Withdrawn"}


class TestApproverLevels:
    """Tests for approver level management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()

    def test_set_and_get_level(self):
        """Test setting and getting approver levels."""
        address = "0x" + "1" * 40

        self.engine.set_approver_level(address, ApprovalLevel.MANAGER)

        level = self.engine.get_approver_level(address)
        assert level == ApprovalLevel.MANAGER

    def test_case_insensitive(self):
        """Test that address lookup is case-insensitive."""
        address_lower = "0x" + "a" * 40
        address_upper = "0x" + "A" * 40

        self.engine.set_approver_level(address_lower, ApprovalLevel.ADMIN)

        level = self.engine.get_approver_level(address_upper)
        assert level == ApprovalLevel.ADMIN

    def test_unknown_approver(self):
        """Test that unknown approver returns None."""
        level = self.engine.get_approver_level("0x" + "9" * 40)
        assert level is None

    def test_level_hierarchy(self):
        """Test level hierarchy checking."""
        engine = ApprovalWorkflowEngine()

        # Admin can approve operator-level
        assert engine._can_approve(ApprovalLevel.ADMIN, ApprovalLevel.OPERATOR)

        # Operator cannot approve admin-level
        assert not engine._can_approve(ApprovalLevel.OPERATOR, ApprovalLevel.ADMIN)

        # Same level is OK
        assert engine._can_approve(ApprovalLevel.MANAGER, ApprovalLevel.MANAGER)


class TestDifferentTicketTypes:
    """Tests for different ticket types."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)
        self.engine.set_approver_level("0x" + "2" * 40, ApprovalLevel.MANAGER)
        self.engine.set_approver_level("0x" + "3" * 40, ApprovalLevel.ADMIN)
        self.engine.set_approver_level("0x" + "4" * 40, ApprovalLevel.EMERGENCY)

    @pytest.mark.asyncio
    async def test_emergency_ticket(self):
        """Test emergency ticket requires emergency level."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.EMERGENCY,
            reference_type="emergency",
            reference_id="123",
            requester="0x" + "a" * 40,
            description="Critical issue",
        )
        ticket_id = await self.engine.create_ticket(data)

        # Operator cannot approve emergency
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        with pytest.raises(ValueError, match="insufficient"):
            await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        # Emergency level can
        await self.engine.process_action(ticket_id, request, "0x" + "4" * 40)
        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.APPROVED

    @pytest.mark.asyncio
    async def test_rebalancing_ticket(self):
        """Test rebalancing ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REBALANCING,
            reference_type="rebalance",
            reference_id="456",
            requester="0x" + "a" * 40,
        )
        ticket_id = await self.engine.create_ticket(data)

        ticket = await self.engine.get_ticket(ticket_id)
        # Rebalancing requires 2 approvals
        assert ticket.required_approvals == 2
