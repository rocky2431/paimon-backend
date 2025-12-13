"""Redemption request model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RedemptionRequest(Base, TimestampMixin):
    """Redemption request table."""

    __tablename__ = "redemption_requests"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # On-chain data
    request_id: Mapped[Decimal] = mapped_column(
        Numeric(78, 0), unique=True, nullable=False
    )
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Request info
    owner: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    receiver: Mapped[str] = mapped_column(String(42), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    locked_nav: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    estimated_fee: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)

    # Time info
    request_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    settlement_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Status info
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    window_id: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)

    # Settlement info (filled after settlement)
    actual_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    settlement_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Approval info
    approval_ticket_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_redemption_tx"),
        CheckConstraint(
            "status IN ('PENDING', 'PENDING_APPROVAL', 'APPROVED', 'SETTLED', 'CANCELLED', 'REJECTED')",
            name="status",
        ),
        CheckConstraint(
            "channel IN ('STANDARD', 'EMERGENCY', 'SCHEDULED')",
            name="channel",
        ),
    )
