# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Repository Manager Service

Handles repository connections, webhook management, and GitHub API interactions.
"""

import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
import structlog

from app.adapters.database.postgres.models import (
    RepositoryConnectionTable,
    OAuthConnectionTable,
)
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.token_manager import TokenManager

logger = structlog.get_logger(__name__)


class RepositoryManager:
    """
    Manages repository connections and webhooks.

    Responsibilities:
    - List user's repositories from GitHub
    - Connect/disconnect repositories
    - Setup/delete webhooks
    - Manage repository metadata
    """

    def __init__(
        self,
        github_provider: GitHubOAuthProvider,
        token_manager: TokenManager,
    ):
        """
        Initialize repository manager.

        Args:
            github_provider: GitHub OAuth provider instance
            token_manager: Token manager for decryption
        """
        self.github_provider = github_provider
        self.token_manager = token_manager

    def generate_repository_connection_id(self) -> str:
        """
        Generate unique repository connection ID.

        Returns:
            ID with format: rpc_<32_hex_chars>
        """
        return f"rpc_{uuid.uuid4().hex}"

    async def list_user_repositories(
        self,
        db: Session,
        user_id: str,
        page: int = 1,
        per_page: int = 30,
        sort: str = "updated",
        direction: str = "desc",
    ) -> Dict[str, Any]:
        """
        List repositories accessible to user via OAuth.

        Args:
            db: Database session
            user_id: User ID
            page: Page number (1-indexed)
            per_page: Items per page (max 100)
            sort: Sort field (created, updated, pushed, full_name)
            direction: Sort direction (asc, desc)

        Returns:
            Dict with repositories list and pagination info

        Raises:
            ValueError: If no GitHub OAuth connection found
        """
        # Get user's GitHub OAuth connection
        oauth_connection = await self.token_manager.get_oauth_connection(
            db=db,
            user_id=user_id,
            provider="github",
        )

        if not oauth_connection:
            raise ValueError("No GitHub OAuth connection found for this user")

        # Get decrypted access token
        access_token = self.token_manager.get_decrypted_token(oauth_connection)

        # Fetch repositories from GitHub
        repos = await self.github_provider.get_user_repositories(
            access_token=access_token,
            page=page,
            per_page=per_page,
            sort=sort,
            direction=direction,
        )

        # Get already connected repositories
        connected_repos = (
            db.query(RepositoryConnectionTable)
            .filter(
                RepositoryConnectionTable.oauth_connection_id == oauth_connection.id,
                RepositoryConnectionTable.is_enabled == True,
            )
            .all()
        )
        connected_repo_ids = {str(conn.repository_id) for conn in connected_repos}

        # Mark which repos are already connected
        for repo in repos:
            repo["is_connected"] = str(repo["id"]) in connected_repo_ids

        return {
            "repositories": repos,
            "total": len(repos),
            "page": page,
            "per_page": per_page,
            "has_next": len(repos) == per_page,
        }

    async def connect_repository(
        self,
        db: Session,
        user_id: str,
        repository_full_name: str,
        auto_pr_enabled: bool = True,
        setup_webhook: bool = True,
        webhook_events: Optional[List[str]] = None,
        webhook_secret: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ) -> RepositoryConnectionTable:
        """
        Connect a repository to DevFlowFix.

        Args:
            db: Database session
            user_id: User ID
            repository_full_name: Repository full name (owner/repo)
            auto_pr_enabled: Enable automatic PR creation
            setup_webhook: Whether to setup webhook
            webhook_events: Events to subscribe to
            webhook_secret: Webhook secret for signature validation
            webhook_url: Webhook URL (defaults to /api/v1/webhook/github/{user_id})

        Returns:
            Created repository connection

        Raises:
            ValueError: If OAuth connection not found or repository already connected
        """
        # Get user's GitHub OAuth connection
        oauth_connection = await self.token_manager.get_oauth_connection(
            db=db,
            user_id=user_id,
            provider="github",
        )

        if not oauth_connection:
            raise ValueError("No GitHub OAuth connection found for this user")

        # Check if repository is already connected
        existing = (
            db.query(RepositoryConnectionTable)
            .filter(
                and_(
                    RepositoryConnectionTable.oauth_connection_id == oauth_connection.id,
                    RepositoryConnectionTable.repository_full_name == repository_full_name,
                    RepositoryConnectionTable.is_enabled == True,
                )
            )
            .first()
        )

        if existing:
            raise ValueError(f"Repository {repository_full_name} is already connected")

        # Get decrypted access token
        access_token = self.token_manager.get_decrypted_token(oauth_connection)

        # Get repository info from GitHub to validate and get ID
        owner, repo = repository_full_name.split("/")
        try:
            repo_info = await self.github_provider.get_repository(
                access_token=access_token,
                owner=owner,
                repo=repo,
            )
        except Exception as e:
            logger.error(
                "failed_to_fetch_repository",
                repository=repository_full_name,
                error=str(e),
            )
            raise ValueError(f"Failed to fetch repository: {str(e)}")

        # Setup webhook if requested
        webhook_id = None
        if setup_webhook:
            try:
                if webhook_events is None:
                    webhook_events = ["workflow_run", "pull_request", "push"]

                webhook_result = await self.github_provider.create_webhook(
                    access_token=access_token,
                    owner=owner,
                    repo=repo,
                    webhook_url=webhook_url or f"/api/v1/webhook/github/{user_id}",
                    secret=webhook_secret or "",
                    events=webhook_events,
                )
                webhook_id = str(webhook_result.get("id"))
                logger.info(
                    "webhook_created",
                    repository=repository_full_name,
                    webhook_id=webhook_id,
                )
            except Exception as e:
                logger.warning(
                    "webhook_setup_failed",
                    repository=repository_full_name,
                    error=str(e),
                )
                # Continue without webhook - user can setup manually

        # Create repository connection
        connection = RepositoryConnectionTable(
            id=self.generate_repository_connection_id(),
            user_id=user_id,
            oauth_connection_id=oauth_connection.id,
            provider="github",
            repository_id=str(repo_info["id"]),
            repository_full_name=repository_full_name,
            repository_name=repo,
            owner_name=owner,
            is_private=repo_info.get("private", False),
            webhook_id=webhook_id,
            webhook_url=webhook_url,
            is_enabled=True,
            auto_pr_enabled=auto_pr_enabled,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_event_at=datetime.now(timezone.utc) if webhook_id else None,
        )

        db.add(connection)
        db.flush()

        logger.info(
            "repository_connected",
            user_id=user_id,
            repository=repository_full_name,
            connection_id=connection.id,
            webhook_id=webhook_id,
        )

        return connection

    async def disconnect_repository(
        self,
        db: Session,
        user_id: str,
        connection_id: str,
        delete_webhook: bool = True,
    ) -> Dict[str, Any]:
        """
        Disconnect a repository from DevFlowFix.

        Args:
            db: Database session
            user_id: User ID
            connection_id: Repository connection ID
            delete_webhook: Whether to delete webhook from GitHub

        Returns:
            Dict with disconnection details

        Raises:
            ValueError: If connection not found
        """
        # Get connection
        connection = (
            db.query(RepositoryConnectionTable)
            .join(
                OAuthConnectionTable,
                RepositoryConnectionTable.oauth_connection_id == OAuthConnectionTable.id,
            )
            .filter(
                and_(
                    RepositoryConnectionTable.id == connection_id,
                    OAuthConnectionTable.user_id == user_id,
                    RepositoryConnectionTable.is_enabled == True,
                )
            )
            .first()
        )

        if not connection:
            raise ValueError("Repository connection not found")

        webhook_deleted = False

        # Delete webhook if requested and exists
        if delete_webhook and connection.webhook_id:
            try:
                oauth_connection = await self.token_manager.get_oauth_connection(
                    db=db,
                    user_id=user_id,
                    provider="github",
                )
                access_token = self.token_manager.get_decrypted_token(oauth_connection)

                owner, repo = connection.repository_full_name.split("/")
                await self.github_provider.delete_webhook(
                    access_token=access_token,
                    owner=owner,
                    repo=repo,
                    webhook_id=int(connection.webhook_id),
                )
                webhook_deleted = True
                logger.info(
                    "webhook_deleted",
                    repository=connection.repository_full_name,
                    webhook_id=connection.webhook_id,
                )
            except Exception as e:
                logger.warning(
                    "webhook_deletion_failed",
                    repository=connection.repository_full_name,
                    error=str(e),
                )

        # Soft delete connection
        connection.is_enabled = False
        connection.updated_at = datetime.now(timezone.utc)

        db.flush()

        logger.info(
            "repository_disconnected",
            user_id=user_id,
            repository=connection.repository_full_name,
            connection_id=connection_id,
            webhook_deleted=webhook_deleted,
        )

        return {
            "connection_id": connection_id,
            "repository_full_name": connection.repository_full_name,
            "webhook_deleted": webhook_deleted,
        }

    async def update_repository_connection(
        self,
        db: Session,
        user_id: str,
        connection_id: str,
        is_enabled: Optional[bool] = None,
        auto_pr_enabled: Optional[bool] = None,
    ) -> RepositoryConnectionTable:
        """
        Update repository connection settings.

        Args:
            db: Database session
            user_id: User ID
            connection_id: Repository connection ID
            is_enabled: Enable/disable monitoring
            auto_pr_enabled: Enable/disable auto PR

        Returns:
            Updated repository connection

        Raises:
            ValueError: If connection not found
        """
        # Get connection
        connection = (
            db.query(RepositoryConnectionTable)
            .join(
                OAuthConnectionTable,
                RepositoryConnectionTable.oauth_connection_id == OAuthConnectionTable.id,
            )
            .filter(
                and_(
                    RepositoryConnectionTable.id == connection_id,
                    OAuthConnectionTable.user_id == user_id,
                )
            )
            .first()
        )

        if not connection:
            raise ValueError("Repository connection not found")

        # Update fields
        if is_enabled is not None:
            connection.is_enabled = is_enabled
        if auto_pr_enabled is not None:
            connection.auto_pr_enabled = auto_pr_enabled

        connection.updated_at = datetime.now(timezone.utc)

        db.flush()

        logger.info(
            "repository_connection_updated",
            user_id=user_id,
            connection_id=connection_id,
            is_enabled=connection.is_enabled,
            auto_pr_enabled=connection.auto_pr_enabled,
        )

        return connection

    async def get_repository_connections(
        self,
        db: Session,
        user_id: str,
        include_disabled: bool = False,
    ) -> List[RepositoryConnectionTable]:
        """
        Get all repository connections for a user.

        Args:
            db: Database session
            user_id: User ID
            include_disabled: Include disabled connections

        Returns:
            List of repository connections
        """
        query = (
            db.query(RepositoryConnectionTable)
            .join(
                OAuthConnectionTable,
                RepositoryConnectionTable.oauth_connection_id == OAuthConnectionTable.id,
            )
            .filter(OAuthConnectionTable.user_id == user_id)
        )

        if not include_disabled:
            query = query.filter(RepositoryConnectionTable.is_enabled == True)

        connections = query.order_by(RepositoryConnectionTable.created_at.desc()).all()

        return connections

    async def get_repository_stats(
        self,
        db: Session,
        user_id: str,
    ) -> Dict[str, int]:
        """
        Get statistics for user's repository connections.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Dict with statistics
        """
        all_connections = await self.get_repository_connections(
            db=db,
            user_id=user_id,
            include_disabled=True,
        )

        active_connections = [c for c in all_connections if c.is_enabled]
        inactive_connections = [c for c in all_connections if not c.is_enabled]
        webhooks = [c for c in active_connections if c.webhook_id]
        auto_pr = [c for c in active_connections if c.auto_pr_enabled]

        return {
            "total_repositories": len(all_connections),
            "active_repositories": len(active_connections),
            "inactive_repositories": len(inactive_connections),
            "total_webhooks": len(webhooks),
            "repositories_with_auto_pr": len(auto_pr),
        }
