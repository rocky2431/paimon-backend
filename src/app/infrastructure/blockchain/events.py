"""Event parsing and handling for blockchain events."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from eth_abi import decode
from eth_utils import event_abi_to_log_topic
from web3 import Web3

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Supported event types.

    Updated for v2.0.0 contracts (PPT.sol, RedemptionManager.sol).
    """

    # =========================================================================
    # ERC-4626 Vault Core Events
    # =========================================================================
    DEPOSIT = "Deposit"
    WITHDRAW = "Withdraw"

    # =========================================================================
    # Redemption Events (RedemptionManager.sol)
    # =========================================================================
    REDEMPTION_REQUESTED = "RedemptionRequested"
    REDEMPTION_APPROVED = "RedemptionApproved"
    REDEMPTION_REJECTED = "RedemptionRejected"
    REDEMPTION_SETTLED = "RedemptionSettled"
    REDEMPTION_CANCELLED = "RedemptionCancelled"  # Note: Disabled in v2.0.0

    # =========================================================================
    # PPT.sol Share Events (v2.0.0)
    # =========================================================================
    SHARES_LOCKED = "SharesLocked"
    SHARES_UNLOCKED = "SharesUnlocked"
    SHARES_BURNED = "SharesBurned"

    # =========================================================================
    # PPT.sol Fee Events (v2.0.0)
    # =========================================================================
    REDEMPTION_FEE_ADDED = "RedemptionFeeAdded"
    REDEMPTION_FEE_REDUCED = "RedemptionFeeReduced"

    # =========================================================================
    # PPT.sol NAV Events (v2.0.0)
    # =========================================================================
    NAV_UPDATED = "NavUpdated"

    # =========================================================================
    # PPT.sol Emergency/Quota Events (v2.0.0)
    # =========================================================================
    EMERGENCY_MODE_CHANGED = "EmergencyModeChanged"
    EMERGENCY_QUOTA_REFRESHED = "EmergencyQuotaRefreshed"
    EMERGENCY_QUOTA_RESTORED = "EmergencyQuotaRestored"
    LOCKED_MINT_ASSETS_RESET = "LockedMintAssetsReset"
    STANDARD_QUOTA_RATIO_UPDATED = "StandardQuotaRatioUpdated"

    # =========================================================================
    # PPT.sol Pending Approval Events (v2.0.0)
    # =========================================================================
    PENDING_APPROVAL_SHARES_ADDED = "PendingApprovalSharesAdded"
    PENDING_APPROVAL_SHARES_REMOVED = "PendingApprovalSharesRemoved"
    PENDING_APPROVAL_SHARES_CONVERTED = "PendingApprovalSharesConverted"

    # =========================================================================
    # PPT.sol Admin Events (v2.0.0)
    # =========================================================================
    ASSET_CONTROLLER_UPDATED = "AssetControllerUpdated"
    REDEMPTION_MANAGER_UPDATED = "RedemptionManagerUpdated"

    # =========================================================================
    # RedemptionManager.sol NFT Voucher Events (v2.0.0)
    # =========================================================================
    VOUCHER_MINTED = "VoucherMinted"
    VOUCHER_SETTLED = "VoucherSettled"

    # =========================================================================
    # RedemptionManager.sol Liability Events (v2.0.0)
    # =========================================================================
    DAILY_LIABILITY_ADDED = "DailyLiabilityAdded"
    LIABILITY_REMOVED = "LiabilityRemoved"
    SETTLEMENT_WATERFALL_TRIGGERED = "SettlementWaterfallTriggered"

    # =========================================================================
    # RedemptionManager.sol Config Events (v2.0.0)
    # =========================================================================
    BASE_REDEMPTION_FEE_UPDATED = "BaseRedemptionFeeUpdated"
    EMERGENCY_PENALTY_FEE_UPDATED = "EmergencyPenaltyFeeUpdated"
    VOUCHER_THRESHOLD_UPDATED = "VoucherThresholdUpdated"

    # =========================================================================
    # Asset Management Events
    # =========================================================================
    ASSET_ADDED = "AssetAdded"
    ASSET_REMOVED = "AssetRemoved"

    # =========================================================================
    # Rebalancing Events
    # =========================================================================
    REBALANCE_EXECUTED = "RebalanceExecuted"

    # =========================================================================
    # Risk Alert Events (Backend-generated)
    # =========================================================================
    LOW_LIQUIDITY_ALERT = "LowLiquidityAlert"
    CRITICAL_LIQUIDITY_ALERT = "CriticalLiquidityAlert"


