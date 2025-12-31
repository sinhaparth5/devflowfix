# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Analytics Schemas

Pydantic models for analytics, metrics, and dashboard data.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field


class TimeSeriesDataPoint(BaseModel):
    """Single data point in time series."""

    timestamp: datetime = Field(..., description="Data point timestamp")
    value: float = Field(..., description="Metric value")
    label: Optional[str] = Field(None, description="Optional label")


class WorkflowTrendResponse(BaseModel):
    """Workflow success/failure trends over time."""

    period: str = Field(..., description="Time period (day, week, month)")
    total_runs: List[TimeSeriesDataPoint] = Field(..., description="Total workflow runs over time")
    successful_runs: List[TimeSeriesDataPoint] = Field(..., description="Successful runs over time")
    failed_runs: List[TimeSeriesDataPoint] = Field(..., description="Failed runs over time")
    failure_rate: List[TimeSeriesDataPoint] = Field(..., description="Failure rate percentage over time")
    avg_duration: List[TimeSeriesDataPoint] = Field(..., description="Average run duration over time")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class RepositoryHealthMetrics(BaseModel):
    """Health metrics for a repository."""

    repository_full_name: str = Field(..., description="Repository full name")
    total_workflows: int = Field(..., description="Total workflow runs")
    successful_workflows: int = Field(..., description="Successful runs")
    failed_workflows: int = Field(..., description="Failed runs")
    failure_rate: float = Field(..., description="Failure rate percentage")
    total_incidents: int = Field(..., description="Total incidents")
    open_incidents: int = Field(..., description="Open incidents")
    resolved_incidents: int = Field(..., description="Resolved incidents")
    prs_created: int = Field(..., description="PRs created by DevFlowFix")
    prs_merged: int = Field(..., description="PRs merged")
    pr_merge_rate: float = Field(..., description="PR merge rate percentage")
    avg_resolution_time_hours: Optional[float] = Field(None, description="Average time to resolve incidents")
    health_score: float = Field(..., description="Overall health score (0-100)")
    last_failure: Optional[datetime] = Field(None, description="Last failure timestamp")
    last_success: Optional[datetime] = Field(None, description="Last success timestamp")


class RepositoryHealthListResponse(BaseModel):
    """List of repository health metrics."""

    repositories: List[RepositoryHealthMetrics] = Field(..., description="Repository health metrics")
    total_repositories: int = Field(..., description="Total repositories monitored")
    avg_health_score: float = Field(..., description="Average health score across all repos")


class IncidentTrendResponse(BaseModel):
    """Incident creation and resolution trends."""

    period: str = Field(..., description="Time period")
    incidents_created: List[TimeSeriesDataPoint] = Field(..., description="Incidents created over time")
    incidents_resolved: List[TimeSeriesDataPoint] = Field(..., description="Incidents resolved over time")
    open_incidents: List[TimeSeriesDataPoint] = Field(..., description="Open incidents over time")
    avg_resolution_time: List[TimeSeriesDataPoint] = Field(..., description="Average resolution time over time")
    by_severity: Dict[str, List[TimeSeriesDataPoint]] = Field(..., description="Incidents by severity")
    by_source: Dict[str, int] = Field(..., description="Incidents by source")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class PREffectivenessResponse(BaseModel):
    """PR effectiveness and success metrics."""

    period: str = Field(..., description="Time period")
    prs_created: List[TimeSeriesDataPoint] = Field(..., description="PRs created over time")
    prs_merged: List[TimeSeriesDataPoint] = Field(..., description="PRs merged over time")
    prs_closed: List[TimeSeriesDataPoint] = Field(..., description="PRs closed without merge over time")
    merge_rate: List[TimeSeriesDataPoint] = Field(..., description="Merge rate over time")
    avg_time_to_merge: List[TimeSeriesDataPoint] = Field(..., description="Average time to merge over time")
    by_fix_type: Dict[str, int] = Field(..., description="PRs by fix type")
    success_rate: float = Field(..., description="Overall success rate")
    total_incidents_fixed: int = Field(..., description="Total incidents auto-fixed")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class FailureTypeDistribution(BaseModel):
    """Distribution of failure types."""

    failure_type: str = Field(..., description="Type of failure")
    count: int = Field(..., description="Number of occurrences")
    percentage: float = Field(..., description="Percentage of total failures")
    avg_resolution_time_hours: Optional[float] = Field(None, description="Average resolution time")
    auto_fix_rate: float = Field(..., description="Percentage auto-fixed")


class FailureAnalysisResponse(BaseModel):
    """Analysis of failure patterns."""

    total_failures: int = Field(..., description="Total failures analyzed")
    failure_types: List[FailureTypeDistribution] = Field(..., description="Failure type distribution")
    most_common_errors: List[Dict[str, Any]] = Field(..., description="Most common error messages")
    failure_by_repository: List[Dict[str, Any]] = Field(..., description="Failures by repository")
    failure_by_workflow: List[Dict[str, Any]] = Field(..., description="Failures by workflow")
    time_of_day_distribution: List[Dict[str, Any]] = Field(..., description="Failures by time of day")


