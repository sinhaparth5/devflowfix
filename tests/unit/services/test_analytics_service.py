# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Unit tests for Analytics Service.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta, timezone
import uuid

from app.services.analytics.analytics_service import AnalyticsService
from app.adapters.database.postgres.models import (
    WorkflowRunTable,
    IncidentTable,
    RepositoryConnectionTable,
)


class TestAnalyticsService:
    """Test suite for AnalyticsService."""

    @pytest.fixture
    def service(self):
        """Create AnalyticsService instance for testing."""
        return AnalyticsService()

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.query = Mock()
        return db

    def test_calculate_health_score_perfect(self, service):
        """Test health score calculation with perfect metrics."""
        score = service.calculate_health_score(
            total_runs=100,
            failed_runs=0,
            open_incidents=0,
            pr_merge_rate=100.0,
        )
        assert score == 100.0

    def test_calculate_health_score_no_runs(self, service):
        """Test health score with no runs."""
        score = service.calculate_health_score(
            total_runs=0,
            failed_runs=0,
            open_incidents=0,
            pr_merge_rate=0.0,
        )
        assert score == 100.0

    def test_calculate_health_score_high_failure_rate(self, service):
        """Test health score with high failure rate."""
        score = service.calculate_health_score(
            total_runs=100,
            failed_runs=50,  # 50% failure rate
            open_incidents=0,
            pr_merge_rate=100.0,
        )
        assert score < 100.0
        assert score > 0.0

    def test_calculate_health_score_many_incidents(self, service):
        """Test health score with many open incidents."""
        score = service.calculate_health_score(
            total_runs=100,
            failed_runs=0,
            open_incidents=10,
            pr_merge_rate=100.0,
        )
        assert score < 100.0

    def test_calculate_health_score_bounds(self, service):
        """Test health score is always between 0 and 100."""
        # Test minimum bound
        score_min = service.calculate_health_score(
            total_runs=100,
            failed_runs=100,
            open_incidents=100,
            pr_merge_rate=0.0,
        )
        assert score_min >= 0.0
        assert score_min <= 100.0

        # Test maximum bound
        score_max = service.calculate_health_score(
            total_runs=1000,
            failed_runs=0,
            open_incidents=0,
            pr_merge_rate=100.0,
        )
        assert score_max >= 0.0
        assert score_max <= 100.0

    @pytest.mark.asyncio
    async def test_get_workflow_trends_basic(self, service, mock_db):
        """Test getting workflow trends."""
        # Mock workflow runs
        now = datetime.now(timezone.utc)
        mock_runs = [
            Mock(
                conclusion="success",
                created_at=now - timedelta(days=1),
                started_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1, hours=-1),
            ),
            Mock(
                conclusion="failure",
                created_at=now - timedelta(days=2),
                started_at=now - timedelta(days=2),
                completed_at=now - timedelta(days=2, hours=-1),
            ),
        ]

        # Mock database query
        mock_query = Mock()
        mock_query.join.return_value.filter.return_value.all.return_value = mock_runs
        mock_db.query.return_value = mock_query

        start_date = now - timedelta(days=7)
        end_date = now

        trends = await service.get_workflow_trends(
            db=mock_db,
            user_id="test_user",
            start_date=start_date,
            end_date=end_date,
            period="day",
        )

        assert "total_runs" in trends
        assert "successful_runs" in trends
        assert "failed_runs" in trends
        assert "summary" in trends
        assert trends["summary"]["total_runs"] == 2
        assert trends["summary"]["successful_runs"] == 1
        assert trends["summary"]["failed_runs"] == 1

    @pytest.mark.asyncio
    async def test_get_repository_health_metrics(self, service, mock_db):
        """Test getting repository health metrics."""
        # Mock repository connections
        mock_repos = [
            Mock(
                id="repo1",
                repository_full_name="owner/repo1",
            ),
        ]

        # Mock workflow runs
        mock_workflows = [
            Mock(conclusion="success"),
            Mock(conclusion="failure"),
        ]

        # Mock incidents
        mock_incidents = [
            Mock(
                status="open",
                metadata={},
            ),
        ]

        # Setup query mocks
        def query_side_effect(model):
            mock_query = Mock()
            if model == RepositoryConnectionTable:
                mock_query.filter.return_value.all.return_value = mock_repos
            elif model == WorkflowRunTable:
                mock_query.filter.return_value.all.return_value = mock_workflows
            elif model == IncidentTable:
                mock_query.filter.return_value.all.return_value = mock_incidents
            return mock_query

        mock_db.query.side_effect = query_side_effect

        metrics = await service.get_repository_health_metrics(
            db=mock_db,
            user_id="test_user",
        )

        assert len(metrics) == 1
        assert metrics[0]["repository_full_name"] == "owner/repo1"
        assert metrics[0]["total_workflows"] == 2
        assert metrics[0]["successful_workflows"] == 1
        assert metrics[0]["failed_workflows"] == 1
        assert metrics[0]["total_incidents"] == 1

    @pytest.mark.asyncio
    async def test_get_incident_trends(self, service, mock_db):
        """Test getting incident trends."""
        now = datetime.now(timezone.utc)
        mock_incidents = [
            Mock(
                status="resolved",
                severity="high",
                source="github",
                created_at=now - timedelta(days=1),
            ),
            Mock(
                status="open",
                severity="medium",
                source="gitlab",
                created_at=now - timedelta(days=2),
            ),
        ]

        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = mock_incidents
        mock_db.query.return_value = mock_query

        start_date = now - timedelta(days=7)
        end_date = now

        trends = await service.get_incident_trends(
            db=mock_db,
            user_id="test_user",
            start_date=start_date,
            end_date=end_date,
            period="day",
        )

        assert "incidents_created" in trends
        assert "incidents_resolved" in trends
        assert "summary" in trends
        assert trends["summary"]["total_incidents"] == 2
        assert trends["summary"]["resolved_incidents"] == 1
        assert trends["summary"]["open_incidents"] == 1

    @pytest.mark.asyncio
    async def test_get_system_health(self, service, mock_db):
        """Test getting system health."""
        # Mock counts
        mock_count_query = Mock()
        mock_count_query.filter.return_value.count.return_value = 5
        mock_count_query.join.return_value.filter.return_value.count.return_value = 10
        mock_db.query.return_value = mock_count_query

        health = await service.get_system_health(
            db=mock_db,
            user_id="test_user",
        )

        assert "status" in health
        assert "health_score" in health
        assert "total_repositories" in health
        assert "active_repositories" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        assert 0.0 <= health["health_score"] <= 100.0

    def test_group_by_period_day(self, service):
        """Test grouping items by day."""
        now = datetime.now(timezone.utc)
        items = [
            Mock(created_at=now),
            Mock(created_at=now - timedelta(days=1)),
            Mock(created_at=now - timedelta(days=2)),
        ]

        start_date = now - timedelta(days=7)
        end_date = now

        buckets = service._group_by_period(
            items=items,
            start_date=start_date,
            end_date=end_date,
            period="day",
        )

        # Should have 8 buckets (7 days + 1)
        assert len(buckets) >= 1

        # Check that items are in buckets
        total_items = sum(len(bucket) for bucket in buckets.values())
        assert total_items == 3

    def test_group_by_period_week(self, service):
        """Test grouping items by week."""
        now = datetime.now(timezone.utc)
        items = [
            Mock(created_at=now),
            Mock(created_at=now - timedelta(weeks=1)),
        ]

        start_date = now - timedelta(weeks=4)
        end_date = now

        buckets = service._group_by_period(
            items=items,
            start_date=start_date,
            end_date=end_date,
            period="week",
        )

        assert len(buckets) >= 1
        total_items = sum(len(bucket) for bucket in buckets.values())
        assert total_items == 2

    def test_group_by_period_month(self, service):
        """Test grouping items by month."""
        now = datetime.now(timezone.utc)
        items = [
            Mock(created_at=now),
        ]

        start_date = now - timedelta(days=60)
        end_date = now

        buckets = service._group_by_period(
            items=items,
            start_date=start_date,
            end_date=end_date,
            period="month",
        )

        assert len(buckets) >= 1

    def test_group_by_period_hour(self, service):
        """Test grouping items by hour."""
        now = datetime.now(timezone.utc)
        items = [
            Mock(created_at=now),
            Mock(created_at=now - timedelta(hours=1)),
            Mock(created_at=now - timedelta(hours=2)),
        ]

        start_date = now - timedelta(hours=5)
        end_date = now

        buckets = service._group_by_period(
            items=items,
            start_date=start_date,
            end_date=end_date,
            period="hour",
        )

        assert len(buckets) >= 1
        total_items = sum(len(bucket) for bucket in buckets.values())
        assert total_items == 3

    def test_group_by_period_empty_items(self, service):
        """Test grouping with no items."""
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=7)
        end_date = now

        buckets = service._group_by_period(
            items=[],
            start_date=start_date,
            end_date=end_date,
            period="day",
        )

        # Should still create buckets, just empty
        assert len(buckets) >= 1
        assert all(len(bucket) == 0 for bucket in buckets.values())
