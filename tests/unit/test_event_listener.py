"""Tests for event listener service."""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.blockchain.events import EventType, ParsedEvent
from app.services.event_listener.checkpoint import (
    Checkpoint,
    CheckpointManager,
)
from app.services.event_listener.deduplicator import (
    EventDeduplicator,
)
from app.services.event_listener.listener import (
    EventListener,
    ListenerConfig,
    ListenerState,
    ListenerStats,
)


class TestCheckpoint:
    """Tests for Checkpoint model."""

    def test_checkpoint_creation(self):
        """Test creating checkpoint with defaults."""
        checkpoint = Checkpoint()
        assert checkpoint.last_block == 0
        assert checkpoint.last_log_index == 0
        assert checkpoint.last_tx_hash == ""

    def test_checkpoint_with_values(self):
        """Test creating checkpoint with values."""
        checkpoint = Checkpoint(
            last_block=12345,
            last_log_index=5,
            last_tx_hash="0xabc123",
        )
        assert checkpoint.last_block == 12345
        assert checkpoint.last_log_index == 5
        assert checkpoint.last_tx_hash == "0xabc123"

    def test_checkpoint_serialization(self):
        """Test checkpoint JSON serialization."""
        checkpoint = Checkpoint(last_block=100)
        json_str = checkpoint.model_dump_json()
        restored = Checkpoint.model_validate_json(json_str)
        assert restored.last_block == 100


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    @pytest.fixture
    def temp_file(self):
        """Create temporary file for checkpoint."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            yield Path(f.name)

    @pytest.mark.asyncio
    async def test_save_and_load_file(self, temp_file):
        """Test saving and loading checkpoint from file."""
        manager = CheckpointManager(checkpoint_path=temp_file)

        # Save checkpoint
        checkpoint = Checkpoint(last_block=12345, last_tx_hash="0xabc")
        await manager.save(checkpoint)

        # Load checkpoint
        loaded = await manager.load()
        assert loaded.last_block == 12345
        assert loaded.last_tx_hash == "0xabc"

    @pytest.mark.asyncio
    async def test_load_default_when_missing(self):
        """Test loading returns default when file missing."""
        manager = CheckpointManager(checkpoint_path=Path("/nonexistent/path.json"))
        checkpoint = await manager.load()
        assert checkpoint.last_block == 0

    @pytest.mark.asyncio
    async def test_update_block(self, temp_file):
        """Test updating block number."""
        manager = CheckpointManager(checkpoint_path=temp_file)
        await manager.load()

        await manager.update_block(100, "0x123", 5)

        assert manager.get_last_block() == 100

    @pytest.mark.asyncio
    async def test_reset_checkpoint(self, temp_file):
        """Test resetting checkpoint."""
        manager = CheckpointManager(checkpoint_path=temp_file)

        # Save some data
        await manager.save(Checkpoint(last_block=1000))

        # Reset
        await manager.reset()

        # Verify reset
        checkpoint = await manager.load()
        assert checkpoint.last_block == 0


class TestEventDeduplicator:
    """Tests for EventDeduplicator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.dedup = EventDeduplicator()

    @pytest.mark.asyncio
    async def test_new_event_not_duplicate(self):
        """Test new event is not marked as duplicate."""
        is_dup = await self.dedup.is_duplicate("0xabc123", 0)
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_marked_event_is_duplicate(self):
        """Test marked event is detected as duplicate."""
        await self.dedup.mark_processed("0xabc123", 0)
        is_dup = await self.dedup.is_duplicate("0xabc123", 0)
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_check_and_mark(self):
        """Test check_and_mark returns correct values."""
        # First call - new event
        is_new = await self.dedup.check_and_mark("0xabc123", 0)
        assert is_new is True

        # Second call - duplicate
        is_new = await self.dedup.check_and_mark("0xabc123", 0)
        assert is_new is False

    @pytest.mark.asyncio
    async def test_different_log_index_not_duplicate(self):
        """Test same tx_hash with different log_index is not duplicate."""
        await self.dedup.mark_processed("0xabc123", 0)

        is_dup = await self.dedup.is_duplicate("0xabc123", 1)
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when at capacity."""
        small_dedup = EventDeduplicator(max_memory_size=3)

        await small_dedup.mark_processed("tx1", 0)
        await small_dedup.mark_processed("tx2", 0)
        await small_dedup.mark_processed("tx3", 0)
        await small_dedup.mark_processed("tx4", 0)  # Should evict tx1

        # tx1 should be evicted
        assert "tx1:0" not in str(small_dedup._seen)

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting deduplicator stats."""
        await self.dedup.mark_processed("tx1", 0)
        await self.dedup.mark_processed("tx2", 0)

        stats = await self.dedup.get_stats()

        assert stats["memory_size"] == 2
        assert stats["has_redis"] is False

    def test_clear_memory(self):
        """Test clearing memory cache."""
        self.dedup._seen["test"] = datetime.now(timezone.utc)
        self.dedup.clear_memory()
        assert len(self.dedup._seen) == 0


