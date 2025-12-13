"""Notification service for risk alerts."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.risk.notification_schemas import (
    ChannelConfig,
    NotificationChannel,
    NotificationMessage,
    NotificationPriority,
    NotificationRecord,
    NotificationStatus,
    SlackConfig,
    TelegramConfig,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications across channels.

    Features:
    - Multi-channel support (Slack, Telegram, Email, Webhook)
    - Async delivery with retries
    - Delivery tracking and history
    - Channel-specific formatting
    """

    def __init__(self):
        """Initialize notification service."""
        self._channels: dict[NotificationChannel, ChannelConfig] = {}
        self._records: dict[str, NotificationRecord] = {}
        self._pending: list[NotificationMessage] = []
        self._http_client: httpx.AsyncClient | None = None
        self._max_retries = 3

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def configure_channel(self, config: ChannelConfig) -> None:
        """Configure a notification channel.

        Args:
            config: Channel configuration
        """
        self._channels[config.channel] = config
        logger.info(f"Configured notification channel: {config.channel.value}")

    def is_channel_configured(self, channel: NotificationChannel) -> bool:
        """Check if channel is configured.

        Args:
            channel: Channel to check

        Returns:
            True if configured
        """
        config = self._channels.get(channel)
        return config is not None and config.enabled

    async def send_notification(
        self,
        message: NotificationMessage,
    ) -> list[NotificationRecord]:
        """Send notification to all specified channels.

        Args:
            message: Notification message

        Returns:
            List of delivery records
        """
        records = []

        for channel in message.channels:
            record = await self._send_to_channel(message, channel)
            records.append(record)
            self._records[record.record_id] = record

        return records

    async def _send_to_channel(
        self,
        message: NotificationMessage,
        channel: NotificationChannel,
    ) -> NotificationRecord:
        """Send notification to a specific channel.

        Args:
            message: Notification message
            channel: Target channel

        Returns:
            Delivery record
        """
        record_id = f"NTF-{uuid.uuid4().hex[:8].upper()}"
        record = NotificationRecord(
            record_id=record_id,
            message_id=message.message_id,
            channel=channel,
            status=NotificationStatus.PENDING,
        )

        if not self.is_channel_configured(channel):
            # If channel not configured, log it (useful for testing)
            if channel == NotificationChannel.LOG:
                record.status = NotificationStatus.SENT
                record.sent_at = datetime.now(timezone.utc)
                logger.info(
                    f"[ALERT] {message.priority.value}: {message.title} - {message.body}"
                )
            else:
                record.status = NotificationStatus.FAILED
                record.error = f"Channel {channel.value} not configured"
            return record

        try:
            config = self._channels[channel]

            if channel == NotificationChannel.SLACK:
                await self._send_slack(message, config)
            elif channel == NotificationChannel.TELEGRAM:
                await self._send_telegram(message, config)
            elif channel == NotificationChannel.WEBHOOK:
                await self._send_webhook(message, config)
            elif channel == NotificationChannel.LOG:
                self._send_log(message)

            record.status = NotificationStatus.SENT
            record.sent_at = datetime.now(timezone.utc)

        except Exception as e:
            record.status = NotificationStatus.FAILED
            record.error = str(e)
            logger.error(f"Failed to send notification to {channel.value}: {e}")

        return record

    async def _send_slack(
        self,
        message: NotificationMessage,
        config: ChannelConfig,
    ) -> dict[str, Any]:
        """Send notification to Slack.

        Args:
            message: Notification message
            config: Slack configuration

        Returns:
            Slack API response
        """
        slack_config = config
        webhook_url = slack_config.endpoint

        # Build Slack message
        color = self._get_slack_color(message.priority)
        mention = ""

        if isinstance(slack_config, SlackConfig) and slack_config.mention_on_critical:
            if message.priority in [
                NotificationPriority.HIGH,
                NotificationPriority.URGENT,
            ]:
                mention = "<!channel> "

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"{mention}{message.title}",
                    "text": message.body,
                    "fields": [
                        {"title": "Priority", "value": message.priority.value, "short": True},
                        {"title": "Time", "value": message.created_at.isoformat(), "short": True},
                    ],
                    "footer": "Paimon Risk Alert System",
                }
            ]
        }

        client = await self._get_http_client()
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()

        return {"status": "ok"}

    def _get_slack_color(self, priority: NotificationPriority) -> str:
        """Get Slack attachment color based on priority.

        Args:
            priority: Notification priority

        Returns:
            Color hex code
        """
        return {
            NotificationPriority.LOW: "#36a64f",  # Green
            NotificationPriority.MEDIUM: "#f2c744",  # Yellow
            NotificationPriority.HIGH: "#ff6b35",  # Orange
            NotificationPriority.URGENT: "#dc3545",  # Red
        }[priority]

    async def _send_telegram(
        self,
        message: NotificationMessage,
        config: ChannelConfig,
    ) -> dict[str, Any]:
        """Send notification to Telegram.

        Args:
            message: Notification message
            config: Telegram configuration

        Returns:
            Telegram API response
        """
        if not isinstance(config, TelegramConfig):
            raise ValueError("Invalid Telegram configuration")

        # Build Telegram message
        emoji = self._get_priority_emoji(message.priority)
        text = (
            f"{emoji} <b>{message.title}</b>\n\n"
            f"{message.body}\n\n"
            f"<i>Priority: {message.priority.value}</i>\n"
            f"<i>Time: {message.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
        )

        url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
        payload = {
            "chat_id": config.chat_id,
            "text": text,
            "parse_mode": config.parse_mode,
        }

        client = await self._get_http_client()
        response = await client.post(url, json=payload)
        response.raise_for_status()

        return response.json()

    def _get_priority_emoji(self, priority: NotificationPriority) -> str:
        """Get emoji for priority level.

        Args:
            priority: Notification priority

        Returns:
            Emoji string
        """
        return {
            NotificationPriority.LOW: "ℹ️",
            NotificationPriority.MEDIUM: "⚠️",
            NotificationPriority.HIGH: "🔴",
            NotificationPriority.URGENT: "🚨",
        }[priority]

    async def _send_webhook(
        self,
        message: NotificationMessage,
        config: ChannelConfig,
    ) -> dict[str, Any]:
        """Send notification to generic webhook.

        Args:
            message: Notification message
            config: Webhook configuration

        Returns:
            Webhook response
        """
        payload = {
            "message_id": message.message_id,
            "title": message.title,
            "body": message.body,
            "priority": message.priority.value,
            "metadata": message.metadata,
            "created_at": message.created_at.isoformat(),
        }

        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        client = await self._get_http_client()
        response = await client.post(
            config.endpoint,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        return {"status": response.status_code}

    def _send_log(self, message: NotificationMessage) -> None:
        """Log notification (for testing/development).

        Args:
            message: Notification message
        """
        log_level = {
            NotificationPriority.LOW: logging.INFO,
            NotificationPriority.MEDIUM: logging.WARNING,
            NotificationPriority.HIGH: logging.ERROR,
            NotificationPriority.URGENT: logging.CRITICAL,
        }[message.priority]

        logger.log(
            log_level,
            f"[ALERT] {message.title}: {message.body} (Priority: {message.priority.value})",
        )

    async def retry_failed(self, record_id: str) -> NotificationRecord | None:
        """Retry a failed notification.

        Args:
            record_id: Record ID to retry

        Returns:
            Updated record or None
        """
        record = self._records.get(record_id)
        if not record:
            return None

        if record.status != NotificationStatus.FAILED:
            return record

        if record.retry_count >= self._max_retries:
            return record

        record.status = NotificationStatus.RETRYING
        record.retry_count += 1

        # Reconstruct message from record (simplified)
        message = NotificationMessage(
            message_id=record.message_id,
            title="Retry",
            body="",
            priority=NotificationPriority.MEDIUM,
            channels=[record.channel],
            created_at=datetime.now(timezone.utc),
        )

        new_record = await self._send_to_channel(message, record.channel)
        record.status = new_record.status
        record.sent_at = new_record.sent_at
        record.error = new_record.error

        return record

    def get_delivery_records(
        self,
        message_id: str | None = None,
        channel: NotificationChannel | None = None,
        status: NotificationStatus | None = None,
        limit: int = 100,
    ) -> list[NotificationRecord]:
        """Get notification delivery records.

        Args:
            message_id: Filter by message ID
            channel: Filter by channel
            status: Filter by status
            limit: Max records to return

        Returns:
            List of records
        """
        records = list(self._records.values())

        if message_id:
            records = [r for r in records if r.message_id == message_id]

        if channel:
            records = [r for r in records if r.channel == channel]

        if status:
            records = [r for r in records if r.status == status]

        return records[-limit:]

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance
_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get or create notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
