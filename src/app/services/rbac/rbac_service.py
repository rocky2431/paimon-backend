"""RBAC service for dual-layer permission management."""

import logging
from typing import Any

from pydantic import BaseModel

from app.services.rbac.definitions import (
    OnChainRole,
    Permission,
    SystemRole,
    get_combined_permissions,
    get_permissions_for_onchain_role,
    get_permissions_for_system_role,
)
from app.services.rbac.onchain_roles import OnChainRoleService, get_onchain_role_service

logger = logging.getLogger(__name__)


class UserRoles(BaseModel):
    """User roles from both layers."""

    wallet_address: str | None = None
    system_roles: list[SystemRole] = []
    onchain_roles: list[OnChainRole] = []
    permissions: list[Permission] = []


class RBACService:
    """Dual-layer RBAC service combining system and on-chain roles."""

    # In-memory user roles storage (should use database in production)
    _user_system_roles: dict[str, list[SystemRole]] = {}

    def __init__(
        self,
        onchain_service: OnChainRoleService | None = None,
    ):
        """Initialize RBAC service.

        Args:
            onchain_service: On-chain role service for blockchain role checks
        """
        self.onchain_service = onchain_service

    def assign_system_role(
        self,
        user_id: str,
        role: SystemRole,
    ) -> bool:
        """Assign a system role to a user.

        Args:
            user_id: User identifier
            role: System role to assign

        Returns:
            True if role was assigned
        """
        if user_id not in self._user_system_roles:
            self._user_system_roles[user_id] = []

        if role not in self._user_system_roles[user_id]:
            self._user_system_roles[user_id].append(role)
            logger.info(f"Assigned role {role} to user {user_id}")
            return True

        return False

    def revoke_system_role(
        self,
        user_id: str,
        role: SystemRole,
    ) -> bool:
        """Revoke a system role from a user.

        Args:
            user_id: User identifier
            role: System role to revoke

        Returns:
            True if role was revoked
        """
        if user_id in self._user_system_roles and role in self._user_system_roles[user_id]:
            self._user_system_roles[user_id].remove(role)
            logger.info(f"Revoked role {role} from user {user_id}")
            return True

        return False

    def get_system_roles(self, user_id: str) -> list[SystemRole]:
        """Get system roles for a user.

        Args:
            user_id: User identifier

        Returns:
            List of system roles
        """
        return self._user_system_roles.get(user_id, [])

    async def get_onchain_roles(
        self,
        wallet_address: str,
        contract_name: str = "vault",
    ) -> list[OnChainRole]:
        """Get on-chain roles for a wallet address.

        Args:
            wallet_address: Wallet address
            contract_name: Contract to check

        Returns:
            List of on-chain roles
        """
        if not self.onchain_service:
            return []

        return await self.onchain_service.get_roles(wallet_address, contract_name)

    async def get_user_roles(
        self,
        user_id: str,
        wallet_address: str | None = None,
    ) -> UserRoles:
        """Get all roles for a user (both layers).

        Args:
            user_id: User identifier
            wallet_address: Optional wallet address for on-chain checks

        Returns:
            UserRoles with all roles and permissions
        """
        system_roles = self.get_system_roles(user_id)
        onchain_roles: list[OnChainRole] = []

        if wallet_address and self.onchain_service:
            onchain_roles = await self.get_onchain_roles(wallet_address)

        permissions = list(get_combined_permissions(system_roles, onchain_roles))

        return UserRoles(
            wallet_address=wallet_address,
            system_roles=system_roles,
            onchain_roles=onchain_roles,
            permissions=permissions,
        )

    def has_system_role(self, user_id: str, role: SystemRole) -> bool:
        """Check if user has a system role.

        Args:
            user_id: User identifier
            role: Role to check

        Returns:
            True if user has the role
        """
        return role in self.get_system_roles(user_id)

    async def has_onchain_role(
        self,
        wallet_address: str,
        role: OnChainRole,
        contract_name: str = "vault",
    ) -> bool:
        """Check if wallet has an on-chain role.

        Args:
            wallet_address: Wallet address
            role: Role to check
            contract_name: Contract to check

        Returns:
            True if wallet has the role
        """
        if not self.onchain_service:
            return False

        return await self.onchain_service.has_role(
            wallet_address, role, contract_name
        )

    def check_system_permission(
        self,
        user_id: str,
        permission: Permission,
    ) -> bool:
        """Check if user has a permission via system roles.

        Args:
            user_id: User identifier
            permission: Permission to check

        Returns:
            True if user has the permission
        """
        system_roles = self.get_system_roles(user_id)

        for role in system_roles:
            role_permissions = get_permissions_for_system_role(role)
            if permission in role_permissions:
                return True

        return False

    async def check_permission(
        self,
        user_id: str,
        permission: Permission,
        wallet_address: str | None = None,
    ) -> bool:
        """Check if user has a permission (from any layer).

        Args:
            user_id: User identifier
            permission: Permission to check
            wallet_address: Optional wallet for on-chain check

        Returns:
            True if user has the permission
        """
        # Check system roles first
        if self.check_system_permission(user_id, permission):
            return True

        # Check on-chain roles
        if wallet_address and self.onchain_service:
            onchain_roles = await self.get_onchain_roles(wallet_address)
            for role in onchain_roles:
                role_permissions = get_permissions_for_onchain_role(role)
                if permission in role_permissions:
                    return True

        return False

    async def check_any_permission(
        self,
        user_id: str,
        permissions: list[Permission],
        wallet_address: str | None = None,
    ) -> bool:
        """Check if user has any of the permissions.

        Args:
            user_id: User identifier
            permissions: Permissions to check
            wallet_address: Optional wallet for on-chain check

        Returns:
            True if user has any of the permissions
        """
        for permission in permissions:
            if await self.check_permission(user_id, permission, wallet_address):
                return True
        return False

    async def check_all_permissions(
        self,
        user_id: str,
        permissions: list[Permission],
        wallet_address: str | None = None,
    ) -> bool:
        """Check if user has all of the permissions.

        Args:
            user_id: User identifier
            permissions: Permissions to check
            wallet_address: Optional wallet for on-chain check

        Returns:
            True if user has all of the permissions
        """
        for permission in permissions:
            if not await self.check_permission(user_id, permission, wallet_address):
                return False
        return True

    def is_super_admin(self, user_id: str) -> bool:
        """Check if user is super admin.

        Args:
            user_id: User identifier

        Returns:
            True if user is super admin
        """
        return self.has_system_role(user_id, SystemRole.SUPER_ADMIN)

    async def can_approve_redemption(
        self,
        user_id: str,
        wallet_address: str | None = None,
    ) -> bool:
        """Check if user can approve redemption requests.

        Args:
            user_id: User identifier
            wallet_address: Optional wallet for on-chain check

        Returns:
            True if user can approve
        """
        return await self.check_permission(
            user_id,
            Permission.REDEMPTION_APPROVE,
            wallet_address,
        )

    async def can_trigger_emergency(
        self,
        user_id: str,
        wallet_address: str | None = None,
    ) -> bool:
        """Check if user can trigger emergency mode.

        Args:
            user_id: User identifier
            wallet_address: Optional wallet for on-chain check

        Returns:
            True if user can trigger emergency
        """
        return await self.check_permission(
            user_id,
            Permission.RISK_EMERGENCY,
            wallet_address,
        )


# Service factory
_rbac_service: RBACService | None = None


def get_rbac_service(
    onchain_service: OnChainRoleService | None = None,
) -> RBACService:
    """Get or create RBAC service.

    Args:
        onchain_service: Optional on-chain role service

    Returns:
        RBACService instance
    """
    global _rbac_service
    if _rbac_service is None:
        _rbac_service = RBACService(onchain_service=onchain_service)
    return _rbac_service