class DeveloperProductivityMetrics(BaseModel):
    """Developer productivity metrics."""

    total_incidents: int = Field(..., description="Total incidents")
    auto_fixed_incidents: int = Field(..., description="Incidents auto-fixed by DevFlowFix")
    manual_fixes: int = Field(..., description="Incidents requiring manual intervention")
    automation_rate: float = Field(..., description="Automation rate percentage")
    time_saved_hours: float = Field(..., description="Estimated developer hours saved")
    avg_manual_fix_time_hours: float = Field(..., description="Average time for manual fixes")
    avg_auto_fix_time_hours: float = Field(..., description="Average time for auto fixes")
    productivity_gain_percentage: float = Field(..., description="Productivity improvement percentage")


class SystemHealthResponse(BaseModel):
    """Overall system health and status."""

    status: str = Field(..., description="System status (healthy, degraded, unhealthy)")
    health_score: float = Field(..., description="Overall health score (0-100)")
    total_repositories: int = Field(..., description="Total repositories monitored")
    active_repositories: int = Field(..., description="Active repositories")
    total_workflows_tracked: int = Field(..., description="Total workflow runs tracked")
    total_incidents: int = Field(..., description="Total incidents")
    open_incidents: int = Field(..., description="Open incidents")
    total_prs_created: int = Field(..., description="Total PRs created")
    oauth_connections: int = Field(..., description="Active OAuth connections")
    webhook_health: Dict[str, Any] = Field(..., description="Webhook health metrics")
    last_24h_activity: Dict[str, int] = Field(..., description="Activity in last 24 hours")
    alerts: List[str] = Field(default=[], description="System alerts")


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary with key metrics."""

    system_health: SystemHealthResponse = Field(..., description="System health")
    workflow_stats: Dict[str, Any] = Field(..., description="Workflow statistics")
    incident_stats: Dict[str, Any] = Field(..., description="Incident statistics")
    pr_stats: Dict[str, Any] = Field(..., description="PR statistics")
    top_repositories: List[RepositoryHealthMetrics] = Field(..., description="Top repositories by activity")
    recent_failures: List[Dict[str, Any]] = Field(..., description="Recent failures")
    recent_fixes: List[Dict[str, Any]] = Field(..., description="Recent auto-fixes")
    generated_at: datetime = Field(..., description="Dashboard generation timestamp")


class TimeRangeQuery(BaseModel):
    """Time range for analytics queries."""

    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")
    period: str = Field(
        default="week",
        description="Aggregation period (hour, day, week, month)"
    )
    timezone: str = Field(default="UTC", description="Timezone for date calculations")


class AnalyticsFilterRequest(BaseModel):
    """Filter criteria for analytics queries."""

    time_range: TimeRangeQuery = Field(..., description="Time range")
    repository_ids: Optional[List[str]] = Field(None, description="Filter by repositories")
    workflow_names: Optional[List[str]] = Field(None, description="Filter by workflow names")
    severity_levels: Optional[List[str]] = Field(None, description="Filter by incident severity")
    sources: Optional[List[str]] = Field(None, description="Filter by incident source")
    include_resolved: bool = Field(default=True, description="Include resolved incidents")
    include_open: bool = Field(default=True, description="Include open incidents")


class MetricComparisonResponse(BaseModel):
    """Comparison of metrics between time periods."""

    metric_name: str = Field(..., description="Metric being compared")
    current_period: Dict[str, Any] = Field(..., description="Current period metrics")
    previous_period: Dict[str, Any] = Field(..., description="Previous period metrics")
    change_percentage: float = Field(..., description="Percentage change")
    change_direction: str = Field(..., description="Direction of change (up, down, stable)")
    is_improvement: bool = Field(..., description="Whether change is improvement")


class AlertThreshold(BaseModel):
    """Alert threshold configuration."""

    metric: str = Field(..., description="Metric to monitor")
    threshold_value: float = Field(..., description="Threshold value")
    condition: str = Field(..., description="Condition (above, below, equals)")
    severity: str = Field(..., description="Alert severity")
    enabled: bool = Field(default=True, description="Whether alert is enabled")


class AnalyticsAlert(BaseModel):
    """Analytics alert."""

    alert_id: str = Field(..., description="Alert ID")
    metric: str = Field(..., description="Metric that triggered alert")
    current_value: float = Field(..., description="Current metric value")
    threshold_value: float = Field(..., description="Threshold that was crossed")
    severity: str = Field(..., description="Alert severity")
    message: str = Field(..., description="Alert message")
    triggered_at: datetime = Field(..., description="When alert was triggered")
    acknowledged: bool = Field(default=False, description="Whether alert was acknowledged")
