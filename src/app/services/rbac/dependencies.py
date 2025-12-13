"""RBAC dependencies for FastAPI."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.services.auth.dependencies import AuthenticatedUser, get_current_user
from app.services.rbac.definitions import OnChainRole, Permission, SystemRole
from app.services.rbac.rbac_service import RBACService, get_rbac_service

logger = logging.getLogger(__name__)


async def get_user_with_roles(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> AuthenticatedUser:
    """Get current user with loaded roles from RBAC service.

    Args:
        user: Current authenticated user
        rbac_service: RBAC service

    Returns:
        User with updated roles
    """
    # Get user roles from RBAC service
    user_roles = await rbac_service.get_user_roles(
        user_id=user.user_id,
        wallet_address=user.wallet_address,
    )

    # Update user with roles and permissions
    user.roles = [r.value for r in user_roles.system_roles]
    user.permissions = [p.value for p in user_roles.permissions]

    return user


def require_permission(*permissions: Permission):
    """Dependency factory for permission-based access control.

    Args:
        permissions: Required permissions (user must have at least one)

    Returns:
        Dependency function
    """

    async def permission_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
        rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
    ) -> AuthenticatedUser:
        """Check if user has required permission."""
        has_permission = await rbac_service.check_any_permission(
            user_id=user.user_id,
            permissions=list(permissions),
            wallet_address=user.wallet_address,
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {', '.join(p.value for p in permissions)}",
            )

        return user

    return permission_checker


def require_all_permissions(*permissions: Permission):
    """Dependency factory requiring all specified permissions.

    Args:
        permissions: Required permissions (user must have all)

    Returns:
        Dependency function
    """

    async def permission_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
        rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
    ) -> AuthenticatedUser:
        """Check if user has all required permissions."""
        has_all = await rbac_service.check_all_permissions(
            user_id=user.user_id,
            permissions=list(permissions),
            wallet_address=user.wallet_address,
        )

        if not has_all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {', '.join(p.value for p in permissions)}",
            )

        return user

    return permission_checker


def require_system_role(*roles: SystemRole):
    """Dependency factory for system role-based access control.

    Args:
        roles: Required system roles (user must have at least one)

    Returns:
        Dependency function
    """

    async def role_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
        rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
    ) -> AuthenticatedUser:
        """Check if user has required system role."""
        for role in roles:
            if rbac_service.has_system_role(user.user_id, role):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required role: {', '.join(r.value for r in roles)}",
        )

    return role_checker


def require_onchain_role(*roles: OnChainRole, contract_name: str = "vault"):
    """Dependency factory for on-chain role-based access control.

    Args:
        roles: Required on-chain roles (user must have at least one)
        contract_name: Contract to check roles against

    Returns:
        Dependency function
    """

    async def role_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
        rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
    ) -> AuthenticatedUser:
        """Check if user has required on-chain role."""
        if not user.wallet_address:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Wallet authentication required for on-chain role check",
            )

        for role in roles:
            if await rbac_service.has_onchain_role(
                user.wallet_address, role, contract_name
            ):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required on-chain role: {', '.join(r.value for r in roles)}",
        )

    return role_checker


async def require_super_admin(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> AuthenticatedUser:
    """Dependency requiring super admin role.

    Args:
        user: Current authenticated user
        rbac_service: RBAC service

    Returns:
        User if super admin

    Raises:
        HTTPException: If user is not super admin
    """
    if not rbac_service.is_super_admin(user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user


async def require_approver(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> AuthenticatedUser:
    """Dependency requiring redemption approver permission.

    Args:
        user: Current authenticated user
        rbac_service: RBAC service

    Returns:
        User if can approve

    Raises:
        HTTPException: If user cannot approve
    """
    can_approve = await rbac_service.can_approve_redemption(
        user_id=user.user_id,
        wallet_address=user.wallet_address,
    )

    if not can_approve:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Redemption approval permission required",
        )

    return user


async def require_emergency_access(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> AuthenticatedUser:
    """Dependency requiring emergency access permission.

    Args:
        user: Current authenticated user
        rbac_service: RBAC service

    Returns:
        User if can trigger emergency

    Raises:
        HTTPException: If user cannot trigger emergency
    """
    can_emergency = await rbac_service.can_trigger_emergency(
        user_id=user.user_id,
        wallet_address=user.wallet_address,
    )

    if not can_emergency:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Emergency access permission required",
        )

    return user


# Type aliases for dependency injection
SuperAdminUser = Annotated[AuthenticatedUser, Depends(require_super_admin)]
ApproverUser = Annotated[AuthenticatedUser, Depends(require_approver)]
EmergencyUser = Annotated[AuthenticatedUser, Depends(require_emergency_access)]
