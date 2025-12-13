"""Performance tests for the backend services."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.redemption import (
    get_redemption_service,
    RedemptionCreate,
    RedemptionChannel,
    RedemptionFilterParams,
)
from app.services.rebalance import get_rebalance_strategy_engine, TierState, LiquidityTier
from app.services.risk import get_risk_monitor_service
from app.services.reports import ReportGenerator
from app.services.metrics import get_metrics_collector
from app.services.security import get_rate_limiter, get_ip_filter


class TestRedemptionPerformance:
    """Performance tests for redemption service."""

    @pytest.mark.asyncio
    async def test_redemption_creation_time(self):
        """Test redemption creation performance."""
        service = get_redemption_service()
        now = datetime.utcnow()

        start = time.time()
        for i in range(50):
            data = RedemptionCreate(
                request_id=Decimal(i),
                tx_hash=f"0x{'a' * 64}",
                block_number=1000000 + i,
                log_index=i,
                owner=f"0x{'a' * 40}",
                receiver=f"0x{'a' * 40}",
                shares=Decimal("1000"),
                gross_amount=Decimal("1000"),
                locked_nav=Decimal("1.0"),
                estimated_fee=Decimal("1.0"),
                request_time=now,
                settlement_time=now + timedelta(hours=24),
                channel=RedemptionChannel.STANDARD,
            )
            await service.create_redemption(data)
        elapsed = time.time() - start

        avg_time = elapsed / 50
        assert avg_time < 0.02, f"Redemption creation too slow: {avg_time:.4f}s avg"

    @pytest.mark.asyncio
    async def test_redemption_listing_time(self):
        """Test redemption listing performance."""
        service = get_redemption_service()
        filters = RedemptionFilterParams()

        start = time.time()
        for _ in range(100):
            await service.list_redemptions(filters, page=1, page_size=50)
        elapsed = time.time() - start

        avg_time = elapsed / 100
        assert avg_time < 0.01, f"Redemption listing too slow: {avg_time:.4f}s avg"


class TestRiskPerformance:
    """Performance tests for risk monitoring."""

    def test_risk_assessment_time(self):
        """Test risk assessment performance."""
        monitor = get_risk_monitor_service()

        start = time.time()
        for _ in range(50):
            monitor.perform_assessment(
                l1_value=Decimal("1000000"),
                total_value=Decimal("5000000"),
                pending_redemptions=Decimal("50000"),
                current_nav=Decimal("1.05"),
                nav_24h_change=Decimal("0.01"),
                nav_7d_volatility=Decimal("0.02"),
                asset_allocations={"USDT": Decimal("0.5"), "USDC": Decimal("0.3"), "DAI": Decimal("0.2")},
                pending_count=10,
            )
        elapsed = time.time() - start

        avg_time = elapsed / 50
        assert avg_time < 0.05, f"Risk assessment too slow: {avg_time:.4f}s avg"


class TestRebalancingPerformance:
    """Performance tests for rebalancing."""

    @pytest.fixture
    def tier_states(self):
        """Create test tier states."""
        return [
            TierState(tier=LiquidityTier.L1, value=Decimal("1000000"), ratio=Decimal("0.20")),
            TierState(tier=LiquidityTier.L2, value=Decimal("1500000"), ratio=Decimal("0.30")),
            TierState(tier=LiquidityTier.L3, value=Decimal("2500000"), ratio=Decimal("0.50")),
        ]

    def test_deviation_calculation_time(self, tier_states):
        """Test deviation calculation performance."""
        engine = get_rebalance_strategy_engine()
        total_value = Decimal("5000000")

        start = time.time()
        for _ in range(100):
            engine.calculate_deviations(tier_states, total_value)
        elapsed = time.time() - start

        avg_time = elapsed / 100
        assert avg_time < 0.02, f"Deviation calculation too slow: {avg_time:.4f}s avg"

    def test_plan_generation_time(self, tier_states):
        """Test plan generation performance."""
        engine = get_rebalance_strategy_engine()
        total_value = Decimal("5000000")

        start = time.time()
        for _ in range(20):
            engine.generate_rebalance_plan(tier_states, total_value, "Performance test")
        elapsed = time.time() - start

        avg_time = elapsed / 20
        assert avg_time < 0.1, f"Plan generation too slow: {avg_time:.4f}s avg"


class TestReportPerformance:
    """Performance tests for report generation."""

    def test_daily_report_time(self):
        """Test daily report generation performance."""
        generator = ReportGenerator()

        start = time.time()
        for i in range(10):
            generator.generate_daily_report(date(2024, 6, 15))
        elapsed = time.time() - start

        avg_time = elapsed / 10
        assert avg_time < 0.2, f"Daily report generation too slow: {avg_time:.4f}s avg"

    def test_weekly_report_time(self):
        """Test weekly report generation performance."""
        generator = ReportGenerator()

        start = time.time()
        for i in range(5):
            generator.generate_weekly_report(date(2024, 6, 10))
        elapsed = time.time() - start

        avg_time = elapsed / 5
        assert avg_time < 0.5, f"Weekly report generation too slow: {avg_time:.4f}s avg"


class TestMetricsPerformance:
    """Performance tests for metrics collection."""

    def test_counter_increment_time(self):
        """Test counter increment performance."""
        collector = get_metrics_collector()

        start = time.time()
        for i in range(10000):
            collector.inc_counter("test_counter", labels={"method": "GET"})
        elapsed = time.time() - start

        avg_time = elapsed / 10000 * 1000  # ms
        assert avg_time < 0.1, f"Counter increment too slow: {avg_time:.4f}ms avg"

    def test_histogram_observe_time(self):
        """Test histogram observation performance."""
        collector = get_metrics_collector()

        start = time.time()
        for i in range(1000):
            collector.observe_histogram("test_histogram", i * 0.001)
        elapsed = time.time() - start

        avg_time = elapsed / 1000 * 1000  # ms
        assert avg_time < 0.5, f"Histogram observe too slow: {avg_time:.4f}ms avg"


class TestSecurityPerformance:
    """Performance tests for security services."""

    def test_rate_limit_check_time(self):
        """Test rate limit check performance."""
        limiter = get_rate_limiter()

        start = time.time()
        for i in range(1000):
            limiter.check(f"ip-{i % 100}")
        elapsed = time.time() - start

        avg_time = elapsed / 1000 * 1000  # ms
        assert avg_time < 0.5, f"Rate limit check too slow: {avg_time:.4f}ms avg"

    def test_ip_filter_check_time(self):
        """Test IP filter check performance."""
        ip_filter = get_ip_filter()

        # Add some entries
        for i in range(100):
            ip_filter.add_to_whitelist(f"192.168.1.{i}")

        start = time.time()
        for i in range(1000):
            ip_filter.is_allowed(f"192.168.1.{i % 100}")
        elapsed = time.time() - start

        avg_time = elapsed / 1000 * 1000  # ms
        assert avg_time < 0.5, f"IP filter check too slow: {avg_time:.4f}ms avg"


class TestConcurrency:
    """Concurrency tests."""

    def test_concurrent_risk_assessments(self):
        """Test concurrent risk assessments."""
        monitor = get_risk_monitor_service()

        def assess():
            for _ in range(5):
                monitor.perform_assessment(
                    l1_value=Decimal("1000000"),
                    total_value=Decimal("5000000"),
                    pending_redemptions=Decimal("50000"),
                    current_nav=Decimal("1.05"),
                    nav_24h_change=Decimal("0.01"),
                    nav_7d_volatility=Decimal("0.02"),
                    asset_allocations={"USDT": Decimal("0.5"), "USDC": Decimal("0.3"), "DAI": Decimal("0.2")},
                    pending_count=10,
                )

        with ThreadPoolExecutor(max_workers=5) as executor:
            start = time.time()
            futures = [executor.submit(assess) for _ in range(5)]
            for future in futures:
                future.result()
            elapsed = time.time() - start

        assert elapsed < 2.0, f"Concurrent risk assessments too slow: {elapsed:.2f}s"

    def test_concurrent_metric_collection(self):
        """Test concurrent metric collection."""
        collector = get_metrics_collector()

        def collect():
            for i in range(100):
                collector.inc_counter("concurrent_test")
                collector.set_gauge("concurrent_gauge", i)

        with ThreadPoolExecutor(max_workers=10) as executor:
            start = time.time()
            futures = [executor.submit(collect) for _ in range(10)]
            for future in futures:
                future.result()
            elapsed = time.time() - start

        assert elapsed < 1.0, f"Concurrent metrics too slow: {elapsed:.2f}s"


class TestLatency:
    """Latency tests."""

    def test_api_response_latency_simulation(self):
        """Test simulated API response latency."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        latencies = []
        for _ in range(20):
            start = time.time()
            response = client.get("/health")
            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)
            assert response.status_code == 200

        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        assert avg_latency < 50, f"Average latency too high: {avg_latency:.2f}ms"
        assert p95_latency < 100, f"P95 latency too high: {p95_latency:.2f}ms"
