# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Integration tests for webhook processing endpoints.
"""

import pytest
import json
import hmac
import hashlib
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.adapters.database.postgres.models import (
    RepositoryConnectionTable,
    WorkflowRunTable,
    IncidentTable,
)


class TestWebhookEndpoints:
    """Integration tests for webhook processing endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def webhook_secret(self):
        """Webhook secret for testing."""
        return "test_webhook_secret_123"

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def github_workflow_payload(self):
        """Sample GitHub workflow_run webhook payload."""
        return {
            "action": "completed",
            "workflow_run": {
                "id": 123456789,
                "run_number": 42,
                "name": "CI",
                "workflow_id": 987654,
                "event": "push",
                "status": "completed",
                "conclusion": "failure",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "head_commit": {
                    "message": "Fix bug in authentication",
                    "author": {
                        "name": "John Doe",
                    },
                },
                "run_started_at": "2025-01-02T10:00:00Z",
                "html_url": "https://github.com/owner/repo/actions/runs/123456789",
                "logs_url": "https://api.github.com/repos/owner/repo/actions/runs/123456789/logs",
            },
            "repository": {
                "id": 111222333,
                "full_name": "owner/repo",
                "name": "repo",
                "private": False,
            },
        }

    @pytest.fixture
    def gitlab_pipeline_payload(self):
        """Sample GitLab pipeline webhook payload."""
        return {
            "object_kind": "pipeline",
            "object_attributes": {
                "id": 789456,
                "status": "failed",
                "ref": "main",
                "sha": "xyz789abc123",
            },
            "project": {
                "id": 444555666,
                "path_with_namespace": "group/project",
                "name": "project",
            },
        }

    def generate_github_signature(self, payload: dict, secret: str) -> str:
        """Generate GitHub webhook signature."""
        payload_bytes = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            key=secret.encode(),
            msg=payload_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_github_webhook_workflow_run_failure(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        github_workflow_payload,
        webhook_secret,
    ):
        """Test GitHub webhook processing for failed workflow run."""
        # Setup mocks
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = webhook_secret
        mock_get_token_manager.return_value = mock_token_manager

        # Mock repository connection
        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.provider = "github"
        repo_conn.user_id = "user_456"
        repo_conn.webhook_secret = "encrypted_secret"

        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        # Generate signature
        signature = self.generate_github_signature(github_workflow_payload, webhook_secret)

        # Make request
        response = client.post(
            "/api/v2/webhooks/github",
            json=github_workflow_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_github_webhook_invalid_signature(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        github_workflow_payload,
    ):
        """Test GitHub webhook rejection with invalid signature."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = "correct_secret"
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.webhook_secret = "encrypted_correct_secret"
        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        # Use wrong signature
        response = client.post(
            "/api/v2/webhooks/github",
            json=github_workflow_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": "sha256=invalid_signature",
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    async def test_github_webhook_unknown_repository(
        self,
        mock_get_db,
        client,
        github_workflow_payload,
        webhook_secret,
    ):
        """Test GitHub webhook for unknown repository."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Repository not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        signature = self.generate_github_signature(github_workflow_payload, webhook_secret)

        response = client.post(
            "/api/v2/webhooks/github",
            json=github_workflow_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        # Should return 200 OK but with message about unknown repo
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Repository not connected"

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    async def test_github_webhook_missing_repository_in_payload(
        self,
        mock_get_db,
        client,
        webhook_secret,
    ):
        """Test GitHub webhook with missing repository information."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Payload without repository
        invalid_payload = {
            "action": "completed",
            "workflow_run": {"id": 123},
        }

        signature = self.generate_github_signature(invalid_payload, webhook_secret)

        response = client.post(
            "/api/v2/webhooks/github",
            json=invalid_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        # Should return 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    async def test_github_webhook_invalid_json(
        self,
        mock_get_db,
        client,
    ):
        """Test GitHub webhook with invalid JSON payload."""
        response = client.post(
            "/api/v2/webhooks/github",
            data="invalid json{{{",
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": "sha256=abc123",
                "X-GitHub-Delivery": "12345-67890",
                "Content-Type": "application/json",
            },
        )

        # Should return 400 Bad Request
        assert response.status_code == 400

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_github_webhook_pull_request_event(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        webhook_secret,
    ):
        """Test GitHub webhook processing for pull_request event."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = webhook_secret
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.webhook_secret = "encrypted_secret"
        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        pr_payload = {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Add new feature",
                "state": "open",
            },
            "repository": {
                "full_name": "owner/repo",
            },
        }

        signature = self.generate_github_signature(pr_payload, webhook_secret)

        response = client.post(
            "/api/v2/webhooks/github",
            json=pr_payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "pull_request_logged"

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_github_webhook_push_event(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        webhook_secret,
    ):
        """Test GitHub webhook processing for push event."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = webhook_secret
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.webhook_secret = "encrypted_secret"
        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        push_payload = {
            "ref": "refs/heads/main",
            "commits": [
                {"id": "abc123", "message": "Fix bug"},
                {"id": "def456", "message": "Add feature"},
            ],
            "repository": {
                "full_name": "owner/repo",
            },
        }

        signature = self.generate_github_signature(push_payload, webhook_secret)

        response = client.post(
            "/api/v2/webhooks/github",
            json=push_payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "push_logged"
        assert data["commits"] == 2

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_gitlab_webhook_valid_token(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        gitlab_pipeline_payload,
        webhook_secret,
    ):
        """Test GitLab webhook processing with valid token."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = webhook_secret
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_789"
        repo_conn.provider = "gitlab"
        repo_conn.webhook_secret = "encrypted_secret"
        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        response = client.post(
            "/api/v2/webhooks/gitlab",
            json=gitlab_pipeline_payload,
            headers={
                "X-Gitlab-Event": "Pipeline Hook",
                "X-Gitlab-Token": webhook_secret,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_gitlab_webhook_invalid_token(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        gitlab_pipeline_payload,
    ):
        """Test GitLab webhook rejection with invalid token."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = "correct_secret"
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.webhook_secret = "encrypted_correct_secret"
        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        response = client.post(
            "/api/v2/webhooks/gitlab",
            json=gitlab_pipeline_payload,
            headers={
                "X-Gitlab-Event": "Pipeline Hook",
                "X-Gitlab-Token": "wrong_token",
            },
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_github_webhook_updates_last_delivery_time(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        github_workflow_payload,
        webhook_secret,
    ):
        """Test that webhook updates last_delivery_at timestamp."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = webhook_secret
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.id = "rpc_123"
        repo_conn.repository_full_name = "owner/repo"
        repo_conn.webhook_secret = "encrypted_secret"
        repo_conn.webhook_last_delivery_at = None

        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        signature = self.generate_github_signature(github_workflow_payload, webhook_secret)

        response = client.post(
            "/api/v2/webhooks/github",
            json=github_workflow_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        assert response.status_code == 200

        # Verify last_delivery_at was updated
        assert repo_conn.webhook_last_delivery_at is not None

    @pytest.mark.asyncio
    @patch("app.api.v2.webhooks.get_db")
    @patch("app.api.v2.webhooks.get_token_manager")
    async def test_github_webhook_unhandled_event_type(
        self,
        mock_get_token_manager,
        mock_get_db,
        client,
        webhook_secret,
    ):
        """Test GitHub webhook with unhandled event type."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_token_manager = MagicMock()
        mock_token_manager.decrypt_token.return_value = webhook_secret
        mock_get_token_manager.return_value = mock_token_manager

        repo_conn = Mock(spec=RepositoryConnectionTable)
        repo_conn.webhook_secret = "encrypted_secret"
        mock_db.query.return_value.filter.return_value.first.return_value = repo_conn

        payload = {
            "action": "created",
            "repository": {
                "full_name": "owner/repo",
            },
        }

        signature = self.generate_github_signature(payload, webhook_secret)

        response = client.post(
            "/api/v2/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "star",  # Unhandled event
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "12345-67890",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "not processed" in data["message"].lower()
