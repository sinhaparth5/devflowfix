# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import structlog

from app.auth import get_current_active_user
from app.core.schemas.repository import (
    ConnectRepositoryRequest,
    DisconnectRepositoryResponse,
    RepositoryConnectionListResponse,
    RepositoryConnectionResponse,
    RepositoryListResponse,
    RepositoryStatsResponse,
    UpdateRepositoryConnectionRequest,
)
from app.dependencies import get_db
from app.api.v2.repository_dependencies import get_repository_manager, get_webhook_manager

logger = structlog.get_logger(__name__)
router = APIRouter()


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

        logger.info("repositories_listed", user_id=user.user_id, count=result["total"], page=page)
        return RepositoryListResponse(**result)
    except ValueError as exc:
        logger.error("list_repositories_failed", error=str(exc), user_id=current_user_data["user"].user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("list_repositories_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch repositories: {str(exc)}",
        ) from exc


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
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()

        connection = await repo_manager.connect_repository(
            db=db,
            user_id=user.user_id,
            repository_full_name=request.repository_full_name,
            auto_pr_enabled=request.auto_pr_enabled,
            setup_webhook=False,
            webhook_events=None,
            webhook_url=None,
        )

        if request.setup_webhook:
            webhook_manager = get_webhook_manager()
            try:
                webhook_result = await webhook_manager.create_webhook(
                    db=db,
                    repository_connection_id=connection.id,
                    events=request.webhook_events,
                )
                logger.info(
                    "webhook_auto_created",
                    repository=request.repository_full_name,
                    webhook_id=webhook_result["webhook_id"],
                    events=webhook_result["events"],
                )
            except Exception as exc:
                logger.warning(
                    "webhook_auto_creation_failed",
                    repository=request.repository_full_name,
                    error=str(exc),
                )
                connection.webhook_status = "failed"

        db.commit()
        logger.info("repository_connected", user_id=user.user_id, repository=request.repository_full_name, connection_id=connection.id)
        return RepositoryConnectionResponse.from_orm(connection)
    except ValueError as exc:
        db.rollback()
        logger.error("connect_repository_failed", error=str(exc), repository=request.repository_full_name)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.error("connect_repository_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect repository: {str(exc)}",
        ) from exc


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
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()
        connections = await repo_manager.get_repository_connections(
            db=db,
            user_id=user.user_id,
            include_disabled=include_disabled,
        )
        connection_responses = [RepositoryConnectionResponse.from_orm(conn) for conn in connections]
        return RepositoryConnectionListResponse(connections=connection_responses, total=len(connection_responses))
    except Exception as exc:
        logger.error("list_connections_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch connections: {str(exc)}",
        ) from exc


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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository connection not found")
        return RepositoryConnectionResponse.from_orm(connection)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_connection_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch connection: {str(exc)}",
        ) from exc


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
        logger.info("connection_updated", user_id=user.user_id, connection_id=connection_id)
        return RepositoryConnectionResponse.from_orm(connection)
    except ValueError as exc:
        db.rollback()
        logger.error("update_connection_failed", error=str(exc), connection_id=connection_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.error("update_connection_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update connection: {str(exc)}",
        ) from exc


@router.delete(
    "/connections/{connection_id}",
    response_model=DisconnectRepositoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect Repository",
    description="Disconnect a repository and automatically delete its webhook.",
)
async def disconnect_repository(
    connection_id: str,
    delete_webhook: bool = Query(True, description="Delete webhook from GitHub/GitLab"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> DisconnectRepositoryResponse:
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()
        webhook_manager = get_webhook_manager()
        result = await repo_manager.disconnect_repository(
            db=db,
            user_id=user.user_id,
            connection_id=connection_id,
            delete_webhook=delete_webhook,
            webhook_manager=webhook_manager,
        )
        db.commit()
        logger.info(
            "repository_disconnected",
            user_id=user.user_id,
            connection_id=connection_id,
            webhook_deleted=result["webhook_deleted"],
        )
        return DisconnectRepositoryResponse(
            success=True,
            connection_id=result["connection_id"],
            repository_full_name=result["repository_full_name"],
            webhook_deleted=result["webhook_deleted"],
            message=f"Repository {result['repository_full_name']} successfully disconnected"
            + (f" and webhook deleted" if result["webhook_deleted"] else ""),
        )
    except ValueError as exc:
        db.rollback()
        logger.error("disconnect_repository_failed", error=str(exc), connection_id=connection_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.error("disconnect_repository_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect repository: {str(exc)}",
        ) from exc


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
    try:
        user = current_user_data["user"]
        repo_manager = get_repository_manager()
        stats = await repo_manager.get_repository_stats(db=db, user_id=user.user_id)
        return RepositoryStatsResponse(**stats)
    except Exception as exc:
        logger.error("get_stats_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch statistics: {str(exc)}",
        ) from exc
