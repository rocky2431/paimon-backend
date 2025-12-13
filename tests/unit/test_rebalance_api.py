"""Tests for rebalancing API endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.rebalance import (
    ExecutionResult,
    ExecutionStatus,
    LiquidityTier,
    RebalancePlan,
    RebalanceStatus,
    TierState,
)


class TestDeviationEndpoint:
    """Tests for deviation calculation endpoint."""

    def test_calculate_deviation(self):
        """Test calculating deviation."""
        from app.api.v1.endpoints.rebalancing import (
            calculate_deviation,
            TierStateInput,
        )
        import asyncio

        tier_states = [
            TierStateInput(tier=LiquidityTier.L1, value=Decimal("10000")),
            TierStateInput(tier=LiquidityTier.L2, value=Decimal("30000")),
            TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
        ]

        result = asyncio.get_event_loop().run_until_complete(
            calculate_deviation(tier_states, Decimal("100000"))
        )

        assert result.total_value == Decimal("100000")
        assert len(result.deviations) == 3


class TestPreviewEndpoint:
    """Tests for plan preview endpoint."""

    def test_preview_plan(self):
        """Test previewing a plan."""
        from app.api.v1.endpoints.rebalancing import (
            preview_plan,
            PlanPreviewRequest,
            TierStateInput,
        )
        import asyncio

        request = PlanPreviewRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("5000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("35000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
            trigger_reason="Test preview",
        )

        result = asyncio.get_event_loop().run_until_complete(
            preview_plan(request)
        )

        assert result.plan_id.startswith("RBL-")
        assert result.status == RebalanceStatus.DRAFT


class TestManualTriggerEndpoint:
    """Tests for manual trigger endpoint."""

    def test_manual_trigger(self):
        """Test manual trigger."""
        from app.api.v1.endpoints.rebalancing import (
            trigger_manual_rebalance,
            ManualTriggerRequest,
            TierStateInput,
        )
        import asyncio

        request = ManualTriggerRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("10000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("30000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
            reason="Test manual trigger",
        )

        result = asyncio.get_event_loop().run_until_complete(
            trigger_manual_rebalance(request)
        )

        assert result["plan_id"].startswith("RBL-")
        assert result["auto_approved"] is False

    def test_manual_trigger_with_auto_approve(self):
        """Test manual trigger with auto approve."""
        from app.api.v1.endpoints.rebalancing import (
            trigger_manual_rebalance,
            ManualTriggerRequest,
            TierStateInput,
        )
        import asyncio

        request = ManualTriggerRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("10000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("30000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
            auto_approve=True,
        )

        result = asyncio.get_event_loop().run_until_complete(
            trigger_manual_rebalance(request)
        )

        assert result["auto_approved"] is True


class TestEvaluateTriggers:
    """Tests for trigger evaluation endpoint."""

    def test_evaluate_triggers(self):
        """Test evaluating triggers."""
        from app.api.v1.endpoints.rebalancing import (
            evaluate_triggers,
            TriggerEvaluationRequest,
            TierStateInput,
        )
        import asyncio

        request = TriggerEvaluationRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("10000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("30000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
        )

        results = asyncio.get_event_loop().run_until_complete(
            evaluate_triggers(request)
        )

        assert len(results) >= 1


class TestAutomaticTriggerEndpoint:
    """Tests for automatic trigger endpoint."""

    def test_automatic_trigger_not_needed(self):
        """Test automatic trigger when not needed."""
        from app.api.v1.endpoints.rebalancing import (
            trigger_automatic_rebalance,
            TriggerEvaluationRequest,
            TierStateInput,
        )
        import asyncio

        request = TriggerEvaluationRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("11500")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("30000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("58500")),
            ],
            total_value=Decimal("100000"),
        )

        result = asyncio.get_event_loop().run_until_complete(
            trigger_automatic_rebalance(request)
        )

        assert result["triggered"] is False
        assert result["plan_id"] is None

    def test_automatic_trigger_needed(self):
        """Test automatic trigger when needed."""
        from app.api.v1.endpoints.rebalancing import (
            trigger_automatic_rebalance,
            TriggerEvaluationRequest,
            TierStateInput,
        )
        import asyncio

        request = TriggerEvaluationRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("3000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("37000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
        )

        result = asyncio.get_event_loop().run_until_complete(
            trigger_automatic_rebalance(request)
        )

        assert result["triggered"] is True
        assert result["plan_id"] is not None


class TestPlanApprovalEndpoints:
    """Tests for plan approval endpoints."""

    def test_approve_plan(self):
        """Test approving a plan."""
        from app.api.v1.endpoints.rebalancing import (
            preview_plan,
            approve_plan,
            PlanPreviewRequest,
            TierStateInput,
        )
        import asyncio

        # First create a plan
        request = PlanPreviewRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("5000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("35000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
        )
        preview = asyncio.get_event_loop().run_until_complete(preview_plan(request))

        # Approve it
        result = asyncio.get_event_loop().run_until_complete(
            approve_plan(preview.plan_id)
        )

        assert result["status"] == "approved"

    def test_approve_nonexistent_plan(self):
        """Test approving nonexistent plan raises error."""
        from app.api.v1.endpoints.rebalancing import approve_plan
        from fastapi import HTTPException
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                approve_plan("RBL-NOTFOUND")
            )

        assert exc_info.value.status_code == 400

    def test_cancel_plan(self):
        """Test canceling a plan."""
        from app.api.v1.endpoints.rebalancing import (
            preview_plan,
            cancel_plan,
            PlanPreviewRequest,
            TierStateInput,
        )
        import asyncio

        # First create a plan
        request = PlanPreviewRequest(
            tier_states=[
                TierStateInput(tier=LiquidityTier.L1, value=Decimal("5000")),
                TierStateInput(tier=LiquidityTier.L2, value=Decimal("35000")),
                TierStateInput(tier=LiquidityTier.L3, value=Decimal("60000")),
            ],
            total_value=Decimal("100000"),
        )
        preview = asyncio.get_event_loop().run_until_complete(preview_plan(request))

        # Cancel it
        result = asyncio.get_event_loop().run_until_complete(
            cancel_plan(preview.plan_id)
        )

        assert result["status"] == "cancelled"


class TestTriggerHistory:
    """Tests for trigger history endpoint."""

    def test_get_trigger_history(self):
        """Test getting trigger history."""
        from app.api.v1.endpoints.rebalancing import get_trigger_history
        import asyncio

        history = asyncio.get_event_loop().run_until_complete(
            get_trigger_history(limit=100, trigger_type=None, triggered_only=False)
        )

        assert isinstance(history, list)


class TestRebalanceStats:
    """Tests for rebalance stats endpoint."""

    def test_get_stats(self):
        """Test getting rebalance stats."""
        from app.api.v1.endpoints.rebalancing import get_rebalance_stats
        import asyncio

        stats = asyncio.get_event_loop().run_until_complete(get_rebalance_stats())

        assert "total_plans" in stats


class TestTriggerConfigEndpoints:
    """Tests for trigger config endpoints."""

    def test_get_trigger_config(self):
        """Test getting trigger config."""
        from app.api.v1.endpoints.rebalancing import get_trigger_config
        import asyncio

        config = asyncio.get_event_loop().run_until_complete(get_trigger_config())

        assert config is not None
        assert hasattr(config, "threshold_enabled")

    def test_update_trigger_config(self):
        """Test updating trigger config."""
        from app.api.v1.endpoints.rebalancing import (
            update_trigger_config,
            TriggerConfigUpdate,
        )
        import asyncio

        update = TriggerConfigUpdate(
            deviation_threshold=Decimal("0.05"),
        )

        config = asyncio.get_event_loop().run_until_complete(
            update_trigger_config(update)
        )

        assert config.deviation_threshold == Decimal("0.05")


class TestWalletUsageEndpoints:
    """Tests for wallet usage endpoints."""

    def test_get_wallet_usage(self):
        """Test getting wallet usage."""
        from app.api.v1.endpoints.rebalancing import get_wallet_usage
        import asyncio

        usage = asyncio.get_event_loop().run_until_complete(get_wallet_usage())

        assert "HOT" in usage
        assert "WARM" in usage
        assert "COLD" in usage

    def test_reset_wallet_usage(self):
        """Test resetting wallet usage."""
        from app.api.v1.endpoints.rebalancing import reset_wallet_usage
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(reset_wallet_usage())

        assert result["status"] == "reset"
