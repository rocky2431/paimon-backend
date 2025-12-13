"""Rebalancing triggers service."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.services.rebalance.schemas import (
    LiquidityTier,
    RebalancePlan,
    TierState,
)
from app.services.rebalance.strategy import RebalanceStrategyEngine

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    """Type of rebalance trigger."""

    MANUAL = "MANUAL"  # User initiated
    SCHEDULED = "SCHEDULED"  # Time-based
    THRESHOLD = "THRESHOLD"  # Deviation threshold
    LIQUIDITY = "LIQUIDITY"  # L1 level
    EVENT = "EVENT"  # External event


class TriggerConfig(BaseModel):
    """Configuration for triggers."""

    # Scheduled trigger
    schedule_enabled: bool = Field(default=False, description="Enable scheduled")
    schedule_cron: str = Field(default="0 0 * * *", description="Cron expression")

    # Threshold trigger
    threshold_enabled: bool = Field(default=True, description="Enable threshold")
    deviation_threshold: Decimal = Field(
        default=Decimal("0.03"), description="Deviation threshold"
    )

    # Liquidity trigger
    liquidity_enabled: bool = Field(default=True, description="Enable liquidity")
    l1_min_ratio: Decimal = Field(
        default=Decimal("0.08"), description="Min L1 ratio"
    )
    l1_critical_ratio: Decimal = Field(
        default=Decimal("0.05"), description="Critical L1 ratio"
    )

    # Event trigger
    event_enabled: bool = Field(default=False, description="Enable event triggers")


class TriggerResult(BaseModel):
    """Result of trigger evaluation."""

    triggered: bool = Field(..., description="Whether trigger activated")
    trigger_type: TriggerType = Field(..., description="Type of trigger")
    reason: str = Field(..., description="Reason for triggering")
    severity: str = Field(default="normal", description="Severity level")
    details: dict[str, Any] = Field(default_factory=dict, description="Extra details")
    evaluated_at: datetime = Field(..., description="Evaluation timestamp")


class TriggerHistory(BaseModel):
    """History of trigger evaluations."""

    id: str = Field(..., description="History ID")
    trigger_type: TriggerType = Field(..., description="Trigger type")
    triggered: bool = Field(..., description="Whether triggered")
    reason: str = Field(..., description="Reason")
    plan_id: str | None = Field(None, description="Generated plan ID if any")
    evaluated_at: datetime = Field(..., description="Evaluation time")


class RebalanceTriggerService:
    """Service for managing rebalance triggers.

    Features:
    - Multiple trigger types
    - Configurable thresholds
    - Automatic plan generation
    - Trigger history tracking
    """

    def __init__(
        self,
        config: TriggerConfig | None = None,
        strategy_engine: RebalanceStrategyEngine | None = None,
    ):
        """Initialize trigger service.

        Args:
            config: Trigger configuration
            strategy_engine: Strategy engine for plan generation
        """
        self.config = config or TriggerConfig()
        self.strategy_engine = strategy_engine or RebalanceStrategyEngine()
        self._history: list[TriggerHistory] = []
        self._history_id = 0

    def evaluate_threshold_trigger(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
    ) -> TriggerResult:
        """Evaluate threshold-based trigger.

        Args:
            tier_states: Current tier states
            total_value: Total portfolio value

        Returns:
            Trigger result
        """
        deviations = self.strategy_engine.calculate_deviations(tier_states, total_value)
        max_deviation = max(abs(d.deviation) for d in deviations) if deviations else Decimal(0)

        triggered = max_deviation > self.config.deviation_threshold

        return TriggerResult(
            triggered=triggered,
            trigger_type=TriggerType.THRESHOLD,
            reason=f"Max deviation {max_deviation:.2%} {'exceeds' if triggered else 'within'} threshold {self.config.deviation_threshold:.2%}",
            severity="high" if triggered else "normal",
            details={
                "max_deviation": float(max_deviation),
                "threshold": float(self.config.deviation_threshold),
                "deviations": {d.tier.value: float(d.deviation) for d in deviations},
            },
            evaluated_at=datetime.now(timezone.utc),
        )

    def evaluate_liquidity_trigger(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
    ) -> TriggerResult:
        """Evaluate liquidity-based trigger.

        Args:
            tier_states: Current tier states
            total_value: Total portfolio value

        Returns:
            Trigger result
        """
        l1_state = next(
            (s for s in tier_states if s.tier == LiquidityTier.L1), None
        )

        if not l1_state or total_value == 0:
            return TriggerResult(
                triggered=False,
                trigger_type=TriggerType.LIQUIDITY,
                reason="L1 state not found or zero total value",
                evaluated_at=datetime.now(timezone.utc),
            )

        l1_ratio = l1_state.value / total_value

        if l1_ratio < self.config.l1_critical_ratio:
            return TriggerResult(
                triggered=True,
                trigger_type=TriggerType.LIQUIDITY,
                reason=f"L1 ratio {l1_ratio:.2%} is CRITICAL (below {self.config.l1_critical_ratio:.2%})",
                severity="critical",
                details={
                    "l1_ratio": float(l1_ratio),
                    "l1_value": float(l1_state.value),
                    "critical_threshold": float(self.config.l1_critical_ratio),
                },
                evaluated_at=datetime.now(timezone.utc),
            )

        if l1_ratio < self.config.l1_min_ratio:
            return TriggerResult(
                triggered=True,
                trigger_type=TriggerType.LIQUIDITY,
                reason=f"L1 ratio {l1_ratio:.2%} below minimum {self.config.l1_min_ratio:.2%}",
                severity="high",
                details={
                    "l1_ratio": float(l1_ratio),
                    "l1_value": float(l1_state.value),
                    "min_threshold": float(self.config.l1_min_ratio),
                },
                evaluated_at=datetime.now(timezone.utc),
            )

        return TriggerResult(
            triggered=False,
            trigger_type=TriggerType.LIQUIDITY,
            reason=f"L1 ratio {l1_ratio:.2%} is healthy",
            details={"l1_ratio": float(l1_ratio)},
            evaluated_at=datetime.now(timezone.utc),
        )

    def evaluate_all_triggers(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
    ) -> list[TriggerResult]:
        """Evaluate all enabled triggers.

        Args:
            tier_states: Current tier states
            total_value: Total portfolio value

        Returns:
            List of trigger results
        """
        results = []

        if self.config.threshold_enabled:
            results.append(
                self.evaluate_threshold_trigger(tier_states, total_value)
            )

        if self.config.liquidity_enabled:
            results.append(
                self.evaluate_liquidity_trigger(tier_states, total_value)
            )

        return results

    def should_rebalance(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
    ) -> tuple[bool, str]:
        """Check if rebalancing should occur.

        Args:
            tier_states: Current tier states
            total_value: Total portfolio value

        Returns:
            Tuple of (should_rebalance, reason)
        """
        results = self.evaluate_all_triggers(tier_states, total_value)

        triggered_results = [r for r in results if r.triggered]
        if not triggered_results:
            return False, "No triggers activated"

        # Prioritize by severity
        critical = [r for r in triggered_results if r.severity == "critical"]
        if critical:
            return True, critical[0].reason

        high = [r for r in triggered_results if r.severity == "high"]
        if high:
            return True, high[0].reason

        return True, triggered_results[0].reason

    def trigger_manual(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
        reason: str = "Manual trigger",
    ) -> RebalancePlan:
        """Manually trigger rebalancing.

        Args:
            tier_states: Current tier states
            total_value: Total portfolio value
            reason: Trigger reason

        Returns:
            Generated rebalance plan
        """
        plan = self.strategy_engine.generate_rebalance_plan(
            tier_states, total_value, trigger_reason=reason
        )

        self._record_history(
            trigger_type=TriggerType.MANUAL,
            triggered=True,
            reason=reason,
            plan_id=plan.plan_id,
        )

        return plan

    def trigger_automatic(
        self,
        tier_states: list[TierState],
        total_value: Decimal,
    ) -> RebalancePlan | None:
        """Automatically trigger rebalancing if needed.

        Args:
            tier_states: Current tier states
            total_value: Total portfolio value

        Returns:
            Generated plan if triggered, None otherwise
        """
        should_trigger, reason = self.should_rebalance(tier_states, total_value)

        if not should_trigger:
            self._record_history(
                trigger_type=TriggerType.THRESHOLD,
                triggered=False,
                reason=reason,
            )
            return None

        plan = self.strategy_engine.generate_rebalance_plan(
            tier_states, total_value, trigger_reason=reason
        )

        self._record_history(
            trigger_type=TriggerType.THRESHOLD,
            triggered=True,
            reason=reason,
            plan_id=plan.plan_id,
        )

        return plan

    def _record_history(
        self,
        trigger_type: TriggerType,
        triggered: bool,
        reason: str,
        plan_id: str | None = None,
    ) -> None:
        """Record trigger history.

        Args:
            trigger_type: Type of trigger
            triggered: Whether triggered
            reason: Reason
            plan_id: Generated plan ID if any
        """
        self._history_id += 1
        history = TriggerHistory(
            id=f"TRG-{self._history_id:08d}",
            trigger_type=trigger_type,
            triggered=triggered,
            reason=reason,
            plan_id=plan_id,
            evaluated_at=datetime.now(timezone.utc),
        )
        self._history.append(history)

        # Keep only last 1000 entries
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def get_history(
        self,
        limit: int = 100,
        trigger_type: TriggerType | None = None,
        triggered_only: bool = False,
    ) -> list[TriggerHistory]:
        """Get trigger history.

        Args:
            limit: Max entries to return
            trigger_type: Filter by trigger type
            triggered_only: Only return triggered entries

        Returns:
            List of history entries
        """
        result = self._history.copy()

        if trigger_type:
            result = [h for h in result if h.trigger_type == trigger_type]

        if triggered_only:
            result = [h for h in result if h.triggered]

        # Return most recent first
        result.reverse()
        return result[:limit]

    def update_config(self, config: TriggerConfig) -> None:
        """Update trigger configuration.

        Args:
            config: New configuration
        """
        self.config = config
        logger.info(f"Updated trigger config: {config.model_dump()}")


# Singleton instance
_trigger_service: RebalanceTriggerService | None = None


def get_trigger_service() -> RebalanceTriggerService:
    """Get or create trigger service singleton."""
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = RebalanceTriggerService()
    return _trigger_service
