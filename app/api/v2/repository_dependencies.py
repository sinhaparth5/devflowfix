# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from app.core.config import get_settings
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.services.oauth.token_manager import get_token_manager
from app.services.repository.repository_manager import RepositoryManager
from app.services.webhook.webhook_manager import WebhookManager

settings = get_settings()


def get_repository_manager() -> RepositoryManager:
    github_provider = GitHubOAuthProvider(
        client_id=settings.github_oauth_client_id or "",
        client_secret=settings.github_oauth_client_secret or "",
        redirect_uri=settings.github_oauth_redirect_uri or "",
        scopes=[],
    )
    token_manager = get_token_manager(settings.oauth_token_encryption_key)

    return RepositoryManager(
        github_provider=github_provider,
        token_manager=token_manager,
    )


def get_webhook_manager() -> WebhookManager:
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

    token_manager = get_token_manager(settings.oauth_token_encryption_key)

    return WebhookManager(
        token_manager=token_manager,
        github_provider=github_provider,
        gitlab_provider=gitlab_provider,
        webhook_base_url=settings.webhook_base_url or "",
    )
