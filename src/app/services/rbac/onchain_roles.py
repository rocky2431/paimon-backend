"""On-chain role service for reading roles from smart contracts."""

import logging
from typing import Any

from eth_abi import decode
from web3 import Web3

from app.core.config import get_settings
from app.infrastructure.blockchain.client import ChainClient
from app.services.rbac.definitions import OnChainRole

logger = logging.getLogger(__name__)


# AccessControl role hashes (keccak256 of role name)
# These are standard OpenZeppelin AccessControl role identifiers
ROLE_HASHES = {
    OnChainRole.ADMIN: Web3.keccak(text="ADMIN_ROLE").hex(),
    OnChainRole.MANAGER: Web3.keccak(text="MANAGER_ROLE").hex(),
    OnChainRole.OPERATOR: Web3.keccak(text="OPERATOR_ROLE").hex(),
    OnChainRole.APPROVER: Web3.keccak(text="APPROVER_ROLE").hex(),
    OnChainRole.SETTLER: Web3.keccak(text="SETTLER_ROLE").hex(),
    OnChainRole.RISK_MANAGER: Web3.keccak(text="RISK_MANAGER_ROLE").hex(),
    OnChainRole.EMERGENCY_ADMIN: Web3.keccak(text="EMERGENCY_ADMIN_ROLE").hex(),
}

# Reverse mapping for lookup
HASH_TO_ROLE = {v: k for k, v in ROLE_HASHES.items()}


# AccessControl ABI for role checking
ACCESS_CONTROL_ABI = [
    {
        "name": "hasRole",
        "type": "function",
        "inputs": [
            {"name": "role", "type": "bytes32"},
            {"name": "account", "type": "address"},
        ],
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
    },
    {
        "name": "getRoleAdmin",
        "type": "function",
        "inputs": [{"name": "role", "type": "bytes32"}],
        "outputs": [{"type": "bytes32"}],
        "stateMutability": "view",
    },
    {
        "name": "getRoleMemberCount",
        "type": "function",
        "inputs": [{"name": "role", "type": "bytes32"}],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "getRoleMember",
        "type": "function",
        "inputs": [
            {"name": "role", "type": "bytes32"},
            {"name": "index", "type": "uint256"},
        ],
        "outputs": [{"type": "address"}],
        "stateMutability": "view",
    },
]


class OnChainRoleService:
    """Service for checking on-chain roles from smart contracts."""

    def __init__(
        self,
        client: ChainClient | None = None,
        contract_addresses: dict[str, str] | None = None,
    ):
        """Initialize on-chain role service.

        Args:
            client: Blockchain client for RPC calls
            contract_addresses: Mapping of contract names to addresses
        """
        self.client = client
        self.w3 = Web3()

        # Get contract addresses from settings or use provided
        settings = get_settings()
        self.contract_addresses = contract_addresses or {
            "vault": settings.vault_contract_address,
            "redemption_manager": settings.redemption_manager_address,
        }

    def _encode_has_role_call(self, role: OnChainRole, account: str) -> bytes:
        """Encode hasRole function call.

        Args:
            role: Role to check
            account: Account address to check

        Returns:
            Encoded call data
        """
        role_hash = bytes.fromhex(ROLE_HASHES[role][2:])  # Remove '0x' prefix
        # hasRole(bytes32,address) selector: 0x91d14854
        selector = self.w3.keccak(text="hasRole(bytes32,address)")[:4]

        # Encode parameters
        account_bytes = bytes.fromhex(account[2:].lower().zfill(64))
        role_bytes = role_hash.ljust(32, b"\x00")

        return selector + role_bytes + account_bytes

    async def has_role(
        self,
        wallet_address: str,
        role: OnChainRole,
        contract_name: str = "vault",
    ) -> bool:
        """Check if an address has a specific on-chain role.

        Args:
            wallet_address: Address to check
            role: Role to check for
            contract_name: Name of the contract to check

        Returns:
            True if address has the role
        """
        if not self.client:
            logger.warning("No blockchain client available, returning False")
            return False

        contract_address = self.contract_addresses.get(contract_name)
        if not contract_address:
            logger.warning(f"Contract address not found for: {contract_name}")
            return False

        try:
            # Build call data
            call_data = self._encode_has_role_call(role, wallet_address)

            # Execute call
            result = await self.client.eth_call(
                {"to": contract_address, "data": call_data}
            )

            # Decode result (bool)
            has_role = decode(["bool"], result)[0]
            return has_role

        except Exception as e:
            logger.error(f"Failed to check on-chain role: {e}")
            return False

    async def get_roles(
        self,
        wallet_address: str,
        contract_name: str = "vault",
    ) -> list[OnChainRole]:
        """Get all on-chain roles for an address.

        Args:
            wallet_address: Address to check
            contract_name: Name of the contract to check

        Returns:
            List of roles the address has
        """
        roles = []

        for role in OnChainRole:
            if await self.has_role(wallet_address, role, contract_name):
                roles.append(role)

        return roles

    async def get_all_roles(
        self,
        wallet_address: str,
    ) -> dict[str, list[OnChainRole]]:
        """Get all roles across all contracts for an address.

        Args:
            wallet_address: Address to check

        Returns:
            Dictionary mapping contract names to list of roles
        """
        all_roles = {}

        for contract_name in self.contract_addresses:
            roles = await self.get_roles(wallet_address, contract_name)
            if roles:
                all_roles[contract_name] = roles

        return all_roles

    def get_role_hash(self, role: OnChainRole) -> str:
        """Get the keccak256 hash for a role.

        Args:
            role: Role to get hash for

        Returns:
            Role hash as hex string
        """
        return ROLE_HASHES.get(role, "")

    @staticmethod
    def role_from_hash(role_hash: str) -> OnChainRole | None:
        """Get role from its hash.

        Args:
            role_hash: Role hash (hex string)

        Returns:
            OnChainRole or None if not found
        """
        return HASH_TO_ROLE.get(role_hash)


# Service factory
_onchain_role_service: OnChainRoleService | None = None


def get_onchain_role_service(
    client: ChainClient | None = None,
) -> OnChainRoleService:
    """Get or create on-chain role service.

    Args:
        client: Optional blockchain client

    Returns:
        OnChainRoleService instance
    """
    global _onchain_role_service
    if _onchain_role_service is None:
        _onchain_role_service = OnChainRoleService(client=client)
    return _onchain_role_service
