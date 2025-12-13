"""Contract management and ABI handling."""

import json
import logging
from pathlib import Path
from typing import Any

from eth_abi import decode
from web3 import Web3
from web3.types import TxParams

from app.infrastructure.blockchain.client import ChainClient

logger = logging.getLogger(__name__)

# Contract ABIs (simplified for core functions)
VAULT_ABI = [
    {
        "name": "sharePrice",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "effectiveSupply",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "totalRedemptionLiability",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "totalLockedShares",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "emergencyMode",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
    },
    {
        "name": "getLayer1Liquidity",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "getLayer2Liquidity",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "getLayer3Value",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "totalAssets",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "totalSupply",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
]

REDEMPTION_MANAGER_ABI = [
    {
        "name": "getRedemptionRequest",
        "type": "function",
        "inputs": [{"name": "requestId", "type": "uint256"}],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "owner", "type": "address"},
                    {"name": "receiver", "type": "address"},
                    {"name": "shares", "type": "uint256"},
                    {"name": "grossAmount", "type": "uint256"},
                    {"name": "lockedNAV", "type": "uint256"},
                    {"name": "estimatedFee", "type": "uint256"},
                    {"name": "channel", "type": "uint8"},
                    {"name": "status", "type": "uint8"},
                    {"name": "requestTime", "type": "uint64"},
                    {"name": "settlementTime", "type": "uint64"},
                    {"name": "windowId", "type": "uint256"},
                    {"name": "requiresApproval", "type": "bool"},
                ],
            }
        ],
        "stateMutability": "view",
    },
    {
        "name": "getRequestCount",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "getPendingApprovals",
        "type": "function",
        "inputs": [],
        "outputs": [{"type": "uint256[]"}],
        "stateMutability": "view",
    },
]


class ContractManager:
    """Manages contract interactions."""

    def __init__(self, client: ChainClient):
        """Initialize contract manager.

        Args:
            client: Blockchain client for RPC calls
        """
        self.client = client
        self.w3 = Web3()  # For encoding/decoding only

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
        # Use a dummy address for encoding (won't be used in actual call)
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
        # Find function in ABI
        func_abi = None
        for item in abi:
            if item.get("type") == "function" and item.get("name") == function_name:
                func_abi = item
                break

        if not func_abi:
            raise ValueError(f"Function {function_name} not found in ABI")

        # Get output types
        output_types = [o["type"] for o in func_abi.get("outputs", [])]
        if not output_types:
            return None

        # Decode
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
        # Encode call data
        data = self.encode_function_call(abi, function_name, args)

        # Execute call
        tx_params: TxParams = {"to": address, "data": data}
        result = await self.client.eth_call(tx_params)

        # Decode result
        return self.decode_function_result(abi, function_name, result)

    async def get_vault_state(self, vault_address: str) -> dict[str, Any]:
        """Get complete vault state.

        Args:
            vault_address: Vault contract address

        Returns:
            Dictionary with vault state
        """
        # Make parallel calls for efficiency
        results = await self._batch_calls(
            vault_address,
            VAULT_ABI,
            [
                "sharePrice",
                "effectiveSupply",
                "totalRedemptionLiability",
                "totalLockedShares",
                "emergencyMode",
                "getLayer1Liquidity",
                "getLayer2Liquidity",
                "getLayer3Value",
                "totalAssets",
                "totalSupply",
            ],
        )

        return {
            "share_price": results[0],
            "effective_supply": results[1],
            "total_redemption_liability": results[2],
            "total_locked_shares": results[3],
            "emergency_mode": results[4],
            "layer1_liquidity": results[5],
            "layer2_liquidity": results[6],
            "layer3_value": results[7],
            "total_assets": results[8],
            "total_supply": results[9],
        }

    async def _batch_calls(
        self,
        address: str,
        abi: list[dict],
        function_names: list[str],
    ) -> list[Any]:
        """Execute batch of contract calls.

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
            result = await self.call_contract(
                redemption_manager_address,
                REDEMPTION_MANAGER_ABI,
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
