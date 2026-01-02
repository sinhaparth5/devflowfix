# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub OAuth Provider

Handles GitHub OAuth 2.0 authentication flow.
"""

from typing import Dict, Any, Optional
import httpx
import structlog

from .provider_base import OAuthProvider

logger = structlog.get_logger(__name__)


class GitHubOAuthProvider(OAuthProvider):
    """
    GitHub OAuth 2.0 provider implementation.

    Documentation: https://docs.github.com/en/developers/apps/building-oauth-apps
    """

    @property
    def provider_name(self) -> str:
        return "github"

    @property
    def authorize_url(self) -> str:
        return "https://github.com/login/oauth/authorize"

    @property
    def token_url(self) -> str:
        return "https://github.com/login/oauth/access_token"

    @property
    def user_info_url(self) -> str:
        return "https://api.github.com/user"

    def _get_extra_auth_params(self) -> Dict[str, str]:
        """
        GitHub-specific authorization parameters.

        Returns:
            Dictionary with allow_signup parameter
        """
        return {
            "allow_signup": "true",  # Allow new GitHub account signup
        }

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for GitHub access token.

        Args:
            code: Authorization code from callback

        Returns:
            Token response with access_token, scope, token_type

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
                    "redirect_uri": self.redirect_uri,
                },
                headers={
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            token_data = response.json()

            logger.info(
                "github_token_exchanged",
                scopes=token_data.get("scope", "").split(","),
            )

            return token_data

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh GitHub access token.

        Note: GitHub OAuth apps do not support refresh tokens.
        GitHub tokens do not expire, so this method is not needed.

        Args:
            refresh_token: Unused for GitHub

        Returns:
            Empty dict (not supported)
        """
        logger.warning(
            "github_refresh_not_supported",
            message="GitHub OAuth tokens do not expire and cannot be refreshed",
        )
        return {}

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get GitHub user information.

        Args:
            access_token: Valid GitHub access token

        Returns:
            User info with id, login, name, email, etc.

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_info_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            user_data = response.json()

            logger.info(
                "github_user_info_fetched",
                user_id=user_data.get("id"),
                username=user_data.get("login"),
            )

            return user_data

    async def revoke_token(self, access_token: str) -> bool:
        """
        Revoke a GitHub access token.

        Args:
            access_token: Token to revoke

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If revocation fails
        """
        # GitHub token revocation endpoint
        revoke_url = f"https://api.github.com/applications/{self.client_id}/token"

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                revoke_url,
                auth=(self.client_id, self.client_secret),
                json={"access_token": access_token},
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code == 204:
                logger.info("github_token_revoked")
                return True
            else:
                logger.error(
                    "github_token_revoke_failed",
                    status_code=response.status_code,
                )
                return False

    async def get_user_repositories(
        self,
        access_token: str,
        page: int = 1,
        per_page: int = 100,
        sort: str = "updated",
        direction: str = "desc",
    ) -> list[Dict[str, Any]]:
        """
        Get list of repositories accessible to the user.

        Args:
            access_token: Valid GitHub access token
            page: Page number for pagination
            per_page: Results per page (max 100)
            sort: Sort field (created, updated, pushed, full_name)
            direction: Sort direction (asc, desc)

        Returns:
            List of repository objects

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos",
                params={
                    "visibility": "all",  # Include private repos
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": sort,
                    "direction": direction,
                    "page": page,
                    "per_page": per_page,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            repos = response.json()

            logger.info(
                "github_repositories_fetched",
                count=len(repos),
                page=page,
            )

            return repos

    async def get_repository(
        self, access_token: str, owner: str, repo: str
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific repository.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository object with detailed info

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            repo_data = response.json()

            logger.info(
                "github_repository_fetched",
                owner=owner,
                repo=repo,
                repo_id=repo_data.get("id"),
            )

            return repo_data

    async def create_webhook(
        self,
        access_token: str,
        owner: str,
        repo: str,
        webhook_url: str,
        secret: str,
        events: list[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a webhook in a GitHub repository.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name
            webhook_url: URL to send webhook events to
            secret: Webhook secret for HMAC verification
            events: List of events to subscribe to (default: workflow_run, push)

        Returns:
            Webhook object with id, url, etc.

        Raises:
            httpx.HTTPError: If webhook creation fails
        """
        if events is None:
            events = ["workflow_run", "push", "pull_request"]

        webhook_config = {
            "name": "web",
            "active": True,
            "events": events,
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/hooks",
                json=webhook_config,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            webhook_data = response.json()

            logger.info(
                "github_webhook_created",
                owner=owner,
                repo=repo,
                webhook_id=webhook_data.get("id"),
                events=events,
            )

            return webhook_data

    async def delete_webhook(
        self, access_token: str, owner: str, repo: str, hook_id: int
    ) -> bool:
        """
        Delete a webhook from a GitHub repository.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name
            hook_id: Webhook ID to delete

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If deletion fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://api.github.com/repos/{owner}/{repo}/hooks/{hook_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code == 204:
                logger.info(
                    "github_webhook_deleted",
                    owner=owner,
                    repo=repo,
                    hook_id=hook_id,
                )
                return True
            else:
                logger.error(
                    "github_webhook_delete_failed",
                    status_code=response.status_code,
                )
                return False

    async def get_workflow_runs(
        self,
        access_token: str,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 30,
        status: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get workflow runs for a repository.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name
            page: Page number for pagination
            per_page: Results per page (max 100)
            status: Filter by status (completed, in_progress, queued)
            branch: Filter by branch name

        Returns:
            Workflow runs response with total_count and workflow_runs list

        Raises:
            httpx.HTTPError: If API request fails
        """
        params = {
            "page": page,
            "per_page": per_page,
        }

        if status:
            params["status"] = status
        if branch:
            params["branch"] = branch

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            data = response.json()

            logger.info(
                "github_workflow_runs_fetched",
                owner=owner,
                repo=repo,
                count=len(data.get("workflow_runs", [])),
                total_count=data.get("total_count", 0),
            )

            return data

    async def get_workflow_run(
        self,
        access_token: str,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Get a specific workflow run.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID

        Returns:
            Workflow run object

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            run_data = response.json()

            logger.info(
                "github_workflow_run_fetched",
                owner=owner,
                repo=repo,
                run_id=run_id,
                status=run_data.get("status"),
                conclusion=run_data.get("conclusion"),
            )

            return run_data

    async def get_pull_requests(
        self,
        access_token: str,
        owner: str,
        repo: str,
        state: str = "all",
        page: int = 1,
        per_page: int = 30,
        sort: str = "created",
        direction: str = "desc",
    ) -> list[Dict[str, Any]]:
        """
        Get pull requests for a repository.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name
            state: Filter by state (open, closed, all)
            page: Page number for pagination
            per_page: Results per page (max 100)
            sort: Sort by (created, updated, popularity, long-running)
            direction: Sort direction (asc, desc)

        Returns:
            List of pull request objects

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                params={
                    "state": state,
                    "page": page,
                    "per_page": per_page,
                    "sort": sort,
                    "direction": direction,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            prs = response.json()

            logger.info(
                "github_pull_requests_fetched",
                owner=owner,
                repo=repo,
                count=len(prs),
                state=state,
            )

            return prs

    async def get_pull_request(
        self,
        access_token: str,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> Dict[str, Any]:
        """
        Get a specific pull request.

        Args:
            access_token: Valid GitHub access token
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            Pull request object

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            pr_data = response.json()

            logger.info(
                "github_pull_request_fetched",
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                state=pr_data.get("state"),
            )

            return pr_data
