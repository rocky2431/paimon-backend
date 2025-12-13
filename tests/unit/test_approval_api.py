"""Tests for approval API endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.approval import (
    ApprovalLevel,
    ApprovalTicketCreate,
    ApprovalTicketStatus,
    ApprovalTicketType,
    ApprovalWorkflowEngine,
)
from app.services.approval.schemas import ApprovalActionRequest, ApprovalAction


class TestApprovalAPIEndpoints:
    """Tests for approval API endpoint logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)
        self.engine.set_approver_level("0x" + "2" * 40, ApprovalLevel.MANAGER)
        self.engine.set_approver_level("0x" + "3" * 40, ApprovalLevel.ADMIN)

    @pytest.mark.asyncio
    async def test_list_tickets_empty(self):
        """Test listing when empty."""
        result = await self.engine.list_tickets()

        assert result.items == []
        assert result.meta.total_items == 0

    @pytest.mark.asyncio
    async def test_list_tickets_with_filters(self):
        """Test listing with status filter."""
        # Create tickets
        for i in range(3):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
                amount=Decimal("1000000000000000000"),
            )
            await self.engine.create_ticket(data)

        result = await self.engine.list_tickets(
            status=ApprovalTicketStatus.PENDING
        )

        assert len(result.items) == 3
        assert all(item.status == ApprovalTicketStatus.PENDING for item in result.items)

    @pytest.mark.asyncio
    async def test_get_ticket_detail(self):
        """Test getting ticket detail."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
            description="Test redemption request",
        )
        ticket_id = await self.engine.create_ticket(data)

        ticket = await self.engine.get_ticket(ticket_id)

        assert ticket is not None
        assert ticket.id == ticket_id
        assert ticket.ticket_type == ApprovalTicketType.REDEMPTION
        assert ticket.description == "Test redemption request"

    @pytest.mark.asyncio
    async def test_get_pending_for_approver(self):
        """Test getting pending tickets for approver."""
        # Create tickets
        for i in range(3):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
                amount=Decimal("1000000000000000000"),
            )
            await self.engine.create_ticket(data)

        result = await self.engine.get_pending_for_approver("0x" + "1" * 40)

        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_process_action_approve(self):
        """Test approving a ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(action=ApprovalAction.APPROVE, reason="OK")
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.APPROVED

    @pytest.mark.asyncio
    async def test_process_action_reject(self):
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
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.REJECTED
        assert ticket.result_reason == "Suspicious activity"

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

        await self.engine.cancel_ticket(ticket_id, "0x" + "a" * 40, "Withdrawn")

        ticket = await self.engine.get_ticket(ticket_id)
        assert ticket.status == ApprovalTicketStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting statistics."""
        # Create and process some tickets
        for i in range(3):
            data = ApprovalTicketCreate(
                ticket_type=ApprovalTicketType.REDEMPTION,
                reference_type="redemption",
                reference_id=str(i),
                requester="0x" + "a" * 40,
                amount=Decimal("1000000000000000000"),
            )
            await self.engine.create_ticket(data)

        stats = await self.engine.get_stats()

        assert stats.total_tickets == 3
        assert stats.pending_tickets == 3

    @pytest.mark.asyncio
    async def test_get_audit_log(self):
        """Test getting audit log."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        # Process an action
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        audit_log = self.engine.get_audit_log(ticket_id)

        assert len(audit_log) == 2  # CREATED + ACTION_APPROVE
        assert audit_log[0].action == "ACTION_APPROVE"
        assert audit_log[1].action == "CREATED"


class TestApprovalAPIErrors:
    """Tests for approval API error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()
        self.engine.set_approver_level("0x" + "1" * 40, ApprovalLevel.OPERATOR)

    @pytest.mark.asyncio
    async def test_ticket_not_found(self):
        """Test error when ticket not found."""
        ticket = await self.engine.get_ticket("APR-INVALID")
        assert ticket is None

    @pytest.mark.asyncio
    async def test_action_on_invalid_ticket(self):
        """Test error when processing action on invalid ticket."""
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)

        with pytest.raises(ValueError, match="not found"):
            await self.engine.process_action("APR-INVALID", request, "0x" + "1" * 40)

    @pytest.mark.asyncio
    async def test_action_insufficient_level(self):
        """Test error when approver has insufficient level."""
        # Create a large redemption requiring manager level
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("50000000000000000000000"),  # Large amount
        )
        ticket_id = await self.engine.create_ticket(data)

        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)

        with pytest.raises(ValueError, match="insufficient"):
            await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

    @pytest.mark.asyncio
    async def test_cancel_resolved_ticket(self):
        """Test error when cancelling resolved ticket."""
        data = ApprovalTicketCreate(
            ticket_type=ApprovalTicketType.REDEMPTION,
            reference_type="redemption",
            reference_id="123",
            requester="0x" + "a" * 40,
            amount=Decimal("1000000000000000000"),
        )
        ticket_id = await self.engine.create_ticket(data)

        # Approve first
        request = ApprovalActionRequest(action=ApprovalAction.APPROVE)
        await self.engine.process_action(ticket_id, request, "0x" + "1" * 40)

        # Try to cancel
        with pytest.raises(ValueError, match="already resolved"):
            await self.engine.cancel_ticket(ticket_id, "0x" + "a" * 40, "Withdraw")


class TestApprovalScheduledTasks:
    """Tests for scheduled approval tasks."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ApprovalWorkflowEngine()

    @pytest.mark.asyncio
    async def test_check_escalation_no_pending(self):
        """Test escalation check with no pending tickets."""
        escalated = await self.engine.check_escalation()
        assert escalated == []

    @pytest.mark.asyncio
    async def test_check_expiration_no_pending(self):
        """Test expiration check with no pending tickets."""
        expired = await self.engine.check_expired_tickets()
        assert expired == []
