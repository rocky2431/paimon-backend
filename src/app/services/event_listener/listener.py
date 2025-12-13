"""Event listener service for blockchain events."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

from app.infrastructure.blockchain.client import ChainClient
from app.infrastructure.blockchain.events import EventParser, ParsedEvent
from app.services.event_listener.checkpoint import CheckpointManager
from app.services.event_listener.deduplicator import EventDeduplicator

logger = logging.getLogger(__name__)


class ListenerState(str, Enum):
    """Event listener state."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ListenerConfig:
    """Configuration for event listener."""

    # Contract addresses to monitor
    contract_addresses: list[str] = field(default_factory=list)

    # Event topics to filter (None = all events)
    topics: list[str] | None = None

    # Block range for each poll
    block_batch_size: int = 1000

    # Polling interval in seconds
    poll_interval: float = 3.0

    # Maximum blocks to process in one batch
    max_blocks_per_batch: int = 5000

    # Confirmation blocks before processing
    confirmation_blocks: int = 3

    # Auto-reconnect on failure
    auto_reconnect: bool = True

    # Reconnect delay (seconds)
    reconnect_delay: float = 5.0

    # Maximum reconnect attempts
    max_reconnect_attempts: int = 10

    # Start block (0 = latest)
    start_block: int = 0


@dataclass
class ListenerStats:
    """Statistics for event listener."""

    state: ListenerState = ListenerState.STOPPED
    current_block: int = 0
    latest_chain_block: int = 0
    events_processed: int = 0
    events_skipped: int = 0
    errors: int = 0
    last_error: str = ""
    last_event_time: datetime | None = None
    started_at: datetime | None = None
    uptime_seconds: float = 0.0


# Event handler type
EventHandler = Callable[[ParsedEvent], Coroutine[Any, Any, None]]


