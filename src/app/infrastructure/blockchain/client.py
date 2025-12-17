"""Blockchain client with multi-RPC failover support."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.exceptions import Web3RPCError
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import BlockIdentifier, TxParams, Wei

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ChainClient(ABC):
    """Abstract base class for blockchain clients."""

    @abstractmethod
    async def get_block_number(self) -> int:
        """Get current block number."""
        ...

    @abstractmethod
    async def get_block(self, block_identifier: BlockIdentifier) -> dict[str, Any]:
        """Get block by number or hash."""
        ...

    @abstractmethod
    async def eth_call(
        self, transaction: TxParams, block_identifier: BlockIdentifier = "latest"
    ) -> bytes:
        """Execute eth_call (read-only contract call)."""
        ...

    @abstractmethod
    async def get_logs(
        self,
        from_block: int,
        to_block: int,
        address: str | list[str] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get logs matching filter."""
        ...

    @abstractmethod
    async def get_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        """Get transaction receipt."""
        ...


class BSCClient(ChainClient):
    """BSC (Binance Smart Chain) client with multi-RPC failover."""

    def __init__(
        self,
        rpc_urls: list[str] | None = None,
        chain_id: int | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize BSC client.

        Args:
            rpc_urls: List of RPC endpoints (primary + backups).
                     If None, uses config based on blockchain_network setting.
            chain_id: Chain ID (56 for BSC mainnet, 97 for testnet).
                     If None, uses config based on blockchain_network setting.
            max_retries: Maximum retry attempts per RPC
            retry_delay: Delay between retries in seconds
        """
        settings = get_settings()
        # Use active network settings if not explicitly provided
        self.rpc_urls = rpc_urls or [
            settings.active_rpc_url,
            *settings.active_backup_rpc_urls,
        ]
        self.chain_id = chain_id if chain_id is not None else settings.chain_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._current_rpc_index = 0
        self._web3: AsyncWeb3 | None = None

    @property
    def web3(self) -> AsyncWeb3:
        """Get or create Web3 instance."""
        if self._web3 is None:
            self._web3 = self._create_web3()
        return self._web3

    def _create_web3(self, rpc_index: int | None = None) -> AsyncWeb3:
        """Create Web3 instance for specified RPC with POA middleware."""
        index = rpc_index if rpc_index is not None else self._current_rpc_index
        rpc_url = self.rpc_urls[index]
        w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        # BSC is a POA chain, need middleware to handle extraData
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

    async def _execute_with_failover(
        self, method: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute method with automatic RPC failover.

        Args:
            method: Web3 method name to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Result from the Web3 method

        Raises:
            Web3RPCError: If all RPCs fail
        """
        last_error: Exception | None = None

        for rpc_offset in range(len(self.rpc_urls)):
            rpc_index = (self._current_rpc_index + rpc_offset) % len(self.rpc_urls)
            web3 = self._create_web3(rpc_index)

            for attempt in range(self.max_retries):
                try:
                    # Get the method from web3.eth
                    web3_method = getattr(web3.eth, method)
                    result = await web3_method(*args, **kwargs)

                    # Success - update current RPC index
                    self._current_rpc_index = rpc_index
                    self._web3 = web3

                    return result

                except Web3RPCError as e:
                    last_error = e
                    logger.warning(
                        f"RPC {self.rpc_urls[rpc_index]} failed (attempt {attempt + 1}): {e}"
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"RPC {self.rpc_urls[rpc_index]} error (attempt {attempt + 1}): {e}"
                    )
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))

            # Try next RPC
            logger.warning(
                f"Switching from RPC {self.rpc_urls[rpc_index]} to next backup"
            )

        # All RPCs failed
        raise Web3RPCError(f"All RPCs failed. Last error: {last_error}")

    async def get_block_number(self) -> int:
        """Get current block number."""
        return await self._execute_with_failover("get_block_number")

    async def get_block(self, block_identifier: BlockIdentifier) -> dict[str, Any]:
        """Get block by number or hash."""
        block = await self._execute_with_failover("get_block", block_identifier)
        return dict(block) if block else {}

    async def eth_call(
        self, transaction: TxParams, block_identifier: BlockIdentifier = "latest"
    ) -> bytes:
        """Execute eth_call (read-only contract call)."""
        return await self._execute_with_failover("call", transaction, block_identifier)

    async def get_logs(
        self,
        from_block: int,
        to_block: int,
        address: str | list[str] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get logs matching filter."""
        filter_params: dict[str, Any] = {
            "fromBlock": from_block,
            "toBlock": to_block,
        }
        if address:
            filter_params["address"] = address
        if topics:
            filter_params["topics"] = topics

        logs = await self._execute_with_failover("get_logs", filter_params)
        return [dict(log) for log in logs]

    async def get_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        """Get transaction receipt."""
        receipt = await self._execute_with_failover("get_transaction_receipt", tx_hash)
        return dict(receipt) if receipt else None

    async def get_balance(self, address: str) -> Wei:
        """Get ETH/BNB balance of address."""
        return await self._execute_with_failover("get_balance", address)

    async def get_transaction_count(self, address: str) -> int:
        """Get transaction count (nonce) for address."""
        return await self._execute_with_failover("get_transaction_count", address)

    async def estimate_gas(self, transaction: TxParams) -> int:
        """Estimate gas for transaction."""
        return await self._execute_with_failover("estimate_gas", transaction)

    async def get_gas_price(self) -> Wei:
        """Get current gas price."""
        # AsyncWeb3 uses gas_price property, not method
        return await self.web3.eth.gas_price

    async def health_check(self) -> bool:
        """Check if client is connected and RPC is healthy."""
        try:
            block_number = await self.get_block_number()
            return block_number > 0
        except Exception:
            return False

    async def send_raw_transaction(self, signed_tx: bytes) -> str:
        """Send signed raw transaction.

        Args:
            signed_tx: Signed transaction bytes

        Returns:
            Transaction hash as hex string
        """
        tx_hash = await self._execute_with_failover("send_raw_transaction", signed_tx)
        return tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)

    async def wait_for_transaction_receipt(
        self, tx_hash: str, timeout: int = 120, poll_latency: float = 2.0
    ) -> dict[str, Any]:
        """Wait for transaction receipt with timeout.

        Args:
            tx_hash: Transaction hash
            timeout: Maximum wait time in seconds
            poll_latency: Polling interval in seconds

        Returns:
            Transaction receipt

        Raises:
            TimeoutError: If transaction not confirmed within timeout
        """
        elapsed = 0.0
        while elapsed < timeout:
            receipt = await self.get_transaction_receipt(tx_hash)
            if receipt and receipt.get("blockNumber") is not None:
                return receipt
            await asyncio.sleep(poll_latency)
            elapsed += poll_latency

        raise TimeoutError(f"Transaction {tx_hash} not confirmed within {timeout}s")
