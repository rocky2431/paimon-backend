"""Audit log model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Audit log table."""

    __tablename__ = "audit_logs"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Operation info
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Actor info
    actor_address: Mapped[Optional[str]] = mapped_column(
        String(42), nullable=True, index=True
    )
    actor_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    actor_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    actor_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Change content
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )
