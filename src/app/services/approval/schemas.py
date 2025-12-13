"""Approval workflow schemas."""

from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ApprovalTicketType(str, Enum):
    """Types of approval tickets."""

    REDEMPTION = "REDEMPTION"
    REBALANCING = "REBALANCING"
    EMERGENCY = "EMERGENCY"
    ASSET_ADD = "ASSET_ADD"
    ASSET_REMOVE = "ASSET_REMOVE"
    CONFIG_CHANGE = "CONFIG_CHANGE"


class ApprovalTicketStatus(str, Enum):
    """Approval ticket status."""

    PENDING = "PENDING"
    PARTIALLY_APPROVED = "PARTIALLY_APPROVED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ApprovalResult(str, Enum):
    """Final approval result."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ApprovalAction(str, Enum):
    """Individual approval action."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ApprovalLevel(str, Enum):
    """Approval levels for multi-level approval."""

    OPERATOR = "OPERATOR"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    EMERGENCY = "EMERGENCY"


class SLAConfig(BaseModel):
    """SLA configuration for approval tickets."""

    warning_hours: float = Field(
        default=4.0, ge=0, description="Hours before deadline to trigger warning"
    )
    deadline_hours: float = Field(
        default=24.0, ge=0, description="Hours until ticket expires"
    )

    def get_warning_time(self, created_at: datetime) -> datetime:
        """Get SLA warning time."""
        return created_at + timedelta(hours=self.warning_hours)

    def get_deadline_time(self, created_at: datetime) -> datetime:
        """Get SLA deadline time."""
        return created_at + timedelta(hours=self.deadline_hours)


class EscalationConfig(BaseModel):
    """Escalation configuration."""

    enabled: bool = Field(default=True, description="Enable auto-escalation")
    escalate_after_hours: float = Field(
        default=2.0, ge=0, description="Hours after warning to escalate"
    )
    escalate_to_level: ApprovalLevel = Field(
        default=ApprovalLevel.ADMIN, description="Level to escalate to"
    )
    notify_addresses: list[str] = Field(
        default_factory=list, description="Addresses to notify on escalation"
    )


class ApprovalRuleConfig(BaseModel):
    """Configuration for approval rules based on amount/type."""

    ticket_type: ApprovalTicketType = Field(..., description="Ticket type this rule applies to")
    min_amount: Decimal | None = Field(
        None, ge=0, description="Minimum amount for this rule"
    )
    max_amount: Decimal | None = Field(
        None, ge=0, description="Maximum amount for this rule"
    )
    required_approvals: int = Field(
        default=1, ge=1, le=5, description="Number of approvals required"
    )
    required_level: ApprovalLevel = Field(
        default=ApprovalLevel.OPERATOR, description="Minimum approval level required"
    )
    allowed_approvers: list[str] = Field(
        default_factory=list, description="Specific approvers allowed (empty = any with level)"
    )
    sla: SLAConfig = Field(default_factory=SLAConfig, description="SLA configuration")
    escalation: EscalationConfig = Field(
        default_factory=EscalationConfig, description="Escalation configuration"
    )


class ApprovalRecord(BaseModel):
    """Record of an approval action."""

    id: str = Field(..., description="Record ID")
    approver: str = Field(..., description="Approver address")
    action: ApprovalAction = Field(..., description="Action taken")
    reason: str | None = Field(None, description="Reason for action")
    signature: str | None = Field(None, description="Wallet signature")
    timestamp: datetime = Field(..., description="Action timestamp")
    level: ApprovalLevel = Field(..., description="Approver's level")


class ApprovalTicketCreate(BaseModel):
    """Create approval ticket request."""

    ticket_type: ApprovalTicketType = Field(..., description="Type of approval")
    reference_type: str = Field(..., description="Type of referenced entity")
    reference_id: str = Field(..., description="ID of referenced entity")
    requester: str = Field(..., description="Requester address")
    amount: Decimal | None = Field(None, ge=0, description="Amount if applicable")
    description: str | None = Field(None, max_length=1000, description="Description")
    request_data: dict[str, Any] | None = Field(None, description="Additional data")
    risk_assessment: dict[str, Any] | None = Field(None, description="Risk assessment")


