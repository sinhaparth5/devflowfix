# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for Analytics API Endpoints.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import status
from datetime import datetime, timedelta, timezone


class TestAnalyticsEndpoints:
    """Test suite for Analytics API endpoints."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        user = Mock()
        user.user_id = "test_user_123"
        user.email = "test@example.com"
        return user

    @pytest.fixture
    def mock_analytics_service(self):
        """Mock analytics service."""
        with patch("app.api.v2.analytics.get_analytics_service") as mock:
            service = Mock()
            mock.return_value = service
            yield service

    @pytest.mark.asyncio
    async def test_get_workflow_trends_success(self, mock_user, mock_analytics_service):
        """Test getting workflow trends."""
        from app.api.v2.analytics import get_workflow_trends

        mock_db = Mock()

        # Mock service response
        mock_trends = {
            "period": "day",
            "total_runs": [],
            "successful_runs": [],
            "failed_runs": [],
            "failure_rate": [],
            "avg_duration": [],
            "summary": {
                "total_runs": 100,
                "successful_runs": 80,
                "failed_runs": 20,
                "failure_rate": 20.0,
                "success_rate": 80.0,
            },
        }
        mock_analytics_service.get_workflow_trends = AsyncMock(return_value=mock_trends)

        result = await get_workflow_trends(
            days=30,
            period="day",
            repository_connection_id=None,
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.period == "day"
        assert result.summary["total_runs"] == 100
        assert result.summary["success_rate"] == 80.0

    @pytest.mark.asyncio
    async def test_get_workflow_trends_with_repository_filter(self, mock_user, mock_analytics_service):
        """Test getting workflow trends filtered by repository."""
        from app.api.v2.analytics import get_workflow_trends

        mock_db = Mock()

        mock_trends = {
            "period": "day",
            "total_runs": [],
            "successful_runs": [],
            "failed_runs": [],
            "failure_rate": [],
            "avg_duration": [],
            "summary": {
                "total_runs": 50,
                "successful_runs": 45,
                "failed_runs": 5,
                "failure_rate": 10.0,
                "success_rate": 90.0,
            },
        }
        mock_analytics_service.get_workflow_trends = AsyncMock(return_value=mock_trends)

        result = await get_workflow_trends(
            days=30,
            period="day",
            repository_connection_id="repo_123",
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        # Verify repository filter was passed
        call_args = mock_analytics_service.get_workflow_trends.call_args
        assert call_args[1]["repository_connection_id"] == "repo_123"

    @pytest.mark.asyncio
    async def test_get_repository_health_success(self, mock_user, mock_analytics_service):
        """Test getting repository health metrics."""
        from app.api.v2.analytics import get_repository_health

        mock_db = Mock()

        mock_health = [
            {
                "repository_full_name": "owner/repo1",
                "total_workflows": 100,
                "successful_workflows": 90,
                "failed_workflows": 10,
                "failure_rate": 10.0,
                "total_incidents": 5,
                "open_incidents": 1,
                "resolved_incidents": 4,
                "prs_created": 3,
                "prs_merged": 2,
                "pr_merge_rate": 66.67,
                "avg_resolution_time_hours": None,
                "health_score": 85.0,
                "last_failure": None,
                "last_success": None,
            },
            {
                "repository_full_name": "owner/repo2",
                "total_workflows": 50,
                "successful_workflows": 48,
                "failed_workflows": 2,
                "failure_rate": 4.0,
                "total_incidents": 2,
                "open_incidents": 0,
                "resolved_incidents": 2,
                "prs_created": 2,
                "prs_merged": 2,
                "pr_merge_rate": 100.0,
                "avg_resolution_time_hours": None,
                "health_score": 95.0,
                "last_failure": None,
                "last_success": None,
            },
        ]
        mock_analytics_service.get_repository_health_metrics = AsyncMock(return_value=mock_health)

        result = await get_repository_health(
            repository_connection_id=None,
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.total_repositories == 2
        assert result.avg_health_score == 90.0
        assert len(result.repositories) == 2

    @pytest.mark.asyncio
    async def test_get_incident_trends_success(self, mock_user, mock_analytics_service):
        """Test getting incident trends."""
        from app.api.v2.analytics import get_incident_trends

        mock_db = Mock()

        mock_trends = {
            "period": "day",
            "incidents_created": [],
            "incidents_resolved": [],
            "open_incidents": [],
            "avg_resolution_time": [],
            "by_severity": {
                "critical": [],
                "high": [],
                "medium": [],
                "low": [],
            },
            "by_source": {
                "github": 50,
                "gitlab": 30,
            },
            "summary": {
                "total_incidents": 80,
                "resolved_incidents": 60,
                "open_incidents": 20,
                "resolution_rate": 75.0,
            },
        }
        mock_analytics_service.get_incident_trends = AsyncMock(return_value=mock_trends)

        result = await get_incident_trends(
            days=30,
            period="day",
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.period == "day"
        assert result.summary["total_incidents"] == 80
        assert result.summary["resolution_rate"] == 75.0
        assert result.by_source["github"] == 50

    @pytest.mark.asyncio
    async def test_get_system_health_success(self, mock_user, mock_analytics_service):
        """Test getting system health."""
        from app.api.v2.analytics import get_system_health

        mock_db = Mock()

        mock_health = {
            "status": "healthy",
            "health_score": 95.0,
            "total_repositories": 10,
            "active_repositories": 8,
            "total_workflows_tracked": 500,
            "total_incidents": 50,
            "open_incidents": 5,
            "total_prs_created": 30,
            "oauth_connections": 2,
            "webhook_health": {
                "active_webhooks": 8,
                "failed_webhooks": 0,
            },
            "last_24h_activity": {
                "workflows": 25,
                "incidents": 2,
                "prs": 1,
            },
            "alerts": [],
        }
        mock_analytics_service.get_system_health = AsyncMock(return_value=mock_health)

        result = await get_system_health(
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.status == "healthy"
        assert result.health_score == 95.0
        assert result.total_repositories == 10
        assert result.oauth_connections == 2

    @pytest.mark.asyncio
    async def test_get_system_health_degraded(self, mock_user, mock_analytics_service):
        """Test system health with degraded status."""
        from app.api.v2.analytics import get_system_health

        mock_db = Mock()

        mock_health = {
            "status": "degraded",
            "health_score": 65.0,
            "total_repositories": 10,
            "active_repositories": 8,
            "total_workflows_tracked": 500,
            "total_incidents": 100,
            "open_incidents": 25,
            "total_prs_created": 30,
            "oauth_connections": 2,
            "webhook_health": {
                "active_webhooks": 8,
                "failed_webhooks": 2,
            },
            "last_24h_activity": {
                "workflows": 25,
                "incidents": 10,
                "prs": 1,
            },
            "alerts": ["High number of open incidents"],
        }
        mock_analytics_service.get_system_health = AsyncMock(return_value=mock_health)

        result = await get_system_health(
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.status == "degraded"
        assert result.health_score == 65.0
        assert result.open_incidents == 25
        assert len(result.alerts) == 1

    @pytest.mark.asyncio
    async def test_get_dashboard_summary_success(self, mock_user, mock_analytics_service):
        """Test getting dashboard summary."""
        from app.api.v2.analytics import get_dashboard_summary

        mock_db = Mock()

        # Mock all required service calls
        mock_analytics_service.get_system_health = AsyncMock(return_value={
            "status": "healthy",
            "health_score": 90.0,
            "total_repositories": 5,
            "active_repositories": 5,
            "total_workflows_tracked": 200,
            "total_incidents": 20,
            "open_incidents": 2,
            "total_prs_created": 15,
            "oauth_connections": 2,
            "webhook_health": {"active_webhooks": 5, "failed_webhooks": 0},
            "last_24h_activity": {"workflows": 10, "incidents": 1, "prs": 0},
            "alerts": [],
        })

        mock_analytics_service.get_workflow_trends = AsyncMock(return_value={
            "period": "day",
            "total_runs": [],
            "successful_runs": [],
            "failed_runs": [],
            "failure_rate": [],
            "avg_duration": [],
            "summary": {
                "total_runs": 100,
                "successful_runs": 90,
                "failed_runs": 10,
                "failure_rate": 10.0,
                "success_rate": 90.0,
            },
        })

        mock_analytics_service.get_incident_trends = AsyncMock(return_value={
            "period": "day",
            "incidents_created": [],
            "incidents_resolved": [],
            "open_incidents": [],
            "avg_resolution_time": [],
            "by_severity": {},
            "by_source": {},
            "summary": {
                "total_incidents": 20,
                "resolved_incidents": 18,
                "open_incidents": 2,
                "resolution_rate": 90.0,
            },
        })

        mock_analytics_service.get_repository_health_metrics = AsyncMock(return_value=[
            {
                "repository_full_name": "owner/repo1",
                "health_score": 95.0,
                "total_workflows": 100,
                "successful_workflows": 95,
                "failed_workflows": 5,
                "failure_rate": 5.0,
                "total_incidents": 5,
                "open_incidents": 0,
                "resolved_incidents": 5,
                "prs_created": 3,
                "prs_merged": 3,
                "pr_merge_rate": 100.0,
                "avg_resolution_time_hours": None,
                "last_failure": None,
                "last_success": None,
            },
        ])

        result = await get_dashboard_summary(
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.system_health.status == "healthy"
        assert result.workflow_stats["total_runs"] == 100
        assert result.incident_stats["total_incidents"] == 20
        assert len(result.top_repositories) == 1

    @pytest.mark.asyncio
    async def test_get_workflow_trends_error_handling(self, mock_user, mock_analytics_service):
        """Test error handling in workflow trends endpoint."""
        from app.api.v2.analytics import get_workflow_trends
        from fastapi import HTTPException

        mock_db = Mock()

        # Mock service to raise exception
        mock_analytics_service.get_workflow_trends = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_workflow_trends(
                days=30,
                period="day",
                repository_connection_id=None,
                db=mock_db,
                current_user_data={"user": mock_user},
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to fetch workflow trends" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_repository_health_empty(self, mock_user, mock_analytics_service):
        """Test repository health with no repositories."""
        from app.api.v2.analytics import get_repository_health

        mock_db = Mock()

        mock_analytics_service.get_repository_health_metrics = AsyncMock(return_value=[])

        result = await get_repository_health(
            repository_connection_id=None,
            db=mock_db,
            current_user_data={"user": mock_user},
        )

        assert result.total_repositories == 0
        assert result.avg_health_score == 0.0
        assert len(result.repositories) == 0
