"""Create business tables for Paimon Backend

Revision ID: 002
Revises: 001
Create Date: 2024-12-15 10:00:00.000000

Creates the following tables:
- redemption_requests: Redemption request records
- approval_tickets: Approval workflow tickets
- approval_records: Individual approval/rejection records
- asset_configs: Asset configuration and management
- rebalance_history: Rebalancing operation history
- transactions: On-chain transaction records
- risk_events: Risk monitoring events
- audit_logs: System audit trail
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================
    # 1. redemption_requests table
    # ========================================
    op.create_table(
        "redemption_requests",
        # Primary key
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # On-chain data
        sa.Column("request_id", sa.Numeric(78, 0), nullable=False),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        # Request info
        sa.Column("owner", sa.String(42), nullable=False),
        sa.Column("receiver", sa.String(42), nullable=False),
        sa.Column("shares", sa.Numeric(78, 0), nullable=False),
        sa.Column("gross_amount", sa.Numeric(78, 0), nullable=False),
        sa.Column("locked_nav", sa.Numeric(78, 0), nullable=False),
        sa.Column("estimated_fee", sa.Numeric(78, 0), nullable=False),
        # Time info
        sa.Column("request_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settlement_time", sa.DateTime(timezone=True), nullable=False),
        # Status info
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("window_id", sa.Numeric(78, 0), nullable=True),
        # Settlement info
        sa.Column("actual_fee", sa.Numeric(78, 0), nullable=True),
        sa.Column("net_amount", sa.Numeric(78, 0), nullable=True),
        sa.Column("settlement_tx_hash", sa.String(66), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        # Approval info
        sa.Column("approval_ticket_id", sa.String(50), nullable=True),
        sa.Column("approved_by", sa.String(42), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(42), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_redemption_tx"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'SETTLED', 'CANCELLED', 'REJECTED')",
            name="ck_redemption_status"
        ),
        sa.CheckConstraint(
            "channel IN ('STANDARD', 'EMERGENCY', 'SCHEDULED')",
            name="ck_redemption_channel"
        ),
    )
    # Indexes for redemption_requests
    op.create_index("ix_redemption_requests_owner", "redemption_requests", ["owner"])
    op.create_index("ix_redemption_requests_request_time", "redemption_requests", ["request_time"])
    op.create_index("ix_redemption_requests_settlement_time", "redemption_requests", ["settlement_time"])
    op.create_index("ix_redemption_requests_status", "redemption_requests", ["status"])
    op.create_index("ix_redemption_requests_channel", "redemption_requests", ["channel"])

    # ========================================
    # 2. approval_tickets table
    # ========================================
    op.create_table(
        "approval_tickets",
        # Primary key
        sa.Column("id", sa.String(50), nullable=False),
        # Ticket type
        sa.Column("ticket_type", sa.String(30), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=False),
        # Request info
        sa.Column("requester", sa.String(42), nullable=False),
        sa.Column("amount", sa.Numeric(78, 0), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("request_data", JSONB, nullable=True),
        sa.Column("risk_assessment", JSONB, nullable=True),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_rejections", sa.Integer(), nullable=False, server_default="0"),
        # SLA
        sa.Column("sla_warning", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_to", ARRAY(sa.String), nullable=True),
        # Result
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("result_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(42), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PARTIALLY_APPROVED', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED')",
            name="ck_ticket_status"
        ),
        sa.CheckConstraint(
            "result IN ('APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED') OR result IS NULL",
            name="ck_ticket_result"
        ),
    )
    # Indexes for approval_tickets
    op.create_index("ix_approval_tickets_ticket_type", "approval_tickets", ["ticket_type"])
    op.create_index("ix_approval_tickets_requester", "approval_tickets", ["requester"])
    op.create_index("ix_approval_tickets_status", "approval_tickets", ["status"])
    op.create_index("ix_approval_tickets_sla_deadline", "approval_tickets", ["sla_deadline"])
    op.create_index("idx_ticket_reference", "approval_tickets", ["reference_type", "reference_id"])

    # ========================================
    # 3. approval_records table
    # ========================================
    op.create_table(
        "approval_records",
        # Primary key
        sa.Column("id", sa.String(50), nullable=False),
        # Foreign key
        sa.Column("ticket_id", sa.String(50), nullable=False),
        # Record info
        sa.Column("approver", sa.String(42), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("signature", sa.String(132), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["ticket_id"], ["approval_tickets.id"], name="fk_approval_records_ticket"),
        sa.CheckConstraint("action IN ('APPROVE', 'REJECT')", name="ck_approval_action"),
    )
    # Indexes for approval_records
    op.create_index("ix_approval_records_ticket_id", "approval_records", ["ticket_id"])

    # ========================================
    # 4. asset_configs table
    # ========================================
    op.create_table(
        "asset_configs",
        # Primary key
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Asset info
        sa.Column("token_address", sa.String(42), nullable=False),
        sa.Column("token_symbol", sa.String(20), nullable=False),
        sa.Column("token_name", sa.String(100), nullable=True),
        sa.Column("decimals", sa.SmallInteger(), nullable=False, server_default="18"),
        # Configuration
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("target_allocation", sa.Numeric(10, 6), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        # Purchase configuration
        sa.Column("purchase_adapter", sa.String(42), nullable=True),
        sa.Column("purchase_method", sa.String(10), server_default="AUTO"),
        sa.Column("max_slippage", sa.Integer(), server_default="200"),
        sa.Column("min_purchase_amount", sa.Numeric(78, 0), nullable=True),
        sa.Column("subscription_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_end", sa.DateTime(timezone=True), nullable=True),
        # Metadata
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("added_tx_hash", sa.String(66), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_tx_hash", sa.String(66), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_address"),
        sa.CheckConstraint("tier IN ('L1', 'L2', 'L3')", name="ck_asset_tier"),
        sa.CheckConstraint("purchase_method IN ('OTC', 'SWAP', 'AUTO')", name="ck_purchase_method"),
    )
    # Indexes for asset_configs
    op.create_index("ix_asset_configs_tier", "asset_configs", ["tier"])
    op.create_index("ix_asset_configs_is_active", "asset_configs", ["is_active"])

    # ========================================
    # 5. rebalance_history table
    # ========================================
    op.create_table(
        "rebalance_history",
        # Primary key
        sa.Column("id", sa.String(50), nullable=False),
        # Trigger info
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("triggered_by", sa.String(42), nullable=True),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        # State
        sa.Column("pre_state", JSONB, nullable=False),
        sa.Column("target_state", JSONB, nullable=False),
        sa.Column("post_state", JSONB, nullable=True),
        # Actions
        sa.Column("actions", JSONB, nullable=False),
        # Execution info
        sa.Column("estimated_gas_cost", sa.Numeric(78, 0), nullable=True),
        sa.Column("actual_gas_cost", sa.Numeric(78, 0), nullable=True),
        sa.Column("estimated_slippage", sa.Numeric(10, 6), nullable=True),
        sa.Column("actual_slippage", sa.Numeric(10, 6), nullable=True),
        # Approval info
        sa.Column("requires_approval", sa.Boolean(), server_default="false"),
        sa.Column("approval_ticket_id", sa.String(50), nullable=True),
        # Execution result
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by", sa.String(42), nullable=True),
        sa.Column("execution_results", JSONB, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "trigger_type IN ('SCHEDULED', 'THRESHOLD', 'LIQUIDITY', 'EVENT', 'MANUAL')",
            name="ck_trigger_type"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'EXECUTING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_rebalance_status"
        ),
    )
    # Indexes for rebalance_history
    op.create_index("ix_rebalance_history_trigger_type", "rebalance_history", ["trigger_type"])
    op.create_index("ix_rebalance_history_status", "rebalance_history", ["status"])

    # ========================================
    # 6. transactions table
    # ========================================
    op.create_table(
        "transactions",
        # Primary key
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # On-chain info
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_timestamp", sa.DateTime(timezone=True), nullable=False),
        # Transaction type
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        # Participants
        sa.Column("from_address", sa.String(42), nullable=True),
        sa.Column("to_address", sa.String(42), nullable=True),
        # Amount info
        sa.Column("token_address", sa.String(42), nullable=True),
        sa.Column("amount", sa.Numeric(78, 0), nullable=True),
        sa.Column("shares", sa.Numeric(78, 0), nullable=True),
        sa.Column("fee", sa.Numeric(78, 0), nullable=True),
        # Raw data
        sa.Column("raw_data", JSONB, nullable=True),
        # Metadata
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tx_hash", "log_index", name="uq_transaction"),
    )
    # Indexes for transactions
    op.create_index("ix_transactions_tx_hash", "transactions", ["tx_hash"])
    op.create_index("ix_transactions_block_number", "transactions", ["block_number"])
    op.create_index("ix_transactions_block_timestamp", "transactions", ["block_timestamp"])
    op.create_index("ix_transactions_event_type", "transactions", ["event_type"])
    op.create_index("ix_transactions_from_address", "transactions", ["from_address"])
    op.create_index("ix_transactions_to_address", "transactions", ["to_address"])

    # ========================================
    # 7. risk_events table
    # ========================================
    op.create_table(
        "risk_events",
        # Primary key
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Event info
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("metric_name", sa.String(50), nullable=False),
        # Threshold and actual value
        sa.Column("threshold_value", sa.Numeric(38, 18), nullable=True),
        sa.Column("actual_value", sa.Numeric(38, 18), nullable=True),
        # Description
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", JSONB, nullable=True),
        # Resolution status
        sa.Column("resolved", sa.Boolean(), server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(42), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        # Notification status
        sa.Column("notified", sa.Boolean(), server_default="false"),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_channels", ARRAY(sa.String), nullable=True),
        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("severity IN ('info', 'warning', 'critical')", name="ck_severity"),
    )
    # Indexes for risk_events
    op.create_index("ix_risk_events_event_type", "risk_events", ["event_type"])
    op.create_index("ix_risk_events_severity", "risk_events", ["severity"])
    op.create_index("ix_risk_events_resolved", "risk_events", ["resolved"])
    op.create_index("ix_risk_events_created_at", "risk_events", ["created_at"])

    # ========================================
    # 8. audit_logs table
    # ========================================
    op.create_table(
        "audit_logs",
        # Primary key
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Operation info
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        # Actor info
        sa.Column("actor_address", sa.String(42), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("actor_ip", sa.String(45), nullable=True),
        sa.Column("actor_user_agent", sa.Text(), nullable=True),
        # Change content
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes for audit_logs
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_actor_address", "audit_logs", ["actor_address"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_table("audit_logs")
    op.drop_table("risk_events")
    op.drop_table("transactions")
    op.drop_table("rebalance_history")
    op.drop_table("asset_configs")
    op.drop_table("approval_records")
    op.drop_table("approval_tickets")
    op.drop_table("redemption_requests")