class ApprovalTicketListItem(BaseModel):
    """Approval ticket in list response."""

    id: str = Field(..., description="Ticket ID")
    ticket_type: ApprovalTicketType = Field(..., description="Ticket type")
    reference_type: str = Field(..., description="Reference type")
    reference_id: str = Field(..., description="Reference ID")
    requester: str = Field(..., description="Requester address")
    amount: str | None = Field(None, description="Amount")
    status: ApprovalTicketStatus = Field(..., description="Current status")
    required_approvals: int = Field(..., description="Required approvals")
    current_approvals: int = Field(..., description="Current approvals")
    current_rejections: int = Field(..., description="Current rejections")
    sla_warning: datetime = Field(..., description="SLA warning time")
    sla_deadline: datetime = Field(..., description="SLA deadline")
    escalated: bool = Field(..., description="Whether ticket is escalated")
    created_at: datetime = Field(..., description="Created timestamp")


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, le=100, description="Page size")
    total_items: int = Field(..., ge=0, description="Total items")
    total_pages: int = Field(..., ge=0, description="Total pages")


class ApprovalTicketListResponse(BaseModel):
    """Paginated approval ticket list response."""

    items: list[ApprovalTicketListItem] = Field(..., description="Ticket items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")


class ApprovalTicketDetail(BaseModel):
    """Detailed approval ticket information."""

    id: str = Field(..., description="Ticket ID")
    ticket_type: ApprovalTicketType = Field(..., description="Ticket type")
    reference_type: str = Field(..., description="Reference type")
    reference_id: str = Field(..., description="Reference ID")
    requester: str = Field(..., description="Requester address")
    amount: str | None = Field(None, description="Amount")
    description: str | None = Field(None, description="Description")
    request_data: dict[str, Any] | None = Field(None, description="Request data")
    risk_assessment: dict[str, Any] | None = Field(None, description="Risk assessment")

    # Status
    status: ApprovalTicketStatus = Field(..., description="Current status")
    required_approvals: int = Field(..., description="Required approvals")
    current_approvals: int = Field(..., description="Current approvals")
    current_rejections: int = Field(..., description="Current rejections")

    # SLA
    sla_warning: datetime = Field(..., description="SLA warning time")
    sla_deadline: datetime = Field(..., description="SLA deadline")
    escalated_at: datetime | None = Field(None, description="Escalation time")
    escalated_to: list[str] | None = Field(None, description="Escalated to addresses")

    # Result
    result: ApprovalResult | None = Field(None, description="Final result")
    result_reason: str | None = Field(None, description="Result reason")
    resolved_at: datetime | None = Field(None, description="Resolution time")
    resolved_by: str | None = Field(None, description="Resolved by address")

    # Records
    approval_records: list[ApprovalRecord] = Field(
        default_factory=list, description="Approval records"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Updated timestamp")


class ApprovalActionRequest(BaseModel):
    """Request to approve or reject a ticket."""

    action: ApprovalAction = Field(..., description="Action to take")
    reason: str | None = Field(None, max_length=1000, description="Reason")
    signature: str | None = Field(None, description="Wallet signature")


class ApprovalStats(BaseModel):
    """Approval workflow statistics."""

    total_tickets: int = Field(default=0, description="Total tickets")
    pending_tickets: int = Field(default=0, description="Pending tickets")
    partially_approved: int = Field(default=0, description="Partially approved")
    approved_tickets: int = Field(default=0, description="Approved tickets")
    rejected_tickets: int = Field(default=0, description="Rejected tickets")
    expired_tickets: int = Field(default=0, description="Expired tickets")
    escalated_tickets: int = Field(default=0, description="Currently escalated")
    avg_resolution_hours: float = Field(default=0.0, description="Avg resolution time")


class AuditLogEntry(BaseModel):
    """Audit log entry for approval actions."""

    id: str = Field(..., description="Entry ID")
    ticket_id: str = Field(..., description="Ticket ID")
    action: str = Field(..., description="Action type")
    actor: str = Field(..., description="Actor address")
    timestamp: datetime = Field(..., description="Action timestamp")
    old_status: ApprovalTicketStatus | None = Field(None, description="Previous status")
    new_status: ApprovalTicketStatus | None = Field(None, description="New status")
    details: dict[str, Any] | None = Field(None, description="Additional details")
