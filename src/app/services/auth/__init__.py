"""Authentication services module."""

from app.services.auth.dependencies import (
    AdminUser,
    AuthenticatedUser,
    CurrentUser,
    OptionalUser,
    WalletUser,
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_all_roles,
    require_permissions,
    require_roles,
    require_wallet_address,
)
from app.services.auth.jwt_service import (
    JWTService,
    TokenPair,
    TokenPayload,
    get_jwt_service,
)
from app.services.auth.wallet_auth import (
    NonceData,
    SignatureVerificationResult,
    WalletAuthService,
    get_wallet_auth_service,
)

__all__ = [
    # JWT
    "JWTService",
    "TokenPayload",
    "TokenPair",
    "get_jwt_service",
    # Wallet Auth
    "WalletAuthService",
    "NonceData",
    "SignatureVerificationResult",
    "get_wallet_auth_service",
    # Dependencies
    "AuthenticatedUser",
    "get_current_user",
    "get_current_user_optional",
    "require_roles",
    "require_all_roles",
    "require_permissions",
    "require_admin",
    "require_wallet_address",
    # Type aliases
    "CurrentUser",
    "OptionalUser",
    "AdminUser",
    "WalletUser",
]
