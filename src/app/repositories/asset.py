"""Repository for asset configuration operations."""

from datetime import datetime
from decimal import Decimal
from typing import Sequence, Any

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetConfig
from app.repositories.base import BaseRepository


class AssetRepository(BaseRepository[AssetConfig]):
    """Repository for AssetConfig database operations.

    Handles asset configuration queries including:
    - Finding assets by tier/address
    - Active asset management
    - Allocation tracking
    """

    model = AssetConfig

    async def get_by_address(self, token_address: str) -> AssetConfig | None:
        """Get asset by token address.

        @param token_address - Token contract address
        @returns AssetConfig or None
        """
        return await self.get_one_by_filter(token_address=token_address.lower())

    async def get_active(
        self,
        *,
        tier: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AssetConfig]:
        """Get all active assets.

        @param tier - Optional tier filter (L1/L2/L3)
        @param skip - Pagination offset
        @param limit - Maximum results
        @returns List of active assets
        """
        stmt = select(self.model).where(self.model.is_active == True)
        if tier:
            stmt = stmt.where(self.model.tier == tier)
        stmt = stmt.order_by(self.model.tier, desc(self.model.target_allocation))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_tier(self, tier: str) -> Sequence[AssetConfig]:
        """Get all assets in a tier.

        @param tier - Tier (L1/L2/L3)
        @returns List of assets in tier
        """
        stmt = (
            select(self.model)
            .where(and_(self.model.tier == tier, self.model.is_active == True))
            .order_by(desc(self.model.target_allocation))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_tier_allocation(self, tier: str) -> Decimal:
        """Get total target allocation for a tier.

        @param tier - Tier (L1/L2/L3)
        @returns Total allocation percentage
        """
        from sqlalchemy import func

        stmt = select(func.coalesce(func.sum(self.model.target_allocation), 0)).where(
            and_(self.model.tier == tier, self.model.is_active == True)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or Decimal(0)

    async def get_all_allocations(self) -> dict[str, Decimal]:
        """Get total allocations by tier.

        @returns Dictionary of tier -> total allocation
        """
        from sqlalchemy import func

        stmt = (
            select(self.model.tier, func.sum(self.model.target_allocation))
            .where(self.model.is_active == True)
            .group_by(self.model.tier)
        )
        result = await self.session.execute(stmt)
        return {tier: alloc for tier, alloc in result.all()}

    async def add_asset(
        self,
        *,
        token_address: str,
        token_symbol: str,
        tier: str,
        target_allocation: Decimal,
        token_name: str | None = None,
        decimals: int = 18,
        purchase_adapter: str | None = None,
        purchase_method: str = "AUTO",
        added_tx_hash: str | None = None,
    ) -> AssetConfig:
        """Add new asset to portfolio.

        @param token_address - Token contract address
        @param token_symbol - Token symbol
        @param tier - Tier (L1/L2/L3)
        @param target_allocation - Target allocation percentage
        @param token_name - Optional full name
        @param decimals - Token decimals (default 18)
        @param purchase_adapter - Optional purchase adapter address
        @param purchase_method - Purchase method (OTC/SWAP/AUTO)
        @param added_tx_hash - Transaction hash where added
        @returns Created AssetConfig
        """
        return await self.create(
            {
                "token_address": token_address.lower(),
                "token_symbol": token_symbol,
                "token_name": token_name,
                "decimals": decimals,
                "tier": tier,
                "target_allocation": target_allocation,
                "is_active": True,
                "purchase_adapter": purchase_adapter.lower() if purchase_adapter else None,
                "purchase_method": purchase_method,
                "added_at": datetime.utcnow(),
                "added_tx_hash": added_tx_hash,
            }
        )

    async def remove_asset(
        self, token_address: str, *, removed_tx_hash: str | None = None
    ) -> AssetConfig | None:
        """Mark asset as removed (soft delete).

        @param token_address - Token contract address
        @param removed_tx_hash - Transaction hash where removed
        @returns Updated AssetConfig or None
        """
        asset = await self.get_by_address(token_address)
        if asset is None:
            return None

        return await self.update(
            asset.id,
            {
                "is_active": False,
                "removed_at": datetime.utcnow(),
                "removed_tx_hash": removed_tx_hash,
            },
        )

    async def update_allocation(
        self, token_address: str, new_allocation: Decimal
    ) -> AssetConfig | None:
        """Update asset target allocation.

        @param token_address - Token contract address
        @param new_allocation - New target allocation
        @returns Updated AssetConfig or None
        """
        asset = await self.get_by_address(token_address)
        if asset is None:
            return None

        return await self.update(asset.id, {"target_allocation": new_allocation})

    async def get_subscription_active(self) -> Sequence[AssetConfig]:
        """Get assets with active subscription windows.

        @returns List of assets in subscription period
        """
        now = datetime.utcnow()
        stmt = select(self.model).where(
            and_(
                self.model.is_active == True,
                self.model.subscription_start <= now,
                or_(
                    self.model.subscription_end.is_(None),
                    self.model.subscription_end >= now,
                ),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_statistics(self) -> dict[str, Any]:
        """Get asset portfolio statistics.

        @returns Statistics dictionary
        """
        from sqlalchemy import func

        # Count by tier
        tier_stmt = (
            select(self.model.tier, func.count(self.model.id))
            .where(self.model.is_active == True)
            .group_by(self.model.tier)
        )
        result = await self.session.execute(tier_stmt)
        tier_counts = dict(result.all())

        # Allocation by tier
        alloc_stmt = (
            select(self.model.tier, func.sum(self.model.target_allocation))
            .where(self.model.is_active == True)
            .group_by(self.model.tier)
        )
        result = await self.session.execute(alloc_stmt)
        tier_allocations = dict(result.all())

        # Total active
        total_stmt = select(func.count(self.model.id)).where(
            self.model.is_active == True
        )
        result = await self.session.execute(total_stmt)
        total_active = result.scalar() or 0

        return {
            "total_active": total_active,
            "by_tier_count": tier_counts,
            "by_tier_allocation": tier_allocations,
            "total_allocation": sum(tier_allocations.values()),
        }


# Import or_ at module level
from sqlalchemy import or_
