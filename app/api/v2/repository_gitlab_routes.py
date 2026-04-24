# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import secrets
import structlog
import uuid

from app.auth import get_current_active_user
from app.core.config import get_settings
from app.core.schemas.repository import ConnectRepositoryRequest, RepositoryConnectionResponse, RepositoryListResponse
from app.dependencies import get_db
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.services.oauth.token_manager import get_token_manager

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


@router.get(
    "/gitlab",
    response_model=RepositoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List GitLab Projects",
    description="List all projects accessible via GitLab OAuth connection.",
)
async def list_gitlab_projects(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Items per page"),
    sort: str = Query("updated_at", description="Sort field"),
    direction: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryListResponse:
    try:
        user = current_user_data["user"]
        token_manager = get_token_manager(settings.oauth_token_encryption_key)
        oauth_connection = await token_manager.get_oauth_connection(db=db, user_id=user.user_id, provider="gitlab")
        if not oauth_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GitLab OAuth connection found. Please connect your GitLab account first.",
            )

        access_token = token_manager.get_decrypted_token(oauth_connection)
        gitlab_url = getattr(settings, "gitlab_instance_url", "https://gitlab.com")
        gitlab_provider = GitLabOAuthProvider(
            client_id=settings.gitlab_oauth_client_id or "",
            client_secret=settings.gitlab_oauth_client_secret or "",
            redirect_uri=settings.gitlab_oauth_redirect_uri or "",
            scopes=[],
            gitlab_url=gitlab_url,
        )
        projects = await gitlab_provider.get_user_projects(
            access_token=access_token,
            page=page,
            per_page=per_page,
            sort=sort,
            direction=direction,
        )

        from app.adapters.database.postgres.models import RepositoryConnectionTable

        connected_repos = (
            db.query(RepositoryConnectionTable)
            .filter(
                RepositoryConnectionTable.user_id == user.user_id,
                RepositoryConnectionTable.provider == "gitlab",
            )
            .all()
        )
        connected_ids = {repo.provider_repository_id for repo in connected_repos}

        repositories = [
            {
                "id": project["id"],
                "name": project["name"],
                "full_name": project["path_with_namespace"],
                "description": project.get("description"),
                "private": project.get("visibility") == "private",
                "url": project["web_url"],
                "default_branch": project.get("default_branch", "main"),
                "is_connected": str(project["id"]) in connected_ids,
            }
            for project in projects
        ]

        logger.info("gitlab_projects_listed", user_id=user.user_id, count=len(repositories), page=page)
        return RepositoryListResponse(repositories=repositories, total=len(repositories), page=page, per_page=per_page)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("list_gitlab_projects_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list GitLab projects: {str(exc)}",
        ) from exc


@router.post(
    "/gitlab/connect",
    response_model=RepositoryConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect GitLab Project",
    description="Connect a GitLab project for monitoring and auto-fix.",
)
async def connect_gitlab_project(
    request: ConnectRepositoryRequest,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryConnectionResponse:
    try:
        user = current_user_data["user"]
        token_manager = get_token_manager(settings.oauth_token_encryption_key)
        oauth_connection = await token_manager.get_oauth_connection(db=db, user_id=user.user_id, provider="gitlab")
        if not oauth_connection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No GitLab OAuth connection found")

        access_token = token_manager.get_decrypted_token(oauth_connection)
        gitlab_url = getattr(settings, "gitlab_instance_url", "https://gitlab.com")
        gitlab_provider = GitLabOAuthProvider(
            client_id=settings.gitlab_oauth_client_id or "",
            client_secret=settings.gitlab_oauth_client_secret or "",
            redirect_uri=settings.gitlab_oauth_redirect_uri or "",
            scopes=[],
            gitlab_url=gitlab_url,
        )
        project = await gitlab_provider.get_project(
            access_token=access_token,
            project_id=request.repository_full_name,
        )

        from app.adapters.database.postgres.models import RepositoryConnectionTable

        repo_connection = RepositoryConnectionTable(
            id=str(uuid.uuid4()),
            user_id=user.user_id,
            oauth_connection_id=oauth_connection.id,
            provider="gitlab",
            provider_repository_id=str(project["id"]),
            repository_full_name=project["path_with_namespace"],
            repository_name=project["name"],
            default_branch=project.get("default_branch", "main"),
            is_private=project.get("visibility") == "private",
            auto_pr_enabled=request.auto_pr_enabled,
            is_enabled=True,
        )
        db.add(repo_connection)
        db.flush()

        if request.setup_webhook:
            try:
                webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/gitlab/{user.user_id}"
                webhook_token = secrets.token_urlsafe(32)
                hook = await gitlab_provider.create_project_hook(
                    access_token=access_token,
                    project_id=str(project["id"]),
                    webhook_url=webhook_url,
                    token=webhook_token,
                    events=["pipeline_events", "merge_requests_events", "push_events"],
                )
                repo_connection.webhook_id = str(hook.get("id"))
                repo_connection.webhook_url = webhook_url
                logger.info(
                    "gitlab_webhook_created",
                    user_id=user.user_id,
                    project=project["path_with_namespace"],
                    webhook_id=hook.get("id"),
                )
            except Exception as exc:
                logger.warning(
                    "gitlab_webhook_creation_failed",
                    error=str(exc),
                    project=project["path_with_namespace"],
                )

        db.commit()
        db.refresh(repo_connection)

        logger.info(
            "gitlab_project_connected",
            user_id=user.user_id,
            project=project["path_with_namespace"],
            connection_id=repo_connection.id,
        )
        return RepositoryConnectionResponse(
            id=repo_connection.id,
            user_id=repo_connection.user_id,
            provider="gitlab",
            repository_full_name=repo_connection.repository_full_name,
            repository_name=repo_connection.repository_name,
            default_branch=repo_connection.default_branch,
            is_private=repo_connection.is_private,
            auto_pr_enabled=repo_connection.auto_pr_enabled,
            is_enabled=repo_connection.is_enabled,
            webhook_url=repo_connection.webhook_url,
            created_at=repo_connection.created_at or datetime.now(timezone.utc),
            updated_at=repo_connection.updated_at or datetime.now(timezone.utc),
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("connect_gitlab_project_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect GitLab project: {str(exc)}",
        ) from exc
