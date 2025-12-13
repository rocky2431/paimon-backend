"""Data synchronization service for chain state."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from app.core.config import get_settings
from app.infrastructure.blockchain.client import ChainClient
from app.infrastructure.blockchain.contracts import ContractManager, VAULT_ABI

logger = logging.getLogger(__name__)


class SyncState(str, Enum):
    """Sync service state."""

    IDLE = "idle"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class ChainSnapshot:
    """Snapshot of on-chain state."""

    block_number: int
    timestamp: datetime
    share_price: int
    total_supply: int
    total_assets: int
    effective_supply: int
    total_redemption_liability: int
    total_locked_shares: int
    layer1_liquidity: int
    layer2_liquidity: int
    layer3_value: int
    emergency_mode: bool
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncStats:
    """Statistics for sync service."""

    state: SyncState = SyncState.IDLE
    last_sync_time: datetime | None = None
    last_block_synced: int = 0
    snapshots_created: int = 0
    sync_errors: int = 0
    last_error: str = ""
    average_sync_duration_ms: float = 0.0


class DataSyncService:
    """Service for synchronizing on-chain state with database.

    Features:
    - Periodic snapshots of vault state
    - Incremental event-driven updates
    - Consistency validation between chain and database
    """

    def __init__(
        self,
        client: ChainClient,
        contract_manager: ContractManager | None = None,
        vault_address: str | None = None,
        snapshot_interval: int = 60,  # seconds
        repository: Any = None,
    ):
        """Initialize data sync service.

        Args:
            client: Blockchain client
            contract_manager: Contract manager for calls
            vault_address: Vault contract address
            snapshot_interval: Interval between snapshots in seconds
            repository: Optional repository for persistence
        """
        self.client = client
        self.contract_manager = contract_manager or ContractManager(client)
        settings = get_settings()
        self.vault_address = vault_address or settings.vault_contract_address
        self.snapshot_interval = snapshot_interval
        self.repository = repository

        # State
        self._stats = SyncStats()
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_snapshot: ChainSnapshot | None = None
        self._sync_durations: list[float] = []

    @property
    def stats(self) -> SyncStats:
        """Get sync statistics."""
        if self._sync_durations:
            self._stats.average_sync_duration_ms = sum(self._sync_durations) / len(
                self._sync_durations
            )
        return self._stats

    @property
    def last_snapshot(self) -> ChainSnapshot | None:
        """Get last chain snapshot."""
        return self._last_snapshot

    async def start(self) -> None:
        """Start the sync service."""
        if self._running:
            logger.warning("Sync service is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info("Data sync service started")

    async def stop(self) -> None:
        """Stop the sync service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Data sync service stopped")

    async def _sync_loop(self) -> None:
        """Main sync loop."""
        while self._running:
            try:
                await self.sync_once()
                await asyncio.sleep(self.snapshot_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync error: {e}")
                self._stats.sync_errors += 1
                self._stats.last_error = str(e)
                await asyncio.sleep(self.snapshot_interval)

    async def sync_once(self) -> ChainSnapshot | None:
        """Perform a single sync operation.

        Returns:
            Chain snapshot if successful
        """
        self._stats.state = SyncState.SYNCING
        start_time = datetime.now(timezone.utc)

        try:
            # Get current block
            block_number = await self.client.get_block_number()
            block = await self.client.get_block(block_number)
            block_timestamp = datetime.fromtimestamp(
                block.get("timestamp", 0), tz=timezone.utc
            )

            # Get vault state
            vault_state = await self.contract_manager.get_vault_state(
                self.vault_address
            )

            # Create snapshot
            snapshot = ChainSnapshot(
                block_number=block_number,
                timestamp=block_timestamp,
                share_price=vault_state.get("share_price", 0),
                total_supply=vault_state.get("total_supply", 0),
                total_assets=vault_state.get("total_assets", 0),
                effective_supply=vault_state.get("effective_supply", 0),
                total_redemption_liability=vault_state.get(
                    "total_redemption_liability", 0
                ),
                total_locked_shares=vault_state.get("total_locked_shares", 0),
                layer1_liquidity=vault_state.get("layer1_liquidity", 0),
                layer2_liquidity=vault_state.get("layer2_liquidity", 0),
                layer3_value=vault_state.get("layer3_value", 0),
                emergency_mode=vault_state.get("emergency_mode", False),
                raw_data=vault_state,
            )

            # Store snapshot
            self._last_snapshot = snapshot
            self._stats.last_sync_time = datetime.now(timezone.utc)
            self._stats.last_block_synced = block_number
            self._stats.snapshots_created += 1
            self._stats.state = SyncState.IDLE

            # Track duration
            duration_ms = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000
            self._sync_durations.append(duration_ms)
            # Keep last 100 durations
            if len(self._sync_durations) > 100:
                self._sync_durations = self._sync_durations[-100:]

            # Persist if repository available
            if self.repository:
                await self._persist_snapshot(snapshot)

            logger.debug(
                f"Synced block {block_number}, "
                f"NAV={snapshot.total_assets}, "
                f"supply={snapshot.total_supply}"
            )

            return snapshot

        except Exception as e:
            self._stats.state = SyncState.ERROR
            self._stats.sync_errors += 1
            self._stats.last_error = str(e)
            logger.error(f"Sync failed: {e}")
            return None

    async def _persist_snapshot(self, snapshot: ChainSnapshot) -> None:
        """Persist snapshot to database.

        Args:
            snapshot: Chain snapshot to persist
        """
        # TODO: Implement when repository is available
        pass

    async def validate_consistency(self) -> dict[str, Any]:
        """Validate consistency between chain and database.

        Returns:
            Validation result with any discrepancies
        """
        result = {
            "valid": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "discrepancies": [],
        }

        if not self._last_snapshot:
            result["valid"] = False
            result["discrepancies"].append("No snapshot available")
            return result

        # Get fresh chain state
        try:
            current_state = await self.contract_manager.get_vault_state(
                self.vault_address
            )

            # Compare key fields (allowing for some drift due to transactions)
            fields_to_check = [
                ("share_price", "share_price"),
                ("total_supply", "total_supply"),
                ("emergency_mode", "emergency_mode"),
            ]

            for snapshot_field, chain_field in fields_to_check:
                snapshot_value = getattr(self._last_snapshot, snapshot_field)
                chain_value = current_state.get(chain_field)

                if snapshot_value != chain_value:
                    # Allow small drift for numeric values
                    if isinstance(snapshot_value, int) and isinstance(chain_value, int):
                        drift_percent = (
                            abs(snapshot_value - chain_value)
                            / max(snapshot_value, 1)
                            * 100
                        )
                        if drift_percent > 1:  # >1% drift
                            result["discrepancies"].append(
                                {
                                    "field": snapshot_field,
                                    "snapshot": snapshot_value,
                                    "chain": chain_value,
                                    "drift_percent": drift_percent,
                                }
                            )
                    else:
                        result["discrepancies"].append(
                            {
                                "field": snapshot_field,
                                "snapshot": snapshot_value,
                                "chain": chain_value,
                            }
                        )

            result["valid"] = len(result["discrepancies"]) == 0

        except Exception as e:
            result["valid"] = False
            result["discrepancies"].append(f"Validation error: {str(e)}")

        return result

    def get_nav(self) -> Decimal | None:
        """Get current NAV (Net Asset Value).

        Returns:
            NAV as Decimal or None if no snapshot
        """
        if not self._last_snapshot:
            return None

        if self._last_snapshot.total_supply == 0:
            return Decimal(0)

        return Decimal(self._last_snapshot.total_assets) / Decimal(
            self._last_snapshot.total_supply
        )

    def get_liquidity_ratios(self) -> dict[str, Decimal] | None:
        """Get current liquidity tier ratios.

        Returns:
            Dictionary with L1, L2, L3 ratios or None
        """
        if not self._last_snapshot:
            return None

        total = (
            self._last_snapshot.layer1_liquidity
            + self._last_snapshot.layer2_liquidity
            + self._last_snapshot.layer3_value
        )

        if total == 0:
            return {"l1": Decimal(0), "l2": Decimal(0), "l3": Decimal(0)}

        return {
            "l1": Decimal(self._last_snapshot.layer1_liquidity) / Decimal(total),
            "l2": Decimal(self._last_snapshot.layer2_liquidity) / Decimal(total),
            "l3": Decimal(self._last_snapshot.layer3_value) / Decimal(total),
        }

    def is_emergency_mode(self) -> bool:
        """Check if vault is in emergency mode.

        Returns:
            True if in emergency mode
        """
        if not self._last_snapshot:
            return False
        return self._last_snapshot.emergency_mode


# Service factory
_sync_service: DataSyncService | None = None


def get_data_sync_service(
    client: ChainClient | None = None,
) -> DataSyncService | None:
    """Get or create data sync service.

    Args:
        client: Optional blockchain client

    Returns:
        DataSyncService instance or None if no client
    """
    global _sync_service
    if _sync_service is None and client is not None:
        _sync_service = DataSyncService(client=client)
    return _sync_service
