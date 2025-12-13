"""Approval Management API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.approval import (
    ApprovalTicketDetail,
    ApprovalTicketListResponse,
    ApprovalTicketStatus,
    ApprovalTicketType,
    ApprovalWorkflowEngine,
    get_approval_workflow_engine,
)
from app.services.approval.schemas import (
    ApprovalActionRequest,
    ApprovalStats,
    AuditLogEntry,
)
from app.services.auth import CurrentUser, require_permissions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("", response_model=ApprovalTicketListResponse)
async def list_approval_tickets(
    user: CurrentUser,
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
    status: ApprovalTicketStatus | None = Query(None, description="Filter by status"),
    ticket_type: ApprovalTicketType | None = Query(
        None, description="Filter by ticket type"
    ),
    requester: str | None = Query(
        None,
        description="Filter by requester address",
        pattern=r"^0x[a-fA-F0-9]{40}$",
    ),
    escalated_only: bool = Query(False, description="Only show escalated tickets"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> ApprovalTicketListResponse:
    """List approval tickets with filters and pagination.

    Requires: read:approval permission
    """
    return await engine.list_tickets(
        status=status,
        ticket_type=ticket_type,
        requester=requester,
        escalated_only=escalated_only,
        page=page,
        page_size=page_size,
    )


@router.get("/pending", response_model=ApprovalTicketListResponse)
async def list_pending_for_user(
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["approve:approval"])),
    ],
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> ApprovalTicketListResponse:
    """List pending tickets that the current user can approve.

    Returns tickets sorted by SLA deadline (most urgent first).

    Requires: approve:approval permission
    """
    approver = user.wallet_address or user.user_id
    return await engine.get_pending_for_approver(
        approver=approver,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=ApprovalStats)
async def get_approval_stats(
    user: CurrentUser,
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
) -> ApprovalStats:
    """Get approval workflow statistics.

    Requires: read:approval permission
    """
    return await engine.get_stats()


@router.get("/audit", response_model=list[AuditLogEntry])
async def get_audit_log(
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["audit:read"])),
    ],
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
    ticket_id: str | None = Query(None, description="Filter by ticket ID"),
    limit: int = Query(100, ge=1, le=500, description="Maximum entries"),
) -> list[AuditLogEntry]:
    """Get audit log entries.

    Returns the most recent entries first.

    Requires: audit:read permission
    """
    return engine.get_audit_log(ticket_id=ticket_id, limit=limit)


@router.get("/{ticket_id}", response_model=ApprovalTicketDetail)
async def get_ticket_detail(
    ticket_id: str,
    user: CurrentUser,
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
) -> ApprovalTicketDetail:
    """Get detailed information for an approval ticket.

    Includes risk assessment and all approval records.

    Requires: read:approval permission
    """
    ticket = await engine.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    return ticket


@router.post("/{ticket_id}/action")
async def process_approval_action(
    ticket_id: str,
    request: ApprovalActionRequest,
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["approve:approval"])),
    ],
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
) -> dict:
    """Process an approval or rejection action.

    Actions:
    - APPROVE: Approve the ticket (may require multiple approvals)
    - REJECT: Reject the ticket with reason

    Requires: approve:approval permission
    """
    approver = user.wallet_address or user.user_id

    try:
        await engine.process_action(
            ticket_id=ticket_id,
            request=request,
            approver=approver,
        )

        # Get updated ticket status
        ticket = await engine.get_ticket(ticket_id)

        return {
            "success": True,
            "ticket_id": ticket_id,
            "action": request.action.value,
            "new_status": ticket.status.value if ticket else "unknown",
            "message": f"Action {request.action.value} processed successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{ticket_id}/cancel")
async def cancel_ticket(
    ticket_id: str,
    user: CurrentUser,
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
    reason: str = Query(..., description="Cancellation reason"),
) -> dict:
    """Cancel a pending approval ticket.

    Only pending or partially approved tickets can be cancelled.

    Requires: The requester or an admin can cancel.
    """
    actor = user.wallet_address or user.user_id

    try:
        await engine.cancel_ticket(
            ticket_id=ticket_id,
            actor=actor,
            reason=reason,
        )
        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": "Ticket cancelled successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/check-escalation")
async def trigger_escalation_check(
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["admin:approval"])),
    ],
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
) -> dict:
    """Manually trigger escalation check for pending tickets.

    Normally runs automatically on a schedule.

    Requires: admin:approval permission
    """
    escalated = await engine.check_escalation()
    return {
        "success": True,
        "escalated_count": len(escalated),
        "escalated_tickets": escalated,
    }


@router.post("/check-expired")
async def trigger_expiration_check(
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["admin:approval"])),
    ],
    engine: Annotated[ApprovalWorkflowEngine, Depends(get_approval_workflow_engine)],
) -> dict:
    """Manually trigger expiration check for pending tickets.

    Normally runs automatically on a schedule.

    Requires: admin:approval permission
    """
    expired = await engine.check_expired_tickets()
    return {
        "success": True,
        "expired_count": len(expired),
        "expired_tickets": expired,
    }
