"""Checkpoint management for event listener resumption."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Checkpoint(BaseModel):
    """Event listener checkpoint state."""

    last_block: int = 0
    last_log_index: int = 0
    last_tx_hash: str = ""
    last_updated: datetime = datetime.now(timezone.utc)
    contract_addresses: list[str] = []
    metadata: dict[str, Any] = {}


class CheckpointManager:
    """Manages checkpoint persistence for event listener resumption.

    Supports both file-based and Redis-based storage.
    """

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        redis_client: Any = None,
        redis_key: str = "event_listener:checkpoint",
    ):
        """Initialize checkpoint manager.

        Args:
            checkpoint_path: Path for file-based checkpoint storage
            redis_client: Redis client for distributed storage
            redis_key: Redis key for checkpoint storage
        """
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.redis_client = redis_client
        self.redis_key = redis_key
        self._checkpoint: Checkpoint | None = None

    async def load(self) -> Checkpoint:
        """Load checkpoint from storage.

        Returns:
            Checkpoint state or default if not found
        """
        # Try Redis first
        if self.redis_client:
            checkpoint = await self._load_from_redis()
            if checkpoint:
                self._checkpoint = checkpoint
                return checkpoint

        # Fall back to file
        if self.checkpoint_path and self.checkpoint_path.exists():
            checkpoint = self._load_from_file()
            if checkpoint:
                self._checkpoint = checkpoint
                return checkpoint

        # Return default checkpoint
        self._checkpoint = Checkpoint()
        return self._checkpoint

    async def save(self, checkpoint: Checkpoint) -> bool:
        """Save checkpoint to storage.

        Args:
            checkpoint: Checkpoint state to save

        Returns:
            True if saved successfully
        """
        checkpoint.last_updated = datetime.now(timezone.utc)
        self._checkpoint = checkpoint

        # Save to Redis if available
        if self.redis_client:
            saved = await self._save_to_redis(checkpoint)
            if saved:
                return True

        # Fall back to file
        if self.checkpoint_path:
            return self._save_to_file(checkpoint)

        return False

    async def update_block(self, block_number: int, tx_hash: str = "", log_index: int = 0) -> bool:
        """Update checkpoint with new block info.

        Args:
            block_number: Latest processed block
            tx_hash: Latest transaction hash
            log_index: Latest log index

        Returns:
            True if updated successfully
        """
        if not self._checkpoint:
            await self.load()

        self._checkpoint.last_block = block_number
        self._checkpoint.last_tx_hash = tx_hash
        self._checkpoint.last_log_index = log_index

        return await self.save(self._checkpoint)

    def get_last_block(self) -> int:
        """Get last processed block number."""
        return self._checkpoint.last_block if self._checkpoint else 0

    async def _load_from_redis(self) -> Checkpoint | None:
        """Load checkpoint from Redis."""
        try:
            data = await self.redis_client.get(self.redis_key)
            if data:
                return Checkpoint.model_validate_json(data)
        except Exception as e:
            logger.error(f"Failed to load checkpoint from Redis: {e}")
        return None

    async def _save_to_redis(self, checkpoint: Checkpoint) -> bool:
        """Save checkpoint to Redis."""
        try:
            await self.redis_client.set(
                self.redis_key,
                checkpoint.model_dump_json(),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint to Redis: {e}")
            return False

    def _load_from_file(self) -> Checkpoint | None:
        """Load checkpoint from file."""
        try:
            with open(self.checkpoint_path, "r") as f:
                data = json.load(f)
                return Checkpoint.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load checkpoint from file: {e}")
            return None

    def _save_to_file(self, checkpoint: Checkpoint) -> bool:
        """Save checkpoint to file."""
        try:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_path, "w") as f:
                json.dump(checkpoint.model_dump(mode="json"), f, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint to file: {e}")
            return False

    async def reset(self) -> bool:
        """Reset checkpoint to initial state.

        Returns:
            True if reset successfully
        """
        self._checkpoint = Checkpoint()
        return await self.save(self._checkpoint)
