"""Approval workflow tasks.

Handles approval-related background operations:
- Ticket creation
- SLA monitoring and escalation
- Notification triggers
"""

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.celery_app import celery_app
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import ApprovalRepository, RedemptionRepository
from app.tasks.base import async_task, get_task_logger

logger = get_task_logger("approval_tasks")

# SLA configuration per ticket type (from docs/backend/04-approval-workflow.md)
SLA_CONFIG = {
    "REDEMPTION_EMERGENCY": {
        "warning_hours": 3,
        "deadline_hours": 4,
        "required_approvals": 1,
    },
    "REDEMPTION_STANDARD": {
        "warning_hours": 20,
        "deadline_hours": 24,
        "required_approvals": 1,
    },
    "REBALANCE_MEDIUM": {
        "warning_hours": 1.5,
        "deadline_hours": 2,
        "required_approvals": 1,
    },
    "REBALANCE_LARGE": {
        "warning_hours": 3,
        "deadline_hours": 4,
        "required_approvals": 2,  # 2/3 multi-sig
    },
    "DEFAULT": {
        "warning_hours": 20,
        "deadline_hours": 24,
        "required_approvals": 1,
    },
}


@async_task(queue="high")
async def create_approval_ticket(
    self,
    reference_type: str,
    reference_id: str,
    requester: str,
    amount: str,
    ticket_type: str,
    description: str | None = None,
    request_data: dict | None = None,
) -> dict[str, Any]:
    """Create approval ticket for a request.

    @param reference_type - Type of reference (REDEMPTION/REBALANCE)
    @param reference_id - ID of referenced entity
    @param requester - Requester address
    @param amount - Amount requiring approval
    @param ticket_type - Type of ticket for SLA lookup
    @param description - Optional description
    @param request_data - Additional request data
    @returns Created ticket info
    """
    logger.info(
        "Creating approval ticket",
        extra={
            "reference_type": reference_type,
            "reference_id": reference_id,
            "ticket_type": ticket_type,
        },
    )

    async with AsyncSessionLocal() as session:
        try:
            approval_repo = ApprovalRepository(session)

            # Check if ticket already exists
            existing = await approval_repo.get_by_reference(reference_type, reference_id)
            if existing:
                logger.info(
                    "Approval ticket already exists",
                    extra={"ticket_id": existing.id},
                )
                return {"status": "exists", "ticket_id": existing.id}

            # Get SLA config
            sla_config = SLA_CONFIG.get(ticket_type, SLA_CONFIG["DEFAULT"])
            now = datetime.utcnow()

            # Create ticket
            ticket_id = f"APR-{uuid.uuid4().hex[:12].upper()}"
            ticket = await approval_repo.create({
                "id": ticket_id,
                "ticket_type": ticket_type,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "requester": requester.lower(),
                "amount": Decimal(amount) if amount else None,
                "description": description,
                "request_data": request_data,
                "status": "PENDING",
                "required_approvals": sla_config["required_approvals"],
                "current_approvals": 0,
                "current_rejections": 0,
                "sla_warning": now + timedelta(hours=sla_config["warning_hours"]),
                "sla_deadline": now + timedelta(hours=sla_config["deadline_hours"]),
            })

            await session.commit()

            # Update reference status
            if reference_type == "REDEMPTION":
                redemption_repo = RedemptionRepository(session)
                await redemption_repo.update(
                    int(reference_id),
                    {
                        "status": "PENDING_APPROVAL",
                        "approval_ticket_id": ticket_id,
                    },
                )
                await session.commit()

            # Trigger notification
            from app.tasks.notification_tasks import send_approval_notification

            send_approval_notification.delay(
                ticket_id=ticket_id,
                notification_type="NEW_TICKET",
            )

            logger.info(
                "Approval ticket created",
                extra={"ticket_id": ticket_id},
            )

            return {"status": "created", "ticket_id": ticket_id}

        except Exception as e:
            await session.rollback()
            logger.exception("Failed to create approval ticket")
            raise self.retry(exc=e)


