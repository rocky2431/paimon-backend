"""Rebalancing strategy engine."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.services.rebalance.schemas import (
    LiquidityTier,
    RebalanceAction,
    RebalanceDirection,
    RebalancePlan,
    RebalancePlanStep,
    RebalanceStats,
    RebalanceStatus,
    TierConfig,
    TierDeviation,
    TierState,
    WaterfallLiquidationPlan,
)

logger = logging.getLogger(__name__)


class RebalanceStrategyEngine:
    """Engine for generating and optimizing rebalance plans.

    Features:
    - Deviation calculation from target ratios
    - Plan generation with step optimization
    - Waterfall liquidation for L1 replenishment
    - Multi-tier rebalancing support
    """

    # Default tier configurations (v2.0.0: L1=10%, L2=30%, L3=60%)
    DEFAULT_TIER_CONFIGS: dict[LiquidityTier, TierConfig] = {
        LiquidityTier.L1: TierConfig(
            tier=LiquidityTier.L1,
            target_ratio=Decimal("0.10"),  # 10% (v2.0.0 标准配比)
            min_ratio=Decimal("0.08"),
            max_ratio=Decimal("0.15"),
            rebalance_threshold=Decimal("0.02"),
        ),
        LiquidityTier.L2: TierConfig(
            tier=LiquidityTier.L2,
            target_ratio=Decimal("0.30"),  # 30% (v2.0.0 标准配比)
            min_ratio=Decimal("0.25"),
            max_ratio=Decimal("0.35"),
            rebalance_threshold=Decimal("0.03"),
        ),
        LiquidityTier.L3: TierConfig(
            tier=LiquidityTier.L3,
            target_ratio=Decimal("0.60"),  # 60% (v2.0.0 标准配比)
            min_ratio=Decimal("0.55"),
            max_ratio=Decimal("0.65"),
            rebalance_threshold=Decimal("0.03"),
        ),
    }

    def __init__(
        self,
        tier_configs: dict[LiquidityTier, TierConfig] | None = None,
    ):
        """Initialize rebalance strategy engine.

        Args:
            tier_configs: Custom tier configurations (uses defaults if None)
        """
        self.tier_configs = tier_configs or self.DEFAULT_TIER_CONFIGS
        self._plans: dict[str, RebalancePlan] = {}
        self._validate_tier_configs()

    def _validate_tier_configs(self) -> None:
        """Validate that tier configs sum to ~100%."""
        total_target = sum(
            config.target_ratio for config in self.tier_configs.values()
        )
        if abs(total_target - Decimal("1.0")) > Decimal("0.01"):
            logger.warning(
                f"Tier target ratios sum to {total_target}, expected ~1.0"
            )

    def calculate_deviations(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
    ) -> list[TierDeviation]:
        """Calculate deviations from target for each tier.

        Args:
            tier_states: Current state of each tier
            total_value: Total portfolio value

        Returns:
            List of deviations for each tier
        """
        deviations = []

        for state in tier_states:
            config = self.tier_configs.get(state.tier)
            if not config:
                continue

            current_ratio = state.ratio if state.ratio > 0 else (
                state.value / total_value if total_value > 0 else Decimal(0)
            )

            deviation = current_ratio - config.target_ratio
            deviation_percent = (
                (deviation / config.target_ratio * 100)
                if config.target_ratio > 0
                else Decimal(0)
            )

            direction = (
                RebalanceDirection.DECREASE
                if deviation > 0
                else RebalanceDirection.INCREASE
            )

            amount_to_adjust = abs(deviation) * total_value

            needs_rebalance = not config.is_within_threshold(current_ratio)
            within_bounds = config.is_within_bounds(current_ratio)

            deviations.append(
                TierDeviation(
                    tier=state.tier,
                    current_ratio=current_ratio,
                    target_ratio=config.target_ratio,
                    deviation=deviation,
                    deviation_percent=deviation_percent,
                    direction=direction,
                    amount_to_adjust=amount_to_adjust,
                    needs_rebalance=needs_rebalance,
                    within_bounds=within_bounds,
                )
            )

        return deviations

    def needs_rebalancing(self, deviations: list[TierDeviation]) -> bool:
        """Check if any tier needs rebalancing.

        Args:
            deviations: Deviation calculations

        Returns:
            True if rebalancing is needed
        """
        return any(d.needs_rebalance for d in deviations)

    def any_out_of_bounds(self, deviations: list[TierDeviation]) -> bool:
        """Check if any tier is out of acceptable bounds.

        Args:
            deviations: Deviation calculations

        Returns:
            True if any tier is out of bounds
        """
        return any(not d.within_bounds for d in deviations)

    def generate_rebalance_plan(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
        trigger_reason: str = "Manual trigger",
    ) -> RebalancePlan:
        """Generate a rebalance plan to bring tiers to target.

        Args:
            tier_states: Current state of each tier
            total_value: Total portfolio value
            trigger_reason: Reason for rebalancing

        Returns:
            Rebalance plan with steps
        """
        plan_id = f"RBL-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        deviations = self.calculate_deviations(tier_states, total_value)
        steps = self._generate_steps(deviations, total_value)

        # Calculate expected final state
        expected_final = self._calculate_expected_final_state(
            tier_states, steps, total_value
        )

        total_amount = sum(step.amount for step in steps)

        plan = RebalancePlan(
            plan_id=plan_id,
            status=RebalanceStatus.DRAFT,
            trigger_reason=trigger_reason,
            initial_state=tier_states,
            deviations=deviations,
            steps=steps,
            total_amount=total_amount,
            estimated_gas=self._estimate_gas(steps),
            estimated_slippage=self._estimate_slippage(steps, total_value),
            expected_final_state=expected_final,
            created_at=now,
        )

        self._plans[plan_id] = plan
        logger.info(
            f"Generated rebalance plan {plan_id} with {len(steps)} steps, "
            f"total amount: {total_amount}"
        )

        return plan

    def _generate_steps(
        self,
        deviations: list[TierDeviation],
        total_value: Decimal,
    ) -> list[RebalancePlanStep]:
        """Generate optimal rebalancing steps.

        Strategy:
        1. Identify tiers that need to decrease (over-allocated)
        2. Identify tiers that need to increase (under-allocated)
        3. Generate transfers from over to under, prioritizing L1

        Args:
            deviations: Deviation calculations
            total_value: Total portfolio value

        Returns:
            List of rebalance steps
        """
        steps = []
        step_id = 1

        # Separate tiers by direction
        to_decrease = [
            d for d in deviations
            if d.direction == RebalanceDirection.DECREASE and d.needs_rebalance
        ]
        to_increase = [
            d for d in deviations
            if d.direction == RebalanceDirection.INCREASE and d.needs_rebalance
        ]

        # Sort: decrease L3 first (least liquid), increase L1 first (most needed)
        to_decrease.sort(
            key=lambda d: (
                0 if d.tier == LiquidityTier.L3 else
                1 if d.tier == LiquidityTier.L2 else 2
            )
        )
        to_increase.sort(
            key=lambda d: (
                0 if d.tier == LiquidityTier.L1 else
                1 if d.tier == LiquidityTier.L2 else 2
            )
        )

        # Generate transfer steps
        for decrease_dev in to_decrease:
            remaining_to_decrease = decrease_dev.amount_to_adjust

            for increase_dev in to_increase:
                if remaining_to_decrease <= 0:
                    break

                if increase_dev.amount_to_adjust <= 0:
                    continue

                transfer_amount = min(
                    remaining_to_decrease,
                    increase_dev.amount_to_adjust,
                )

                if transfer_amount > 0:
                    steps.append(
                        RebalancePlanStep(
                            step_id=step_id,
                            action=RebalanceAction.SWAP,
                            from_tier=decrease_dev.tier,
                            to_tier=increase_dev.tier,
                            amount=transfer_amount,
                            priority=self._get_priority(
                                decrease_dev.tier, increase_dev.tier
                            ),
                            notes=f"Transfer from {decrease_dev.tier.value} to {increase_dev.tier.value}",
                        )
                    )
                    step_id += 1

                    remaining_to_decrease -= transfer_amount
                    increase_dev.amount_to_adjust -= transfer_amount

        # Sort steps by priority
        steps.sort(key=lambda s: s.priority)

        return steps

    def _get_priority(
        self,
        from_tier: LiquidityTier,
        to_tier: LiquidityTier,
    ) -> int:
        """Get priority for a transfer.

        Higher priority for transfers to L1 (liquidity).

        Args:
            from_tier: Source tier
            to_tier: Destination tier

        Returns:
            Priority (1=highest)
        """
        if to_tier == LiquidityTier.L1:
            return 1
        if to_tier == LiquidityTier.L2:
            return 2
        return 3

    def _calculate_expected_final_state(
        self,
        initial_states: list[TierState],
        steps: list[RebalancePlanStep],
        total_value: Decimal,
    ) -> list[TierState]:
        """Calculate expected state after executing steps.

        Args:
            initial_states: Initial tier states
            steps: Rebalance steps
            total_value: Total portfolio value

        Returns:
            Expected final state
        """
        # Create mutable copy of values
        values = {state.tier: state.value for state in initial_states}

        for step in steps:
            if step.from_tier and step.from_tier in values:
                values[step.from_tier] -= step.amount
            if step.to_tier and step.to_tier in values:
                values[step.to_tier] += step.amount

        # Convert back to TierState
        return [
            TierState(
                tier=tier,
                value=value,
                ratio=value / total_value if total_value > 0 else Decimal(0),
                assets=[],
            )
            for tier, value in values.items()
        ]

    def _estimate_gas(self, steps: list[RebalancePlanStep]) -> Decimal:
        """Estimate gas cost for executing steps.

        Args:
            steps: Rebalance steps

        Returns:
            Estimated gas in wei
        """
        # Rough estimate: 200k gas per swap
        base_gas = Decimal("200000")
        return base_gas * len(steps)

    def _estimate_slippage(
        self,
        steps: list[RebalancePlanStep],
        total_value: Decimal,
    ) -> Decimal:
        """Estimate total slippage.

        Args:
            steps: Rebalance steps
            total_value: Total value

        Returns:
            Estimated slippage as ratio
        """
        # Rough estimate: 0.1% slippage per swap
        base_slippage = Decimal("0.001")
        total_swap_amount = sum(
            step.amount for step in steps if step.action == RebalanceAction.SWAP
        )

        if total_value == 0:
            return Decimal(0)

        return base_slippage * (total_swap_amount / total_value)

    def generate_waterfall_liquidation(
        self,
        target_amount: Decimal,
        tier_states: list[TierState],
    ) -> WaterfallLiquidationPlan:
        """Generate waterfall liquidation plan for L1 replenishment.

        Liquidation order: L2 -> L3 (easier to harder liquidity)

        Args:
            target_amount: Amount needed for L1
            tier_states: Current tier states

        Returns:
            Waterfall liquidation plan
        """
        steps = []
        step_id = 1
        remaining = target_amount
        total_liquidated = Decimal(0)

        # Liquidation order: L2 first, then L3
        liquidation_order = [LiquidityTier.L2, LiquidityTier.L3]

        state_map = {state.tier: state for state in tier_states}

        for tier in liquidation_order:
            if remaining <= 0:
                break

            state = state_map.get(tier)
            if not state or state.value <= 0:
                continue

            config = self.tier_configs.get(tier)
            if not config:
                continue

            # Calculate how much we can take while staying above minimum
            total_value = sum(s.value for s in tier_states)
            min_value = config.min_ratio * total_value
            available = max(Decimal(0), state.value - min_value)

            if available > 0:
                liquidate_amount = min(remaining, available)

                steps.append(
                    RebalancePlanStep(
                        step_id=step_id,
                        action=RebalanceAction.LIQUIDATE,
                        from_tier=tier,
                        to_tier=LiquidityTier.L1,
                        amount=liquidate_amount,
                        priority=step_id,
                        notes=f"Waterfall liquidation from {tier.value}",
                    )
                )
                step_id += 1

                remaining -= liquidate_amount
                total_liquidated += liquidate_amount

        return WaterfallLiquidationPlan(
            target_amount=target_amount,
            liquidation_steps=steps,
            total_liquidated=total_liquidated,
            remaining_deficit=max(Decimal(0), remaining),
        )

    def get_plan(self, plan_id: str) -> RebalancePlan | None:
        """Get a rebalance plan by ID.

        Args:
            plan_id: Plan ID

        Returns:
            Rebalance plan or None
        """
        return self._plans.get(plan_id)

    def approve_plan(self, plan_id: str) -> bool:
        """Approve a rebalance plan for execution.

        Args:
            plan_id: Plan ID

        Returns:
            True if approved

        Raises:
            ValueError: If plan not found or wrong status
        """
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        if plan.status != RebalanceStatus.DRAFT:
            raise ValueError(
                f"Plan {plan_id} is not in DRAFT status (current: {plan.status})"
            )

        plan.status = RebalanceStatus.APPROVED
        plan.approved_at = datetime.now(timezone.utc)
        logger.info(f"Approved rebalance plan {plan_id}")
        return True

    def cancel_plan(self, plan_id: str) -> bool:
        """Cancel a rebalance plan.

        Args:
            plan_id: Plan ID

        Returns:
            True if cancelled

        Raises:
            ValueError: If plan not found or cannot cancel
        """
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        if plan.status in [
            RebalanceStatus.COMPLETED,
            RebalanceStatus.EXECUTING,
        ]:
            raise ValueError(f"Cannot cancel plan in {plan.status} status")

        plan.status = RebalanceStatus.CANCELLED
        logger.info(f"Cancelled rebalance plan {plan_id}")
        return True

    def get_stats(self) -> RebalanceStats:
        """Get rebalancing statistics.

        Returns:
            Rebalance statistics
        """
        stats = RebalanceStats()

        for plan in self._plans.values():
            stats.total_plans += 1

            if plan.status == RebalanceStatus.COMPLETED:
                stats.completed_plans += 1
                stats.total_volume_rebalanced += plan.total_amount
            elif plan.status == RebalanceStatus.FAILED:
                stats.failed_plans += 1
            elif plan.status in [
                RebalanceStatus.DRAFT,
                RebalanceStatus.PENDING_APPROVAL,
            ]:
                stats.pending_plans += 1

        return stats


# Singleton instance
_strategy_engine: RebalanceStrategyEngine | None = None


def get_rebalance_strategy_engine() -> RebalanceStrategyEngine:
    """Get or create rebalance strategy engine singleton."""
    global _strategy_engine
    if _strategy_engine is None:
        _strategy_engine = RebalanceStrategyEngine()
    return _strategy_engine
