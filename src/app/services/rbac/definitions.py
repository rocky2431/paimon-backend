"""Role and permission definitions for dual-layer RBAC system.

Dual-Layer RBAC:
- Layer 1 (On-chain): Roles from smart contracts (Admin, Approver, Manager, etc.)
- Layer 2 (System): Internal system roles (SuperAdmin, Operator, Auditor, etc.)

Each role has a set of permissions that define what actions the user can perform.
"""

from enum import Enum
from typing import FrozenSet


class OnChainRole(str, Enum):
    """On-chain roles from smart contracts (Layer 1).

    These roles are read from the blockchain and represent
    actual on-chain permissions.
    """

    # Vault roles
    ADMIN = "ADMIN"  # Full admin access to vault
    MANAGER = "MANAGER"  # Can manage vault parameters
    OPERATOR = "OPERATOR"  # Can execute operations

    # Redemption roles
    APPROVER = "APPROVER"  # Can approve redemption requests
    SETTLER = "SETTLER"  # Can settle redemptions

    # Risk roles
    RISK_MANAGER = "RISK_MANAGER"  # Can manage risk parameters
    EMERGENCY_ADMIN = "EMERGENCY_ADMIN"  # Can trigger emergency mode


class SystemRole(str, Enum):
    """System internal roles (Layer 2).

    These roles are managed in the database and represent
    system-level permissions.
    """

    SUPER_ADMIN = "SUPER_ADMIN"  # Full system access
    ADMIN = "ADMIN"  # Administrative access
    OPERATOR = "OPERATOR"  # Operational access
    AUDITOR = "AUDITOR"  # Read-only audit access
    ANALYST = "ANALYST"  # Analytics and reporting access
    USER = "USER"  # Basic user access
    VIEWER = "VIEWER"  # View-only access


class Permission(str, Enum):
    """System permissions.

    Fine-grained permissions for specific actions.
    Format: <resource>:<action>
    """

    # Portfolio permissions
    PORTFOLIO_READ = "portfolio:read"
    PORTFOLIO_WRITE = "portfolio:write"

    # Redemption permissions
    REDEMPTION_CREATE = "redemption:create"
    REDEMPTION_READ = "redemption:read"
    REDEMPTION_APPROVE = "redemption:approve"
    REDEMPTION_REJECT = "redemption:reject"
    REDEMPTION_SETTLE = "redemption:settle"
    REDEMPTION_CANCEL = "redemption:cancel"

    # Asset permissions
    ASSET_READ = "asset:read"
    ASSET_WRITE = "asset:write"
    ASSET_REBALANCE = "asset:rebalance"

    # Risk permissions
    RISK_READ = "risk:read"
    RISK_WRITE = "risk:write"
    RISK_EMERGENCY = "risk:emergency"

    # Audit permissions
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"

    # User permissions
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_ROLES = "user:roles"

    # System permissions
    SYSTEM_CONFIG = "system:config"
    SYSTEM_METRICS = "system:metrics"
    SYSTEM_LOGS = "system:logs"


# Role to permission mappings
SYSTEM_ROLE_PERMISSIONS: dict[SystemRole, FrozenSet[Permission]] = {
    SystemRole.SUPER_ADMIN: frozenset(Permission),  # All permissions
    SystemRole.ADMIN: frozenset([
        Permission.PORTFOLIO_READ,
        Permission.PORTFOLIO_WRITE,
        Permission.REDEMPTION_READ,
        Permission.REDEMPTION_APPROVE,
        Permission.REDEMPTION_REJECT,
        Permission.REDEMPTION_SETTLE,
        Permission.ASSET_READ,
        Permission.ASSET_WRITE,
        Permission.RISK_READ,
        Permission.RISK_WRITE,
        Permission.AUDIT_READ,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_ROLES,
        Permission.SYSTEM_CONFIG,
        Permission.SYSTEM_METRICS,
    ]),
    SystemRole.OPERATOR: frozenset([
        Permission.PORTFOLIO_READ,
        Permission.REDEMPTION_READ,
        Permission.REDEMPTION_CREATE,
        Permission.REDEMPTION_SETTLE,
        Permission.ASSET_READ,
        Permission.ASSET_REBALANCE,
        Permission.RISK_READ,
        Permission.SYSTEM_METRICS,
    ]),
    SystemRole.AUDITOR: frozenset([
        Permission.PORTFOLIO_READ,
        Permission.REDEMPTION_READ,
        Permission.ASSET_READ,
        Permission.RISK_READ,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        Permission.SYSTEM_LOGS,
    ]),
    SystemRole.ANALYST: frozenset([
        Permission.PORTFOLIO_READ,
        Permission.REDEMPTION_READ,
        Permission.ASSET_READ,
        Permission.RISK_READ,
        Permission.SYSTEM_METRICS,
    ]),
    SystemRole.USER: frozenset([
        Permission.PORTFOLIO_READ,
        Permission.REDEMPTION_CREATE,
        Permission.REDEMPTION_READ,
        Permission.REDEMPTION_CANCEL,
    ]),
    SystemRole.VIEWER: frozenset([
        Permission.PORTFOLIO_READ,
        Permission.REDEMPTION_READ,
        Permission.ASSET_READ,
    ]),
}


# On-chain role to permission mappings
ONCHAIN_ROLE_PERMISSIONS: dict[OnChainRole, FrozenSet[Permission]] = {
    OnChainRole.ADMIN: frozenset([
        Permission.ASSET_WRITE,
        Permission.ASSET_REBALANCE,
        Permission.RISK_WRITE,
        Permission.RISK_EMERGENCY,
        Permission.SYSTEM_CONFIG,
    ]),
    OnChainRole.MANAGER: frozenset([
        Permission.ASSET_WRITE,
        Permission.ASSET_REBALANCE,
        Permission.RISK_WRITE,
    ]),
    OnChainRole.OPERATOR: frozenset([
        Permission.ASSET_REBALANCE,
        Permission.SYSTEM_METRICS,
    ]),
    OnChainRole.APPROVER: frozenset([
        Permission.REDEMPTION_APPROVE,
        Permission.REDEMPTION_REJECT,
    ]),
    OnChainRole.SETTLER: frozenset([
        Permission.REDEMPTION_SETTLE,
    ]),
    OnChainRole.RISK_MANAGER: frozenset([
        Permission.RISK_READ,
        Permission.RISK_WRITE,
    ]),
    OnChainRole.EMERGENCY_ADMIN: frozenset([
        Permission.RISK_EMERGENCY,
    ]),
}


def get_permissions_for_system_role(role: SystemRole) -> FrozenSet[Permission]:
    """Get all permissions for a system role.

    Args:
        role: System role

    Returns:
        Set of permissions for the role
    """
    return SYSTEM_ROLE_PERMISSIONS.get(role, frozenset())


def get_permissions_for_onchain_role(role: OnChainRole) -> FrozenSet[Permission]:
    """Get all permissions for an on-chain role.

    Args:
        role: On-chain role

    Returns:
        Set of permissions for the role
    """
    return ONCHAIN_ROLE_PERMISSIONS.get(role, frozenset())


def get_combined_permissions(
    system_roles: list[SystemRole],
    onchain_roles: list[OnChainRole],
) -> set[Permission]:
    """Get combined permissions from both system and on-chain roles.

    Args:
        system_roles: List of system roles
        onchain_roles: List of on-chain roles

    Returns:
        Combined set of all permissions
    """
    permissions: set[Permission] = set()

    for role in system_roles:
        permissions.update(get_permissions_for_system_role(role))

    for role in onchain_roles:
        permissions.update(get_permissions_for_onchain_role(role))

    return permissions
