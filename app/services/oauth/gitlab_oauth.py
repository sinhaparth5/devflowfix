# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitLab OAuth Provider

Handles GitLab OAuth 2.0 authentication flow.
"""

from typing import Dict, Any, Optional, List
import httpx
import structlog

from .provider_base import OAuthProvider

logger = structlog.get_logger(__name__)


class GitLabOAuthProvider(OAuthProvider):
    """
    GitLab OAuth 2.0 provider implementation.

    Documentation: https://docs.gitlab.com/ee/api/oauth2.html
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: List[str],
        gitlab_url: str = "https://gitlab.com",
    ):
        """
        Initialize GitLab OAuth provider.

        Args:
            client_id: GitLab application ID
            client_secret: GitLab application secret
            redirect_uri: OAuth callback URL
            scopes: List of OAuth scopes
            gitlab_url: GitLab instance URL (default: https://gitlab.com)
        """
        super().__init__(client_id, client_secret, redirect_uri, scopes)
        self.gitlab_url = gitlab_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "gitlab"

    @property
    def authorize_url(self) -> str:
        return f"{self.gitlab_url}/oauth/authorize"

    @property
    def token_url(self) -> str:
        return f"{self.gitlab_url}/oauth/token"

    @property
    def user_info_url(self) -> str:
        return f"{self.gitlab_url}/api/v4/user"

    def _get_extra_auth_params(self) -> Dict[str, str]:
        """
        GitLab-specific authorization parameters.

        Returns:
            Empty dict (GitLab doesn't need extra params)
        """
        return {}

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for GitLab access token.

        Args:
            code: Authorization code from callback

        Returns:
            Token response with access_token, refresh_token, scope

        Raises:
            httpx.HTTPError: If token exchange fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                },
                headers={
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            token_data = response.json()

            logger.info(
                "gitlab_token_exchanged",
                scopes=token_data.get("scope", "").split(" "),
            )

            return token_data

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh GitLab access token.

        Args:
            refresh_token: Refresh token

        Returns:
            New token data

        Raises:
            httpx.HTTPError: If refresh fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "redirect_uri": self.redirect_uri,
                },
                headers={
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get GitLab user information.

        Args:
            access_token: Valid GitLab access token

        Returns:
            User info with id, username, name, email, etc.

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_info_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            user_data = response.json()

            logger.info(
                "gitlab_user_info_fetched",
                user_id=user_data.get("id"),
                username=user_data.get("username"),
            )

            return user_data

    async def revoke_token(self, access_token: str) -> bool:
        """
        Revoke a GitLab access token.

        Args:
            access_token: Token to revoke

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If revocation fails
        """
        # GitLab token revocation endpoint
        revoke_url = f"{self.gitlab_url}/oauth/revoke"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                revoke_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "token": access_token,
                },
                headers={
                    "Accept": "application/json",
                },
            )

            if response.status_code == 200:
                logger.info("gitlab_token_revoked")
                return True
            else:
                logger.error(
                    "gitlab_token_revoke_failed",
                    status_code=response.status_code,
                )
                return False

    async def get_user_projects(
        self,
        access_token: str,
        page: int = 1,
        per_page: int = 100,
        sort: str = "updated_at",
        direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        Get list of projects (repositories) accessible to the user.

        Args:
            access_token: Valid GitLab access token
            page: Page number for pagination
            per_page: Results per page (max 100)
            sort: Sort field
            direction: Sort direction (asc, desc)

        Returns:
            List of project objects

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.gitlab_url}/api/v4/projects",
                params={
                    "membership": "true",
                    "page": page,
                    "per_page": per_page,
                    "order_by": sort,
                    "sort": direction,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            projects = response.json()

            logger.info(
                "gitlab_projects_fetched",
                count=len(projects),
                page=page,
            )

            return projects

    async def get_project(
        self, access_token: str, project_id: str
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific project.

        Args:
            access_token: Valid GitLab access token
            project_id: Project ID or path (e.g., "namespace/project")

        Returns:
            Project object with detailed info

        Raises:
            httpx.HTTPError: If API request fails
        """
        # URL encode the project ID/path
        import urllib.parse
        encoded_project = urllib.parse.quote(project_id, safe="")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.gitlab_url}/api/v4/projects/{encoded_project}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            project_data = response.json()

            logger.info(
                "gitlab_project_fetched",
                project_id=project_data.get("id"),
                project_path=project_data.get("path_with_namespace"),
            )

            return project_data

    async def create_project_hook(
        self,
        access_token: str,
        project_id: str,
        webhook_url: str,
        token: str,
        events: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a webhook (project hook) in a GitLab project.

        Args:
            access_token: Valid GitLab access token
            project_id: Project ID or path
            webhook_url: URL to send webhook events to
            token: Secret token for webhook verification
            events: List of events to subscribe to

        Returns:
            Hook object with id, url, etc.

        Raises:
            httpx.HTTPError: If hook creation fails
        """
        if events is None:
            events = ["pipeline_events", "merge_requests_events", "push_events"]

        # Build event flags
        event_flags = {
            "pipeline_events": "pipeline_events" in events,
            "merge_requests_events": "merge_requests_events" in events,
            "push_events": "push_events" in events,
            "job_events": "job_events" in events,
            "issues_events": "issues_events" in events,
        }

        import urllib.parse
        encoded_project = urllib.parse.quote(project_id, safe="")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.gitlab_url}/api/v4/projects/{encoded_project}/hooks",
                json={
                    "url": webhook_url,
                    "token": token,
                    "enable_ssl_verification": True,
                    **event_flags,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            hook_data = response.json()

            logger.info(
                "gitlab_hook_created",
                project_id=project_id,
                hook_id=hook_data.get("id"),
                events=events,
            )

            return hook_data

    async def delete_project_hook(
        self, access_token: str, project_id: str, hook_id: int
    ) -> bool:
        """
        Delete a webhook from a GitLab project.

        Args:
            access_token: Valid GitLab access token
            project_id: Project ID or path
            hook_id: Hook ID to delete

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If deletion fails
        """
        import urllib.parse
        encoded_project = urllib.parse.quote(project_id, safe="")

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.gitlab_url}/api/v4/projects/{encoded_project}/hooks/{hook_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 204:
                logger.info(
                    "gitlab_hook_deleted",
                    project_id=project_id,
                    hook_id=hook_id,
                )
                return True
            else:
                logger.error(
                    "gitlab_hook_delete_failed",
                    status_code=response.status_code,
                )
                return False

    async def get_pipeline_runs(
        self,
        access_token: str,
        project_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get pipeline runs for a project.

        Args:
            access_token: Valid GitLab access token
            project_id: Project ID or path
            page: Page number
            per_page: Results per page

        Returns:
            List of pipeline objects
        """
        import urllib.parse
        encoded_project = urllib.parse.quote(project_id, safe="")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.gitlab_url}/api/v4/projects/{encoded_project}/pipelines",
                params={
                    "page": page,
                    "per_page": per_page,
                    "order_by": "updated_at",
                    "sort": "desc",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            return response.json()

    async def get_pipeline(
        self, access_token: str, project_id: str, pipeline_id: int
    ) -> Dict[str, Any]:
        """
        Get detailed pipeline information.

        Args:
            access_token: Valid GitLab access token
            project_id: Project ID or path
            pipeline_id: Pipeline ID

        Returns:
            Pipeline object
        """
        import urllib.parse
        encoded_project = urllib.parse.quote(project_id, safe="")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.gitlab_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            return response.json()

    async def retry_pipeline(
        self, access_token: str, project_id: str, pipeline_id: int
    ) -> Dict[str, Any]:
        """
        Retry a pipeline.

        Args:
            access_token: Valid GitLab access token
            project_id: Project ID or path
            pipeline_id: Pipeline ID

        Returns:
            Updated pipeline object
        """
        import urllib.parse
        encoded_project = urllib.parse.quote(project_id, safe="")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.gitlab_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}/retry",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            return response.json()
