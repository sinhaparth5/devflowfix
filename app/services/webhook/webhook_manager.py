# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Webhook Manager Service

Handles automatic webhook creation, deletion, and management for GitHub/GitLab repositories.
"""

import secrets
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import structlog

from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.services.oauth.token_manager import TokenManager
from app.adapters.database.postgres.models import RepositoryConnectionTable, OAuthConnectionTable
from app.core.config import Settings

logger = structlog.get_logger(__name__)


class WebhookManager:
    """
    Manages webhook lifecycle for repository connections.

    Automatically creates, updates, and deletes webhooks when users
    connect/disconnect repositories.
    """

    def __init__(
        self,
        token_manager: TokenManager,
        github_provider: GitHubOAuthProvider,
        gitlab_provider: Optional[GitLabOAuthProvider] = None,
        webhook_base_url: str = "",
    ):
        """
        Initialize webhook manager.

        Args:
            token_manager: Token manager for OAuth token encryption/decryption
            github_provider: GitHub OAuth provider for API calls
            gitlab_provider: GitLab OAuth provider (optional)
            webhook_base_url: Base URL for webhook endpoints (e.g., https://api.devflowfix.com)
        """
        self.token_manager = token_manager
        self.github_provider = github_provider
        self.gitlab_provider = gitlab_provider
        self.webhook_base_url = webhook_base_url.rstrip('/')

    def generate_webhook_secret(self) -> str:
        """
        Generate a secure random webhook secret.

        Returns:
            Random 32-byte URL-safe secret
        """
        return secrets.token_urlsafe(32)

    async def create_webhook(
        self,
        db: Session,
        repository_connection_id: str,
        events: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create webhook for a repository connection.

        Args:
            db: Database session
            repository_connection_id: Repository connection ID
            events: List of events to subscribe to (default: workflow_run, pull_request, push)

        Returns:
            Webhook creation result with webhook_id, url, events

        Raises:
            ValueError: If repository connection not found or invalid
            PermissionError: If OAuth token lacks webhook permissions
            Exception: If webhook creation fails
        """
        # Get repository connection
        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.id == repository_connection_id
        ).first()

        if not repo_conn:
            raise ValueError(f"Repository connection {repository_connection_id} not found")

        # Get OAuth connection
        oauth_conn = db.query(OAuthConnectionTable).filter(
            OAuthConnectionTable.id == repo_conn.oauth_connection_id
        ).first()

        if not oauth_conn:
            raise ValueError(f"OAuth connection not found for repository {repo_conn.repository_full_name}")

        # Get access token
        access_token = self.token_manager.get_decrypted_token(oauth_conn)

        # Default events if not specified
        if events is None:
            events = ["workflow_run", "pull_request", "push"]

        # Generate webhook secret
        webhook_secret = self.generate_webhook_secret()

        # Determine webhook URL based on provider
        if repo_conn.provider == "github":
            webhook_url = f"{self.webhook_base_url}/api/v2/webhooks/github"
            result = await self._create_github_webhook(
                access_token=access_token,
                repository_full_name=repo_conn.repository_full_name,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                events=events,
            )
        elif repo_conn.provider == "gitlab":
            if not self.gitlab_provider:
                raise ValueError("GitLab provider not configured")
            webhook_url = f"{self.webhook_base_url}/api/v2/webhooks/gitlab"
            result = await self._create_gitlab_webhook(
                access_token=access_token,
                repository_full_name=repo_conn.repository_full_name,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                events=events,
            )
        else:
            raise ValueError(f"Unsupported provider: {repo_conn.provider}")

        # Encrypt webhook secret before storing
        encrypted_secret = self.token_manager.encrypt_token(webhook_secret)

        # Update repository connection with webhook details
        repo_conn.webhook_id = str(result["id"])
        repo_conn.webhook_url = webhook_url
        repo_conn.webhook_secret = encrypted_secret
        repo_conn.webhook_events = {"events": events}  # Store as JSON
        repo_conn.webhook_status = "active"
        repo_conn.webhook_created_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(
            "webhook_created",
            repository=repo_conn.repository_full_name,
            webhook_id=result["id"],
            events=events,
            provider=repo_conn.provider,
        )

        return {
            "success": True,
            "webhook_id": str(result["id"]),
            "webhook_url": webhook_url,
            "events": events,
            "repository_full_name": repo_conn.repository_full_name,
        }

    async def _create_github_webhook(
        self,
        access_token: str,
        repository_full_name: str,
        webhook_url: str,
        webhook_secret: str,
        events: List[str],
    ) -> Dict[str, Any]:
        """
        Create webhook on GitHub repository.

        Args:
            access_token: GitHub OAuth access token
            repository_full_name: Repository (owner/repo)
            webhook_url: Webhook endpoint URL
            webhook_secret: Webhook secret for signature verification
            events: Events to subscribe to

        Returns:
            GitHub webhook object

        Raises:
            Exception: If webhook creation fails
        """
        owner, repo = repository_full_name.split("/")

        try:
            webhook_data = await self.github_provider.create_webhook(
                access_token=access_token,
                owner=owner,
                repo=repo,
                webhook_url=webhook_url,
                secret=webhook_secret,
                events=events,
            )

            return webhook_data

        except Exception as e:
            logger.error(
                "github_webhook_creation_failed",
                repository=repository_full_name,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _create_gitlab_webhook(
        self,
        access_token: str,
        repository_full_name: str,
        webhook_url: str,
        webhook_secret: str,
        events: List[str],
    ) -> Dict[str, Any]:
        """
        Create webhook on GitLab project.

        Args:
            access_token: GitLab OAuth access token
            repository_full_name: Project path
            webhook_url: Webhook endpoint URL
            webhook_secret: Webhook secret (token)
            events: Events to subscribe to

        Returns:
            GitLab webhook object

        Raises:
            Exception: If webhook creation fails
        """
        try:
            webhook_data = await self.gitlab_provider.create_webhook(
                access_token=access_token,
                project_path=repository_full_name,
                webhook_url=webhook_url,
                token=webhook_secret,
                events=events,
            )

            return webhook_data

        except Exception as e:
            logger.error(
                "gitlab_webhook_creation_failed",
                project=repository_full_name,
                error=str(e),
                exc_info=True,
            )
            raise

    async def delete_webhook(
        self,
        db: Session,
        repository_connection_id: str,
    ) -> bool:
        """
        Delete webhook for a repository connection.

        Args:
            db: Database session
            repository_connection_id: Repository connection ID

        Returns:
            True if webhook deleted successfully, False otherwise

        Raises:
            ValueError: If repository connection not found
        """
        # Get repository connection
        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.id == repository_connection_id
        ).first()

        if not repo_conn:
            raise ValueError(f"Repository connection {repository_connection_id} not found")

        # If no webhook configured, nothing to delete
        if not repo_conn.webhook_id:
            logger.info(
                "no_webhook_to_delete",
                repository=repo_conn.repository_full_name,
            )
            return True

        # Get OAuth connection
        oauth_conn = db.query(OAuthConnectionTable).filter(
            OAuthConnectionTable.id == repo_conn.oauth_connection_id
        ).first()

        if not oauth_conn:
            logger.warning(
                "oauth_connection_not_found_for_webhook_deletion",
                repository=repo_conn.repository_full_name,
            )
            # Continue with database cleanup even if OAuth missing
            repo_conn.webhook_id = None
            repo_conn.webhook_url = None
            repo_conn.webhook_secret = None
            repo_conn.webhook_status = "inactive"
            db.commit()
            return True

        # Get access token
        access_token = self.token_manager.get_decrypted_token(oauth_conn)

        # Delete webhook from provider
        try:
            if repo_conn.provider == "github":
                success = await self._delete_github_webhook(
                    access_token=access_token,
                    repository_full_name=repo_conn.repository_full_name,
                    webhook_id=int(repo_conn.webhook_id),
                )
            elif repo_conn.provider == "gitlab":
                if not self.gitlab_provider:
                    raise ValueError("GitLab provider not configured")
                success = await self._delete_gitlab_webhook(
                    access_token=access_token,
                    repository_full_name=repo_conn.repository_full_name,
                    webhook_id=int(repo_conn.webhook_id),
                )
            else:
                raise ValueError(f"Unsupported provider: {repo_conn.provider}")

        except Exception as e:
            logger.warning(
                "webhook_deletion_failed",
                repository=repo_conn.repository_full_name,
                webhook_id=repo_conn.webhook_id,
                error=str(e),
            )
            # Continue with database cleanup even if deletion fails
            success = False

        # Clean up database
        repo_conn.webhook_id = None
        repo_conn.webhook_url = None
        repo_conn.webhook_secret = None
        repo_conn.webhook_events = None
        repo_conn.webhook_status = "inactive"

        db.commit()

        logger.info(
            "webhook_deleted",
            repository=repo_conn.repository_full_name,
            success=success,
        )

        return success

    async def _delete_github_webhook(
        self,
        access_token: str,
        repository_full_name: str,
        webhook_id: int,
    ) -> bool:
        """
        Delete webhook from GitHub repository.

        Args:
            access_token: GitHub OAuth access token
            repository_full_name: Repository (owner/repo)
            webhook_id: GitHub webhook ID

        Returns:
            True if deleted successfully
        """
        owner, repo = repository_full_name.split("/")

        try:
            success = await self.github_provider.delete_webhook(
                access_token=access_token,
                owner=owner,
                repo=repo,
                hook_id=webhook_id,
            )
            return success

        except Exception as e:
            logger.error(
                "github_webhook_deletion_failed",
                repository=repository_full_name,
                webhook_id=webhook_id,
                error=str(e),
            )
            return False

    async def _delete_gitlab_webhook(
        self,
        access_token: str,
        repository_full_name: str,
        webhook_id: int,
    ) -> bool:
        """
        Delete webhook from GitLab project.

        Args:
            access_token: GitLab OAuth access token
            repository_full_name: Project path
            webhook_id: GitLab webhook ID

        Returns:
            True if deleted successfully
        """
        try:
            success = await self.gitlab_provider.delete_webhook(
                access_token=access_token,
                project_path=repository_full_name,
                hook_id=webhook_id,
            )
            return success

        except Exception as e:
            logger.error(
                "gitlab_webhook_deletion_failed",
                project=repository_full_name,
                webhook_id=webhook_id,
                error=str(e),
            )
            return False

    @staticmethod
    def verify_github_signature(
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """
        Verify GitHub webhook signature.

        GitHub sends: X-Hub-Signature-256: sha256=<hash>

        Args:
            payload: Raw request body
            signature: Signature from X-Hub-Signature-256 header
            secret: Webhook secret (decrypted)

        Returns:
            True if signature is valid

        Raises:
            ValueError: If signature format is invalid
        """
        if not signature.startswith("sha256="):
            raise ValueError("Invalid signature format")

        expected_signature = "sha256=" + hmac.new(
            key=secret.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    @staticmethod
    def verify_gitlab_signature(
        token_header: str,
        secret: str,
    ) -> bool:
        """
        Verify GitLab webhook signature.

        GitLab sends: X-Gitlab-Token: <secret>

        Args:
            token_header: Token from X-Gitlab-Token header
            secret: Webhook secret (decrypted)

        Returns:
            True if token matches
        """
        return hmac.compare_digest(token_header, secret)
