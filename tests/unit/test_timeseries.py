"""Test cases for TimescaleDB time-series models."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest


class TestDailySnapshot:
    """Test DailySnapshot model."""

    def test_daily_snapshot_creation(self):
        """Test creating a daily snapshot."""
        from app.models.timeseries import DailySnapshot

        snapshot = DailySnapshot(
            snapshot_time=datetime.now(timezone.utc),
            total_assets=Decimal("12345678000000000000000000"),
            total_supply=Decimal("11728645000000000000000000"),
            share_price=Decimal("1052300000000000000"),
            layer1_value=Decimal("1234567800000000000000000"),
            layer2_value=Decimal("3703703400000000000000000"),
            layer3_value=Decimal("7407406800000000000000000"),
            layer1_ratio=Decimal("0.100000"),
            layer2_ratio=Decimal("0.300000"),
            layer3_ratio=Decimal("0.600000"),
            total_redemption_liability=Decimal("0"),
            total_locked_shares=Decimal("0"),
            emergency_mode=False,
        )

        assert snapshot.emergency_mode is False
        assert snapshot.layer1_ratio == Decimal("0.100000")


class TestRiskMetricsSeries:
    """Test RiskMetricsSeries model."""

    def test_risk_metrics_creation(self):
        """Test creating risk metrics."""
        from app.models.timeseries import RiskMetricsSeries

        metrics = RiskMetricsSeries(
            metric_time=datetime.now(timezone.utc),
            l1_ratio=Decimal("0.10"),
            l1_l2_ratio=Decimal("0.40"),
            redemption_coverage=Decimal("2.5"),
            nav=Decimal("1.05"),
            risk_score=15,
            risk_level="NORMAL",
        )

        assert metrics.risk_level == "NORMAL"
        assert metrics.risk_score == 15


class TestEventProcessingLog:
    """Test EventProcessingLog model."""

    def test_event_processing_log_creation(self):
        """Test creating event processing log."""
        from app.models.timeseries import EventProcessingLog

        log = EventProcessingLog(
            processed_at=datetime.now(timezone.utc),
            tx_hash="0x" + "a" * 64,
            log_index=0,
            block_number=12345678,
            event_name="Deposit",
            contract_address="0x" + "1" * 40,
            status="SUCCESS",
            processing_time_ms=150,
            retry_count=0,
        )

        assert log.status == "SUCCESS"
        assert log.processing_time_ms == 150
