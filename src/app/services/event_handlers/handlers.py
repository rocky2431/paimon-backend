"""Concrete event handlers for blockchain events.

All handlers persist events to database and trigger appropriate workflows.
Heavy processing is delegated to Celery tasks for async execution.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.blockchain.events import EventType, ParsedEvent
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import (
    RedemptionRepository,
    ApprovalRepository,
    AssetRepository,
    RebalanceRepository,
    TransactionRepository,
    RiskEventRepository,
    AuditLogRepository,
)
from app.services.event_handlers.dispatcher import EventHandlerBase

logger = logging.getLogger(__name__)

# Approval thresholds from docs/backend/04-approval-workflow.md
APPROVAL_THRESHOLDS = {
    "EMERGENCY": Decimal("30000"),  # >30K USDC requires approval
    "STANDARD": Decimal("100000"),  # >100K USDC requires approval
}


class DepositHandler(EventHandlerBase):
    """Handler for Deposit events.

    Persists deposit transactions and updates fund statistics.
    """

    def __init__(self):
        super().__init__(EventType.DEPOSIT)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle Deposit event with persistence."""
        args = event.args
        logger.info(
            "Processing Deposit event",
            extra={
                "tx_hash": event.tx_hash,
                "sender": args.get("sender"),
                "assets": str(args.get("assets")),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            audit_repo = AuditLogRepository(session)

            # Check for duplicate
            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                logger.debug("Deposit event already processed", extra={"tx_hash": event.tx_hash})
                return

            # Create transaction record
            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "Deposit",
                "contract_address": event.contract_address,
                "from_address": args.get("sender"),
                "to_address": args.get("owner"),
                "amount": Decimal(str(args.get("assets", 0))),
                "shares": Decimal(str(args.get("shares", 0))),
                "raw_data": event.raw_data,
            })

            # Audit log
            await audit_repo.log_action(
                action="DEPOSIT",
                resource_type="FUND",
                resource_id=event.tx_hash,
                actor_address=args.get("sender"),
                new_value={
                    "assets": str(args.get("assets")),
                    "shares": str(args.get("shares")),
                },
            )

            await session.commit()
            logger.info("Deposit event persisted", extra={"tx_hash": event.tx_hash})


