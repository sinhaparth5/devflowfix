# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Repository Request/Response Schemas

Pydantic models for repository management endpoints.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class GitHubRepositoryResponse(BaseModel):
    """GitHub repository information from API."""

    id: int = Field(..., description="GitHub repository ID")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repository name (owner/repo)")
    description: Optional[str] = Field(None, description="Repository description")
    private: bool = Field(..., description="Whether repository is private")
    owner: dict = Field(..., description="Repository owner information")
    html_url: str = Field(..., description="Repository URL")
    default_branch: str = Field(default="main", description="Default branch")
    has_issues: bool = Field(default=True, description="Whether issues are enabled")
    has_projects: bool = Field(default=True, description="Whether projects are enabled")
    has_wiki: bool = Field(default=True, description="Whether wiki is enabled")
    language: Optional[str] = Field(None, description="Primary language")
    stargazers_count: int = Field(default=0, description="Number of stars")
    watchers_count: int = Field(default=0, description="Number of watchers")
    forks_count: int = Field(default=0, description="Number of forks")
    open_issues_count: int = Field(default=0, description="Number of open issues")
    created_at: Optional[datetime] = Field(None, description="Repository creation time")
    updated_at: Optional[datetime] = Field(None, description="Last update time")
    pushed_at: Optional[datetime] = Field(None, description="Last push time")
    permissions: Optional[dict] = Field(None, description="User permissions on repository")

    class Config:
        from_attributes = True


class RepositoryListResponse(BaseModel):
    """List of repositories from OAuth provider."""

    repositories: List[GitHubRepositoryResponse] = Field(
        ...,
        description="List of repositories"
    )
    total: int = Field(..., description="Total number of repositories")
    page: int = Field(default=1, description="Current page number")
    per_page: int = Field(default=30, description="Items per page")
    has_next: bool = Field(default=False, description="Whether there are more pages")


class ConnectRepositoryRequest(BaseModel):
    """Request to connect a repository to DevFlowFix."""

    repository_full_name: str = Field(
        ...,
        description="Full repository name (owner/repo)",
        example="octocat/Hello-World"
    )
    auto_pr_enabled: bool = Field(
        default=True,
        description="Enable automatic PR creation for fixes"
    )
    setup_webhook: bool = Field(
        default=True,
        description="Automatically setup webhook in repository"
    )
    webhook_events: List[str] = Field(
        default=["workflow_run", "pull_request", "push"],
        description="Webhook events to subscribe to"
    )


class RepositoryConnectionResponse(BaseModel):
    """Repository connection information."""

    id: str = Field(..., description="Connection ID")
    oauth_connection_id: str = Field(..., description="Associated OAuth connection ID")
    repository_id: str = Field(..., description="GitHub repository ID")
    repository_full_name: str = Field(..., description="Full repository name (owner/repo)")
    repository_name: str = Field(..., description="Repository name")
    owner_name: str = Field(..., description="Repository owner")
    webhook_id: Optional[str] = Field(None, description="GitHub webhook ID")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    is_enabled: bool = Field(..., description="Whether monitoring is enabled")
    auto_pr_enabled: bool = Field(..., description="Whether auto PR is enabled")
    created_at: datetime = Field(..., description="Connection creation time")
    last_event_at: Optional[datetime] = Field(None, description="Last webhook event time")

    class Config:
        from_attributes = True


class RepositoryConnectionListResponse(BaseModel):
    """List of connected repositories."""

    connections: List[RepositoryConnectionResponse] = Field(
        ...,
        description="List of repository connections"
    )
    total: int = Field(..., description="Total number of connections")


class UpdateRepositoryConnectionRequest(BaseModel):
    """Request to update repository connection settings."""

    is_enabled: Optional[bool] = Field(
        None,
        description="Enable/disable monitoring for this repository"
    )
    auto_pr_enabled: Optional[bool] = Field(
        None,
        description="Enable/disable automatic PR creation"
    )


class DisconnectRepositoryResponse(BaseModel):
    """Response from repository disconnect endpoint."""

    success: bool = Field(..., description="Whether disconnection succeeded")
    connection_id: str = Field(..., description="Disconnected connection ID")
    repository_full_name: str = Field(..., description="Repository full name")
    webhook_deleted: bool = Field(..., description="Whether webhook was deleted")
    message: str = Field(..., description="Success message")


class WebhookSetupRequest(BaseModel):
    """Request to setup webhook for a repository."""

    repository_full_name: str = Field(
        ...,
        description="Full repository name (owner/repo)",
        example="octocat/Hello-World"
    )
    events: List[str] = Field(
        default=["workflow_run", "pull_request", "push"],
        description="Webhook events to subscribe to"
    )


class WebhookSetupResponse(BaseModel):
    """Response from webhook setup."""

    success: bool = Field(..., description="Whether webhook setup succeeded")
    webhook_id: str = Field(..., description="GitHub webhook ID")
    webhook_url: str = Field(..., description="Webhook URL")
    events: List[str] = Field(..., description="Subscribed events")
    repository_full_name: str = Field(..., description="Repository full name")
    message: str = Field(..., description="Success message")


class RepositoryStatsResponse(BaseModel):
    """Statistics for connected repositories."""

    total_repositories: int = Field(..., description="Total connected repositories")
    active_repositories: int = Field(..., description="Active repositories")
    inactive_repositories: int = Field(..., description="Inactive repositories")
    total_webhooks: int = Field(..., description="Total webhooks setup")
    repositories_with_auto_pr: int = Field(..., description="Repositories with auto PR enabled")
