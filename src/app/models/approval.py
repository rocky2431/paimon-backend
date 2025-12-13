"""Approval ticket and record models."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class ApprovalTicket(Base, TimestampMixin):
    """Approval ticket table."""

    __tablename__ = "approval_tickets"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Ticket type
    ticket_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Request info
    requester: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    risk_assessment: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_approvals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_rejections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # SLA
    sla_warning: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sla_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    escalated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalated_to: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Result
    result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)

    # Relationships
    records: Mapped[list["ApprovalRecord"]] = relationship(
        "ApprovalRecord", back_populates="ticket", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_ticket_reference", "reference_type", "reference_id"),
        CheckConstraint(
            "status IN ('PENDING', 'PARTIALLY_APPROVED', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED')",
            name="ticket_status",
        ),
        CheckConstraint(
            "result IN ('APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED') OR result IS NULL",
            name="ticket_result",
        ),
    )


class ApprovalRecord(Base):
    """Approval record table."""

    __tablename__ = "approval_records"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Foreign key
    ticket_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("approval_tickets.id"), nullable=False, index=True
    )

    # Record info
    approver: Mapped[str] = mapped_column(String(42), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(String(132), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    ticket: Mapped["ApprovalTicket"] = relationship(
        "ApprovalTicket", back_populates="records"
    )

    __table_args__ = (
        CheckConstraint("action IN ('APPROVE', 'REJECT')", name="action"),
    )
