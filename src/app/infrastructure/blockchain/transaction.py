"""Transaction service for sending on-chain transactions.

Provides functionality to sign and send transactions with:
- Automatic gas estimation
- Nonce management
- Mainnet protection
- Transaction receipt waiting
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

from app.core.config import get_settings
from app.infrastructure.blockchain.client import BSCClient, ChainClient

logger = logging.getLogger(__name__)


class TransactionStatus(str, Enum):
    """Transaction execution status."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class TransactionResult:
    """Result of a transaction execution."""

    tx_hash: str
    status: TransactionStatus
    block_number: int | None = None
    gas_used: int | None = None
    error: str | None = None


class TransactionService:
    """Service for sending on-chain transactions.

    Handles transaction signing, gas estimation, and sending with
    automatic nonce management and mainnet protection.
    """

    def __init__(
        self,
        client: ChainClient,
        private_key: str,
        gas_limit_multiplier: float = 1.2,
        gas_price_multiplier: float = 1.1,
    ):
        """Initialize transaction service.

        Args:
            client: Blockchain client for sending transactions
            private_key: Private key for signing (hex string with or without 0x)
            gas_limit_multiplier: Multiplier for estimated gas limit
            gas_price_multiplier: Multiplier for gas price
        """
        self.client = client
        self.gas_limit_multiplier = gas_limit_multiplier
        self.gas_price_multiplier = gas_price_multiplier

        # Initialize account from private key
        key = private_key if private_key.startswith("0x") else f"0x{private_key}"
        self.account: LocalAccount = Account.from_key(key)
        self.w3 = Web3()

        logger.info(f"TransactionService initialized for address: {self.account.address}")

    @property
    def address(self) -> str:
        """Get the signer address."""
        return self.account.address

    async def send_transaction(
        self,
        contract_address: str,
        abi: list[dict[str, Any]],
        function_name: str,
        args: list[Any],
        gas_limit: int | None = None,
        value: int = 0,
    ) -> TransactionResult:
        """Send a contract function call transaction.

        Args:
            contract_address: Target contract address
            abi: Contract ABI
            function_name: Name of function to call
            args: Function arguments
            gas_limit: Optional gas limit (will estimate if not provided)
            value: Amount of native token to send (in wei)

        Returns:
            TransactionResult with tx_hash and status
        """
        settings = get_settings()

        # Mainnet protection check
        if settings.is_mainnet:
            settings.require_mainnet_protection()
            logger.warning(f"MAINNET TRANSACTION: {function_name} on {contract_address}")

        try:
            # 1. Encode function call
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=abi,
            )
            func = contract.get_function_by_name(function_name)
            data = func(*args)._encode_transaction_data()

            # 2. Get nonce
            nonce = await self.client.get_transaction_count(self.account.address)
            logger.debug(f"Current nonce: {nonce}")

            # 3. Get gas price with multiplier
            base_gas_price = await self.client.get_gas_price()
            gas_price = int(base_gas_price * self.gas_price_multiplier)

            # 4. Estimate or use provided gas limit
            if gas_limit is None:
                tx_for_estimate = {
                    "from": self.account.address,
                    "to": Web3.to_checksum_address(contract_address),
                    "data": data,
                    "value": value,
                }
                estimated_gas = await self.client.estimate_gas(tx_for_estimate)
                gas_limit = int(estimated_gas * self.gas_limit_multiplier)
                logger.debug(f"Estimated gas: {estimated_gas}, using: {gas_limit}")

            # 5. Build transaction
            tx = {
                "to": Web3.to_checksum_address(contract_address),
                "data": data,
                "gas": gas_limit,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": settings.chain_id,
                "value": value,
            }

            # 6. Sign transaction
            signed_tx = self.account.sign_transaction(tx)
            logger.debug(f"Transaction signed, hash: {signed_tx.hash.hex()}")

            # 7. Send transaction
            tx_hash = await self.client.send_raw_transaction(signed_tx.raw_transaction)
            logger.info(
                f"Transaction sent: {tx_hash}, "
                f"function: {function_name}, "
                f"contract: {contract_address}"
            )

            return TransactionResult(
                tx_hash=tx_hash,
                status=TransactionStatus.PENDING,
            )

        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            return TransactionResult(
                tx_hash="",
                status=TransactionStatus.FAILED,
                error=str(e),
            )

    async def send_and_wait(
        self,
        contract_address: str,
        abi: list[dict[str, Any]],
        function_name: str,
        args: list[Any],
        gas_limit: int | None = None,
        value: int = 0,
        timeout: int = 120,
    ) -> TransactionResult:
        """Send transaction and wait for confirmation.

        Args:
            contract_address: Target contract address
            abi: Contract ABI
            function_name: Name of function to call
            args: Function arguments
            gas_limit: Optional gas limit
            value: Amount of native token to send
            timeout: Confirmation timeout in seconds

        Returns:
            TransactionResult with confirmation details
        """
        # Send transaction
        result = await self.send_transaction(
            contract_address=contract_address,
            abi=abi,
            function_name=function_name,
            args=args,
            gas_limit=gas_limit,
            value=value,
        )

        if result.status == TransactionStatus.FAILED:
            return result

        # Wait for confirmation
        try:
            receipt = await self.client.wait_for_transaction_receipt(
                result.tx_hash, timeout=timeout
            )

            success = receipt.get("status") == 1
            return TransactionResult(
                tx_hash=result.tx_hash,
                status=TransactionStatus.SUCCESS if success else TransactionStatus.FAILED,
                block_number=receipt.get("blockNumber"),
                gas_used=receipt.get("gasUsed"),
                error=None if success else "Transaction reverted",
            )

        except TimeoutError:
            return TransactionResult(
                tx_hash=result.tx_hash,
                status=TransactionStatus.TIMEOUT,
                error=f"Transaction not confirmed within {timeout}s",
            )

    async def get_nonce(self) -> int:
        """Get current nonce for signer address."""
        return await self.client.get_transaction_count(self.account.address)

    async def get_balance(self) -> int:
        """Get native token balance for signer address."""
        return await self.client.get_balance(self.account.address)


# Factory function
def get_transaction_service(
    client: ChainClient | None = None,
    private_key: str | None = None,
) -> TransactionService:
    """Create TransactionService instance.

    Args:
        client: Blockchain client (uses default BSCClient if not provided)
        private_key: Private key (uses config active_approver_key if not provided)

    Returns:
        Configured TransactionService instance

    Raises:
        ValueError: If no private key available
    """
    settings = get_settings()

    if client is None:
        client = BSCClient()

    if private_key is None:
        private_key = settings.active_approver_key
        if not private_key:
            raise ValueError(
                "No private key configured. "
                "Set TESTNET_HOT_WALLET_PK (testnet) or "
                "VIP_APPROVER_PRIVATE_KEY (mainnet)"
            )

    return TransactionService(client=client, private_key=private_key)
