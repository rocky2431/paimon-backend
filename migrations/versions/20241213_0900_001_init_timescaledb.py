"""Initialize TimescaleDB hypertables

Revision ID: 001
Revises: None
Create Date: 2024-12-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # Create daily_snapshots table
    op.create_table(
        "daily_snapshots",
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_assets", sa.Numeric(78, 0), nullable=False),
        sa.Column("total_supply", sa.Numeric(78, 0), nullable=False),
        sa.Column("share_price", sa.Numeric(78, 0), nullable=False),
        sa.Column("layer1_value", sa.Numeric(78, 0), nullable=False),
        sa.Column("layer2_value", sa.Numeric(78, 0), nullable=False),
        sa.Column("layer3_value", sa.Numeric(78, 0), nullable=False),
        sa.Column("layer1_ratio", sa.Numeric(10, 6), nullable=False),
        sa.Column("layer2_ratio", sa.Numeric(10, 6), nullable=False),
        sa.Column("layer3_ratio", sa.Numeric(10, 6), nullable=False),
        sa.Column("total_redemption_liability", sa.Numeric(78, 0), nullable=False),
        sa.Column("total_locked_shares", sa.Numeric(78, 0), nullable=False),
        sa.Column("emergency_mode", sa.Boolean(), nullable=False, default=False),
        sa.Column("accumulated_management_fees", sa.Numeric(78, 0), nullable=True),
        sa.Column("accumulated_performance_fees", sa.Numeric(78, 0), nullable=True),
        sa.Column("accumulated_redemption_fees", sa.Numeric(78, 0), nullable=True),
        sa.PrimaryKeyConstraint("snapshot_time"),
    )

    # Convert to hypertable
    op.execute(
        "SELECT create_hypertable('daily_snapshots', 'snapshot_time', if_not_exists => TRUE)"
    )

    # Add retention policy (2 years)
    op.execute(
        "SELECT add_retention_policy('daily_snapshots', INTERVAL '2 years', if_not_exists => TRUE)"
    )

    # Enable compression (after 30 days)
    op.execute(
        """
        ALTER TABLE daily_snapshots SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = ''
        )
        """
    )
    op.execute(
        "SELECT add_compression_policy('daily_snapshots', INTERVAL '30 days', if_not_exists => TRUE)"
    )

    # Create asset_holdings_snapshots table
    op.create_table(
        "asset_holdings_snapshots",
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_address", sa.String(42), nullable=False),
        sa.Column("token_symbol", sa.String(20), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(78, 0), nullable=False),
        sa.Column("price", sa.Numeric(38, 18), nullable=False),
        sa.Column("value_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("allocation_pct", sa.Numeric(10, 6), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_time", "token_address"),
    )

    # Convert to hypertable
    op.execute(
        "SELECT create_hypertable('asset_holdings_snapshots', 'snapshot_time', if_not_exists => TRUE)"
    )

    # Add retention policy (1 year)
    op.execute(
        "SELECT add_retention_policy('asset_holdings_snapshots', INTERVAL '1 year', if_not_exists => TRUE)"
    )

    # Create risk_metrics_series table
    op.create_table(
        "risk_metrics_series",
        sa.Column("metric_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("l1_ratio", sa.Numeric(10, 6), nullable=True),
        sa.Column("l1_l2_ratio", sa.Numeric(10, 6), nullable=True),
        sa.Column("redemption_coverage", sa.Numeric(10, 6), nullable=True),
        sa.Column("nav", sa.Numeric(38, 18), nullable=True),
        sa.Column("nav_change_24h", sa.Numeric(10, 6), nullable=True),
        sa.Column("max_asset_concentration", sa.Numeric(10, 6), nullable=True),
        sa.Column("top3_concentration", sa.Numeric(10, 6), nullable=True),
        sa.Column("pending_redemption_count", sa.Integer(), nullable=True),
        sa.Column("pending_redemption_amount", sa.Numeric(78, 0), nullable=True),
        sa.Column("daily_redemption_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint("metric_time"),
    )

    # Convert to hypertable
    op.execute(
        "SELECT create_hypertable('risk_metrics_series', 'metric_time', if_not_exists => TRUE)"
    )

    # Add retention policy (90 days)
    op.execute(
        "SELECT add_retention_policy('risk_metrics_series', INTERVAL '90 days', if_not_exists => TRUE)"
    )

    # Create continuous aggregate for hourly metrics
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS risk_metrics_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', metric_time) AS bucket,
            AVG(l1_ratio) AS avg_l1_ratio,
            MIN(l1_ratio) AS min_l1_ratio,
            AVG(nav) AS avg_nav,
            MAX(risk_score) AS max_risk_score
        FROM risk_metrics_series
        GROUP BY bucket
        """
    )

    # Add refresh policy for continuous aggregate
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('risk_metrics_hourly',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists => TRUE)
        """
    )

    # Create event_processing_logs table
    op.create_table(
        "event_processing_logs",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("event_name", sa.String(100), nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.PrimaryKeyConstraint("processed_at", "tx_hash", "log_index"),
    )

    # Convert to hypertable
    op.execute(
        "SELECT create_hypertable('event_processing_logs', 'processed_at', if_not_exists => TRUE)"
    )

    # Add retention policy (7 days)
    op.execute(
        "SELECT add_retention_policy('event_processing_logs', INTERVAL '7 days', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    # Drop continuous aggregate first
    op.execute("DROP MATERIALIZED VIEW IF EXISTS risk_metrics_hourly CASCADE")

    # Drop tables
    op.drop_table("event_processing_logs")
    op.drop_table("risk_metrics_series")
    op.drop_table("asset_holdings_snapshots")
    op.drop_table("daily_snapshots")

    # Note: We don't drop the TimescaleDB extension as it might be used by other tables
