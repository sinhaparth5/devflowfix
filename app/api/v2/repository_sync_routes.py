# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import structlog
import uuid

from app.auth import get_current_active_user
from app.core.config import get_settings
from app.dependencies import get_db
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.token_manager import get_token_manager

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


async def _get_github_sync_context(db: Session, user_id: str, repository_connection_id: str):
    from app.adapters.database.postgres.models import RepositoryConnectionTable

    repo_conn = db.query(RepositoryConnectionTable).filter(
        RepositoryConnectionTable.id == repository_connection_id,
        RepositoryConnectionTable.user_id == user_id,
    ).first()
    if not repo_conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository connection not found")
    if repo_conn.provider != "github":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only GitHub repositories are supported for this sync operation",
        )

    token_manager = get_token_manager(settings.oauth_token_encryption_key)
    oauth_conn = await token_manager.get_oauth_connection(db=db, user_id=user_id, provider="github")
    if not oauth_conn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No GitHub OAuth connection found")

    access_token = token_manager.get_decrypted_token(oauth_conn)
    github_provider = GitHubOAuthProvider(
        client_id=settings.github_oauth_client_id,
        client_secret=settings.github_oauth_client_secret,
        redirect_uri=settings.github_oauth_redirect_uri,
        scopes=["repo"],
    )
    owner, repo = repo_conn.repository_full_name.split("/")
    return repo_conn, github_provider, access_token, owner, repo


@router.post(
    "/{repository_connection_id}/sync/workflows",
    status_code=status.HTTP_200_OK,
    summary="Sync Workflow Runs from GitHub",
    description="Fetch workflow runs from GitHub API and store them in database.",
)
async def sync_workflow_runs(
    repository_connection_id: str,
    limit: int = Query(30, ge=1, le=100, description="Number of runs to fetch"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    try:
        user = current_user_data["user"]
        repo_conn, github_provider, access_token, owner, repo = await _get_github_sync_context(
            db=db,
            user_id=user.user_id,
            repository_connection_id=repository_connection_id,
        )
        runs_data = await github_provider.get_workflow_runs(
            access_token=access_token,
            owner=owner,
            repo=repo,
            per_page=limit,
            status=status_filter,
        )

        from app.adapters.database.postgres.models import WorkflowRunTable

        new_count = 0
        updated_count = 0
        for run in runs_data.get("workflow_runs", []):
            existing_run = db.query(WorkflowRunTable).filter(
                WorkflowRunTable.repository_connection_id == repository_connection_id,
                WorkflowRunTable.run_id == str(run["id"]),
            ).first()
            if existing_run:
                existing_run.status = run["status"]
                existing_run.conclusion = run.get("conclusion")
                existing_run.updated_at = datetime.now(timezone.utc)
                updated_count += 1
            else:
                workflow_run = WorkflowRunTable(
                    id=str(uuid.uuid4()),
                    repository_connection_id=repository_connection_id,
                    run_id=str(run["id"]),
                    run_number=run["run_number"],
                    workflow_name=run["name"],
                    workflow_id=str(run["workflow_id"]),
                    event=run["event"],
                    status=run["status"],
                    conclusion=run.get("conclusion"),
                    branch=run["head_branch"],
                    commit_sha=run["head_sha"],
                    commit_message=run.get("head_commit", {}).get("message", ""),
                    author=run.get("head_commit", {}).get("author", {}).get("name", ""),
                    run_started_at=datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00")) if run.get("run_started_at") else None,
                    run_url=run["html_url"],
                    logs_url=run.get("logs_url"),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(workflow_run)
                new_count += 1

        db.commit()
        logger.info(
            "workflow_runs_synced",
            user_id=user.user_id,
            repository_connection_id=repository_connection_id,
            fetched=len(runs_data.get("workflow_runs", [])),
            new=new_count,
            updated=updated_count,
        )
        return {
            "success": True,
            "repository_full_name": repo_conn.repository_full_name,
            "total_fetched": len(runs_data.get("workflow_runs", [])),
            "new_runs": new_count,
            "updated_runs": updated_count,
            "total_available": runs_data.get("total_count", 0),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("sync_workflow_runs_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync workflow runs: {str(exc)}",
        ) from exc


@router.post(
    "/{repository_connection_id}/sync/prs",
    status_code=status.HTTP_200_OK,
    summary="Sync Pull Requests from GitHub",
    description="Fetch pull requests from GitHub API and store metadata.",
)
async def sync_pull_requests(
    repository_connection_id: str,
    state: str = Query("all", description="Filter by state (open, closed, all)"),
    limit: int = Query(30, ge=1, le=100, description="Number of PRs to fetch"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    try:
        user = current_user_data["user"]
        repo_conn, github_provider, access_token, owner, repo = await _get_github_sync_context(
            db=db,
            user_id=user.user_id,
            repository_connection_id=repository_connection_id,
        )
        prs = await github_provider.get_pull_requests(
            access_token=access_token,
            owner=owner,
            repo=repo,
            state=state,
            per_page=limit,
        )
        logger.info(
            "pull_requests_synced",
            user_id=user.user_id,
            repository_connection_id=repository_connection_id,
            fetched=len(prs),
            state=state,
        )
        pr_list = [
            {
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "url": pr["html_url"],
                "author": pr["user"]["login"],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "merged_at": pr.get("merged_at"),
                "closed_at": pr.get("closed_at"),
                "draft": pr.get("draft", False),
                "branch": pr["head"]["ref"],
                "base_branch": pr["base"]["ref"],
            }
            for pr in prs
        ]
        return {
            "success": True,
            "repository_full_name": repo_conn.repository_full_name,
            "total_fetched": len(prs),
            "state": state,
            "pull_requests": pr_list,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("sync_pull_requests_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync pull requests: {str(exc)}",
        ) from exc


@router.post(
    "/{repository_connection_id}/sync",
    status_code=status.HTTP_200_OK,
    summary="Sync All Repository Data",
    description="Sync workflows, PRs, and other repository data from GitHub.",
)
async def sync_repository_data(
    repository_connection_id: str,
    sync_workflows: bool = Query(True, description="Sync workflow runs"),
    sync_prs: bool = Query(True, description="Sync pull requests"),
    limit: int = Query(30, ge=1, le=100, description="Limit per resource type"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    try:
        results = {
            "success": True,
            "repository_connection_id": repository_connection_id,
            "workflows": None,
            "pull_requests": None,
        }
        if sync_workflows:
            results["workflows"] = await sync_workflow_runs(
                repository_connection_id=repository_connection_id,
                limit=limit,
                status_filter=None,
                db=db,
                current_user_data=current_user_data,
            )
        if sync_prs:
            results["pull_requests"] = await sync_pull_requests(
                repository_connection_id=repository_connection_id,
                state="all",
                limit=limit,
                db=db,
                current_user_data=current_user_data,
            )
        return results
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("sync_repository_data_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync repository data: {str(exc)}",
        ) from exc
