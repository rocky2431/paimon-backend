"""Redemption API schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RedemptionStatus(str, Enum):
    """Redemption request status."""

    PENDING = "PENDING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class RedemptionChannel(str, Enum):
    """Redemption channel type."""

    STANDARD = "STANDARD"
    EMERGENCY = "EMERGENCY"
    SCHEDULED = "SCHEDULED"


class RedemptionAction(str, Enum):
    """Approval action type."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


class RedemptionFilterParams(BaseModel):
    """Filter parameters for redemption list."""

    status: RedemptionStatus | None = Field(None, description="Filter by status")
    channel: RedemptionChannel | None = Field(None, description="Filter by channel")
    owner: str | None = Field(
        None,
        description="Filter by owner wallet address",
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )
    requires_approval: bool | None = Field(
        None, description="Filter by approval requirement"
    )
    from_date: datetime | None = Field(None, description="Filter from date")
    to_date: datetime | None = Field(None, description="Filter to date")
    min_amount: Decimal | None = Field(
        None, ge=0, description="Filter by minimum gross amount"
    )
    max_amount: Decimal | None = Field(
        None, ge=0, description="Filter by maximum gross amount"
    )


class SortOrder(str, Enum):
    """Sort order."""

    ASC = "asc"
    DESC = "desc"


class RedemptionSortField(str, Enum):
    """Sortable fields for redemption list."""

    REQUEST_TIME = "request_time"
    SETTLEMENT_TIME = "settlement_time"
    GROSS_AMOUNT = "gross_amount"
    STATUS = "status"


class RedemptionListItem(BaseModel):
    """Redemption item in list response."""

    id: int = Field(..., description="Database ID")
    request_id: str = Field(..., description="On-chain request ID")
    tx_hash: str = Field(..., description="Transaction hash")
    owner: str = Field(..., description="Owner wallet address")
    receiver: str = Field(..., description="Receiver wallet address")
    shares: str = Field(..., description="Shares to redeem (wei)")
    gross_amount: str = Field(..., description="Gross amount (wei)")
    estimated_fee: str = Field(..., description="Estimated fee (wei)")
    channel: RedemptionChannel = Field(..., description="Redemption channel")
    status: RedemptionStatus = Field(..., description="Current status")
    requires_approval: bool = Field(..., description="Requires approval")
    request_time: datetime = Field(..., description="Request time")
    settlement_time: datetime = Field(..., description="Expected settlement time")
    created_at: datetime = Field(..., description="Record created at")

    class Config:
        from_attributes = True


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, le=100, description="Page size")
    total_items: int = Field(..., ge=0, description="Total items")
    total_pages: int = Field(..., ge=0, description="Total pages")


class RedemptionListResponse(BaseModel):
    """Paginated redemption list response."""

    items: list[RedemptionListItem] = Field(..., description="Redemption items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")


class RedemptionTimelineEvent(BaseModel):
    """Single event in redemption timeline."""

    event_type: str = Field(..., description="Event type")
    timestamp: datetime = Field(..., description="Event timestamp")
    actor: str | None = Field(None, description="Actor wallet address")
    tx_hash: str | None = Field(None, description="Related transaction hash")
    details: dict[str, Any] | None = Field(None, description="Additional details")


class RedemptionTimeline(BaseModel):
    """Redemption timeline with all events."""

    events: list[RedemptionTimelineEvent] = Field(
        default_factory=list, description="Timeline events"
    )


class RedemptionDetail(BaseModel):
    """Detailed redemption information."""

    id: int = Field(..., description="Database ID")
    request_id: str = Field(..., description="On-chain request ID")
    tx_hash: str = Field(..., description="Transaction hash")
    block_number: int = Field(..., description="Block number")
    log_index: int = Field(..., description="Log index")

    # Request info
    owner: str = Field(..., description="Owner wallet address")
    receiver: str = Field(..., description="Receiver wallet address")
    shares: str = Field(..., description="Shares to redeem (wei)")
    gross_amount: str = Field(..., description="Gross amount (wei)")
    locked_nav: str = Field(..., description="Locked NAV (wei)")
    estimated_fee: str = Field(..., description="Estimated fee (wei)")

    # Time info
    request_time: datetime = Field(..., description="Request time")
    settlement_time: datetime = Field(..., description="Expected settlement time")

    # Status info
    status: RedemptionStatus = Field(..., description="Current status")
    channel: RedemptionChannel = Field(..., description="Redemption channel")
    requires_approval: bool = Field(..., description="Requires approval")
    window_id: str | None = Field(None, description="Settlement window ID")

    # Settlement info
    actual_fee: str | None = Field(None, description="Actual fee (wei)")
    net_amount: str | None = Field(None, description="Net amount (wei)")
    settlement_tx_hash: str | None = Field(None, description="Settlement tx hash")
    settled_at: datetime | None = Field(None, description="Actual settlement time")

    # Approval info
    approval_ticket_id: str | None = Field(None, description="Approval ticket ID")
    approved_by: str | None = Field(None, description="Approved by wallet")
    approved_at: datetime | None = Field(None, description="Approval time")
    rejected_by: str | None = Field(None, description="Rejected by wallet")
    rejected_at: datetime | None = Field(None, description="Rejection time")
    rejection_reason: str | None = Field(None, description="Rejection reason")

    # Timestamps
    created_at: datetime = Field(..., description="Record created at")
    updated_at: datetime = Field(..., description="Record updated at")

    # Timeline
    timeline: RedemptionTimeline = Field(..., description="Event timeline")

    class Config:
        from_attributes = True


class RedemptionCreate(BaseModel):
    """Create redemption request (from chain event)."""

    request_id: Decimal = Field(..., description="On-chain request ID")
    tx_hash: str = Field(..., description="Transaction hash")
    block_number: int = Field(..., description="Block number")
    log_index: int = Field(..., description="Log index")
    owner: str = Field(..., description="Owner wallet address")
    receiver: str = Field(..., description="Receiver wallet address")
    shares: Decimal = Field(..., description="Shares to redeem")
    gross_amount: Decimal = Field(..., description="Gross amount")
    locked_nav: Decimal = Field(..., description="Locked NAV")
    estimated_fee: Decimal = Field(..., description="Estimated fee")
    request_time: datetime = Field(..., description="Request time")
    settlement_time: datetime = Field(..., description="Expected settlement time")
    channel: RedemptionChannel = Field(..., description="Redemption channel")
    requires_approval: bool = Field(
        default=False, description="Requires approval"
    )
    window_id: Decimal | None = Field(None, description="Settlement window ID")


class ApprovalRequest(BaseModel):
    """Request to approve or reject a redemption."""

    action: RedemptionAction = Field(..., description="Approve or reject")
    reason: str | None = Field(
        None, max_length=1000, description="Reason for the action"
    )
    signature: str | None = Field(
        None, description="Wallet signature for verification"
    )


class SettlementRequest(BaseModel):
    """Request to trigger manual settlement."""

    force: bool = Field(
        default=False, description="Force settlement even if conditions not met"
    )


class SettlementResponse(BaseModel):
    """Settlement trigger response."""

    success: bool = Field(..., description="Settlement triggered successfully")
    tx_hash: str | None = Field(None, description="Settlement transaction hash")
    message: str = Field(..., description="Result message")
