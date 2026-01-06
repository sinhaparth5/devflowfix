# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for OAuth Token Manager.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet

from app.services.oauth.token_manager import TokenManager, get_token_manager


class TestTokenManager:
    """Test suite for TokenManager."""

    @pytest.fixture
    def encryption_key(self):
        """Generate a valid Fernet encryption key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def token_manager(self, encryption_key):
        """Create TokenManager instance with encryption."""
        return TokenManager(encryption_key=encryption_key)

    @pytest.fixture
    def token_manager_no_encryption(self):
        """Create TokenManager instance without encryption."""
        return TokenManager(encryption_key=None)

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.add = Mock()
        db.commit = Mock()
        db.query = Mock()
        return db

    def test_initialization_with_encryption(self, token_manager):
        """Test token manager initializes correctly with encryption."""
        assert token_manager.encryption_enabled is True
        assert token_manager.cipher_suite is not None

    def test_initialization_without_encryption(self, token_manager_no_encryption):
        """Test token manager initializes correctly without encryption."""
        assert token_manager_no_encryption.encryption_enabled is False
        assert token_manager_no_encryption.cipher_suite is None

    def test_encrypt_token_with_encryption(self, token_manager):
        """Test token encryption when encryption is enabled."""
        plaintext = "my_access_token_123"
        encrypted = token_manager.encrypt_token(plaintext)

        # Encrypted token should be different from plaintext
        assert encrypted != plaintext
        # Should be a string
        assert isinstance(encrypted, str)

    def test_encrypt_token_without_encryption(self, token_manager_no_encryption):
        """Test token encryption when encryption is disabled."""
        plaintext = "my_access_token_123"
        encrypted = token_manager_no_encryption.encrypt_token(plaintext)

        # Should return plaintext when encryption disabled
        assert encrypted == plaintext

    def test_decrypt_token_with_encryption(self, token_manager):
        """Test token decryption when encryption is enabled."""
        plaintext = "my_access_token_123"
        encrypted = token_manager.encrypt_token(plaintext)
        decrypted = token_manager.decrypt_token(encrypted)

        # Decrypted should match original plaintext
        assert decrypted == plaintext

    def test_decrypt_token_without_encryption(self, token_manager_no_encryption):
        """Test token decryption when encryption is disabled."""
        token = "my_access_token_123"
        decrypted = token_manager_no_encryption.decrypt_token(token)

        # Should return token as-is when encryption disabled
        assert decrypted == token

    def test_encrypt_decrypt_roundtrip(self, token_manager):
        """Test that encrypt->decrypt returns original value."""
        original_tokens = [
            "access_token_abc123",
            "another_token_xyz789",
            "special-chars!@#$%",
            "very_long_token" * 100,
        ]

        for original in original_tokens:
            encrypted = token_manager.encrypt_token(original)
            decrypted = token_manager.decrypt_token(encrypted)
            assert decrypted == original

    def test_decrypt_invalid_token_fails(self, token_manager):
        """Test that decrypting invalid token raises exception."""
        invalid_encrypted = "not_a_valid_encrypted_token"

        with pytest.raises(Exception):
            token_manager.decrypt_token(invalid_encrypted)

    @pytest.mark.asyncio
    async def test_store_oauth_connection_new(self, token_manager, mock_db):
        """Test storing a new OAuth connection."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        # Mock database query to return None (no existing connection)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        connection = await token_manager.store_oauth_connection(
            db=mock_db,
            user_id="user123",
            provider="github",
            provider_user_id="gh_user_456",
            provider_username="testuser",
            access_token="github_token_789",
            refresh_token=None,
            scopes=["repo", "read:user"],
            expires_at=None,
        )

        # Verify connection was added to database
        assert mock_db.add.called
        call_args = mock_db.add.call_args_list[0][0][0]
        assert isinstance(call_args, OAuthConnectionTable)
        assert call_args.user_id == "user123"
        assert call_args.provider == "github"
        assert call_args.provider_username == "testuser"

    @pytest.mark.asyncio
    async def test_store_oauth_connection_update_existing(self, token_manager, mock_db):
        """Test updating an existing OAuth connection."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        # Mock existing connection
        existing_connection = Mock(spec=OAuthConnectionTable)
        existing_connection.id = "oac_123"
        existing_connection.user_id = "user123"
        existing_connection.provider = "github"

        # Mock database query to return existing connection
        mock_db.query.return_value.filter.return_value.first.return_value = existing_connection

        connection = await token_manager.store_oauth_connection(
            db=mock_db,
            user_id="user123",
            provider="github",
            provider_user_id="gh_user_456",
            provider_username="updated_username",
            access_token="new_token_789",
            refresh_token="refresh_123",
            scopes=["repo"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # Verify existing connection was updated
        assert connection.provider_username == "updated_username"
        assert connection.is_active is True
        # Should not add new connection
        assert not mock_db.add.called

    @pytest.mark.asyncio
    async def test_store_oauth_connection_encrypts_tokens(self, token_manager, mock_db):
        """Test that tokens are encrypted before storage."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        mock_db.query.return_value.filter.return_value.first.return_value = None

        access_token = "plaintext_access_token"
        refresh_token = "plaintext_refresh_token"

        await token_manager.store_oauth_connection(
            db=mock_db,
            user_id="user123",
            provider="gitlab",
            provider_user_id="gl_user_789",
            provider_username="gitlabuser",
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=["api"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )

        # Get the connection object that was added
        call_args = mock_db.add.call_args_list[0][0][0]

        # Tokens in database should be encrypted (different from plaintext)
        assert call_args.access_token != access_token
        assert call_args.refresh_token != refresh_token

    @pytest.mark.asyncio
    async def test_get_oauth_connection_exists(self, token_manager, mock_db):
        """Test getting an existing OAuth connection."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        # Mock existing connection
        mock_connection = Mock(spec=OAuthConnectionTable)
        mock_connection.id = "oac_123"
        mock_connection.user_id = "user123"
        mock_connection.provider = "github"
        mock_connection.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_connection

        connection = await token_manager.get_oauth_connection(
            db=mock_db,
            user_id="user123",
            provider="github",
        )

        assert connection is not None
        assert connection.id == "oac_123"
        assert connection.provider == "github"
        # Should update last_used_at
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_oauth_connection_not_found(self, token_manager, mock_db):
        """Test getting a non-existent OAuth connection."""
        # Mock database query to return None
        mock_db.query.return_value.filter.return_value.first.return_value = None

        connection = await token_manager.get_oauth_connection(
            db=mock_db,
            user_id="user123",
            provider="nonexistent",
        )

        assert connection is None

    def test_get_decrypted_token(self, token_manager):
        """Test getting decrypted token from OAuth connection."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        # Create mock connection with encrypted token
        plaintext_token = "my_access_token"
        encrypted_token = token_manager.encrypt_token(plaintext_token)

        mock_connection = Mock(spec=OAuthConnectionTable)
        mock_connection.access_token = encrypted_token

        # Get decrypted token
        decrypted = token_manager.get_decrypted_token(mock_connection)

        assert decrypted == plaintext_token

    @pytest.mark.asyncio
    async def test_revoke_oauth_connection_success(self, token_manager, mock_db):
        """Test successful OAuth connection revocation."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        # Mock existing connection
        mock_connection = Mock(spec=OAuthConnectionTable)
        mock_connection.id = "oac_123"
        mock_connection.user_id = "user123"
        mock_connection.provider = "github"
        mock_connection.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_connection

        result = await token_manager.revoke_oauth_connection(
            db=mock_db,
            connection_id="oac_123",
            user_id="user123",
        )

        assert result is True
        assert mock_connection.is_active is False
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_revoke_oauth_connection_not_found(self, token_manager, mock_db):
        """Test revoking non-existent OAuth connection."""
        # Mock database query to return None
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await token_manager.revoke_oauth_connection(
            db=mock_db,
            connection_id="nonexistent_id",
            user_id="user123",
        )

        assert result is False
        assert not mock_db.commit.called

    def test_get_token_manager_singleton(self, encryption_key):
        """Test that get_token_manager returns singleton instance."""
        # Reset global instance
        import app.services.oauth.token_manager as tm_module
        tm_module._token_manager = None

        # First call creates instance
        manager1 = get_token_manager(encryption_key)
        assert manager1 is not None

        # Second call returns same instance
        manager2 = get_token_manager()
        assert manager1 is manager2

        # Reset for other tests
        tm_module._token_manager = None

    def test_encryption_with_different_keys(self):
        """Test that different encryption keys produce different results."""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        manager1 = TokenManager(key1)
        manager2 = TokenManager(key2)

        token = "same_token"

        encrypted1 = manager1.encrypt_token(token)
        encrypted2 = manager2.encrypt_token(token)

        # Different keys should produce different encrypted values
        assert encrypted1 != encrypted2

        # Each manager should decrypt its own encrypted token correctly
        assert manager1.decrypt_token(encrypted1) == token
        assert manager2.decrypt_token(encrypted2) == token

        # But trying to decrypt with wrong key should fail
        with pytest.raises(Exception):
            manager1.decrypt_token(encrypted2)

    def test_empty_token_encryption(self, token_manager):
        """Test encrypting empty or whitespace tokens."""
        empty_tokens = ["", " ", "   "]

        for token in empty_tokens:
            encrypted = token_manager.encrypt_token(token)
            decrypted = token_manager.decrypt_token(encrypted)
            assert decrypted == token
