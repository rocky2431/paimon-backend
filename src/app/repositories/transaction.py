"""Repository for transaction record operations."""

from datetime import datetime
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    """Repository for Transaction database operations.

    Handles on-chain transaction queries including:
    - Finding transactions by hash/block/address
    - Event type filtering
    - Block range queries
    """

    model = Transaction

    async def get_by_tx_hash(
        self, tx_hash: str, log_index: int | None = None
    ) -> Transaction | Sequence[Transaction]:
        """Get transaction(s) by hash.

        @param tx_hash - Transaction hash
        @param log_index - Optional specific log index
        @returns Single transaction or list of transactions
        """
        if log_index is not None:
            return await self.get_one_by_filter(tx_hash=tx_hash, log_index=log_index)

        stmt = (
            select(self.model)
            .where(self.model.tx_hash == tx_hash)
            .order_by(self.model.log_index)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_block_range(
        self,
        start_block: int,
        end_block: int,
        *,
        event_type: str | None = None,
    ) -> Sequence[Transaction]:
        """Get transactions in block range.

        @param start_block - Starting block number
        @param end_block - Ending block number
        @param event_type - Optional event type filter
        @returns List of transactions
        """
        stmt = select(self.model).where(
            and_(
                self.model.block_number >= start_block,
                self.model.block_number <= end_block,
            )
        )
        if event_type:
            stmt = stmt.where(self.model.event_type == event_type)
        stmt = stmt.order_by(self.model.block_number, self.model.log_index)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_event_type(
        self,
        event_type: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Transaction]:
        """Get transactions by event type.

        @param event_type - Event type name
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of transactions
        """
        stmt = (
            select(self.model)
            .where(self.model.event_type == event_type)
            .order_by(desc(self.model.block_timestamp))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_address(
        self,
        address: str,
        *,
        direction: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Transaction]:
        """Get transactions involving an address.

        @param address - Wallet address
        @param direction - 'from', 'to', or None for both
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of transactions
        """
        addr_lower = address.lower()
        stmt = select(self.model)

        if direction == "from":
            stmt = stmt.where(self.model.from_address == addr_lower)
        elif direction == "to":
            stmt = stmt.where(self.model.to_address == addr_lower)
        else:
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    self.model.from_address == addr_lower,
                    self.model.to_address == addr_lower,
                )
            )

        stmt = stmt.order_by(desc(self.model.block_timestamp)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent(
        self,
        *,
        event_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[Transaction]:
        """Get most recent transactions.

        @param event_type - Optional event type filter
        @param limit - Maximum results
        @returns List of recent transactions
        """
        stmt = select(self.model)
        if event_type:
            stmt = stmt.where(self.model.event_type == event_type)
        stmt = stmt.order_by(desc(self.model.block_timestamp)).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_block(self) -> int | None:
        """Get the latest processed block number.

        @returns Latest block number or None
        """
        stmt = select(func.max(self.model.block_number))
        result = await self.session.execute(stmt)
        return result.scalar()

    async def exists_tx(self, tx_hash: str, log_index: int) -> bool:
        """Check if transaction already exists (for deduplication).

        @param tx_hash - Transaction hash
        @param log_index - Log index
        @returns True if exists
        """
        return await self.exists(tx_hash=tx_hash, log_index=log_index)

    async def get_volume_by_event(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Decimal]:
        """Get total volume by event type.

        @param start_date - Period start
        @param end_date - Period end
        @returns Dictionary of event_type -> total amount
        """
        stmt = select(
            self.model.event_type, func.coalesce(func.sum(self.model.amount), 0)
        ).group_by(self.model.event_type)

        if start_date:
            stmt = stmt.where(self.model.block_timestamp >= start_date)
        if end_date:
            stmt = stmt.where(self.model.block_timestamp <= end_date)

        result = await self.session.execute(stmt)
        return {event_type: amount for event_type, amount in result.all()}

    async def get_statistics(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get transaction statistics for period.

        @param start_date - Period start
        @param end_date - Period end
        @returns Statistics dictionary
        """
        # Count by event type
        event_stmt = (
            select(self.model.event_type, func.count(self.model.id))
            .group_by(self.model.event_type)
        )
        if start_date:
            event_stmt = event_stmt.where(self.model.block_timestamp >= start_date)
        if end_date:
            event_stmt = event_stmt.where(self.model.block_timestamp <= end_date)

        result = await self.session.execute(event_stmt)
        event_counts = dict(result.all())

        # Volume by event type
        volume = await self.get_volume_by_event(
            start_date=start_date, end_date=end_date
        )

        # Block range
        range_stmt = select(
            func.min(self.model.block_number), func.max(self.model.block_number)
        )
        if start_date:
            range_stmt = range_stmt.where(self.model.block_timestamp >= start_date)
        if end_date:
            range_stmt = range_stmt.where(self.model.block_timestamp <= end_date)

        result = await self.session.execute(range_stmt)
        min_block, max_block = result.first() or (None, None)

        return {
            "by_event_count": event_counts,
            "by_event_volume": volume,
            "total_count": sum(event_counts.values()),
            "block_range": {"min": min_block, "max": max_block},
        }
