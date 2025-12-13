"""Transaction model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Transaction(Base):
    """General transaction record table."""

    __tablename__ = "transactions"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # On-chain info
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, index=True)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Transaction type
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)

    # Participants
    from_address: Mapped[Optional[str]] = mapped_column(
        String(42), nullable=True, index=True
    )
    to_address: Mapped[Optional[str]] = mapped_column(
        String(42), nullable=True, index=True
    )

    # Amount info
    token_address: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    shares: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)
    fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(78, 0), nullable=True)

    # Raw data
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Metadata
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_transaction"),
    )
