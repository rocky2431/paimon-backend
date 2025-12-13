"""Asset configuration model."""

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
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AssetConfig(Base, TimestampMixin):
    """Asset configuration table."""

    __tablename__ = "asset_configs"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Asset info
    token_address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False)
    token_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    token_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decimals: Mapped[int] = mapped_column(SmallInteger, default=18, nullable=False)

    # Configuration
    tier: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_allocation: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Purchase configuration
    purchase_adapter: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    purchase_method: Mapped[str] = mapped_column(String(10), default="AUTO")
    max_slippage: Mapped[int] = mapped_column(Integer, default=200)  # bps
    min_purchase_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(78, 0), nullable=True
    )
    subscription_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Metadata
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    added_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)

    __table_args__ = (
        CheckConstraint("tier IN ('L1', 'L2', 'L3')", name="tier"),
        CheckConstraint(
            "purchase_method IN ('OTC', 'SWAP', 'AUTO')", name="purchase_method"
        ),
    )
