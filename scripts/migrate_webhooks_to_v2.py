#!/usr/bin/env python3
# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Migration script to update existing webhooks to use v2 endpoints.

This script:
1. Finds all repository connections with webhooks
2. Checks if they're using v1 endpoints
3. Updates webhooks to v2 endpoints with proper secrets
4. Re-creates webhooks if necessary
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.adapters.database.postgres.connection import get_db_connection
from app.adapters.database.postgres.models import RepositoryConnectionTable
from app.services.webhook.webhook_manager import WebhookManager
from app.services.oauth.token_manager import get_token_manager
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.core.config import get_settings
import structlog

logger = structlog.get_logger(__name__)
settings = get_settings()


async def migrate_webhooks():
    """Migrate existing webhooks to v2 endpoints."""

    # Get database session
    engine = get_db_connection()
    db = Session(engine)

    try:
        # Get all repository connections with webhooks
        repo_connections = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.webhook_id.isnot(None)
        ).all()

        logger.info(f"Found {len(repo_connections)} repositories with webhooks")

        # Initialize managers
        token_manager = get_token_manager(settings.oauth_token_encryption_key)
        github_provider = GitHubOAuthProvider(
            client_id=settings.github_oauth_client_id or "",
            client_secret=settings.github_oauth_client_secret or "",
            redirect_uri=settings.github_oauth_redirect_uri or "",
            scopes=[],
        )

        gitlab_provider = None
        if settings.gitlab_oauth_client_id:
            gitlab_provider = GitLabOAuthProvider(
                client_id=settings.gitlab_oauth_client_id or "",
                client_secret=settings.gitlab_oauth_client_secret or "",
                redirect_uri=settings.gitlab_oauth_redirect_uri or "",
                scopes=[],
            )

        webhook_manager = WebhookManager(
            token_manager=token_manager,
            github_provider=github_provider,
            gitlab_provider=gitlab_provider,
            webhook_base_url=settings.webhook_base_url or "",
        )

        # Statistics
        stats = {
            "total": len(repo_connections),
            "v1_endpoints": 0,
            "missing_secrets": 0,
            "updated": 0,
            "failed": 0,
            "skipped": 0,
        }

        for repo_conn in repo_connections:
            logger.info(
                "processing_repository",
                repository=repo_conn.repository_full_name,
                webhook_id=repo_conn.webhook_id,
                webhook_url=repo_conn.webhook_url,
            )

            # Check if using v1 endpoint
            if repo_conn.webhook_url and "/api/v1/webhook/" in repo_conn.webhook_url:
                logger.warning(
                    "v1_endpoint_detected",
                    repository=repo_conn.repository_full_name,
                    current_url=repo_conn.webhook_url,
                )
                stats["v1_endpoints"] += 1

                # Delete old webhook and recreate with v2
                try:
                    # Delete old webhook
                    await webhook_manager.delete_webhook(
                        db=db,
                        repository_connection_id=repo_conn.id,
                    )

                    # Create new webhook
                    result = await webhook_manager.create_webhook(
                        db=db,
                        repository_connection_id=repo_conn.id,
                        events=["workflow_run", "pull_request", "push"],
                    )

                    logger.info(
                        "webhook_migrated_to_v2",
                        repository=repo_conn.repository_full_name,
                        new_webhook_id=result["webhook_id"],
                    )
                    stats["updated"] += 1

                except Exception as e:
                    logger.error(
                        "migration_failed",
                        repository=repo_conn.repository_full_name,
                        error=str(e),
                    )
                    stats["failed"] += 1
                    continue

            # Check if secret is missing
            elif not repo_conn.webhook_secret:
                logger.warning(
                    "missing_webhook_secret",
                    repository=repo_conn.repository_full_name,
                )
                stats["missing_secrets"] += 1

                # Recreate webhook with secret
                try:
                    # Delete and recreate
                    await webhook_manager.delete_webhook(
                        db=db,
                        repository_connection_id=repo_conn.id,
                    )

                    result = await webhook_manager.create_webhook(
                        db=db,
                        repository_connection_id=repo_conn.id,
                    )

                    logger.info(
                        "webhook_recreated_with_secret",
                        repository=repo_conn.repository_full_name,
                        webhook_id=result["webhook_id"],
                    )
                    stats["updated"] += 1

                except Exception as e:
                    logger.error(
                        "recreation_failed",
                        repository=repo_conn.repository_full_name,
                        error=str(e),
                    )
                    stats["failed"] += 1

            else:
                logger.info(
                    "webhook_already_v2",
                    repository=repo_conn.repository_full_name,
                )
                stats["skipped"] += 1

        # Print summary
        print("\n=== Migration Summary ===")
        print(f"Total repositories: {stats['total']}")
        print(f"V1 endpoints found: {stats['v1_endpoints']}")
        print(f"Missing secrets: {stats['missing_secrets']}")
        print(f"Successfully updated: {stats['updated']}")
        print(f"Failed: {stats['failed']}")
        print(f"Skipped (already v2): {stats['skipped']}")
        print("=========================\n")

        db.commit()

    except Exception as e:
        logger.error("migration_script_failed", error=str(e), exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting webhook migration to v2...")
    print("This will update webhooks to use /api/v2/webhooks/{provider} endpoints")
    print("and ensure all webhooks have proper secrets configured.\n")

    response = input("Do you want to continue? (yes/no): ")
    if response.lower() != "yes":
        print("Migration cancelled.")
        sys.exit(0)

    asyncio.run(migrate_webhooks())
    print("Migration completed!")