class EventListener:
    """Blockchain event listener with checkpoint-based resumption.

    Features:
    - Checkpoint-based resumption after restart
    - Event deduplication (txHash + logIndex)
    - Automatic reconnection with backoff
    - Polling fallback for reliability
    - Multiple contract monitoring
    """

    def __init__(
        self,
        client: ChainClient,
        config: ListenerConfig,
        checkpoint_manager: CheckpointManager | None = None,
        deduplicator: EventDeduplicator | None = None,
    ):
        """Initialize event listener.

        Args:
            client: Blockchain client for RPC calls
            config: Listener configuration
            checkpoint_manager: Optional checkpoint manager
            deduplicator: Optional event deduplicator
        """
        self.client = client
        self.config = config
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.deduplicator = deduplicator or EventDeduplicator()
        self.event_parser = EventParser()

        # State
        self._state = ListenerState.STOPPED
        self._stats = ListenerStats()
        self._handlers: list[EventHandler] = []
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def state(self) -> ListenerState:
        """Get current listener state."""
        return self._state

    @property
    def stats(self) -> ListenerStats:
        """Get listener statistics."""
        self._stats.state = self._state
        if self._stats.started_at:
            self._stats.uptime_seconds = (
                datetime.now(timezone.utc) - self._stats.started_at
            ).total_seconds()
        return self._stats

    def add_handler(self, handler: EventHandler) -> None:
        """Add event handler.

        Args:
            handler: Async function to handle events
        """
        self._handlers.append(handler)

    def remove_handler(self, handler: EventHandler) -> None:
        """Remove event handler.

        Args:
            handler: Handler to remove
        """
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def start(self) -> None:
        """Start the event listener."""
        if self._state == ListenerState.RUNNING:
            logger.warning("Event listener is already running")
            return

        self._state = ListenerState.STARTING
        self._stop_event.clear()
        self._stats.started_at = datetime.now(timezone.utc)

        # Load checkpoint
        checkpoint = await self.checkpoint_manager.load()
        self._stats.current_block = checkpoint.last_block or self.config.start_block

        logger.info(
            f"Starting event listener from block {self._stats.current_block}"
        )

        # Start polling task
        self._task = asyncio.create_task(self._poll_loop())
        self._state = ListenerState.RUNNING

    async def stop(self) -> None:
        """Stop the event listener."""
        if self._state == ListenerState.STOPPED:
            return

        logger.info("Stopping event listener...")
        self._stop_event.set()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._state = ListenerState.STOPPED
        logger.info("Event listener stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop for events."""
        reconnect_attempts = 0

        while not self._stop_event.is_set():
            try:
                await self._poll_once()
                reconnect_attempts = 0  # Reset on success
                await asyncio.sleep(self.config.poll_interval)

            except asyncio.CancelledError:
                break

            except Exception as e:
                self._stats.errors += 1
                self._stats.last_error = str(e)
                logger.error(f"Event polling error: {e}")

                if not self.config.auto_reconnect:
                    self._state = ListenerState.ERROR
                    break

                reconnect_attempts += 1
                if reconnect_attempts >= self.config.max_reconnect_attempts:
                    logger.error("Max reconnect attempts reached, stopping")
                    self._state = ListenerState.ERROR
                    break

                self._state = ListenerState.RECONNECTING
                delay = self.config.reconnect_delay * reconnect_attempts
                logger.info(f"Reconnecting in {delay}s (attempt {reconnect_attempts})")
                await asyncio.sleep(delay)
                self._state = ListenerState.RUNNING

    async def _poll_once(self) -> None:
        """Execute one polling cycle."""
        # Get latest block
        latest_block = await self.client.get_block_number()
        self._stats.latest_chain_block = latest_block

        # Calculate block range with confirmations
        safe_block = latest_block - self.config.confirmation_blocks
        from_block = self._stats.current_block + 1

        if from_block > safe_block:
            return  # Nothing new to process

        # Limit batch size
        to_block = min(
            from_block + self.config.block_batch_size - 1,
            safe_block,
        )

        # Fetch logs
        logs = await self.client.get_logs(
            from_block=from_block,
            to_block=to_block,
            address=self.config.contract_addresses or None,
            topics=self.config.topics,
        )

        # Get block timestamps for logs
        block_timestamps = await self._get_block_timestamps(logs)

        # Parse events
        events = self.event_parser.parse_logs(logs, block_timestamps)

        # Process events
        for event in events:
            await self._process_event(event)

        # Update checkpoint
        self._stats.current_block = to_block
        await self.checkpoint_manager.update_block(to_block)

        if events:
            logger.info(
                f"Processed {len(events)} events from blocks {from_block}-{to_block}"
            )

    async def _process_event(self, event: ParsedEvent) -> None:
        """Process a single event.

        Args:
            event: Parsed blockchain event
        """
        # Check for duplicate
        is_new = await self.deduplicator.check_and_mark(
            event.tx_hash,
            event.log_index,
        )

        if not is_new:
            self._stats.events_skipped += 1
            return

        # Call all handlers
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
                self._stats.errors += 1

        self._stats.events_processed += 1
        self._stats.last_event_time = datetime.now(timezone.utc)

    async def _get_block_timestamps(
        self, logs: list[dict[str, Any]]
    ) -> dict[int, int]:
        """Get timestamps for blocks containing logs.

        Args:
            logs: List of log entries

        Returns:
            Mapping of block number to timestamp
        """
        block_numbers = set(log.get("blockNumber", 0) for log in logs)
        timestamps: dict[int, int] = {}

        for block_num in block_numbers:
            if block_num:
                try:
                    block = await self.client.get_block(block_num)
                    timestamps[block_num] = block.get("timestamp", 0)
                except Exception as e:
                    logger.warning(f"Failed to get block {block_num} timestamp: {e}")

        return timestamps

    async def sync_from_block(self, block_number: int) -> int:
        """Sync events from a specific block.

        Args:
            block_number: Starting block number

        Returns:
            Number of events processed
        """
        original_block = self._stats.current_block
        self._stats.current_block = block_number - 1
        events_before = self._stats.events_processed

        try:
            await self._poll_once()
        finally:
            pass  # Keep the updated block

        return self._stats.events_processed - events_before

    async def get_sync_status(self) -> dict[str, Any]:
        """Get synchronization status.

        Returns:
            Sync status dictionary
        """
        stats = self.stats
        return {
            "state": stats.state.value,
            "current_block": stats.current_block,
            "latest_block": stats.latest_chain_block,
            "blocks_behind": stats.latest_chain_block - stats.current_block,
            "events_processed": stats.events_processed,
            "events_skipped": stats.events_skipped,
            "errors": stats.errors,
            "last_error": stats.last_error,
            "uptime_seconds": stats.uptime_seconds,
            "synced": stats.current_block >= stats.latest_chain_block - self.config.confirmation_blocks,
        }
