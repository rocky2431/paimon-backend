"""RBAC (Role-Based Access Control) services module."""

from app.services.rbac.definitions import (
    OnChainRole,
    Permission,
    SystemRole,
    get_combined_permissions,
    get_permissions_for_onchain_role,
    get_permissions_for_system_role,
)
from app.services.rbac.dependencies import (
    ApproverUser,
    EmergencyUser,
    SuperAdminUser,
    get_user_with_roles,
    require_all_permissions,
    require_approver,
    require_emergency_access,
    require_onchain_role,
    require_permission,
    require_super_admin,
    require_system_role,
)
from app.services.rbac.onchain_roles import (
    OnChainRoleService,
    get_onchain_role_service,
)
from app.services.rbac.rbac_service import (
    RBACService,
    UserRoles,
    get_rbac_service,
)

__all__ = [
    # Definitions
    "OnChainRole",
    "SystemRole",
    "Permission",
    "get_permissions_for_system_role",
    "get_permissions_for_onchain_role",
    "get_combined_permissions",
    # On-chain service
    "OnChainRoleService",
    "get_onchain_role_service",
    # RBAC service
    "RBACService",
    "UserRoles",
    "get_rbac_service",
    # Dependencies
    "get_user_with_roles",
    "require_permission",
    "require_all_permissions",
    "require_system_role",
    "require_onchain_role",
    "require_super_admin",
    "require_approver",
    "require_emergency_access",
    # Type aliases
    "SuperAdminUser",
    "ApproverUser",
    "EmergencyUser",
]
