"""Notification delivery tasks with real integrations.

Handles notification delivery to various channels:
- Slack webhooks (for team alerts)
- Telegram bot (for critical alerts)
- Email via SMTP (for reports and summaries)
"""

import logging
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import ApprovalRepository, RiskEventRepository
from app.tasks.base import async_task, get_task_logger

logger = get_task_logger("notification_tasks")


# HTTP client for async requests
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


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

            # Determine channels and priority
            is_urgent = notification_type in ["SLA_WARNING", "TICKET_EXPIRED"]
            channels = ["slack"]
            if is_urgent:
                channels.append("telegram")

            # Send to channels
            results = await _send_to_channels(
                message=message,
                channels=channels,
                priority="critical" if is_urgent else "high",
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


@async_task(queue="normal")
async def send_daily_report_email(
    self,
    report_data: dict[str, Any],
    recipients: list[str] | None = None,
) -> dict[str, Any]:
    """Send daily report via email.

    @param report_data - Report data to include
    @param recipients - Override recipients (optional)
    @returns Send result
    """
    logger.info("Sending daily report email")

    settings = get_settings()
    email_recipients = recipients or settings.alert_email_recipients

    if not email_recipients:
        return {"status": "skipped", "reason": "no recipients configured"}

    if not settings.smtp_host:
        return {"status": "skipped", "reason": "SMTP not configured"}

    try:
        subject = f"Paimon Daily Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        html_content = _build_report_email_html(report_data)

        result = await _send_email(
            recipients=email_recipients,
            subject=subject,
            html_content=html_content,
        )

        return {"status": "success", "result": result}

    except Exception as e:
        logger.exception("Failed to send daily report email")
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
            "deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
        }
    elif notification_type == "SLA_WARNING":
        return {
            **base_message,
            "title": "SLA Warning - Approval Deadline Approaching",
            "text": f"Ticket {ticket.id} is approaching SLA deadline",
            "urgency": "critical",
            "deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
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
            "text": f"Ticket {ticket.id} has been {ticket.result.lower() if ticket.result else 'resolved'}",
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
                settings = get_settings()
                if settings.alert_email_recipients:
                    results["email"] = await _send_email(
                        recipients=settings.alert_email_recipients,
                        subject=message.get("title", "Alert"),
                        html_content=_build_alert_email_html(message),
                    )
                else:
                    results["email"] = {"status": "skipped", "reason": "no recipients"}
            else:
                results[channel] = {"status": "skipped", "reason": "unknown channel"}
        except Exception as e:
            logger.error(f"Failed to send to {channel}: {e}")
            results[channel] = {"status": "error", "reason": str(e)}

    return results


async def _send_slack(message: dict[str, Any], priority: str) -> dict[str, Any]:
    """Send message to Slack via webhook.

    @param message - Message to send
    @param priority - Message priority
    @returns Send result
    """
    settings = get_settings()

    if not settings.slack_webhook_url:
        logger.warning("Slack webhook URL not configured, logging instead")
        logger.info(f"[SLACK] {message.get('title')}: {message.get('text')}")
        return {"status": "logged", "reason": "webhook not configured"}

    # Build Slack payload
    color = _get_slack_color(priority)
    mention = ""

    if settings.slack_mention_on_critical and priority in ["critical", "urgent"]:
        mention = "<!channel> "

    title = message.get("title", "Alert")
    text = message.get("text", "")
    urgency = message.get("urgency", "normal")

    fields = [
        {"title": "Priority", "value": urgency.upper(), "short": True},
        {"title": "Time", "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "short": True},
    ]

    # Add optional fields
    if message.get("ticket_id"):
        fields.append({"title": "Ticket ID", "value": message["ticket_id"], "short": True})
    if message.get("amount"):
        fields.append({"title": "Amount", "value": message["amount"], "short": True})
    if message.get("deadline"):
        fields.append({"title": "Deadline", "value": message["deadline"], "short": True})

    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"{mention}{title}",
                "text": text,
                "fields": fields,
                "footer": "Paimon Alert System",
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }
        ]
    }

    # Add channel override if configured
    if settings.slack_channel:
        payload["channel"] = settings.slack_channel

    client = await _get_http_client()
    response = await client.post(settings.slack_webhook_url, json=payload)
    response.raise_for_status()

    logger.info(f"Slack notification sent: {title}")
    return {"status": "sent", "channel": "slack"}


def _get_slack_color(priority: str) -> str:
    """Get Slack attachment color based on priority."""
    return {
        "low": "#36a64f",      # Green
        "normal": "#f2c744",   # Yellow
        "high": "#ff6b35",     # Orange
        "critical": "#dc3545", # Red
        "urgent": "#dc3545",   # Red
    }.get(priority, "#808080")


