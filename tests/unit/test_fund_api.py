"""Tests for Fund Overview API endpoints."""

from decimal import Decimal

import pytest


class TestFundOverview:
    """Tests for fund overview endpoint."""

    def test_get_overview(self):
        """Test getting fund overview."""
        from app.api.v1.endpoints.fund import get_fund_overview
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fund_overview()
        )

        assert result.fund_name == "Paimon Prime Fund"
        assert result.fund_symbol == "PPF"
        assert result.total_aum > 0
        assert result.current_nav > 0

    def test_overview_has_holder_count(self):
        """Test overview includes holder count."""
        from app.api.v1.endpoints.fund import get_fund_overview
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fund_overview()
        )

        assert result.holder_count > 0

    def test_overview_has_changes(self):
        """Test overview includes NAV changes."""
        from app.api.v1.endpoints.fund import get_fund_overview
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fund_overview()
        )

        assert result.nav_24h_change is not None
        assert result.nav_7d_change is not None
        assert result.nav_30d_change is not None


class TestYieldMetrics:
    """Tests for yield metrics endpoint."""

    def test_get_yields(self):
        """Test getting yield metrics."""
        from app.api.v1.endpoints.fund import get_yield_metrics
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_yield_metrics()
        )

        assert result.apy_7d is not None
        assert result.apy_30d is not None
        assert result.apy_90d is not None

    def test_yields_has_cumulative(self):
        """Test yields include cumulative."""
        from app.api.v1.endpoints.fund import get_yield_metrics
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_yield_metrics()
        )

        assert result.cumulative_yield is not None


class TestNAVHistory:
    """Tests for NAV history endpoint."""

    def test_get_nav_history_default(self):
        """Test getting NAV history with default range."""
        from app.api.v1.endpoints.fund import get_nav_history, TimeRange
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_nav_history(time_range=TimeRange.MONTH_1)
        )

        assert result.time_range == TimeRange.MONTH_1
        assert len(result.data_points) > 0

    def test_nav_history_1_day(self):
        """Test 1-day NAV history."""
        from app.api.v1.endpoints.fund import get_nav_history, TimeRange
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_nav_history(time_range=TimeRange.DAY_1)
        )

        assert result.time_range == TimeRange.DAY_1
        assert len(result.data_points) == 24  # Hourly for 1 day

    def test_nav_history_has_high_low(self):
        """Test NAV history includes high/low."""
        from app.api.v1.endpoints.fund import get_nav_history, TimeRange
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_nav_history(time_range=TimeRange.WEEK_1)
        )

        assert result.high_nav >= result.low_nav
        assert result.high_nav >= result.start_nav or result.high_nav >= result.end_nav

    def test_nav_data_point_structure(self):
        """Test NAV data point has correct structure."""
        from app.api.v1.endpoints.fund import get_nav_history, TimeRange
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_nav_history(time_range=TimeRange.MONTH_1)
        )

        if result.data_points:
            point = result.data_points[0]
            assert point.timestamp is not None
            assert point.nav > 0
            assert point.aum > 0


class TestAssetAllocations:
    """Tests for asset allocations endpoint."""

    def test_get_asset_allocations(self):
        """Test getting asset allocations."""
        from app.api.v1.endpoints.fund import get_asset_allocations
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_asset_allocations()
        )

        assert len(result) > 0

    def test_allocations_sum_to_100(self):
        """Test allocations sum to approximately 100%."""
        from app.api.v1.endpoints.fund import get_asset_allocations
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_asset_allocations()
        )

        total = sum(a.allocation_percent for a in result)
        assert Decimal("99.0") <= total <= Decimal("101.0")

    def test_allocation_has_tier(self):
        """Test each allocation has liquidity tier."""
        from app.api.v1.endpoints.fund import get_asset_allocations
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_asset_allocations()
        )

        for allocation in result:
            assert allocation.liquidity_tier in ["L1", "L2", "L3"]


class TestTierAllocations:
    """Tests for tier allocations endpoint."""

    def test_get_tier_allocations(self):
        """Test getting tier allocations."""
        from app.api.v1.endpoints.fund import get_tier_allocations
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_tier_allocations()
        )

        assert len(result) == 3  # L1, L2, L3
        tiers = [t.tier for t in result]
        assert "L1" in tiers
        assert "L2" in tiers
        assert "L3" in tiers

    def test_tier_has_deviation(self):
        """Test tier allocation includes deviation from target."""
        from app.api.v1.endpoints.fund import get_tier_allocations
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_tier_allocations()
        )

        for tier in result:
            assert tier.target_percent is not None
            assert tier.deviation is not None


