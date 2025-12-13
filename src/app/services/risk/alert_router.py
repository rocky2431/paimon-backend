"""Alert routing service for risk alerts."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.risk.notification_schemas import (
    AlertRoutingConfig,
    EmergencyProtocol,
    EmergencyTrigger,
    EscalationRule,
    NotificationChannel,
    NotificationMessage,
    NotificationPriority,
)
from app.services.risk.notification_service import (
    NotificationService,
    get_notification_service,
)
from app.services.risk.schemas import RiskAlert, RiskLevel, RiskType

logger = logging.getLogger(__name__)


class AlertRouter:
    """Service for routing risk alerts to appropriate channels.

    Features:
    - Priority-based channel routing
    - Escalation rules
    - Emergency protocol triggering
    - Alert history tracking
    """

    def __init__(
        self,
        notification_service: NotificationService | None = None,
        config: AlertRoutingConfig | None = None,
    ):
        """Initialize alert router.

        Args:
            notification_service: Notification service instance
            config: Routing configuration
        """
        self.notification_service = notification_service or get_notification_service()
        self.config = config or AlertRoutingConfig()
        self._emergency_protocols: dict[str, EmergencyProtocol] = {}
        self._emergency_triggers: dict[str, EmergencyTrigger] = {}
        self._alert_history: list[dict[str, Any]] = []
        self._last_emergency_trigger: datetime | None = None

        # Register default emergency protocol
        self._register_default_protocol()

    def _register_default_protocol(self) -> None:
        """Register default emergency protocol."""
        default_protocol = EmergencyProtocol(
            protocol_id="EMRG-001",
            name="Critical Risk Emergency",
            description="Auto-triggered on critical risk levels",
            actions=[
                "Pause new subscriptions",
                "Prioritize pending redemptions",
                "Alert operations team",
                "Initiate emergency rebalancing review",
            ],
            notification_list=["ops-team", "risk-team", "management"],
            auto_execute=False,
            cooldown_minutes=60,
        )
        self._emergency_protocols[default_protocol.protocol_id] = default_protocol

    def _risk_level_to_priority(self, level: RiskLevel) -> NotificationPriority:
        """Convert risk level to notification priority.

        Args:
            level: Risk level

        Returns:
            Notification priority
        """
        return {
            RiskLevel.LOW: NotificationPriority.LOW,
            RiskLevel.MEDIUM: NotificationPriority.MEDIUM,
            RiskLevel.HIGH: NotificationPriority.HIGH,
            RiskLevel.CRITICAL: NotificationPriority.URGENT,
        }[level]

    def _get_channels_for_priority(
        self,
        priority: NotificationPriority,
    ) -> list[NotificationChannel]:
        """Get notification channels for a priority level.

        Args:
            priority: Notification priority

        Returns:
            List of channels
        """
        return self.config.default_channels.get(priority, [NotificationChannel.LOG])

    async def route_alert(self, alert: RiskAlert) -> dict[str, Any]:
        """Route a risk alert to appropriate channels.

        Args:
            alert: Risk alert to route

        Returns:
            Routing result with delivery status
        """
        # Determine priority
        priority = self._risk_level_to_priority(alert.level)

        # Get target channels
        channels = self._get_channels_for_priority(priority)

        # Create notification message
        message = NotificationMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            title=alert.title,
            body=self._format_alert_body(alert),
            priority=priority,
            channels=channels,
            metadata={
                "alert_id": alert.alert_id,
                "risk_type": alert.risk_type.value,
                "level": alert.level.value,
                "value": str(alert.value),
                "threshold": str(alert.threshold),
            },
            created_at=datetime.now(timezone.utc),
        )

        # Send notifications
        records = await self.notification_service.send_notification(message)

        # Track in history
        history_entry = {
            "alert_id": alert.alert_id,
            "message_id": message.message_id,
            "priority": priority.value,
            "channels": [c.value for c in channels],
            "delivery_records": [r.record_id for r in records],
            "routed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._alert_history.append(history_entry)

        # Check for emergency protocol trigger
        emergency_triggered = False
        if alert.level == RiskLevel.CRITICAL:
            emergency_triggered = await self._check_emergency_trigger(alert)

        # Check escalation rules
        escalation_applied = self._check_escalation_rules(alert, priority)

        logger.info(
            f"Routed alert {alert.alert_id} to {len(channels)} channels, "
            f"priority={priority.value}, emergency={emergency_triggered}"
        )

        return {
            "message_id": message.message_id,
            "priority": priority.value,
            "channels": [c.value for c in channels],
            "delivery_count": len(records),
            "emergency_triggered": emergency_triggered,
            "escalation_applied": escalation_applied,
        }

    def _format_alert_body(self, alert: RiskAlert) -> str:
        """Format alert body for notification.

        Args:
            alert: Risk alert

        Returns:
            Formatted body text
        """
        return (
            f"{alert.message}\n\n"
            f"Value: {alert.value}\n"
            f"Threshold: {alert.threshold}\n"
            f"Recommendation: {alert.recommendation}"
        )

    async def _check_emergency_trigger(self, alert: RiskAlert) -> bool:
        """Check if emergency protocol should be triggered.

        Args:
            alert: Critical risk alert

        Returns:
            True if emergency was triggered
        """
        # Get default protocol
        protocol = self._emergency_protocols.get("EMRG-001")
        if not protocol:
            return False

        # Check cooldown
        if self._last_emergency_trigger:
            elapsed = (
                datetime.now(timezone.utc) - self._last_emergency_trigger
            ).total_seconds() / 60
            if elapsed < protocol.cooldown_minutes:
                logger.info(
                    f"Emergency protocol on cooldown, {protocol.cooldown_minutes - elapsed:.0f} minutes remaining"
                )
                return False

        # Create trigger record
        trigger = EmergencyTrigger(
            trigger_id=f"TRG-{uuid.uuid4().hex[:8].upper()}",
            protocol_id=protocol.protocol_id,
            triggered_by=alert.alert_id,
            triggered_at=datetime.now(timezone.utc),
            executed=False,
        )

        self._emergency_triggers[trigger.trigger_id] = trigger
        self._last_emergency_trigger = datetime.now(timezone.utc)

        # Send emergency notification
        emergency_message = NotificationMessage(
            message_id=f"EMRG-{uuid.uuid4().hex[:8].upper()}",
            title=f"🚨 EMERGENCY: {protocol.name}",
            body=(
                f"Emergency protocol triggered by: {alert.title}\n\n"
                f"Protocol: {protocol.description}\n\n"
                f"Required actions:\n"
                + "\n".join(f"• {action}" for action in protocol.actions)
                + f"\n\nTrigger ID: {trigger.trigger_id}"
            ),
            priority=NotificationPriority.URGENT,
            channels=[
                NotificationChannel.SLACK,
                NotificationChannel.TELEGRAM,
                NotificationChannel.LOG,
            ],
            metadata={
                "trigger_id": trigger.trigger_id,
                "protocol_id": protocol.protocol_id,
                "alert_id": alert.alert_id,
            },
            created_at=datetime.now(timezone.utc),
        )

        await self.notification_service.send_notification(emergency_message)

        logger.warning(
            f"Emergency protocol triggered: {protocol.name}, trigger_id={trigger.trigger_id}"
        )

        return True

    def _check_escalation_rules(
        self,
        alert: RiskAlert,
        priority: NotificationPriority,
    ) -> bool:
        """Check and apply escalation rules.

        Args:
            alert: Risk alert
            priority: Current priority

        Returns:
            True if escalation was applied
        """
        for rule in self.config.escalation_rules:
            if rule.trigger_priority == priority:
                logger.info(f"Escalation rule {rule.name} matched for alert {alert.alert_id}")
                return True

        return False

    def register_emergency_protocol(self, protocol: EmergencyProtocol) -> None:
        """Register an emergency protocol.

        Args:
            protocol: Emergency protocol definition
        """
        self._emergency_protocols[protocol.protocol_id] = protocol
        logger.info(f"Registered emergency protocol: {protocol.name}")

    def execute_emergency_protocol(self, trigger_id: str) -> bool:
        """Mark emergency protocol as executed.

        Args:
            trigger_id: Trigger ID

        Returns:
            True if executed
        """
        trigger = self._emergency_triggers.get(trigger_id)
        if not trigger:
            return False

        protocol = self._emergency_protocols.get(trigger.protocol_id)
        if not protocol:
            return False

        trigger.executed = True
        trigger.executed_at = datetime.now(timezone.utc)
        trigger.actions_taken = protocol.actions

        logger.info(f"Emergency protocol executed: trigger_id={trigger_id}")
        return True

    def resolve_emergency(self, trigger_id: str) -> bool:
        """Resolve an emergency.

        Args:
            trigger_id: Trigger ID

        Returns:
            True if resolved
        """
        trigger = self._emergency_triggers.get(trigger_id)
        if not trigger:
            return False

        trigger.resolved_at = datetime.now(timezone.utc)
        logger.info(f"Emergency resolved: trigger_id={trigger_id}")
        return True

    def get_active_emergencies(self) -> list[EmergencyTrigger]:
        """Get active (unresolved) emergencies.

        Returns:
            List of active emergency triggers
        """
        return [
            t for t in self._emergency_triggers.values()
            if t.resolved_at is None
        ]

    def get_alert_history(
        self,
        limit: int = 100,
        risk_type: RiskType | None = None,
    ) -> list[dict[str, Any]]:
        """Get alert routing history.

        Args:
            limit: Max entries to return
            risk_type: Filter by risk type

        Returns:
            List of history entries
        """
        history = self._alert_history[-limit:]

        if risk_type:
            history = [
                h for h in history
                if h.get("metadata", {}).get("risk_type") == risk_type.value
            ]

        return history

    def add_escalation_rule(self, rule: EscalationRule) -> None:
        """Add an escalation rule.

        Args:
            rule: Escalation rule to add
        """
        self.config.escalation_rules.append(rule)
        logger.info(f"Added escalation rule: {rule.name}")

    def update_routing_config(self, config: AlertRoutingConfig) -> None:
        """Update routing configuration.

        Args:
            config: New configuration
        """
        self.config = config
        logger.info("Alert routing configuration updated")


# Singleton instance
_alert_router: AlertRouter | None = None


def get_alert_router() -> AlertRouter:
    """Get or create alert router singleton."""
    global _alert_router
    if _alert_router is None:
        _alert_router = AlertRouter()
    return _alert_router
