"""Event processing tasks.

Handles blockchain event processing in background:
- RedemptionRequested events
- RedemptionSettled events
- Rebalance events
- Other contract events
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.celery_app import celery_app
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import RedemptionRepository, TransactionRepository
from app.tasks.base import async_task, get_task_logger

logger = get_task_logger("event_tasks")


@async_task(queue="critical", max_retries=5)
async def process_redemption_requested(
    self,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Process RedemptionRequested event from blockchain.

    @param event_data - Event data from blockchain
    @returns Processing result
    """
    logger.info(
        "Processing RedemptionRequested event",
        extra={"tx_hash": event_data.get("tx_hash")},
    )

    async with AsyncSessionLocal() as session:
        try:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)

            # Check for duplicate (idempotency)
            tx_hash = event_data["tx_hash"]
            log_index = event_data["log_index"]

            if await tx_repo.exists_tx(tx_hash, log_index):
                logger.info("Event already processed, skipping", extra={"tx_hash": tx_hash})
                return {"status": "skipped", "reason": "duplicate"}

            # Create transaction record
            await tx_repo.create({
                "tx_hash": tx_hash,
                "block_number": event_data["block_number"],
                "log_index": log_index,
                "block_timestamp": datetime.fromisoformat(event_data["block_timestamp"]),
                "event_type": "RedemptionRequested",
                "contract_address": event_data["contract_address"],
                "from_address": event_data.get("owner"),
                "amount": Decimal(str(event_data.get("shares", 0))),
                "raw_data": event_data,
            })

            # Create redemption request
            request_id = Decimal(str(event_data["request_id"]))
            redemption = await redemption_repo.create({
                "request_id": request_id,
                "tx_hash": tx_hash,
                "block_number": event_data["block_number"],
                "log_index": log_index,
                "owner": event_data["owner"].lower(),
                "receiver": event_data["receiver"].lower(),
                "shares": Decimal(str(event_data["shares"])),
                "gross_amount": Decimal(str(event_data["gross_amount"])),
                "locked_nav": Decimal(str(event_data["locked_nav"])),
                "estimated_fee": Decimal(str(event_data["estimated_fee"])),
                "request_time": datetime.fromisoformat(event_data["request_time"]),
                "settlement_time": datetime.fromisoformat(event_data["settlement_time"]),
                "channel": event_data.get("channel", "STANDARD"),
                "status": "PENDING",
                "requires_approval": event_data.get("requires_approval", False),
            })

            await session.commit()

            # Trigger approval workflow if needed
            if redemption.requires_approval:
                from app.tasks.approval_tasks import create_approval_ticket

                create_approval_ticket.delay(
                    reference_type="REDEMPTION",
                    reference_id=str(redemption.id),
                    requester=redemption.owner,
                    amount=str(redemption.gross_amount),
                    ticket_type="REDEMPTION_APPROVAL",
                )

            logger.info(
                "RedemptionRequested processed successfully",
                extra={"redemption_id": redemption.id, "request_id": str(request_id)},
            )

            return {
                "status": "success",
                "redemption_id": redemption.id,
                "request_id": str(request_id),
            }

        except Exception as e:
            await session.rollback()
            logger.exception("Failed to process RedemptionRequested event")
            raise self.retry(exc=e)


@async_task(queue="critical", max_retries=5)
async def process_redemption_settled(
    self,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Process RedemptionSettled event from blockchain.

    @param event_data - Event data from blockchain
    @returns Processing result
    """
    logger.info(
        "Processing RedemptionSettled event",
        extra={"tx_hash": event_data.get("tx_hash")},
    )

    async with AsyncSessionLocal() as session:
        try:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)

            tx_hash = event_data["tx_hash"]
            log_index = event_data["log_index"]

            # Check for duplicate
            if await tx_repo.exists_tx(tx_hash, log_index):
                return {"status": "skipped", "reason": "duplicate"}

            # Create transaction record
            await tx_repo.create({
                "tx_hash": tx_hash,
                "block_number": event_data["block_number"],
                "log_index": log_index,
                "block_timestamp": datetime.fromisoformat(event_data["block_timestamp"]),
                "event_type": "RedemptionSettled",
                "contract_address": event_data["contract_address"],
                "from_address": event_data.get("receiver"),
                "amount": Decimal(str(event_data.get("net_amount", 0))),
                "fee": Decimal(str(event_data.get("actual_fee", 0))),
                "raw_data": event_data,
            })

            # Find and update redemption
            request_id = Decimal(str(event_data["request_id"]))
            redemption = await redemption_repo.get_by_request_id(request_id)

            if redemption:
                await redemption_repo.settle(
                    redemption.id,
                    actual_fee=Decimal(str(event_data["actual_fee"])),
                    net_amount=Decimal(str(event_data["net_amount"])),
                    settlement_tx_hash=tx_hash,
                )

            await session.commit()

            logger.info(
                "RedemptionSettled processed successfully",
                extra={"request_id": str(request_id)},
            )

            return {"status": "success", "request_id": str(request_id)}

        except Exception as e:
            await session.rollback()
            logger.exception("Failed to process RedemptionSettled event")
            raise self.retry(exc=e)


@async_task(queue="critical")
async def check_pending_settlements(self) -> dict[str, Any]:
    """Check for redemptions ready for settlement.

    Scheduled task that runs every 5 minutes.

    @returns Check results
    """
    logger.info("Checking pending settlements")

    async with AsyncSessionLocal() as session:
        try:
            redemption_repo = RedemptionRepository(session)

            # Get approved redemptions past settlement time
            ready = await redemption_repo.get_ready_for_settlement()

            if not ready:
                return {"status": "success", "ready_count": 0}

            logger.info(
                "Found redemptions ready for settlement",
                extra={"count": len(ready)},
            )

            # Trigger settlement for each (in production, this would call contract)
            for redemption in ready:
                # TODO: Call contract to execute settlement
                logger.info(
                    "Redemption ready for settlement",
                    extra={
                        "redemption_id": redemption.id,
                        "request_id": str(redemption.request_id),
                        "amount": str(redemption.gross_amount),
                    },
                )

            return {"status": "success", "ready_count": len(ready)}

        except Exception as e:
            logger.exception("Failed to check pending settlements")
            raise


@celery_app.task(queue="critical")
def process_event(event_type: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """Route event to appropriate handler.

    @param event_type - Type of event
    @param event_data - Event data
    @returns Processing result
    """
    handlers = {
        "RedemptionRequested": process_redemption_requested,
        "RedemptionSettled": process_redemption_settled,
    }

    handler = handlers.get(event_type)
    if handler:
        return handler.delay(event_data)

    logger.warning("No handler for event type", extra={"event_type": event_type})
    return {"status": "skipped", "reason": f"no handler for {event_type}"}
