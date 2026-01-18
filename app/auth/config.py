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


@lru_cache()
def get_zitadel_settings() -> ZitadelSettings:
    """
    Get cached Zitadel settings.

    Returns:
        ZitadelSettings instance
    """
    return ZitadelSettings()
