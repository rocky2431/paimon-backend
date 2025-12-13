"""Tests for rebalance triggers service."""

from decimal import Decimal

import pytest

from app.services.rebalance import (
    LiquidityTier,
    TierState,
)
from app.services.rebalance.triggers import (
    RebalanceTriggerService,
    TriggerConfig,
    TriggerType,
)


class TestThresholdTrigger:
    """Tests for threshold-based triggers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = TriggerConfig(
            threshold_enabled=True,
            deviation_threshold=Decimal("0.03"),
        )
        self.service = RebalanceTriggerService(config=self.config)

    def test_threshold_not_triggered_when_within(self):
        """Test no trigger when deviation within threshold."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("11500"), ratio=Decimal("0.115"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("58500"), ratio=Decimal("0.585"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_threshold_trigger(states, total_value)

        assert result.triggered is False
        assert result.trigger_type == TriggerType.THRESHOLD

    def test_threshold_triggered_when_exceeded(self):
        """Test trigger when deviation exceeds threshold."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("5000"), ratio=Decimal("0.05"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("35000"), ratio=Decimal("0.35"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_threshold_trigger(states, total_value)

        assert result.triggered is True
        assert result.severity == "high"

    def test_threshold_trigger_details(self):
        """Test trigger includes deviation details."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("8000"), ratio=Decimal("0.08"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("32000"), ratio=Decimal("0.32"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_threshold_trigger(states, total_value)

        assert "max_deviation" in result.details
        assert "threshold" in result.details
        assert "deviations" in result.details


