"""Tests for data sync service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.data_sync.sync_service import (
    ChainSnapshot,
    DataSyncService,
    SyncState,
    SyncStats,
)


class TestChainSnapshot:
    """Tests for ChainSnapshot dataclass."""

    def test_snapshot_creation(self):
        """Test creating chain snapshot."""
        snapshot = ChainSnapshot(
            block_number=12345,
            timestamp=datetime.now(timezone.utc),
            share_price=1000000000000000000,  # 1e18
            total_supply=5000000000000000000000,  # 5000e18
            total_assets=5500000000000000000000,  # 5500e18
            effective_supply=4800000000000000000000,
            total_redemption_liability=100000000000000000000,
            total_locked_shares=200000000000000000000,
            layer1_liquidity=500000000000000000000,
            layer2_liquidity=1500000000000000000000,
            layer3_value=3500000000000000000000,
            emergency_mode=False,
        )

        assert snapshot.block_number == 12345
        assert snapshot.share_price == 1000000000000000000
        assert snapshot.emergency_mode is False

    def test_snapshot_with_raw_data(self):
        """Test snapshot with raw data."""
        snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=0,
            total_supply=0,
            total_assets=0,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
            raw_data={"extra": "data"},
        )

        assert snapshot.raw_data == {"extra": "data"}


class TestSyncStats:
    """Tests for SyncStats dataclass."""

    def test_default_stats(self):
        """Test default statistics."""
        stats = SyncStats()

        assert stats.state == SyncState.IDLE
        assert stats.last_sync_time is None
        assert stats.snapshots_created == 0
        assert stats.sync_errors == 0


class TestDataSyncService:
    """Tests for DataSyncService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock()
        self.mock_client.get_block_number = AsyncMock(return_value=12345)
        self.mock_client.get_block = AsyncMock(
            return_value={"timestamp": 1234567890}
        )
        self.mock_client.eth_call = AsyncMock(
            return_value=(1000000000000000000).to_bytes(32, "big")
        )

        self.mock_contract_manager = AsyncMock()
        self.mock_contract_manager.get_vault_state = AsyncMock(
            return_value={
                "share_price": 1000000000000000000,
                "total_supply": 5000000000000000000000,
                "total_assets": 5500000000000000000000,
                "effective_supply": 4800000000000000000000,
                "total_redemption_liability": 100000000000000000000,
                "total_locked_shares": 200000000000000000000,
                "layer1_liquidity": 500000000000000000000,
                "layer2_liquidity": 1500000000000000000000,
                "layer3_value": 3500000000000000000000,
                "emergency_mode": False,
            }
        )

    def test_service_initialization(self):
        """Test service initializes correctly."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        assert service.stats.state == SyncState.IDLE
        assert service.last_snapshot is None

    @pytest.mark.asyncio
    async def test_sync_once(self):
        """Test single sync operation."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        snapshot = await service.sync_once()

        assert snapshot is not None
        assert snapshot.block_number == 12345
        assert snapshot.share_price == 1000000000000000000
        assert service.stats.snapshots_created == 1
        assert service.last_snapshot == snapshot

    @pytest.mark.asyncio
    async def test_sync_error_handling(self):
        """Test sync error handling."""
        self.mock_contract_manager.get_vault_state = AsyncMock(
            side_effect=Exception("RPC Error")
        )

        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        snapshot = await service.sync_once()

        assert snapshot is None
        assert service.stats.sync_errors == 1
        assert "RPC Error" in service.stats.last_error

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping service."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
            snapshot_interval=0.1,  # Short interval for testing
        )

        await service.start()
        assert service._running is True

        await service.stop()
        assert service._running is False

    def test_get_nav(self):
        """Test NAV calculation."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        # Before sync, NAV is None
        assert service.get_nav() is None

        # Set up snapshot
        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=0,
            total_supply=1000,
            total_assets=1100,  # 10% gain
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
        )

        nav = service.get_nav()
        assert nav == Decimal("1.1")

    def test_get_nav_zero_supply(self):
        """Test NAV calculation with zero supply."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=0,
            total_supply=0,
            total_assets=0,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
        )

        nav = service.get_nav()
        assert nav == Decimal(0)

    def test_get_liquidity_ratios(self):
        """Test liquidity ratio calculation."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=0,
            total_supply=0,
            total_assets=0,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=100,  # 10%
            layer2_liquidity=300,  # 30%
            layer3_value=600,  # 60%
            emergency_mode=False,
        )

        ratios = service.get_liquidity_ratios()

        assert ratios is not None
        assert ratios["l1"] == Decimal("0.1")
        assert ratios["l2"] == Decimal("0.3")
        assert ratios["l3"] == Decimal("0.6")

    def test_get_liquidity_ratios_zero_total(self):
        """Test liquidity ratios with zero total."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=0,
            total_supply=0,
            total_assets=0,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
        )

        ratios = service.get_liquidity_ratios()

        assert ratios["l1"] == Decimal(0)
        assert ratios["l2"] == Decimal(0)
        assert ratios["l3"] == Decimal(0)

    def test_is_emergency_mode(self):
        """Test emergency mode check."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        # Without snapshot
        assert service.is_emergency_mode() is False

        # With snapshot, not in emergency
        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=0,
            total_supply=0,
            total_assets=0,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
        )
        assert service.is_emergency_mode() is False

        # In emergency mode
        service._last_snapshot.emergency_mode = True
        assert service.is_emergency_mode() is True

    @pytest.mark.asyncio
    async def test_validate_consistency_no_snapshot(self):
        """Test consistency validation without snapshot."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        result = await service.validate_consistency()

        assert result["valid"] is False
        assert "No snapshot available" in result["discrepancies"]

    @pytest.mark.asyncio
    async def test_validate_consistency_valid(self):
        """Test consistency validation with matching state."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        # Set snapshot matching mock return value
        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=1000000000000000000,
            total_supply=5000000000000000000000,
            total_assets=5500000000000000000000,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
        )

        result = await service.validate_consistency()

        assert result["valid"] is True
        assert len(result["discrepancies"]) == 0

    @pytest.mark.asyncio
    async def test_validate_consistency_with_drift(self):
        """Test consistency validation with significant drift."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        # Set snapshot with different values (>1% drift)
        service._last_snapshot = ChainSnapshot(
            block_number=100,
            timestamp=datetime.now(timezone.utc),
            share_price=900000000000000000,  # 10% different
            total_supply=5000000000000000000000,
            total_assets=0,
            effective_supply=0,
            total_redemption_liability=0,
            total_locked_shares=0,
            layer1_liquidity=0,
            layer2_liquidity=0,
            layer3_value=0,
            emergency_mode=False,
        )

        result = await service.validate_consistency()

        assert result["valid"] is False
        assert len(result["discrepancies"]) > 0

    def test_stats_average_duration(self):
        """Test average sync duration calculation."""
        service = DataSyncService(
            client=self.mock_client,
            contract_manager=self.mock_contract_manager,
            vault_address="0x1234567890123456789012345678901234567890",
        )

        service._sync_durations = [100, 200, 300]

        stats = service.stats
        assert stats.average_sync_duration_ms == 200.0
