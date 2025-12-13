"""Fund overview API endpoints."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/fund", tags=["Fund Overview"])


# Enums
class TimeRange(str, Enum):
    """Time range for historical data."""

    DAY_1 = "1D"
    WEEK_1 = "1W"
    MONTH_1 = "1M"
    MONTH_3 = "3M"
    MONTH_6 = "6M"
    YEAR_1 = "1Y"
    ALL = "ALL"


# Response models
class FundOverview(BaseModel):
    """Fund overview data."""

    fund_name: str = Field(..., description="Fund name")
    fund_symbol: str = Field(..., description="Fund symbol")
    total_aum: Decimal = Field(..., description="Total AUM")
    current_nav: Decimal = Field(..., description="Current NAV")
    nav_24h_change: Decimal = Field(..., description="24h NAV change %")
    nav_7d_change: Decimal = Field(..., description="7d NAV change %")
    nav_30d_change: Decimal = Field(..., description="30d NAV change %")
    total_supply: Decimal = Field(..., description="Total token supply")
    holder_count: int = Field(..., description="Number of holders")
    inception_date: date = Field(..., description="Fund inception date")
    last_updated: datetime = Field(..., description="Last update time")


class YieldMetrics(BaseModel):
    """Yield metrics."""

    apy_7d: Decimal = Field(..., description="7-day APY")
    apy_30d: Decimal = Field(..., description="30-day APY")
    apy_90d: Decimal = Field(..., description="90-day APY")
    apy_ytd: Decimal = Field(..., description="Year-to-date APY")
    cumulative_yield: Decimal = Field(..., description="Cumulative yield since inception")
    next_distribution_date: date | None = Field(None, description="Next distribution date")


class NAVDataPoint(BaseModel):
    """Single NAV data point."""

    timestamp: datetime = Field(..., description="Timestamp")
    nav: Decimal = Field(..., description="NAV value")
    aum: Decimal = Field(..., description="AUM at timestamp")


class NAVHistory(BaseModel):
    """NAV history data."""

    time_range: TimeRange = Field(..., description="Time range")
    start_nav: Decimal = Field(..., description="NAV at start")
    end_nav: Decimal = Field(..., description="NAV at end")
    high_nav: Decimal = Field(..., description="Highest NAV")
    low_nav: Decimal = Field(..., description="Lowest NAV")
    change_percent: Decimal = Field(..., description="Change percentage")
    data_points: list[NAVDataPoint] = Field(..., description="NAV data points")


class AssetAllocation(BaseModel):
    """Asset allocation data."""

    asset_name: str = Field(..., description="Asset name")
    asset_symbol: str = Field(..., description="Asset symbol")
    value: Decimal = Field(..., description="Value in USD")
    allocation_percent: Decimal = Field(..., description="Allocation percentage")
    chain: str = Field(..., description="Blockchain")
    protocol: str | None = Field(None, description="DeFi protocol if applicable")
    apy: Decimal | None = Field(None, description="Current APY if applicable")
    liquidity_tier: str = Field(..., description="Liquidity tier (L1/L2/L3)")


class TierAllocation(BaseModel):
    """Liquidity tier allocation."""

    tier: str = Field(..., description="Tier name")
    value: Decimal = Field(..., description="Tier value")
    allocation_percent: Decimal = Field(..., description="Allocation percentage")
    asset_count: int = Field(..., description="Number of assets")
    target_percent: Decimal = Field(..., description="Target allocation")
    deviation: Decimal = Field(..., description="Deviation from target")


class FeeStructure(BaseModel):
    """Fund fee structure."""

    management_fee: Decimal = Field(..., description="Annual management fee %")
    performance_fee: Decimal = Field(..., description="Performance fee %")
    entry_fee: Decimal = Field(..., description="Entry/subscription fee %")
    exit_fee: Decimal = Field(..., description="Exit/redemption fee %")
    min_subscription: Decimal = Field(..., description="Minimum subscription amount")
    min_redemption: Decimal = Field(..., description="Minimum redemption amount")
    redemption_notice_days: int = Field(..., description="Redemption notice period")
    lock_up_days: int = Field(..., description="Lock-up period")


class PerformanceMetrics(BaseModel):
    """Performance metrics."""

    return_1d: Decimal = Field(..., description="1-day return")
    return_7d: Decimal = Field(..., description="7-day return")
    return_30d: Decimal = Field(..., description="30-day return")
    return_90d: Decimal = Field(..., description="90-day return")
    return_ytd: Decimal = Field(..., description="Year-to-date return")
    return_inception: Decimal = Field(..., description="Return since inception")
    volatility_30d: Decimal = Field(..., description="30-day volatility")
    sharpe_ratio: Decimal = Field(..., description="Sharpe ratio")
    max_drawdown: Decimal = Field(..., description="Maximum drawdown")


class FlowMetrics(BaseModel):
    """Fund flow metrics."""

    subscriptions_24h: Decimal = Field(..., description="24h subscriptions")
    redemptions_24h: Decimal = Field(..., description="24h redemptions")
    net_flow_24h: Decimal = Field(..., description="24h net flow")
    subscriptions_7d: Decimal = Field(..., description="7d subscriptions")
    redemptions_7d: Decimal = Field(..., description="7d redemptions")
    net_flow_7d: Decimal = Field(..., description="7d net flow")
    pending_redemptions: Decimal = Field(..., description="Pending redemptions")


# In-memory cache simulation (in production, use Redis)
class FundDataCache:
    """Simple in-memory cache for fund data."""

    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._expiry: dict[str, datetime] = {}

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None
        if datetime.now(timezone.utc) > self._expiry.get(key, datetime.min.replace(tzinfo=timezone.utc)):
            del self._cache[key]
            del self._expiry[key]
            return None
        return self._cache[key]

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        """Set cached value with TTL."""
        self._cache[key] = value
        self._expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    def invalidate(self, key: str) -> None:
        """Invalidate cache entry."""
        self._cache.pop(key, None)
        self._expiry.pop(key, None)


# Global cache
_cache = FundDataCache()


# Mock data generators (in production, fetch from database)
def _generate_fund_overview() -> FundOverview:
    """Generate mock fund overview."""
    return FundOverview(
        fund_name="Paimon Prime Fund",
        fund_symbol="PPF",
        total_aum=Decimal("25000000.00"),
        current_nav=Decimal("1.0523"),
        nav_24h_change=Decimal("0.0012"),
        nav_7d_change=Decimal("0.0078"),
        nav_30d_change=Decimal("0.0234"),
        total_supply=Decimal("23755000.00"),
        holder_count=1250,
        inception_date=date(2024, 1, 15),
        last_updated=datetime.now(timezone.utc),
    )


def _generate_yield_metrics() -> YieldMetrics:
    """Generate mock yield metrics."""
    return YieldMetrics(
        apy_7d=Decimal("4.56"),
        apy_30d=Decimal("5.12"),
        apy_90d=Decimal("5.45"),
        apy_ytd=Decimal("5.23"),
        cumulative_yield=Decimal("5.23"),
        next_distribution_date=date.today() + timedelta(days=15),
    )


def _generate_nav_history(time_range: TimeRange) -> NAVHistory:
    """Generate mock NAV history."""
    now = datetime.now(timezone.utc)
    base_nav = Decimal("1.00")

    # Determine number of points based on range
    points_map = {
        TimeRange.DAY_1: 24,
        TimeRange.WEEK_1: 7 * 24,
        TimeRange.MONTH_1: 30,
        TimeRange.MONTH_3: 90,
        TimeRange.MONTH_6: 180,
        TimeRange.YEAR_1: 365,
        TimeRange.ALL: 365,
    }
    num_points = min(points_map.get(time_range, 30), 100)  # Limit for response size

    # Generate data points
    data_points = []
    current_nav = base_nav
    aum_base = Decimal("25000000")

    for i in range(num_points):
        # Small random-ish walk
        change = Decimal(str(0.0001 * (i % 10 - 5)))
        current_nav = current_nav + change
        current_nav = max(Decimal("0.95"), min(Decimal("1.10"), current_nav))

        ts = now - timedelta(hours=num_points - i)
        data_points.append(NAVDataPoint(
            timestamp=ts,
            nav=current_nav,
            aum=aum_base + (current_nav - Decimal("1.00")) * aum_base,
        ))

    navs = [dp.nav for dp in data_points]
    return NAVHistory(
        time_range=time_range,
        start_nav=navs[0] if navs else base_nav,
        end_nav=navs[-1] if navs else base_nav,
        high_nav=max(navs) if navs else base_nav,
        low_nav=min(navs) if navs else base_nav,
        change_percent=((navs[-1] - navs[0]) / navs[0] * 100) if navs else Decimal(0),
        data_points=data_points,
    )


def _generate_asset_allocations() -> list[AssetAllocation]:
    """Generate mock asset allocations."""
    return [
        AssetAllocation(
            asset_name="USD Coin",
            asset_symbol="USDC",
            value=Decimal("5000000"),
            allocation_percent=Decimal("20.00"),
            chain="BSC",
            protocol=None,
            apy=None,
            liquidity_tier="L1",
        ),
        AssetAllocation(
            asset_name="Tether USD",
            asset_symbol="USDT",
            value=Decimal("3750000"),
            allocation_percent=Decimal("15.00"),
            chain="BSC",
            protocol=None,
            apy=None,
            liquidity_tier="L1",
        ),
        AssetAllocation(
            asset_name="Venus USDC",
            asset_symbol="vUSDC",
            value=Decimal("5000000"),
            allocation_percent=Decimal("20.00"),
            chain="BSC",
            protocol="Venus",
            apy=Decimal("4.5"),
            liquidity_tier="L2",
        ),
        AssetAllocation(
            asset_name="Alpaca BUSD",
            asset_symbol="ibBUSD",
            value=Decimal("5000000"),
            allocation_percent=Decimal("20.00"),
            chain="BSC",
            protocol="Alpaca Finance",
            apy=Decimal("6.2"),
            liquidity_tier="L2",
        ),
        AssetAllocation(
            asset_name="Goldfinch Senior Pool",
            asset_symbol="FIDU",
            value=Decimal("6250000"),
            allocation_percent=Decimal("25.00"),
            chain="Ethereum",
            protocol="Goldfinch",
            apy=Decimal("8.5"),
            liquidity_tier="L3",
        ),
    ]


def _generate_tier_allocations() -> list[TierAllocation]:
    """Generate mock tier allocations."""
    return [
        TierAllocation(
            tier="L1",
            value=Decimal("8750000"),
            allocation_percent=Decimal("35.00"),
            asset_count=2,
            target_percent=Decimal("30.00"),
            deviation=Decimal("5.00"),
        ),
        TierAllocation(
            tier="L2",
            value=Decimal("10000000"),
            allocation_percent=Decimal("40.00"),
            asset_count=2,
            target_percent=Decimal("40.00"),
            deviation=Decimal("0.00"),
        ),
        TierAllocation(
            tier="L3",
            value=Decimal("6250000"),
            allocation_percent=Decimal("25.00"),
            asset_count=1,
            target_percent=Decimal("30.00"),
            deviation=Decimal("-5.00"),
        ),
    ]


def _generate_fee_structure() -> FeeStructure:
    """Generate mock fee structure."""
    return FeeStructure(
        management_fee=Decimal("1.00"),
        performance_fee=Decimal("10.00"),
        entry_fee=Decimal("0.00"),
        exit_fee=Decimal("0.10"),
        min_subscription=Decimal("1000.00"),
        min_redemption=Decimal("100.00"),
        redemption_notice_days=3,
        lock_up_days=0,
    )


def _generate_performance_metrics() -> PerformanceMetrics:
    """Generate mock performance metrics."""
    return PerformanceMetrics(
        return_1d=Decimal("0.12"),
        return_7d=Decimal("0.78"),
        return_30d=Decimal("2.34"),
        return_90d=Decimal("4.56"),
        return_ytd=Decimal("5.23"),
        return_inception=Decimal("5.23"),
        volatility_30d=Decimal("1.23"),
        sharpe_ratio=Decimal("2.45"),
        max_drawdown=Decimal("-2.10"),
    )


def _generate_flow_metrics() -> FlowMetrics:
    """Generate mock flow metrics."""
    return FlowMetrics(
        subscriptions_24h=Decimal("150000"),
        redemptions_24h=Decimal("75000"),
        net_flow_24h=Decimal("75000"),
        subscriptions_7d=Decimal("1200000"),
        redemptions_7d=Decimal("450000"),
        net_flow_7d=Decimal("750000"),
        pending_redemptions=Decimal("125000"),
    )


# Endpoints
@router.get("/overview", response_model=FundOverview)
async def get_fund_overview() -> FundOverview:
    """Get fund overview.

    Returns AUM, NAV, supply, and holder information.
    Cached for 60 seconds.
    """
    cache_key = "fund:overview"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_fund_overview()
    _cache.set(cache_key, data, ttl_seconds=60)
    return data


@router.get("/yields", response_model=YieldMetrics)
async def get_yield_metrics() -> YieldMetrics:
    """Get yield metrics.

    Returns APY across different time periods.
    Cached for 5 minutes.
    """
    cache_key = "fund:yields"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_yield_metrics()
    _cache.set(cache_key, data, ttl_seconds=300)
    return data


@router.get("/nav/history", response_model=NAVHistory)
async def get_nav_history(
    time_range: TimeRange = Query(TimeRange.MONTH_1, description="Time range"),
) -> NAVHistory:
    """Get NAV history.

    Returns historical NAV data points for charting.
    Cached for 5 minutes.
    """
    cache_key = f"fund:nav:{time_range.value}"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_nav_history(time_range)
    _cache.set(cache_key, data, ttl_seconds=300)
    return data


@router.get("/allocations/assets", response_model=list[AssetAllocation])
async def get_asset_allocations() -> list[AssetAllocation]:
    """Get asset allocations.

    Returns detailed breakdown of fund assets.
    Cached for 5 minutes.
    """
    cache_key = "fund:allocations:assets"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_asset_allocations()
    _cache.set(cache_key, data, ttl_seconds=300)
    return data


@router.get("/allocations/tiers", response_model=list[TierAllocation])
async def get_tier_allocations() -> list[TierAllocation]:
    """Get liquidity tier allocations.

    Returns allocation breakdown by liquidity tier.
    Cached for 5 minutes.
    """
    cache_key = "fund:allocations:tiers"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_tier_allocations()
    _cache.set(cache_key, data, ttl_seconds=300)
    return data


@router.get("/fees", response_model=FeeStructure)
async def get_fee_structure() -> FeeStructure:
    """Get fee structure.

    Returns fund fee information.
    Cached for 1 hour.
    """
    cache_key = "fund:fees"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_fee_structure()
    _cache.set(cache_key, data, ttl_seconds=3600)
    return data


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics() -> PerformanceMetrics:
    """Get performance metrics.

    Returns returns, volatility, and risk-adjusted metrics.
    Cached for 5 minutes.
    """
    cache_key = "fund:performance"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_performance_metrics()
    _cache.set(cache_key, data, ttl_seconds=300)
    return data


@router.get("/flows", response_model=FlowMetrics)
async def get_flow_metrics() -> FlowMetrics:
    """Get fund flow metrics.

    Returns subscription and redemption flow data.
    Cached for 1 minute.
    """
    cache_key = "fund:flows"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    data = _generate_flow_metrics()
    _cache.set(cache_key, data, ttl_seconds=60)
    return data


@router.post("/cache/invalidate")
async def invalidate_cache(keys: list[str] | None = None) -> dict[str, Any]:
    """Invalidate cache entries.

    Args:
        keys: Specific cache keys to invalidate. If None, invalidates all.
    """
    if keys is None:
        # Invalidate all fund cache
        all_keys = [
            "fund:overview", "fund:yields", "fund:fees",
            "fund:performance", "fund:flows",
            "fund:allocations:assets", "fund:allocations:tiers",
        ]
        for k in all_keys:
            _cache.invalidate(k)
        # Also invalidate NAV history
        for tr in TimeRange:
            _cache.invalidate(f"fund:nav:{tr.value}")
        return {"status": "invalidated", "keys": "all"}

    for key in keys:
        _cache.invalidate(key)
    return {"status": "invalidated", "keys": keys}


@router.get("/summary")
async def get_fund_summary() -> dict[str, Any]:
    """Get complete fund summary.

    Returns overview, yields, performance, and flows in one call.
    """
    overview = await get_fund_overview()
    yields = await get_yield_metrics()
    performance = await get_performance_metrics()
    flows = await get_flow_metrics()

    return {
        "overview": overview.model_dump(),
        "yields": yields.model_dump(),
        "performance": performance.model_dump(),
        "flows": flows.model_dump(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
