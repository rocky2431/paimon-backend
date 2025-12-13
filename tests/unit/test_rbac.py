"""Tests for RBAC services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.services.rbac.definitions import (
    OnChainRole,
    Permission,
    SystemRole,
    get_combined_permissions,
    get_permissions_for_onchain_role,
    get_permissions_for_system_role,
    SYSTEM_ROLE_PERMISSIONS,
    ONCHAIN_ROLE_PERMISSIONS,
)
from app.services.rbac.onchain_roles import (
    OnChainRoleService,
    ROLE_HASHES,
)
from app.services.rbac.rbac_service import (
    RBACService,
    UserRoles,
)
from app.services.rbac.dependencies import (
    require_permission,
    require_system_role,
)
from app.services.auth.dependencies import AuthenticatedUser


class TestRoleDefinitions:
    """Tests for role and permission definitions."""

    def test_system_roles_defined(self):
        """Test all system roles are defined."""
        assert len(SystemRole) == 7
        assert SystemRole.SUPER_ADMIN in SystemRole
        assert SystemRole.ADMIN in SystemRole
        assert SystemRole.USER in SystemRole

    def test_onchain_roles_defined(self):
        """Test all on-chain roles are defined."""
        assert len(OnChainRole) == 7
        assert OnChainRole.ADMIN in OnChainRole
        assert OnChainRole.APPROVER in OnChainRole
        assert OnChainRole.EMERGENCY_ADMIN in OnChainRole

    def test_permissions_defined(self):
        """Test permissions are properly defined."""
        assert Permission.PORTFOLIO_READ in Permission
        assert Permission.REDEMPTION_APPROVE in Permission
        assert Permission.RISK_EMERGENCY in Permission

    def test_super_admin_has_all_permissions(self):
        """Test super admin has all permissions."""
        permissions = get_permissions_for_system_role(SystemRole.SUPER_ADMIN)
        assert len(permissions) == len(Permission)

    def test_user_role_permissions(self):
        """Test user role has correct permissions."""
        permissions = get_permissions_for_system_role(SystemRole.USER)
        assert Permission.PORTFOLIO_READ in permissions
        assert Permission.REDEMPTION_CREATE in permissions
        assert Permission.REDEMPTION_APPROVE not in permissions
        assert Permission.RISK_EMERGENCY not in permissions

    def test_approver_onchain_permissions(self):
        """Test approver on-chain role permissions."""
        permissions = get_permissions_for_onchain_role(OnChainRole.APPROVER)
        assert Permission.REDEMPTION_APPROVE in permissions
        assert Permission.REDEMPTION_REJECT in permissions
        assert Permission.RISK_EMERGENCY not in permissions

    def test_emergency_admin_onchain_permissions(self):
        """Test emergency admin on-chain role permissions."""
        permissions = get_permissions_for_onchain_role(OnChainRole.EMERGENCY_ADMIN)
        assert Permission.RISK_EMERGENCY in permissions


class TestCombinedPermissions:
    """Tests for combined permission calculation."""

    def test_combine_system_roles(self):
        """Test combining system roles."""
        permissions = get_combined_permissions(
            system_roles=[SystemRole.USER, SystemRole.ANALYST],
            onchain_roles=[],
        )

        # Should have USER permissions
        assert Permission.PORTFOLIO_READ in permissions
        assert Permission.REDEMPTION_CREATE in permissions

        # Should have ANALYST permissions
        assert Permission.SYSTEM_METRICS in permissions

    def test_combine_onchain_roles(self):
        """Test combining on-chain roles."""
        permissions = get_combined_permissions(
            system_roles=[],
            onchain_roles=[OnChainRole.APPROVER, OnChainRole.SETTLER],
        )

        assert Permission.REDEMPTION_APPROVE in permissions
        assert Permission.REDEMPTION_SETTLE in permissions

    def test_combine_both_layers(self):
        """Test combining both system and on-chain roles."""
        permissions = get_combined_permissions(
            system_roles=[SystemRole.USER],
            onchain_roles=[OnChainRole.APPROVER],
        )

        # User permissions
        assert Permission.PORTFOLIO_READ in permissions
        assert Permission.REDEMPTION_CREATE in permissions

        # Approver permissions
        assert Permission.REDEMPTION_APPROVE in permissions

    def test_empty_roles(self):
        """Test empty role lists."""
        permissions = get_combined_permissions(
            system_roles=[],
            onchain_roles=[],
        )
        assert len(permissions) == 0


class TestOnChainRoleService:
    """Tests for on-chain role service."""

    def test_role_hashes_defined(self):
        """Test role hashes are defined for all on-chain roles."""
        for role in OnChainRole:
            assert role in ROLE_HASHES
            # Hash is 64 hex chars (may or may not have 0x prefix)
            hash_value = ROLE_HASHES[role]
            clean_hash = hash_value[2:] if hash_value.startswith("0x") else hash_value
            assert len(clean_hash) == 64

    def test_role_hash_format(self):
        """Test role hash format is correct."""
        service = OnChainRoleService()
        hash_value = service.get_role_hash(OnChainRole.ADMIN)
        # Hash is 64 hex chars (may or may not have 0x prefix)
        clean_hash = hash_value[2:] if hash_value.startswith("0x") else hash_value
        assert len(clean_hash) == 64

    def test_role_from_hash(self):
        """Test looking up role from hash."""
        admin_hash = ROLE_HASHES[OnChainRole.ADMIN]
        role = OnChainRoleService.role_from_hash(admin_hash)
        assert role == OnChainRole.ADMIN

    def test_role_from_invalid_hash(self):
        """Test invalid hash returns None."""
        role = OnChainRoleService.role_from_hash("0x" + "0" * 64)
        assert role is None

    def test_service_initialization(self):
        """Test service initializes correctly."""
        service = OnChainRoleService(
            contract_addresses={"vault": "0x1234567890123456789012345678901234567890"}
        )
        assert "vault" in service.contract_addresses

    @pytest.mark.asyncio
    async def test_has_role_without_client(self):
        """Test has_role returns False without client."""
        service = OnChainRoleService()
        result = await service.has_role(
            "0x1234567890123456789012345678901234567890",
            OnChainRole.ADMIN,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_get_roles_without_client(self):
        """Test get_roles returns empty list without client."""
        service = OnChainRoleService()
        roles = await service.get_roles(
            "0x1234567890123456789012345678901234567890"
        )
        assert roles == []


class TestRBACService:
    """Tests for RBAC service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rbac_service = RBACService()
        # Clear stored roles between tests
        RBACService._user_system_roles = {}

    def test_assign_system_role(self):
        """Test assigning system role."""
        result = self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        assert result is True
        assert SystemRole.ADMIN in self.rbac_service.get_system_roles("user1")

    def test_assign_duplicate_role(self):
        """Test assigning same role twice returns False."""
        self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        result = self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        assert result is False

    def test_revoke_system_role(self):
        """Test revoking system role."""
        self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        result = self.rbac_service.revoke_system_role("user1", SystemRole.ADMIN)
        assert result is True
        assert SystemRole.ADMIN not in self.rbac_service.get_system_roles("user1")

    def test_revoke_nonexistent_role(self):
        """Test revoking role user doesn't have returns False."""
        result = self.rbac_service.revoke_system_role("user1", SystemRole.ADMIN)
        assert result is False

    def test_get_system_roles_empty(self):
        """Test getting roles for user without roles."""
        roles = self.rbac_service.get_system_roles("nonexistent")
        assert roles == []

    def test_has_system_role(self):
        """Test has_system_role check."""
        self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        assert self.rbac_service.has_system_role("user1", SystemRole.ADMIN)
        assert not self.rbac_service.has_system_role("user1", SystemRole.SUPER_ADMIN)

    def test_is_super_admin(self):
        """Test is_super_admin check."""
        self.rbac_service.assign_system_role("user1", SystemRole.SUPER_ADMIN)
        assert self.rbac_service.is_super_admin("user1")
        assert not self.rbac_service.is_super_admin("user2")

    def test_check_system_permission(self):
        """Test checking permission via system role."""
        self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        assert self.rbac_service.check_system_permission(
            "user1", Permission.REDEMPTION_APPROVE
        )
        assert not self.rbac_service.check_system_permission(
            "user2", Permission.REDEMPTION_APPROVE
        )

    @pytest.mark.asyncio
    async def test_check_permission(self):
        """Test checking permission from any layer."""
        self.rbac_service.assign_system_role("user1", SystemRole.USER)
        assert await self.rbac_service.check_permission(
            "user1", Permission.PORTFOLIO_READ
        )
        assert not await self.rbac_service.check_permission(
            "user1", Permission.REDEMPTION_APPROVE
        )

    @pytest.mark.asyncio
    async def test_get_user_roles(self):
        """Test getting all user roles."""
        self.rbac_service.assign_system_role("user1", SystemRole.USER)
        self.rbac_service.assign_system_role("user1", SystemRole.ANALYST)

        user_roles = await self.rbac_service.get_user_roles("user1")

        assert isinstance(user_roles, UserRoles)
        assert SystemRole.USER in user_roles.system_roles
        assert SystemRole.ANALYST in user_roles.system_roles
        assert len(user_roles.permissions) > 0

    @pytest.mark.asyncio
    async def test_check_any_permission(self):
        """Test checking if user has any of permissions."""
        self.rbac_service.assign_system_role("user1", SystemRole.USER)

        assert await self.rbac_service.check_any_permission(
            "user1",
            [Permission.PORTFOLIO_READ, Permission.REDEMPTION_APPROVE],
        )
        assert not await self.rbac_service.check_any_permission(
            "user1",
            [Permission.REDEMPTION_APPROVE, Permission.RISK_EMERGENCY],
        )

    @pytest.mark.asyncio
    async def test_check_all_permissions(self):
        """Test checking if user has all permissions."""
        self.rbac_service.assign_system_role("user1", SystemRole.USER)

        assert await self.rbac_service.check_all_permissions(
            "user1",
            [Permission.PORTFOLIO_READ, Permission.REDEMPTION_CREATE],
        )
        assert not await self.rbac_service.check_all_permissions(
            "user1",
            [Permission.PORTFOLIO_READ, Permission.REDEMPTION_APPROVE],
        )

    @pytest.mark.asyncio
    async def test_can_approve_redemption(self):
        """Test can_approve_redemption check."""
        self.rbac_service.assign_system_role("user1", SystemRole.ADMIN)
        assert await self.rbac_service.can_approve_redemption("user1")

        self.rbac_service.assign_system_role("user2", SystemRole.USER)
        assert not await self.rbac_service.can_approve_redemption("user2")


