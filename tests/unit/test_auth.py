"""Tests for authentication services."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException
from web3 import Web3

from app.services.auth.jwt_service import JWTService, TokenPayload, TokenPair
from app.services.auth.wallet_auth import (
    NonceData,
    SignatureVerificationResult,
    WalletAuthService,
)
from app.services.auth.dependencies import (
    AuthenticatedUser,
    require_roles,
    require_permissions,
)


class TestJWTService:
    """Tests for JWT service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.jwt_service = JWTService(
            secret_key="test-secret-key-for-testing-only",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
        )

    def test_create_access_token(self):
        """Test creating access token."""
        token = self.jwt_service.create_access_token(
            subject="0x1234567890123456789012345678901234567890",
            wallet_address="0x1234567890123456789012345678901234567890",
            roles=["user"],
            permissions=["read:portfolio"],
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """Test creating refresh token."""
        token = self.jwt_service.create_refresh_token(
            subject="0x1234567890123456789012345678901234567890",
            wallet_address="0x1234567890123456789012345678901234567890",
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_pair(self):
        """Test creating token pair."""
        pair = self.jwt_service.create_token_pair(
            subject="0x1234567890123456789012345678901234567890",
            wallet_address="0x1234567890123456789012345678901234567890",
            roles=["user", "admin"],
            permissions=["read:all", "write:all"],
        )

        assert isinstance(pair, TokenPair)
        assert pair.access_token
        assert pair.refresh_token
        assert pair.token_type == "Bearer"
        assert pair.expires_in == 30 * 60  # 30 minutes in seconds

    def test_verify_access_token(self):
        """Test verifying access token."""
        token = self.jwt_service.create_access_token(
            subject="test-user",
            wallet_address="0x1234567890123456789012345678901234567890",
            roles=["user"],
            permissions=["read:portfolio"],
        )

        payload = self.jwt_service.verify_access_token(token)

        assert payload is not None
        assert payload.sub == "test-user"
        assert payload.type == "access"
        assert payload.wallet_address == "0x1234567890123456789012345678901234567890"
        assert "user" in payload.roles
        assert "read:portfolio" in payload.permissions

    def test_verify_refresh_token(self):
        """Test verifying refresh token."""
        token = self.jwt_service.create_refresh_token(
            subject="test-user",
            wallet_address="0x1234567890123456789012345678901234567890",
        )

        payload = self.jwt_service.verify_refresh_token(token)

        assert payload is not None
        assert payload.sub == "test-user"
        assert payload.type == "refresh"

    def test_verify_access_token_rejects_refresh_token(self):
        """Test that verify_access_token rejects refresh tokens."""
        refresh_token = self.jwt_service.create_refresh_token(
            subject="test-user",
        )

        payload = self.jwt_service.verify_access_token(refresh_token)

        assert payload is None

    def test_verify_refresh_token_rejects_access_token(self):
        """Test that verify_refresh_token rejects access tokens."""
        access_token = self.jwt_service.create_access_token(
            subject="test-user",
        )

        payload = self.jwt_service.verify_refresh_token(access_token)

        assert payload is None

    def test_verify_invalid_token(self):
        """Test verifying invalid token returns None."""
        payload = self.jwt_service.verify_token("invalid-token")

        assert payload is None

    def test_verify_tampered_token(self):
        """Test verifying tampered token returns None."""
        token = self.jwt_service.create_access_token(subject="test-user")
        tampered_token = token + "tampered"

        payload = self.jwt_service.verify_token(tampered_token)

        assert payload is None

    def test_refresh_tokens(self):
        """Test refreshing tokens."""
        original_pair = self.jwt_service.create_token_pair(
            subject="test-user",
            wallet_address="0x1234567890123456789012345678901234567890",
        )

        new_pair = self.jwt_service.refresh_tokens(
            refresh_token=original_pair.refresh_token,
            roles=["user", "premium"],
            permissions=["read:all"],
        )

        assert new_pair is not None
        # Access token should be different due to different roles/permissions
        assert new_pair.access_token != original_pair.access_token
        # Note: Refresh token may be same if generated in same second
        # (same iat/exp timestamp). This is expected behavior.

    def test_refresh_tokens_with_invalid_token(self):
        """Test refreshing with invalid token returns None."""
        result = self.jwt_service.refresh_tokens(
            refresh_token="invalid-refresh-token",
        )

        assert result is None

    def test_token_expiration(self):
        """Test that tokens contain correct expiration time."""
        token = self.jwt_service.create_access_token(subject="test-user")
        payload = self.jwt_service.verify_access_token(token)

        assert payload is not None
        # Expiration should be approximately 30 minutes from now
        expected_exp = datetime.now(timezone.utc) + timedelta(minutes=30)
        assert abs((payload.exp - expected_exp).total_seconds()) < 5


class TestWalletAuthService:
    """Tests for wallet authentication service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.wallet_auth = WalletAuthService(nonce_expire_seconds=300)
        # Clear nonces between tests
        WalletAuthService._nonces = {}
        # Generate a test account
        self.test_account = Account.create()
        self.test_address = self.test_account.address
        self.w3 = Web3()

    def test_generate_nonce(self):
        """Test generating authentication nonce."""
        nonce_data = self.wallet_auth.generate_nonce(self.test_address)

        assert isinstance(nonce_data, NonceData)
        assert len(nonce_data.nonce) == 64  # 32 bytes hex
        assert nonce_data.message
        assert nonce_data.expires_at > time.time()
        assert nonce_data.wallet_address.lower() == self.test_address.lower()

    def test_verify_valid_signature(self):
        """Test verifying valid wallet signature."""
        # Generate nonce
        nonce_data = self.wallet_auth.generate_nonce(self.test_address)

        # Sign the message
        message = encode_defunct(text=nonce_data.message)
        signed = self.w3.eth.account.sign_message(message, self.test_account.key)

        # Verify signature
        result = self.wallet_auth.verify_signature(
            wallet_address=self.test_address,
            signature=signed.signature.hex(),
            nonce=nonce_data.nonce,
        )

        assert result.valid is True
        assert result.wallet_address.lower() == self.test_address.lower()
        assert result.error is None

    def test_verify_invalid_nonce(self):
        """Test verification with invalid nonce."""
        result = self.wallet_auth.verify_signature(
            wallet_address=self.test_address,
            signature="0x" + "00" * 65,
            nonce="invalid-nonce",
        )

        assert result.valid is False
        assert "Invalid or expired nonce" in result.error

    def test_verify_wrong_signature(self):
        """Test verification with wrong signature (different wallet)."""
        # Generate nonce
        nonce_data = self.wallet_auth.generate_nonce(self.test_address)

        # Sign with different account
        other_account = Account.create()
        message = encode_defunct(text=nonce_data.message)
        signed = self.w3.eth.account.sign_message(message, other_account.key)

        # Verify signature
        result = self.wallet_auth.verify_signature(
            wallet_address=self.test_address,
            signature=signed.signature.hex(),
            nonce=nonce_data.nonce,
        )

        assert result.valid is False
        assert "Signature does not match" in result.error

    def test_nonce_single_use(self):
        """Test that nonce can only be used once."""
        # Generate nonce
        nonce_data = self.wallet_auth.generate_nonce(self.test_address)

        # Sign the message
        message = encode_defunct(text=nonce_data.message)
        signed = self.w3.eth.account.sign_message(message, self.test_account.key)

        # First verification should succeed
        result1 = self.wallet_auth.verify_signature(
            wallet_address=self.test_address,
            signature=signed.signature.hex(),
            nonce=nonce_data.nonce,
        )
        assert result1.valid is True

        # Second verification should fail (nonce consumed)
        result2 = self.wallet_auth.verify_signature(
            wallet_address=self.test_address,
            signature=signed.signature.hex(),
            nonce=nonce_data.nonce,
        )
        assert result2.valid is False

    def test_expired_nonce(self):
        """Test verification with expired nonce."""
        # Create service with very short expiration
        short_auth = WalletAuthService(nonce_expire_seconds=0)
        WalletAuthService._nonces = {}  # Clear shared nonces

        # Generate nonce (will be immediately expired)
        nonce_data = short_auth.generate_nonce(self.test_address)

        # Wait a tiny bit to ensure expiration
        time.sleep(0.1)

        # Sign the message
        message = encode_defunct(text=nonce_data.message)
        signed = self.w3.eth.account.sign_message(message, self.test_account.key)

        # Verify should fail
        result = short_auth.verify_signature(
            wallet_address=self.test_address,
            signature=signed.signature.hex(),
            nonce=nonce_data.nonce,
        )

        assert result.valid is False
        assert "expired" in result.error.lower()

    def test_is_valid_address(self):
        """Test address validation."""
        assert self.wallet_auth.is_valid_address(self.test_address) is True
        assert self.wallet_auth.is_valid_address("0x" + "1" * 40) is True
        assert self.wallet_auth.is_valid_address("invalid") is False
        assert self.wallet_auth.is_valid_address("0x123") is False

    def test_normalize_address(self):
        """Test address normalization to checksum format."""
        lowercase_address = self.test_address.lower()
        normalized = self.wallet_auth._normalize_address(lowercase_address)

        assert normalized == self.test_address
        assert normalized[0:2] == "0x"


class TestAuthenticatedUser:
    """Tests for AuthenticatedUser class."""

    def test_authenticated_user_creation(self):
        """Test creating authenticated user."""
        user = AuthenticatedUser(
            user_id="test-user",
            wallet_address="0x1234567890123456789012345678901234567890",
            roles=["user", "admin"],
            permissions=["read:all", "write:all"],
        )

        assert user.user_id == "test-user"
        assert user.wallet_address == "0x1234567890123456789012345678901234567890"
        assert "user" in user.roles
        assert "admin" in user.roles

    def test_has_role(self):
        """Test role checking."""
        user = AuthenticatedUser(
            user_id="test-user",
            roles=["user", "admin"],
        )

        assert user.has_role("user") is True
        assert user.has_role("admin") is True
        assert user.has_role("superadmin") is False

    def test_has_permission(self):
        """Test permission checking."""
        user = AuthenticatedUser(
            user_id="test-user",
            permissions=["read:portfolio", "create:redemption"],
        )

        assert user.has_permission("read:portfolio") is True
        assert user.has_permission("create:redemption") is True
        assert user.has_permission("delete:all") is False

    def test_has_any_role(self):
        """Test any role checking."""
        user = AuthenticatedUser(
            user_id="test-user",
            roles=["user"],
        )

        assert user.has_any_role(["user", "admin"]) is True
        assert user.has_any_role(["admin", "superadmin"]) is False

    def test_has_all_roles(self):
        """Test all roles checking."""
        user = AuthenticatedUser(
            user_id="test-user",
            roles=["user", "admin"],
        )

        assert user.has_all_roles(["user"]) is True
        assert user.has_all_roles(["user", "admin"]) is True
        assert user.has_all_roles(["user", "superadmin"]) is False

    def test_is_admin(self):
        """Test admin check."""
        admin_user = AuthenticatedUser(user_id="admin", roles=["admin"])
        regular_user = AuthenticatedUser(user_id="user", roles=["user"])

        assert admin_user.is_admin is True
        assert regular_user.is_admin is False


class TestAuthDependencies:
    """Tests for authentication dependencies."""

    @pytest.mark.asyncio
    async def test_require_roles_passes(self):
        """Test require_roles allows users with correct role."""
        user = AuthenticatedUser(user_id="test", roles=["admin"])
        checker = require_roles("admin")

        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_require_roles_fails(self):
        """Test require_roles rejects users without required role."""
        user = AuthenticatedUser(user_id="test", roles=["user"])
        checker = require_roles("admin")

        with pytest.raises(HTTPException) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_roles_any_match(self):
        """Test require_roles passes if user has any of the roles."""
        user = AuthenticatedUser(user_id="test", roles=["moderator"])
        checker = require_roles("admin", "moderator")

        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_require_permissions_passes(self):
        """Test require_permissions allows users with correct permission."""
        user = AuthenticatedUser(
            user_id="test", permissions=["read:portfolio"]
        )
        checker = require_permissions("read:portfolio")

        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_require_permissions_fails(self):
        """Test require_permissions rejects users without required permission."""
        user = AuthenticatedUser(user_id="test", permissions=["read:portfolio"])
        checker = require_permissions("delete:all")

        with pytest.raises(HTTPException) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 403
