# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
OAuth Token Manager

Handles secure storage, encryption, and refresh of OAuth tokens.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import structlog

logger = structlog.get_logger(__name__)


class TokenManager:
    """
    Manages OAuth token encryption, decryption, and storage.

    Tokens are encrypted at rest using Fernet (symmetric encryption).
    """

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize token manager.

        Args:
            encryption_key: Base64-encoded Fernet key for encryption.
                           If None, encryption is disabled (not recommended for production).
        """
        self.encryption_enabled = encryption_key is not None

        if self.encryption_enabled:
            self.cipher_suite = Fernet(encryption_key.encode())
            logger.info("token_encryption_enabled")
        else:
            self.cipher_suite = None
            logger.warning(
                "token_encryption_disabled",
                message="OAuth tokens will be stored in plaintext! Set OAUTH_TOKEN_ENCRYPTION_KEY in production.",
            )

    def encrypt_token(self, token: str) -> str:
        """
        Encrypt an OAuth token for storage.

        Args:
            token: Plaintext OAuth token

        Returns:
            Encrypted token (or plaintext if encryption disabled)
        """
        if not self.encryption_enabled:
            return token

        try:
            encrypted = self.cipher_suite.encrypt(token.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(
                "token_encryption_failed",
                error=str(e),
            )
            raise

    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt an OAuth token for use.

        Args:
            encrypted_token: Encrypted token from storage

        Returns:
            Plaintext OAuth token

        Raises:
            Exception: If decryption fails
        """
        if not self.encryption_enabled:
            return encrypted_token

        try:
            decrypted = self.cipher_suite.decrypt(encrypted_token.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(
                "token_decryption_failed",
                error=str(e),
            )
            raise

    async def store_oauth_connection(
        self,
        db,
        user_id: str,
        provider: str,
        provider_user_id: str,
        provider_username: str,
        access_token: str,
        refresh_token: Optional[str],
        scopes: list[str],
        expires_at: Optional[datetime] = None,
    ) -> Any:
        """
        Store OAuth connection in database.

        Args:
            db: Database session
            user_id: DevFlowFix user ID
            provider: OAuth provider name (github, gitlab)
            provider_user_id: User ID from provider
            provider_username: Username from provider
            access_token: Access token to encrypt and store
            refresh_token: Refresh token (if supported by provider)
            scopes: List of granted permission scopes
            expires_at: Token expiration time (if applicable)

        Returns:
            OAuthConnectionTable record
        """
        from app.adapters.database.postgres.models import OAuthConnectionTable
        from uuid import uuid4

        # Encrypt tokens
        encrypted_access_token = self.encrypt_token(access_token)
        encrypted_refresh_token = (
            self.encrypt_token(refresh_token) if refresh_token else None
        )

        # Check if connection already exists
        existing = (
            db.query(OAuthConnectionTable)
            .filter(
                OAuthConnectionTable.user_id == user_id,
                OAuthConnectionTable.provider == provider,
            )
            .first()
        )

        if existing:
            # Update existing connection
            existing.provider_user_id = provider_user_id
            existing.provider_username = provider_username
            existing.access_token = encrypted_access_token
            existing.refresh_token = encrypted_refresh_token
            existing.scopes = scopes
            existing.token_expires_at = expires_at
            existing.is_active = True
            existing.updated_at = datetime.now(timezone.utc)

            logger.info(
                "oauth_connection_updated",
                user_id=user_id,
                provider=provider,
            )

            return existing
        else:
            # Create new connection
            connection = OAuthConnectionTable(
                id=f"oac_{uuid4().hex}",
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_username=provider_username,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                scopes=scopes,
                token_expires_at=expires_at,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(connection)

            logger.info(
                "oauth_connection_created",
                user_id=user_id,
                provider=provider,
                connection_id=connection.id,
            )

            return connection

    async def get_oauth_connection(
        self, db, user_id: str, provider: str
    ) -> Optional[Any]:
        """
        Get OAuth connection for user and provider.

        Args:
            db: Database session
            user_id: DevFlowFix user ID
            provider: OAuth provider name

        Returns:
            OAuthConnectionTable record or None
        """
        from app.adapters.database.postgres.models import OAuthConnectionTable

        connection = (
            db.query(OAuthConnectionTable)
            .filter(
                OAuthConnectionTable.user_id == user_id,
                OAuthConnectionTable.provider == provider,
                OAuthConnectionTable.is_active == True,
            )
            .first()
        )

        if connection:
            # Update last_used_at
            connection.last_used_at = datetime.now(timezone.utc)
            db.commit()

        return connection

    def get_decrypted_token(self, oauth_connection: Any) -> str:
        """
        Get decrypted access token from OAuth connection.

        Args:
            oauth_connection: OAuthConnectionTable record

        Returns:
            Decrypted access token
        """
        return self.decrypt_token(oauth_connection.access_token)

    async def revoke_oauth_connection(
        self, db, connection_id: str, user_id: str
    ) -> bool:
        """
        Revoke/deactivate OAuth connection.

        Args:
            db: Database session
            connection_id: OAuth connection ID
            user_id: User ID (for security check)

        Returns:
            True if successful
        """
        from app.adapters.database.postgres.models import OAuthConnectionTable

        connection = (
            db.query(OAuthConnectionTable)
            .filter(
                OAuthConnectionTable.id == connection_id,
                OAuthConnectionTable.user_id == user_id,
            )
            .first()
        )

        if not connection:
            logger.warning(
                "oauth_connection_not_found",
                connection_id=connection_id,
                user_id=user_id,
            )
            return False

        connection.is_active = False
        connection.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "oauth_connection_revoked",
            connection_id=connection_id,
            user_id=user_id,
            provider=connection.provider,
        )

        return True


# Global token manager instance
_token_manager: Optional[TokenManager] = None


def get_token_manager(encryption_key: Optional[str] = None) -> TokenManager:
    """
    Get global token manager instance.

    Args:
        encryption_key: Encryption key (only used on first call)

    Returns:
        TokenManager instance
    """
    global _token_manager

    if _token_manager is None:
        _token_manager = TokenManager(encryption_key)

    return _token_manager