@async_task(queue="high")
async def process_approval(
    self,
    ticket_id: str,
    approver: str,
    action: str,
    reason: str | None = None,
    signature: str | None = None,
) -> dict[str, Any]:
    """Process approval or rejection action.

    @param ticket_id - Ticket ID
    @param approver - Approver address
    @param action - APPROVE or REJECT
    @param reason - Optional reason
    @param signature - Optional signature
    @returns Processing result
    """
    logger.info(
        "Processing approval action",
        extra={"ticket_id": ticket_id, "action": action, "approver": approver},
    )

    async with AsyncSessionLocal() as session:
        try:
            from app.repositories import ApprovalRecordRepository

            approval_repo = ApprovalRepository(session)
            record_repo = ApprovalRecordRepository(session)

            # Get ticket
            ticket = await approval_repo.get_by_id(ticket_id)
            if not ticket:
                return {"status": "error", "reason": "ticket not found"}

            if ticket.status not in ["PENDING", "PARTIALLY_APPROVED"]:
                return {"status": "error", "reason": f"invalid status: {ticket.status}"}

            # Check if already acted
            if await record_repo.has_already_acted(ticket_id, approver):
                return {"status": "error", "reason": "already acted"}

            # Create record
            record_id = f"REC-{uuid.uuid4().hex[:12].upper()}"
            await record_repo.create({
                "id": record_id,
                "ticket_id": ticket_id,
                "approver": approver.lower(),
                "action": action,
                "reason": reason,
                "signature": signature,
            })

            # Update ticket counts
            if action == "APPROVE":
                ticket = await approval_repo.add_approval(
                    ticket_id, increment_approvals=True
                )
            else:
                ticket = await approval_repo.add_approval(
                    ticket_id, increment_rejections=True
                )
                # Single rejection = rejected
                await approval_repo.resolve(
                    ticket_id,
                    result="REJECTED",
                    result_reason=reason,
                    resolved_by=approver,
                )

            await session.commit()

            # Update referenced entity
            if ticket.status in ["APPROVED", "REJECTED"]:
                await _update_reference_status(
                    session,
                    ticket.reference_type,
                    ticket.reference_id,
                    ticket.status,
                    approver if ticket.status == "APPROVED" else None,
                    approver if ticket.status == "REJECTED" else None,
                    reason if ticket.status == "REJECTED" else None,
                )

            # Send notification
            from app.tasks.notification_tasks import send_approval_notification

            send_approval_notification.delay(
                ticket_id=ticket_id,
                notification_type="TICKET_RESOLVED" if ticket.status in ["APPROVED", "REJECTED"] else "APPROVAL_RECEIVED",
            )

            return {
                "status": "success",
                "ticket_status": ticket.status,
                "current_approvals": ticket.current_approvals,
            }

        except Exception as e:
            await session.rollback()
            logger.exception("Failed to process approval")
            raise self.retry(exc=e)


async def _update_reference_status(
    session,
    reference_type: str,
    reference_id: str,
    status: str,
    approved_by: str | None,
    rejected_by: str | None,
    rejection_reason: str | None,
) -> None:
    """Update status of referenced entity."""
    if reference_type == "REDEMPTION":
        redemption_repo = RedemptionRepository(session)
        await redemption_repo.update_status(
            int(reference_id),
            status,
            approved_by=approved_by,
            rejected_by=rejected_by,
            rejection_reason=rejection_reason,
        )
        await session.commit()


@async_task(queue="high")
async def check_sla_deadlines(self) -> dict[str, Any]:
    """Check for tickets approaching or past SLA deadlines.

    Scheduled task that runs every minute.

    @returns Check results
    """
    logger.info("Checking SLA deadlines")

    async with AsyncSessionLocal() as session:
        try:
            approval_repo = ApprovalRepository(session)

            # Check for tickets past warning but not yet escalated
            warning_tickets = await approval_repo.get_past_warning()
            for ticket in warning_tickets:
                # Escalate
                await approval_repo.escalate(ticket.id, escalated_to=["admin@paimon.finance"])

                # Send warning notification
                from app.tasks.notification_tasks import send_approval_notification

                send_approval_notification.delay(
                    ticket_id=ticket.id,
                    notification_type="SLA_WARNING",
                )

            await session.commit()

            # Check for expired tickets
            expired_tickets = await approval_repo.get_expired()
            for ticket in expired_tickets:
                # Auto-expire
                await approval_repo.resolve(
                    ticket.id,
                    result="EXPIRED",
                    result_reason="SLA deadline exceeded",
                )

                # Send expiry notification
                from app.tasks.notification_tasks import send_approval_notification

                send_approval_notification.delay(
                    ticket_id=ticket.id,
                    notification_type="TICKET_EXPIRED",
                )

            await session.commit()

            return {
                "status": "success",
                "escalated": len(warning_tickets),
                "expired": len(expired_tickets),
            }

        except Exception as e:
            await session.rollback()
            logger.exception("Failed to check SLA deadlines")
            raise
