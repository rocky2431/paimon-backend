"""Notification schemas for risk alerts."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationChannel(str, Enum):
    """Notification channel types."""

    SLACK = "SLACK"
    TELEGRAM = "TELEGRAM"
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"
    LOG = "LOG"  # For testing/development


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "LOW"  # Info level, can be batched
    MEDIUM = "MEDIUM"  # Warning level, send within minutes
    HIGH = "HIGH"  # Critical, send immediately
    URGENT = "URGENT"  # Emergency, multiple channels + escalation


class NotificationStatus(str, Enum):
    """Notification delivery status."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class ChannelConfig(BaseModel):
    """Configuration for a notification channel."""

    channel: NotificationChannel = Field(..., description="Channel type")
    enabled: bool = Field(default=True, description="Is channel enabled")
    endpoint: str = Field(..., description="Channel endpoint (URL/ID)")
    api_key: str | None = Field(default=None, description="API key if required")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra config")


class SlackConfig(ChannelConfig):
    """Slack-specific configuration."""

    channel: NotificationChannel = NotificationChannel.SLACK
    webhook_url: str = Field(..., description="Slack webhook URL")
    channel_name: str = Field(default="#alerts", description="Channel name")
    mention_on_critical: bool = Field(
        default=True, description="Mention @channel on critical"
    )


class TelegramConfig(ChannelConfig):
    """Telegram-specific configuration."""

    channel: NotificationChannel = NotificationChannel.TELEGRAM
    bot_token: str = Field(..., description="Telegram bot token")
    chat_id: str = Field(..., description="Target chat ID")
    parse_mode: str = Field(default="HTML", description="Message parse mode")


class NotificationMessage(BaseModel):
    """Notification message to be sent."""

    message_id: str = Field(..., description="Unique message ID")
    title: str = Field(..., description="Message title")
    body: str = Field(..., description="Message body")
    priority: NotificationPriority = Field(..., description="Priority level")
    channels: list[NotificationChannel] = Field(..., description="Target channels")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra data")
    created_at: datetime = Field(..., description="Creation time")


class NotificationRecord(BaseModel):
    """Record of a sent notification."""

    record_id: str = Field(..., description="Record ID")
    message_id: str = Field(..., description="Source message ID")
    channel: NotificationChannel = Field(..., description="Channel used")
    status: NotificationStatus = Field(..., description="Delivery status")
    sent_at: datetime | None = Field(None, description="Send time")
    error: str | None = Field(None, description="Error if failed")
    retry_count: int = Field(default=0, description="Retry attempts")
    response: dict[str, Any] | None = Field(None, description="Channel response")


class EscalationRule(BaseModel):
    """Rule for alert escalation."""

    rule_id: str = Field(..., description="Rule ID")
    name: str = Field(..., description="Rule name")
    trigger_priority: NotificationPriority = Field(
        ..., description="Priority that triggers"
    )
    escalation_delay_minutes: int = Field(
        default=15, description="Delay before escalation"
    )
    escalation_channels: list[NotificationChannel] = Field(
        ..., description="Channels to add"
    )
    notify_managers: bool = Field(default=True, description="Notify managers")
    trigger_emergency: bool = Field(
        default=False, description="Trigger emergency protocol"
    )


class AlertRoutingConfig(BaseModel):
    """Configuration for alert routing."""

    default_channels: dict[NotificationPriority, list[NotificationChannel]] = Field(
        default_factory=lambda: {
            NotificationPriority.LOW: [NotificationChannel.LOG],
            NotificationPriority.MEDIUM: [
                NotificationChannel.LOG,
                NotificationChannel.SLACK,
            ],
            NotificationPriority.HIGH: [
                NotificationChannel.SLACK,
                NotificationChannel.TELEGRAM,
            ],
            NotificationPriority.URGENT: [
                NotificationChannel.SLACK,
                NotificationChannel.TELEGRAM,
                NotificationChannel.EMAIL,
            ],
        },
        description="Default channels by priority",
    )
    escalation_rules: list[EscalationRule] = Field(
        default_factory=list, description="Escalation rules"
    )
    quiet_hours: tuple[int, int] | None = Field(
        None, description="Quiet hours (start, end) in UTC"
    )
    batch_low_priority: bool = Field(
        default=True, description="Batch low priority alerts"
    )
    batch_interval_minutes: int = Field(default=15, description="Batch interval")


class EmergencyProtocol(BaseModel):
    """Emergency protocol definition."""

    protocol_id: str = Field(..., description="Protocol ID")
    name: str = Field(..., description="Protocol name")
    description: str = Field(..., description="What this protocol does")
    actions: list[str] = Field(..., description="Actions to take")
    notification_list: list[str] = Field(
        ..., description="People/groups to notify"
    )
    auto_execute: bool = Field(
        default=False, description="Auto-execute or require approval"
    )
    cooldown_minutes: int = Field(
        default=60, description="Cooldown before re-trigger"
    )


class EmergencyTrigger(BaseModel):
    """Record of emergency protocol trigger."""

    trigger_id: str = Field(..., description="Trigger ID")
    protocol_id: str = Field(..., description="Protocol ID")
    triggered_by: str = Field(..., description="What triggered it")
    triggered_at: datetime = Field(..., description="Trigger time")
    executed: bool = Field(default=False, description="Was it executed")
    executed_at: datetime | None = Field(None, description="Execution time")
    actions_taken: list[str] = Field(default_factory=list, description="Actions taken")
    resolved_at: datetime | None = Field(None, description="Resolution time")
