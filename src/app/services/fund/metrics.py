"""Fund metrics calculation service.

Provides calculations for yield, performance, and risk metrics.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories import DailySnapshotRepository
from app.models.timeseries import DailySnapshot

logger = logging.getLogger(__name__)
settings = get_settings()


class FundMetricsService:
    """Service for calculating fund performance metrics.

    Calculates returns, APY, volatility, and max drawdown from
    historical snapshot data.
    """

    def __init__(self, session: AsyncSession | None = None):
        """Initialize FundMetricsService.

        @param session - Optional SQLAlchemy async session
        """
        self._session = session
        self._owned_session = session is None

    async def _get_session(self) -> AsyncSession:
        """Get or create database session."""
        if self._session is not None:
            return self._session
        return AsyncSessionLocal()

    async def _close_session(self, session: AsyncSession) -> None:
        """Close session if we own it."""
        if self._owned_session and session is not self._session:
            await session.close()

    async def _get_snapshots(self, days: int) -> Sequence[DailySnapshot]:
        """Get snapshots for calculation period."""
        session = await self._get_session()
        try:
            repo = DailySnapshotRepository(session)
            return await repo.get_history_by_days(days)
        finally:
            await self._close_session(session)

    # ==========================================================================
    # Return Calculations
    # ==========================================================================

    async def calculate_return(self, days: int) -> Decimal:
        """Calculate period return as percentage.

        @param days - Number of days for calculation
        @returns Return percentage (e.g., 2.5 for 2.5%)
        """
        snapshots = await self._get_snapshots(days)
        if len(snapshots) < 2:
            return Decimal(0)

        start_price = snapshots[0].share_price
        end_price = snapshots[-1].share_price

        if start_price == 0:
            return Decimal(0)

        return (end_price - start_price) / start_price * Decimal(100)

    async def calculate_apy(self, days: int) -> Decimal:
        """Calculate annualized APY.

        @param days - Number of days for calculation
        @returns Annualized percentage yield
        """
        period_return = await self.calculate_return(days)
        if days == 0:
            return Decimal(0)

        # Annualize the return
        return period_return * Decimal(365) / Decimal(days)

    # ==========================================================================
    # Risk Metrics
    # ==========================================================================

    async def calculate_volatility(self, days: int) -> Decimal:
        """Calculate annualized volatility (standard deviation of returns).

        @param days - Number of days for calculation
        @returns Annualized volatility as percentage
        """
        snapshots = await self._get_snapshots(days)
        if len(snapshots) < 3:
            return Decimal(0)

        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(snapshots)):
            if snapshots[i - 1].share_price > 0:
                ret = (
                    snapshots[i].share_price - snapshots[i - 1].share_price
                ) / snapshots[i - 1].share_price
                daily_returns.append(ret)

        if len(daily_returns) < 2:
            return Decimal(0)

        # Calculate standard deviation
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / (
            len(daily_returns) - 1
        )
        std_dev = variance ** Decimal("0.5")

        # Annualize (sqrt(365) factor)
        annualized_vol = std_dev * Decimal("365") ** Decimal("0.5") * Decimal(100)
        return annualized_vol

    async def calculate_max_drawdown(self, days: int) -> Decimal:
        """Calculate maximum drawdown over period.

        @param days - Number of days for calculation
        @returns Maximum drawdown as percentage (negative)
        """
        snapshots = await self._get_snapshots(days)
        if len(snapshots) < 2:
            return Decimal(0)

        prices = [s.share_price for s in snapshots]
        max_drawdown = Decimal(0)
        peak = prices[0]

        for price in prices[1:]:
            if price > peak:
                peak = price
            drawdown = (price - peak) / peak
            if drawdown < max_drawdown:
                max_drawdown = drawdown

        return max_drawdown * Decimal(100)

    async def calculate_sharpe_ratio(
        self, days: int, risk_free_rate: Decimal = Decimal("0.02")
    ) -> Decimal:
        """Calculate Sharpe ratio.

        @param days - Number of days for calculation
        @param risk_free_rate - Annual risk-free rate (default 2%)
        @returns Sharpe ratio
        """
        apy = await self.calculate_apy(days)
        volatility = await self.calculate_volatility(days)

        if volatility == 0:
            return Decimal(0)

        excess_return = apy / Decimal(100) - risk_free_rate
        sharpe = excess_return / (volatility / Decimal(100))
        return sharpe

    # ==========================================================================
    # Aggregated Metrics
    # ==========================================================================

    async def get_yield_metrics(self) -> dict[str, Any]:
        """Get comprehensive yield metrics.

        Uses FF_YIELD_METRICS_SOURCE to determine data source.

        @returns Dictionary of yield metrics
        """
        if settings.ff_yield_metrics_source == "real":
            try:
                return await self._get_yield_metrics_real()
            except Exception as e:
                logger.warning(f"Real yield metrics failed: {e}, fallback to mock")
        return self._generate_yield_metrics_mock()

    async def _get_yield_metrics_real(self) -> dict[str, Any]:
        """Calculate yield metrics from real data."""
        apy_7d = await self.calculate_apy(7)
        apy_30d = await self.calculate_apy(30)
        apy_90d = await self.calculate_apy(90)
        apy_365d = await self.calculate_apy(365)

        return {
            "current_apy": str(apy_30d.quantize(Decimal("0.01"))),
            "projected_apy": str(apy_7d.quantize(Decimal("0.01"))),
            "apy_7d": str(apy_7d.quantize(Decimal("0.01"))),
            "apy_30d": str(apy_30d.quantize(Decimal("0.01"))),
            "apy_90d": str(apy_90d.quantize(Decimal("0.01"))),
            "apy_365d": str(apy_365d.quantize(Decimal("0.01"))),
            "yield_source": "DeFi Stablecoin Strategies",
        }

    def _generate_yield_metrics_mock(self) -> dict[str, Any]:
        """Generate mock yield metrics data."""
        return {
            "current_apy": "4.56",
            "projected_apy": "5.12",
            "apy_7d": "4.89",
            "apy_30d": "4.56",
            "apy_90d": "4.32",
            "apy_365d": "4.15",
            "yield_source": "DeFi Stablecoin Strategies",
        }

    async def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics.

        @returns Dictionary of performance metrics
        """
        if settings.ff_yield_metrics_source == "real":
            try:
                return await self._get_performance_metrics_real()
            except Exception as e:
                logger.warning(f"Real performance metrics failed: {e}, fallback to mock")
        return self._generate_performance_metrics_mock()

    async def _get_performance_metrics_real(self) -> dict[str, Any]:
        """Calculate performance metrics from real data."""
        return_7d = await self.calculate_return(7)
        return_30d = await self.calculate_return(30)
        return_90d = await self.calculate_return(90)
        return_ytd = await self.calculate_return(365)
        volatility_30d = await self.calculate_volatility(30)
        max_dd = await self.calculate_max_drawdown(90)
        sharpe = await self.calculate_sharpe_ratio(90)

        return {
            "return_7d": str(return_7d.quantize(Decimal("0.01"))),
            "return_30d": str(return_30d.quantize(Decimal("0.01"))),
            "return_90d": str(return_90d.quantize(Decimal("0.01"))),
            "return_ytd": str(return_ytd.quantize(Decimal("0.01"))),
            "volatility_30d": str(volatility_30d.quantize(Decimal("0.01"))),
            "max_drawdown_90d": str(max_dd.quantize(Decimal("0.01"))),
            "sharpe_ratio": str(sharpe.quantize(Decimal("0.01"))),
        }

    def _generate_performance_metrics_mock(self) -> dict[str, Any]:
        """Generate mock performance metrics data."""
        return {
            "return_7d": "0.12",
            "return_30d": "0.45",
            "return_90d": "1.28",
            "return_ytd": "4.56",
            "volatility_30d": "0.85",
            "max_drawdown_90d": "-0.32",
            "sharpe_ratio": "2.15",
        }
