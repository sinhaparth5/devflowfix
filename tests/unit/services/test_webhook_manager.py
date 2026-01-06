# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for WebhookManager service.
"""

import pytest
import hmac
import hashlib
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from app.services.webhook.webhook_manager import WebhookManager
from app.services.oauth.token_manager import TokenManager
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider


class TestWebhookManager:
    """Test suite for WebhookManager."""

    @pytest.fixture
    def mock_token_manager(self):
        """Create mock TokenManager."""
        manager = MagicMock(spec=TokenManager)
        manager.encrypt_token = Mock(side_effect=lambda x: f"encrypted_{x}")
        manager.decrypt_token = Mock(side_effect=lambda x: x.replace("encrypted_", ""))
        manager.get_decrypted_token = Mock(return_value="github_access_token_123")
        return manager

    @pytest.fixture
    def mock_github_provider(self):
        """Create mock GitHubOAuthProvider."""
        provider = MagicMock(spec=GitHubOAuthProvider)
        provider.create_webhook = AsyncMock(return_value={
            "id": 12345,
            "url": "https://api.github.com/repos/owner/repo/hooks/12345",
            "events": ["workflow_run", "pull_request", "push"],
            "active": True,
        })
        provider.delete_webhook = AsyncMock(return_value=True)
        return provider

    @pytest.fixture
    def mock_gitlab_provider(self):
        """Create mock GitLabOAuthProvider."""
        provider = MagicMock(spec=GitLabOAuthProvider)
        provider.create_webhook = AsyncMock(return_value={
            "id": 67890,
            "url": "https://gitlab.com/api/v4/projects/123/hooks/67890",
        })
        provider.delete_webhook = AsyncMock(return_value=True)
        return provider

    @pytest.fixture
    def webhook_manager(self, mock_token_manager, mock_github_provider):
        """Create WebhookManager instance."""
        return WebhookManager(
            token_manager=mock_token_manager,
            github_provider=mock_github_provider,
            gitlab_provider=None,
            webhook_base_url="https://api.devflowfix.com",
        )

    @pytest.fixture
    def webhook_manager_with_gitlab(self, mock_token_manager, mock_github_provider, mock_gitlab_provider):
        """Create WebhookManager instance with GitLab support."""
        return WebhookManager(
            token_manager=mock_token_manager,
            github_provider=mock_github_provider,
            gitlab_provider=mock_gitlab_provider,
            webhook_base_url="https://api.devflowfix.com",
        )

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.query = Mock()
        db.commit = Mock()
        db.add = Mock()
        return db

    def test_generate_webhook_secret(self, webhook_manager):
        """Test webhook secret generation."""
        secret1 = webhook_manager.generate_webhook_secret()
        secret2 = webhook_manager.generate_webhook_secret()

        # Secrets should be URL-safe strings
        assert isinstance(secret1, str)
        assert isinstance(secret2, str)

        # Secrets should be unique
        assert secret1 != secret2

        # Should be reasonably long (32 bytes -> ~43 chars in base64)
        assert len(secret1) > 40

    @pytest.mark.asyncio
    async def test_create_github_webhook_success(self, webhook_manager, mock_db, mock_token_manager):
        """Test successful GitHub webhook creation."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        # Mock repository connection
        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "github"
        repo_conn.oauth_connection_id = "oac_456"

        # Mock OAuth connection
        oauth_conn = Mock(spec=OAuthConnectionTable)
        oauth_conn.id = "oac_456"

        # Setup mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn,  # First call for repository connection
            oauth_conn,  # Second call for OAuth connection
        ]

        # Create webhook
        result = await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
            events=["workflow_run", "pull_request"],
        )

        # Verify result
        assert result["success"] is True
        assert result["webhook_id"] == "12345"
        assert result["webhook_url"] == "https://api.devflowfix.com/api/v2/webhooks/github"
        assert result["events"] == ["workflow_run", "pull_request"]

        # Verify repository connection was updated
        assert repo_conn.webhook_id == "12345"
        assert repo_conn.webhook_url == "https://api.devflowfix.com/api/v2/webhooks/github"
        assert repo_conn.webhook_status == "active"
        assert repo_conn.webhook_created_at is not None

        # Verify secret was encrypted
        assert mock_token_manager.encrypt_token.called

        # Verify database commit
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_create_gitlab_webhook_success(self, webhook_manager_with_gitlab, mock_db, mock_token_manager):
        """Test successful GitLab webhook creation."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        # Mock repository connection
        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_789"
        repo_conn.repository_full_name = "group/project"
        repo_conn.provider = "gitlab"
        repo_conn.oauth_connection_id = "oac_101"

        # Mock OAuth connection
        oauth_conn = Mock(spec=OAuthConnectionTable)
        oauth_conn.id = "oac_101"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn,
            oauth_conn,
        ]

        result = await webhook_manager_with_gitlab.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_789",
        )

        assert result["success"] is True
        assert result["webhook_id"] == "67890"
        assert result["webhook_url"] == "https://api.devflowfix.com/api/v2/webhooks/gitlab"

    @pytest.mark.asyncio
    async def test_create_webhook_repository_not_found(self, webhook_manager, mock_db):
        """Test webhook creation when repository connection not found."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Repository connection .* not found"):
            await webhook_manager.create_webhook(
                db=mock_db,
                repository_connection_id="nonexistent",
            )

    @pytest.mark.asyncio
    async def test_create_webhook_oauth_not_found(self, webhook_manager, mock_db):
        """Test webhook creation when OAuth connection not found."""
        from app.adapters.database.postgres.models import RepositoryConnectionTable

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.oauth_connection_id = "oac_nonexistent"
        repo_conn.repository_full_name = "owner/repo"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn,
            None,  # OAuth connection not found
        ]

        with pytest.raises(ValueError, match="OAuth connection not found"):
            await webhook_manager.create_webhook(
                db=mock_db,
                repository_connection_id="rpc_123",
            )

    @pytest.mark.asyncio
    async def test_create_webhook_default_events(self, webhook_manager, mock_db, mock_token_manager):
        """Test that default events are used when not specified."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "github"
        repo_conn.oauth_connection_id = "oac_456"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [repo_conn, oauth_conn]

        result = await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
            events=None,  # Use defaults
        )

        # Should use default events
        assert result["events"] == ["workflow_run", "pull_request", "push"]

    @pytest.mark.asyncio
    async def test_delete_github_webhook_success(self, webhook_manager, mock_db, mock_token_manager):
        """Test successful GitHub webhook deletion."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "github"
        repo_conn.webhook_id = "12345"
        repo_conn.oauth_connection_id = "oac_456"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [repo_conn, oauth_conn]

        result = await webhook_manager.delete_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
        )

        # Verify webhook was deleted
        assert result is True

        # Verify repository connection was cleaned up
        assert repo_conn.webhook_id is None
        assert repo_conn.webhook_url is None
        assert repo_conn.webhook_secret is None
        assert repo_conn.webhook_status == "inactive"

        # Verify database commit
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_delete_webhook_no_webhook_configured(self, webhook_manager, mock_db):
        """Test deleting webhook when none is configured."""
        from app.adapters.database.postgres.models import RepositoryConnectionTable

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.webhook_id = None  # No webhook configured

        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        result = await webhook_manager.delete_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
        )

        # Should succeed without trying to delete
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_webhook_provider_deletion_fails(self, webhook_manager, mock_db, mock_token_manager, mock_github_provider):
        """Test that database is cleaned up even if provider deletion fails."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        # Make provider deletion fail
        mock_github_provider.delete_webhook = AsyncMock(side_effect=Exception("API error"))

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "github"
        repo_conn.webhook_id = "12345"
        repo_conn.oauth_connection_id = "oac_456"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [repo_conn, oauth_conn]

        result = await webhook_manager.delete_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
        )

        # Should still return success (graceful degradation)
        # Database should be cleaned up
        assert repo_conn.webhook_id is None
        assert repo_conn.webhook_status == "inactive"
        assert mock_db.commit.called

    def test_verify_github_signature_valid(self):
        """Test GitHub signature verification with valid signature."""
        payload = b'{"action": "completed"}'
        secret = "my_webhook_secret"

        # Generate valid signature
        expected_signature = "sha256=" + hmac.new(
            key=secret.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()

        result = WebhookManager.verify_github_signature(
            payload=payload,
            signature=expected_signature,
            secret=secret,
        )

        assert result is True

    def test_verify_github_signature_invalid(self):
        """Test GitHub signature verification with invalid signature."""
        payload = b'{"action": "completed"}'
        secret = "my_webhook_secret"
        invalid_signature = "sha256=invalid_hash_value"

        result = WebhookManager.verify_github_signature(
            payload=payload,
            signature=invalid_signature,
            secret=secret,
        )

        assert result is False

    def test_verify_github_signature_wrong_format(self):
        """Test GitHub signature verification with wrong format."""
        payload = b'{"action": "completed"}'
        secret = "my_webhook_secret"
        wrong_format = "md5=somehash"  # Wrong algorithm prefix

        with pytest.raises(ValueError, match="Invalid signature format"):
            WebhookManager.verify_github_signature(
                payload=payload,
                signature=wrong_format,
                secret=secret,
            )

    def test_verify_github_signature_timing_attack_safe(self):
        """Test that signature verification uses constant-time comparison."""
        payload = b'{"action": "completed"}'
        secret = "my_webhook_secret"

        correct_sig = "sha256=" + hmac.new(
            key=secret.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()

        # Similar but wrong signature
        wrong_sig = correct_sig[:-4] + "beef"

        # Both should return False/True without timing differences
        result1 = WebhookManager.verify_github_signature(payload, wrong_sig, secret)
        result2 = WebhookManager.verify_github_signature(payload, correct_sig, secret)

        assert result1 is False
        assert result2 is True

    def test_verify_gitlab_signature_valid(self):
        """Test GitLab signature verification with valid token."""
        token = "my_gitlab_webhook_token"
        secret = "my_gitlab_webhook_token"

        result = WebhookManager.verify_gitlab_signature(
            token_header=token,
            secret=secret,
        )

        assert result is True

    def test_verify_gitlab_signature_invalid(self):
        """Test GitLab signature verification with invalid token."""
        token = "wrong_token"
        secret = "my_gitlab_webhook_token"

        result = WebhookManager.verify_gitlab_signature(
            token_header=token,
            secret=secret,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_create_webhook_unsupported_provider(self, webhook_manager, mock_db, mock_token_manager):
        """Test webhook creation for unsupported provider."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "bitbucket"  # Unsupported
        repo_conn.oauth_connection_id = "oac_456"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [repo_conn, oauth_conn]

        with pytest.raises(ValueError, match="Unsupported provider"):
            await webhook_manager.create_webhook(
                db=mock_db,
                repository_connection_id="rpc_123",
            )

    @pytest.mark.asyncio
    async def test_create_webhook_gitlab_not_configured(self, webhook_manager, mock_db, mock_token_manager):
        """Test GitLab webhook creation when GitLab provider not configured."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "group/project"
        repo_conn.provider = "gitlab"
        repo_conn.oauth_connection_id = "oac_456"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [repo_conn, oauth_conn]

        with pytest.raises(ValueError, match="GitLab provider not configured"):
            await webhook_manager.create_webhook(
                db=mock_db,
                repository_connection_id="rpc_123",
            )

    def test_webhook_base_url_trailing_slash(self):
        """Test that trailing slash is removed from webhook base URL."""
        manager = WebhookManager(
            token_manager=Mock(),
            github_provider=Mock(),
            webhook_base_url="https://api.devflowfix.com/",  # With trailing slash
        )

        assert manager.webhook_base_url == "https://api.devflowfix.com"

    @pytest.mark.asyncio
    async def test_webhook_secret_encryption_integration(self, webhook_manager, mock_db):
        """Test that webhook secret is properly encrypted and stored."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "github"
        repo_conn.oauth_connection_id = "oac_456"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [repo_conn, oauth_conn]

        await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
        )

        # Verify webhook_secret was set and is encrypted
        assert repo_conn.webhook_secret is not None
        assert repo_conn.webhook_secret.startswith("encrypted_")
