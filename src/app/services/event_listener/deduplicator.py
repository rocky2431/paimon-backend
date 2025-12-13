"""Event deduplication for preventing duplicate processing."""

import hashlib
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class EventDeduplicator:
    """Deduplicates blockchain events using txHash + logIndex.

    Supports both in-memory and Redis-based deduplication.
    """

    def __init__(
        self,
        redis_client: Any = None,
        redis_prefix: str = "event_dedup:",
        ttl_seconds: int = 3600 * 24,  # 24 hours
        max_memory_size: int = 10000,
    ):
        """Initialize event deduplicator.

        Args:
            redis_client: Optional Redis client for distributed deduplication
            redis_prefix: Redis key prefix
            ttl_seconds: TTL for Redis entries
            max_memory_size: Max entries for in-memory deduplication
        """
        self.redis_client = redis_client
        self.redis_prefix = redis_prefix
        self.ttl_seconds = ttl_seconds
        self.max_memory_size = max_memory_size

        # In-memory deduplication cache (LRU)
        self._seen: OrderedDict[str, datetime] = OrderedDict()

    def _generate_event_id(self, tx_hash: str, log_index: int) -> str:
        """Generate unique event ID from tx_hash and log_index.

        Args:
            tx_hash: Transaction hash
            log_index: Log index within transaction

        Returns:
            Unique event identifier
        """
        # Normalize tx_hash
        if tx_hash.startswith("0x"):
            tx_hash = tx_hash[2:]
        tx_hash = tx_hash.lower()

        # Create composite ID
        composite = f"{tx_hash}:{log_index}"
        return hashlib.sha256(composite.encode()).hexdigest()[:32]

    async def is_duplicate(self, tx_hash: str, log_index: int) -> bool:
        """Check if event has already been processed.

        Args:
            tx_hash: Transaction hash
            log_index: Log index within transaction

        Returns:
            True if event was already processed
        """
        event_id = self._generate_event_id(tx_hash, log_index)

        # Check Redis first if available
        if self.redis_client:
            try:
                exists = await self.redis_client.exists(f"{self.redis_prefix}{event_id}")
                if exists:
                    return True
            except Exception as e:
                logger.warning(f"Redis check failed, falling back to memory: {e}")

        # Check in-memory cache
        return event_id in self._seen

    async def mark_processed(self, tx_hash: str, log_index: int) -> bool:
        """Mark event as processed.

        Args:
            tx_hash: Transaction hash
            log_index: Log index within transaction

        Returns:
            True if marked successfully
        """
        event_id = self._generate_event_id(tx_hash, log_index)
        now = datetime.now(timezone.utc)

        # Mark in Redis if available
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"{self.redis_prefix}{event_id}",
                    self.ttl_seconds,
                    now.isoformat(),
                )
            except Exception as e:
                logger.warning(f"Redis mark failed: {e}")

        # Mark in memory
        self._add_to_memory(event_id, now)

        return True

    async def check_and_mark(self, tx_hash: str, log_index: int) -> bool:
        """Check if duplicate and mark as processed if not.

        Args:
            tx_hash: Transaction hash
            log_index: Log index within transaction

        Returns:
            True if event is new (not duplicate), False if duplicate
        """
        if await self.is_duplicate(tx_hash, log_index):
            return False

        await self.mark_processed(tx_hash, log_index)
        return True

    def _add_to_memory(self, event_id: str, timestamp: datetime) -> None:
        """Add event to in-memory cache with LRU eviction.

        Args:
            event_id: Event identifier
            timestamp: Processing timestamp
        """
        # Remove oldest if at capacity
        while len(self._seen) >= self.max_memory_size:
            self._seen.popitem(last=False)

        # Add new entry
        self._seen[event_id] = timestamp

    async def get_stats(self) -> dict[str, Any]:
        """Get deduplicator statistics.

        Returns:
            Statistics dictionary
        """
        stats = {
            "memory_size": len(self._seen),
            "max_memory_size": self.max_memory_size,
            "has_redis": self.redis_client is not None,
        }

        if self.redis_client:
            try:
                # Count Redis keys (expensive, use sparingly)
                keys = await self.redis_client.keys(f"{self.redis_prefix}*")
                stats["redis_size"] = len(keys)
            except Exception:
                stats["redis_size"] = -1

        return stats

    def clear_memory(self) -> None:
        """Clear in-memory cache."""
        self._seen.clear()

    async def clear_all(self) -> None:
        """Clear all deduplication data (memory and Redis)."""
        self.clear_memory()

        if self.redis_client:
            try:
                keys = await self.redis_client.keys(f"{self.redis_prefix}*")
                if keys:
                    await self.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Failed to clear Redis dedup data: {e}")
