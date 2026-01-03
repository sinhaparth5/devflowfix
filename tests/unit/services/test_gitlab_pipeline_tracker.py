# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for GitLab Pipeline Tracker.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone
import uuid

from app.services.workflow.gitlab_pipeline_tracker import GitLabPipelineTracker
from app.adapters.database.postgres.models import (
    WorkflowRunTable,
    IncidentTable,
    RepositoryConnectionTable,
)


class TestGitLabPipelineTracker:
    """Test suite for GitLabPipelineTracker."""

    @pytest.fixture
    def tracker(self):
        """Create GitLabPipelineTracker instance for testing."""
        return GitLabPipelineTracker()

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.add = Mock()
        db.flush = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        db.query = Mock()
        return db

    @pytest.fixture
    def mock_repo_connection(self):
        """Create mock repository connection."""
        return RepositoryConnectionTable(
            id=str(uuid.uuid4()),
            user_id="test_user_123",
            oauth_connection_id=str(uuid.uuid4()),
            provider="gitlab",
            provider_repository_id="456",
            repository_full_name="group/test-project",
            repository_name="test-project",
            default_branch="main",
            is_enabled=True,
        )

    @pytest.fixture
    def pipeline_event_payload(self):
        """Create sample GitLab pipeline event payload."""
        return {
            "object_kind": "pipeline",
            "object_attributes": {
                "id": 12345,
                "ref": "main",
                "sha": "abc123def456",
                "status": "failed",
                "created_at": "2025-01-01T10:00:00Z",
                "updated_at": "2025-01-01T10:05:00Z",
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
                "id": 789,
                "name": "Test User",
                "username": "testuser",
                "email": "test@example.com",
            },
            "commit": {
                "id": "abc123def456",
                "message": "Fix bug in login",
                "timestamp": "2025-01-01T09:59:00Z",
                "url": "https://gitlab.com/group/test-project/-/commit/abc123",
                "author": {
                    "name": "Test User",
                    "email": "test@example.com",
                },
            },
            "builds": [
                {
                    "id": 111,
                    "stage": "test",
                    "name": "rspec",
                    "status": "failed",
                    "created_at": "2025-01-01T10:00:00Z",
                    "started_at": "2025-01-01T10:00:10Z",
                    "finished_at": "2025-01-01T10:01:00Z",
                    "duration": 50,
                    "allow_failure": False,
                    "failure_reason": "script_failure",
                },
            ],
        }

    def test_map_gitlab_status_created(self, tracker):
        """Test GitLab status mapping for 'created'."""
        status, conclusion = tracker._map_gitlab_status("created")
        assert status == "queued"
        assert conclusion is None

    def test_map_gitlab_status_running(self, tracker):
        """Test GitLab status mapping for 'running'."""
        status, conclusion = tracker._map_gitlab_status("running")
        assert status == "in_progress"
        assert conclusion is None

    def test_map_gitlab_status_success(self, tracker):
        """Test GitLab status mapping for 'success'."""
        status, conclusion = tracker._map_gitlab_status("success")
        assert status == "completed"
        assert conclusion == "success"

    def test_map_gitlab_status_failed(self, tracker):
        """Test GitLab status mapping for 'failed'."""
        status, conclusion = tracker._map_gitlab_status("failed")
        assert status == "completed"
        assert conclusion == "failure"

    def test_map_gitlab_status_canceled(self, tracker):
        """Test GitLab status mapping for 'canceled'."""
        status, conclusion = tracker._map_gitlab_status("canceled")
        assert status == "completed"
        assert conclusion == "cancelled"

    def test_map_gitlab_status_unknown(self, tracker):
        """Test GitLab status mapping for unknown status."""
        status, conclusion = tracker._map_gitlab_status("unknown_status")
        assert status == "completed"
        assert conclusion == "unknown"

    def test_determine_severity_production_branch(self, tracker):
        """Test severity determination for production branch."""
        severity = tracker._determine_severity(
            branch="main",
            failed_builds=[],
        )
        assert severity == "high"

    def test_determine_severity_multiple_failures(self, tracker):
        """Test severity determination with multiple failed jobs."""
        failed_builds = [{"name": f"job{i}"} for i in range(5)]
        severity = tracker._determine_severity(
            branch="feature",
            failed_builds=failed_builds,
        )
        assert severity == "high"

    def test_determine_severity_critical_failure_reason(self, tracker):
        """Test severity determination with critical failure reason."""
        failed_builds = [{"failure_reason": "unknown_failure"}]
        severity = tracker._determine_severity(
            branch="feature",
            failed_builds=failed_builds,
        )
        assert severity == "high"

    def test_determine_severity_default(self, tracker):
        """Test default severity determination."""
        failed_builds = [{"failure_reason": "script_failure"}]
        severity = tracker._determine_severity(
            branch="feature",
            failed_builds=failed_builds,
        )
        assert severity == "medium"

    def test_build_failure_summary_no_failures(self, tracker):
        """Test failure summary with no failed builds."""
        pipeline = {"id": 123}
        summary = tracker._build_failure_summary(
            pipeline=pipeline,
            failed_builds=[],
            commit={},
        )
        assert "pipeline #123 failed" in summary

    def test_build_failure_summary_single_failure(self, tracker):
        """Test failure summary with single failed job."""
        pipeline = {"id": 123}
        failed_builds = [
            {"name": "test-job", "failure_reason": "script_failure"}
        ]
        commit = {}

        summary = tracker._build_failure_summary(
            pipeline=pipeline,
            failed_builds=failed_builds,
            commit=commit,
        )

        assert "test-job" in summary
        assert "script_failure" in summary

    def test_build_failure_summary_multiple_failures(self, tracker):
        """Test failure summary with multiple failed jobs."""
        pipeline = {"id": 123}
        failed_builds = [
            {"name": "job1", "failure_reason": "script_failure"},
            {"name": "job2", "failure_reason": "timeout"},
            {"name": "job3", "failure_reason": "error"},
            {"name": "job4", "failure_reason": "error"},
        ]
        commit = {}

        summary = tracker._build_failure_summary(
            pipeline=pipeline,
            failed_builds=failed_builds,
            commit=commit,
        )

        assert "job1" in summary
        assert "job2" in summary
        assert "job3" in summary
        assert "+1 more" in summary  # 4th job

    @pytest.mark.asyncio
    async def test_process_pipeline_event_new_run(
        self, tracker, mock_db, mock_repo_connection, pipeline_event_payload
    ):
        """Test processing new pipeline event."""
        # Mock database query to return None (no existing run)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await tracker.process_pipeline_event(
            db=mock_db,
            event_payload=pipeline_event_payload,
            repository_connection=mock_repo_connection,
        )

        # Verify workflow run was added
        assert mock_db.add.called
        assert mock_db.flush.called

        # Verify result is a WorkflowRunTable
        call_args = mock_db.add.call_args_list
        added_workflow = call_args[0][0][0]
        assert isinstance(added_workflow, WorkflowRunTable)
        assert added_workflow.run_id == "12345"
        assert added_workflow.conclusion == "failure"

    @pytest.mark.asyncio
    async def test_process_pipeline_event_update_existing(
        self, tracker, mock_db, mock_repo_connection, pipeline_event_payload
    ):
        """Test updating existing pipeline run."""
        # Mock existing workflow run
        existing_run = WorkflowRunTable(
            id=str(uuid.uuid4()),
            repository_connection_id=mock_repo_connection.id,
            run_id="12345",
            status="in_progress",
            conclusion=None,
        )

        # Mock database query to return existing run
        mock_db.query.return_value.filter.return_value.first.return_value = existing_run

        result = await tracker.process_pipeline_event(
            db=mock_db,
            event_payload=pipeline_event_payload,
            repository_connection=mock_repo_connection,
        )

        # Verify run was updated
        assert existing_run.status == "completed"
        assert existing_run.conclusion == "failure"
        assert mock_db.add.called
        assert mock_db.flush.called

    @pytest.mark.asyncio
    async def test_process_pipeline_event_creates_incident(
        self, tracker, mock_db, mock_repo_connection, pipeline_event_payload
    ):
        """Test that failed pipeline creates incident."""
        # Mock database query to return None (no existing run)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await tracker.process_pipeline_event(
            db=mock_db,
            event_payload=pipeline_event_payload,
            repository_connection=mock_repo_connection,
        )

        # Verify incident was created
        # The add method should be called twice: once for workflow, once for incident
        assert mock_db.add.call_count >= 2

        # Check if IncidentTable was added
        call_args = mock_db.add.call_args_list
        incident_added = any(
            isinstance(args[0][0], IncidentTable)
            for args in call_args
        )
        assert incident_added

    @pytest.mark.asyncio
    async def test_process_pipeline_event_success_no_incident(
        self, tracker, mock_db, mock_repo_connection, pipeline_event_payload
    ):
        """Test that successful pipeline doesn't create incident."""
        # Modify payload to success
        pipeline_event_payload["object_attributes"]["status"] = "success"

        # Mock database query to return None (no existing run)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await tracker.process_pipeline_event(
            db=mock_db,
            event_payload=pipeline_event_payload,
            repository_connection=mock_repo_connection,
        )

        # Verify workflow run was added but incident was not
        assert mock_db.add.call_count == 1
        call_args = mock_db.add.call_args_list
        assert isinstance(call_args[0][0][0], WorkflowRunTable)

    @pytest.mark.asyncio
    async def test_get_pipeline_runs(self, tracker, mock_db):
        """Test getting pipeline runs."""
        # Mock pipeline runs
        mock_runs = [
            Mock(id=str(uuid.uuid4()), run_id="1", status="completed"),
            Mock(id=str(uuid.uuid4()), run_id="2", status="in_progress"),
        ]

        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_runs
        mock_db.query.return_value = mock_query

        runs = await tracker.get_pipeline_runs(
            db=mock_db,
            repository_connection_id="test_repo_id",
            limit=50,
        )

        assert len(runs) == 2
        assert runs[0].run_id == "1"
        assert runs[1].run_id == "2"

    @pytest.mark.asyncio
    async def test_get_pipeline_stats(self, tracker, mock_db):
        """Test getting pipeline statistics."""
        # Mock pipeline runs
        mock_runs = [
            Mock(conclusion="success"),
            Mock(conclusion="success"),
            Mock(conclusion="failure"),
            Mock(conclusion="cancelled"),
        ]

        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_runs
        mock_db.query.return_value = mock_query

        stats = await tracker.get_pipeline_stats(
            db=mock_db,
            repository_connection_id="test_repo_id",
        )

        assert stats["total_runs"] == 4
        assert stats["successful_runs"] == 2
        assert stats["failed_runs"] == 1
        assert stats["cancelled_runs"] == 1
        assert stats["success_rate"] == 50.0
        assert stats["failure_rate"] == 25.0

    @pytest.mark.asyncio
    async def test_get_pipeline_stats_no_runs(self, tracker, mock_db):
        """Test pipeline stats with no runs."""
        # Mock empty runs
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        stats = await tracker.get_pipeline_stats(
            db=mock_db,
            repository_connection_id="test_repo_id",
        )

        assert stats["total_runs"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["failure_rate"] == 0.0
