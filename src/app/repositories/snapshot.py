"""Repository for time-series snapshot operations."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.timeseries import DailySnapshot, RiskMetricsSeries
from app.repositories.base import BaseRepository


class DailySnapshotRepository(BaseRepository[DailySnapshot]):
    """Repository for DailySnapshot database operations.

    Handles time-series queries including:
    - NAV history retrieval
    - Fund state snapshots
    - Historical data aggregation
    """

    model = DailySnapshot

    async def get_latest(self) -> DailySnapshot | None:
        """Get most recent snapshot.

        @returns Latest DailySnapshot or None
        """
        stmt = select(self.model).order_by(desc(self.model.snapshot_time)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history(
        self,
        start_time: datetime,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[DailySnapshot]:
        """Get snapshot history within time range.

        @param start_time - Start of time range
        @param end_time - End of time range (default: now)
        @param limit - Maximum results
        @returns List of snapshots ordered by time ascending
        """
        end_time = end_time or datetime.utcnow()
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.snapshot_time >= start_time,
                    self.model.snapshot_time <= end_time,
                )
            )
            .order_by(self.model.snapshot_time)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_history_by_days(
        self, days: int, limit: int = 1000
    ) -> Sequence[DailySnapshot]:
        """Get snapshot history for past N days.

        @param days - Number of days to look back
        @param limit - Maximum results
        @returns List of snapshots
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        return await self.get_history(start_time=start_time, limit=limit)

    async def get_nav_at_time(self, target_time: datetime) -> Decimal | None:
        """Get NAV (share price) closest to specified time.

        @param target_time - Target timestamp
        @returns Share price or None
        """
        # Try to find exact or closest earlier snapshot
        stmt = (
            select(self.model.share_price)
            .where(self.model.snapshot_time <= target_time)
            .order_by(desc(self.model.snapshot_time))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_nav_range(
        self, start_time: datetime, end_time: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get NAV values within time range.

        @param start_time - Start of time range
        @param end_time - End of time range (default: now)
        @returns List of {time, nav} dictionaries
        """
        end_time = end_time or datetime.utcnow()
        stmt = (
            select(self.model.snapshot_time, self.model.share_price)
            .where(
                and_(
                    self.model.snapshot_time >= start_time,
                    self.model.snapshot_time <= end_time,
                )
            )
            .order_by(self.model.snapshot_time)
        )
        result = await self.session.execute(stmt)
        return [{"time": row[0], "nav": row[1]} for row in result.all()]

    async def get_aum_history(
        self, start_time: datetime, end_time: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get total assets history within time range.

        @param start_time - Start of time range
        @param end_time - End of time range (default: now)
        @returns List of {time, aum} dictionaries
        """
        end_time = end_time or datetime.utcnow()
        stmt = (
            select(self.model.snapshot_time, self.model.total_assets)
            .where(
                and_(
                    self.model.snapshot_time >= start_time,
                    self.model.snapshot_time <= end_time,
                )
            )
            .order_by(self.model.snapshot_time)
        )
        result = await self.session.execute(stmt)
        return [{"time": row[0], "aum": row[1]} for row in result.all()]

    async def get_tier_ratios_latest(self) -> dict[str, Decimal] | None:
        """Get latest tier allocation ratios.

        @returns Dictionary of tier -> ratio or None
        """
        latest = await self.get_latest()
        if latest is None:
            return None
        return {
            "L1": latest.layer1_ratio,
            "L2": latest.layer2_ratio,
            "L3": latest.layer3_ratio,
        }

    async def count_snapshots(
        self, start_time: datetime, end_time: datetime | None = None
    ) -> int:
        """Count snapshots in time range.

        @param start_time - Start of time range
        @param end_time - End of time range (default: now)
        @returns Number of snapshots
        """
        end_time = end_time or datetime.utcnow()
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                and_(
                    self.model.snapshot_time >= start_time,
                    self.model.snapshot_time <= end_time,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0


class RiskMetricsRepository(BaseRepository[RiskMetricsSeries]):
    """Repository for RiskMetricsSeries database operations.

    Handles risk metrics time-series queries.
    """

    model = RiskMetricsSeries

    async def get_latest(self) -> RiskMetricsSeries | None:
        """Get most recent risk metrics.

        @returns Latest RiskMetricsSeries or None
        """
        stmt = select(self.model).order_by(desc(self.model.metric_time)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_history(
        self,
        start_time: datetime,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[RiskMetricsSeries]:
        """Get risk metrics history within time range.

        @param start_time - Start of time range
        @param end_time - End of time range (default: now)
        @param limit - Maximum results
        @returns List of risk metrics ordered by time ascending
        """
        end_time = end_time or datetime.utcnow()
        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.metric_time >= start_time,
                    self.model.metric_time <= end_time,
                )
            )
            .order_by(self.model.metric_time)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_risk_score_history(
        self, days: int
    ) -> list[dict[str, Any]]:
        """Get risk score history for past N days.

        @param days - Number of days to look back
        @returns List of {time, score, level} dictionaries
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(
                self.model.metric_time,
                self.model.risk_score,
                self.model.risk_level,
            )
            .where(self.model.metric_time >= start_time)
            .order_by(self.model.metric_time)
        )
        result = await self.session.execute(stmt)
        return [
            {"time": row[0], "score": row[1], "level": row[2]}
            for row in result.all()
        ]
