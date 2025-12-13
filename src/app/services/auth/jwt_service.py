"""JWT token service for authentication."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # Subject (wallet address or user id)
    exp: datetime  # Expiration time
    iat: datetime  # Issued at time
    type: str  # Token type: "access" or "refresh"
    wallet_address: str | None = None
    roles: list[str] = []
    permissions: list[str] = []


class TokenPair(BaseModel):
    """Access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # Access token expiration in seconds


class JWTService:
    """Service for creating and validating JWT tokens."""

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int | None = None,
        refresh_token_expire_days: int | None = None,
    ):
        """Initialize JWT service.

        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT algorithm (default: HS256)
            access_token_expire_minutes: Access token expiration in minutes
            refresh_token_expire_days: Refresh token expiration in days
        """
        settings = get_settings()
        self.secret_key = secret_key or settings.secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = (
            access_token_expire_minutes or settings.access_token_expire_minutes
        )
        self.refresh_token_expire_days = (
            refresh_token_expire_days or settings.refresh_token_expire_days
        )

    def create_access_token(
        self,
        subject: str,
        wallet_address: str | None = None,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create an access token.

        Args:
            subject: Token subject (usually wallet address or user id)
            wallet_address: User's wallet address
            roles: User roles
            permissions: User permissions
            extra_claims: Additional claims to include

        Returns:
            Encoded JWT access token
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)

        payload = {
            "sub": subject,
            "exp": expire,
            "iat": now,
            "type": "access",
            "wallet_address": wallet_address,
            "roles": roles or [],
            "permissions": permissions or [],
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(
        self,
        subject: str,
        wallet_address: str | None = None,
    ) -> str:
        """Create a refresh token.

        Args:
            subject: Token subject
            wallet_address: User's wallet address

        Returns:
            Encoded JWT refresh token
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.refresh_token_expire_days)

        payload = {
            "sub": subject,
            "exp": expire,
            "iat": now,
            "type": "refresh",
            "wallet_address": wallet_address,
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_token_pair(
        self,
        subject: str,
        wallet_address: str | None = None,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> TokenPair:
        """Create both access and refresh tokens.

        Args:
            subject: Token subject
            wallet_address: User's wallet address
            roles: User roles
            permissions: User permissions

        Returns:
            TokenPair with both tokens
        """
        access_token = self.create_access_token(
            subject=subject,
            wallet_address=wallet_address,
            roles=roles,
            permissions=permissions,
        )
        refresh_token = self.create_refresh_token(
            subject=subject,
            wallet_address=wallet_address,
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expire_minutes * 60,
        )

    def verify_token(self, token: str) -> TokenPayload | None:
        """Verify and decode a JWT token.

        Args:
            token: JWT token to verify

        Returns:
            TokenPayload if valid, None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            return TokenPayload(**payload)
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            return None

    def verify_access_token(self, token: str) -> TokenPayload | None:
        """Verify an access token specifically.

        Args:
            token: JWT token to verify

        Returns:
            TokenPayload if valid access token, None otherwise
        """
        payload = self.verify_token(token)
        if payload and payload.type == "access":
            return payload
        return None

    def verify_refresh_token(self, token: str) -> TokenPayload | None:
        """Verify a refresh token specifically.

        Args:
            token: JWT token to verify

        Returns:
            TokenPayload if valid refresh token, None otherwise
        """
        payload = self.verify_token(token)
        if payload and payload.type == "refresh":
            return payload
        return None

    def refresh_tokens(
        self,
        refresh_token: str,
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> TokenPair | None:
        """Refresh tokens using a valid refresh token.

        Args:
            refresh_token: Valid refresh token
            roles: Updated roles (if changed)
            permissions: Updated permissions (if changed)

        Returns:
            New TokenPair if refresh successful, None otherwise
        """
        payload = self.verify_refresh_token(refresh_token)
        if not payload:
            return None

        return self.create_token_pair(
            subject=payload.sub,
            wallet_address=payload.wallet_address,
            roles=roles,
            permissions=permissions,
        )


# Singleton instance
_jwt_service: JWTService | None = None


def get_jwt_service() -> JWTService:
    """Get or create JWT service singleton."""
    global _jwt_service
    if _jwt_service is None:
        _jwt_service = JWTService()
    return _jwt_service
