# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Workflow Run API Endpoints

Handles workflow run tracking, statistics, and management.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog

from app.core.config import get_settings
from app.core.schemas.workflow import (
    WorkflowRunResponse,
    WorkflowRunListResponse,
    WorkflowRunStatsResponse,
    WorkflowRetryRequest,
)
from app.dependencies import get_db
from app.api.v1.auth import get_current_active_user
from app.services.oauth.token_manager import get_token_manager
from app.services.workflow.workflow_tracker import WorkflowTracker
from app.adapters.database.postgres.models import RepositoryConnectionTable

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/workflows", tags=["Workflows"])
settings = get_settings()


def get_workflow_tracker() -> WorkflowTracker:
    """
    Get workflow tracker instance.

    Returns:
        WorkflowTracker instance
    """
    token_manager = get_token_manager(settings.oauth_token_encryption_key)
    return WorkflowTracker(token_manager=token_manager)


@router.get(
    "/runs",
    response_model=WorkflowRunListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Workflow Runs",
    description="List workflow runs for user's repositories.",
)
async def list_workflow_runs(
    repository_connection_id: Optional[str] = Query(None, description="Filter by repository connection"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    conclusion_filter: Optional[str] = Query(None, description="Filter by conclusion"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of runs"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> WorkflowRunListResponse:
    """
    List workflow runs for user's repositories.

    **Query Parameters:**
    - repository_connection_id: Filter by specific repository
    - status_filter: Filter by status (queued, in_progress, completed)
    - conclusion_filter: Filter by conclusion (success, failure, cancelled, etc.)
    - limit: Maximum number of runs to return (default: 50, max: 200)

    **Returns:**
    - List of workflow runs
    - Statistics (total, failed, successful)
    """
    try:
        user = current_user_data["user"]
        tracker = get_workflow_tracker()

        # If specific repository requested, verify user owns it
        if repository_connection_id:
            repo_conn = (
                db.query(RepositoryConnectionTable)
                .filter(
                    RepositoryConnectionTable.id == repository_connection_id,
                    RepositoryConnectionTable.user_id == user.user_id,
                )
                .first()
            )

            if not repo_conn:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repository connection not found"
                )

            runs = await tracker.get_workflow_runs_for_repository(
                db=db,
                repository_connection_id=repository_connection_id,
                status_filter=status_filter,
                conclusion_filter=conclusion_filter,
                limit=limit,
            )
        else:
            # Get all runs for user's repositories
            from app.adapters.database.postgres.models import WorkflowRunTable
            from sqlalchemy import and_

            query = (
                db.query(WorkflowRunTable)
                .join(
                    RepositoryConnectionTable,
                    WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
                )
                .filter(RepositoryConnectionTable.user_id == user.user_id)
            )

            if status_filter:
                query = query.filter(WorkflowRunTable.status == status_filter)

            if conclusion_filter:
                query = query.filter(WorkflowRunTable.conclusion == conclusion_filter)

            from sqlalchemy import desc
            runs = query.order_by(desc(WorkflowRunTable.created_at)).limit(limit).all()

        run_responses = [WorkflowRunResponse.from_orm(run) for run in runs]

        failed_runs = len([r for r in runs if r.conclusion == "failure"])
        successful_runs = len([r for r in runs if r.conclusion == "success"])

        return WorkflowRunListResponse(
            runs=run_responses,
            total=len(run_responses),
            failed_runs=failed_runs,
            successful_runs=successful_runs,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "list_workflow_runs_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workflow runs: {str(e)}"
        )


@router.get(
    "/runs/{run_id}",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Workflow Run",
    description="Get details of a specific workflow run.",
)
async def get_workflow_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> WorkflowRunResponse:
    """
    Get workflow run details.

    **Path Parameters:**
    - run_id: Workflow run tracking ID

    **Returns:**
    - Workflow run details
    """
    try:
        user = current_user_data["user"]

        from app.adapters.database.postgres.models import WorkflowRunTable

        run = (
            db.query(WorkflowRunTable)
            .join(
                RepositoryConnectionTable,
                WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
            )
            .filter(
                WorkflowRunTable.id == run_id,
                RepositoryConnectionTable.user_id == user.user_id,
            )
            .first()
        )

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow run not found"
            )

        return WorkflowRunResponse.from_orm(run)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_workflow_run_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workflow run: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=WorkflowRunStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Workflow Statistics",
    description="Get workflow run statistics for user's repositories.",
)
async def get_workflow_stats(
    repository_connection_id: Optional[str] = Query(None, description="Filter by repository connection"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> WorkflowRunStatsResponse:
    """
    Get workflow run statistics.

    **Query Parameters:**
    - repository_connection_id: Filter by specific repository (optional)

    **Returns:**
    - Total runs, failed runs, successful runs
    - In-progress runs, average duration
    - Failure rate, repositories tracked
    """
    try:
        user = current_user_data["user"]
        tracker = get_workflow_tracker()

        stats = await tracker.get_workflow_run_stats(
            db=db,
            user_id=user.user_id,
            repository_connection_id=repository_connection_id,
        )

        return WorkflowRunStatsResponse(**stats)

    except Exception as e:
        logger.error(
            "get_workflow_stats_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch statistics: {str(e)}"
        )


@router.post(
    "/runs/{run_id}/rerun",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Rerun Workflow",
    description="Trigger a rerun of a workflow run.",
)
async def rerun_workflow(
    run_id: str,
    request: WorkflowRetryRequest,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    """
    Rerun a workflow run.

    **Path Parameters:**
    - run_id: Workflow run tracking ID

    **Request Body:**
    - retry_failed_jobs: If true, only retry failed jobs (default: false)

    **Returns:**
    - Success message
    """
    try:
        user = current_user_data["user"]
        tracker = get_workflow_tracker()

        from app.adapters.database.postgres.models import WorkflowRunTable

        # Get workflow run
        run = (
            db.query(WorkflowRunTable)
            .join(
                RepositoryConnectionTable,
                WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
            )
            .filter(
                WorkflowRunTable.id == run_id,
                RepositoryConnectionTable.user_id == user.user_id,
            )
            .first()
        )

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow run not found"
            )

        # Get repository connection for OAuth token
        repo_conn = (
            db.query(RepositoryConnectionTable)
            .filter(RepositoryConnectionTable.id == run.repository_connection_id)
            .first()
        )

        # Get OAuth token
        from app.services.oauth.token_manager import get_token_manager
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        oauth_conn = await token_manager.get_oauth_connection(
            db=db,
            user_id=user.user_id,
            provider="github",
        )

        if not oauth_conn:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No GitHub OAuth connection found"
            )

        access_token = token_manager.get_decrypted_token(oauth_conn)

        # Split repository full name
        owner, repo = repo_conn.repository_full_name.split("/")

        # Trigger rerun
        success = await tracker.rerun_workflow(
            access_token=access_token,
            owner=owner,
            repo=repo,
            run_id=int(run.run_id),
            rerun_failed_jobs=request.retry_failed_jobs,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to trigger workflow rerun"
            )

        logger.info(
            "workflow_rerun_triggered",
            user_id=user.user_id,
            run_id=run_id,
            github_run_id=run.run_id,
        )

        return {
            "success": True,
            "message": f"Workflow rerun triggered for run #{run.run_number}",
            "run_id": run_id,
            "github_run_id": run.run_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "rerun_workflow_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rerun workflow: {str(e)}"
        )
