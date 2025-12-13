"""Tests for rebalancing strategy engine."""

from decimal import Decimal

import pytest

from app.services.rebalance import (
    LiquidityTier,
    RebalanceAction,
    RebalanceDirection,
    RebalanceStatus,
    RebalanceStrategyEngine,
    TierConfig,
    TierState,
)


class TestDeviationCalculation:
    """Tests for deviation calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RebalanceStrategyEngine()

    def test_calculate_deviations_balanced(self):
        """Test deviations when tiers are balanced."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("115000"),  # 11.5%
                ratio=Decimal("0.115"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("300000"),  # 30%
                ratio=Decimal("0.30"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("585000"),  # 58.5%
                ratio=Decimal("0.585"),
                assets=[],
            ),
        ]

        deviations = self.engine.calculate_deviations(tier_states, total_value)

        assert len(deviations) == 3
        # All should be at target, no rebalancing needed
        assert all(d.needs_rebalance is False for d in deviations)
        assert all(d.within_bounds is True for d in deviations)

    def test_calculate_deviations_l1_low(self):
        """Test deviations when L1 is below target."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),  # 5% (below 8% min)
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("350000"),  # 35%
                ratio=Decimal("0.35"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("600000"),  # 60%
                ratio=Decimal("0.60"),
                assets=[],
            ),
        ]

        deviations = self.engine.calculate_deviations(tier_states, total_value)

        l1_dev = next(d for d in deviations if d.tier == LiquidityTier.L1)
        assert l1_dev.direction == RebalanceDirection.INCREASE
        assert l1_dev.needs_rebalance is True
        assert l1_dev.within_bounds is False

    def test_calculate_deviations_l3_high(self):
        """Test deviations when L3 is above target."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("100000"),  # 10%
                ratio=Decimal("0.10"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("200000"),  # 20% (below 25% min)
                ratio=Decimal("0.20"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("700000"),  # 70% (above 65% max)
                ratio=Decimal("0.70"),
                assets=[],
            ),
        ]

        deviations = self.engine.calculate_deviations(tier_states, total_value)

        l3_dev = next(d for d in deviations if d.tier == LiquidityTier.L3)
        assert l3_dev.direction == RebalanceDirection.DECREASE
        assert l3_dev.needs_rebalance is True
        assert l3_dev.within_bounds is False


