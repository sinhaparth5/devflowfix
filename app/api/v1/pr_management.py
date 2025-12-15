# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
PR Management Endpoints

REST API for managing automated PR creation and tracking.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Depends, status as http_status
from sqlalchemy.orm import Session
from sqlalchemy import func
import structlog

from app.dependencies import get_db
from app.core.schemas.common import PaginatedResponse
from app.services.github_token_manager import GitHubTokenManager
from app.api.v1.auth import get_current_active_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/pr-management", tags=["PR Management"])


# ============================================================================
# GitHub Token Management Endpoints
# ============================================================================

@router.post(
    "/tokens/register",
    summary="Register GitHub token",
    description="Register a GitHub access token for a repository or organization",
)
async def register_github_token(
    owner: str = Query(..., description="GitHub organization/user"),
    repo: Optional[str] = Query(None, description="Repository name (None for org-level)"),
    token: str = Query(..., description="GitHub Personal Access Token"),
    description: str = Query("", description="Token description"),
    scopes: Optional[str] = Query(None, description="Comma-separated scopes"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Register a GitHub access token for automated PR creation.
    
    Tokens can be:
    - Repository-specific: owner/repo (recommended for security)
    - Organization-wide: owner/* (simpler, broader access)
    
    **Scopes required:**
    - `repo` - Push to repositories
    - `workflow` - Modify workflow files
    - `contents` - Write repository contents
    """
    try:
        user = current_user["user"]
        manager = GitHubTokenManager()

        logger.info(
            "token_registration_request",
            user_id=user.user_id,
            owner=owner,
            repo=repo,
        )

        result = manager.register_token(
            user_id=user.user_id,
            owner=owner,
            repo=repo,
            token=token,
            description=description,
            scopes=scopes.split(",") if scopes else ["repo", "workflow", "contents"],
            created_by=user.email or user.user_id,
        )
        
        logger.info(
            "token_registration_successful",
            owner=owner,
            repo=repo,
        )
        
        return {
            "success": True,
            "message": f"Token registered for {owner}/{repo or '*'}",
            "token": result,
        }
        
    except Exception as e:
        logger.error(
            "token_registration_error",
            owner=owner,
            repo=repo,
            error=str(e),
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to register token: {str(e)}",
        )


@router.get(
    "/tokens",
    summary="List registered tokens",
    description="List all registered GitHub tokens for current user",
)
async def list_github_tokens(
    owner: Optional[str] = Query(None, description="Filter by owner"),
    active_only: bool = Query(True, description="Only list active tokens"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all registered GitHub tokens.
    
    Tokens are displayed with masked values for security.
    """
    try:
        user = current_user["user"]
        manager = GitHubTokenManager()

        tokens = manager.list_tokens(user_id=user.user_id, owner=owner, active_only=active_only)

        logger.info(
            "tokens_listed",
            user_id=user.user_id,
            count=len(tokens),
            owner=owner,
        )
        
        return {
            "success": True,
            "count": len(tokens),
            "tokens": tokens,
        }
        
    except Exception as e:
        logger.error("token_list_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tokens: {str(e)}",
        )


@router.post(
    "/tokens/{token_id}/deactivate",
    summary="Deactivate token",
    description="Deactivate a GitHub token",
)
async def deactivate_github_token(
    token_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Deactivate a GitHub token (soft delete).
    
    The token is marked as inactive but not deleted from the database.
    """
    try:
        user = current_user["user"]
        manager = GitHubTokenManager()

        # Verify token belongs to user before deactivating
        success = manager.deactivate_token(token_id, user_id=user.user_id)
        
        if not success:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Token not found: {token_id}",
            )
        
        logger.info("token_deactivated", token_id=token_id)
        
        return {
            "success": True,
            "message": f"Token {token_id} deactivated",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("token_deactivation_error", token_id=token_id, error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate token: {str(e)}",
        )


# ============================================================================
# PR Tracking Endpoints
# ============================================================================

@router.get(
    "/pulls",
    summary="List automated PRs",
    description="List pull requests created by DevFlowFix",
)
async def list_pull_requests(
    incident_id: Optional[str] = Query(None, description="Filter by incident ID"),
    repository: Optional[str] = Query(None, description="Filter by repository (owner/repo)"),
    status_filter: Optional[str] = Query(None, description="Filter by PR status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List automated pull requests.
    
    **Statuses:**
    - `created` - PR created
    - `open` - PR is open
    - `draft` - PR is draft
    - `review_requested` - Review requested
    - `approved` - PR approved
    - `merged` - PR merged
    - `closed` - PR closed
    - `failed` - PR creation failed
    """
    from app.adapters.database.postgres.models import PullRequestTable
    
    try:
        query = db.query(PullRequestTable)
        
        if incident_id:
            query = query.filter(PullRequestTable.incident_id == incident_id)
        
        if repository:
            query = query.filter(PullRequestTable.repository_full == repository)
        
        if status_filter:
            query = query.filter(PullRequestTable.status == status_filter)
        
        total = query.count()
        prs = query.order_by(PullRequestTable.created_at.desc()).offset(skip).limit(limit).all()
        
        logger.info(
            "pull_requests_listed",
            count=len(prs),
            total=total,
            incident_id=incident_id,
        )
        
        return {
            "success": True,
            "total": total,
            "skip": skip,
            "limit": limit,
            "prs": [
                {
                    "id": pr.id,
                    "incident_id": pr.incident_id,
                    "pr_number": pr.pr_number,
                    "pr_url": pr.pr_url,
                    "repository": pr.repository_full,
                    "title": pr.title,
                    "branch": pr.branch_name,
                    "status": pr.status.value,
                    "failure_type": pr.failure_type,
                    "confidence_score": pr.confidence_score,
                    "files_changed": pr.files_changed,
                    "additions": pr.additions,
                    "deletions": pr.deletions,
                    "created_at": pr.created_at.isoformat(),
                    "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                    "approved_by": pr.approved_by,
                }
                for pr in prs
            ],
        }
        
    except Exception as e:
        logger.error("pull_requests_list_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list pull requests: {str(e)}",
        )


@router.get(
    "/pulls/{pr_id}",
    summary="Get PR details",
    description="Get detailed information about a specific PR",
)
async def get_pull_request_details(
    pr_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get detailed information about an automated PR."""
    from app.adapters.database.postgres.models import PullRequestTable
    
    try:
        pr = db.query(PullRequestTable).filter(PullRequestTable.id == pr_id).first()

        if not pr:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"PR not found: {pr_id}",
            )
        
        logger.info("pull_request_details_retrieved", pr_id=pr_id)
        
        return {
            "success": True,
            "pr": {
                "id": pr.id,
                "incident_id": pr.incident_id,
                "pr_number": pr.pr_number,
                "pr_url": pr.pr_url,
                "repository": pr.repository_full,
                "title": pr.title,
                "description": pr.description,
                "branch": pr.branch_name,
                "base_branch": pr.base_branch,
                "status": pr.status.value,
                "failure_type": pr.failure_type,
                "root_cause": pr.root_cause,
                "confidence_score": pr.confidence_score,
                "files_changed": pr.files_changed,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "commits_count": pr.commits_count,
                "review_comments_count": pr.review_comments_count,
                "approved_by": pr.approved_by,
                "has_conflicts": pr.has_conflicts,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
                "metadata": pr.metadata or {},
            },
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pull_request_details_error", pr_id=pr_id, error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve PR details: {str(e)}",
        )


@router.post(
    "/pulls/{pr_id}/update-status",
    summary="Update PR status",
    description="Update the status of a pull request",
)
async def update_pr_status(
    pr_id: str,
    new_status: str = Query(..., description="New status (open, merged, closed, etc.)"),
    metadata: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Update the status of an automated PR.
    
    Useful for syncing PR status from GitHub.
    """
    from app.adapters.database.postgres.models import PullRequestTable, PRStatus
    
    try:
        pr = db.query(PullRequestTable).filter(PullRequestTable.id == pr_id).first()

        if not pr:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"PR not found: {pr_id}",
            )
        
        # Validate status
        try:
            status_enum = PRStatus(new_status)
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {new_status}",
            )
        
        pr.status = status_enum
        pr.updated_at = datetime.now(timezone.utc)
        
        if new_status == "merged":
            pr.merged_at = datetime.now(timezone.utc)
        elif new_status == "closed":
            pr.closed_at = datetime.now(timezone.utc)
        
        if metadata:
            pr.metadata = pr.metadata or {}
            pr.metadata.update(metadata)
        
        db.commit()
        
        logger.info(
            "pull_request_status_updated",
            pr_id=pr_id,
            new_status=new_status,
        )
        
        return {
            "success": True,
            "message": f"PR {pr.pr_number} status updated to {new_status}",
            "pr_id": pr_id,
            "status": pr.status.value,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "pull_request_status_update_error",
            pr_id=pr_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update PR status: {str(e)}",
        )


# ============================================================================
# Statistics Endpoints
# ============================================================================

@router.get(
    "/stats",
    summary="PR creation statistics",
    description="Get statistics about automated PR creation",
)
async def get_pr_statistics(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get statistics about automated PR creation."""
    from app.adapters.database.postgres.models import PullRequestTable, PRStatus
    
    try:
        total_prs = db.query(PullRequestTable).count()
        
        status_counts = {}
        for pr_status in PRStatus:
            count = db.query(PullRequestTable).filter(
                PullRequestTable.status == pr_status
            ).count()
            status_counts[pr_status.value] = count
        
        merged_prs = db.query(PullRequestTable).filter(
            PullRequestTable.status == PRStatus.MERGED
        ).count()
        
        avg_files_changed = db.query(
            func.avg(PullRequestTable.files_changed)
        ).scalar() or 0

        total_additions = db.query(
            func.sum(PullRequestTable.additions)
        ).scalar() or 0

        total_deletions = db.query(
            func.sum(PullRequestTable.deletions)
        ).scalar() or 0
        
        logger.info(
            "pr_statistics_retrieved",
            total=total_prs,
            merged=merged_prs,
        )
        
        return {
            "success": True,
            "statistics": {
                "total_prs": total_prs,
                "merged_count": merged_prs,
                "merge_rate": (merged_prs / total_prs * 100) if total_prs > 0 else 0,
                "status_distribution": status_counts,
                "avg_files_per_pr": avg_files_changed,
                "total_additions": int(total_additions),
                "total_deletions": int(total_deletions),
            },
        }
        
    except Exception as e:
        logger.error("pr_statistics_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}",
        )
