"""Tests for redemption management service and API."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.redemption import (
    RedemptionChannel,
    RedemptionCreate,
    RedemptionFilterParams,
    RedemptionService,
    RedemptionStatus,
)
from app.services.redemption.schemas import (
    ApprovalRequest,
    RedemptionAction,
    RedemptionSortField,
    SortOrder,
)


class TestRedemptionService:
    """Tests for RedemptionService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RedemptionService()
        self.sample_redemption = RedemptionCreate(
            request_id=Decimal(1),
            tx_hash="0x" + "a" * 64,
            block_number=12345,
            log_index=0,
            owner="0x" + "1" * 40,
            receiver="0x" + "2" * 40,
            shares=Decimal("1000000000000000000"),
            gross_amount=Decimal("1000000000000000000"),
            locked_nav=Decimal("1000000000000000000"),
            estimated_fee=Decimal("10000000000000000"),
            request_time=datetime.now(timezone.utc),
            settlement_time=datetime.now(timezone.utc) + timedelta(hours=24),
            channel=RedemptionChannel.STANDARD,
            requires_approval=False,
        )

    @pytest.mark.asyncio
    async def test_create_redemption(self):
        """Test creating a redemption request."""
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        assert redemption_id == 1
        detail = await self.service.get_redemption_detail(redemption_id)
        assert detail is not None
        assert detail.status == RedemptionStatus.PENDING
        assert len(detail.timeline.events) == 1
        assert detail.timeline.events[0].event_type == "CREATED"

    @pytest.mark.asyncio
    async def test_create_redemption_requires_approval(self):
        """Test creating a redemption that requires approval."""
        self.sample_redemption.requires_approval = True
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        detail = await self.service.get_redemption_detail(redemption_id)
        assert detail is not None
        assert detail.status == RedemptionStatus.PENDING_APPROVAL
        assert len(detail.timeline.events) == 2
        assert detail.timeline.events[1].event_type == "PENDING_APPROVAL"

    @pytest.mark.asyncio
    async def test_list_redemptions_empty(self):
        """Test listing redemptions when empty."""
        result = await self.service.list_redemptions(RedemptionFilterParams())

        assert result.items == []
        assert result.meta.total_items == 0
        assert result.meta.total_pages == 0

    @pytest.mark.asyncio
    async def test_list_redemptions_with_items(self):
        """Test listing redemptions with items."""
        # Create multiple redemptions
        for i in range(3):
            data = RedemptionCreate(
                request_id=Decimal(i + 1),
                tx_hash=f"0x{'a' * 62}{i:02d}",
                block_number=12345 + i,
                log_index=0,
                owner="0x" + "1" * 40,
                receiver="0x" + "2" * 40,
                shares=Decimal("1000000000000000000") * (i + 1),
                gross_amount=Decimal("1000000000000000000") * (i + 1),
                locked_nav=Decimal("1000000000000000000"),
                estimated_fee=Decimal("10000000000000000"),
                request_time=datetime.now(timezone.utc) - timedelta(hours=i),
                settlement_time=datetime.now(timezone.utc) + timedelta(hours=24),
                channel=RedemptionChannel.STANDARD,
                requires_approval=False,
            )
            await self.service.create_redemption(data)

        result = await self.service.list_redemptions(RedemptionFilterParams())

        assert len(result.items) == 3
        assert result.meta.total_items == 3
        assert result.meta.total_pages == 1

    @pytest.mark.asyncio
    async def test_list_redemptions_filter_by_status(self):
        """Test filtering redemptions by status."""
        # Create one pending and one requiring approval
        await self.service.create_redemption(self.sample_redemption)
        self.sample_redemption.request_id = Decimal(2)
        self.sample_redemption.tx_hash = "0x" + "b" * 64
        self.sample_redemption.requires_approval = True
        await self.service.create_redemption(self.sample_redemption)

        # Filter by PENDING
        filters = RedemptionFilterParams(status=RedemptionStatus.PENDING)
        result = await self.service.list_redemptions(filters)
        assert len(result.items) == 1
        assert result.items[0].status == RedemptionStatus.PENDING

        # Filter by PENDING_APPROVAL
        filters = RedemptionFilterParams(status=RedemptionStatus.PENDING_APPROVAL)
        result = await self.service.list_redemptions(filters)
        assert len(result.items) == 1
        assert result.items[0].status == RedemptionStatus.PENDING_APPROVAL

    @pytest.mark.asyncio
    async def test_list_redemptions_filter_by_owner(self):
        """Test filtering redemptions by owner."""
        await self.service.create_redemption(self.sample_redemption)

        # Create another with different owner
        self.sample_redemption.request_id = Decimal(2)
        self.sample_redemption.tx_hash = "0x" + "b" * 64
        self.sample_redemption.owner = "0x" + "3" * 40
        await self.service.create_redemption(self.sample_redemption)

        filters = RedemptionFilterParams(owner="0x" + "1" * 40)
        result = await self.service.list_redemptions(filters)
        assert len(result.items) == 1
        assert result.items[0].owner == "0x" + "1" * 40

    @pytest.mark.asyncio
    async def test_list_redemptions_pagination(self):
        """Test pagination."""
        # Create 25 redemptions
        for i in range(25):
            data = RedemptionCreate(
                request_id=Decimal(i + 1),
                tx_hash=f"0x{'a' * 62}{i:02d}",
                block_number=12345 + i,
                log_index=0,
                owner="0x" + "1" * 40,
                receiver="0x" + "2" * 40,
                shares=Decimal("1000000000000000000"),
                gross_amount=Decimal("1000000000000000000"),
                locked_nav=Decimal("1000000000000000000"),
                estimated_fee=Decimal("10000000000000000"),
                request_time=datetime.now(timezone.utc),
                settlement_time=datetime.now(timezone.utc) + timedelta(hours=24),
                channel=RedemptionChannel.STANDARD,
                requires_approval=False,
            )
            await self.service.create_redemption(data)

        # Page 1
        result = await self.service.list_redemptions(
            RedemptionFilterParams(), page=1, page_size=10
        )
        assert len(result.items) == 10
        assert result.meta.page == 1
        assert result.meta.total_items == 25
        assert result.meta.total_pages == 3

        # Page 3
        result = await self.service.list_redemptions(
            RedemptionFilterParams(), page=3, page_size=10
        )
        assert len(result.items) == 5
        assert result.meta.page == 3

    @pytest.mark.asyncio
    async def test_list_redemptions_sorting(self):
        """Test sorting redemptions."""
        # Create redemptions with different amounts
        for i in range(3):
            data = RedemptionCreate(
                request_id=Decimal(i + 1),
                tx_hash=f"0x{'a' * 62}{i:02d}",
                block_number=12345 + i,
                log_index=0,
                owner="0x" + "1" * 40,
                receiver="0x" + "2" * 40,
                shares=Decimal("1000000000000000000") * (i + 1),
                gross_amount=Decimal("1000000000000000000") * (i + 1),
                locked_nav=Decimal("1000000000000000000"),
                estimated_fee=Decimal("10000000000000000"),
                request_time=datetime.now(timezone.utc),
                settlement_time=datetime.now(timezone.utc) + timedelta(hours=24),
                channel=RedemptionChannel.STANDARD,
                requires_approval=False,
            )
            await self.service.create_redemption(data)

        # Sort by amount ascending
        result = await self.service.list_redemptions(
            RedemptionFilterParams(),
            sort_by=RedemptionSortField.GROSS_AMOUNT,
            sort_order=SortOrder.ASC,
        )
        amounts = [Decimal(item.gross_amount) for item in result.items]
        assert amounts == sorted(amounts)

        # Sort by amount descending
        result = await self.service.list_redemptions(
            RedemptionFilterParams(),
            sort_by=RedemptionSortField.GROSS_AMOUNT,
            sort_order=SortOrder.DESC,
        )
        amounts = [Decimal(item.gross_amount) for item in result.items]
        assert amounts == sorted(amounts, reverse=True)

    @pytest.mark.asyncio
    async def test_get_redemption_detail(self):
        """Test getting redemption detail."""
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        detail = await self.service.get_redemption_detail(redemption_id)

        assert detail is not None
        assert detail.id == redemption_id
        assert detail.owner == self.sample_redemption.owner
        assert detail.shares == str(self.sample_redemption.shares)
        assert detail.timeline is not None

    @pytest.mark.asyncio
    async def test_get_redemption_detail_not_found(self):
        """Test getting non-existent redemption."""
        detail = await self.service.get_redemption_detail(9999)
        assert detail is None

    @pytest.mark.asyncio
    async def test_approve_redemption(self):
        """Test approving a redemption."""
        self.sample_redemption.requires_approval = True
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        request = ApprovalRequest(
            action=RedemptionAction.APPROVE,
            reason="Verified by admin",
        )
        result = await self.service.approve_redemption(
            redemption_id, request, "0x" + "9" * 40
        )

        assert result is True
        detail = await self.service.get_redemption_detail(redemption_id)
        assert detail.status == RedemptionStatus.APPROVED
        assert detail.approved_by == "0x" + "9" * 40
        assert detail.approved_at is not None

    @pytest.mark.asyncio
    async def test_reject_redemption(self):
        """Test rejecting a redemption."""
        self.sample_redemption.requires_approval = True
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        request = ApprovalRequest(
            action=RedemptionAction.REJECT,
            reason="Suspicious activity",
        )
        result = await self.service.approve_redemption(
            redemption_id, request, "0x" + "9" * 40
        )

        assert result is True
        detail = await self.service.get_redemption_detail(redemption_id)
        assert detail.status == RedemptionStatus.REJECTED
        assert detail.rejected_by == "0x" + "9" * 40
        assert detail.rejection_reason == "Suspicious activity"

    @pytest.mark.asyncio
    async def test_approve_not_found(self):
        """Test approving non-existent redemption."""
        request = ApprovalRequest(action=RedemptionAction.APPROVE)

        with pytest.raises(ValueError, match="not found"):
            await self.service.approve_redemption(9999, request, "0x" + "9" * 40)

    @pytest.mark.asyncio
    async def test_approve_wrong_status(self):
        """Test approving redemption not pending approval."""
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        request = ApprovalRequest(action=RedemptionAction.APPROVE)

        with pytest.raises(ValueError, match="not pending approval"):
            await self.service.approve_redemption(
                redemption_id, request, "0x" + "9" * 40
            )

    @pytest.mark.asyncio
    async def test_trigger_settlement(self):
        """Test triggering settlement."""
        # Set settlement time in the past
        self.sample_redemption.settlement_time = datetime.now(
            timezone.utc
        ) - timedelta(hours=1)
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        response = await self.service.trigger_settlement(redemption_id)

        assert response.success is True
        assert response.tx_hash is not None
        detail = await self.service.get_redemption_detail(redemption_id)
        assert detail.status == RedemptionStatus.SETTLED

    @pytest.mark.asyncio
    async def test_trigger_settlement_too_early(self):
        """Test triggering settlement before time."""
        self.sample_redemption.settlement_time = datetime.now(
            timezone.utc
        ) + timedelta(hours=24)
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        response = await self.service.trigger_settlement(redemption_id)

        assert response.success is False
        assert "Settlement time not reached" in response.message

    @pytest.mark.asyncio
    async def test_trigger_settlement_force(self):
        """Test forcing settlement before time."""
        self.sample_redemption.settlement_time = datetime.now(
            timezone.utc
        ) + timedelta(hours=24)
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        response = await self.service.trigger_settlement(redemption_id, force=True)

        assert response.success is True
        assert response.tx_hash is not None

    @pytest.mark.asyncio
    async def test_trigger_settlement_not_found(self):
        """Test triggering settlement for non-existent redemption."""
        response = await self.service.trigger_settlement(9999)

        assert response.success is False
        assert "not found" in response.message

    @pytest.mark.asyncio
    async def test_trigger_settlement_wrong_status(self):
        """Test triggering settlement for rejected redemption."""
        self.sample_redemption.requires_approval = True
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        # Reject it first
        request = ApprovalRequest(
            action=RedemptionAction.REJECT, reason="Test rejection"
        )
        await self.service.approve_redemption(
            redemption_id, request, "0x" + "9" * 40
        )

        response = await self.service.trigger_settlement(redemption_id)

        assert response.success is False
        assert "Cannot settle" in response.message

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting statistics."""
        # Create various redemptions
        await self.service.create_redemption(self.sample_redemption)

        self.sample_redemption.request_id = Decimal(2)
        self.sample_redemption.tx_hash = "0x" + "b" * 64
        self.sample_redemption.requires_approval = True
        await self.service.create_redemption(self.sample_redemption)

        stats = await self.service.get_stats()

        assert stats.total_requests == 2
        assert stats.pending_requests == 1
        assert stats.pending_approval == 1

    @pytest.mark.asyncio
    async def test_get_pending_approvals(self):
        """Test getting pending approvals list."""
        # Create one pending and one requiring approval
        await self.service.create_redemption(self.sample_redemption)

        self.sample_redemption.request_id = Decimal(2)
        self.sample_redemption.tx_hash = "0x" + "b" * 64
        self.sample_redemption.requires_approval = True
        await self.service.create_redemption(self.sample_redemption)

        result = await self.service.get_pending_approvals()

        assert len(result.items) == 1
        assert result.items[0].status == RedemptionStatus.PENDING_APPROVAL

    @pytest.mark.asyncio
    async def test_get_redemption_by_request_id(self):
        """Test getting redemption by on-chain request ID."""
        redemption_id = await self.service.create_redemption(self.sample_redemption)

        found_id = self.service.get_redemption_by_request_id(Decimal(1))

        assert found_id == redemption_id

    @pytest.mark.asyncio
    async def test_get_redemption_by_request_id_not_found(self):
        """Test getting non-existent request ID."""
        found_id = self.service.get_redemption_by_request_id(Decimal(9999))
        assert found_id is None


class TestRedemptionTimeline:
    """Tests for redemption timeline."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RedemptionService()

    @pytest.mark.asyncio
    async def test_timeline_created_event(self):
        """Test timeline includes created event."""
        data = RedemptionCreate(
            request_id=Decimal(1),
            tx_hash="0x" + "a" * 64,
            block_number=12345,
            log_index=0,
            owner="0x" + "1" * 40,
            receiver="0x" + "2" * 40,
            shares=Decimal("1000000000000000000"),
            gross_amount=Decimal("1000000000000000000"),
            locked_nav=Decimal("1000000000000000000"),
            estimated_fee=Decimal("10000000000000000"),
            request_time=datetime.now(timezone.utc),
            settlement_time=datetime.now(timezone.utc) + timedelta(hours=24),
            channel=RedemptionChannel.STANDARD,
            requires_approval=False,
        )
        redemption_id = await self.service.create_redemption(data)

        detail = await self.service.get_redemption_detail(redemption_id)
        events = detail.timeline.events

        assert len(events) >= 1
        assert events[0].event_type == "CREATED"
        assert events[0].actor == data.owner
        assert events[0].tx_hash == data.tx_hash

    @pytest.mark.asyncio
    async def test_timeline_approval_events(self):
        """Test timeline includes approval events."""
        data = RedemptionCreate(
            request_id=Decimal(1),
            tx_hash="0x" + "a" * 64,
            block_number=12345,
            log_index=0,
            owner="0x" + "1" * 40,
            receiver="0x" + "2" * 40,
            shares=Decimal("1000000000000000000"),
            gross_amount=Decimal("1000000000000000000"),
            locked_nav=Decimal("1000000000000000000"),
            estimated_fee=Decimal("10000000000000000"),
            request_time=datetime.now(timezone.utc),
            settlement_time=datetime.now(timezone.utc) + timedelta(hours=24),
            channel=RedemptionChannel.STANDARD,
            requires_approval=True,
        )
        redemption_id = await self.service.create_redemption(data)

        # Approve
        request = ApprovalRequest(action=RedemptionAction.APPROVE, reason="Approved")
        await self.service.approve_redemption(
            redemption_id, request, "0x" + "9" * 40
        )

        detail = await self.service.get_redemption_detail(redemption_id)
        events = detail.timeline.events
        event_types = [e.event_type for e in events]

        assert "CREATED" in event_types
        assert "PENDING_APPROVAL" in event_types
        assert "APPROVED" in event_types

    @pytest.mark.asyncio
    async def test_timeline_settlement_event(self):
        """Test timeline includes settlement event."""
        data = RedemptionCreate(
            request_id=Decimal(1),
            tx_hash="0x" + "a" * 64,
            block_number=12345,
            log_index=0,
            owner="0x" + "1" * 40,
            receiver="0x" + "2" * 40,
            shares=Decimal("1000000000000000000"),
            gross_amount=Decimal("1000000000000000000"),
            locked_nav=Decimal("1000000000000000000"),
            estimated_fee=Decimal("10000000000000000"),
            request_time=datetime.now(timezone.utc),
            settlement_time=datetime.now(timezone.utc) - timedelta(hours=1),
            channel=RedemptionChannel.STANDARD,
            requires_approval=False,
        )
        redemption_id = await self.service.create_redemption(data)

        # Settle
        await self.service.trigger_settlement(redemption_id)

        detail = await self.service.get_redemption_detail(redemption_id)
        events = detail.timeline.events
        event_types = [e.event_type for e in events]

        assert "CREATED" in event_types
        assert "SETTLED" in event_types

        # Check settlement details
        settled_event = next(e for e in events if e.event_type == "SETTLED")
        assert settled_event.tx_hash is not None
        assert settled_event.details is not None
        assert "net_amount" in settled_event.details