class WithdrawHandler(EventHandlerBase):
    """Handler for Withdraw events."""

    def __init__(self):
        super().__init__(EventType.WITHDRAW)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle Withdraw event with persistence."""
        args = event.args
        logger.info(
            "Processing Withdraw event",
            extra={
                "tx_hash": event.tx_hash,
                "sender": args.get("sender"),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "Withdraw",
                "contract_address": event.contract_address,
                "from_address": args.get("sender"),
                "to_address": args.get("receiver"),
                "amount": Decimal(str(args.get("assets", 0))),
                "shares": Decimal(str(args.get("shares", 0))),
                "raw_data": event.raw_data,
            })

            await session.commit()


class RedemptionRequestedHandler(EventHandlerBase):
    """Handler for RedemptionRequested events.

    Creates redemption request in database and triggers approval workflow
    if amount exceeds threshold.
    """

    def __init__(self):
        super().__init__(EventType.REDEMPTION_REQUESTED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle RedemptionRequested event."""
        args = event.args
        request_id = args.get("request_id")
        owner = args.get("owner", "").lower()
        gross_amount = Decimal(str(args.get("gross_amount", 0)))
        channel_code = args.get("channel", 0)

        # Map channel code to string
        channel_map = {0: "STANDARD", 1: "EMERGENCY", 2: "SCHEDULED"}
        channel = channel_map.get(channel_code, "STANDARD")

        logger.info(
            "Processing RedemptionRequested event",
            extra={
                "tx_hash": event.tx_hash,
                "request_id": request_id,
                "owner": owner,
                "gross_amount": str(gross_amount),
                "channel": channel,
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)
            audit_repo = AuditLogRepository(session)

            # Check for duplicate
            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                logger.debug("RedemptionRequested already processed", extra={"tx_hash": event.tx_hash})
                return

            # Determine if approval is required based on threshold
            threshold = APPROVAL_THRESHOLDS.get(channel, APPROVAL_THRESHOLDS["STANDARD"])
            requires_approval = gross_amount > threshold

            # Calculate settlement time based on channel
            # T+7 for standard, T+1 for emergency
            from datetime import timedelta
            settlement_days = 1 if channel == "EMERGENCY" else 7
            settlement_time = event.block_timestamp + timedelta(days=settlement_days)

            # Create transaction record
            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "RedemptionRequested",
                "contract_address": event.contract_address,
                "from_address": owner,
                "amount": gross_amount,
                "shares": Decimal(str(args.get("shares", 0))),
                "raw_data": event.raw_data,
            })

            # Create redemption request
            redemption = await redemption_repo.create({
                "request_id": Decimal(str(request_id)),
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "owner": owner,
                "receiver": args.get("receiver", owner).lower(),
                "shares": Decimal(str(args.get("shares", 0))),
                "gross_amount": gross_amount,
                "locked_nav": Decimal(str(args.get("locked_nav", 0))),
                "estimated_fee": Decimal(str(args.get("estimated_fee", 0))),
                "request_time": event.block_timestamp,
                "settlement_time": settlement_time,
                "channel": channel,
                "status": "PENDING_APPROVAL" if requires_approval else "PENDING",
                "requires_approval": requires_approval,
            })

            # Audit log
            await audit_repo.log_action(
                action="REDEMPTION_REQUESTED",
                resource_type="REDEMPTION",
                resource_id=str(redemption.id),
                actor_address=owner,
                new_value={
                    "request_id": str(request_id),
                    "gross_amount": str(gross_amount),
                    "channel": channel,
                    "requires_approval": requires_approval,
                },
            )

            await session.commit()

            # Trigger approval workflow via Celery task if needed
            if requires_approval:
                from app.tasks.approval_tasks import create_approval_ticket

                ticket_type = f"REDEMPTION_{channel}"
                create_approval_ticket.delay(
                    reference_type="REDEMPTION",
                    reference_id=str(redemption.id),
                    requester=owner,
                    amount=str(gross_amount),
                    ticket_type=ticket_type,
                    description=f"Redemption request for {gross_amount} USDC via {channel} channel",
                )

                logger.info(
                    "Triggered approval workflow for redemption",
                    extra={"redemption_id": redemption.id},
                )

            logger.info(
                "RedemptionRequested event persisted",
                extra={
                    "redemption_id": redemption.id,
                    "requires_approval": requires_approval,
                },
            )


