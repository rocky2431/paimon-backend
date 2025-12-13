"""Rebalance history model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RebalanceHistory(Base, TimestampMixin):
    """Rebalance history table."""

    __tablename__ = "rebalance_history"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Trigger info
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )

    # State before/after rebalancing
    pre_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    target_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    post_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Actions
    actions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Execution info
    estimated_gas_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )
    actual_gas_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )
    estimated_slippage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    actual_slippage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )

    # Approval info
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_ticket_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Execution result
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    execution_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('SCHEDULED', 'THRESHOLD', 'LIQUIDITY', 'EVENT', 'MANUAL')",
            name="trigger_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'EXECUTING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="rebalance_status",
        ),
    )
