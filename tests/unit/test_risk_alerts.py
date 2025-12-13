"""Tests for risk alert system."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.risk import (
    AlertRouter,
    AlertRoutingConfig,
    ChannelConfig,
    EmergencyProtocol,
    EscalationRule,
    NotificationChannel,
    NotificationMessage,
    NotificationPriority,
    NotificationRecord,
    NotificationService,
    NotificationStatus,
    RiskAlert,
    RiskLevel,
    RiskType,
    SlackConfig,
    TelegramConfig,
)


class TestNotificationSchemas:
    """Tests for notification schemas."""

    def test_notification_channel_enum(self):
        """Test notification channel enum values."""
        assert NotificationChannel.SLACK == "SLACK"
        assert NotificationChannel.TELEGRAM == "TELEGRAM"
        assert NotificationChannel.EMAIL == "EMAIL"
        assert NotificationChannel.WEBHOOK == "WEBHOOK"
        assert NotificationChannel.LOG == "LOG"

    def test_notification_priority_enum(self):
        """Test notification priority enum values."""
        assert NotificationPriority.LOW == "LOW"
        assert NotificationPriority.MEDIUM == "MEDIUM"
        assert NotificationPriority.HIGH == "HIGH"
        assert NotificationPriority.URGENT == "URGENT"

    def test_slack_config(self):
        """Test Slack configuration."""
        config = SlackConfig(
            endpoint="https://hooks.slack.com/test",
            webhook_url="https://hooks.slack.com/test",
            channel_name="#risk-alerts",
        )

        assert config.channel == NotificationChannel.SLACK
        assert config.webhook_url == "https://hooks.slack.com/test"
        assert config.mention_on_critical is True

    def test_telegram_config(self):
        """Test Telegram configuration."""
        config = TelegramConfig(
            endpoint="https://api.telegram.org",
            bot_token="123456:ABC",
            chat_id="-1001234567890",
        )

        assert config.channel == NotificationChannel.TELEGRAM
        assert config.bot_token == "123456:ABC"
        assert config.parse_mode == "HTML"

    def test_notification_message(self):
        """Test notification message creation."""
        message = NotificationMessage(
            message_id="MSG-001",
            title="Test Alert",
            body="This is a test",
            priority=NotificationPriority.HIGH,
            channels=[NotificationChannel.SLACK, NotificationChannel.TELEGRAM],
            created_at=datetime.now(timezone.utc),
        )

        assert message.message_id == "MSG-001"
        assert len(message.channels) == 2

    def test_escalation_rule(self):
        """Test escalation rule creation."""
        rule = EscalationRule(
            rule_id="ESC-001",
            name="High to Urgent Escalation",
            trigger_priority=NotificationPriority.HIGH,
            escalation_delay_minutes=15,
            escalation_channels=[NotificationChannel.EMAIL],
            notify_managers=True,
        )

        assert rule.trigger_priority == NotificationPriority.HIGH
        assert rule.escalation_delay_minutes == 15

    def test_emergency_protocol(self):
        """Test emergency protocol creation."""
        protocol = EmergencyProtocol(
            protocol_id="EMRG-001",
            name="Critical Risk Protocol",
            description="Handle critical risk events",
            actions=["Pause subscriptions", "Alert team"],
            notification_list=["ops-team", "management"],
            auto_execute=False,
            cooldown_minutes=60,
        )

        assert protocol.protocol_id == "EMRG-001"
        assert len(protocol.actions) == 2
        assert protocol.cooldown_minutes == 60


class TestNotificationService:
    """Tests for notification service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = NotificationService()

    def test_configure_channel(self):
        """Test configuring a notification channel."""
        config = ChannelConfig(
            channel=NotificationChannel.WEBHOOK,
            endpoint="https://example.com/webhook",
        )

        self.service.configure_channel(config)

        assert self.service.is_channel_configured(NotificationChannel.WEBHOOK)

    def test_channel_not_configured(self):
        """Test unconfigured channel check."""
        assert not self.service.is_channel_configured(NotificationChannel.SLACK)

    @pytest.mark.asyncio
    async def test_send_to_log_channel(self):
        """Test sending notification to LOG channel."""
        message = NotificationMessage(
            message_id="MSG-001",
            title="Test Alert",
            body="Test message body",
            priority=NotificationPriority.MEDIUM,
            channels=[NotificationChannel.LOG],
            created_at=datetime.now(timezone.utc),
        )

        records = await self.service.send_notification(message)

        assert len(records) == 1
        assert records[0].status == NotificationStatus.SENT
        assert records[0].channel == NotificationChannel.LOG

    @pytest.mark.asyncio
    async def test_send_to_unconfigured_channel_fails(self):
        """Test sending to unconfigured channel fails."""
        message = NotificationMessage(
            message_id="MSG-002",
            title="Test Alert",
            body="Test message",
            priority=NotificationPriority.HIGH,
            channels=[NotificationChannel.SLACK],
            created_at=datetime.now(timezone.utc),
        )

        records = await self.service.send_notification(message)

        assert len(records) == 1
        assert records[0].status == NotificationStatus.FAILED
        assert "not configured" in records[0].error

    @pytest.mark.asyncio
    async def test_send_to_multiple_channels(self):
        """Test sending to multiple channels."""
        message = NotificationMessage(
            message_id="MSG-003",
            title="Multi-channel Alert",
            body="Test",
            priority=NotificationPriority.HIGH,
            channels=[
                NotificationChannel.LOG,
                NotificationChannel.SLACK,
                NotificationChannel.TELEGRAM,
            ],
            created_at=datetime.now(timezone.utc),
        )

        records = await self.service.send_notification(message)

        assert len(records) == 3
        # LOG should succeed (no config needed)
        log_record = next(r for r in records if r.channel == NotificationChannel.LOG)
        assert log_record.status == NotificationStatus.SENT

    def test_get_delivery_records(self):
        """Test getting delivery records."""
        # Create some mock records
        record = NotificationRecord(
            record_id="NTF-001",
            message_id="MSG-001",
            channel=NotificationChannel.LOG,
            status=NotificationStatus.SENT,
            sent_at=datetime.now(timezone.utc),
        )
        self.service._records[record.record_id] = record

        records = self.service.get_delivery_records()

        assert len(records) == 1
        assert records[0].record_id == "NTF-001"

    def test_filter_records_by_status(self):
        """Test filtering records by status."""
        # Add sent and failed records
        sent_record = NotificationRecord(
            record_id="NTF-001",
            message_id="MSG-001",
            channel=NotificationChannel.LOG,
            status=NotificationStatus.SENT,
        )
        failed_record = NotificationRecord(
            record_id="NTF-002",
            message_id="MSG-002",
            channel=NotificationChannel.SLACK,
            status=NotificationStatus.FAILED,
            error="Test error",
        )
        self.service._records[sent_record.record_id] = sent_record
        self.service._records[failed_record.record_id] = failed_record

        sent_only = self.service.get_delivery_records(status=NotificationStatus.SENT)
        failed_only = self.service.get_delivery_records(status=NotificationStatus.FAILED)

        assert len(sent_only) == 1
        assert len(failed_only) == 1


