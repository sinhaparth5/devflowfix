# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for GitLab OAuth Provider.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from app.services.oauth.gitlab_oauth import GitLabOAuthProvider


class TestGitLabOAuthProvider:
    """Test suite for GitLabOAuthProvider."""

    @pytest.fixture
    def provider(self):
        """Create GitLab OAuth provider instance for testing."""
        return GitLabOAuthProvider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="http://localhost:3000/callback",
            scopes=["api", "read_user"],
            gitlab_url="https://gitlab.com",
        )

    def test_provider_initialization(self, provider):
        """Test provider initialization with correct values."""
        assert provider.client_id == "test_client_id"
        assert provider.client_secret == "test_client_secret"
        assert provider.redirect_uri == "http://localhost:3000/callback"
        assert provider.scopes == ["api", "read_user"]
        assert provider.gitlab_url == "https://gitlab.com"

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.provider_name == "gitlab"

    def test_authorize_url(self, provider):
        """Test authorize URL construction."""
        assert provider.authorize_url == "https://gitlab.com/oauth/authorize"

    def test_token_url(self, provider):
        """Test token URL construction."""
        assert provider.token_url == "https://gitlab.com/oauth/token"

    def test_user_info_url(self, provider):
        """Test user info URL construction."""
        assert provider.user_info_url == "https://gitlab.com/api/v4/user"

    def test_custom_gitlab_url(self):
        """Test custom GitLab instance URL."""
        provider = GitLabOAuthProvider(
            client_id="test",
            client_secret="test",
            redirect_uri="http://localhost/callback",
            scopes=["api"],
            gitlab_url="https://gitlab.mycompany.com",
        )
        assert provider.gitlab_url == "https://gitlab.mycompany.com"
        assert provider.authorize_url == "https://gitlab.mycompany.com/oauth/authorize"

    def test_gitlab_url_trailing_slash_removal(self):
        """Test that trailing slash is removed from GitLab URL."""
        provider = GitLabOAuthProvider(
            client_id="test",
            client_secret="test",
            redirect_uri="http://localhost/callback",
            scopes=["api"],
            gitlab_url="https://gitlab.com/",
        )
        assert provider.gitlab_url == "https://gitlab.com"

    def test_build_authorization_url(self, provider):
        """Test authorization URL building with state."""
        state = "random_state_123"
        auth_url = provider.build_authorization_url(state)

        assert "https://gitlab.com/oauth/authorize" in auth_url
        assert "client_id=test_client_id" in auth_url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fcallback" in auth_url
        assert "response_type=code" in auth_url
        assert f"state={state}" in auth_url
        assert "scope=api+read_user" in auth_url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, provider):
        """Test successful token exchange."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "gitlab_access_token_123",
            "refresh_token": "gitlab_refresh_token_456",
            "token_type": "Bearer",
            "expires_in": 7200,
            "scope": "api read_user",
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            token_data = await provider.exchange_code_for_token("auth_code_123")

            assert token_data["access_token"] == "gitlab_access_token_123"
            assert token_data["refresh_token"] == "gitlab_refresh_token_456"
            assert token_data["expires_in"] == 7200

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self, provider):
        """Test token exchange failure."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("Invalid code")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(Exception, match="Invalid code"):
                await provider.exchange_code_for_token("invalid_code")

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, provider):
        """Test successful token refresh."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "new_access_token_789",
            "refresh_token": "new_refresh_token_012",
            "expires_in": 7200,
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            token_data = await provider.refresh_access_token("old_refresh_token")

            assert token_data["access_token"] == "new_access_token_789"
            assert token_data["refresh_token"] == "new_refresh_token_012"

    @pytest.mark.asyncio
    async def test_get_user_info_success(self, provider):
        """Test successful user info retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 12345,
            "username": "testuser",
            "name": "Test User",
            "email": "test@example.com",
            "avatar_url": "https://gitlab.com/avatar.jpg",
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            user_info = await provider.get_user_info("access_token")

            assert user_info["id"] == 12345
            assert user_info["username"] == "testuser"
            assert user_info["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_revoke_token_success(self, provider):
        """Test successful token revocation."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await provider.revoke_token("token_to_revoke")

            assert result is True

    @pytest.mark.asyncio
    async def test_revoke_token_failure(self, provider):
        """Test token revocation failure."""
        mock_response = Mock()
        mock_response.status_code = 400

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await provider.revoke_token("invalid_token")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_user_projects_success(self, provider):
        """Test successful project listing."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "name": "Project 1",
                "path_with_namespace": "group/project1",
                "web_url": "https://gitlab.com/group/project1",
                "visibility": "private",
                "default_branch": "main",
            },
            {
                "id": 2,
                "name": "Project 2",
                "path_with_namespace": "group/project2",
                "web_url": "https://gitlab.com/group/project2",
                "visibility": "public",
                "default_branch": "master",
            },
        ]
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            projects = await provider.get_user_projects(
                access_token="token",
                page=1,
                per_page=100,
            )

            assert len(projects) == 2
            assert projects[0]["name"] == "Project 1"
            assert projects[1]["visibility"] == "public"

    @pytest.mark.asyncio
    async def test_get_project_success(self, provider):
        """Test successful project retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 123,
            "name": "Test Project",
            "path_with_namespace": "group/test-project",
            "web_url": "https://gitlab.com/group/test-project",
            "default_branch": "main",
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            project = await provider.get_project(
                access_token="token",
                project_id="group/test-project",
            )

            assert project["id"] == 123
            assert project["name"] == "Test Project"

    @pytest.mark.asyncio
    async def test_create_project_hook_success(self, provider):
        """Test successful webhook creation."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 456,
            "url": "https://api.example.com/webhooks",
            "pipeline_events": True,
            "merge_requests_events": True,
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            hook = await provider.create_project_hook(
                access_token="token",
                project_id="123",
                webhook_url="https://api.example.com/webhooks",
                token="webhook_secret",
                events=["pipeline_events", "merge_requests_events"],
            )

            assert hook["id"] == 456
            assert hook["pipeline_events"] is True

    @pytest.mark.asyncio
    async def test_delete_project_hook_success(self, provider):
        """Test successful webhook deletion."""
        mock_response = Mock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete = AsyncMock(
                return_value=mock_response
            )

            result = await provider.delete_project_hook(
                access_token="token",
                project_id="123",
                hook_id=456,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_get_pipeline_runs_success(self, provider):
        """Test successful pipeline runs retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "status": "success",
                "ref": "main",
                "sha": "abc123",
            },
            {
                "id": 2,
                "status": "failed",
                "ref": "develop",
                "sha": "def456",
            },
        ]
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            pipelines = await provider.get_pipeline_runs(
                access_token="token",
                project_id="123",
                page=1,
                per_page=20,
            )

            assert len(pipelines) == 2
            assert pipelines[0]["status"] == "success"
            assert pipelines[1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_retry_pipeline_success(self, provider):
        """Test successful pipeline retry."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 789,
            "status": "pending",
            "ref": "main",
        }
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            pipeline = await provider.retry_pipeline(
                access_token="token",
                project_id="123",
                pipeline_id=789,
            )

            assert pipeline["id"] == 789
            assert pipeline["status"] == "pending"
