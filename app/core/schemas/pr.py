# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Pull Request Schemas

Pydantic models for automated PR creation and management.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class CreatePRRequest(BaseModel):
    """Request to create a PR for an incident."""

    incident_id: str = Field(..., description="Incident ID to create PR for")
    branch_name: Optional[str] = Field(
        None,
        description="Custom branch name (auto-generated if not provided)"
    )
    use_ai_analysis: bool = Field(
        default=True,
        description="Use AI to analyze and generate fixes"
    )
    auto_commit: bool = Field(
        default=True,
        description="Automatically commit and push changes"
    )
    draft_pr: bool = Field(
        default=False,
        description="Create as draft PR requiring manual review"
    )


class PRFileChange(BaseModel):
    """Represents a file change in a PR."""

    file_path: str = Field(..., description="Path to the file")
    change_type: str = Field(..., description="Type of change (modified, added, deleted)")
    original_content: Optional[str] = Field(None, description="Original file content")
    new_content: str = Field(..., description="New file content")
    diff: Optional[str] = Field(None, description="Unified diff")
    explanation: str = Field(..., description="Explanation of changes")


class AIFixSuggestion(BaseModel):
    """AI-generated fix suggestion."""

    fix_type: str = Field(..., description="Type of fix (test_fix, dependency_update, config_change, etc.)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    description: str = Field(..., description="Description of the fix")
    file_changes: List[PRFileChange] = Field(..., description="Proposed file changes")
    reasoning: str = Field(..., description="AI reasoning for this fix")
    estimated_impact: str = Field(..., description="Estimated impact (low, medium, high)")


class CreatePRResponse(BaseModel):
    """Response from PR creation."""

    success: bool = Field(..., description="Whether PR creation succeeded")
    pr_number: Optional[int] = Field(None, description="GitHub PR number")
    pr_url: Optional[str] = Field(None, description="URL to the PR")
    branch_name: str = Field(..., description="Branch name used")
    commit_sha: Optional[str] = Field(None, description="Commit SHA")
    files_changed: int = Field(default=0, description="Number of files changed")
    incident_id: str = Field(..., description="Associated incident ID")
    ai_analysis_used: bool = Field(..., description="Whether AI analysis was used")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    created_at: datetime = Field(..., description="PR creation timestamp")


class PRStatus(BaseModel):
    """Pull request status information."""

    pr_number: int = Field(..., description="GitHub PR number")
    pr_url: str = Field(..., description="URL to the PR")
    title: str = Field(..., description="PR title")
    body: str = Field(..., description="PR description")
    state: str = Field(..., description="PR state (open, closed, merged)")
    draft: bool = Field(..., description="Whether PR is draft")
    mergeable: Optional[bool] = Field(None, description="Whether PR is mergeable")
    merged: bool = Field(..., description="Whether PR was merged")
    merged_at: Optional[datetime] = Field(None, description="Merge timestamp")
    closed_at: Optional[datetime] = Field(None, description="Close timestamp")
    branch_name: str = Field(..., description="Source branch name")
    base_branch: str = Field(..., description="Target branch name")
    commits: int = Field(..., description="Number of commits")
    changed_files: int = Field(..., description="Number of files changed")
    additions: int = Field(..., description="Lines added")
    deletions: int = Field(..., description="Lines deleted")
    comments: int = Field(..., description="Number of comments")
    reviews: int = Field(..., description="Number of reviews")
    created_at: datetime = Field(..., description="PR creation time")
    updated_at: datetime = Field(..., description="Last update time")
    created_by: str = Field(..., description="PR creator username")


class IncidentPRResponse(BaseModel):
    """PR information for an incident."""

    incident_id: str = Field(..., description="Incident ID")
    prs: List[PRStatus] = Field(..., description="List of PRs for this incident")
    total_prs: int = Field(..., description="Total number of PRs")
    open_prs: int = Field(..., description="Number of open PRs")
    merged_prs: int = Field(..., description="Number of merged PRs")
    closed_prs: int = Field(..., description="Number of closed PRs")


class PRListResponse(BaseModel):
    """List of pull requests."""

    prs: List[PRStatus] = Field(..., description="List of pull requests")
    total: int = Field(..., description="Total number of PRs")
    page: int = Field(default=1, description="Current page")
    per_page: int = Field(default=30, description="Items per page")


class PRStatsResponse(BaseModel):
    """Pull request statistics."""

    total_prs_created: int = Field(..., description="Total PRs created by DevFlowFix")
    merged_prs: int = Field(..., description="Number of merged PRs")
    closed_without_merge: int = Field(..., description="Number of closed without merge")
    open_prs: int = Field(..., description="Number of open PRs")
    draft_prs: int = Field(..., description="Number of draft PRs")
    merge_rate: float = Field(..., description="Merge rate percentage")
    avg_time_to_merge_hours: Optional[float] = Field(None, description="Average time to merge in hours")
    avg_files_changed: float = Field(..., description="Average files changed per PR")
    success_rate: float = Field(..., description="Success rate (merged / total)")
    incidents_with_prs: int = Field(..., description="Number of incidents with PRs")
    incidents_auto_fixed: int = Field(..., description="Number of incidents auto-fixed")


class UpdatePRRequest(BaseModel):
    """Request to update a PR."""

    title: Optional[str] = Field(None, description="New PR title")
    body: Optional[str] = Field(None, description="New PR description")
    state: Optional[str] = Field(None, description="New state (open, closed)")
    draft: Optional[bool] = Field(None, description="Convert to/from draft")


class PRCommentRequest(BaseModel):
    """Request to add a comment to a PR."""

    comment: str = Field(..., description="Comment text", min_length=1)
    review_event: Optional[str] = Field(
        None,
        description="Review event (APPROVE, REQUEST_CHANGES, COMMENT)"
    )


class PRMergeRequest(BaseModel):
    """Request to merge a PR."""

    commit_title: Optional[str] = Field(None, description="Custom merge commit title")
    commit_message: Optional[str] = Field(None, description="Custom merge commit message")
    merge_method: str = Field(
        default="squash",
        description="Merge method (merge, squash, rebase)"
    )
    delete_branch: bool = Field(
        default=True,
        description="Delete branch after merge"
    )


class PRAnalysisResponse(BaseModel):
    """Analysis of a pull request."""

    pr_number: int = Field(..., description="GitHub PR number")
    incident_id: str = Field(..., description="Associated incident ID")
    fix_type: str = Field(..., description="Type of fix applied")
    files_analyzed: int = Field(..., description="Number of files analyzed")
    potential_issues: List[str] = Field(default=[], description="Potential issues detected")
    test_coverage: Optional[float] = Field(None, description="Test coverage percentage")
    code_quality_score: Optional[float] = Field(None, description="Code quality score")
    breaking_changes: bool = Field(..., description="Whether PR contains breaking changes")
    recommendations: List[str] = Field(default=[], description="Recommendations for improvement")
    ai_confidence: float = Field(..., description="AI confidence in the fix")
