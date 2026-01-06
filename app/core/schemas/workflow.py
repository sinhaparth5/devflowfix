# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Workflow Event Schemas

Pydantic models for GitHub workflow run events and tracking.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class WorkflowRunResponse(BaseModel):
    """Workflow run information."""

    id: str = Field(..., description="Workflow run tracking ID")
    incident_id: Optional[str] = Field(None, description="Associated incident ID")
    repository_connection_id: str = Field(..., description="Repository connection ID")
    run_id: str = Field(..., description="GitHub workflow run ID")
    run_number: int = Field(..., description="Run number")
    workflow_name: str = Field(..., description="Workflow name")
    workflow_id: str = Field(..., description="GitHub workflow ID")
    status: str = Field(..., description="Run status (queued, in_progress, completed)")
    conclusion: Optional[str] = Field(None, description="Run conclusion (success, failure, cancelled, etc.)")
    branch: str = Field(..., description="Branch name")
    commit_sha: str = Field(..., description="Commit SHA")
    commit_message: Optional[str] = Field(None, description="Commit message")
    author: Optional[str] = Field(None, description="Commit author")
    started_at: Optional[datetime] = Field(None, description="Run start time")
    completed_at: Optional[datetime] = Field(None, description="Run completion time")
    run_url: Optional[str] = Field(None, description="GitHub run URL")
    created_at: datetime = Field(..., description="Tracking record creation time")
    updated_at: datetime = Field(..., description="Tracking record update time")

    class Config:
        from_attributes = True


class WorkflowRunListResponse(BaseModel):
    """List of workflow runs."""

    runs: List[WorkflowRunResponse] = Field(..., description="List of workflow runs")
    total: int = Field(..., description="Total number of runs")
    failed_runs: int = Field(default=0, description="Number of failed runs")
    successful_runs: int = Field(default=0, description="Number of successful runs")


class WorkflowRunStatsResponse(BaseModel):
    """Workflow run statistics."""

    total_runs: int = Field(..., description="Total workflow runs")
    failed_runs: int = Field(..., description="Failed workflow runs")
    successful_runs: int = Field(..., description="Successful workflow runs")
    in_progress_runs: int = Field(..., description="Currently running workflows")
    avg_duration_seconds: Optional[float] = Field(None, description="Average run duration")
    failure_rate: float = Field(..., description="Failure rate percentage")
    repositories_tracked: int = Field(..., description="Number of repositories tracked")


class GitHubWorkflowRunEvent(BaseModel):
    """GitHub workflow_run event payload."""

    action: str = Field(..., description="Event action (completed, requested, in_progress)")
    workflow_run: Dict[str, Any] = Field(..., description="Workflow run object")
    repository: Dict[str, Any] = Field(..., description="Repository object")
    sender: Dict[str, Any] = Field(..., description="User who triggered the event")

    class Config:
        extra = "allow"


class WorkflowJobEvent(BaseModel):
    """GitHub workflow_job event payload."""

    action: str = Field(..., description="Event action (queued, in_progress, completed)")
    workflow_job: Dict[str, Any] = Field(..., description="Workflow job object")
    repository: Dict[str, Any] = Field(..., description="Repository object")

    class Config:
        extra = "allow"


class WorkflowRunDetails(BaseModel):
    """Detailed workflow run information from GitHub API."""

    id: int = Field(..., description="GitHub run ID")
    name: str = Field(..., description="Workflow name")
    node_id: str = Field(..., description="GraphQL node ID")
    head_branch: str = Field(..., description="Head branch")
    head_sha: str = Field(..., description="Head commit SHA")
    path: str = Field(..., description="Workflow file path")
    display_title: str = Field(..., description="Display title")
    run_number: int = Field(..., description="Run number")
    event: str = Field(..., description="Triggering event")
    status: str = Field(..., description="Run status")
    conclusion: Optional[str] = Field(None, description="Run conclusion")
    workflow_id: int = Field(..., description="Workflow ID")
    check_suite_id: int = Field(..., description="Check suite ID")
    check_suite_node_id: str = Field(..., description="Check suite node ID")
    url: str = Field(..., description="API URL")
    html_url: str = Field(..., description="Web URL")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")
    run_attempt: int = Field(..., description="Run attempt number")
    run_started_at: Optional[datetime] = Field(None, description="Run start time")
    jobs_url: str = Field(..., description="Jobs API URL")
    logs_url: str = Field(..., description="Logs API URL")
    check_suite_url: str = Field(..., description="Check suite API URL")
    artifacts_url: str = Field(..., description="Artifacts API URL")
    cancel_url: str = Field(..., description="Cancel API URL")
    rerun_url: str = Field(..., description="Rerun API URL")
    previous_attempt_url: Optional[str] = Field(None, description="Previous attempt URL")
    head_commit: Dict[str, Any] = Field(..., description="Head commit object")
    repository: Dict[str, Any] = Field(..., description="Repository object")

    class Config:
        from_attributes = True
        extra = "allow"


class WorkflowJobDetails(BaseModel):
    """Workflow job details from GitHub API."""

    id: int = Field(..., description="Job ID")
    run_id: int = Field(..., description="Workflow run ID")
    run_url: str = Field(..., description="Run API URL")
    node_id: str = Field(..., description="GraphQL node ID")
    head_sha: str = Field(..., description="Head SHA")
    url: str = Field(..., description="Job API URL")
    html_url: Optional[str] = Field(None, description="Job web URL")
    status: str = Field(..., description="Job status")
    conclusion: Optional[str] = Field(None, description="Job conclusion")
    started_at: datetime = Field(..., description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    name: str = Field(..., description="Job name")
    steps: List[Dict[str, Any]] = Field(..., description="Job steps")
    check_run_url: str = Field(..., description="Check run URL")
    labels: List[str] = Field(..., description="Runner labels")
    runner_id: Optional[int] = Field(None, description="Runner ID")
    runner_name: Optional[str] = Field(None, description="Runner name")
    runner_group_id: Optional[int] = Field(None, description="Runner group ID")
    runner_group_name: Optional[str] = Field(None, description="Runner group name")

    class Config:
        from_attributes = True
        extra = "allow"


class WorkflowFailureAnalysis(BaseModel):
    """Analysis of workflow failure."""

    run_id: str = Field(..., description="Workflow run ID")
    failure_type: str = Field(..., description="Type of failure (test, build, lint, deploy, etc.)")
    failed_jobs: List[str] = Field(..., description="Names of failed jobs")
    failed_steps: List[Dict[str, Any]] = Field(..., description="Failed step details")
    error_messages: List[str] = Field(..., description="Extracted error messages")
    log_excerpts: List[str] = Field(..., description="Relevant log excerpts")
    suggested_fixes: List[str] = Field(default=[], description="AI-suggested fixes")
    confidence_score: float = Field(..., description="Analysis confidence (0-1)")
    requires_human_review: bool = Field(..., description="Whether human review is needed")


class WorkflowRetryRequest(BaseModel):
    """Request to retry a workflow run."""

    run_id: str = Field(..., description="Workflow run ID to retry")
    retry_failed_jobs: bool = Field(
        default=False,
        description="Retry only failed jobs instead of entire workflow"
    )
