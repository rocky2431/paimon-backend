"""Wallet signature authentication service."""

import hashlib
import logging
import secrets
import time
from typing import Any

from eth_account.messages import encode_defunct
from pydantic import BaseModel
from web3 import Web3

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class NonceData(BaseModel):
    """Nonce data for wallet authentication."""

    nonce: str
    message: str
    expires_at: int
    wallet_address: str


class SignatureVerificationResult(BaseModel):
    """Result of signature verification."""

    valid: bool
    wallet_address: str | None = None
    error: str | None = None


class WalletAuthService:
    """Service for wallet-based authentication using signatures."""

    # In-memory nonce storage (should use Redis in production)
    _nonces: dict[str, NonceData] = {}

    def __init__(
        self,
        nonce_expire_seconds: int = 300,  # 5 minutes
        message_template: str | None = None,
    ):
        """Initialize wallet auth service.

        Args:
            nonce_expire_seconds: How long nonces are valid
            message_template: Template for sign message
        """
        settings = get_settings()
        self.nonce_expire_seconds = nonce_expire_seconds
        self.message_template = message_template or (
            f"Sign this message to authenticate with {settings.app_name}.\n\n"
            "Nonce: {nonce}\n"
            "Timestamp: {timestamp}\n\n"
            "This signature will not trigger any blockchain transaction."
        )
        self.w3 = Web3()

    def generate_nonce(self, wallet_address: str) -> NonceData:
        """Generate a nonce for wallet authentication.

        Args:
            wallet_address: Wallet address requesting authentication

        Returns:
            NonceData with nonce and message to sign
        """
        # Normalize address
        wallet_address = self._normalize_address(wallet_address)

        # Generate cryptographically secure nonce
        nonce = secrets.token_hex(32)
        timestamp = int(time.time())
        expires_at = timestamp + self.nonce_expire_seconds

        # Create message to sign
        message = self.message_template.format(
            nonce=nonce,
            timestamp=timestamp,
        )

        nonce_data = NonceData(
            nonce=nonce,
            message=message,
            expires_at=expires_at,
            wallet_address=wallet_address,
        )

        # Store nonce (keyed by wallet + nonce to prevent reuse)
        storage_key = self._get_storage_key(wallet_address, nonce)
        self._nonces[storage_key] = nonce_data

        # Cleanup expired nonces
        self._cleanup_expired_nonces()

        return nonce_data

    def verify_signature(
        self,
        wallet_address: str,
        signature: str,
        nonce: str,
    ) -> SignatureVerificationResult:
        """Verify a wallet signature.

        Args:
            wallet_address: Expected wallet address
            signature: Signature from wallet
            nonce: Nonce that was signed

        Returns:
            SignatureVerificationResult indicating success or failure
        """
        wallet_address = self._normalize_address(wallet_address)
        storage_key = self._get_storage_key(wallet_address, nonce)

        # Check if nonce exists
        nonce_data = self._nonces.get(storage_key)
        if not nonce_data:
            return SignatureVerificationResult(
                valid=False,
                error="Invalid or expired nonce",
            )

        # Check if nonce is expired
        if time.time() > nonce_data.expires_at:
            del self._nonces[storage_key]
            return SignatureVerificationResult(
                valid=False,
                error="Nonce has expired",
            )

        # Verify signature
        try:
            recovered_address = self._recover_address(
                message=nonce_data.message,
                signature=signature,
            )

            if recovered_address.lower() != wallet_address.lower():
                return SignatureVerificationResult(
                    valid=False,
                    error="Signature does not match wallet address",
                )

            # Remove used nonce (one-time use)
            del self._nonces[storage_key]

            return SignatureVerificationResult(
                valid=True,
                wallet_address=wallet_address,
            )

        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return SignatureVerificationResult(
                valid=False,
                error=f"Signature verification failed: {str(e)}",
            )

    def _recover_address(self, message: str, signature: str) -> str:
        """Recover wallet address from signed message.

        Args:
            message: Original message that was signed
            signature: Signature from wallet

        Returns:
            Recovered wallet address
        """
        # Encode message for personal_sign (EIP-191)
        message_encoded = encode_defunct(text=message)

        # Recover address
        recovered = self.w3.eth.account.recover_message(
            message_encoded,
            signature=signature,
        )

        return recovered

    def _normalize_address(self, address: str) -> str:
        """Normalize wallet address to checksum format.

        Args:
            address: Wallet address

        Returns:
            Checksummed address
        """
        return self.w3.to_checksum_address(address)

    def _get_storage_key(self, wallet_address: str, nonce: str) -> str:
        """Generate storage key for nonce.

        Args:
            wallet_address: Wallet address
            nonce: Nonce value

        Returns:
            Storage key
        """
        return hashlib.sha256(f"{wallet_address}:{nonce}".encode()).hexdigest()

    def _cleanup_expired_nonces(self) -> None:
        """Remove expired nonces from storage."""
        current_time = time.time()
        expired_keys = [
            key
            for key, data in self._nonces.items()
            if current_time > data.expires_at
        ]
        for key in expired_keys:
            del self._nonces[key]

    def is_valid_address(self, address: str) -> bool:
        """Check if address is valid Ethereum address.

        Args:
            address: Address to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            self.w3.to_checksum_address(address)
            return True
        except ValueError:
            return False


# Singleton instance
_wallet_auth_service: WalletAuthService | None = None


def get_wallet_auth_service() -> WalletAuthService:
    """Get or create wallet auth service singleton."""
    global _wallet_auth_service
    if _wallet_auth_service is None:
        _wallet_auth_service = WalletAuthService()
    return _wallet_auth_service
