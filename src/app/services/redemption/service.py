"""Redemption management service with database persistence.

Provides full lifecycle management for redemption requests:
- Create from blockchain events
- List with filters and pagination
- Detail view with timeline
- Approval/rejection operations
- Manual settlement trigger
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import AsyncSessionLocal
from app.models.redemption import RedemptionRequest
from app.repositories.redemption import RedemptionRepository
from app.repositories.audit_log import AuditLogRepository
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


class RedemptionService:
    """Service for managing redemption requests with database persistence.

    Provides:
    - Listing with filters and pagination
    - Detail view with timeline
    - Approval/rejection operations
    - Manual settlement trigger
    - Statistics and reporting

    Uses Repository pattern for database operations.
    """

    # Approval thresholds (USDC amounts)
    EMERGENCY_APPROVAL_THRESHOLD = Decimal("30000")  # >30K USDC requires approval
    STANDARD_APPROVAL_THRESHOLD = Decimal("100000")  # >100K USDC requires approval

    def __init__(self, session_factory: Callable[[], AsyncSession] | None = None):
        """Initialize redemption service.

        @param session_factory - Optional factory for creating database sessions
        """
        self._session_factory = session_factory or AsyncSessionLocal

    async def create_redemption(self, data: RedemptionCreate) -> int:
        """Create a new redemption request in database.

        @param data - Redemption creation data from blockchain event
        @returns Created redemption database ID
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            audit_repo = AuditLogRepository(session)

            # Check if already exists (deduplication)
            existing = await repo.get_by_tx_hash(data.tx_hash, data.log_index)
            if existing:
                logger.warning(
                    f"Redemption already exists: tx={data.tx_hash}, log={data.log_index}"
                )
                return existing.id

            # Determine initial status based on approval requirement
            initial_status = (
                RedemptionStatus.PENDING_APPROVAL.value
                if data.requires_approval
                else RedemptionStatus.PENDING.value
            )

            # Create redemption record
            redemption = await repo.create({
                "request_id": data.request_id,
                "tx_hash": data.tx_hash,
                "block_number": data.block_number,
                "log_index": data.log_index,
                "owner": data.owner.lower(),
                "receiver": data.receiver.lower(),
                "shares": data.shares,
                "gross_amount": data.gross_amount,
                "locked_nav": data.locked_nav,
                "estimated_fee": data.estimated_fee,
                "request_time": data.request_time,
                "settlement_time": data.settlement_time,
                "status": initial_status,
                "channel": data.channel.value,
                "requires_approval": data.requires_approval,
                "window_id": data.window_id,
            })

            # Create audit log entry
            await audit_repo.create({
                "action": "redemption.created",
                "resource_type": "redemption",
                "resource_id": str(redemption.id),
                "actor_address": data.owner.lower(),
                "new_value": {
                    "request_id": str(data.request_id),
                    "shares": str(data.shares),
                    "gross_amount": str(data.gross_amount),
                    "channel": data.channel.value,
                    "requires_approval": data.requires_approval,
                },
            })

            await session.commit()
            logger.info(f"Created redemption {redemption.id} with status {initial_status}")
            return redemption.id

    async def list_redemptions(
        self,
        filters: RedemptionFilterParams,
        page: int = 1,
        page_size: int = 20,
        sort_by: RedemptionSortField = RedemptionSortField.REQUEST_TIME,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> RedemptionListResponse:
        """List redemptions with filters and pagination.

        @param filters - Filter parameters
        @param page - Page number (1-based)
        @param page_size - Items per page
        @param sort_by - Sort field
        @param sort_order - Sort order
        @returns Paginated list response
        """
        async with self._session_factory() as session:
            # Build query with filters
            conditions = []

            if filters.status:
                conditions.append(RedemptionRequest.status == filters.status.value)

            if filters.channel:
                conditions.append(RedemptionRequest.channel == filters.channel.value)

            if filters.owner:
                conditions.append(
                    RedemptionRequest.owner == filters.owner.lower()
                )

            if filters.requires_approval is not None:
                conditions.append(
                    RedemptionRequest.requires_approval == filters.requires_approval
                )

            if filters.from_date:
                conditions.append(RedemptionRequest.request_time >= filters.from_date)

            if filters.to_date:
                conditions.append(RedemptionRequest.request_time <= filters.to_date)

            if filters.min_amount:
                conditions.append(RedemptionRequest.gross_amount >= filters.min_amount)

            if filters.max_amount:
                conditions.append(RedemptionRequest.gross_amount <= filters.max_amount)

            # Base query
            base_query = select(RedemptionRequest)
            if conditions:
                base_query = base_query.where(and_(*conditions))

            # Count total items
            count_query = select(func.count()).select_from(base_query.subquery())
            total_result = await session.execute(count_query)
            total_items = total_result.scalar() or 0

            # Sort
            sort_column_map = {
                RedemptionSortField.REQUEST_TIME: RedemptionRequest.request_time,
                RedemptionSortField.SETTLEMENT_TIME: RedemptionRequest.settlement_time,
                RedemptionSortField.GROSS_AMOUNT: RedemptionRequest.gross_amount,
                RedemptionSortField.STATUS: RedemptionRequest.status,
            }
            sort_column = sort_column_map.get(
                sort_by, RedemptionRequest.request_time
            )

            if sort_order == SortOrder.DESC:
                base_query = base_query.order_by(sort_column.desc())
            else:
                base_query = base_query.order_by(sort_column.asc())

            # Paginate
            offset = (page - 1) * page_size
            base_query = base_query.offset(offset).limit(page_size)

            result = await session.execute(base_query)
            records = result.scalars().all()

            # Calculate pagination
            total_pages = (
                (total_items + page_size - 1) // page_size if total_items > 0 else 0
            )

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
                    channel=RedemptionChannel(r.channel),
                    status=RedemptionStatus(r.status),
                    requires_approval=r.requires_approval,
                    request_time=r.request_time,
                    settlement_time=r.settlement_time,
                    created_at=r.created_at,
                )
                for r in records
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

        @param redemption_id - Redemption database ID
        @returns Redemption detail or None if not found
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            redemption = await repo.get_by_id(redemption_id)

            if not redemption:
                return None

            # Build timeline from audit logs
            audit_repo = AuditLogRepository(session)
            audit_logs = await audit_repo.get_by_resource(
                resource_type="redemption",
                resource_id=str(redemption_id)
            )

            timeline_events = []
            for log in audit_logs:
                event_type = log.action.replace("redemption.", "").upper()
                timeline_events.append(
                    RedemptionTimelineEvent(
                        event_type=event_type,
                        timestamp=log.created_at,
                        actor=log.actor_address,
                        tx_hash=log.new_value.get("tx_hash") if log.new_value else None,
                        details=log.new_value,
                    )
                )

            timeline = RedemptionTimeline(events=timeline_events)

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
                status=RedemptionStatus(redemption.status),
                channel=RedemptionChannel(redemption.channel),
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

        @param redemption_id - Redemption database ID
        @param request - Approval request data
        @param approver - Approver wallet address
        @returns True if successful
        @raises ValueError if redemption not found or invalid state
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            audit_repo = AuditLogRepository(session)

            redemption = await repo.get_by_id(redemption_id)
            if not redemption:
                raise ValueError(f"Redemption {redemption_id} not found")

            if redemption.status != RedemptionStatus.PENDING_APPROVAL.value:
                raise ValueError(
                    f"Redemption {redemption_id} is not pending approval "
                    f"(current status: {redemption.status})"
                )

            now = datetime.now(timezone.utc)

            if request.action == RedemptionAction.APPROVE:
                await repo.update_status(
                    redemption_id,
                    RedemptionStatus.APPROVED.value,
                    approved_by=approver.lower(),
                )

                await audit_repo.create({
                    "action": "redemption.approved",
                    "resource_type": "redemption",
                    "resource_id": str(redemption_id),
                    "actor_address": approver.lower(),
                    "new_value": {
                        "reason": request.reason,
                        "gross_amount": str(redemption.gross_amount),
                    },
                })

                logger.info(f"Redemption {redemption_id} approved by {approver}")

            else:  # REJECT
                await repo.update_status(
                    redemption_id,
                    RedemptionStatus.REJECTED.value,
                    rejected_by=approver.lower(),
                    rejection_reason=request.reason,
                )

                await audit_repo.create({
                    "action": "redemption.rejected",
                    "resource_type": "redemption",
                    "resource_id": str(redemption_id),
                    "actor_address": approver.lower(),
                    "new_value": {
                        "reason": request.reason,
                        "gross_amount": str(redemption.gross_amount),
                    },
                })

                logger.info(
                    f"Redemption {redemption_id} rejected by {approver}: {request.reason}"
                )

            await session.commit()
            return True

    async def trigger_settlement(
        self,
        redemption_id: int,
        force: bool = False,
        operator: str | None = None,
    ) -> SettlementResponse:
        """Trigger manual settlement for a redemption.

        In production, this would call the smart contract.
        Currently creates an audit trail and updates status.

        @param redemption_id - Redemption database ID
        @param force - Force settlement even if conditions not met
        @param operator - Operator wallet address triggering settlement
        @returns Settlement response with status and tx hash
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            audit_repo = AuditLogRepository(session)

            redemption = await repo.get_by_id(redemption_id)
            if not redemption:
                return SettlementResponse(
                    success=False,
                    tx_hash=None,
                    message=f"Redemption {redemption_id} not found",
                )

            # Check if settlement is allowed
            allowed_statuses = [
                RedemptionStatus.PENDING.value,
                RedemptionStatus.APPROVED.value,
            ]
            if redemption.status not in allowed_statuses:
                return SettlementResponse(
                    success=False,
                    tx_hash=None,
                    message=f"Cannot settle redemption with status {redemption.status}",
                )

            # Check if settlement time has passed
            now = datetime.now(timezone.utc)
            if not force and now < redemption.settlement_time:
                return SettlementResponse(
                    success=False,
                    tx_hash=None,
                    message=f"Settlement time not reached. Expected: {redemption.settlement_time}",
                )

            # TODO: In production, call smart contract here
            # For now, simulate settlement transaction
            settlement_tx = f"0x{'a' * 62}{redemption_id:02d}"

            # Calculate net amount
            actual_fee = redemption.estimated_fee
            net_amount = redemption.gross_amount - actual_fee

            # Update redemption record
            await repo.settle(
                redemption_id,
                actual_fee=actual_fee,
                net_amount=net_amount,
                settlement_tx_hash=settlement_tx,
            )

            # Audit log
            await audit_repo.create({
                "action": "redemption.settled",
                "resource_type": "redemption",
                "resource_id": str(redemption_id),
                "actor_address": operator.lower() if operator else None,
                "new_value": {
                    "tx_hash": settlement_tx,
                    "actual_fee": str(actual_fee),
                    "net_amount": str(net_amount),
                    "forced": force,
                },
            })

            await session.commit()
            logger.info(f"Redemption {redemption_id} settled: {settlement_tx}")

            return SettlementResponse(
                success=True,
                tx_hash=settlement_tx,
                message="Settlement triggered successfully",
            )

    async def get_stats(self) -> RedemptionStats:
        """Get redemption statistics.

        @returns Aggregated redemption statistics
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            stats_data = await repo.get_statistics()

            stats = RedemptionStats()
            status_counts = stats_data.get("by_status", {})

            stats.total_requests = stats_data.get("total_count", 0)
            stats.total_volume = stats_data.get("total_amount", Decimal(0))

            stats.pending_requests = status_counts.get("PENDING", 0)
            stats.pending_approval = status_counts.get("PENDING_APPROVAL", 0)
            stats.approved_requests = status_counts.get("APPROVED", 0)
            stats.settled_requests = status_counts.get("SETTLED", 0)
            stats.rejected_requests = status_counts.get("REJECTED", 0)
            stats.cancelled_requests = status_counts.get("CANCELLED", 0)

            return stats

    async def get_pending_approvals(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> RedemptionListResponse:
        """Get redemptions pending approval.

        @param page - Page number
        @param page_size - Items per page
        @returns Paginated list of pending approvals
        """
        filters = RedemptionFilterParams(status=RedemptionStatus.PENDING_APPROVAL)
        return await self.list_redemptions(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=RedemptionSortField.REQUEST_TIME,
            sort_order=SortOrder.ASC,
        )

    async def get_redemption_by_request_id(
        self, request_id: Decimal
    ) -> RedemptionDetail | None:
        """Get redemption by on-chain request ID.

        @param request_id - On-chain request ID
        @returns Redemption detail or None if not found
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            redemption = await repo.get_by_request_id(request_id)

            if not redemption:
                return None

            return await self.get_redemption_detail(redemption.id)

    async def link_approval_ticket(
        self,
        redemption_id: int,
        ticket_id: str,
    ) -> bool:
        """Link an approval ticket to a redemption.

        @param redemption_id - Redemption database ID
        @param ticket_id - Approval ticket ID
        @returns True if successful
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)

            updated = await repo.update(
                redemption_id,
                {"approval_ticket_id": ticket_id}
            )

            if updated:
                await session.commit()
                logger.info(
                    f"Linked approval ticket {ticket_id} to redemption {redemption_id}"
                )
                return True
            return False

    async def get_ready_for_settlement(self) -> list[RedemptionDetail]:
        """Get all redemptions ready for settlement.

        @returns List of redemptions ready to be settled
        """
        async with self._session_factory() as session:
            repo = RedemptionRepository(session)
            records = await repo.get_ready_for_settlement()

            results = []
            for r in records:
                detail = await self.get_redemption_detail(r.id)
                if detail:
                    results.append(detail)

            return results

    @staticmethod
    def requires_approval(
        gross_amount: Decimal,
        channel: RedemptionChannel,
    ) -> bool:
        """Determine if a redemption amount requires approval.

        @param gross_amount - Gross redemption amount in USDC
        @param channel - Redemption channel type
        @returns True if approval is required
        """
        if channel == RedemptionChannel.EMERGENCY:
            return gross_amount > RedemptionService.EMERGENCY_APPROVAL_THRESHOLD
        else:
            return gross_amount > RedemptionService.STANDARD_APPROVAL_THRESHOLD


# Service singleton with dependency injection support
_redemption_service: RedemptionService | None = None


def get_redemption_service() -> RedemptionService:
    """Get or create redemption service singleton.

    @returns RedemptionService instance
    """
    global _redemption_service
    if _redemption_service is None:
        _redemption_service = RedemptionService()
    return _redemption_service


def reset_redemption_service() -> None:
    """Reset redemption service singleton (for testing)."""
    global _redemption_service
    _redemption_service = None