class TestFeeStructure:
    """Tests for fee structure endpoint."""

    def test_get_fee_structure(self):
        """Test getting fee structure."""
        from app.api.v1.endpoints.fund import get_fee_structure
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fee_structure()
        )

        assert result.management_fee is not None
        assert result.performance_fee is not None

    def test_fee_structure_has_minimums(self):
        """Test fee structure includes minimums."""
        from app.api.v1.endpoints.fund import get_fee_structure
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fee_structure()
        )

        assert result.min_subscription > 0
        assert result.min_redemption > 0

    def test_fee_structure_has_periods(self):
        """Test fee structure includes notice/lock-up periods."""
        from app.api.v1.endpoints.fund import get_fee_structure
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fee_structure()
        )

        assert result.redemption_notice_days >= 0
        assert result.lock_up_days >= 0


class TestPerformanceMetrics:
    """Tests for performance metrics endpoint."""

    def test_get_performance(self):
        """Test getting performance metrics."""
        from app.api.v1.endpoints.fund import get_performance_metrics
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_performance_metrics()
        )

        assert result.return_1d is not None
        assert result.return_7d is not None
        assert result.return_30d is not None

    def test_performance_has_risk_metrics(self):
        """Test performance includes risk metrics."""
        from app.api.v1.endpoints.fund import get_performance_metrics
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_performance_metrics()
        )

        assert result.volatility_30d is not None
        assert result.sharpe_ratio is not None
        assert result.max_drawdown is not None


class TestFlowMetrics:
    """Tests for flow metrics endpoint."""

    def test_get_flows(self):
        """Test getting flow metrics."""
        from app.api.v1.endpoints.fund import get_flow_metrics
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_flow_metrics()
        )

        assert result.subscriptions_24h is not None
        assert result.redemptions_24h is not None
        assert result.net_flow_24h is not None

    def test_flows_has_pending(self):
        """Test flows include pending redemptions."""
        from app.api.v1.endpoints.fund import get_flow_metrics
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_flow_metrics()
        )

        assert result.pending_redemptions is not None


class TestFundSummary:
    """Tests for fund summary endpoint."""

    def test_get_summary(self):
        """Test getting fund summary."""
        from app.api.v1.endpoints.fund import get_fund_summary
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fund_summary()
        )

        assert "overview" in result
        assert "yields" in result
        assert "performance" in result
        assert "flows" in result

    def test_summary_has_timestamp(self):
        """Test summary includes generation timestamp."""
        from app.api.v1.endpoints.fund import get_fund_summary
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            get_fund_summary()
        )

        assert "generated_at" in result


class TestCaching:
    """Tests for caching functionality."""

    def test_invalidate_all_cache(self):
        """Test invalidating all cache."""
        from app.api.v1.endpoints.fund import invalidate_cache
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            invalidate_cache(keys=None)
        )

        assert result["status"] == "invalidated"
        assert result["keys"] == "all"

    def test_invalidate_specific_keys(self):
        """Test invalidating specific cache keys."""
        from app.api.v1.endpoints.fund import invalidate_cache
        import asyncio

        keys = ["fund:overview", "fund:yields"]
        result = asyncio.get_event_loop().run_until_complete(
            invalidate_cache(keys=keys)
        )

        assert result["status"] == "invalidated"
        assert result["keys"] == keys

    def test_cache_returns_same_data(self):
        """Test that cached data is returned on subsequent calls."""
        from app.api.v1.endpoints.fund import get_fund_overview, invalidate_cache
        import asyncio

        # Invalidate first to ensure fresh data
        asyncio.get_event_loop().run_until_complete(
            invalidate_cache(keys=["fund:overview"])
        )

        # First call
        result1 = asyncio.get_event_loop().run_until_complete(
            get_fund_overview()
        )

        # Second call (should be cached)
        result2 = asyncio.get_event_loop().run_until_complete(
            get_fund_overview()
        )

        # Last updated should be the same (cached)
        assert result1.last_updated == result2.last_updated
