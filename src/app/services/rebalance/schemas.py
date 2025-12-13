"""Rebalancing strategy schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LiquidityTier(str, Enum):
    """Liquidity tier levels."""

    L1 = "L1"  # Instant liquidity (stablecoins, etc.)
    L2 = "L2"  # Short-term assets (T-bills, money market)
    L3 = "L3"  # Long-term assets (bonds, RWA)


class RebalanceDirection(str, Enum):
    """Direction of rebalancing operation."""

    INCREASE = "INCREASE"  # Move funds into tier
    DECREASE = "DECREASE"  # Move funds out of tier


class RebalanceAction(str, Enum):
    """Type of rebalancing action."""

    DEPOSIT = "DEPOSIT"  # Deposit into tier
    WITHDRAW = "WITHDRAW"  # Withdraw from tier
    SWAP = "SWAP"  # Swap between tiers
    LIQUIDATE = "LIQUIDATE"  # Waterfall liquidation


class RebalanceStatus(str, Enum):
    """Status of rebalance plan."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TierConfig(BaseModel):
    """Configuration for a liquidity tier."""

    tier: LiquidityTier = Field(..., description="Tier level")
    target_ratio: Decimal = Field(
        ..., ge=0, le=1, description="Target ratio (0-1)"
    )
    min_ratio: Decimal = Field(
        ..., ge=0, le=1, description="Minimum acceptable ratio"
    )
    max_ratio: Decimal = Field(
        ..., ge=0, le=1, description="Maximum acceptable ratio"
    )
    rebalance_threshold: Decimal = Field(
        default=Decimal("0.02"),
        ge=0,
        le=1,
        description="Threshold to trigger rebalancing",
    )

    def is_within_bounds(self, current_ratio: Decimal) -> bool:
        """Check if current ratio is within bounds."""
        return self.min_ratio <= current_ratio <= self.max_ratio

    def is_within_threshold(self, current_ratio: Decimal) -> bool:
        """Check if current ratio is within rebalance threshold."""
        deviation = abs(current_ratio - self.target_ratio)
        return deviation <= self.rebalance_threshold


class TierState(BaseModel):
    """Current state of a liquidity tier."""

    tier: LiquidityTier = Field(..., description="Tier level")
    value: Decimal = Field(..., ge=0, description="Current value in tier")
    ratio: Decimal = Field(..., ge=0, le=1, description="Current ratio of total")
    assets: list[dict[str, Any]] = Field(
        default_factory=list, description="Assets in this tier"
    )


class TierDeviation(BaseModel):
    """Deviation from target for a tier."""

    tier: LiquidityTier = Field(..., description="Tier level")
    current_ratio: Decimal = Field(..., description="Current ratio")
    target_ratio: Decimal = Field(..., description="Target ratio")
    deviation: Decimal = Field(..., description="Deviation from target")
    deviation_percent: Decimal = Field(..., description="Deviation as percentage")
    direction: RebalanceDirection = Field(..., description="Direction to adjust")
    amount_to_adjust: Decimal = Field(
        ..., ge=0, description="Amount needed to reach target"
    )
    needs_rebalance: bool = Field(..., description="Whether rebalancing is needed")
    within_bounds: bool = Field(..., description="Whether within min/max bounds")


class RebalancePlanStep(BaseModel):
    """Single step in a rebalance plan."""

    step_id: int = Field(..., ge=1, description="Step number")
    action: RebalanceAction = Field(..., description="Action type")
    from_tier: LiquidityTier | None = Field(None, description="Source tier")
    to_tier: LiquidityTier | None = Field(None, description="Destination tier")
    amount: Decimal = Field(..., ge=0, description="Amount to move")
    asset_address: str | None = Field(None, description="Specific asset address")
    expected_slippage: Decimal = Field(
        default=Decimal(0), ge=0, description="Expected slippage"
    )
    priority: int = Field(default=1, ge=1, le=10, description="Execution priority")
    notes: str | None = Field(None, description="Notes about this step")


class RebalancePlan(BaseModel):
    """Complete rebalance plan."""

    plan_id: str = Field(..., description="Plan ID")
    status: RebalanceStatus = Field(
        default=RebalanceStatus.DRAFT, description="Plan status"
    )
    trigger_reason: str = Field(..., description="Reason for rebalancing")

    # State before rebalancing
    initial_state: list[TierState] = Field(
        ..., description="Initial tier states"
    )
    deviations: list[TierDeviation] = Field(
        ..., description="Deviations from target"
    )

    # Plan details
    steps: list[RebalancePlanStep] = Field(
        default_factory=list, description="Rebalance steps"
    )
    total_amount: Decimal = Field(
        default=Decimal(0), ge=0, description="Total amount to rebalance"
    )
    estimated_gas: Decimal = Field(
        default=Decimal(0), ge=0, description="Estimated gas cost"
    )
    estimated_slippage: Decimal = Field(
        default=Decimal(0), ge=0, description="Total estimated slippage"
    )

    # Expected final state
    expected_final_state: list[TierState] = Field(
        default_factory=list, description="Expected state after rebalancing"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Plan creation time")
    approved_at: datetime | None = Field(None, description="Approval time")
    executed_at: datetime | None = Field(None, description="Execution start time")
    completed_at: datetime | None = Field(None, description="Completion time")

    # Execution details
    executed_steps: int = Field(
        default=0, ge=0, description="Number of executed steps"
    )
    failed_step: int | None = Field(None, description="Failed step number if any")
    error_message: str | None = Field(None, description="Error message if failed")
    tx_hashes: list[str] = Field(
        default_factory=list, description="Transaction hashes"
    )


class WaterfallLiquidationPlan(BaseModel):
    """Plan for waterfall liquidation."""

    target_amount: Decimal = Field(..., ge=0, description="Amount needed")
    liquidation_steps: list[RebalancePlanStep] = Field(
        ..., description="Liquidation steps in order"
    )
    total_liquidated: Decimal = Field(
        default=Decimal(0), description="Total amount liquidated"
    )
    remaining_deficit: Decimal = Field(
        default=Decimal(0), description="Remaining deficit"
    )


class RebalanceStats(BaseModel):
    """Statistics for rebalancing operations."""

    total_plans: int = Field(default=0, description="Total plans created")
    completed_plans: int = Field(default=0, description="Completed plans")
    failed_plans: int = Field(default=0, description="Failed plans")
    pending_plans: int = Field(default=0, description="Pending approval plans")
    total_volume_rebalanced: Decimal = Field(
        default=Decimal(0), description="Total volume rebalanced"
    )
    avg_execution_time_seconds: float = Field(
        default=0, description="Average execution time"
    )
