# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for GitLab Webhook Processing.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import status


class TestGitLabWebhook:
    """Test suite for GitLab webhook processing."""

    @pytest.fixture
    def pipeline_event_payload(self):
        """Sample GitLab pipeline event payload."""
        return {
            "object_kind": "pipeline",
            "object_attributes": {
                "id": 12345,
                "ref": "main",
                "sha": "abc123",
                "status": "failed",
                "created_at": "2025-01-01T10:00:00Z",
                "finished_at": "2025-01-01T10:05:00Z",
                "duration": 300,
                "source": "push",
            },
            "project": {
                "id": 456,
                "name": "test-project",
                "path_with_namespace": "group/test-project",
                "web_url": "https://gitlab.com/group/test-project",
            },
            "user": {
                "username": "testuser",
            },
            "commit": {
                "id": "abc123",
                "message": "Fix bug",
            },
            "builds": [
                {
                    "id": 111,
                    "stage": "test",
                    "name": "rspec",
                    "status": "failed",
                    "failure_reason": "script_failure",
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_receive_gitlab_webhook_pipeline_event(self, pipeline_event_payload):
        """Test receiving GitLab pipeline webhook event."""
        from app.api.v1.webhook import receive_gitlab_webhook
        from fastapi import Request, BackgroundTasks

        mock_request = Mock(spec=Request)
        mock_request.body = AsyncMock(
            return_value=str(pipeline_event_payload).encode()
        )

        mock_bg_tasks = Mock(spec=BackgroundTasks)
        mock_db = Mock()

        with patch("app.api.v1.webhook.process_oauth_connected_pipeline_event") as mock_process:
            mock_process.return_value = True

            response = await receive_gitlab_webhook(
                user_id="test_user_123",
                request=mock_request,
                background_tasks=mock_bg_tasks,
                x_gitlab_event="Pipeline Hook",
                x_gitlab_token="webhook_token",
                db=mock_db,
                event_processor=Mock(),
            )

            assert response.acknowledged is True
            assert mock_process.called

    @pytest.mark.asyncio
    async def test_process_oauth_connected_pipeline_event_success(self, pipeline_event_payload):
        """Test successful OAuth pipeline event processing."""
        from app.api.v1.webhook import process_oauth_connected_pipeline_event

        mock_db = Mock()

        # Mock repository connection query
        mock_repo = Mock(
            id="repo_123",
            user_id="test_user_123",
            repository_full_name="group/test-project",
            provider="gitlab",
            is_enabled=True,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repo
        mock_db.flush = Mock()
        mock_db.commit = Mock()

        with patch("app.api.v1.webhook.GitLabPipelineTracker") as mock_tracker_class:
            mock_tracker = Mock()
            mock_tracker.process_pipeline_event = AsyncMock(return_value=Mock(
                id="run_123",
                run_id="12345",
                conclusion="failure",
            ))
            mock_tracker_class.return_value = mock_tracker

            result = await process_oauth_connected_pipeline_event(
                db=mock_db,
                user_id="test_user_123",
                payload=pipeline_event_payload,
            )

            assert result is True
            assert mock_tracker.process_pipeline_event.called
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_process_oauth_connected_pipeline_event_no_connection(self, pipeline_event_payload):
        """Test pipeline event with no OAuth connection."""
        from app.api.v1.webhook import process_oauth_connected_pipeline_event

        mock_db = Mock()

        # Mock query to return None (no connection)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await process_oauth_connected_pipeline_event(
            db=mock_db,
            user_id="test_user_123",
            payload=pipeline_event_payload,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_process_oauth_connected_pipeline_event_error(self, pipeline_event_payload):
        """Test pipeline event processing with error."""
        from app.api.v1.webhook import process_oauth_connected_pipeline_event

        mock_db = Mock()
        mock_db.rollback = Mock()

        # Mock repository connection
        mock_repo = Mock(
            id="repo_123",
            user_id="test_user_123",
            repository_full_name="group/test-project",
            provider="gitlab",
            is_enabled=True,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

        with patch("app.api.v1.webhook.GitLabPipelineTracker") as mock_tracker_class:
            mock_tracker = Mock()
            mock_tracker.process_pipeline_event = AsyncMock(
                side_effect=Exception("Processing error")
            )
            mock_tracker_class.return_value = mock_tracker

            result = await process_oauth_connected_pipeline_event(
                db=mock_db,
                user_id="test_user_123",
                payload=pipeline_event_payload,
            )

            assert result is False
            assert mock_db.rollback.called

    def test_verify_gitlab_token_valid(self):
        """Test GitLab token verification with valid token."""
        from app.api.v1.webhook import verify_gitlab_token

        result = verify_gitlab_token(
            token_header="secret_token_123",
            expected_token="secret_token_123",
        )

        assert result is True

    def test_verify_gitlab_token_invalid(self):
        """Test GitLab token verification with invalid token."""
        from app.api.v1.webhook import verify_gitlab_token

        result = verify_gitlab_token(
            token_header="wrong_token",
            expected_token="secret_token_123",
        )

        assert result is False

    def test_verify_gitlab_token_missing(self):
        """Test GitLab token verification with missing token."""
        from app.api.v1.webhook import verify_gitlab_token

        result = verify_gitlab_token(
            token_header=None,
            expected_token="secret_token_123",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_gitlab_webhook_invalid_json(self):
        """Test webhook with invalid JSON payload."""
        from app.api.v1.webhook import receive_gitlab_webhook
        from fastapi import Request, HTTPException

        mock_request = Mock(spec=Request)
        mock_request.body = AsyncMock(
            return_value=b"invalid json {{{{"
        )

        mock_bg_tasks = Mock()
        mock_db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await receive_gitlab_webhook(
                user_id="test_user_123",
                request=mock_request,
                background_tasks=mock_bg_tasks,
                x_gitlab_event="Pipeline Hook",
                x_gitlab_token=None,
                db=mock_db,
                event_processor=Mock(),
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_gitlab_webhook_non_pipeline_event(self):
        """Test webhook with non-pipeline event."""
        from app.api.v1.webhook import receive_gitlab_webhook
        from fastapi import Request

        push_event = {
            "object_kind": "push",
            "ref": "refs/heads/main",
            "commits": [],
        }

        mock_request = Mock(spec=Request)
        mock_request.body = AsyncMock(
            return_value=str(push_event).encode()
        )

        mock_bg_tasks = Mock()
        mock_db = Mock()

        response = await receive_gitlab_webhook(
            user_id="test_user_123",
            request=mock_request,
            background_tasks=mock_bg_tasks,
            x_gitlab_event="Push Hook",
            x_gitlab_token=None,
            db=mock_db,
            event_processor=Mock(),
        )

        # Should acknowledge but not process
        assert response.acknowledged is True

    @pytest.mark.asyncio
    async def test_gitlab_webhook_missing_project_data(self):
        """Test webhook with missing project data."""
        from app.api.v1.webhook import process_oauth_connected_pipeline_event

        incomplete_payload = {
            "object_kind": "pipeline",
            "object_attributes": {"id": 123},
            "project": {},  # Missing path_with_namespace
        }

        mock_db = Mock()

        result = await process_oauth_connected_pipeline_event(
            db=mock_db,
            user_id="test_user_123",
            payload=incomplete_payload,
        )

        assert result is False


class TestGitLabWebhookIntegration:
    """Integration tests for GitLab webhook flow."""

    @pytest.fixture
    def complete_pipeline_failure_payload(self):
        """Complete GitLab pipeline failure payload."""
        return {
            "object_kind": "pipeline",
            "object_attributes": {
                "id": 99999,
                "ref": "main",
                "sha": "def456abc789",
                "status": "failed",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:05:00Z",
                "finished_at": "2025-01-01T12:05:00Z",
                "duration": 300,
                "source": "push",
            },
            "project": {
                "id": 789,
                "name": "my-app",
                "path_with_namespace": "myorg/my-app",
                "web_url": "https://gitlab.com/myorg/my-app",
            },
            "user": {
                "id": 111,
                "name": "John Doe",
                "username": "johndoe",
                "email": "john@example.com",
            },
            "commit": {
                "id": "def456abc789",
                "message": "Update feature X",
                "timestamp": "2025-01-01T11:59:00Z",
                "url": "https://gitlab.com/myorg/my-app/-/commit/def456",
                "author": {
                    "name": "John Doe",
                    "email": "john@example.com",
                },
            },
            "builds": [
                {
                    "id": 11111,
                    "stage": "test",
                    "name": "unit-tests",
                    "status": "failed",
                    "created_at": "2025-01-01T12:00:00Z",
                    "started_at": "2025-01-01T12:00:10Z",
                    "finished_at": "2025-01-01T12:02:00Z",
                    "duration": 110,
                    "allow_failure": False,
                    "failure_reason": "script_failure",
                },
                {
                    "id": 11112,
                    "stage": "build",
                    "name": "compile",
                    "status": "success",
                    "created_at": "2025-01-01T12:00:00Z",
                    "started_at": "2025-01-01T12:00:05Z",
                    "finished_at": "2025-01-01T12:01:00Z",
                    "duration": 55,
                    "allow_failure": False,
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_complete_pipeline_failure_flow(self, complete_pipeline_failure_payload):
        """Test complete flow from webhook to incident creation."""
        from app.api.v1.webhook import process_oauth_connected_pipeline_event
        from app.adapters.database.postgres.models import WorkflowRunTable, IncidentTable

        mock_db = Mock()
        mock_db.flush = Mock()
        mock_db.commit = Mock()

        # Mock repository connection
        mock_repo = Mock(
            id="repo_abc123",
            user_id="user_xyz789",
            repository_full_name="myorg/my-app",
            provider="gitlab",
            is_enabled=True,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repo

        # Track what gets added to database
        added_objects = []
        def track_add(obj):
            added_objects.append(obj)
        mock_db.add = track_add

        with patch("app.api.v1.webhook.GitLabPipelineTracker") as mock_tracker_class:
            # Create real tracker to test actual logic
            from app.services.workflow.gitlab_pipeline_tracker import GitLabPipelineTracker
            real_tracker = GitLabPipelineTracker()
            mock_tracker_class.return_value = real_tracker

            # Mock database queries within tracker
            mock_db.query.return_value.filter.return_value.first.return_value = None

            result = await process_oauth_connected_pipeline_event(
                db=mock_db,
                user_id="user_xyz789",
                payload=complete_pipeline_failure_payload,
            )

            assert result is True

            # Verify workflow run was created
            workflow_runs = [obj for obj in added_objects if isinstance(obj, WorkflowRunTable)]
            assert len(workflow_runs) == 1
            assert workflow_runs[0].run_id == "99999"
            assert workflow_runs[0].conclusion == "failure"

            # Verify incident was created
            incidents = [obj for obj in added_objects if isinstance(obj, IncidentTable)]
            assert len(incidents) == 1
            assert incidents[0].severity in ["high", "medium"]
            assert "unit-tests" in incidents[0].error_message
