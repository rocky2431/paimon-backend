"""Authentication API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.auth import (
    CurrentUser,
    JWTService,
    NonceData,
    TokenPair,
    WalletAuthService,
    get_jwt_service,
    get_wallet_auth_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# Request/Response Models
class NonceRequest(BaseModel):
    """Request for authentication nonce."""

    wallet_address: str = Field(
        ...,
        description="Wallet address to authenticate",
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )


class NonceResponse(BaseModel):
    """Response with nonce for signing."""

    nonce: str
    message: str
    expires_at: int


class WalletLoginRequest(BaseModel):
    """Request for wallet login with signature."""

    wallet_address: str = Field(
        ...,
        description="Wallet address",
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )
    signature: str = Field(
        ...,
        description="Signature of the nonce message",
    )
    nonce: str = Field(
        ...,
        description="Nonce that was signed",
    )


class RefreshTokenRequest(BaseModel):
    """Request to refresh tokens."""

    refresh_token: str = Field(..., description="Valid refresh token")


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserInfoResponse(BaseModel):
    """Current user information."""

    user_id: str
    wallet_address: str | None
    roles: list[str]
    permissions: list[str]


# Endpoints
@router.post("/nonce", response_model=NonceResponse)
async def request_nonce(
    request: NonceRequest,
    wallet_auth: Annotated[WalletAuthService, Depends(get_wallet_auth_service)],
) -> NonceResponse:
    """Request a nonce for wallet authentication.

    This nonce must be signed by the wallet and submitted to /auth/login.
    The nonce expires after 5 minutes.
    """
    if not wallet_auth.is_valid_address(request.wallet_address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid wallet address",
        )

    nonce_data = wallet_auth.generate_nonce(request.wallet_address)

    return NonceResponse(
        nonce=nonce_data.nonce,
        message=nonce_data.message,
        expires_at=nonce_data.expires_at,
    )


@router.post("/login", response_model=TokenResponse)
async def wallet_login(
    request: WalletLoginRequest,
    wallet_auth: Annotated[WalletAuthService, Depends(get_wallet_auth_service)],
    jwt_service: Annotated[JWTService, Depends(get_jwt_service)],
) -> TokenResponse:
    """Login with wallet signature.

    The user must first request a nonce, sign it with their wallet,
    and submit the signature here.
    """
    # Verify signature
    result = wallet_auth.verify_signature(
        wallet_address=request.wallet_address,
        signature=request.signature,
        nonce=request.nonce,
    )

    if not result.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "Authentication failed",
        )

    # TODO: Look up user roles/permissions from database
    # For now, use default roles based on wallet
    roles = ["user"]
    permissions = ["read:portfolio", "create:redemption"]

    # Create tokens
    token_pair = jwt_service.create_token_pair(
        subject=result.wallet_address,  # Use wallet address as subject
        wallet_address=result.wallet_address,
        roles=roles,
        permissions=permissions,
    )

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: RefreshTokenRequest,
    jwt_service: Annotated[JWTService, Depends(get_jwt_service)],
) -> TokenResponse:
    """Refresh access token using refresh token.

    Submit a valid refresh token to get new access and refresh tokens.
    """
    # TODO: Look up user roles/permissions from database
    roles = ["user"]
    permissions = ["read:portfolio", "create:redemption"]

    token_pair = jwt_service.refresh_tokens(
        refresh_token=request.refresh_token,
        roles=roles,
        permissions=permissions,
    )

    if not token_pair:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    user: CurrentUser,
) -> UserInfoResponse:
    """Get current authenticated user information."""
    return UserInfoResponse(
        user_id=user.user_id,
        wallet_address=user.wallet_address,
        roles=user.roles,
        permissions=user.permissions,
    )


@router.post("/logout")
async def logout() -> dict:
    """Logout current user.

    Note: JWT tokens are stateless, so this endpoint is mainly for
    client-side token cleanup. In production, you may want to:
    - Add the token to a blacklist (requires Redis)
    - Revoke refresh tokens
    """
    return {"message": "Successfully logged out"}
