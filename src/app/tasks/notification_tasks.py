"""Notification delivery tasks.

Handles notification delivery to various channels:
- Slack webhooks
- Telegram bot
- Email (future)
"""

import logging
from datetime import datetime
from typing import Any

from app.core.celery_app import celery_app
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import ApprovalRepository, RiskEventRepository
from app.tasks.base import async_task, get_task_logger

logger = get_task_logger("notification_tasks")


@async_task(queue="high")
async def send_approval_notification(
    self,
    ticket_id: str,
    notification_type: str,
) -> dict[str, Any]:
    """Send notification about approval ticket.

    @param ticket_id - Ticket ID
    @param notification_type - Type of notification
    @returns Send result
    """
    logger.info(
        "Sending approval notification",
        extra={"ticket_id": ticket_id, "type": notification_type},
    )

    async with AsyncSessionLocal() as session:
        try:
            approval_repo = ApprovalRepository(session)
            ticket = await approval_repo.get_with_records(ticket_id)

            if not ticket:
                return {"status": "error", "reason": "ticket not found"}

            # Build message based on type
            message = _build_approval_message(ticket, notification_type)

            # Send to channels
            results = await _send_to_channels(
                message=message,
                channels=["slack"],  # TODO: Configure per notification type
                priority="high" if notification_type in ["SLA_WARNING", "TICKET_EXPIRED"] else "normal",
            )

            return {"status": "success", "channels": results}

        except Exception as e:
            logger.exception("Failed to send approval notification")
            return {"status": "error", "reason": str(e)}


@async_task(queue="high")
async def send_risk_alert(
    self,
    event_id: int,
) -> dict[str, Any]:
    """Send risk alert notification.

    @param event_id - Risk event ID
    @returns Send result
    """
    logger.info("Sending risk alert", extra={"event_id": event_id})

    async with AsyncSessionLocal() as session:
        try:
            risk_repo = RiskEventRepository(session)
            event = await risk_repo.get_by_id(event_id)

            if not event:
                return {"status": "error", "reason": "event not found"}

            # Build message
            message = _build_risk_alert_message(event)

            # Determine channels based on severity
            channels = ["slack"]
            if event.severity == "critical":
                channels.append("telegram")

            # Send to channels
            results = await _send_to_channels(
                message=message,
                channels=channels,
                priority="critical" if event.severity == "critical" else "high",
            )

            # Mark as notified
            await risk_repo.mark_notified(event_id, channels=channels)
            await session.commit()

            return {"status": "success", "channels": results}

        except Exception as e:
            logger.exception("Failed to send risk alert")
            return {"status": "error", "reason": str(e)}


@async_task(queue="high")
async def send_unnotified_alerts(self) -> dict[str, Any]:
    """Send all pending risk alerts.

    Scheduled task to ensure no alerts are missed.

    @returns Send results
    """
    logger.info("Checking for unnotified alerts")

    async with AsyncSessionLocal() as session:
        try:
            risk_repo = RiskEventRepository(session)
            unnotified = await risk_repo.get_unnotified()

            if not unnotified:
                return {"status": "success", "sent": 0}

            sent_count = 0
            for event in unnotified:
                try:
                    await send_risk_alert(self=None, event_id=event.id)
                    sent_count += 1
                except Exception as e:
                    logger.error(
                        "Failed to send alert for event",
                        extra={"event_id": event.id, "error": str(e)},
                    )

            return {"status": "success", "sent": sent_count}

        except Exception as e:
            logger.exception("Failed to process unnotified alerts")
            return {"status": "error", "reason": str(e)}


def _build_approval_message(ticket: Any, notification_type: str) -> dict[str, Any]:
    """Build notification message for approval ticket."""
    base_message = {
        "ticket_id": ticket.id,
        "ticket_type": ticket.ticket_type,
        "requester": ticket.requester,
        "amount": str(ticket.amount) if ticket.amount else None,
        "status": ticket.status,
    }

    if notification_type == "NEW_TICKET":
        return {
            **base_message,
            "title": "New Approval Required",
            "text": f"New {ticket.ticket_type} ticket requires approval",
            "urgency": "high",
            "deadline": ticket.sla_deadline.isoformat(),
        }
    elif notification_type == "SLA_WARNING":
        return {
            **base_message,
            "title": "SLA Warning - Approval Deadline Approaching",
            "text": f"Ticket {ticket.id} is approaching SLA deadline",
            "urgency": "critical",
            "deadline": ticket.sla_deadline.isoformat(),
        }
    elif notification_type == "TICKET_EXPIRED":
        return {
            **base_message,
            "title": "Ticket Expired",
            "text": f"Ticket {ticket.id} has expired due to SLA breach",
            "urgency": "critical",
        }
    elif notification_type == "TICKET_RESOLVED":
        return {
            **base_message,
            "title": f"Ticket {ticket.result}",
            "text": f"Ticket {ticket.id} has been {ticket.result.lower()}",
            "urgency": "normal",
        }
    else:
        return {
            **base_message,
            "title": notification_type,
            "text": f"Update for ticket {ticket.id}",
            "urgency": "normal",
        }


def _build_risk_alert_message(event: Any) -> dict[str, Any]:
    """Build notification message for risk event."""
    return {
        "event_id": event.id,
        "event_type": event.event_type,
        "severity": event.severity,
        "metric_name": event.metric_name,
        "title": f"Risk Alert: {event.event_type}",
        "text": event.message,
        "threshold": str(event.threshold_value) if event.threshold_value else None,
        "actual": str(event.actual_value) if event.actual_value else None,
        "urgency": event.severity,
        "timestamp": event.created_at.isoformat(),
    }


async def _send_to_channels(
    message: dict[str, Any],
    channels: list[str],
    priority: str = "normal",
) -> dict[str, Any]:
    """Send message to specified notification channels."""
    results = {}

    for channel in channels:
        try:
            if channel == "slack":
                results["slack"] = await _send_slack(message, priority)
            elif channel == "telegram":
                results["telegram"] = await _send_telegram(message, priority)
            elif channel == "email":
                results["email"] = await _send_email(message, priority)
            else:
                results[channel] = {"status": "skipped", "reason": "unknown channel"}
        except Exception as e:
            results[channel] = {"status": "error", "reason": str(e)}

    return results


async def _send_slack(message: dict[str, Any], priority: str) -> dict[str, Any]:
    """Send message to Slack.

    @param message - Message to send
    @param priority - Message priority
    @returns Send result
    """
    # TODO: Implement actual Slack webhook
    # This is a placeholder
    logger.info(
        "Slack notification (placeholder)",
        extra={"message": message, "priority": priority},
    )
    return {"status": "logged", "channel": "slack"}


async def _send_telegram(message: dict[str, Any], priority: str) -> dict[str, Any]:
    """Send message to Telegram.

    @param message - Message to send
    @param priority - Message priority
    @returns Send result
    """
    # TODO: Implement actual Telegram bot
    # This is a placeholder
    logger.info(
        "Telegram notification (placeholder)",
        extra={"message": message, "priority": priority},
    )
    return {"status": "logged", "channel": "telegram"}


async def _send_email(message: dict[str, Any], priority: str) -> dict[str, Any]:
    """Send message via email.

    @param message - Message to send
    @param priority - Message priority
    @returns Send result
    """
    # TODO: Implement actual email sending
    # This is a placeholder
    logger.info(
        "Email notification (placeholder)",
        extra={"message": message, "priority": priority},
    )
    return {"status": "logged", "channel": "email"}
