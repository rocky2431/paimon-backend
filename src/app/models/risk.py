"""Risk event model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiskEvent(Base):
    """Risk event table."""

    __tablename__ = "risk_events"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Event info
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)

    # Threshold and actual value
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(38, 18), nullable=True
    )
    actual_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(38, 18), nullable=True
    )

    # Description
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Resolution status
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notification status
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notification_channels: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="severity"
        ),
    )