class TestAlertRouter:
    """Tests for alert router."""

    def setup_method(self):
        """Set up test fixtures."""
        self.notification_service = NotificationService()
        self.router = AlertRouter(notification_service=self.notification_service)

    def _create_test_alert(
        self,
        level: RiskLevel = RiskLevel.HIGH,
        risk_type: RiskType = RiskType.LIQUIDITY,
    ) -> RiskAlert:
        """Create a test alert."""
        return RiskAlert(
            alert_id="ALR-001",
            risk_type=risk_type,
            level=level,
            title=f"{level.value} Risk Alert",
            message="Test alert message",
            value=Decimal("0.05"),
            threshold=Decimal("0.06"),
            recommendation="Take action",
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_route_low_priority_alert(self):
        """Test routing low priority alert."""
        alert = self._create_test_alert(level=RiskLevel.LOW)

        result = await self.router.route_alert(alert)

        assert result["priority"] == "LOW"
        assert NotificationChannel.LOG.value in result["channels"]

    @pytest.mark.asyncio
    async def test_route_medium_priority_alert(self):
        """Test routing medium priority alert."""
        alert = self._create_test_alert(level=RiskLevel.MEDIUM)

        result = await self.router.route_alert(alert)

        assert result["priority"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_route_high_priority_alert(self):
        """Test routing high priority alert."""
        alert = self._create_test_alert(level=RiskLevel.HIGH)

        result = await self.router.route_alert(alert)

        assert result["priority"] == "HIGH"

    @pytest.mark.asyncio
    async def test_route_critical_triggers_emergency(self):
        """Test critical alert triggers emergency protocol."""
        alert = self._create_test_alert(level=RiskLevel.CRITICAL)

        result = await self.router.route_alert(alert)

        assert result["priority"] == "URGENT"
        assert result["emergency_triggered"] is True

    @pytest.mark.asyncio
    async def test_emergency_cooldown(self):
        """Test emergency protocol cooldown."""
        alert1 = self._create_test_alert(level=RiskLevel.CRITICAL)
        alert1.alert_id = "ALR-001"

        alert2 = self._create_test_alert(level=RiskLevel.CRITICAL)
        alert2.alert_id = "ALR-002"

        # First alert triggers emergency
        result1 = await self.router.route_alert(alert1)
        assert result1["emergency_triggered"] is True

        # Second alert should be on cooldown
        result2 = await self.router.route_alert(alert2)
        assert result2["emergency_triggered"] is False

    def test_register_emergency_protocol(self):
        """Test registering custom emergency protocol."""
        protocol = EmergencyProtocol(
            protocol_id="EMRG-CUSTOM",
            name="Custom Protocol",
            description="Test protocol",
            actions=["Action 1", "Action 2"],
            notification_list=["team"],
        )

        self.router.register_emergency_protocol(protocol)

        assert "EMRG-CUSTOM" in self.router._emergency_protocols

    def test_execute_emergency_protocol(self):
        """Test executing emergency protocol."""
        # First trigger an emergency
        from app.services.risk.notification_schemas import EmergencyTrigger

        trigger = EmergencyTrigger(
            trigger_id="TRG-001",
            protocol_id="EMRG-001",
            triggered_by="ALR-001",
            triggered_at=datetime.now(timezone.utc),
        )
        self.router._emergency_triggers[trigger.trigger_id] = trigger

        result = self.router.execute_emergency_protocol("TRG-001")

        assert result is True
        assert trigger.executed is True
        assert trigger.executed_at is not None

    def test_resolve_emergency(self):
        """Test resolving emergency."""
        from app.services.risk.notification_schemas import EmergencyTrigger

        trigger = EmergencyTrigger(
            trigger_id="TRG-002",
            protocol_id="EMRG-001",
            triggered_by="ALR-002",
            triggered_at=datetime.now(timezone.utc),
            executed=True,
        )
        self.router._emergency_triggers[trigger.trigger_id] = trigger

        result = self.router.resolve_emergency("TRG-002")

        assert result is True
        assert trigger.resolved_at is not None

    def test_get_active_emergencies(self):
        """Test getting active emergencies."""
        from app.services.risk.notification_schemas import EmergencyTrigger

        # Add resolved and unresolved triggers
        resolved = EmergencyTrigger(
            trigger_id="TRG-001",
            protocol_id="EMRG-001",
            triggered_by="ALR-001",
            triggered_at=datetime.now(timezone.utc),
            resolved_at=datetime.now(timezone.utc),
        )
        active = EmergencyTrigger(
            trigger_id="TRG-002",
            protocol_id="EMRG-001",
            triggered_by="ALR-002",
            triggered_at=datetime.now(timezone.utc),
        )

        self.router._emergency_triggers[resolved.trigger_id] = resolved
        self.router._emergency_triggers[active.trigger_id] = active

        active_list = self.router.get_active_emergencies()

        assert len(active_list) == 1
        assert active_list[0].trigger_id == "TRG-002"

    @pytest.mark.asyncio
    async def test_alert_history_tracking(self):
        """Test that alerts are tracked in history."""
        alert = self._create_test_alert(level=RiskLevel.MEDIUM)

        await self.router.route_alert(alert)

        history = self.router.get_alert_history()
        assert len(history) >= 1
        assert history[-1]["alert_id"] == "ALR-001"

    def test_add_escalation_rule(self):
        """Test adding escalation rule."""
        rule = EscalationRule(
            rule_id="ESC-001",
            name="Test Rule",
            trigger_priority=NotificationPriority.HIGH,
            escalation_channels=[NotificationChannel.EMAIL],
        )

        self.router.add_escalation_rule(rule)

        assert len(self.router.config.escalation_rules) >= 1

    def test_update_routing_config(self):
        """Test updating routing configuration."""
        new_config = AlertRoutingConfig(
            batch_low_priority=False,
            batch_interval_minutes=30,
        )

        self.router.update_routing_config(new_config)

        assert self.router.config.batch_low_priority is False
        assert self.router.config.batch_interval_minutes == 30


class TestAlertRoutingConfig:
    """Tests for alert routing configuration."""

    def test_default_channels_by_priority(self):
        """Test default channel configuration."""
        config = AlertRoutingConfig()

        assert NotificationChannel.LOG in config.default_channels[NotificationPriority.LOW]
        assert NotificationChannel.SLACK in config.default_channels[NotificationPriority.MEDIUM]
        assert NotificationChannel.TELEGRAM in config.default_channels[NotificationPriority.HIGH]

    def test_custom_channels_config(self):
        """Test custom channel configuration."""
        config = AlertRoutingConfig(
            default_channels={
                NotificationPriority.LOW: [NotificationChannel.WEBHOOK],
                NotificationPriority.MEDIUM: [NotificationChannel.WEBHOOK],
                NotificationPriority.HIGH: [NotificationChannel.WEBHOOK],
                NotificationPriority.URGENT: [NotificationChannel.WEBHOOK],
            }
        )

        assert config.default_channels[NotificationPriority.HIGH] == [
            NotificationChannel.WEBHOOK
        ]


class TestSlackIntegration:
    """Tests for Slack integration (mock)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = NotificationService()
        self.slack_config = SlackConfig(
            endpoint="https://hooks.slack.com/test",
            webhook_url="https://hooks.slack.com/test",
        )
        self.service.configure_channel(self.slack_config)

    @pytest.mark.asyncio
    async def test_slack_message_format(self):
        """Test Slack message formatting."""
        # Get color for different priorities
        colors = {
            NotificationPriority.LOW: "#36a64f",
            NotificationPriority.MEDIUM: "#f2c744",
            NotificationPriority.HIGH: "#ff6b35",
            NotificationPriority.URGENT: "#dc3545",
        }

        for priority, expected_color in colors.items():
            color = self.service._get_slack_color(priority)
            assert color == expected_color

    @pytest.mark.asyncio
    async def test_slack_send_mock(self):
        """Test Slack send with mock."""
        message = NotificationMessage(
            message_id="MSG-SLACK",
            title="Slack Test",
            body="Test body",
            priority=NotificationPriority.HIGH,
            channels=[NotificationChannel.SLACK],
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(self.service, "_send_slack", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "ok"}
            records = await self.service.send_notification(message)

            # Should have called _send_slack
            mock.assert_called_once()


class TestTelegramIntegration:
    """Tests for Telegram integration (mock)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = NotificationService()

    def test_priority_emoji(self):
        """Test priority emoji mapping."""
        emojis = {
            NotificationPriority.LOW: "ℹ️",
            NotificationPriority.MEDIUM: "⚠️",
            NotificationPriority.HIGH: "🔴",
            NotificationPriority.URGENT: "🚨",
        }

        for priority, expected_emoji in emojis.items():
            emoji = self.service._get_priority_emoji(priority)
            assert emoji == expected_emoji
