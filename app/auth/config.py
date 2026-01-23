# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Zitadel Configuration

Settings for Zitadel OIDC integration.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class ZitadelSettings(BaseSettings):
    """
    Zitadel OIDC configuration.

    These settings are loaded from environment variables.
    """

    # Zitadel instance URL (e.g., https://devflowfix-xxx.zitadel.cloud)
    issuer: str = Field(
        default="",
        alias="ZITADEL_ISSUER",
        description="Zitadel instance URL"
    )

    # Client ID from Zitadel Console
    client_id: str = Field(
        default="",
        alias="ZITADEL_CLIENT_ID",
        description="Application Client ID from Zitadel"
    )

    # Client Secret from Zitadel Console (required for token introspection)
    client_secret: str = Field(
        default="",
        alias="ZITADEL_CLIENT_SECRET",
        description="Application Client Secret from Zitadel (for introspection)"
    )

    # Project ID (optional, for audience validation)
    project_id: str = Field(
        default="",
        alias="ZITADEL_PROJECT_ID",
        description="Zitadel Project ID"
    )

    # API URL (your backend URL, used for audience validation)
    api_audience: str = Field(
        default="",
        alias="ZITADEL_API_AUDIENCE",
        description="API audience for token validation"
    )

    # JWKS cache duration in seconds
    jwks_cache_ttl: int = Field(
        default=3600,
        alias="ZITADEL_JWKS_CACHE_TTL",
        description="How long to cache JWKS keys (seconds)"
    )

    # Token validation settings
    verify_at_hash: bool = Field(
        default=False,
        alias="ZITADEL_VERIFY_AT_HASH",
        description="Verify access token hash in ID token"
    )

    # Management API credentials (for fetching IdP tokens)
    # Create a Service User in Zitadel with IAM_OWNER or ORG_OWNER role
    service_user_id: str = Field(
        default="",
        alias="ZITADEL_SERVICE_USER_ID",
        description="Service user ID for Management API"
    )

    service_user_key: str = Field(
        default="",
        alias="ZITADEL_SERVICE_USER_KEY",
        description="Service user private key (JSON) for Management API"
    )

    # Organization ID (required for Management API calls)
    org_id: str = Field(
        default="",
        alias="ZITADEL_ORG_ID",
        description="Zitadel Organization ID"
    )

    # IdP IDs for GitHub and GitLab (from Zitadel Console > Identity Providers)
    github_idp_id: str = Field(
        default="",
        alias="ZITADEL_GITHUB_IDP_ID",
        description="GitHub IdP ID in Zitadel"
    )

    gitlab_idp_id: str = Field(
        default="",
        alias="ZITADEL_GITLAB_IDP_ID",
        description="GitLab IdP ID in Zitadel"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def jwks_uri(self) -> str:
        """Get JWKS URI from issuer."""
        # Zitadel uses /oauth/v2/keys instead of /.well-known/jwks.json
        return f"{self.issuer.rstrip('/')}/oauth/v2/keys"

    @property
    def openid_config_uri(self) -> str:
        """Get OpenID configuration URI."""
        return f"{self.issuer.rstrip('/')}/.well-known/openid-configuration"

    @property
    def userinfo_uri(self) -> str:
        """Get userinfo endpoint URI."""
        return f"{self.issuer.rstrip('/')}/oidc/v1/userinfo"

    @property
    def introspection_uri(self) -> str:
        """Get token introspection endpoint URI."""
        return f"{self.issuer.rstrip('/')}/oauth/v2/introspect"

    @property
    def management_api_uri(self) -> str:
        """Get Management API base URI."""
        return f"{self.issuer.rstrip('/')}/management/v1"

    @property
    def auth_api_uri(self) -> str:
        """Get Auth API base URI (for user's own data)."""
        return f"{self.issuer.rstrip('/')}/auth/v1"

    @property
    def is_configured(self) -> bool:
        """Check if Zitadel is properly configured."""
        return bool(self.issuer and self.client_id)

    @property
    def is_management_configured(self) -> bool:
        """Check if Management API is configured for IdP token access."""
        return bool(
            self.issuer
            and self.service_user_id
            and self.service_user_key
        )

    @property
    def has_github_idp(self) -> bool:
        """Check if GitHub IdP is configured."""
        return bool(self.github_idp_id)

    @property
    def has_gitlab_idp(self) -> bool:
        """Check if GitLab IdP is configured."""
        return bool(self.gitlab_idp_id)


@lru_cache()
def get_zitadel_settings() -> ZitadelSettings:
    """
    Get cached Zitadel settings.

    Returns:
        ZitadelSettings instance
    """
    return ZitadelSettings()