class TestUserRoles:
    """Tests for UserRoles model."""

    def test_user_roles_creation(self):
        """Test creating UserRoles model."""
        user_roles = UserRoles(
            wallet_address="0x1234567890123456789012345678901234567890",
            system_roles=[SystemRole.ADMIN],
            onchain_roles=[OnChainRole.APPROVER],
            permissions=[Permission.REDEMPTION_APPROVE],
        )

        assert user_roles.wallet_address == "0x1234567890123456789012345678901234567890"
        assert SystemRole.ADMIN in user_roles.system_roles
        assert OnChainRole.APPROVER in user_roles.onchain_roles

    def test_user_roles_defaults(self):
        """Test UserRoles default values."""
        user_roles = UserRoles()
        assert user_roles.wallet_address is None
        assert user_roles.system_roles == []
        assert user_roles.onchain_roles == []
        assert user_roles.permissions == []


class TestRBACDependencies:
    """Tests for RBAC dependencies."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear stored roles between tests
        RBACService._user_system_roles = {}

    @pytest.mark.asyncio
    async def test_require_permission_passes(self):
        """Test require_permission allows users with permission."""
        user = AuthenticatedUser(user_id="dep_user1", roles=["user"])
        rbac_service = RBACService()
        rbac_service.assign_system_role("dep_user1", SystemRole.ADMIN)

        checker = require_permission(Permission.REDEMPTION_APPROVE)
        result = await checker(user, rbac_service)

        assert result == user

    @pytest.mark.asyncio
    async def test_require_permission_fails(self):
        """Test require_permission rejects users without permission."""
        user = AuthenticatedUser(user_id="dep_user2", roles=["user"])
        rbac_service = RBACService()
        rbac_service.assign_system_role("dep_user2", SystemRole.USER)

        checker = require_permission(Permission.REDEMPTION_APPROVE)

        with pytest.raises(HTTPException) as exc_info:
            await checker(user, rbac_service)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_system_role_passes(self):
        """Test require_system_role allows users with role."""
        user = AuthenticatedUser(user_id="dep_user3", roles=["user"])
        rbac_service = RBACService()
        rbac_service.assign_system_role("dep_user3", SystemRole.ADMIN)

        checker = require_system_role(SystemRole.ADMIN)
        result = await checker(user, rbac_service)

        assert result == user

    @pytest.mark.asyncio
    async def test_require_system_role_fails(self):
        """Test require_system_role rejects users without role."""
        user = AuthenticatedUser(user_id="dep_user4", roles=["user"])
        rbac_service = RBACService()
        # Don't assign any roles

        checker = require_system_role(SystemRole.ADMIN)

        with pytest.raises(HTTPException) as exc_info:
            await checker(user, rbac_service)

        assert exc_info.value.status_code == 403
