# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Zitadel User Schemas

Pydantic models for user-related API responses.
These are simplified schemas since Zitadel handles most user management.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """
    User profile response.

    Contains user information from Zitadel + local preferences.
    """

    # From Zitadel
    user_id: str = Field(..., description="Zitadel user ID")
    email: str = Field(..., description="User email")
    email_verified: bool = Field(default=False, description="Email verification status")
    name: str = Field(default="", description="Display name")
    given_name: str = Field(default="", description="First name")
    family_name: str = Field(default="", description="Last name")
    picture: Optional[str] = Field(default=None, description="Profile picture URL")

    # From local database
    role: str = Field(default="user", description="User role")
    organization_id: Optional[str] = Field(default=None, description="Organization ID")
    team_id: Optional[str] = Field(default=None, description="Team ID")
    is_active: bool = Field(default=True, description="Account active status")
    created_at: datetime = Field(..., description="Account creation date")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login timestamp")

    # User preferences (stored locally)
    preferences: dict = Field(default_factory=dict, description="User preferences")

    class Config:
        from_attributes = True


class UserPreferencesUpdate(BaseModel):
    """
    Request to update user preferences.

    Preferences are stored locally since Zitadel manages auth.
    """

    theme: Optional[str] = Field(default=None, description="UI theme (light/dark)")
    notifications_enabled: bool = Field(default=True, description="Enable notifications")
    email_notifications: bool = Field(default=True, description="Enable email notifications")
    default_repository_id: Optional[str] = Field(default=None, description="Default repository")
    timezone: Optional[str] = Field(default=None, description="User timezone")
    language: Optional[str] = Field(default=None, description="Preferred language")


class UserPreferencesResponse(BaseModel):
    """User preferences response."""

    theme: str = Field(default="system", description="UI theme")
    notifications_enabled: bool = Field(default=True)
    email_notifications: bool = Field(default=True)
    default_repository_id: Optional[str] = None
    timezone: str = Field(default="UTC")
    language: str = Field(default="en")


class ConnectedAccount(BaseModel):
    """
    Connected OAuth account info.

    Shows what accounts are linked via Zitadel social login.
    """

    provider: str = Field(..., description="Provider name (github, google, gitlab)")
    provider_user_id: str = Field(..., description="User ID at provider")
    username: Optional[str] = Field(default=None, description="Username at provider")
    connected_at: datetime = Field(..., description="When account was connected")


class UserConnectionsResponse(BaseModel):
    """Response with user's connected accounts."""

    connections: List[ConnectedAccount] = Field(default_factory=list)
    github_connected: bool = Field(default=False)
    gitlab_connected: bool = Field(default=False)
    google_connected: bool = Field(default=False)


class UserStatsResponse(BaseModel):
    """User statistics response."""

    total_repositories: int = Field(default=0, description="Connected repositories")
    total_incidents: int = Field(default=0, description="Total incidents")
    resolved_incidents: int = Field(default=0, description="Resolved incidents")
    auto_fixed_incidents: int = Field(default=0, description="Auto-fixed by AI")
    total_prs_created: int = Field(default=0, description="PRs created")
    prs_merged: int = Field(default=0, description="PRs merged")
    member_since_days: int = Field(default=0, description="Days since registration")
