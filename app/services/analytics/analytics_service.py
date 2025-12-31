# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Analytics Service

Provides data aggregation and analysis for metrics and dashboards.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
import structlog

from app.adapters.database.postgres.models import (
    WorkflowRunTable,
    IncidentTable,
    RepositoryConnectionTable,
    OAuthConnectionTable,
)
from app.core.schemas.analytics import TimeSeriesDataPoint

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """
    Provides analytics and metrics aggregation.

    Responsibilities:
    - Calculate workflow trends and statistics
    - Analyze incident patterns and resolution
    - Track PR effectiveness
    - Compute repository health scores
    - Generate dashboard summaries
    """

    def calculate_health_score(
        self,
        total_runs: int,
        failed_runs: int,
        open_incidents: int,
        pr_merge_rate: float,
    ) -> float:
        """
        Calculate repository health score (0-100).

        Args:
            total_runs: Total workflow runs
            failed_runs: Failed workflow runs
            open_incidents: Number of open incidents
            pr_merge_rate: PR merge rate percentage

        Returns:
            Health score from 0-100
        """
        if total_runs == 0:
            return 100.0  # No runs = no problems

        # Calculate components (each worth 25 points)
        failure_score = max(0, 25 - (failed_runs / total_runs * 100) * 0.25)
        incident_score = max(0, 25 - (open_incidents * 5))
        pr_score = pr_merge_rate * 0.25
        activity_score = min(25, total_runs / 10)  # More activity = better

        health_score = failure_score + incident_score + pr_score + activity_score
        return min(100.0, max(0.0, health_score))

    async def get_workflow_trends(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        period: str = "day",
        repository_connection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get workflow success/failure trends over time.

        Args:
            db: Database session
            user_id: User ID
            start_date: Start of time range
            end_date: End of time range
            period: Aggregation period (hour, day, week, month)
            repository_connection_id: Optional repository filter

        Returns:
            Workflow trend data with time series
        """
        # Build query
        query = (
            db.query(WorkflowRunTable)
            .join(
                RepositoryConnectionTable,
                WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
            )
            .filter(
                RepositoryConnectionTable.user_id == user_id,
                WorkflowRunTable.created_at >= start_date,
                WorkflowRunTable.created_at <= end_date,
            )
        )

        if repository_connection_id:
            query = query.filter(
                WorkflowRunTable.repository_connection_id == repository_connection_id
            )

        runs = query.all()

        # Group by time period
        time_series = self._group_by_period(runs, start_date, end_date, period)

        # Calculate metrics for each period
        total_runs = []
        successful_runs = []
        failed_runs = []
        failure_rate = []
        avg_duration = []

        for period_start, period_runs in time_series.items():
            total = len(period_runs)
            successful = len([r for r in period_runs if r.conclusion == "success"])
            failed = len([r for r in period_runs if r.conclusion == "failure"])

            total_runs.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=float(total),
            ))
            successful_runs.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=float(successful),
            ))
            failed_runs.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=float(failed),
            ))
            failure_rate.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=(failed / total * 100) if total > 0 else 0.0,
            ))

            # Calculate average duration
            durations = [
                (r.completed_at - r.started_at).total_seconds()
                for r in period_runs
                if r.started_at and r.completed_at
            ]
            avg_duration.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=sum(durations) / len(durations) if durations else 0.0,
            ))

        # Calculate summary
        total_all = len(runs)
        successful_all = len([r for r in runs if r.conclusion == "success"])
        failed_all = len([r for r in runs if r.conclusion == "failure"])

        summary = {
            "total_runs": total_all,
            "successful_runs": successful_all,
            "failed_runs": failed_all,
            "failure_rate": (failed_all / total_all * 100) if total_all > 0 else 0.0,
            "success_rate": (successful_all / total_all * 100) if total_all > 0 else 0.0,
        }

        return {
            "period": period,
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "failure_rate": failure_rate,
            "avg_duration": avg_duration,
            "summary": summary,
        }

    async def get_repository_health_metrics(
        self,
        db: Session,
        user_id: str,
        repository_connection_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get health metrics for repositories.

        Args:
            db: Database session
            user_id: User ID
            repository_connection_id: Optional filter for specific repository

        Returns:
            List of repository health metrics
        """
        # Get repository connections
        query = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.user_id == user_id,
            RepositoryConnectionTable.is_enabled == True,
        )

        if repository_connection_id:
            query = query.filter(RepositoryConnectionTable.id == repository_connection_id)

        repos = query.all()

        health_metrics = []

        for repo in repos:
            # Get workflow runs
            workflows = db.query(WorkflowRunTable).filter(
                WorkflowRunTable.repository_connection_id == repo.id
            ).all()

            total_workflows = len(workflows)
            successful_workflows = len([w for w in workflows if w.conclusion == "success"])
            failed_workflows = len([w for w in workflows if w.conclusion == "failure"])
            failure_rate = (failed_workflows / total_workflows * 100) if total_workflows > 0 else 0.0

            # Get incidents
            incidents = db.query(IncidentTable).filter(
                IncidentTable.repository == repo.repository_full_name,
                IncidentTable.user_id == user_id,
            ).all()

            total_incidents = len(incidents)
            open_incidents = len([i for i in incidents if i.status in ["open", "in_progress"]])
            resolved_incidents = len([i for i in incidents if i.status == "resolved"])

            # Get PR stats from incident metadata
            prs_created = 0
            prs_merged = 0

            for incident in incidents:
                if incident.metadata and "prs" in incident.metadata:
                    prs_created += len(incident.metadata["prs"])
                    # Would need to fetch actual PR status to count merged

            pr_merge_rate = (prs_merged / prs_created * 100) if prs_created > 0 else 0.0

            # Calculate health score
            health_score = self.calculate_health_score(
                total_runs=total_workflows,
                failed_runs=failed_workflows,
                open_incidents=open_incidents,
                pr_merge_rate=pr_merge_rate,
            )

            # Get last failure and success
            last_failure = None
            last_success = None

            failed_runs = [w for w in workflows if w.conclusion == "failure"]
            if failed_runs:
                last_failure = max(w.created_at for w in failed_runs)

            successful_runs = [w for w in workflows if w.conclusion == "success"]
            if successful_runs:
                last_success = max(w.created_at for w in successful_runs)

            health_metrics.append({
                "repository_full_name": repo.repository_full_name,
                "total_workflows": total_workflows,
                "successful_workflows": successful_workflows,
                "failed_workflows": failed_workflows,
                "failure_rate": failure_rate,
                "total_incidents": total_incidents,
                "open_incidents": open_incidents,
                "resolved_incidents": resolved_incidents,
                "prs_created": prs_created,
                "prs_merged": prs_merged,
                "pr_merge_rate": pr_merge_rate,
                "avg_resolution_time_hours": None,  # Would need to track resolution times
                "health_score": health_score,
                "last_failure": last_failure,
                "last_success": last_success,
            })

        return health_metrics

    async def get_incident_trends(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        period: str = "day",
    ) -> Dict[str, Any]:
        """
        Get incident creation and resolution trends.

        Args:
            db: Database session
            user_id: User ID
            start_date: Start of time range
            end_date: End of time range
            period: Aggregation period

        Returns:
            Incident trend data
        """
        # Get incidents in time range
        incidents = db.query(IncidentTable).filter(
            IncidentTable.user_id == user_id,
            IncidentTable.created_at >= start_date,
            IncidentTable.created_at <= end_date,
        ).all()

        # Group by time period
        time_series = self._group_by_period(incidents, start_date, end_date, period)

        incidents_created = []
        incidents_resolved = []
        open_incidents_series = []

        cumulative_open = 0

        for period_start, period_incidents in time_series.items():
            created = len(period_incidents)
            resolved = len([i for i in period_incidents if i.status == "resolved"])

            cumulative_open += (created - resolved)

            incidents_created.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=float(created),
            ))
            incidents_resolved.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=float(resolved),
            ))
            open_incidents_series.append(TimeSeriesDataPoint(
                timestamp=period_start,
                value=float(max(0, cumulative_open)),
            ))

        # Calculate by severity
        by_severity = {}
        for severity in ["critical", "high", "medium", "low"]:
            severity_incidents = [i for i in incidents if i.severity == severity]
            by_severity[severity] = [
                TimeSeriesDataPoint(
                    timestamp=period_start,
                    value=float(len([i for i in period_incidents if i.severity == severity])),
                )
                for period_start, period_incidents in time_series.items()
            ]

        # Calculate by source
        by_source = {}
        sources = set(i.source for i in incidents if i.source)
        for source in sources:
            by_source[source] = len([i for i in incidents if i.source == source])

        summary = {
            "total_incidents": len(incidents),
            "resolved_incidents": len([i for i in incidents if i.status == "resolved"]),
            "open_incidents": len([i for i in incidents if i.status in ["open", "in_progress"]]),
            "resolution_rate": (len([i for i in incidents if i.status == "resolved"]) / len(incidents) * 100) if incidents else 0.0,
        }

        return {
            "period": period,
            "incidents_created": incidents_created,
            "incidents_resolved": incidents_resolved,
            "open_incidents": open_incidents_series,
            "avg_resolution_time": [],  # Would need to track resolution times
            "by_severity": by_severity,
            "by_source": by_source,
            "summary": summary,
        }

    async def get_system_health(
        self,
        db: Session,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Get overall system health and status.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            System health metrics
        """
        # Count active resources
        total_repositories = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.user_id == user_id,
        ).count()

        active_repositories = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.user_id == user_id,
            RepositoryConnectionTable.is_enabled == True,
        ).count()

        total_workflows = db.query(WorkflowRunTable).join(
            RepositoryConnectionTable,
            WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
        ).filter(
            RepositoryConnectionTable.user_id == user_id,
        ).count()

        total_incidents = db.query(IncidentTable).filter(
            IncidentTable.user_id == user_id,
        ).count()

        open_incidents = db.query(IncidentTable).filter(
            IncidentTable.user_id == user_id,
            IncidentTable.status.in_(["open", "in_progress"]),
        ).count()

        oauth_connections = db.query(OAuthConnectionTable).filter(
            OAuthConnectionTable.user_id == user_id,
            OAuthConnectionTable.is_active == True,
        ).count()

        # Calculate health score
        health_score = 100.0
        if open_incidents > 10:
            health_score -= (open_incidents - 10) * 2
        if active_repositories == 0:
            health_score -= 20

        health_score = max(0.0, min(100.0, health_score))

        # Determine status
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "degraded"
        else:
            status = "unhealthy"

        # Get last 24h activity
        last_24h = datetime.now(timezone.utc) - timedelta(hours=24)

        workflows_24h = db.query(WorkflowRunTable).join(
            RepositoryConnectionTable,
            WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
        ).filter(
            RepositoryConnectionTable.user_id == user_id,
            WorkflowRunTable.created_at >= last_24h,
        ).count()

        incidents_24h = db.query(IncidentTable).filter(
            IncidentTable.user_id == user_id,
            IncidentTable.created_at >= last_24h,
        ).count()

        return {
            "status": status,
            "health_score": health_score,
            "total_repositories": total_repositories,
            "active_repositories": active_repositories,
            "total_workflows_tracked": total_workflows,
            "total_incidents": total_incidents,
            "open_incidents": open_incidents,
            "total_prs_created": 0,  # Would aggregate from incidents
            "oauth_connections": oauth_connections,
            "webhook_health": {
                "active_webhooks": active_repositories,  # Simplified
                "failed_webhooks": 0,
            },
            "last_24h_activity": {
                "workflows": workflows_24h,
                "incidents": incidents_24h,
                "prs": 0,
            },
            "alerts": [],
        }

    def _group_by_period(
        self,
        items: List[Any],
        start_date: datetime,
        end_date: datetime,
        period: str,
    ) -> Dict[datetime, List[Any]]:
        """
        Group items by time period.

        Args:
            items: Items to group
            start_date: Start date
            end_date: End date
            period: Period (hour, day, week, month)

        Returns:
            Dictionary mapping period start to items in that period
        """
        # Determine period delta
        if period == "hour":
            delta = timedelta(hours=1)
        elif period == "day":
            delta = timedelta(days=1)
        elif period == "week":
            delta = timedelta(weeks=1)
        elif period == "month":
            delta = timedelta(days=30)
        else:
            delta = timedelta(days=1)

        # Create buckets
        buckets = {}
        current = start_date
        while current <= end_date:
            buckets[current] = []
            current += delta

        # Assign items to buckets
        for item in items:
            item_date = item.created_at
            # Find appropriate bucket
            for bucket_start in sorted(buckets.keys()):
                bucket_end = bucket_start + delta
                if bucket_start <= item_date < bucket_end:
                    buckets[bucket_start].append(item)
                    break

        return buckets
