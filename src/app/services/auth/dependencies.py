"""Authentication dependencies for FastAPI."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth.jwt_service import JWTService, TokenPayload, get_jwt_service

logger = logging.getLogger(__name__)

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents an authenticated user."""

    def __init__(
        self,
        user_id: str,
        wallet_address: str | None = None,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
    ):
        """Initialize authenticated user.

        Args:
            user_id: User ID (subject from token)
            wallet_address: User's wallet address
            roles: User roles
            permissions: User permissions
        """
        self.user_id = user_id
        self.wallet_address = wallet_address
        self.roles = roles or []
        self.permissions = permissions or []

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def has_any_role(self, roles: list[str]) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in roles)

    def has_all_roles(self, roles: list[str]) -> bool:
        """Check if user has all of the specified roles."""
        return all(role in self.roles for role in roles)

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return "admin" in self.roles


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    jwt_service: Annotated[JWTService, Depends(get_jwt_service)],
) -> AuthenticatedUser:
    """Get current authenticated user from JWT token.

    Args:
        credentials: Bearer token from request
        jwt_service: JWT service for token verification

    Returns:
        AuthenticatedUser if token is valid

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = jwt_service.verify_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        user_id=payload.sub,
        wallet_address=payload.wallet_address,
        roles=payload.roles,
        permissions=payload.permissions,
    )


async def get_current_user_optional(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    jwt_service: Annotated[JWTService, Depends(get_jwt_service)],
) -> AuthenticatedUser | None:
    """Get current user if authenticated, None otherwise.

    Args:
        credentials: Bearer token from request
        jwt_service: JWT service for token verification

    Returns:
        AuthenticatedUser if token is valid, None otherwise
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = jwt_service.verify_access_token(token)

    if not payload:
        return None

    return AuthenticatedUser(
        user_id=payload.sub,
        wallet_address=payload.wallet_address,
        roles=payload.roles,
        permissions=payload.permissions,
    )


def require_roles(*roles: str):
    """Dependency factory for role-based access control.

    Args:
        roles: Required roles (user must have at least one)

    Returns:
        Dependency function
    """

    async def role_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        """Check if user has required role."""
        if not user.has_any_role(list(roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return user

    return role_checker


def require_all_roles(*roles: str):
    """Dependency factory requiring all specified roles.

    Args:
        roles: Required roles (user must have all)

    Returns:
        Dependency function
    """

    async def role_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        """Check if user has all required roles."""
        if not user.has_all_roles(list(roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires all roles: {', '.join(roles)}",
            )
        return user

    return role_checker


def require_permissions(*permissions: str):
    """Dependency factory for permission-based access control.

    Args:
        permissions: Required permissions (user must have at least one)

    Returns:
        Dependency function
    """

    async def permission_checker(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        """Check if user has required permission."""
        if not any(user.has_permission(p) for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of permissions: {', '.join(permissions)}",
            )
        return user

    return permission_checker


async def require_admin(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Dependency requiring admin role.

    Args:
        user: Current authenticated user

    Returns:
        User if admin

    Raises:
        HTTPException: If user is not admin
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_wallet_address(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Dependency requiring wallet address in token.

    Args:
        user: Current authenticated user

    Returns:
        User if wallet address is present

    Raises:
        HTTPException: If wallet address is missing
    """
    if not user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wallet authentication required",
        )
    return user


# Type aliases for dependency injection
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)]
AdminUser = Annotated[AuthenticatedUser, Depends(require_admin)]
WalletUser = Annotated[AuthenticatedUser, Depends(require_wallet_address)]