async def _send_telegram(message: dict[str, Any], priority: str) -> dict[str, Any]:
    """Send message to Telegram via bot.

    @param message - Message to send
    @param priority - Message priority
    @returns Send result
    """
    settings = get_settings()

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured, logging instead")
        logger.info(f"[TELEGRAM] {message.get('title')}: {message.get('text')}")
        return {"status": "logged", "reason": "telegram not configured"}

    # Build Telegram message with HTML formatting
    emoji = _get_priority_emoji(priority)
    title = message.get("title", "Alert")
    text = message.get("text", "")
    urgency = message.get("urgency", "normal")

    telegram_text = (
        f"{emoji} <b>{title}</b>\n\n"
        f"{text}\n\n"
        f"<i>Priority: {urgency.upper()}</i>\n"
        f"<i>Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    )

    # Add optional info
    if message.get("ticket_id"):
        telegram_text += f"\n<i>Ticket: {message['ticket_id']}</i>"
    if message.get("amount"):
        telegram_text += f"\n<i>Amount: {message['amount']}</i>"

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": telegram_text,
        "parse_mode": "HTML",
    }

    client = await _get_http_client()
    response = await client.post(url, json=payload)
    response.raise_for_status()

    logger.info(f"Telegram notification sent: {title}")
    return {"status": "sent", "channel": "telegram"}


def _get_priority_emoji(priority: str) -> str:
    """Get emoji for priority level."""
    return {
        "low": "ℹ️",
        "normal": "⚠️",
        "high": "🔴",
        "critical": "🚨",
        "urgent": "🚨",
    }.get(priority, "📢")


async def _send_email(
    recipients: list[str],
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> dict[str, Any]:
    """Send email via SMTP.

    @param recipients - List of recipient email addresses
    @param subject - Email subject
    @param html_content - HTML email body
    @param text_content - Plain text fallback (optional)
    @returns Send result
    """
    settings = get_settings()

    if not settings.smtp_host or not settings.smtp_from_email:
        logger.warning("SMTP not configured, logging instead")
        logger.info(f"[EMAIL] To: {recipients}, Subject: {subject}")
        return {"status": "logged", "reason": "smtp not configured"}

    # Build email message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = ", ".join(recipients)

    # Add plain text part if provided
    if text_content:
        msg.attach(MIMEText(text_content, "plain"))

    # Add HTML part
    msg.attach(MIMEText(html_content, "html"))

    # Send email (using sync smtp in thread to not block)
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _send_smtp_sync,
        settings,
        recipients,
        msg,
    )

    logger.info(f"Email sent to {len(recipients)} recipients: {subject}")
    return {"status": "sent", "recipients": len(recipients)}


def _send_smtp_sync(settings: Any, recipients: list[str], msg: MIMEMultipart) -> None:
    """Synchronous SMTP send (run in thread pool)."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, recipients, msg.as_string())


def _build_alert_email_html(message: dict[str, Any]) -> str:
    """Build HTML email content for alerts."""
    title = message.get("title", "Alert")
    text = message.get("text", "")
    urgency = message.get("urgency", "normal")

    color = {
        "low": "#36a64f",
        "normal": "#f2c744",
        "high": "#ff6b35",
        "critical": "#dc3545",
        "urgent": "#dc3545",
    }.get(urgency, "#808080")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
            .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 5px 5px; }}
            .info {{ margin-top: 15px; padding: 10px; background: #fff; border-left: 3px solid {color}; }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin: 0;">{title}</h2>
        </div>
        <div class="content">
            <p>{text}</p>
            <div class="info">
                <strong>Priority:</strong> {urgency.upper()}<br>
                <strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
    """

    if message.get("ticket_id"):
        html += f"<br><strong>Ticket ID:</strong> {message['ticket_id']}"
    if message.get("amount"):
        html += f"<br><strong>Amount:</strong> {message['amount']}"
    if message.get("deadline"):
        html += f"<br><strong>Deadline:</strong> {message['deadline']}"

    html += """
            </div>
        </div>
        <div class="footer">
            This is an automated message from Paimon Alert System.
        </div>
    </body>
    </html>
    """

    return html


def _build_report_email_html(report_data: dict[str, Any]) -> str:
    """Build HTML email content for daily report."""
    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #4a90d9; color: white; padding: 15px; }}
            .section {{ margin: 20px 0; padding: 15px; background: #f9f9f9; border-radius: 5px; }}
            .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #fff; border-radius: 5px; text-align: center; }}
            .metric-value {{ font-size: 24px; font-weight: bold; color: #4a90d9; }}
            .metric-label {{ font-size: 12px; color: #666; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f0f0f0; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1 style="margin: 0;">Paimon Daily Report</h1>
            <p style="margin: 5px 0 0 0;">{date_str}</p>
        </div>

        <div class="section">
            <h2>Summary</h2>
            <div class="metric">
                <div class="metric-value">{report_data.get('total_redemptions', 0)}</div>
                <div class="metric-label">Redemptions</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report_data.get('pending_approvals', 0)}</div>
                <div class="metric-label">Pending Approvals</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report_data.get('total_volume', '0')}</div>
                <div class="metric-label">Volume (USDC)</div>
            </div>
        </div>

        <div class="section">
            <h2>Alerts</h2>
            <p>Total alerts today: {report_data.get('alert_count', 0)}</p>
        </div>

        <div class="footer" style="margin-top: 30px; padding: 15px; font-size: 12px; color: #666; border-top: 1px solid #ddd;">
            This is an automated daily report from Paimon Alert System.
        </div>
    </body>
    </html>
    """

    return html
