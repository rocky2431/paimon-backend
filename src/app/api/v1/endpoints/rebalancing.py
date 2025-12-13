"""Rebalancing API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.rebalance import (
    ExecutionResult,
    ExecutionStatus,
    LiquidityTier,
    RebalanceExecutor,
    RebalancePlan,
    RebalanceStatus,
    RebalanceStrategyEngine,
    TierDeviation,
    TierState,
    get_rebalance_executor,
    get_rebalance_strategy_engine,
)
from app.services.rebalance.triggers import (
    RebalanceTriggerService,
    TriggerConfig,
    TriggerHistory,
    TriggerResult,
    TriggerType,
    get_trigger_service,
)

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])


# Request/Response Models
class TierStateInput(BaseModel):
    """Input for tier state."""

    tier: LiquidityTier
    value: Decimal = Field(..., ge=0)
    ratio: Decimal = Field(default=Decimal(0), ge=0, le=1)


class DeviationResponse(BaseModel):
    """Response for deviation calculation."""

    deviations: list[dict[str, Any]]
    needs_rebalancing: bool
    any_out_of_bounds: bool
    total_value: Decimal


class PlanPreviewRequest(BaseModel):
    """Request for plan preview."""

    tier_states: list[TierStateInput]
    total_value: Decimal = Field(..., gt=0)
    trigger_reason: str = Field(default="Preview")


class PlanPreviewResponse(BaseModel):
    """Response for plan preview."""

    plan_id: str
    status: RebalanceStatus
    steps: list[dict[str, Any]]
    total_amount: Decimal
    estimated_gas: Decimal
    estimated_slippage: Decimal
    expected_final_state: list[dict[str, Any]]


class ManualTriggerRequest(BaseModel):
    """Request for manual trigger."""

    tier_states: list[TierStateInput]
    total_value: Decimal = Field(..., gt=0)
    reason: str = Field(default="Manual trigger")
    auto_approve: bool = Field(default=False)


class ExecuteRequest(BaseModel):
    """Request to execute a plan."""

    plan_id: str


class TriggerConfigUpdate(BaseModel):
    """Request to update trigger config."""

    threshold_enabled: bool | None = None
    deviation_threshold: Decimal | None = None
    liquidity_enabled: bool | None = None
    l1_min_ratio: Decimal | None = None
    l1_critical_ratio: Decimal | None = None
    schedule_enabled: bool | None = None
    schedule_cron: str | None = None


class TriggerEvaluationRequest(BaseModel):
    """Request to evaluate triggers."""

    tier_states: list[TierStateInput]
    total_value: Decimal = Field(..., gt=0)


class PaginatedHistoryResponse(BaseModel):
    """Paginated history response."""

    items: list[TriggerHistory]
    total: int
    page: int
    page_size: int


def _convert_tier_states(inputs: list[TierStateInput]) -> list[TierState]:
    """Convert input tier states to domain model."""
    return [
        TierState(
            tier=inp.tier,
            value=inp.value,
            ratio=inp.ratio,
            assets=[],
        )
        for inp in inputs
    ]


@router.post("/deviation", response_model=DeviationResponse)
async def calculate_deviation(
    tier_states: list[TierStateInput],
    total_value: Decimal = Query(..., gt=0),
) -> DeviationResponse:
    """Calculate deviation from target ratios.

    Returns deviation information for each tier.
    """
    engine = get_rebalance_strategy_engine()
    states = _convert_tier_states(tier_states)

    deviations = engine.calculate_deviations(states, total_value)

    return DeviationResponse(
        deviations=[d.model_dump() for d in deviations],
        needs_rebalancing=engine.needs_rebalancing(deviations),
        any_out_of_bounds=engine.any_out_of_bounds(deviations),
        total_value=total_value,
    )


@router.post("/preview", response_model=PlanPreviewResponse)
async def preview_plan(request: PlanPreviewRequest) -> PlanPreviewResponse:
    """Preview a rebalancing plan without executing.

    Generates a plan that shows what steps would be taken.
    """
    engine = get_rebalance_strategy_engine()
    states = _convert_tier_states(request.tier_states)

    plan = engine.generate_rebalance_plan(
        states, request.total_value, request.trigger_reason
    )

    return PlanPreviewResponse(
        plan_id=plan.plan_id,
        status=plan.status,
        steps=[s.model_dump() for s in plan.steps],
        total_amount=plan.total_amount,
        estimated_gas=plan.estimated_gas,
        estimated_slippage=plan.estimated_slippage,
        expected_final_state=[s.model_dump() for s in plan.expected_final_state],
    )


@router.post("/trigger/manual")
async def trigger_manual_rebalance(
    request: ManualTriggerRequest,
) -> dict[str, Any]:
    """Manually trigger rebalancing.

    Creates and optionally approves a rebalance plan.
    """
    trigger_service = get_trigger_service()
    engine = trigger_service.strategy_engine
    states = _convert_tier_states(request.tier_states)

    plan = trigger_service.trigger_manual(
        states, request.total_value, request.reason
    )

    if request.auto_approve:
        engine.approve_plan(plan.plan_id)

    return {
        "plan_id": plan.plan_id,
        "status": plan.status.value if not request.auto_approve else RebalanceStatus.APPROVED.value,
        "steps_count": len(plan.steps),
        "total_amount": float(plan.total_amount),
        "auto_approved": request.auto_approve,
    }


@router.post("/trigger/evaluate")
async def evaluate_triggers(
    request: TriggerEvaluationRequest,
) -> list[TriggerResult]:
    """Evaluate all triggers without executing.

    Returns which triggers would fire given current state.
    """
    trigger_service = get_trigger_service()
    states = _convert_tier_states(request.tier_states)

    return trigger_service.evaluate_all_triggers(states, request.total_value)


@router.post("/trigger/automatic")
async def trigger_automatic_rebalance(
    request: TriggerEvaluationRequest,
) -> dict[str, Any]:
    """Automatically trigger rebalancing if needed.

    Evaluates triggers and creates a plan if any fire.
    """
    trigger_service = get_trigger_service()
    states = _convert_tier_states(request.tier_states)

    plan = trigger_service.trigger_automatic(states, request.total_value)

    if plan:
        return {
            "triggered": True,
            "plan_id": plan.plan_id,
            "reason": plan.trigger_reason,
            "steps_count": len(plan.steps),
        }

    return {
        "triggered": False,
        "plan_id": None,
        "reason": "No triggers activated",
    }


@router.get("/plan/{plan_id}")
async def get_plan(plan_id: str) -> dict[str, Any]:
    """Get a rebalance plan by ID."""
    engine = get_rebalance_strategy_engine()
    plan = engine.get_plan(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    return plan.model_dump()


@router.post("/plan/{plan_id}/approve")
async def approve_plan(plan_id: str) -> dict[str, Any]:
    """Approve a rebalance plan for execution."""
    engine = get_rebalance_strategy_engine()

    try:
        engine.approve_plan(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"plan_id": plan_id, "status": "approved"}


@router.post("/plan/{plan_id}/cancel")
async def cancel_plan(plan_id: str) -> dict[str, Any]:
    """Cancel a rebalance plan."""
    engine = get_rebalance_strategy_engine()

    try:
        engine.cancel_plan(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"plan_id": plan_id, "status": "cancelled"}


@router.post("/execute", response_model=dict)
async def execute_plan(request: ExecuteRequest) -> dict[str, Any]:
    """Execute an approved rebalance plan.

    Submits transactions and tracks execution.
    """
    engine = get_rebalance_strategy_engine()
    executor = get_rebalance_executor()

    plan = engine.get_plan(request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=404, detail=f"Plan {request.plan_id} not found"
        )

    if plan.status != RebalanceStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Plan must be approved before execution (current: {plan.status.value})",
        )

    result = await executor.execute_plan(plan)

    return {
        "execution_id": result.execution_id,
        "plan_id": result.plan_id,
        "status": result.status.value,
        "completed_steps": result.completed_steps,
        "total_steps": result.total_steps,
        "total_gas_used": result.total_gas_used,
        "total_value_moved": float(result.total_value_moved),
        "duration_seconds": result.duration_seconds,
        "transactions": [
            {
                "tx_id": tx.tx_id,
                "tx_hash": tx.tx_hash,
                "status": tx.status.value,
                "step_id": tx.step_id,
            }
            for tx in result.transactions
        ],
    }


@router.get("/execution/{execution_id}")
async def get_execution(execution_id: str) -> dict[str, Any]:
    """Get execution status by ID."""
    executor = get_rebalance_executor()
    context = executor.get_execution(execution_id)

    if not context:
        raise HTTPException(
            status_code=404, detail=f"Execution {execution_id} not found"
        )

    return context.model_dump()


@router.get("/history/triggers")
async def get_trigger_history(
    limit: int = 100,
    trigger_type: TriggerType | None = None,
    triggered_only: bool = False,
) -> list[TriggerHistory]:
    """Get trigger evaluation history."""
    trigger_service = get_trigger_service()
    return trigger_service.get_history(
        limit=limit,
        trigger_type=trigger_type,
        triggered_only=triggered_only,
    )


@router.get("/stats")
async def get_rebalance_stats() -> dict[str, Any]:
    """Get rebalancing statistics."""
    engine = get_rebalance_strategy_engine()
    stats = engine.get_stats()
    return stats.model_dump()


@router.get("/config/triggers")
async def get_trigger_config() -> TriggerConfig:
    """Get current trigger configuration."""
    trigger_service = get_trigger_service()
    return trigger_service.config


@router.patch("/config/triggers")
async def update_trigger_config(
    update: TriggerConfigUpdate,
) -> TriggerConfig:
    """Update trigger configuration."""
    trigger_service = get_trigger_service()
    current = trigger_service.config.model_dump()

    # Apply updates
    for key, value in update.model_dump(exclude_unset=True).items():
        if value is not None:
            current[key] = value

    new_config = TriggerConfig(**current)
    trigger_service.update_config(new_config)

    return new_config


@router.get("/wallets/usage")
async def get_wallet_usage() -> dict[str, Any]:
    """Get current daily wallet usage."""
    executor = get_rebalance_executor()
    usage = executor.get_daily_usage()

    return {
        tier.value: float(amount) for tier, amount in usage.items()
    }


@router.post("/wallets/reset-usage")
async def reset_wallet_usage() -> dict[str, str]:
    """Reset daily wallet usage counters."""
    executor = get_rebalance_executor()
    executor.reset_daily_usage()

    return {"status": "reset", "message": "Daily usage counters reset"}
