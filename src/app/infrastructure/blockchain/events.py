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
    """Supported event types."""

    # Vault events
    DEPOSIT = "Deposit"
    WITHDRAW = "Withdraw"

    # Redemption events
    REDEMPTION_REQUESTED = "RedemptionRequested"
    REDEMPTION_APPROVED = "RedemptionApproved"
    REDEMPTION_REJECTED = "RedemptionRejected"
    REDEMPTION_SETTLED = "RedemptionSettled"
    REDEMPTION_CANCELLED = "RedemptionCancelled"

    # Emergency events
    EMERGENCY_MODE_CHANGED = "EmergencyModeChanged"

    # Asset events
    ASSET_ADDED = "AssetAdded"
    ASSET_REMOVED = "AssetRemoved"

    # Rebalancing events
    REBALANCE_EXECUTED = "RebalanceExecuted"

    # Risk events
    LOW_LIQUIDITY_ALERT = "LowLiquidityAlert"
    CRITICAL_LIQUIDITY_ALERT = "CriticalLiquidityAlert"


# Event signatures (keccak256 hash of event signature)
EVENT_SIGNATURES = {
    EventType.DEPOSIT: "Deposit(address,address,uint256,uint256)",
    EventType.WITHDRAW: "Withdraw(address,address,address,uint256,uint256)",
    EventType.REDEMPTION_REQUESTED: "RedemptionRequested(uint256,address,address,uint256,uint256,uint8)",
    EventType.REDEMPTION_APPROVED: "RedemptionApproved(uint256,address)",
    EventType.REDEMPTION_REJECTED: "RedemptionRejected(uint256,address,string)",
    EventType.REDEMPTION_SETTLED: "RedemptionSettled(uint256,address,uint256,uint256)",
    EventType.REDEMPTION_CANCELLED: "RedemptionCancelled(uint256,address)",
    EventType.EMERGENCY_MODE_CHANGED: "EmergencyModeChanged(bool,address)",
    EventType.ASSET_ADDED: "AssetAdded(address,uint8,uint256)",
    EventType.ASSET_REMOVED: "AssetRemoved(address)",
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
        elif event_type == EventType.REDEMPTION_SETTLED:
            return self._decode_redemption_settled(topics, data)
        elif event_type == EventType.EMERGENCY_MODE_CHANGED:
            return self._decode_emergency_mode_changed(topics, data)
        else:
            # Generic decode for other events
            return {"raw_topics": topics, "raw_data": data.hex()}

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
        """Decode RedemptionRequested event."""
        # RedemptionRequested(uint256 indexed requestId, address indexed owner, address receiver, uint256 shares, uint256 grossAmount, uint8 channel)
        request_id = int(topics[1].hex(), 16) if len(topics) > 1 else 0
        owner = self._decode_address(topics[2]) if len(topics) > 2 else None

        if data:
            decoded = decode(["address", "uint256", "uint256", "uint8"], data)
            receiver, shares, gross_amount, channel = decoded
        else:
            receiver, shares, gross_amount, channel = None, 0, 0, 0

        return {
            "request_id": request_id,
            "owner": owner,
            "receiver": receiver,
            "shares": shares,
            "gross_amount": gross_amount,
            "channel": channel,
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
