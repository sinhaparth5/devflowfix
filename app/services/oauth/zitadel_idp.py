# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Zitadel IdP Token Service

Fetches GitHub/GitLab access tokens from Zitadel's IdP links.
When users login via GitHub/GitLab through Zitadel, their provider
access tokens are stored in Zitadel and can be retrieved via the Auth API.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import httpx
import structlog
import json

from app.auth.config import get_zitadel_settings, ZitadelSettings

logger = structlog.get_logger(__name__)


@dataclass
class IdPToken:
    """Represents an IdP access token from Zitadel."""
    provider: str  # "github" or "gitlab"
    idp_id: str  # Zitadel IdP ID
    access_token: str
    provider_user_id: str
    provider_username: str
    scopes: List[str]
    expires_at: Optional[datetime] = None


class ZitadelIdPService:
    """
    Service to fetch IdP tokens from Zitadel.

    When users authenticate via GitHub/GitLab through Zitadel,
    Zitadel stores their provider access tokens. This service
    retrieves those tokens using Zitadel's Auth API.

    The Auth API uses the user's own access token to fetch their data,
    which is more secure than using Management API with a service account.
    """

    def __init__(self, settings: Optional[ZitadelSettings] = None):
        self.settings = settings or get_zitadel_settings()
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=10),
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def get_user_idp_links(
        self,
        user_access_token: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all IdP links for the current user.

        Uses the Auth API endpoint which allows users to access their own data
        using their access token (no service account needed).

        Args:
            user_access_token: User's Zitadel access token

        Returns:
            List of IdP link objects
        """
        client = await self._get_client()

        # Auth API - get user's own IdP links
        url = f"{self.settings.auth_api_uri}/users/me/idps"

        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {user_access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 200:
                data = response.json()
                links = data.get("result", [])
                logger.info(
                    "idp_links_fetched",
                    count=len(links),
                )
                return links
            else:
                logger.warning(
                    "idp_links_fetch_failed",
                    status=response.status_code,
                    response=response.text[:200],
                )
                return []

        except Exception as e:
            logger.error(
                "idp_links_fetch_error",
                error=str(e),
            )
            return []

    async def get_idp_access_token(
        self,
        user_access_token: str,
        idp_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the access token for a specific IdP link.

        This retrieves the GitHub/GitLab access token that was stored
        when the user authenticated via that IdP.

        Args:
            user_access_token: User's Zitadel access token
            idp_id: The IdP ID (from Zitadel's Identity Providers)
            user_id: The user's Zitadel user ID

        Returns:
            Token data dict or None
        """
        client = await self._get_client()

        # Auth API endpoint to get IdP token
        # Note: This endpoint may require specific configuration in Zitadel
        url = f"{self.settings.auth_api_uri}/users/me/idps/{idp_id}"

        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {user_access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "idp_token_fetched",
                    idp_id=idp_id,
                )
                return data
            else:
                logger.warning(
                    "idp_token_fetch_failed",
                    idp_id=idp_id,
                    status=response.status_code,
                    response=response.text[:200],
                )
                return None

        except Exception as e:
            logger.error(
                "idp_token_fetch_error",
                idp_id=idp_id,
                error=str(e),
            )
            return None

    def identify_provider(self, idp_id: str) -> Optional[str]:
        """
        Identify the provider type from IdP ID.

        Args:
            idp_id: Zitadel IdP ID

        Returns:
            "github", "gitlab", or None
        """
        if self.settings.github_idp_id and idp_id == self.settings.github_idp_id:
            return "github"
        if self.settings.gitlab_idp_id and idp_id == self.settings.gitlab_idp_id:
            return "gitlab"
        return None

    async def get_github_token(
        self,
        user_access_token: str,
        user_id: str,
    ) -> Optional[IdPToken]:
        """
        Get GitHub access token for the user.

        Args:
            user_access_token: User's Zitadel access token
            user_id: User's Zitadel user ID

        Returns:
            IdPToken or None if user hasn't linked GitHub
        """
        if not self.settings.github_idp_id:
            logger.warning("github_idp_not_configured")
            return None

        # First get IdP links to find GitHub
        links = await self.get_user_idp_links(user_access_token)

        github_link = None
        for link in links:
            idp_id = link.get("idpId", "")
            if idp_id == self.settings.github_idp_id:
                github_link = link
                break

        if not github_link:
            logger.info(
                "github_not_linked",
                user_id=user_id,
            )
            return None

        # Get the token
        token_data = await self.get_idp_access_token(
            user_access_token=user_access_token,
            idp_id=self.settings.github_idp_id,
            user_id=user_id,
        )

        if not token_data:
            return None

        return IdPToken(
            provider="github",
            idp_id=self.settings.github_idp_id,
            access_token=token_data.get("accessToken", ""),
            provider_user_id=github_link.get("providerId", ""),
            provider_username=github_link.get("providerUserName", ""),
            scopes=["repo", "read:user"],  # Default GitHub scopes
        )

    async def get_gitlab_token(
        self,
        user_access_token: str,
        user_id: str,
    ) -> Optional[IdPToken]:
        """
        Get GitLab access token for the user.

        Args:
            user_access_token: User's Zitadel access token
            user_id: User's Zitadel user ID

        Returns:
            IdPToken or None if user hasn't linked GitLab
        """
        if not self.settings.gitlab_idp_id:
            logger.warning("gitlab_idp_not_configured")
            return None

        # First get IdP links to find GitLab
        links = await self.get_user_idp_links(user_access_token)

        gitlab_link = None
        for link in links:
            idp_id = link.get("idpId", "")
            if idp_id == self.settings.gitlab_idp_id:
                gitlab_link = link
                break

        if not gitlab_link:
            logger.info(
                "gitlab_not_linked",
                user_id=user_id,
            )
            return None

        # Get the token
        token_data = await self.get_idp_access_token(
            user_access_token=user_access_token,
            idp_id=self.settings.gitlab_idp_id,
            user_id=user_id,
        )

        if not token_data:
            return None

        return IdPToken(
            provider="gitlab",
            idp_id=self.settings.gitlab_idp_id,
            access_token=token_data.get("accessToken", ""),
            provider_user_id=gitlab_link.get("providerId", ""),
            provider_username=gitlab_link.get("providerUserName", ""),
            scopes=["api", "read_user", "read_repository"],  # Default GitLab scopes
        )

    async def get_all_idp_tokens(
        self,
        user_access_token: str,
        user_id: str,
    ) -> Dict[str, IdPToken]:
        """
        Get all available IdP tokens for the user.

        Args:
            user_access_token: User's Zitadel access token
            user_id: User's Zitadel user ID

        Returns:
            Dict mapping provider name to IdPToken
        """
        tokens = {}

        # Try GitHub
        github_token = await self.get_github_token(user_access_token, user_id)
        if github_token:
            tokens["github"] = github_token

        # Try GitLab
        gitlab_token = await self.get_gitlab_token(user_access_token, user_id)
        if gitlab_token:
            tokens["gitlab"] = gitlab_token

        return tokens


# Global service instance
_idp_service: Optional[ZitadelIdPService] = None


def get_zitadel_idp_service() -> ZitadelIdPService:
    """Get or create ZitadelIdPService instance."""
    global _idp_service
    if _idp_service is None:
        _idp_service = ZitadelIdPService()
    return _idp_service