# Event signatures (keccak256 hash of event signature)
# Updated for v2.0.0 contracts with correct parameter types
EVENT_SIGNATURES = {
    # =========================================================================
    # ERC-4626 Core Events
    # =========================================================================
    EventType.DEPOSIT: "Deposit(address,address,uint256,uint256)",
    EventType.WITHDRAW: "Withdraw(address,address,address,uint256,uint256)",

    # =========================================================================
    # Redemption Events - v2.0.0 signatures
    # RedemptionRequested has 10 params in v2.0.0
    # =========================================================================
    EventType.REDEMPTION_REQUESTED: (
        "RedemptionRequested(uint256,address,address,uint256,uint256,"
        "uint256,uint8,bool,uint256,uint256)"
    ),
    EventType.REDEMPTION_APPROVED: "RedemptionApproved(uint256,address,uint256)",
    EventType.REDEMPTION_REJECTED: "RedemptionRejected(uint256,address,string)",
    EventType.REDEMPTION_SETTLED: "RedemptionSettled(uint256,address,uint256,uint256)",
    EventType.REDEMPTION_CANCELLED: "RedemptionCancelled(uint256,address)",

    # =========================================================================
    # PPT.sol Share Events
    # =========================================================================
    EventType.SHARES_LOCKED: "SharesLocked(address,uint256,uint256)",
    EventType.SHARES_UNLOCKED: "SharesUnlocked(address,uint256)",
    EventType.SHARES_BURNED: "SharesBurned(address,uint256)",

    # =========================================================================
    # PPT.sol Fee Events
    # =========================================================================
    EventType.REDEMPTION_FEE_ADDED: "RedemptionFeeAdded(uint256)",
    EventType.REDEMPTION_FEE_REDUCED: "RedemptionFeeReduced(uint256)",

    # =========================================================================
    # PPT.sol NAV Events
    # =========================================================================
    EventType.NAV_UPDATED: "NavUpdated(uint256,uint256,uint256)",

    # =========================================================================
    # PPT.sol Emergency/Quota Events
    # =========================================================================
    EventType.EMERGENCY_MODE_CHANGED: "EmergencyModeChanged(bool,address)",
    EventType.EMERGENCY_QUOTA_REFRESHED: "EmergencyQuotaRefreshed(uint256)",
    EventType.EMERGENCY_QUOTA_RESTORED: "EmergencyQuotaRestored(uint256)",
    EventType.LOCKED_MINT_ASSETS_RESET: "LockedMintAssetsReset(uint256)",
    EventType.STANDARD_QUOTA_RATIO_UPDATED: "StandardQuotaRatioUpdated(uint256,uint256)",

    # =========================================================================
    # PPT.sol Pending Approval Events
    # =========================================================================
    EventType.PENDING_APPROVAL_SHARES_ADDED: "PendingApprovalSharesAdded(address,uint256)",
    EventType.PENDING_APPROVAL_SHARES_REMOVED: "PendingApprovalSharesRemoved(address,uint256)",
    EventType.PENDING_APPROVAL_SHARES_CONVERTED: "PendingApprovalSharesConverted(address,uint256)",

    # =========================================================================
    # PPT.sol Admin Events
    # =========================================================================
    EventType.ASSET_CONTROLLER_UPDATED: "AssetControllerUpdated(address,address)",
    EventType.REDEMPTION_MANAGER_UPDATED: "RedemptionManagerUpdated(address,address)",

    # =========================================================================
    # RedemptionManager.sol NFT Voucher Events
    # =========================================================================
    EventType.VOUCHER_MINTED: "VoucherMinted(uint256,uint256,address)",
    EventType.VOUCHER_SETTLED: "VoucherSettled(uint256,uint256,address,uint256)",

    # =========================================================================
    # RedemptionManager.sol Liability Events
    # =========================================================================
    EventType.DAILY_LIABILITY_ADDED: "DailyLiabilityAdded(uint256,uint256)",
    EventType.LIABILITY_REMOVED: "LiabilityRemoved(uint256,uint256)",
    EventType.SETTLEMENT_WATERFALL_TRIGGERED: "SettlementWaterfallTriggered(uint256,uint256,uint256)",

    # =========================================================================
    # RedemptionManager.sol Config Events
    # =========================================================================
    EventType.BASE_REDEMPTION_FEE_UPDATED: "BaseRedemptionFeeUpdated(uint256,uint256)",
    EventType.EMERGENCY_PENALTY_FEE_UPDATED: "EmergencyPenaltyFeeUpdated(uint256,uint256)",
    EventType.VOUCHER_THRESHOLD_UPDATED: "VoucherThresholdUpdated(uint256,uint256)",

    # =========================================================================
    # Asset Management Events
    # =========================================================================
    EventType.ASSET_ADDED: "AssetAdded(address,uint8,uint256)",
    EventType.ASSET_REMOVED: "AssetRemoved(address)",

    # =========================================================================
    # Rebalancing Events
    # =========================================================================
    EventType.REBALANCE_EXECUTED: "RebalanceExecuted(address,uint256)",
}


