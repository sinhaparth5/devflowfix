# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
OAuth Request/Response Schemas

Pydantic models for OAuth endpoints.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

class OAuthAuthorizeResponse(BaseModel):
    """Response from OAuth authorization endpoint."""

    authorization_url: HttpUrl = Field(
        ...,
        description="URL to redirect user to for OAuth authorization"
    )
    state: str = Field(
        ...,
        description="CSRF protection state parameter (store in session)"
    )
    provider: str = Field(
        ...,
        description="OAuth provider name (github, gitlab)"
    )

class OAuthConnectionResponse(BaseModel):
    """OAuth connection information."""

    id: str = Field(..., description="Connection ID")
    provider: str = Field(..., description="Provider name (github, gitlab)")
    provider_username: str = Field(..., description="Username from provider")
    provider_user_id: str = Field(..., description="User ID from provider")
    scopes: List[str] = Field(..., description="Granted permission scopes")
    is_active: bool = Field(..., description="Whether connection is active")
    created_at: datetime = Field(..., description="Connection creation time")
    last_used_at: Optional[datetime] = Field(None, description="Last time connection was used")

    class Config:
        from_attributes = True


class OAuthConnectionListResponse(BaseModel):
    """List of OAuth connections."""

    connections: List[OAuthConnectionResponse] = Field(
        ...,
        description="List of OAuth connections"
    )
    total: int = Field(..., description="Total number of connections")

class OAuthCallbackRequest(BaseModel):
    """OAuth callback query parameters."""

    code: str = Field(..., description="Authorization code from provider")
    state: str = Field(..., description="CSRF protection state parameter")


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback."""

    success: bool = Field(..., description="Whether OAuth flow succeeded")
    connection_id: str = Field(..., description="Created OAuth connection ID")
    provider: str = Field(..., description="OAuth provider")
    username: str = Field(..., description="User's username from provider")
    message: str = Field(..., description="Success message")
    redirect_url: Optional[str] = Field(
        None,
        description="URL to redirect user to after OAuth"
    )

class OAuthDisconnectResponse(BaseModel):
    """Response from disconnect endpoint."""

    success: bool = Field(..., description="Whether disconnection succeeded")
    connection_id: str = Field(..., description="Disconnected connection ID")
    provider: str = Field(..., description="OAuth provider")
    message: str = Field(..., description="Success message")

class OAuthErrorResponse(BaseModel):
    """OAuth error response."""

    error: str = Field(..., description="Error type")
    error_description: str = Field(..., description="Human-readable error description")
    state: Optional[str] = Field(None, description="State parameter if available")

class GitHubUserInfo(BaseModel):
    """GitHub user information."""

    id: int = Field(..., description="GitHub user ID")
    login: str = Field(..., description="GitHub username")
    name: Optional[str] = Field(None, description="Full name")
    email: Optional[str] = Field(None, description="Email address")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")
    html_url: Optional[str] = Field(None, description="Profile URL")
    type: str = Field(default="User", description="Account type")
    company: Optional[str] = Field(None, description="Company name")
    location: Optional[str] = Field(None, description="Location")
    bio: Optional[str] = Field(None, description="Bio")

    class Config:
        from_attributes = True


class GitLabUserInfo(BaseModel):
    """GitLab user information."""

    id: int = Field(..., description="GitLab user ID")
    username: str = Field(..., description="GitLab username")
    name: Optional[str] = Field(None, description="Full name")
    email: Optional[str] = Field(None, description="Email address")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")
    web_url: Optional[str] = Field(None, description="Profile URL")
    state: str = Field(default="active", description="Account state")
    bio: Optional[str] = Field(None, description="Bio")

    class Config:
        from_attributes = True
