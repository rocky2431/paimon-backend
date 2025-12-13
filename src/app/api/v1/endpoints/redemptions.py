"""Redemption Management API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.auth import CurrentUser, require_permissions
from app.services.redemption import (
    RedemptionChannel,
    RedemptionDetail,
    RedemptionFilterParams,
    RedemptionListResponse,
    RedemptionService,
    RedemptionStatus,
    get_redemption_service,
)
from app.services.redemption.schemas import (
    ApprovalRequest,
    RedemptionSortField,
    SettlementRequest,
    SettlementResponse,
    SortOrder,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/redemptions", tags=["Redemptions"])


@router.get("", response_model=RedemptionListResponse)
async def list_redemptions(
    user: CurrentUser,
    service: Annotated[RedemptionService, Depends(get_redemption_service)],
    status: RedemptionStatus | None = Query(None, description="Filter by status"),
    channel: RedemptionChannel | None = Query(None, description="Filter by channel"),
    owner: str | None = Query(
        None,
        description="Filter by owner address",
        pattern=r"^0x[a-fA-F0-9]{40}$",
    ),
    requires_approval: bool | None = Query(
        None, description="Filter by approval requirement"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: RedemptionSortField = Query(
        RedemptionSortField.REQUEST_TIME, description="Sort field"
    ),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
) -> RedemptionListResponse:
    """List redemption requests with filters and pagination.

    Requires: read:redemption permission
    """
    filters = RedemptionFilterParams(
        status=status,
        channel=channel,
        owner=owner,
        requires_approval=requires_approval,
    )

    return await service.list_redemptions(
        filters=filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/pending-approvals", response_model=RedemptionListResponse)
async def list_pending_approvals(
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["approve:redemption"])),
    ],
    service: Annotated[RedemptionService, Depends(get_redemption_service)],
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> RedemptionListResponse:
    """List redemptions pending approval.

    Requires: approve:redemption permission
    """
    return await service.get_pending_approvals(page=page, page_size=page_size)


@router.get("/stats")
async def get_redemption_stats(
    user: CurrentUser,
    service: Annotated[RedemptionService, Depends(get_redemption_service)],
) -> dict:
    """Get redemption statistics.

    Requires: read:redemption permission
    """
    stats = await service.get_stats()
    return {
        "total_requests": stats.total_requests,
        "pending_requests": stats.pending_requests,
        "pending_approval": stats.pending_approval,
        "approved_requests": stats.approved_requests,
        "settled_requests": stats.settled_requests,
        "rejected_requests": stats.rejected_requests,
        "cancelled_requests": stats.cancelled_requests,
        "total_volume": str(stats.total_volume),
    }


@router.get("/{redemption_id}", response_model=RedemptionDetail)
async def get_redemption_detail(
    redemption_id: int,
    user: CurrentUser,
    service: Annotated[RedemptionService, Depends(get_redemption_service)],
) -> RedemptionDetail:
    """Get detailed information for a redemption request.

    Includes full timeline of events.

    Requires: read:redemption permission
    """
    detail = await service.get_redemption_detail(redemption_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Redemption {redemption_id} not found",
        )
    return detail


@router.post("/{redemption_id}/approve")
async def approve_redemption(
    redemption_id: int,
    request: ApprovalRequest,
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["approve:redemption"])),
    ],
    service: Annotated[RedemptionService, Depends(get_redemption_service)],
) -> dict:
    """Approve or reject a redemption request.

    Actions:
    - APPROVE: Approve the redemption for settlement
    - REJECT: Reject the redemption with reason

    Requires: approve:redemption permission
    """
    try:
        await service.approve_redemption(
            redemption_id=redemption_id,
            request=request,
            approver=user.wallet_address or user.user_id,
        )
        return {
            "success": True,
            "redemption_id": redemption_id,
            "action": request.action.value,
            "message": f"Redemption {request.action.value.lower()}d successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{redemption_id}/settle", response_model=SettlementResponse)
async def trigger_settlement(
    redemption_id: int,
    request: SettlementRequest,
    user: Annotated[
        CurrentUser,
        Depends(require_permissions(["settle:redemption"])),
    ],
    service: Annotated[RedemptionService, Depends(get_redemption_service)],
) -> SettlementResponse:
    """Trigger manual settlement for a redemption.

    Normally settlements are processed automatically at settlement_time.
    This endpoint allows manual trigger for:
    - Approved redemptions ready for settlement
    - Force settlement if needed (admin only)

    Requires: settle:redemption permission
    """
    response = await service.trigger_settlement(
        redemption_id=redemption_id,
        force=request.force,
    )

    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.message,
        )

    return response