@dataclass
class ParsedEvent:
    """Parsed blockchain event."""

    event_type: EventType
    tx_hash: str
    block_number: int
    log_index: int
    block_timestamp: datetime
    contract_address: str
    args: dict[str, Any]
    raw_data: dict[str, Any]


class EventParser:
    """Parses blockchain event logs."""

    def __init__(self):
        """Initialize event parser."""
        self.w3 = Web3()
        self._build_topic_map()

    def _build_topic_map(self) -> None:
        """Build mapping from topic hash to event type."""
        self.topic_to_event: dict[str, EventType] = {}
        for event_type, signature in EVENT_SIGNATURES.items():
            topic = self.w3.keccak(text=signature).hex()
            self.topic_to_event[topic] = event_type

    def parse_log(
        self, log: dict[str, Any], block_timestamp: int | None = None
    ) -> ParsedEvent | None:
        """Parse a single log entry.

        Args:
            log: Raw log entry from eth_getLogs
            block_timestamp: Block timestamp (if known)

        Returns:
            ParsedEvent or None if not recognized
        """
        topics = log.get("topics", [])
        if not topics:
            return None

        # Get event type from topic
        topic0 = topics[0].hex() if hasattr(topics[0], "hex") else topics[0]
        event_type = self.topic_to_event.get(topic0)

        if not event_type:
            logger.debug(f"Unknown event topic: {topic0}")
            return None

        # Parse event arguments
        try:
            args = self._decode_event_args(event_type, log)
        except Exception as e:
            logger.error(f"Failed to decode event {event_type}: {e}")
            return None

        # Build parsed event
        tx_hash = log.get("transactionHash", b"")
        if hasattr(tx_hash, "hex"):
            tx_hash = tx_hash.hex()

        address = log.get("address", "")
        if hasattr(address, "lower"):
            address = address.lower()

        timestamp = (
            datetime.fromtimestamp(block_timestamp, tz=timezone.utc)
            if block_timestamp
            else datetime.now(timezone.utc)
        )

        return ParsedEvent(
            event_type=event_type,
            tx_hash=tx_hash,
            block_number=log.get("blockNumber", 0),
            log_index=log.get("logIndex", 0),
            block_timestamp=timestamp,
            contract_address=address,
            args=args,
            raw_data=log,
        )

    def _decode_event_args(
        self, event_type: EventType, log: dict[str, Any]
    ) -> dict[str, Any]:
        """Decode event arguments based on event type.

        Args:
            event_type: Type of event
            log: Raw log entry

        Returns:
            Dictionary of decoded arguments
        """
        topics = log.get("topics", [])
        data = log.get("data", b"")

        if isinstance(data, str):
            data = bytes.fromhex(data[2:] if data.startswith("0x") else data)

        if event_type == EventType.DEPOSIT:
            return self._decode_deposit(topics, data)
        elif event_type == EventType.REDEMPTION_REQUESTED:
            return self._decode_redemption_requested(topics, data)
        elif event_type == EventType.REDEMPTION_APPROVED:
            return self._decode_redemption_approved(topics, data)
        elif event_type == EventType.REDEMPTION_SETTLED:
            return self._decode_redemption_settled(topics, data)
        elif event_type == EventType.EMERGENCY_MODE_CHANGED:
            return self._decode_emergency_mode_changed(topics, data)
        elif event_type == EventType.VOUCHER_MINTED:
            return self._decode_voucher_minted(topics, data)
        elif event_type == EventType.NAV_UPDATED:
            return self._decode_nav_updated(topics, data)
        elif event_type == EventType.PENDING_APPROVAL_SHARES_ADDED:
            return self._decode_pending_approval_shares(topics, data)
        elif event_type == EventType.PENDING_APPROVAL_SHARES_REMOVED:
            return self._decode_pending_approval_shares(topics, data)
        elif event_type == EventType.SETTLEMENT_WATERFALL_TRIGGERED:
            return self._decode_waterfall_triggered(topics, data)
        elif event_type == EventType.DAILY_LIABILITY_ADDED:
            return self._decode_daily_liability(topics, data)
        else:
            # Generic decode for other events
            return {"raw_topics": topics, "raw_data": data.hex() if data else ""}

    def _decode_deposit(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode Deposit event."""
        # Deposit(address indexed sender, address indexed owner, uint256 assets, uint256 shares)
        sender = self._decode_address(topics[1]) if len(topics) > 1 else None
        owner = self._decode_address(topics[2]) if len(topics) > 2 else None

        # Decode non-indexed args from data
        if data:
            decoded = decode(["uint256", "uint256"], data)
            assets, shares = decoded
        else:
            assets, shares = 0, 0

        return {
            "sender": sender,
            "owner": owner,
            "assets": assets,
            "shares": shares,
        }

    def _decode_redemption_requested(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode RedemptionRequested event.

        v2.0.0 signature:
        RedemptionRequested(
            uint256 indexed requestId,
            address indexed owner,
            address receiver,
            uint256 shares,
            uint256 lockedAmount,
            uint256 estimatedFee,
            uint8 channel,
            bool requiresApproval,
            uint256 settlementTime,
            uint256 windowId
        )
        """
        request_id = int(topics[1].hex(), 16) if len(topics) > 1 else 0
        owner = self._decode_address(topics[2]) if len(topics) > 2 else None

        if data:
            decoded = decode(
                ["address", "uint256", "uint256", "uint256", "uint8", "bool", "uint256", "uint256"],
                data,
            )
            (
                receiver,
                shares,
                locked_amount,
                estimated_fee,
                channel,
                requires_approval,
                settlement_time,
                window_id,
            ) = decoded
        else:
            receiver = None
            shares = 0
            locked_amount = 0
            estimated_fee = 0
            channel = 0
            requires_approval = False
            settlement_time = 0
            window_id = 0

        return {
            "request_id": request_id,
            "owner": owner,
            "receiver": receiver,
            "shares": shares,
            "locked_amount": locked_amount,
            "estimated_fee": estimated_fee,
            "channel": channel,
            "requires_approval": requires_approval,
            "settlement_time": settlement_time,
            "window_id": window_id,
        }

    def _decode_redemption_settled(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode RedemptionSettled event."""
        # RedemptionSettled(uint256 indexed requestId, address indexed receiver, uint256 netAmount, uint256 fee)
        request_id = int(topics[1].hex(), 16) if len(topics) > 1 else 0
        receiver = self._decode_address(topics[2]) if len(topics) > 2 else None

        if data:
            decoded = decode(["uint256", "uint256"], data)
            net_amount, fee = decoded
        else:
            net_amount, fee = 0, 0

        return {
            "request_id": request_id,
            "receiver": receiver,
            "net_amount": net_amount,
            "fee": fee,
        }

    def _decode_emergency_mode_changed(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode EmergencyModeChanged event."""
        # EmergencyModeChanged(bool enabled, address triggeredBy)
        if data:
            decoded = decode(["bool", "address"], data)
            enabled, triggered_by = decoded
        else:
            enabled, triggered_by = False, None

        return {
            "enabled": enabled,
            "triggered_by": triggered_by,
        }

    def _decode_redemption_approved(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode RedemptionApproved event.

        v2.0.0: RedemptionApproved(uint256 indexed requestId, address indexed approver, uint256 settlementTime)
        """
        request_id = int(topics[1].hex(), 16) if len(topics) > 1 else 0
        approver = self._decode_address(topics[2]) if len(topics) > 2 else None

        if data:
            decoded = decode(["uint256"], data)
            settlement_time = decoded[0]
        else:
            settlement_time = 0

        return {
            "request_id": request_id,
            "approver": approver,
            "settlement_time": settlement_time,
        }

    def _decode_voucher_minted(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode VoucherMinted event.

        VoucherMinted(uint256 indexed requestId, uint256 tokenId, address owner)
        """
        request_id = int(topics[1].hex(), 16) if len(topics) > 1 else 0

        if data:
            decoded = decode(["uint256", "address"], data)
            token_id, owner = decoded
        else:
            token_id, owner = 0, None

        return {
            "request_id": request_id,
            "token_id": token_id,
            "owner": owner,
        }

    def _decode_nav_updated(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode NavUpdated event.

        NavUpdated(uint256 newSharePrice, uint256 totalAssets, uint256 totalSupply)
        """
        if data:
            decoded = decode(["uint256", "uint256", "uint256"], data)
            share_price, total_assets, total_supply = decoded
        else:
            share_price, total_assets, total_supply = 0, 0, 0

        return {
            "share_price": share_price,
            "total_assets": total_assets,
            "total_supply": total_supply,
        }

    def _decode_pending_approval_shares(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode PendingApprovalShares events.

        PendingApprovalSharesAdded/Removed(address indexed owner, uint256 amount)
        """
        owner = self._decode_address(topics[1]) if len(topics) > 1 else None

        if data:
            decoded = decode(["uint256"], data)
            amount = decoded[0]
        else:
            amount = 0

        return {
            "owner": owner,
            "amount": amount,
        }

    def _decode_waterfall_triggered(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode SettlementWaterfallTriggered event.

        SettlementWaterfallTriggered(uint256 indexed requestId, uint256 shortfall, uint256 liquidated)
        """
        request_id = int(topics[1].hex(), 16) if len(topics) > 1 else 0

        if data:
            decoded = decode(["uint256", "uint256"], data)
            shortfall, liquidated = decoded
        else:
            shortfall, liquidated = 0, 0

        return {
            "request_id": request_id,
            "shortfall": shortfall,
            "liquidated": liquidated,
        }

    def _decode_daily_liability(
        self, topics: list, data: bytes
    ) -> dict[str, Any]:
        """Decode DailyLiabilityAdded event.

        DailyLiabilityAdded(uint256 dayIndex, uint256 amount)
        """
        if data:
            decoded = decode(["uint256", "uint256"], data)
            day_index, amount = decoded
        else:
            day_index, amount = 0, 0

        return {
            "day_index": day_index,
            "amount": amount,
        }

    def _decode_address(self, topic: Any) -> str:
        """Decode address from indexed topic."""
        if hasattr(topic, "hex"):
            hex_str = topic.hex()
        else:
            hex_str = topic

        # Address is last 40 characters (20 bytes)
        return "0x" + hex_str[-40:]

    def parse_logs(
        self,
        logs: list[dict[str, Any]],
        block_timestamps: dict[int, int] | None = None,
    ) -> list[ParsedEvent]:
        """Parse multiple logs.

        Args:
            logs: List of raw log entries
            block_timestamps: Optional mapping of block number to timestamp

        Returns:
            List of parsed events
        """
        events = []
        for log in logs:
            block_number = log.get("blockNumber", 0)
            timestamp = block_timestamps.get(block_number) if block_timestamps else None

            event = self.parse_log(log, timestamp)
            if event:
                events.append(event)

        return events