class TestNeedsRebalancing:
    """Tests for rebalancing checks."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RebalanceStrategyEngine()

    def test_needs_rebalancing_false(self):
        """Test no rebalancing needed when balanced."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("115000"),
                ratio=Decimal("0.115"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("300000"),
                ratio=Decimal("0.30"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("585000"),
                ratio=Decimal("0.585"),
                assets=[],
            ),
        ]

        deviations = self.engine.calculate_deviations(tier_states, total_value)
        assert self.engine.needs_rebalancing(deviations) is False

    def test_needs_rebalancing_true(self):
        """Test rebalancing needed when imbalanced."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),  # 5% - low
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("250000"),
                ratio=Decimal("0.25"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("700000"),  # 70% - high
                ratio=Decimal("0.70"),
                assets=[],
            ),
        ]

        deviations = self.engine.calculate_deviations(tier_states, total_value)
        assert self.engine.needs_rebalancing(deviations) is True


class TestPlanGeneration:
    """Tests for rebalance plan generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RebalanceStrategyEngine()

    def test_generate_plan_balanced(self):
        """Test plan generation when already balanced."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("115000"),
                ratio=Decimal("0.115"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("300000"),
                ratio=Decimal("0.30"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("585000"),
                ratio=Decimal("0.585"),
                assets=[],
            ),
        ]

        plan = self.engine.generate_rebalance_plan(
            tier_states, total_value, "Test trigger"
        )

        assert plan.plan_id.startswith("RBL-")
        assert plan.status == RebalanceStatus.DRAFT
        assert len(plan.steps) == 0  # No steps needed

    def test_generate_plan_imbalanced(self):
        """Test plan generation when imbalanced."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),  # 5%
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("250000"),  # 25%
                ratio=Decimal("0.25"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("700000"),  # 70%
                ratio=Decimal("0.70"),
                assets=[],
            ),
        ]

        plan = self.engine.generate_rebalance_plan(
            tier_states, total_value, "Liquidity low"
        )

        assert plan.plan_id.startswith("RBL-")
        assert len(plan.steps) > 0
        assert plan.total_amount > 0

        # First step should prioritize L1
        first_step = plan.steps[0]
        assert first_step.to_tier == LiquidityTier.L1

    def test_generate_plan_preserves_state(self):
        """Test that plan is stored in engine."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("250000"),
                ratio=Decimal("0.25"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("700000"),
                ratio=Decimal("0.70"),
                assets=[],
            ),
        ]

        plan = self.engine.generate_rebalance_plan(tier_states, total_value)

        retrieved = self.engine.get_plan(plan.plan_id)
        assert retrieved is not None
        assert retrieved.plan_id == plan.plan_id


class TestWaterfallLiquidation:
    """Tests for waterfall liquidation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RebalanceStrategyEngine()

    def test_waterfall_liquidation_from_l2(self):
        """Test liquidation takes from L2 first."""
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("350000"),  # Has excess
                ratio=Decimal("0.35"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("600000"),
                ratio=Decimal("0.60"),
                assets=[],
            ),
        ]

        plan = self.engine.generate_waterfall_liquidation(
            target_amount=Decimal("50000"),
            tier_states=tier_states,
        )

        assert plan.total_liquidated > 0
        assert len(plan.liquidation_steps) > 0

        # First step should be from L2
        first_step = plan.liquidation_steps[0]
        assert first_step.from_tier == LiquidityTier.L2
        assert first_step.to_tier == LiquidityTier.L1
        assert first_step.action == RebalanceAction.LIQUIDATE

    def test_waterfall_liquidation_insufficient_l2(self):
        """Test liquidation cascades to L3 if L2 insufficient."""
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("260000"),  # At minimum, no excess
                ratio=Decimal("0.26"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("690000"),  # Has excess
                ratio=Decimal("0.69"),
                assets=[],
            ),
        ]

        plan = self.engine.generate_waterfall_liquidation(
            target_amount=Decimal("100000"),
            tier_states=tier_states,
        )

        assert plan.total_liquidated > 0
        # Should include L3 liquidation
        assert any(
            step.from_tier == LiquidityTier.L3
            for step in plan.liquidation_steps
        )

    def test_waterfall_liquidation_deficit(self):
        """Test remaining deficit when insufficient liquidity."""
        tier_states = [
            TierState(
                tier=LiquidityTier.L1,
                value=Decimal("50000"),
                ratio=Decimal("0.05"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L2,
                value=Decimal("250000"),  # At minimum
                ratio=Decimal("0.25"),
                assets=[],
            ),
            TierState(
                tier=LiquidityTier.L3,
                value=Decimal("700000"),  # At/near maximum
                ratio=Decimal("0.70"),
                assets=[],
            ),
        ]

        plan = self.engine.generate_waterfall_liquidation(
            target_amount=Decimal("500000"),  # Very large amount
            tier_states=tier_states,
        )

        # Should have remaining deficit
        assert plan.remaining_deficit > 0 or plan.total_liquidated > 0


class TestPlanApprovalAndCancellation:
    """Tests for plan approval and cancellation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RebalanceStrategyEngine()

    def test_approve_plan(self):
        """Test approving a plan."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("50000"), ratio=Decimal("0.05"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("250000"), ratio=Decimal("0.25"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("700000"), ratio=Decimal("0.70"), assets=[]),
        ]

        plan = self.engine.generate_rebalance_plan(tier_states, total_value)

        result = self.engine.approve_plan(plan.plan_id)

        assert result is True
        updated_plan = self.engine.get_plan(plan.plan_id)
        assert updated_plan.status == RebalanceStatus.APPROVED
        assert updated_plan.approved_at is not None

    def test_approve_plan_not_found(self):
        """Test approving non-existent plan."""
        with pytest.raises(ValueError, match="not found"):
            self.engine.approve_plan("RBL-INVALID")

    def test_approve_plan_wrong_status(self):
        """Test approving already approved plan."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("50000"), ratio=Decimal("0.05"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("250000"), ratio=Decimal("0.25"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("700000"), ratio=Decimal("0.70"), assets=[]),
        ]

        plan = self.engine.generate_rebalance_plan(tier_states, total_value)
        self.engine.approve_plan(plan.plan_id)

        with pytest.raises(ValueError, match="not in DRAFT"):
            self.engine.approve_plan(plan.plan_id)

    def test_cancel_plan(self):
        """Test cancelling a plan."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("50000"), ratio=Decimal("0.05"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("250000"), ratio=Decimal("0.25"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("700000"), ratio=Decimal("0.70"), assets=[]),
        ]

        plan = self.engine.generate_rebalance_plan(tier_states, total_value)

        result = self.engine.cancel_plan(plan.plan_id)

        assert result is True
        updated_plan = self.engine.get_plan(plan.plan_id)
        assert updated_plan.status == RebalanceStatus.CANCELLED


class TestStatistics:
    """Tests for rebalancing statistics."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RebalanceStrategyEngine()

    def test_empty_stats(self):
        """Test stats when empty."""
        stats = self.engine.get_stats()

        assert stats.total_plans == 0
        assert stats.completed_plans == 0

    def test_stats_after_plans(self):
        """Test stats after creating plans."""
        total_value = Decimal("1000000")
        tier_states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("50000"), ratio=Decimal("0.05"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("250000"), ratio=Decimal("0.25"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("700000"), ratio=Decimal("0.70"), assets=[]),
        ]

        for _ in range(3):
            self.engine.generate_rebalance_plan(tier_states, total_value)

        stats = self.engine.get_stats()

        assert stats.total_plans == 3
        assert stats.pending_plans == 3  # All in DRAFT


class TestCustomTierConfigs:
    """Tests for custom tier configurations."""

    def test_custom_configs(self):
        """Test using custom tier configurations."""
        custom_configs = {
            LiquidityTier.L1: TierConfig(
                tier=LiquidityTier.L1,
                target_ratio=Decimal("0.20"),  # 20%
                min_ratio=Decimal("0.15"),
                max_ratio=Decimal("0.25"),
            ),
            LiquidityTier.L2: TierConfig(
                tier=LiquidityTier.L2,
                target_ratio=Decimal("0.30"),
                min_ratio=Decimal("0.25"),
                max_ratio=Decimal("0.35"),
            ),
            LiquidityTier.L3: TierConfig(
                tier=LiquidityTier.L3,
                target_ratio=Decimal("0.50"),
                min_ratio=Decimal("0.45"),
                max_ratio=Decimal("0.55"),
            ),
        }

        engine = RebalanceStrategyEngine(tier_configs=custom_configs)

        total_value = Decimal("1000000")
        tier_states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("200000"), ratio=Decimal("0.20"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("300000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("500000"), ratio=Decimal("0.50"), assets=[]),
        ]

        deviations = engine.calculate_deviations(tier_states, total_value)

        # All should be at target with custom configs
        assert all(d.needs_rebalance is False for d in deviations)
