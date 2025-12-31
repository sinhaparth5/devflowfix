# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Repository Management API Endpoints

Handles repository connections, webhook management, and GitHub repository operations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog

from app.core.config import get_settings
from app.core.schemas.repository import (
    RepositoryListResponse,
    GitHubRepositoryResponse,
    ConnectRepositoryRequest,
    RepositoryConnectionResponse,
    RepositoryConnectionListResponse,
    UpdateRepositoryConnectionRequest,
    DisconnectRepositoryResponse,
    WebhookSetupRequest,
    WebhookSetupResponse,
    RepositoryStatsResponse,
)
from app.dependencies import get_db, get_current_active_user
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.services.oauth.token_manager import get_token_manager
from app.services.repository.repository_manager import RepositoryManager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/repositories", tags=["Repositories"])
settings = get_settings()


def get_repository_manager() -> RepositoryManager:
    """
    Get repository manager instance.

    Returns:
        RepositoryManager instance
    """
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


@router.get(
    "/github",
    response_model=RepositoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List GitHub Repositories",
    description="List all repositories accessible via GitHub OAuth connection.",
)
async def list_github_repositories(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Items per page"),
    sort: str = Query("updated", description="Sort field (created, updated, pushed, full_name)"),
    direction: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryListResponse:
    """
    List GitHub repositories accessible to the user.

    **Requirements:**
    - User must have an active GitHub OAuth connection

    **Query Parameters:**
    - page: Page number (default: 1)
    - per_page: Items per page, max 100 (default: 30)
    - sort: Sort by created, updated, pushed, or full_name (default: updated)
    - direction: asc or desc (default: desc)

    **Returns:**
    - List of repositories with connection status
    - Pagination information
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        result = await repo_manager.list_user_repositories(
            db=db,
            user_id=user.user_id,
            page=page,
            per_page=per_page,
            sort=sort,
            direction=direction,
        )

        logger.info(
            "repositories_listed",
            user_id=user.user_id,
            count=result["total"],
            page=page,
        )

        return RepositoryListResponse(**result)

    except ValueError as e:
        logger.error(
            "list_repositories_failed",
            error=str(e),
            user_id=current_user_data["user"].user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "list_repositories_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch repositories: {str(e)}"
        )


@router.post(
    "/connect",
    response_model=RepositoryConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect Repository",
    description="Connect a GitHub repository to DevFlowFix for monitoring.",
)
async def connect_repository(
    request: ConnectRepositoryRequest,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryConnectionResponse:
    """
    Connect a repository to DevFlowFix.

    **Flow:**
    1. Validates repository access via OAuth
    2. Optionally sets up webhook in repository
    3. Creates repository connection record
    4. Returns connection details

    **Request Body:**
    - repository_full_name: Full repository name (owner/repo)
    - auto_pr_enabled: Enable automatic PR creation (default: true)
    - setup_webhook: Automatically setup webhook (default: true)
    - webhook_events: Events to subscribe to (default: workflow_run, pull_request, push)

    **Returns:**
    - Repository connection details
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        # Build webhook URL
        webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/github/{user.user_id}" if settings.webhook_base_url else None

        connection = await repo_manager.connect_repository(
            db=db,
            user_id=user.user_id,
            repository_full_name=request.repository_full_name,
            auto_pr_enabled=request.auto_pr_enabled,
            setup_webhook=request.setup_webhook,
            webhook_events=request.webhook_events,
            webhook_url=webhook_url,
        )

        db.commit()

        logger.info(
            "repository_connected",
            user_id=user.user_id,
            repository=request.repository_full_name,
            connection_id=connection.id,
        )

        return RepositoryConnectionResponse.from_orm(connection)

    except ValueError as e:
        db.rollback()
        logger.error(
            "connect_repository_failed",
            error=str(e),
            repository=request.repository_full_name,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        logger.error(
            "connect_repository_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect repository: {str(e)}"
        )


@router.get(
    "/connections",
    response_model=RepositoryConnectionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Repository Connections",
    description="Get all connected repositories for the current user.",
)
async def list_repository_connections(
    include_disabled: bool = Query(False, description="Include disabled connections"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryConnectionListResponse:
    """
    List all repository connections for current user.

    **Query Parameters:**
    - include_disabled: Include disabled connections (default: false)

    **Returns:**
    - List of repository connections
    - Total count
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        connections = await repo_manager.get_repository_connections(
            db=db,
            user_id=user.user_id,
            include_disabled=include_disabled,
        )

        connection_responses = [
            RepositoryConnectionResponse.from_orm(conn) for conn in connections
        ]

        return RepositoryConnectionListResponse(
            connections=connection_responses,
            total=len(connection_responses),
        )

    except Exception as e:
        logger.error(
            "list_connections_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch connections: {str(e)}"
        )


@router.get(
    "/connections/{connection_id}",
    response_model=RepositoryConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Repository Connection",
    description="Get details of a specific repository connection.",
)
async def get_repository_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryConnectionResponse:
    """
    Get repository connection details.

    **Path Parameters:**
    - connection_id: Repository connection ID

    **Returns:**
    - Repository connection details
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        connections = await repo_manager.get_repository_connections(
            db=db,
            user_id=user.user_id,
            include_disabled=True,
        )

        connection = next((c for c in connections if c.id == connection_id), None)

        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository connection not found"
            )

        return RepositoryConnectionResponse.from_orm(connection)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_connection_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch connection: {str(e)}"
        )


@router.patch(
    "/connections/{connection_id}",
    response_model=RepositoryConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Repository Connection",
    description="Update repository connection settings.",
)
async def update_repository_connection(
    connection_id: str,
    request: UpdateRepositoryConnectionRequest,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryConnectionResponse:
    """
    Update repository connection settings.

    **Path Parameters:**
    - connection_id: Repository connection ID

    **Request Body:**
    - is_enabled: Enable/disable monitoring
    - auto_pr_enabled: Enable/disable automatic PR creation

    **Returns:**
    - Updated repository connection details
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        connection = await repo_manager.update_repository_connection(
            db=db,
            user_id=user.user_id,
            connection_id=connection_id,
            is_enabled=request.is_enabled,
            auto_pr_enabled=request.auto_pr_enabled,
        )

        db.commit()

        logger.info(
            "connection_updated",
            user_id=user.user_id,
            connection_id=connection_id,
        )

        return RepositoryConnectionResponse.from_orm(connection)

    except ValueError as e:
        db.rollback()
        logger.error(
            "update_connection_failed",
            error=str(e),
            connection_id=connection_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        logger.error(
            "update_connection_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update connection: {str(e)}"
        )


@router.delete(
    "/connections/{connection_id}",
    response_model=DisconnectRepositoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect Repository",
    description="Disconnect a repository and optionally delete its webhook.",
)
async def disconnect_repository(
    connection_id: str,
    delete_webhook: bool = Query(True, description="Delete webhook from GitHub"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> DisconnectRepositoryResponse:
    """
    Disconnect a repository from DevFlowFix.

    **Path Parameters:**
    - connection_id: Repository connection ID

    **Query Parameters:**
    - delete_webhook: Delete webhook from GitHub (default: true)

    **Returns:**
    - Disconnection confirmation
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        result = await repo_manager.disconnect_repository(
            db=db,
            user_id=user.user_id,
            connection_id=connection_id,
            delete_webhook=delete_webhook,
        )

        db.commit()

        logger.info(
            "repository_disconnected",
            user_id=user.user_id,
            connection_id=connection_id,
        )

        return DisconnectRepositoryResponse(
            success=True,
            connection_id=result["connection_id"],
            repository_full_name=result["repository_full_name"],
            webhook_deleted=result["webhook_deleted"],
            message=f"Repository {result['repository_full_name']} successfully disconnected",
        )

    except ValueError as e:
        db.rollback()
        logger.error(
            "disconnect_repository_failed",
            error=str(e),
            connection_id=connection_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        logger.error(
            "disconnect_repository_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect repository: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=RepositoryStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Repository Statistics",
    description="Get statistics for connected repositories.",
)
async def get_repository_stats(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryStatsResponse:
    """
    Get repository connection statistics.

    **Returns:**
    - Total repositories
    - Active/inactive repositories
    - Webhook count
    - Auto-PR enabled count
    """
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        stats = await repo_manager.get_repository_stats(
            db=db,
            user_id=user.user_id,
        )

        return RepositoryStatsResponse(**stats)

    except Exception as e:
        logger.error(
            "get_stats_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch statistics: {str(e)}"
        )


# ==================== GitLab Repository Endpoints ====================


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
    """
    List GitLab projects accessible to the user.

    **Requirements:**
    - User must have an active GitLab OAuth connection

    **Query Parameters:**
    - page: Page number (default: 1)
    - per_page: Items per page, max 100 (default: 30)
    - sort: Sort field (default: updated_at)
    - direction: asc or desc (default: desc)

    **Returns:**
    - List of projects with connection status
    - Pagination information
    """
    try:
        user = current_user_data["user"]
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        # Get GitLab OAuth connection
        oauth_connection = await token_manager.get_oauth_connection(
            db=db,
            user_id=user.user_id,
            provider="gitlab",
        )

        if not oauth_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GitLab OAuth connection found. Please connect your GitLab account first."
            )

        # Get decrypted access token
        access_token = token_manager.get_decrypted_token(oauth_connection)

        # Initialize GitLab provider
        gitlab_url = getattr(settings, 'gitlab_instance_url', 'https://gitlab.com')
        gitlab_provider = GitLabOAuthProvider(
            client_id=settings.gitlab_oauth_client_id or "",
            client_secret=settings.gitlab_oauth_client_secret or "",
            redirect_uri=settings.gitlab_oauth_redirect_uri or "",
            scopes=[],
            gitlab_url=gitlab_url,
        )

        # Fetch projects from GitLab
        projects = await gitlab_provider.get_user_projects(
            access_token=access_token,
            page=page,
            per_page=per_page,
            sort=sort,
            direction=direction,
        )

        # Get connected repository IDs
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

        # Map GitLab projects to our schema
        repositories = []
        for project in projects:
            repositories.append({
                "id": project["id"],
                "name": project["name"],
                "full_name": project["path_with_namespace"],
                "description": project.get("description"),
                "private": project.get("visibility") == "private",
                "url": project["web_url"],
                "default_branch": project.get("default_branch", "main"),
                "is_connected": str(project["id"]) in connected_ids,
            })

        logger.info(
            "gitlab_projects_listed",
            user_id=user.user_id,
            count=len(repositories),
            page=page,
        )

        return RepositoryListResponse(
            repositories=repositories,
            total=len(repositories),
            page=page,
            per_page=per_page,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "list_gitlab_projects_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list GitLab projects: {str(e)}"
        )


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
    """
    Connect a GitLab project to DevFlowFix.

    **Actions:**
    1. Verify GitLab OAuth connection
    2. Fetch project details from GitLab
    3. Create repository connection record
    4. Optionally set up webhook

    **Request Body:**
    - repository_full_name: GitLab project path (e.g., "group/project")
    - auto_pr_enabled: Enable automatic PR creation (default: true)
    - setup_webhook: Automatically create webhook (default: true)

    **Returns:**
    - Repository connection details
    - Webhook URL and secret token (if created)
    """
    try:
        user = current_user_data["user"]
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        # Get GitLab OAuth connection
        oauth_connection = await token_manager.get_oauth_connection(
            db=db,
            user_id=user.user_id,
            provider="gitlab",
        )

        if not oauth_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GitLab OAuth connection found"
            )

        # Get decrypted access token
        access_token = token_manager.get_decrypted_token(oauth_connection)

        # Initialize GitLab provider
        gitlab_url = getattr(settings, 'gitlab_instance_url', 'https://gitlab.com')
        gitlab_provider = GitLabOAuthProvider(
            client_id=settings.gitlab_oauth_client_id or "",
            client_secret=settings.gitlab_oauth_client_secret or "",
            redirect_uri=settings.gitlab_oauth_redirect_uri or "",
            scopes=[],
            gitlab_url=gitlab_url,
        )

        # Fetch project details
        project = await gitlab_provider.get_project(
            access_token=access_token,
            project_id=request.repository_full_name,
        )

        # Create repository connection
        from app.adapters.database.postgres.models import RepositoryConnectionTable
        import uuid

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

        # Set up webhook if requested
        webhook_data = None
        if request.setup_webhook:
            try:
                webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/gitlab/{user.user_id}"

                # Generate webhook secret token
                import secrets
                webhook_token = secrets.token_urlsafe(32)

                # Create webhook in GitLab
                hook = await gitlab_provider.create_project_hook(
                    access_token=access_token,
                    project_id=str(project["id"]),
                    webhook_url=webhook_url,
                    token=webhook_token,
                    events=["pipeline_events", "merge_requests_events", "push_events"],
                )

                repo_connection.webhook_id = str(hook.get("id"))
                repo_connection.webhook_url = webhook_url

                webhook_data = {
                    "webhook_url": webhook_url,
                    "webhook_id": hook.get("id"),
                    "webhook_token": webhook_token,
                }

                logger.info(
                    "gitlab_webhook_created",
                    user_id=user.user_id,
                    project=project["path_with_namespace"],
                    webhook_id=hook.get("id"),
                )

            except Exception as e:
                logger.warning(
                    "gitlab_webhook_creation_failed",
                    error=str(e),
                    project=project["path_with_namespace"],
                )
                # Continue without webhook

        db.commit()
        db.refresh(repo_connection)

        logger.info(
            "gitlab_project_connected",
            user_id=user.user_id,
            project=project["path_with_namespace"],
            connection_id=repo_connection.id,
        )

        # Build response
        from app.core.schemas.repository import RepositoryConnectionResponse
        from datetime import datetime, timezone

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
    except Exception as e:
        db.rollback()
        logger.error(
            "connect_gitlab_project_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect GitLab project: {str(e)}"
        )