class TestLiquidityTrigger:
    """Tests for liquidity-based triggers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = TriggerConfig(
            liquidity_enabled=True,
            l1_min_ratio=Decimal("0.08"),
            l1_critical_ratio=Decimal("0.05"),
        )
        self.service = RebalanceTriggerService(config=self.config)

    def test_liquidity_healthy(self):
        """Test no trigger when L1 is healthy."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("12000"), ratio=Decimal("0.12"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("58000"), ratio=Decimal("0.58"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_liquidity_trigger(states, total_value)

        assert result.triggered is False
        assert "healthy" in result.reason

    def test_liquidity_below_minimum(self):
        """Test trigger when L1 below minimum."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("6000"), ratio=Decimal("0.06"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("34000"), ratio=Decimal("0.34"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_liquidity_trigger(states, total_value)

        assert result.triggered is True
        assert result.severity == "high"

    def test_liquidity_critical(self):
        """Test critical trigger when L1 very low."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("3000"), ratio=Decimal("0.03"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("37000"), ratio=Decimal("0.37"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_liquidity_trigger(states, total_value)

        assert result.triggered is True
        assert result.severity == "critical"
        assert "CRITICAL" in result.reason

    def test_liquidity_no_l1_state(self):
        """Test handling when L1 state missing."""
        states = [
            TierState(tier=LiquidityTier.L2, value=Decimal("40000"), ratio=Decimal("0.40"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        result = self.service.evaluate_liquidity_trigger(states, total_value)

        assert result.triggered is False


class TestAllTriggers:
    """Tests for evaluating all triggers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = TriggerConfig(
            threshold_enabled=True,
            liquidity_enabled=True,
        )
        self.service = RebalanceTriggerService(config=self.config)

    def test_evaluate_all_triggers(self):
        """Test evaluating all enabled triggers."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("10000"), ratio=Decimal("0.10"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        results = self.service.evaluate_all_triggers(states, total_value)

        assert len(results) == 2
        assert any(r.trigger_type == TriggerType.THRESHOLD for r in results)
        assert any(r.trigger_type == TriggerType.LIQUIDITY for r in results)

    def test_should_rebalance_true(self):
        """Test should_rebalance returns true when triggers fire."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("3000"), ratio=Decimal("0.03"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("37000"), ratio=Decimal("0.37"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        should, reason = self.service.should_rebalance(states, total_value)

        assert should is True
        assert len(reason) > 0

    def test_should_rebalance_false(self):
        """Test should_rebalance returns false when no triggers fire."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("11500"), ratio=Decimal("0.115"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("58500"), ratio=Decimal("0.585"), assets=[]),
        ]
        total_value = Decimal("100000")

        should, reason = self.service.should_rebalance(states, total_value)

        assert should is False


class TestManualTrigger:
    """Tests for manual triggering."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RebalanceTriggerService()

    def test_manual_trigger_creates_plan(self):
        """Test manual trigger creates a plan."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("10000"), ratio=Decimal("0.10"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        plan = self.service.trigger_manual(states, total_value, "Test reason")

        assert plan is not None
        assert plan.trigger_reason == "Test reason"

    def test_manual_trigger_records_history(self):
        """Test manual trigger records history."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("10000"), ratio=Decimal("0.10"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        self.service.trigger_manual(states, total_value)

        history = self.service.get_history(limit=1)
        assert len(history) == 1
        assert history[0].trigger_type == TriggerType.MANUAL
        assert history[0].triggered is True


class TestAutomaticTrigger:
    """Tests for automatic triggering."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RebalanceTriggerService()

    def test_automatic_trigger_when_needed(self):
        """Test automatic trigger creates plan when needed."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("3000"), ratio=Decimal("0.03"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("37000"), ratio=Decimal("0.37"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        plan = self.service.trigger_automatic(states, total_value)

        assert plan is not None

    def test_automatic_trigger_not_needed(self):
        """Test automatic trigger returns None when not needed."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("11500"), ratio=Decimal("0.115"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("58500"), ratio=Decimal("0.585"), assets=[]),
        ]
        total_value = Decimal("100000")

        plan = self.service.trigger_automatic(states, total_value)

        assert plan is None


class TestTriggerHistory:
    """Tests for trigger history tracking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RebalanceTriggerService()

    def test_get_history_empty(self):
        """Test getting empty history."""
        history = self.service.get_history()
        assert history == []

    def test_get_history_with_items(self):
        """Test getting history with items."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("10000"), ratio=Decimal("0.10"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        # Create some history
        self.service.trigger_manual(states, total_value, "Test 1")
        self.service.trigger_manual(states, total_value, "Test 2")

        history = self.service.get_history()
        assert len(history) == 2

    def test_get_history_filter_by_type(self):
        """Test filtering history by trigger type."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("10000"), ratio=Decimal("0.10"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        self.service.trigger_manual(states, total_value)
        self.service.trigger_automatic(states, total_value)

        manual_history = self.service.get_history(trigger_type=TriggerType.MANUAL)
        assert len(manual_history) == 1
        assert manual_history[0].trigger_type == TriggerType.MANUAL

    def test_get_history_limit(self):
        """Test history limit."""
        states = [
            TierState(tier=LiquidityTier.L1, value=Decimal("10000"), ratio=Decimal("0.10"), assets=[]),
            TierState(tier=LiquidityTier.L2, value=Decimal("30000"), ratio=Decimal("0.30"), assets=[]),
            TierState(tier=LiquidityTier.L3, value=Decimal("60000"), ratio=Decimal("0.60"), assets=[]),
        ]
        total_value = Decimal("100000")

        for i in range(5):
            self.service.trigger_manual(states, total_value, f"Test {i}")

        history = self.service.get_history(limit=3)
        assert len(history) == 3


class TestTriggerConfigUpdate:
    """Tests for trigger config updates."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RebalanceTriggerService()

    def test_update_config(self):
        """Test updating trigger configuration."""
        new_config = TriggerConfig(
            threshold_enabled=False,
            deviation_threshold=Decimal("0.05"),
        )

        self.service.update_config(new_config)

        assert self.service.config.threshold_enabled is False
        assert self.service.config.deviation_threshold == Decimal("0.05")
