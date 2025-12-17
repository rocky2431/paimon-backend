"""Contract management and ABI handling.

Loads ABIs from backed-abi/ directory and provides contract interaction methods.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from eth_abi import decode
from web3 import Web3
from web3.types import TxParams

from app.infrastructure.blockchain.client import ChainClient

logger = logging.getLogger(__name__)

# ABI directory path (relative to project root)
ABI_DIR = Path(__file__).parent.parent.parent.parent.parent / "backed-abi"


class ABILoader:
    """Loads and caches contract ABIs from JSON files."""

    _instance = None
    _abis: dict[str, list[dict]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_all_abis()
        return cls._instance

    def _load_all_abis(self) -> None:
        """Load all ABIs from the backed-abi directory."""
        if not ABI_DIR.exists():
            logger.warning(f"ABI directory not found: {ABI_DIR}")
            return

        for abi_file in ABI_DIR.glob("*.json"):
            try:
                with open(abi_file, "r") as f:
                    data = json.load(f)
                    # Extract ABI array from the JSON
                    abi = data.get("abi", [])
                    if abi:
                        name = abi_file.stem  # e.g., "PPT", "RedemptionManager"
                        self._abis[name] = abi
                        logger.debug(f"Loaded ABI: {name} ({len(abi)} entries)")
            except Exception as e:
                logger.error(f"Failed to load ABI {abi_file}: {e}")

        logger.info(f"Loaded {len(self._abis)} ABIs: {list(self._abis.keys())}")

    def get_abi(self, contract_name: str) -> list[dict]:
        """Get ABI by contract name.

        Args:
            contract_name: Contract name (e.g., "PPT", "RedemptionManager")

        Returns:
            Contract ABI as list of dicts
        """
        if contract_name not in self._abis:
            raise ValueError(f"ABI not found for contract: {contract_name}")
        return self._abis[contract_name]

    @property
    def ppt_abi(self) -> list[dict]:
        """Get PPT (Vault) contract ABI."""
        return self.get_abi("PPT")

    @property
    def redemption_manager_abi(self) -> list[dict]:
        """Get RedemptionManager contract ABI."""
        return self.get_abi("RedemptionManager")

    @property
    def redemption_voucher_abi(self) -> list[dict]:
        """Get RedemptionVoucher contract ABI."""
        return self.get_abi("RedemptionVoucher")


# Global ABI loader instance
@lru_cache(maxsize=1)
def get_abi_loader() -> ABILoader:
    """Get the singleton ABI loader instance."""
    return ABILoader()


class ContractManager:
    """Manages contract interactions with full ABI support."""

    def __init__(self, client: ChainClient):
        """Initialize contract manager.

        Args:
            client: Blockchain client for RPC calls
        """
        self.client = client
        self.w3 = Web3()  # For encoding/decoding only
        self.abi_loader = get_abi_loader()

    def encode_function_call(
        self, abi: list[dict], function_name: str, args: list[Any] | None = None
    ) -> bytes:
        """Encode function call data.

        Args:
            abi: Contract ABI
            function_name: Name of the function to call
            args: Function arguments

        Returns:
            Encoded function call data
        """
        dummy_address = "0x0000000000000000000000000000000000000000"
        contract = self.w3.eth.contract(address=dummy_address, abi=abi)
        func = contract.get_function_by_name(function_name)
        return func(*args if args else [])._encode_transaction_data()

    def decode_function_result(
        self, abi: list[dict], function_name: str, data: bytes
    ) -> Any:
        """Decode function result.

        Args:
            abi: Contract ABI
            function_name: Name of the function
            data: Raw result data

        Returns:
            Decoded result
        """
        func_abi = None
        for item in abi:
            if item.get("type") == "function" and item.get("name") == function_name:
                func_abi = item
                break

        if not func_abi:
            raise ValueError(f"Function {function_name} not found in ABI")

        output_types = []
        for o in func_abi.get("outputs", []):
            if o["type"] == "tuple":
                # Handle tuple types
                components = o.get("components", [])
                component_types = ",".join(c["type"] for c in components)
                output_types.append(f"({component_types})")
            else:
                output_types.append(o["type"])

        if not output_types:
            return None

        decoded = decode(output_types, data)
        return decoded[0] if len(decoded) == 1 else decoded

    async def call_contract(
        self,
        address: str,
        abi: list[dict],
        function_name: str,
        args: list[Any] | None = None,
    ) -> Any:
        """Call contract function (read-only).

        Args:
            address: Contract address
            abi: Contract ABI
            function_name: Function name
            args: Function arguments

        Returns:
            Decoded function result
        """
        # Convert to checksum address
        checksum_address = Web3.to_checksum_address(address)
        data = self.encode_function_call(abi, function_name, args)
        tx_params: TxParams = {"to": checksum_address, "data": data}
        result = await self.client.eth_call(tx_params)
        return self.decode_function_result(abi, function_name, result)

    async def _batch_calls(
        self,
        address: str,
        abi: list[dict],
        function_names: list[str],
    ) -> list[Any]:
        """Execute batch of contract calls in parallel.

        Args:
            address: Contract address
            abi: Contract ABI
            function_names: List of function names to call

        Returns:
            List of results in same order as function_names
        """
        import asyncio

        tasks = [
            self.call_contract(address, abi, name) for name in function_names
        ]
        return await asyncio.gather(*tasks)

    # =========================================================================
    # PPT (Vault) Contract Methods
    # =========================================================================

    async def get_vault_state(self, vault_address: str) -> dict[str, Any]:
        """Get complete vault state from chain.

        Args:
            vault_address: PPT vault contract address

        Returns:
            Dictionary with all vault state values
        """
        abi = self.abi_loader.ppt_abi

        # Core functions that are known to work
        core_functions = [
            "sharePrice",
            "totalAssets",
            "totalSupply",
            "getLayer1Liquidity",
            "getLayer2Liquidity",
            "getLayer3Value",
        ]

        results = await self._batch_calls(vault_address, abi, core_functions)

        state = {
            "share_price": results[0],
            "total_assets": results[1],
            "total_supply": results[2],
            "layer1_liquidity": results[3],
            "layer2_liquidity": results[4],
            "layer3_value": results[5],
        }

        # Try to get optional fields with graceful fallback
        optional_functions = [
            ("effectiveSupply", "effective_supply"),
            ("totalRedemptionLiability", "total_redemption_liability"),
            ("totalLockedShares", "total_locked_shares"),
            ("emergencyMode", "emergency_mode"),
        ]

        for func_name, key in optional_functions:
            try:
                value = await self.call_contract(vault_address, abi, func_name)
                state[key] = value
            except Exception:
                state[key] = None  # Graceful fallback

        return state

    async def get_liquidity_breakdown(self, vault_address: str) -> dict[str, Any]:
        """Get detailed liquidity breakdown.

        Args:
            vault_address: PPT vault contract address

        Returns:
            Dictionary with liquidity breakdown
        """
        abi = self.abi_loader.ppt_abi

        # Core functions that are known to work
        core_functions = [
            "getLayer1Liquidity",
            "getLayer2Liquidity",
            "getLayer3Value",
        ]

        results = await self._batch_calls(vault_address, abi, core_functions)

        breakdown = {
            "layer1_total": results[0],
            "layer2_total": results[1],
            "layer3_total": results[2],
        }

        # Try optional functions with graceful fallback
        optional_functions = [
            ("getLayer1Cash", "layer1_cash"),
            ("getLayer1YieldAssets", "layer1_yield_assets"),
            ("getAvailableLiquidity", "available_liquidity"),
            ("getRedeemableLiquidity", "redeemable_liquidity"),
            ("getStandardChannelQuota", "standard_channel_quota"),
        ]

        for func_name, key in optional_functions:
            try:
                value = await self.call_contract(vault_address, abi, func_name)
                breakdown[key] = value
            except Exception:
                breakdown[key] = None

        return breakdown

    async def get_user_shares(
        self, vault_address: str, user_address: str
    ) -> dict[str, Any]:
        """Get user's share balances.

        Args:
            vault_address: PPT vault contract address
            user_address: User wallet address

        Returns:
            Dictionary with user share info
        """
        abi = self.abi_loader.ppt_abi

        balance = await self.call_contract(
            vault_address, abi, "balanceOf", [user_address]
        )
        available = await self.call_contract(
            vault_address, abi, "getAvailableShares", [user_address]
        )
        locked = await self.call_contract(
            vault_address, abi, "lockedSharesOf", [user_address]
        )
        pending = await self.call_contract(
            vault_address, abi, "pendingApprovalSharesOf", [user_address]
        )

        return {
            "total_balance": balance,
            "available_shares": available,
            "locked_shares": locked,
            "pending_approval_shares": pending,
        }

    async def get_emergency_info(self, vault_address: str) -> dict[str, Any]:
        """Get emergency mode information.

        Args:
            vault_address: PPT vault contract address

        Returns:
            Dictionary with emergency mode info
        """
        abi = self.abi_loader.ppt_abi

        results = await self._batch_calls(
            vault_address,
            abi,
            ["emergencyMode", "emergencyQuota", "paused"],
        )

        return {
            "emergency_mode": results[0],
            "emergency_quota": results[1],
            "paused": results[2],
        }

    # =========================================================================
    # RedemptionManager Contract Methods
    # =========================================================================

    async def get_redemption_request(
        self, redemption_manager_address: str, request_id: int
    ) -> dict[str, Any] | None:
        """Get redemption request details.

        Args:
            redemption_manager_address: RedemptionManager contract address
            request_id: Redemption request ID

        Returns:
            Redemption request details or None if not found
        """
        try:
            abi = self.abi_loader.redemption_manager_abi
            result = await self.call_contract(
                redemption_manager_address,
                abi,
                "getRedemptionRequest",
                [request_id],
            )

            if not result:
                return None

            return {
                "owner": result[0],
                "receiver": result[1],
                "shares": result[2],
                "gross_amount": result[3],
                "locked_nav": result[4],
                "estimated_fee": result[5],
                "channel": result[6],
                "status": result[7],
                "request_time": result[8],
                "settlement_time": result[9],
                "window_id": result[10],
                "requires_approval": result[11],
            }

        except Exception as e:
            logger.error(f"Failed to get redemption request {request_id}: {e}")
            return None

    async def get_redemption_stats(
        self, redemption_manager_address: str
    ) -> dict[str, Any]:
        """Get redemption manager statistics.

        Args:
            redemption_manager_address: RedemptionManager contract address

        Returns:
            Dictionary with redemption statistics
        """
        abi = self.abi_loader.redemption_manager_abi

        results = await self._batch_calls(
            redemption_manager_address,
            abi,
            [
                "getRequestCount",
                "getTotalPendingApprovalAmount",
                "getSevenDayLiability",
                "getOverdueLiability",
                "baseRedemptionFeeBps",
                "emergencyPenaltyFeeBps",
                "voucherThreshold",
            ],
        )

        return {
            "request_count": results[0],
            "total_pending_approval_amount": results[1],
            "seven_day_liability": results[2],
            "overdue_liability": results[3],
            "base_redemption_fee_bps": results[4],
            "emergency_penalty_fee_bps": results[5],
            "voucher_threshold": results[6],
        }

    async def get_pending_approvals(
        self, redemption_manager_address: str
    ) -> list[int]:
        """Get list of pending approval request IDs.

        Args:
            redemption_manager_address: RedemptionManager contract address

        Returns:
            List of request IDs pending approval
        """
        abi = self.abi_loader.redemption_manager_abi
        return await self.call_contract(
            redemption_manager_address, abi, "getPendingApprovals"
        )

    async def get_user_redemptions(
        self, redemption_manager_address: str, user_address: str
    ) -> list[int]:
        """Get list of user's redemption request IDs.

        Args:
            redemption_manager_address: RedemptionManager contract address
            user_address: User wallet address

        Returns:
            List of request IDs for the user
        """
        abi = self.abi_loader.redemption_manager_abi
        return await self.call_contract(
            redemption_manager_address,
            abi,
            "getUserRedemptions",
            [user_address],
        )

    async def preview_redemption(
        self, redemption_manager_address: str, shares: int
    ) -> dict[str, Any]:
        """Preview standard redemption.

        Args:
            redemption_manager_address: RedemptionManager contract address
            shares: Number of shares to redeem

        Returns:
            Preview result with estimated amounts and fees
        """
        abi = self.abi_loader.redemption_manager_abi
        result = await self.call_contract(
            redemption_manager_address, abi, "previewRedemption", [shares]
        )

        return {
            "gross_amount": result[0],
            "estimated_fee": result[1],
            "net_amount": result[2],
            "requires_approval": result[3],
            "channel": result[4],
        }

    async def preview_emergency_redemption(
        self, redemption_manager_address: str, shares: int
    ) -> dict[str, Any]:
        """Preview emergency redemption.

        Args:
            redemption_manager_address: RedemptionManager contract address
            shares: Number of shares to redeem

        Returns:
            Preview result with estimated amounts and fees
        """
        abi = self.abi_loader.redemption_manager_abi
        result = await self.call_contract(
            redemption_manager_address,
            abi,
            "previewEmergencyRedemption",
            [shares],
        )

        return {
            "gross_amount": result[0],
            "penalty_fee": result[1],
            "net_amount": result[2],
            "available": result[3],
        }

    async def get_daily_liability(
        self, redemption_manager_address: str, day_index: int
    ) -> int:
        """Get liability for a specific day.

        Args:
            redemption_manager_address: RedemptionManager contract address
            day_index: Day index (0 = today, 1 = tomorrow, etc.)

        Returns:
            Liability amount for that day
        """
        abi = self.abi_loader.redemption_manager_abi
        return await self.call_contract(
            redemption_manager_address,
            abi,
            "getDailyLiability",
            [day_index],
        )