class RedemptionApprovedHandler(EventHandlerBase):
    """Handler for RedemptionApproved events from on-chain."""

    def __init__(self):
        super().__init__(EventType.REDEMPTION_APPROVED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle RedemptionApproved event."""
        args = event.args
        request_id = Decimal(str(args.get("request_id", 0)))
        approver = args.get("approver", "").lower()

        logger.info(
            "Processing RedemptionApproved event",
            extra={
                "tx_hash": event.tx_hash,
                "request_id": str(request_id),
                "approver": approver,
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            # Create transaction record
            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "RedemptionApproved",
                "contract_address": event.contract_address,
                "from_address": approver,
                "raw_data": event.raw_data,
            })

            # Update redemption status
            redemption = await redemption_repo.get_by_request_id(request_id)
            if redemption:
                await redemption_repo.update_status(
                    redemption.id,
                    "APPROVED",
                    approved_by=approver,
                )
                logger.info(
                    "Redemption approved",
                    extra={"redemption_id": redemption.id},
                )

            await session.commit()


class RedemptionRejectedHandler(EventHandlerBase):
    """Handler for RedemptionRejected events from on-chain."""

    def __init__(self):
        super().__init__(EventType.REDEMPTION_REJECTED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle RedemptionRejected event."""
        args = event.args
        request_id = Decimal(str(args.get("request_id", 0)))
        rejector = args.get("rejector", "").lower()
        reason = args.get("reason", "")

        logger.info(
            "Processing RedemptionRejected event",
            extra={
                "tx_hash": event.tx_hash,
                "request_id": str(request_id),
                "reason": reason,
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "RedemptionRejected",
                "contract_address": event.contract_address,
                "from_address": rejector,
                "raw_data": event.raw_data,
            })

            redemption = await redemption_repo.get_by_request_id(request_id)
            if redemption:
                await redemption_repo.update_status(
                    redemption.id,
                    "REJECTED",
                    rejected_by=rejector,
                    rejection_reason=reason,
                )

            await session.commit()


class RedemptionSettledHandler(EventHandlerBase):
    """Handler for RedemptionSettled events."""

    def __init__(self):
        super().__init__(EventType.REDEMPTION_SETTLED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle RedemptionSettled event."""
        args = event.args
        request_id = Decimal(str(args.get("request_id", 0)))
        net_amount = Decimal(str(args.get("net_amount", 0)))
        fee = Decimal(str(args.get("fee", 0)))

        logger.info(
            "Processing RedemptionSettled event",
            extra={
                "tx_hash": event.tx_hash,
                "request_id": str(request_id),
                "net_amount": str(net_amount),
                "fee": str(fee),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)
            audit_repo = AuditLogRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "RedemptionSettled",
                "contract_address": event.contract_address,
                "to_address": args.get("receiver"),
                "amount": net_amount,
                "fee": fee,
                "raw_data": event.raw_data,
            })

            redemption = await redemption_repo.get_by_request_id(request_id)
            if redemption:
                await redemption_repo.settle(
                    redemption.id,
                    actual_fee=fee,
                    net_amount=net_amount,
                    settlement_tx_hash=event.tx_hash,
                )

                await audit_repo.log_action(
                    action="REDEMPTION_SETTLED",
                    resource_type="REDEMPTION",
                    resource_id=str(redemption.id),
                    new_value={
                        "net_amount": str(net_amount),
                        "fee": str(fee),
                        "settlement_tx": event.tx_hash,
                    },
                )

            await session.commit()
            logger.info("RedemptionSettled processed", extra={"request_id": str(request_id)})


class RedemptionCancelledHandler(EventHandlerBase):
    """Handler for RedemptionCancelled events."""

    def __init__(self):
        super().__init__(EventType.REDEMPTION_CANCELLED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle RedemptionCancelled event."""
        args = event.args
        request_id = Decimal(str(args.get("request_id", 0)))

        logger.info(
            "Processing RedemptionCancelled event",
            extra={"tx_hash": event.tx_hash, "request_id": str(request_id)},
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "RedemptionCancelled",
                "contract_address": event.contract_address,
                "raw_data": event.raw_data,
            })

            redemption = await redemption_repo.get_by_request_id(request_id)
            if redemption:
                await redemption_repo.update(redemption.id, {"status": "CANCELLED"})

            await session.commit()


class EmergencyModeChangedHandler(EventHandlerBase):
    """Handler for EmergencyModeChanged events.

    Creates critical alert and updates system state.
    """

    def __init__(self):
        super().__init__(EventType.EMERGENCY_MODE_CHANGED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle EmergencyModeChanged event."""
        args = event.args
        enabled = args.get("enabled", False)
        triggered_by = args.get("triggered_by", "").lower()

        logger.warning(
            "EMERGENCY MODE CHANGED",
            extra={
                "tx_hash": event.tx_hash,
                "enabled": enabled,
                "triggered_by": triggered_by,
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            risk_repo = RiskEventRepository(session)
            audit_repo = AuditLogRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "EmergencyModeChanged",
                "contract_address": event.contract_address,
                "from_address": triggered_by,
                "raw_data": event.raw_data,
            })

            # Create critical risk event
            risk_event = await risk_repo.create_event(
                event_type="EMERGENCY_MODE",
                severity="critical",
                metric_name="emergency_mode",
                message=f"Emergency mode {'ENABLED' if enabled else 'DISABLED'} by {triggered_by}",
                details={"enabled": enabled, "triggered_by": triggered_by},
            )

            await audit_repo.log_action(
                action="EMERGENCY_MODE_CHANGED",
                resource_type="SYSTEM",
                resource_id="emergency_mode",
                actor_address=triggered_by,
                new_value={"enabled": enabled},
            )

            await session.commit()

            # Send critical notification via Celery
            from app.tasks.notification_tasks import send_risk_alert

            send_risk_alert.delay(event_id=risk_event.id)


class AssetAddedHandler(EventHandlerBase):
    """Handler for AssetAdded events."""

    def __init__(self):
        super().__init__(EventType.ASSET_ADDED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle AssetAdded event."""
        args = event.args
        token_address = args.get("token", "").lower()
        tier_code = args.get("tier", 0)
        allocation = Decimal(str(args.get("allocation", 0)))

        tier_map = {0: "L1", 1: "L2", 2: "L3"}
        tier = tier_map.get(tier_code, "L3")

        logger.info(
            "Processing AssetAdded event",
            extra={
                "tx_hash": event.tx_hash,
                "token": token_address,
                "tier": tier,
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            asset_repo = AssetRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "AssetAdded",
                "contract_address": event.contract_address,
                "token_address": token_address,
                "raw_data": event.raw_data,
            })

            # Check if asset already exists
            existing = await asset_repo.get_by_address(token_address)
            if existing:
                # Reactivate if previously removed
                await asset_repo.update(
                    existing.id,
                    {
                        "is_active": True,
                        "tier": tier,
                        "target_allocation": allocation / Decimal("10000"),  # Convert from bps
                        "removed_at": None,
                    },
                )
            else:
                # Create new asset config
                await asset_repo.add_asset(
                    token_address=token_address,
                    token_symbol="UNKNOWN",  # TODO: Fetch from chain
                    tier=tier,
                    target_allocation=allocation / Decimal("10000"),
                    added_tx_hash=event.tx_hash,
                )

            await session.commit()


class AssetRemovedHandler(EventHandlerBase):
    """Handler for AssetRemoved events."""

    def __init__(self):
        super().__init__(EventType.ASSET_REMOVED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle AssetRemoved event."""
        args = event.args
        token_address = args.get("token", "").lower()

        logger.info(
            "Processing AssetRemoved event",
            extra={"tx_hash": event.tx_hash, "token": token_address},
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            asset_repo = AssetRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "AssetRemoved",
                "contract_address": event.contract_address,
                "token_address": token_address,
                "raw_data": event.raw_data,
            })

            await asset_repo.remove_asset(token_address, removed_tx_hash=event.tx_hash)
            await session.commit()


class RebalanceExecutedHandler(EventHandlerBase):
    """Handler for RebalanceExecuted events."""

    def __init__(self):
        super().__init__(EventType.REBALANCE_EXECUTED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle RebalanceExecuted event."""
        args = event.args
        executor = args.get("executor", "").lower()

        logger.info(
            "Processing RebalanceExecuted event",
            extra={"tx_hash": event.tx_hash, "executor": executor},
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            audit_repo = AuditLogRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "RebalanceExecuted",
                "contract_address": event.contract_address,
                "from_address": executor,
                "raw_data": event.raw_data,
            })

            await audit_repo.log_action(
                action="REBALANCE_EXECUTED",
                resource_type="REBALANCE",
                resource_id=event.tx_hash,
                actor_address=executor,
                new_value={"tx_hash": event.tx_hash},
            )

            await session.commit()


# =============================================================================
# v2.0.0 新增事件处理器
# =============================================================================


class VoucherMintedHandler(EventHandlerBase):
    """Handler for VoucherMinted events.

    NFT Voucher 在 settlementDelay > voucherThreshold 时自动铸造。
    对应 04-approval-workflow.md 第10章。
    """

    def __init__(self):
        super().__init__(EventType.VOUCHER_MINTED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle VoucherMinted event."""
        args = event.args
        request_id = Decimal(str(args.get("request_id", 0)))
        token_id = Decimal(str(args.get("token_id", 0)))
        owner = args.get("owner", "").lower()

        logger.info(
            "Processing VoucherMinted event",
            extra={
                "tx_hash": event.tx_hash,
                "request_id": str(request_id),
                "token_id": str(token_id),
                "owner": owner,
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)
            audit_repo = AuditLogRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "VoucherMinted",
                "contract_address": event.contract_address,
                "to_address": owner,
                "raw_data": event.raw_data,
            })

            # Update redemption request with voucher info
            redemption = await redemption_repo.get_by_request_id(request_id)
            if redemption:
                await redemption_repo.update(
                    redemption.id,
                    {
                        "voucher_token_id": token_id,
                        "has_voucher": True,
                    },
                )
                logger.info(
                    "Voucher info updated for redemption",
                    extra={
                        "redemption_id": redemption.id,
                        "token_id": str(token_id),
                    },
                )

            await audit_repo.log_action(
                action="VOUCHER_MINTED",
                resource_type="REDEMPTION",
                resource_id=str(request_id),
                new_value={
                    "token_id": str(token_id),
                    "owner": owner,
                },
            )

            await session.commit()


class NavUpdatedHandler(EventHandlerBase):
    """Handler for NavUpdated events.

    NAV 更新事件用于同步链上价格数据。
    """

    def __init__(self):
        super().__init__(EventType.NAV_UPDATED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle NavUpdated event."""
        args = event.args
        share_price = Decimal(str(args.get("share_price", 0)))
        total_assets = Decimal(str(args.get("total_assets", 0)))
        total_supply = Decimal(str(args.get("total_supply", 0)))

        logger.info(
            "Processing NavUpdated event",
            extra={
                "tx_hash": event.tx_hash,
                "share_price": str(share_price),
                "total_assets": str(total_assets),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "NavUpdated",
                "contract_address": event.contract_address,
                "amount": share_price,
                "raw_data": event.raw_data,
            })

            await session.commit()

            # Trigger metrics update task
            from app.tasks.monitoring_tasks import sync_chain_data

            sync_chain_data.delay()


class PendingApprovalSharesAddedHandler(EventHandlerBase):
    """Handler for PendingApprovalSharesAdded events.

    待审批份额增加 - 用户发起需要审批的赎回请求时触发。
    """

    def __init__(self):
        super().__init__(EventType.PENDING_APPROVAL_SHARES_ADDED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle PendingApprovalSharesAdded event."""
        args = event.args
        owner = args.get("owner", "").lower()
        amount = Decimal(str(args.get("amount", 0)))

        logger.info(
            "Processing PendingApprovalSharesAdded event",
            extra={
                "tx_hash": event.tx_hash,
                "owner": owner,
                "amount": str(amount),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "PendingApprovalSharesAdded",
                "contract_address": event.contract_address,
                "from_address": owner,
                "shares": amount,
                "raw_data": event.raw_data,
            })

            await session.commit()


class PendingApprovalSharesRemovedHandler(EventHandlerBase):
    """Handler for PendingApprovalSharesRemoved events.

    待审批份额移除 - 审批被拒绝或取消时触发。
    """

    def __init__(self):
        super().__init__(EventType.PENDING_APPROVAL_SHARES_REMOVED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle PendingApprovalSharesRemoved event."""
        args = event.args
        owner = args.get("owner", "").lower()
        amount = Decimal(str(args.get("amount", 0)))

        logger.info(
            "Processing PendingApprovalSharesRemoved event",
            extra={
                "tx_hash": event.tx_hash,
                "owner": owner,
                "amount": str(amount),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "PendingApprovalSharesRemoved",
                "contract_address": event.contract_address,
                "from_address": owner,
                "shares": amount,
                "raw_data": event.raw_data,
            })

            await session.commit()


class SettlementWaterfallTriggeredHandler(EventHandlerBase):
    """Handler for SettlementWaterfallTriggered events.

    瀑布清算事件 - 当结算时流动性不足触发自动清算。
    对应 03-risk-control.md 第5章。
    """

    def __init__(self):
        super().__init__(EventType.SETTLEMENT_WATERFALL_TRIGGERED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle SettlementWaterfallTriggered event."""
        args = event.args
        request_id = Decimal(str(args.get("request_id", 0)))
        shortfall = Decimal(str(args.get("shortfall", 0)))
        liquidated = Decimal(str(args.get("liquidated", 0)))

        logger.warning(
            "WATERFALL LIQUIDATION TRIGGERED",
            extra={
                "tx_hash": event.tx_hash,
                "request_id": str(request_id),
                "shortfall": str(shortfall),
                "liquidated": str(liquidated),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)
            redemption_repo = RedemptionRepository(session)
            risk_repo = RiskEventRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "SettlementWaterfallTriggered",
                "contract_address": event.contract_address,
                "amount": liquidated,
                "raw_data": event.raw_data,
            })

            # Update redemption with waterfall info
            redemption = await redemption_repo.get_by_request_id(request_id)
            if redemption:
                await redemption_repo.update(
                    redemption.id,
                    {
                        "waterfall_triggered": True,
                        "waterfall_amount": liquidated,
                    },
                )

            # Create risk event for monitoring
            risk_event = await risk_repo.create_event(
                event_type="WATERFALL_LIQUIDATION",
                severity="warning",
                metric_name="waterfall_liquidation",
                message=f"Waterfall liquidation triggered: shortfall={shortfall}, liquidated={liquidated}",
                details={
                    "request_id": str(request_id),
                    "shortfall": str(shortfall),
                    "liquidated": str(liquidated),
                },
            )

            await session.commit()

            # Send alert
            from app.tasks.notification_tasks import send_risk_alert

            send_risk_alert.delay(event_id=risk_event.id)


class DailyLiabilityAddedHandler(EventHandlerBase):
    """Handler for DailyLiabilityAdded events.

    每日负债记录 - 用于追踪未来 T+7 内的赎回负债。
    对应 03-risk-control.md 第4章。
    """

    def __init__(self):
        super().__init__(EventType.DAILY_LIABILITY_ADDED)

    async def handle(self, event: ParsedEvent) -> None:
        """Handle DailyLiabilityAdded event."""
        args = event.args
        day_index = int(args.get("day_index", 0))
        amount = Decimal(str(args.get("amount", 0)))

        logger.info(
            "Processing DailyLiabilityAdded event",
            extra={
                "tx_hash": event.tx_hash,
                "day_index": day_index,
                "amount": str(amount),
            },
        )

        async with AsyncSessionLocal() as session:
            tx_repo = TransactionRepository(session)

            if await tx_repo.exists_tx(event.tx_hash, event.log_index):
                return

            await tx_repo.create({
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
                "log_index": event.log_index,
                "block_timestamp": event.block_timestamp,
                "event_type": "DailyLiabilityAdded",
                "contract_address": event.contract_address,
                "amount": amount,
                "raw_data": event.raw_data,
            })

            await session.commit()


def register_all_handlers(dispatcher: Any) -> None:
    """Register all event handlers with the dispatcher.

    Args:
        dispatcher: Event dispatcher instance
    """
    # Deposit/Withdraw handlers
    dispatcher.register_handler(EventType.DEPOSIT, DepositHandler())
    dispatcher.register_handler(EventType.WITHDRAW, WithdrawHandler())

    # Redemption handlers (higher priority for critical events)
    dispatcher.register_handler(
        EventType.REDEMPTION_REQUESTED,
        RedemptionRequestedHandler(),
        priority=10,
    )
    dispatcher.register_handler(
        EventType.REDEMPTION_APPROVED,
        RedemptionApprovedHandler(),
        priority=5,
    )
    dispatcher.register_handler(
        EventType.REDEMPTION_REJECTED,
        RedemptionRejectedHandler(),
        priority=5,
    )
    dispatcher.register_handler(
        EventType.REDEMPTION_SETTLED,
        RedemptionSettledHandler(),
        priority=5,
    )
    dispatcher.register_handler(
        EventType.REDEMPTION_CANCELLED,
        RedemptionCancelledHandler(),
    )

    # Emergency handler (highest priority)
    dispatcher.register_handler(
        EventType.EMERGENCY_MODE_CHANGED,
        EmergencyModeChangedHandler(),
        priority=100,
    )

    # Asset handlers
    dispatcher.register_handler(EventType.ASSET_ADDED, AssetAddedHandler())
    dispatcher.register_handler(EventType.ASSET_REMOVED, AssetRemovedHandler())

    # Rebalance handler
    dispatcher.register_handler(
        EventType.REBALANCE_EXECUTED,
        RebalanceExecutedHandler(),
    )

    # =========================================================================
    # v2.0.0 新增事件处理器
    # =========================================================================

    # NFT Voucher handler
    dispatcher.register_handler(
        EventType.VOUCHER_MINTED,
        VoucherMintedHandler(),
        priority=5,
    )

    # NAV update handler
    dispatcher.register_handler(
        EventType.NAV_UPDATED,
        NavUpdatedHandler(),
    )

    # Pending approval shares handlers
    dispatcher.register_handler(
        EventType.PENDING_APPROVAL_SHARES_ADDED,
        PendingApprovalSharesAddedHandler(),
    )
    dispatcher.register_handler(
        EventType.PENDING_APPROVAL_SHARES_REMOVED,
        PendingApprovalSharesRemovedHandler(),
    )

    # Waterfall liquidation handler (high priority for risk monitoring)
    dispatcher.register_handler(
        EventType.SETTLEMENT_WATERFALL_TRIGGERED,
        SettlementWaterfallTriggeredHandler(),
        priority=50,
    )

    # Daily liability handler
    dispatcher.register_handler(
        EventType.DAILY_LIABILITY_ADDED,
        DailyLiabilityAddedHandler(),
    )

    logger.info("Registered all event handlers with persistence (including v2.0.0)")
