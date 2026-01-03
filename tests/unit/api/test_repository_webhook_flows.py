# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for repository connect/disconnect flows with webhook management.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from app.services.repository.repository_manager import RepositoryManager
from app.services.webhook.webhook_manager import WebhookManager


class TestRepositoryWebhookFlows:
    """Test repository connection flows with automatic webhook management."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.query = Mock()
        db.commit = Mock()
        db.add = Mock()
        db.rollback = Mock()
        db.flush = Mock()
        return db

    @pytest.fixture
    def mock_github_provider(self):
        """Create mock GitHub provider."""
        provider = MagicMock()
        provider.get_user_repositories = AsyncMock(return_value=[])
        provider.get_repository = AsyncMock(return_value={
            "id": 123456,
            "name": "test-repo",
            "full_name": "owner/test-repo",
            "private": False,
        })
        provider.create_webhook = AsyncMock(return_value={
            "id": 789,
            "url": "https://api.github.com/repos/owner/test-repo/hooks/789",
        })
        provider.delete_webhook = AsyncMock(return_value=True)
        return provider

    @pytest.fixture
    def mock_token_manager(self):
        """Create mock token manager."""
        manager = MagicMock()
        manager.get_oauth_connection = AsyncMock(return_value=Mock(id="oac_123"))
        manager.get_decrypted_token = Mock(return_value="github_token_123")
        manager.encrypt_token = Mock(side_effect=lambda x: f"encrypted_{x}")
        manager.decrypt_token = Mock(side_effect=lambda x: x.replace("encrypted_", ""))
        return manager

    @pytest.fixture
    def repo_manager(self, mock_github_provider, mock_token_manager):
        """Create RepositoryManager instance."""
        return RepositoryManager(
            github_provider=mock_github_provider,
            token_manager=mock_token_manager,
        )

    @pytest.fixture
    def webhook_manager(self, mock_token_manager, mock_github_provider):
        """Create WebhookManager instance."""
        return WebhookManager(
            token_manager=mock_token_manager,
            github_provider=mock_github_provider,
            webhook_base_url="https://api.devflowfix.com",
        )

    @pytest.mark.asyncio
    async def test_connect_repository_with_webhook_creation(
        self,
        repo_manager,
        webhook_manager,
        mock_db,
        mock_github_provider,
    ):
        """Test repository connection with automatic webhook creation."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        # Mock OAuth connection
        oauth_conn = Mock(spec=OAuthConnectionTable)
        oauth_conn.id = "oac_123"

        # Setup mock queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No existing connection
            oauth_conn,  # OAuth connection for webhook
        ]

        # Connect repository (without webhook)
        connection = await repo_manager.connect_repository(
            db=mock_db,
            user_id="user_123",
            repository_full_name="owner/test-repo",
            setup_webhook=False,
        )

        # Verify connection was created
        assert connection is not None
        assert mock_db.add.called

        # Now create webhook using WebhookManager
        webhook_result = await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id=connection.id,
            events=["workflow_run", "pull_request"],
        )

        # Verify webhook was created
        assert webhook_result["success"] is True
        assert webhook_result["webhook_id"] == "789"

        # Verify GitHub API was called
        assert mock_github_provider.create_webhook.called

    @pytest.mark.asyncio
    async def test_connect_repository_webhook_creation_fails_gracefully(
        self,
        repo_manager,
        webhook_manager,
        mock_db,
        mock_github_provider,
    ):
        """Test that repository connection succeeds even if webhook creation fails."""
        from app.adapters.database.postgres.models import OAuthConnectionTable

        oauth_conn = Mock(spec=OAuthConnectionTable)
        oauth_conn.id = "oac_123"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No existing connection
            oauth_conn,  # OAuth connection
        ]

        # Make webhook creation fail
        mock_github_provider.create_webhook = AsyncMock(
            side_effect=Exception("GitHub API error")
        )

        # Connect repository should succeed
        connection = await repo_manager.connect_repository(
            db=mock_db,
            user_id="user_123",
            repository_full_name="owner/test-repo",
            setup_webhook=False,
        )

        assert connection is not None

        # Webhook creation should fail but not crash
        with pytest.raises(Exception):
            await webhook_manager.create_webhook(
                db=mock_db,
                repository_connection_id=connection.id,
            )

        # Repository connection should still exist
        assert connection.id is not None

    @pytest.mark.asyncio
    async def test_disconnect_repository_with_webhook_deletion(
        self,
        repo_manager,
        webhook_manager,
        mock_db,
        mock_github_provider,
    ):
        """Test repository disconnection with automatic webhook deletion."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        # Mock existing repository connection with webhook
        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/test-repo"
        repo_conn.provider = "github"
        repo_conn.webhook_id = "789"
        repo_conn.oauth_connection_id = "oac_123"
        repo_conn.is_enabled = True

        oauth_conn = Mock(spec=OAuthConnectionTable)
        oauth_conn.id = "oac_123"
        oauth_conn.user_id = "user_123"

        mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = repo_conn
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn,
            oauth_conn,
        ]

        # Disconnect repository with webhook deletion
        result = await repo_manager.disconnect_repository(
            db=mock_db,
            user_id="user_123",
            connection_id="rpc_123",
            delete_webhook=True,
            webhook_manager=webhook_manager,
        )

        # Verify disconnection succeeded
        assert result["connection_id"] == "rpc_123"
        assert result["webhook_deleted"] is True

        # Verify repository was soft-deleted
        assert repo_conn.is_enabled is False

        # Verify webhook was deleted from GitHub
        assert mock_github_provider.delete_webhook.called

    @pytest.mark.asyncio
    async def test_disconnect_repository_webhook_deletion_fails_gracefully(
        self,
        repo_manager,
        webhook_manager,
        mock_db,
        mock_github_provider,
    ):
        """Test that repository disconnection succeeds even if webhook deletion fails."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/test-repo"
        repo_conn.provider = "github"
        repo_conn.webhook_id = "789"
        repo_conn.oauth_connection_id = "oac_123"
        repo_conn.is_enabled = True

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = repo_conn
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn,
            oauth_conn,
        ]

        # Make webhook deletion fail
        mock_github_provider.delete_webhook = AsyncMock(
            side_effect=Exception("GitHub API error")
        )

        # Disconnect should still succeed
        result = await repo_manager.disconnect_repository(
            db=mock_db,
            user_id="user_123",
            connection_id="rpc_123",
            delete_webhook=True,
            webhook_manager=webhook_manager,
        )

        # Repository should be disconnected
        assert repo_conn.is_enabled is False

        # Database should still be cleaned up
        assert repo_conn.webhook_id is None
        assert repo_conn.webhook_status == "inactive"

    @pytest.mark.asyncio
    async def test_disconnect_repository_no_webhook(
        self,
        repo_manager,
        mock_db,
    ):
        """Test disconnecting repository that has no webhook."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.webhook_id = None  # No webhook
        repo_conn.is_enabled = True

        oauth_conn = Mock(spec=OAuthConnectionTable)
        oauth_conn.user_id = "user_123"

        mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = repo_conn

        result = await repo_manager.disconnect_repository(
            db=mock_db,
            user_id="user_123",
            connection_id="rpc_123",
            delete_webhook=True,
        )

        # Should succeed without trying to delete webhook
        assert result["webhook_deleted"] is False
        assert repo_conn.is_enabled is False

    @pytest.mark.asyncio
    async def test_connect_repository_already_connected(
        self,
        repo_manager,
        mock_db,
    ):
        """Test connecting repository that is already connected."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        # Mock existing connection
        existing_conn = Mock(spec=RepositoryConnectionTable)
        existing_conn.repository_full_name = "owner/test-repo"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            oauth_conn,
            existing_conn,  # Already exists
        ]

        # Should raise ValueError
        with pytest.raises(ValueError, match="already connected"):
            await repo_manager.connect_repository(
                db=mock_db,
                user_id="user_123",
                repository_full_name="owner/test-repo",
            )

    @pytest.mark.asyncio
    async def test_webhook_events_customization(
        self,
        webhook_manager,
        mock_db,
        mock_token_manager,
    ):
        """Test webhook creation with custom events."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/test-repo"
        repo_conn.provider = "github"
        repo_conn.oauth_connection_id = "oac_123"

        oauth_conn = Mock(spec=OAuthConnectionTable)

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn,
            oauth_conn,
        ]

        # Create webhook with custom events
        custom_events = ["workflow_run", "push"]
        result = await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_123",
            events=custom_events,
        )

        # Verify custom events were used
        assert result["events"] == custom_events

        # Verify webhook_events was stored in database
        assert repo_conn.webhook_events == custom_events

    @pytest.mark.asyncio
    async def test_disconnect_repository_not_found(
        self,
        repo_manager,
        mock_db,
    ):
        """Test disconnecting non-existent repository."""
        mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await repo_manager.disconnect_repository(
                db=mock_db,
                user_id="user_123",
                connection_id="nonexistent",
            )

    @pytest.mark.asyncio
    async def test_webhook_url_configuration(
        self,
        mock_token_manager,
        mock_github_provider,
    ):
        """Test webhook URL is correctly configured."""
        custom_base_url = "https://custom.devflowfix.com"

        manager = WebhookManager(
            token_manager=mock_token_manager,
            github_provider=mock_github_provider,
            webhook_base_url=custom_base_url,
        )

        assert manager.webhook_base_url == custom_base_url

    @pytest.mark.asyncio
    async def test_multiple_webhooks_different_repositories(
        self,
        webhook_manager,
        mock_db,
        mock_token_manager,
    ):
        """Test creating webhooks for multiple repositories."""
        from app.adapters.database.postgres.models import (
            RepositoryConnectionTable,
            OAuthConnectionTable,
        )

        oauth_conn = Mock(spec=OAuthConnectionTable)

        # First repository
        repo_conn1 = Mock(spec=RepositoryConnectionTable)
        repo_conn1.id = "rpc_1"
        repo_conn1.repository_full_name = "owner/repo1"
        repo_conn1.provider = "github"
        repo_conn1.oauth_connection_id = "oac_123"

        # Second repository
        repo_conn2 = Mock(spec=RepositoryConnectionTable)
        repo_conn2.id = "rpc_2"
        repo_conn2.repository_full_name = "owner/repo2"
        repo_conn2.provider = "github"
        repo_conn2.oauth_connection_id = "oac_123"

        # Setup mocks for first webhook
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn1,
            oauth_conn,
        ]

        result1 = await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_1",
        )

        # Setup mocks for second webhook
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            repo_conn2,
            oauth_conn,
        ]

        result2 = await webhook_manager.create_webhook(
            db=mock_db,
            repository_connection_id="rpc_2",
        )

        # Both webhooks should be created successfully
        assert result1["success"] is True
        assert result2["success"] is True

        # Each should have unique webhook ID
        assert repo_conn1.webhook_id is not None
        assert repo_conn2.webhook_id is not None
