"""TimescaleDB time-series models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailySnapshot(Base):
    """Daily fund state snapshot (TimescaleDB hypertable)."""

    __tablename__ = "daily_snapshots"

    # Time key (primary key for hypertable)
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    # Fund state
    total_assets: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    total_supply: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    share_price: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)

    # Liquidity tiers
    layer1_value: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    layer2_value: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    layer3_value: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    layer1_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    layer2_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    layer3_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    # Liabilities
    total_redemption_liability: Mapped[Decimal] = mapped_column(
        Numeric(78, 0), nullable=False
    )
    total_locked_shares: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)

    # Status
    emergency_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Fees
    accumulated_management_fees: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )
    accumulated_performance_fees: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )
    accumulated_redemption_fees: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )


class AssetHoldingsSnapshot(Base):
    """Asset holdings snapshot (TimescaleDB hypertable)."""

    __tablename__ = "asset_holdings_snapshots"

    # Composite primary key
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    token_address: Mapped[str] = mapped_column(String(42), primary_key=True)

    # Asset info
    token_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    tier: Mapped[str] = mapped_column(String(10), nullable=False)

    # Holdings data
    balance: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    value_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    allocation_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)


class RiskMetricsSeries(Base):
    """Risk metrics time-series (TimescaleDB hypertable)."""

    __tablename__ = "risk_metrics_series"

    # Time key
    metric_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    # Liquidity indicators
    l1_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    l1_l2_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    redemption_coverage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )

    # Price indicators
    nav: Mapped[Optional[Decimal]] = mapped_column(Numeric(38, 18), nullable=True)
    nav_change_24h: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )

    # Concentration indicators
    max_asset_concentration: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    top3_concentration: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )

    # Redemption indicators
    pending_redemption_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    pending_redemption_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )
    daily_redemption_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )

    # Composite score
    risk_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


class EventProcessingLog(Base):
    """Event processing log (TimescaleDB hypertable)."""

    __tablename__ = "event_processing_logs"

    # Composite primary key
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    tx_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    log_index: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Event info
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)

    # Processing status
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry info
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
