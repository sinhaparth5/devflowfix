# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for GitLab OAuth API Endpoints.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import status
from datetime import datetime, timedelta, timezone


class TestGitLabOAuthEndpoints:
    """Test suite for GitLab OAuth API endpoints."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        user = Mock()
        user.user_id = "test_user_123"
        user.email = "test@example.com"
        user.full_name = "Test User"
        return user

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with GitLab OAuth credentials."""
        with patch("app.api.v2.oauth.gitlab.settings") as mock:
            mock.gitlab_oauth_client_id = "test_client_id"
            mock.gitlab_oauth_client_secret = "test_client_secret"
            mock.gitlab_oauth_redirect_uri = "http://localhost:3000/callback"
            mock.gitlab_oauth_scopes = "api,read_user"
            mock.gitlab_instance_url = "https://gitlab.com"
            mock.cors_origins = "http://localhost:3000"
            mock.oauth_token_encryption_key = "test_key"
            yield mock

    @pytest.mark.asyncio
    async def test_authorize_gitlab_generates_state(self, mock_user, mock_settings):
        """Test that authorize endpoint generates CSRF state."""
        from app.api.v2.oauth.gitlab import authorize_gitlab
        from fastapi import Request, Response

        mock_request = Mock(spec=Request)
        mock_response = Mock(spec=Response)
        mock_response.set_cookie = Mock()

        with patch("app.api.v2.oauth.gitlab.get_gitlab_oauth_provider") as mock_provider:
            provider_mock = Mock()
            provider_mock.generate_state.return_value = "random_state_abc123"
            provider_mock.build_authorization_url.return_value = "https://gitlab.com/oauth/authorize?state=random_state_abc123"
            mock_provider.return_value = provider_mock

            result = await authorize_gitlab(
                request=mock_request,
                response=mock_response,
                current_user_data={"user": mock_user},
            )

            assert result.authorization_url == "https://gitlab.com/oauth/authorize?state=random_state_abc123"
            assert result.state == "random_state_abc123"
            assert result.provider == "gitlab"
            # Verify state cookie was set
            assert mock_response.set_cookie.called

    @pytest.mark.asyncio
    async def test_authorize_gitlab_missing_config(self):
        """Test authorization fails with missing configuration."""
        from app.api.v2.oauth.gitlab import get_gitlab_oauth_provider
        from fastapi import HTTPException

        with patch("app.api.v2.oauth.gitlab.settings") as mock_settings:
            mock_settings.gitlab_oauth_client_id = None
            mock_settings.gitlab_oauth_client_secret = None
            mock_settings.gitlab_oauth_redirect_uri = None

            with pytest.raises(HTTPException) as exc_info:
                get_gitlab_oauth_provider()

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_gitlab_callback_success(self, mock_user, mock_settings):
        """Test successful GitLab OAuth callback."""
        from app.api.v2.oauth.gitlab import gitlab_callback
        from fastapi import Request
        from fastapi.responses import RedirectResponse

        mock_request = Mock(spec=Request)
        mock_request.cookies = {f"oauth_state_{mock_user.user_id}": "valid_state"}

        mock_db = Mock()
        mock_db.commit = Mock()

        with patch("app.api.v2.oauth.gitlab.get_gitlab_oauth_provider") as mock_provider:
            provider_mock = Mock()
            provider_mock.validate_state.return_value = True
            provider_mock.exchange_code_for_token = AsyncMock(return_value={
                "access_token": "gitlab_token_123",
                "refresh_token": "refresh_token_456",
                "expires_in": 7200,
                "scope": "api read_user",
            })
            provider_mock.get_user_info = AsyncMock(return_value={
                "id": 12345,
                "username": "testuser",
                "name": "Test User",
                "email": "test@example.com",
            })
            mock_provider.return_value = provider_mock

            with patch("app.api.v2.oauth.gitlab.get_token_manager") as mock_tm:
                token_manager_mock = Mock()
                token_manager_mock.store_oauth_connection = AsyncMock(return_value=Mock(
                    id="oac_123",
                    provider="gitlab",
                ))
                mock_tm.return_value = token_manager_mock

                result = await gitlab_callback(
                    request=mock_request,
                    code="auth_code_123",
                    state="valid_state",
                    db=mock_db,
                    current_user_data={"user": mock_user},
                )

                assert isinstance(result, RedirectResponse)
                assert "oauth=success" in result.headers["location"]
                assert "provider=gitlab" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_gitlab_callback_invalid_state(self, mock_user, mock_settings):
        """Test callback fails with invalid state."""
        from app.api.v2.oauth.gitlab import gitlab_callback
        from fastapi import Request, HTTPException

        mock_request = Mock(spec=Request)
        mock_request.cookies = {f"oauth_state_{mock_user.user_id}": "stored_state"}

        mock_db = Mock()

        with patch("app.api.v2.oauth.gitlab.get_gitlab_oauth_provider") as mock_provider:
            provider_mock = Mock()
            provider_mock.validate_state.return_value = False
            mock_provider.return_value = provider_mock

            result = await gitlab_callback(
                request=mock_request,
                code="auth_code_123",
                state="different_state",
                db=mock_db,
                current_user_data={"user": mock_user},
            )

            # Should redirect to error page
            assert "oauth=error" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_get_gitlab_connection_exists(self, mock_user, mock_settings):
        """Test getting existing GitLab connection."""
        from app.api.v2.oauth.gitlab import get_gitlab_connection

        mock_db = Mock()
        mock_connection = Mock(
            id="oac_123",
            user_id=mock_user.user_id,
            provider="gitlab",
            provider_username="testuser",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.v2.oauth.gitlab.get_token_manager") as mock_tm:
            token_manager_mock = Mock()
            token_manager_mock.get_oauth_connection = AsyncMock(return_value=mock_connection)
            mock_tm.return_value = token_manager_mock

            result = await get_gitlab_connection(
                db=mock_db,
                current_user_data={"user": mock_user},
            )

            # Verify result has from_orm method called
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_gitlab_connection_not_found(self, mock_user, mock_settings):
        """Test getting non-existent GitLab connection."""
        from app.api.v2.oauth.gitlab import get_gitlab_connection
        from fastapi import HTTPException

        mock_db = Mock()

        with patch("app.api.v2.oauth.gitlab.get_token_manager") as mock_tm:
            token_manager_mock = Mock()
            token_manager_mock.get_oauth_connection = AsyncMock(return_value=None)
            mock_tm.return_value = token_manager_mock

            with pytest.raises(HTTPException) as exc_info:
                await get_gitlab_connection(
                    db=mock_db,
                    current_user_data={"user": mock_user},
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_disconnect_gitlab_success(self, mock_user, mock_settings):
        """Test successful GitLab disconnection."""
        from app.api.v2.oauth.gitlab import disconnect_gitlab

        mock_db = Mock()
        mock_db.commit = Mock()

        mock_connection = Mock(
            id="oac_123",
            access_token="encrypted_token",
        )

        with patch("app.api.v2.oauth.gitlab.get_token_manager") as mock_tm:
            token_manager_mock = Mock()
            token_manager_mock.get_oauth_connection = AsyncMock(return_value=mock_connection)
            token_manager_mock.get_decrypted_token.return_value = "decrypted_token"
            token_manager_mock.revoke_oauth_connection = AsyncMock(return_value=True)
            mock_tm.return_value = token_manager_mock

            with patch("app.api.v2.oauth.gitlab.get_gitlab_oauth_provider") as mock_provider:
                provider_mock = Mock()
                provider_mock.revoke_token = AsyncMock(return_value=True)
                mock_provider.return_value = provider_mock

                result = await disconnect_gitlab(
                    db=mock_db,
                    current_user_data={"user": mock_user},
                )

                assert result.success is True
                assert result.provider == "gitlab"
                assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_refresh_gitlab_token_success(self, mock_user, mock_settings):
        """Test successful token refresh."""
        from app.api.v2.oauth.gitlab import refresh_gitlab_token

        mock_db = Mock()
        mock_db.commit = Mock()

        mock_connection = Mock(
            id="oac_123",
            refresh_token_encrypted="encrypted_refresh",
        )

        with patch("app.api.v2.oauth.gitlab.get_token_manager") as mock_tm:
            token_manager_mock = Mock()
            token_manager_mock.get_oauth_connection = AsyncMock(return_value=mock_connection)
            token_manager_mock.decrypt_token.return_value = "refresh_token"
            token_manager_mock.update_oauth_tokens = AsyncMock(return_value=mock_connection)
            mock_tm.return_value = token_manager_mock

            with patch("app.api.v2.oauth.gitlab.get_gitlab_oauth_provider") as mock_provider:
                provider_mock = Mock()
                provider_mock.refresh_access_token = AsyncMock(return_value={
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token",
                    "expires_in": 7200,
                })
                mock_provider.return_value = provider_mock

                result = await refresh_gitlab_token(
                    db=mock_db,
                    current_user_data={"user": mock_user},
                )

                assert result is not None
                assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_refresh_gitlab_token_no_refresh_token(self, mock_user, mock_settings):
        """Test refresh fails without refresh token."""
        from app.api.v2.oauth.gitlab import refresh_gitlab_token
        from fastapi import HTTPException

        mock_db = Mock()
        mock_connection = Mock(
            id="oac_123",
            refresh_token_encrypted=None,
        )

        with patch("app.api.v2.oauth.gitlab.get_token_manager") as mock_tm:
            token_manager_mock = Mock()
            token_manager_mock.get_oauth_connection = AsyncMock(return_value=mock_connection)
            mock_tm.return_value = token_manager_mock

            with pytest.raises(HTTPException) as exc_info:
                await refresh_gitlab_token(
                    db=mock_db,
                    current_user_data={"user": mock_user},
                )

            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