class TestListenerConfig:
    """Tests for ListenerConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ListenerConfig()

        assert config.block_batch_size == 1000
        assert config.poll_interval == 3.0
        assert config.confirmation_blocks == 3
        assert config.auto_reconnect is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ListenerConfig(
            contract_addresses=["0x123", "0x456"],
            block_batch_size=500,
            poll_interval=1.0,
        )

        assert len(config.contract_addresses) == 2
        assert config.block_batch_size == 500
        assert config.poll_interval == 1.0


class TestListenerStats:
    """Tests for ListenerStats."""

    def test_default_stats(self):
        """Test default statistics."""
        stats = ListenerStats()

        assert stats.state == ListenerState.STOPPED
        assert stats.events_processed == 0
        assert stats.errors == 0


class TestEventListener:
    """Tests for EventListener."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock()
        self.mock_client.get_block_number = AsyncMock(return_value=1000)
        self.mock_client.get_logs = AsyncMock(return_value=[])
        self.mock_client.get_block = AsyncMock(return_value={"timestamp": 1234567890})

        self.config = ListenerConfig(
            contract_addresses=["0x1234567890123456789012345678901234567890"],
            poll_interval=0.1,
        )

    def test_listener_initialization(self):
        """Test listener initializes correctly."""
        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )

        assert listener.state == ListenerState.STOPPED
        assert listener.stats.events_processed == 0

    def test_add_handler(self):
        """Test adding event handler."""
        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )

        async def handler(event):
            pass

        listener.add_handler(handler)
        assert handler in listener._handlers

    def test_remove_handler(self):
        """Test removing event handler."""
        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )

        async def handler(event):
            pass

        listener.add_handler(handler)
        listener.remove_handler(handler)
        assert handler not in listener._handlers

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping listener."""
        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )

        await listener.start()
        assert listener.state == ListenerState.RUNNING

        await listener.stop()
        assert listener.state == ListenerState.STOPPED

    @pytest.mark.asyncio
    async def test_poll_once(self):
        """Test single polling cycle."""
        # Set up mock to return a log
        mock_log = {
            "topics": [bytes.fromhex("0" * 64)],
            "data": b"",
            "blockNumber": 100,
            "logIndex": 0,
            "transactionHash": bytes.fromhex("abc" * 21 + "a"),
            "address": "0x1234567890123456789012345678901234567890",
        }
        self.mock_client.get_logs = AsyncMock(return_value=[mock_log])

        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )
        await listener.checkpoint_manager.load()
        listener._stats.current_block = 90

        await listener._poll_once()

        # Should have fetched logs
        self.mock_client.get_logs.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_processing(self):
        """Test event is processed through handler."""
        events_received = []

        async def handler(event):
            events_received.append(event)

        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )
        listener.add_handler(handler)

        # Create mock event
        event = ParsedEvent(
            event_type=EventType.DEPOSIT,
            tx_hash="0x123",
            block_number=100,
            log_index=0,
            block_timestamp=datetime.now(timezone.utc),
            contract_address="0x456",
            args={},
            raw_data={},
        )

        await listener._process_event(event)

        assert len(events_received) == 1
        assert events_received[0].tx_hash == "0x123"

    @pytest.mark.asyncio
    async def test_duplicate_event_skipped(self):
        """Test duplicate events are skipped."""
        events_received = []

        async def handler(event):
            events_received.append(event)

        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )
        listener.add_handler(handler)

        event = ParsedEvent(
            event_type=EventType.DEPOSIT,
            tx_hash="0x123",
            block_number=100,
            log_index=0,
            block_timestamp=datetime.now(timezone.utc),
            contract_address="0x456",
            args={},
            raw_data={},
        )

        # Process same event twice
        await listener._process_event(event)
        await listener._process_event(event)

        # Should only receive once
        assert len(events_received) == 1
        assert listener.stats.events_skipped == 1

    @pytest.mark.asyncio
    async def test_get_sync_status(self):
        """Test getting sync status."""
        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )

        listener._stats.current_block = 990
        listener._stats.latest_chain_block = 1000

        status = await listener.get_sync_status()

        assert status["current_block"] == 990
        assert status["latest_block"] == 1000
        assert status["blocks_behind"] == 10
        assert status["synced"] is False

    @pytest.mark.asyncio
    async def test_handler_error_handled(self):
        """Test handler errors are caught."""

        async def bad_handler(event):
            raise Exception("Handler error")

        listener = EventListener(
            client=self.mock_client,
            config=self.config,
        )
        listener.add_handler(bad_handler)

        event = ParsedEvent(
            event_type=EventType.DEPOSIT,
            tx_hash="0x999",
            block_number=100,
            log_index=0,
            block_timestamp=datetime.now(timezone.utc),
            contract_address="0x456",
            args={},
            raw_data={},
        )

        # Should not raise
        await listener._process_event(event)

        assert listener.stats.errors == 1
