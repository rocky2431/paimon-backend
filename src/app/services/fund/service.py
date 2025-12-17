"""Fund data service with hybrid mock/real data sources.

This service provides fund overview, asset allocation, and flow metrics
with configurable data sources via Feature Flags.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.blockchain.client import BSCClient
from app.infrastructure.blockchain.contracts import ContractManager
from app.repositories import (
    AssetRepository,
    RedemptionRepository,
    TransactionRepository,
    DailySnapshotRepository,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class FundService:
    """Service for fund data retrieval with hybrid data sources.

    Supports switching between mock and real data via Feature Flags.
    Each method checks the corresponding feature flag and falls back
    to mock data on errors.
    """

    def __init__(self, session: AsyncSession | None = None):
        """Initialize FundService.

        @param session - Optional SQLAlchemy async session
        """
        self._session = session
        self._owned_session = session is None

    async def _get_session(self) -> AsyncSession:
        """Get or create database session."""
        if self._session is not None:
            return self._session
        return AsyncSessionLocal()

    async def _close_session(self, session: AsyncSession) -> None:
        """Close session if we own it."""
        if self._owned_session and session is not self._session:
            await session.close()

    # ==========================================================================
    # Flow Metrics
    # ==========================================================================

    async def get_flow_metrics(self) -> dict[str, Any]:
        """Get fund flow metrics (subscriptions, redemptions, pending).

        Uses FF_FLOW_METRICS_SOURCE to determine data source.

        @returns Flow metrics dictionary
        """
        if settings.ff_flow_metrics_source == "real":
            try:
                return await self._get_flow_metrics_real()
            except Exception as e:
                logger.warning(f"Real flow metrics failed: {e}, fallback to mock")
        return self._generate_flow_metrics_mock()

    async def _get_flow_metrics_real(self) -> dict[str, Any]:
        """Get flow metrics from real database."""
        session = await self._get_session()
        try:
            redemption_repo = RedemptionRepository(session)
            tx_repo = TransactionRepository(session)

            day_ago = datetime.utcnow() - timedelta(days=1)
            week_ago = datetime.utcnow() - timedelta(days=7)

            # Get redemption statistics
            stats_24h = await redemption_repo.get_statistics(
                start_date=day_ago, end_date=datetime.utcnow()
            )
            stats_7d = await redemption_repo.get_statistics(
                start_date=week_ago, end_date=datetime.utcnow()
            )

            # Get pending redemptions
            pending = await redemption_repo.get_total_pending_amount()

            # Get transaction volumes
            volume_24h = await tx_repo.get_volume_by_event(start_date=day_ago)
            volume_7d = await tx_repo.get_volume_by_event(start_date=week_ago)

            return {
                "subscriptions_24h": str(volume_24h.get("Deposit", Decimal(0))),
                "subscriptions_7d": str(volume_7d.get("Deposit", Decimal(0))),
                "redemptions_24h": str(stats_24h.get("total_amount", Decimal(0))),
                "redemptions_7d": str(stats_7d.get("total_amount", Decimal(0))),
                "pending_redemptions": str(pending),
                "net_flow_24h": str(
                    volume_24h.get("Deposit", Decimal(0))
                    - stats_24h.get("total_amount", Decimal(0))
                ),
            }
        finally:
            await self._close_session(session)

    def _generate_flow_metrics_mock(self) -> dict[str, Any]:
        """Generate mock flow metrics data."""
        return {
            "subscriptions_24h": "150000000000000000000000",
            "subscriptions_7d": "980000000000000000000000",
            "redemptions_24h": "85000000000000000000000",
            "redemptions_7d": "520000000000000000000000",
            "pending_redemptions": "125000000000000000000000",
            "net_flow_24h": "65000000000000000000000",
        }

    # ==========================================================================
    # Asset Allocations
    # ==========================================================================

    async def get_asset_allocations(self) -> list[dict[str, Any]]:
        """Get asset allocation details.

        Uses FF_ASSET_ALLOCATION_SOURCE to determine data source.

        @returns List of asset allocation dictionaries
        """
        if settings.ff_asset_allocation_source == "real":
            try:
                return await self._get_asset_allocations_real()
            except Exception as e:
                logger.warning(f"Real asset allocations failed: {e}, fallback to mock")
        return self._generate_asset_allocations_mock()

    async def _get_asset_allocations_real(self) -> list[dict[str, Any]]:
        """Get asset allocations from real database."""
        session = await self._get_session()
        try:
            repo = AssetRepository(session)
            assets = await repo.get_active()

            return [
                {
                    "asset_symbol": asset.token_symbol,
                    "asset_name": asset.token_name or asset.token_symbol,
                    "token_address": asset.token_address,
                    "allocation_percent": str(asset.target_allocation),
                    "liquidity_tier": asset.tier,
                    "decimals": asset.decimals,
                    "is_active": asset.is_active,
                }
                for asset in assets
            ]
        finally:
            await self._close_session(session)

    def _generate_asset_allocations_mock(self) -> list[dict[str, Any]]:
        """Generate mock asset allocation data."""
        return [
            {
                "asset_symbol": "USDC",
                "asset_name": "USD Coin",
                "token_address": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
                "allocation_percent": "30.00",
                "liquidity_tier": "L1",
                "decimals": 18,
                "is_active": True,
            },
            {
                "asset_symbol": "USDT",
                "asset_name": "Tether USD",
                "token_address": "0x55d398326f99059ff775485246999027b3197955",
                "allocation_percent": "25.00",
                "liquidity_tier": "L1",
                "decimals": 18,
                "is_active": True,
            },
            {
                "asset_symbol": "BUSD",
                "asset_name": "Binance USD",
                "token_address": "0xe9e7cea3dedca5984780bafc599bd69add087d56",
                "allocation_percent": "20.00",
                "liquidity_tier": "L2",
                "decimals": 18,
                "is_active": True,
            },
            {
                "asset_symbol": "DAI",
                "asset_name": "Dai Stablecoin",
                "token_address": "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3",
                "allocation_percent": "15.00",
                "liquidity_tier": "L2",
                "decimals": 18,
                "is_active": True,
            },
            {
                "asset_symbol": "FRAX",
                "asset_name": "Frax",
                "token_address": "0x90c97f71e18723b0cf0dfa30ee176ab653e89f40",
                "allocation_percent": "10.00",
                "liquidity_tier": "L3",
                "decimals": 18,
                "is_active": True,
            },
        ]

    # ==========================================================================
    # Tier Allocations
    # ==========================================================================

    async def get_tier_allocations(self) -> dict[str, Any]:
        """Get tier allocation summary.

        Uses FF_TIER_ALLOCATION_SOURCE to determine data source.

        @returns Tier allocation dictionary
        """
        if settings.ff_tier_allocation_source == "real":
            try:
                return await self._get_tier_allocations_real()
            except Exception as e:
                logger.warning(f"Real tier allocations failed: {e}, fallback to mock")
        return self._generate_tier_allocations_mock()

    async def _get_tier_allocations_real(self) -> dict[str, Any]:
        """Get tier allocations from real database."""
        session = await self._get_session()
        try:
            repo = AssetRepository(session)
            allocations = await repo.get_all_allocations()
            stats = await repo.get_statistics()

            return {
                "L1": {
                    "name": "High Liquidity",
                    "allocation_percent": str(allocations.get("L1", Decimal(0))),
                    "asset_count": stats["by_tier_count"].get("L1", 0),
                    "description": "Instantly redeemable stablecoins",
                },
                "L2": {
                    "name": "Medium Liquidity",
                    "allocation_percent": str(allocations.get("L2", Decimal(0))),
                    "asset_count": stats["by_tier_count"].get("L2", 0),
                    "description": "DeFi protocol positions",
                },
                "L3": {
                    "name": "Yield Generating",
                    "allocation_percent": str(allocations.get("L3", Decimal(0))),
                    "asset_count": stats["by_tier_count"].get("L3", 0),
                    "description": "Longer-term yield strategies",
                },
                "total_allocation": str(stats.get("total_allocation", Decimal(0))),
                "total_assets": stats.get("total_active", 0),
            }
        finally:
            await self._close_session(session)

    def _generate_tier_allocations_mock(self) -> dict[str, Any]:
        """Generate mock tier allocation data."""
        return {
            "L1": {
                "name": "High Liquidity",
                "allocation_percent": "55.00",
                "asset_count": 2,
                "description": "Instantly redeemable stablecoins",
            },
            "L2": {
                "name": "Medium Liquidity",
                "allocation_percent": "35.00",
                "asset_count": 2,
                "description": "DeFi protocol positions",
            },
            "L3": {
                "name": "Yield Generating",
                "allocation_percent": "10.00",
                "asset_count": 1,
                "description": "Longer-term yield strategies",
            },
            "total_allocation": "100.00",
            "total_assets": 5,
        }

    # ==========================================================================
    # NAV History
    # ==========================================================================

    async def get_nav_history(
        self, days: int = 30, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Get NAV history for charting.

        Uses FF_NAV_HISTORY_SOURCE to determine data source.

        @param days - Number of days of history
        @param limit - Maximum data points
        @returns List of {time, nav} dictionaries
        """
        if settings.ff_nav_history_source == "real":
            try:
                return await self._get_nav_history_real(days, limit)
            except Exception as e:
                logger.warning(f"Real NAV history failed: {e}, fallback to mock")
        return self._generate_nav_history_mock(days)

    async def _get_nav_history_real(
        self, days: int, limit: int
    ) -> list[dict[str, Any]]:
        """Get NAV history from real database."""
        session = await self._get_session()
        try:
            repo = DailySnapshotRepository(session)
            start_time = datetime.utcnow() - timedelta(days=days)
            nav_data = await repo.get_nav_range(start_time=start_time)

            # Convert to API format
            decimals = Decimal(10**18)
            return [
                {
                    "time": item["time"].isoformat(),
                    "nav": str(item["nav"] / decimals),
                }
                for item in nav_data
            ]
        finally:
            await self._close_session(session)

    def _generate_nav_history_mock(self, days: int) -> list[dict[str, Any]]:
        """Generate mock NAV history data."""
        import random

        base_nav = 1.0523
        result = []
        for i in range(days):
            time = datetime.utcnow() - timedelta(days=days - i - 1)
            # Add small random variation
            nav = base_nav + random.uniform(-0.002, 0.003) * i / days
            result.append({"time": time.isoformat(), "nav": f"{nav:.4f}"})
        return result

    # ==========================================================================
    # Fund Overview (Chain Data)
    # ==========================================================================

    async def get_fund_overview(self) -> dict[str, Any]:
        """Get fund overview data.

        Uses FF_FUND_OVERVIEW_SOURCE to determine data source.

        @returns Fund overview dictionary
        """
        if settings.ff_fund_overview_source == "real":
            try:
                return await self._get_fund_overview_real()
            except Exception as e:
                logger.warning(f"Real fund overview failed: {e}, fallback to mock")
        return self._generate_fund_overview_mock()

    async def _get_fund_overview_real(self) -> dict[str, Any]:
        """Get fund overview from blockchain."""
        client = BSCClient()
        cm = ContractManager(client)

        # Get vault state from chain
        vault_state = await cm.get_vault_state(settings.active_vault_address)

        # Convert from wei (10^18) to decimal
        decimals = Decimal(10**18)

        total_assets = Decimal(vault_state["total_assets"]) / decimals
        total_supply = Decimal(vault_state["total_supply"]) / decimals
        share_price = Decimal(vault_state["share_price"]) / decimals

        # Get layer values
        layer1 = Decimal(vault_state["layer1_liquidity"]) / decimals
        layer2 = Decimal(vault_state["layer2_liquidity"]) / decimals
        layer3 = Decimal(vault_state["layer3_value"]) / decimals

        # Helper to safely convert optional values
        def safe_decimal(value: Any) -> Decimal:
            if value is None:
                return Decimal(0)
            return Decimal(value) / decimals

        return {
            "total_aum": str(total_assets),
            "current_nav": str(share_price),
            "total_supply": str(total_supply),
            "effective_supply": str(safe_decimal(vault_state.get("effective_supply"))),
            "layer1_liquidity": str(layer1),
            "layer2_liquidity": str(layer2),
            "layer3_value": str(layer3),
            "total_redemption_liability": str(
                safe_decimal(vault_state.get("total_redemption_liability"))
            ),
            "total_locked_shares": str(
                safe_decimal(vault_state.get("total_locked_shares"))
            ),
            "emergency_mode": vault_state.get("emergency_mode", False),
            "layer1_ratio": str(layer1 / total_assets * 100) if total_assets > 0 else "0",
            "layer2_ratio": str(layer2 / total_assets * 100) if total_assets > 0 else "0",
            "layer3_ratio": str(layer3 / total_assets * 100) if total_assets > 0 else "0",
        }

    def _generate_fund_overview_mock(self) -> dict[str, Any]:
        """Generate mock fund overview data."""
        return {
            "total_aum": "25000000.00",
            "current_nav": "1.0523",
            "total_supply": "23755000.00",
            "effective_supply": "23500000.00",
            "layer1_liquidity": "8750000.00",
            "layer2_liquidity": "10000000.00",
            "layer3_value": "6250000.00",
            "total_redemption_liability": "125000.00",
            "total_locked_shares": "100000.00",
            "emergency_mode": False,
            "layer1_ratio": "35.00",
            "layer2_ratio": "40.00",
            "layer3_ratio": "25.00",
        }
