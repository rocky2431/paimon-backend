"""Redemption management service."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.services.redemption.schemas import (
    ApprovalRequest,
    PaginationMeta,
    RedemptionAction,
    RedemptionChannel,
    RedemptionCreate,
    RedemptionDetail,
    RedemptionFilterParams,
    RedemptionListItem,
    RedemptionListResponse,
    RedemptionSortField,
    RedemptionStatus,
    RedemptionTimeline,
    RedemptionTimelineEvent,
    SettlementResponse,
    SortOrder,
)

logger = logging.getLogger(__name__)


@dataclass
class RedemptionStats:
    """Statistics for redemption service."""

    total_requests: int = 0
    pending_requests: int = 0
    pending_approval: int = 0
    approved_requests: int = 0
    settled_requests: int = 0
    rejected_requests: int = 0
    cancelled_requests: int = 0
    total_volume: Decimal = field(default_factory=lambda: Decimal(0))


@dataclass
class InMemoryRedemption:
    """In-memory redemption record for testing."""

    id: int
    request_id: Decimal
    tx_hash: str
    block_number: int
    log_index: int
    owner: str
    receiver: str
    shares: Decimal
    gross_amount: Decimal
    locked_nav: Decimal
    estimated_fee: Decimal
    request_time: datetime
    settlement_time: datetime
    status: RedemptionStatus
    channel: RedemptionChannel
    requires_approval: bool
    window_id: Decimal | None = None
    actual_fee: Decimal | None = None
    net_amount: Decimal | None = None
    settlement_tx_hash: str | None = None
    settled_at: datetime | None = None
    approval_ticket_id: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    timeline_events: list[dict[str, Any]] = field(default_factory=list)


class RedemptionService:
    """Service for managing redemption requests.

    Provides:
    - Listing with filters and pagination
    - Detail view with timeline
    - Approval/rejection operations
    - Manual settlement trigger
    """

    def __init__(self, repository: Any = None):
        """Initialize redemption service.

        Args:
            repository: Optional database repository
        """
        self.repository = repository
        self._redemptions: dict[int, InMemoryRedemption] = {}
        self._next_id = 1

    async def create_redemption(self, data: RedemptionCreate) -> int:
        """Create a new redemption request.

        Args:
            data: Redemption creation data

        Returns:
            Created redemption ID
        """
        redemption_id = self._next_id
        self._next_id += 1

        initial_status = (
            RedemptionStatus.PENDING_APPROVAL
            if data.requires_approval
            else RedemptionStatus.PENDING
        )

        redemption = InMemoryRedemption(
            id=redemption_id,
            request_id=data.request_id,
            tx_hash=data.tx_hash,
            block_number=data.block_number,
            log_index=data.log_index,
            owner=data.owner,
            receiver=data.receiver,
            shares=data.shares,
            gross_amount=data.gross_amount,
            locked_nav=data.locked_nav,
            estimated_fee=data.estimated_fee,
            request_time=data.request_time,
            settlement_time=data.settlement_time,
            status=initial_status,
            channel=data.channel,
            requires_approval=data.requires_approval,
            window_id=data.window_id,
        )

        # Add initial timeline event
        redemption.timeline_events.append(
            {
                "event_type": "CREATED",
                "timestamp": data.request_time,
                "actor": data.owner,
                "tx_hash": data.tx_hash,
                "details": {
                    "shares": str(data.shares),
                    "gross_amount": str(data.gross_amount),
                    "channel": data.channel.value,
                },
            }
        )

        if data.requires_approval:
            redemption.timeline_events.append(
                {
                    "event_type": "PENDING_APPROVAL",
                    "timestamp": datetime.now(timezone.utc),
                    "actor": None,
                    "tx_hash": None,
                    "details": {"reason": "Amount exceeds auto-approval threshold"},
                }
            )

        self._redemptions[redemption_id] = redemption
        logger.info(f"Created redemption {redemption_id} with status {initial_status}")

        return redemption_id

    async def list_redemptions(
        self,
        filters: RedemptionFilterParams,
        page: int = 1,
        page_size: int = 20,
        sort_by: RedemptionSortField = RedemptionSortField.REQUEST_TIME,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> RedemptionListResponse:
        """List redemptions with filters and pagination.

        Args:
            filters: Filter parameters
            page: Page number (1-based)
            page_size: Items per page
            sort_by: Sort field
            sort_order: Sort order

        Returns:
            Paginated list response
        """
        # Apply filters
        filtered = list(self._redemptions.values())

        if filters.status:
            filtered = [r for r in filtered if r.status == filters.status]

        if filters.channel:
            filtered = [r for r in filtered if r.channel == filters.channel]

        if filters.owner:
            filtered = [
                r for r in filtered if r.owner.lower() == filters.owner.lower()
            ]

        if filters.requires_approval is not None:
            filtered = [
                r for r in filtered if r.requires_approval == filters.requires_approval
            ]

        if filters.from_date:
            filtered = [r for r in filtered if r.request_time >= filters.from_date]

        if filters.to_date:
            filtered = [r for r in filtered if r.request_time <= filters.to_date]

        if filters.min_amount:
            filtered = [r for r in filtered if r.gross_amount >= filters.min_amount]

        if filters.max_amount:
            filtered = [r for r in filtered if r.gross_amount <= filters.max_amount]

        # Sort
        reverse = sort_order == SortOrder.DESC
        sort_key = {
            RedemptionSortField.REQUEST_TIME: lambda r: r.request_time,
            RedemptionSortField.SETTLEMENT_TIME: lambda r: r.settlement_time,
            RedemptionSortField.GROSS_AMOUNT: lambda r: r.gross_amount,
            RedemptionSortField.STATUS: lambda r: r.status.value,
        }.get(sort_by, lambda r: r.request_time)

        filtered.sort(key=sort_key, reverse=reverse)

        # Paginate
        total_items = len(filtered)
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered[start_idx:end_idx]

        # Convert to response models
        items = [
            RedemptionListItem(
                id=r.id,
                request_id=str(r.request_id),
                tx_hash=r.tx_hash,
                owner=r.owner,
                receiver=r.receiver,
                shares=str(r.shares),
                gross_amount=str(r.gross_amount),
                estimated_fee=str(r.estimated_fee),
                channel=r.channel,
                status=r.status,
                requires_approval=r.requires_approval,
                request_time=r.request_time,
                settlement_time=r.settlement_time,
                created_at=r.created_at,
            )
            for r in page_items
        ]

        return RedemptionListResponse(
            items=items,
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_redemption_detail(self, redemption_id: int) -> RedemptionDetail | None:
        """Get detailed redemption information.

        Args:
            redemption_id: Redemption ID

        Returns:
            Redemption detail or None if not found
        """
        redemption = self._redemptions.get(redemption_id)
        if not redemption:
            return None

        # Build timeline
        timeline = RedemptionTimeline(
            events=[
                RedemptionTimelineEvent(
                    event_type=event["event_type"],
                    timestamp=event["timestamp"],
                    actor=event.get("actor"),
                    tx_hash=event.get("tx_hash"),
                    details=event.get("details"),
                )
                for event in redemption.timeline_events
            ]
        )

        return RedemptionDetail(
            id=redemption.id,
            request_id=str(redemption.request_id),
            tx_hash=redemption.tx_hash,
            block_number=redemption.block_number,
            log_index=redemption.log_index,
            owner=redemption.owner,
            receiver=redemption.receiver,
            shares=str(redemption.shares),
            gross_amount=str(redemption.gross_amount),
            locked_nav=str(redemption.locked_nav),
            estimated_fee=str(redemption.estimated_fee),
            request_time=redemption.request_time,
            settlement_time=redemption.settlement_time,
            status=redemption.status,
            channel=redemption.channel,
            requires_approval=redemption.requires_approval,
            window_id=str(redemption.window_id) if redemption.window_id else None,
            actual_fee=str(redemption.actual_fee) if redemption.actual_fee else None,
            net_amount=str(redemption.net_amount) if redemption.net_amount else None,
            settlement_tx_hash=redemption.settlement_tx_hash,
            settled_at=redemption.settled_at,
            approval_ticket_id=redemption.approval_ticket_id,
            approved_by=redemption.approved_by,
            approved_at=redemption.approved_at,
            rejected_by=redemption.rejected_by,
            rejected_at=redemption.rejected_at,
            rejection_reason=redemption.rejection_reason,
            created_at=redemption.created_at,
            updated_at=redemption.updated_at,
            timeline=timeline,
        )

    async def approve_redemption(
        self,
        redemption_id: int,
        request: ApprovalRequest,
        approver: str,
    ) -> bool:
        """Approve or reject a redemption request.

        Args:
            redemption_id: Redemption ID
            request: Approval request data
            approver: Approver wallet address

        Returns:
            True if successful

        Raises:
            ValueError: If redemption not found or invalid state
        """
        redemption = self._redemptions.get(redemption_id)
        if not redemption:
            raise ValueError(f"Redemption {redemption_id} not found")

        if redemption.status != RedemptionStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Redemption {redemption_id} is not pending approval "
                f"(current status: {redemption.status})"
            )

        now = datetime.now(timezone.utc)

        if request.action == RedemptionAction.APPROVE:
            redemption.status = RedemptionStatus.APPROVED
            redemption.approved_by = approver
            redemption.approved_at = now
            redemption.timeline_events.append(
                {
                    "event_type": "APPROVED",
                    "timestamp": now,
                    "actor": approver,
                    "tx_hash": None,
                    "details": {"reason": request.reason} if request.reason else None,
                }
            )
            logger.info(f"Redemption {redemption_id} approved by {approver}")

        else:  # REJECT
            redemption.status = RedemptionStatus.REJECTED
            redemption.rejected_by = approver
            redemption.rejected_at = now
            redemption.rejection_reason = request.reason
            redemption.timeline_events.append(
                {
                    "event_type": "REJECTED",
                    "timestamp": now,
                    "actor": approver,
                    "tx_hash": None,
                    "details": {"reason": request.reason} if request.reason else None,
                }
            )
            logger.info(
                f"Redemption {redemption_id} rejected by {approver}: {request.reason}"
            )

        redemption.updated_at = now
        return True

    async def trigger_settlement(
        self,
        redemption_id: int,
        force: bool = False,
    ) -> SettlementResponse:
        """Trigger manual settlement for a redemption.

        Args:
            redemption_id: Redemption ID
            force: Force settlement even if conditions not met

        Returns:
            Settlement response
        """
        redemption = self._redemptions.get(redemption_id)
        if not redemption:
            return SettlementResponse(
                success=False,
                tx_hash=None,
                message=f"Redemption {redemption_id} not found",
            )

        # Check if settlement is allowed
        allowed_statuses = [RedemptionStatus.PENDING, RedemptionStatus.APPROVED]
        if redemption.status not in allowed_statuses:
            return SettlementResponse(
                success=False,
                tx_hash=None,
                message=f"Cannot settle redemption with status {redemption.status.value}",
            )

        # Check if settlement time has passed
        now = datetime.now(timezone.utc)
        if not force and now < redemption.settlement_time:
            return SettlementResponse(
                success=False,
                tx_hash=None,
                message=f"Settlement time not reached. Expected: {redemption.settlement_time}",
            )

        # In a real implementation, this would call the smart contract
        # For now, simulate settlement
        settlement_tx = f"0x{'a' * 62}01"
        redemption.status = RedemptionStatus.SETTLED
        redemption.settled_at = now
        redemption.settlement_tx_hash = settlement_tx
        redemption.actual_fee = redemption.estimated_fee
        redemption.net_amount = redemption.gross_amount - redemption.estimated_fee
        redemption.updated_at = now

        redemption.timeline_events.append(
            {
                "event_type": "SETTLED",
                "timestamp": now,
                "actor": None,
                "tx_hash": settlement_tx,
                "details": {
                    "actual_fee": str(redemption.actual_fee),
                    "net_amount": str(redemption.net_amount),
                    "forced": force,
                },
            }
        )

        logger.info(f"Redemption {redemption_id} settled: {settlement_tx}")

        return SettlementResponse(
            success=True,
            tx_hash=settlement_tx,
            message="Settlement triggered successfully",
        )

    async def get_stats(self) -> RedemptionStats:
        """Get redemption statistics.

        Returns:
            Redemption statistics
        """
        stats = RedemptionStats()

        for redemption in self._redemptions.values():
            stats.total_requests += 1
            stats.total_volume += redemption.gross_amount

            if redemption.status == RedemptionStatus.PENDING:
                stats.pending_requests += 1
            elif redemption.status == RedemptionStatus.PENDING_APPROVAL:
                stats.pending_approval += 1
            elif redemption.status == RedemptionStatus.APPROVED:
                stats.approved_requests += 1
            elif redemption.status == RedemptionStatus.SETTLED:
                stats.settled_requests += 1
            elif redemption.status == RedemptionStatus.REJECTED:
                stats.rejected_requests += 1
            elif redemption.status == RedemptionStatus.CANCELLED:
                stats.cancelled_requests += 1

        return stats

    async def get_pending_approvals(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> RedemptionListResponse:
        """Get redemptions pending approval.

        Args:
            page: Page number
            page_size: Items per page

        Returns:
            Paginated list of pending approvals
        """
        filters = RedemptionFilterParams(status=RedemptionStatus.PENDING_APPROVAL)
        return await self.list_redemptions(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=RedemptionSortField.REQUEST_TIME,
            sort_order=SortOrder.ASC,
        )

    def get_redemption_by_request_id(self, request_id: Decimal) -> int | None:
        """Get redemption ID by on-chain request ID.

        Args:
            request_id: On-chain request ID

        Returns:
            Database ID or None if not found
        """
        for redemption in self._redemptions.values():
            if redemption.request_id == request_id:
                return redemption.id
        return None


# Service singleton
_redemption_service: RedemptionService | None = None


def get_redemption_service() -> RedemptionService:
    """Get or create redemption service singleton."""
    global _redemption_service
    if _redemption_service is None:
        _redemption_service = RedemptionService()
    return _redemption_service
