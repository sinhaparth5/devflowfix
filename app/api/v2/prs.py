# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Pull Request Management API Endpoints

Handles automated PR creation and management for incident fixes.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog

from app.core.config import get_settings
from app.core.schemas.pr import (
    CreatePRRequest,
    CreatePRResponse,
    PRStatus,
    IncidentPRResponse,
    PRListResponse,
    PRStatsResponse,
    UpdatePRRequest,
    PRMergeRequest,
    PRCommentRequest,
)
from app.dependencies import get_db
from app.auth import get_current_active_user
from app.services.oauth.token_manager import get_token_manager
from app.services.pr.pr_creator import PRCreator
from app.adapters.database.postgres.models import (
    IncidentTable,
    RepositoryConnectionTable,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/prs", tags=["Pull Requests"])
settings = get_settings()


def get_pr_creator() -> PRCreator:
    """
    Get PR creator instance.

    Returns:
        PRCreator instance
    """
    token_manager = get_token_manager(settings.oauth_token_encryption_key)
    return PRCreator(token_manager=token_manager)


@router.post(
    "/create",
    response_model=CreatePRResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create PR for Incident",
    description="Create an automated pull request to fix an incident.",
)
async def create_pr_for_incident(
    request: CreatePRRequest,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> CreatePRResponse:
    """
    Create a pull request to fix an incident.

    **Flow:**
    1. Fetches incident and repository details
    2. Analyzes failure (optionally with AI)
    3. Generates code fixes
    4. Creates branch and commits changes
    5. Opens pull request on GitHub
    6. Links PR to incident

    **Request Body:**
    - incident_id: ID of incident to fix
    - branch_name: Custom branch name (optional, auto-generated if not provided)
    - use_ai_analysis: Use AI to analyze and generate fixes (default: true)
    - auto_commit: Automatically commit and push changes (default: true)
    - draft_pr: Create as draft PR (default: false)

    **Returns:**
    - PR creation result with PR number, URL, and details

    **Note:** This endpoint requires:
    - Active OAuth connection to GitHub
    - Repository connection for the incident's repository
    - `repo` scope in OAuth token
    """
    try:
        user = current_user_data["user"]

        # Get incident to understand what needs to be fixed
        incident = db.query(IncidentTable).filter(
            IncidentTable.incident_id == request.incident_id,
            IncidentTable.user_id == user.user_id,
        ).first()

        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {request.incident_id} not found"
            )

        # Use existing services to generate AI-powered fixes
        if request.use_ai_analysis:
            try:
                logger.info(
                    "generating_ai_fixes",
                    incident_id=request.incident_id,
                    user_id=user.user_id,
                )

                # Use existing services (same as webhook)
                from app.services.github_log_parser import GitHubLogExtractor
                from app.services.pr_creator import PRCreatorService
                from app.core.models.incident import Incident as DomainIncident
                from app.core.enums import IncidentSource
                from app.dependencies import get_service_container

                token_manager = get_token_manager(settings.oauth_token_encryption_key)
                container = get_service_container()

                # Get repository connection
                repo_conn = db.query(RepositoryConnectionTable).filter(
                    RepositoryConnectionTable.user_id == user.user_id,
                    RepositoryConnectionTable.repository_full_name == incident.repository,
                    RepositoryConnectionTable.is_enabled == True,
                ).first()

                if not repo_conn:
                    raise ValueError(f"No repository connection found for {incident.repository}")

                # Get OAuth token
                oauth_conn = await token_manager.get_oauth_connection(
                    db=db,
                    user_id=user.user_id,
                    provider="github",
                )

                if not oauth_conn:
                    raise ValueError("No GitHub OAuth connection found")

                access_token = token_manager.get_decrypted_token(oauth_conn)
                owner, repo = incident.repository.split("/")
                run_id = incident.metadata.get("run_id") if incident.metadata else None

                if not run_id and incident.workflow_run:
                    run_id = incident.workflow_run.run_id

                if not run_id:
                    raise ValueError("No workflow run ID found in incident")

                # Parse logs using existing GitHubLogExtractor
                log_extractor = GitHubLogExtractor(github_token=access_token)
                error_summary = await log_extractor.fetch_and_parse_logs(
                    owner=owner,
                    repo=repo,
                    run_id=int(run_id),
                )

                if not error_summary:
                    raise ValueError("No errors found in workflow logs")

                # Convert to domain model
                domain_incident = DomainIncident(
                    incident_id=incident.incident_id,
                    source=IncidentSource.GITHUB,
                    severity=incident.severity,
                    error_log=error_summary,
                    error_message=incident.title or "Workflow failure",
                    context={
                        "repository": incident.repository,
                        "workflow": incident.workflow_name,
                        "branch": incident.branch,
                        "commit": incident.commit_sha,
                        "run_id": run_id,
                        "user_id": user.user_id,
                    },
                    timestamp=incident.created_at,
                )

                # Use existing analyzer service
                analyzer = container.get_analyzer_service(db)
                if not analyzer:
                    raise ValueError("Analyzer service not available")

                analysis = await analyzer.analyze(
                    incident=domain_incident,
                    similar_incidents=[],
                )

                solution = await analyzer.llm.generate_solution(
                    error_log=error_summary,
                    failure_type=analysis.category.value if analysis.category else "build_failure",
                    root_cause=analysis.root_cause or "Workflow failure",
                    context=domain_incident.context,
                    repository_code=None,
                )

                logger.info(
                    "solution_generated",
                    incident_id=request.incident_id,
                    has_code_changes=bool(solution.get("code_changes")),
                )

                # Create PR using existing PRCreatorService
                if solution.get("code_changes"):
                    pr_creator_service = PRCreatorService()
                    pr_result = await pr_creator_service.create_fix_pr(
                        incident=domain_incident,
                        analysis=analysis,
                        solution=solution,
                        user_id=user.user_id,
                    )

                    return CreatePRResponse(
                        success=True,
                        pr_number=pr_result.get("number"),
                        pr_url=pr_result.get("html_url"),
                        branch_name=pr_result.get("head", {}).get("ref"),
                        files_changed=len(solution.get("code_changes", [])),
                        incident_id=request.incident_id,
                        ai_analysis_used=True,
                    )
                else:
                    raise ValueError("No code changes generated by AI")

            except Exception as e:
                logger.error(
                    "ai_fix_generation_failed",
                    incident_id=request.incident_id,
                    error=str(e),
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"AI fix generation failed: {str(e)}"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AI analysis is required for automatic PR creation. Set use_ai_analysis=true"
            )

    except ValueError as e:
        logger.error(
            "create_pr_failed",
            error=str(e),
            incident_id=request.incident_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "create_pr_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create PR: {str(e)}"
        )


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentPRResponse,
    status_code=status.HTTP_200_OK,
    summary="Get PRs for Incident",
    description="Get all pull requests associated with an incident.",
)
async def get_prs_for_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> IncidentPRResponse:
    """
    Get all pull requests for an incident.

    **Path Parameters:**
    - incident_id: Incident ID

    **Returns:**
    - List of PRs with their status
    - PR statistics (total, open, merged, closed)
    """
    try:
        user = current_user_data["user"]

        # Get incident
        incident = db.query(IncidentTable).filter(
            IncidentTable.incident_id == incident_id,
            IncidentTable.user_id == user.user_id,
        ).first()

        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} not found"
            )

        # Get PRs from incident metadata
        prs_data = incident.metadata.get("prs", []) if incident.metadata else []

        # Fetch current PR status from GitHub for each PR
        pr_creator = get_pr_creator()
        pr_statuses = []

        if prs_data and incident.repository:
            try:
                repo_conn = db.query(RepositoryConnectionTable).filter(
                    RepositoryConnectionTable.user_id == user.user_id,
                    RepositoryConnectionTable.repository_full_name == incident.repository,
                    RepositoryConnectionTable.is_enabled == True,
                ).first()

                if repo_conn:
                    from app.services.oauth.token_manager import get_token_manager
                    token_manager = get_token_manager(settings.oauth_token_encryption_key)

                    oauth_conn = await token_manager.get_oauth_connection(
                        db=db,
                        user_id=user.user_id,
                        provider="github",
                    )

                    if oauth_conn:
                        access_token = token_manager.get_decrypted_token(oauth_conn)
                        owner, repo = incident.repository.split("/")

                        for pr_data in prs_data:
                            pr_number = pr_data.get("pr_number")
                            if pr_number:
                                try:
                                    pr_info = await pr_creator.get_pull_request(
                                        access_token=access_token,
                                        owner=owner,
                                        repo=repo,
                                        pr_number=pr_number,
                                    )

                                    pr_status = PRStatus(
                                        pr_number=pr_info["number"],
                                        pr_url=pr_info["html_url"],
                                        title=pr_info["title"],
                                        body=pr_info["body"] or "",
                                        state=pr_info["state"],
                                        draft=pr_info.get("draft", False),
                                        mergeable=pr_info.get("mergeable"),
                                        merged=pr_info.get("merged", False),
                                        merged_at=pr_info.get("merged_at"),
                                        closed_at=pr_info.get("closed_at"),
                                        branch_name=pr_info["head"]["ref"],
                                        base_branch=pr_info["base"]["ref"],
                                        commits=pr_info.get("commits", 0),
                                        changed_files=pr_info.get("changed_files", 0),
                                        additions=pr_info.get("additions", 0),
                                        deletions=pr_info.get("deletions", 0),
                                        comments=pr_info.get("comments", 0),
                                        reviews=0,  # Would need separate API call
                                        created_at=pr_info["created_at"],
                                        updated_at=pr_info["updated_at"],
                                        created_by=pr_info["user"]["login"],
                                    )
                                    pr_statuses.append(pr_status)
                                except Exception as e:
                                    logger.warning(
                                        "failed_to_fetch_pr_status",
                                        pr_number=pr_number,
                                        error=str(e),
                                    )
            except Exception as e:
                logger.warning(
                    "failed_to_fetch_pr_statuses",
                    incident_id=incident_id,
                    error=str(e),
                )

        # Calculate statistics
        total_prs = len(pr_statuses)
        open_prs = len([pr for pr in pr_statuses if pr.state == "open"])
        merged_prs = len([pr for pr in pr_statuses if pr.merged])
        closed_prs = len([pr for pr in pr_statuses if pr.state == "closed" and not pr.merged])

        return IncidentPRResponse(
            incident_id=incident_id,
            prs=pr_statuses,
            total_prs=total_prs,
            open_prs=open_prs,
            merged_prs=merged_prs,
            closed_prs=closed_prs,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_incident_prs_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch PRs: {str(e)}"
        )


@router.get(
    "/{repository_owner}/{repository_name}/{pr_number}",
    response_model=PRStatus,
    status_code=status.HTTP_200_OK,
    summary="Get PR Status",
    description="Get detailed status of a specific pull request.",
)
async def get_pr_status(
    repository_owner: str,
    repository_name: str,
    pr_number: int,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> PRStatus:
    """
    Get pull request status.

    **Path Parameters:**
    - repository_owner: Repository owner (e.g., "octocat")
    - repository_name: Repository name (e.g., "Hello-World")
    - pr_number: PR number

    **Returns:**
    - Detailed PR status and information
    """
    try:
        user = current_user_data["user"]
        repository_full_name = f"{repository_owner}/{repository_name}"

        # Verify user has access to this repository
        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.user_id == user.user_id,
            RepositoryConnectionTable.repository_full_name == repository_full_name,
        ).first()

        if not repo_conn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository {repository_full_name} not found or not connected"
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

        # Fetch PR details
        pr_creator = get_pr_creator()
        pr_info = await pr_creator.get_pull_request(
            access_token=access_token,
            owner=repository_owner,
            repo=repository_name,
            pr_number=pr_number,
        )

        return PRStatus(
            pr_number=pr_info["number"],
            pr_url=pr_info["html_url"],
            title=pr_info["title"],
            body=pr_info["body"] or "",
            state=pr_info["state"],
            draft=pr_info.get("draft", False),
            mergeable=pr_info.get("mergeable"),
            merged=pr_info.get("merged", False),
            merged_at=pr_info.get("merged_at"),
            closed_at=pr_info.get("closed_at"),
            branch_name=pr_info["head"]["ref"],
            base_branch=pr_info["base"]["ref"],
            commits=pr_info.get("commits", 0),
            changed_files=pr_info.get("changed_files", 0),
            additions=pr_info.get("additions", 0),
            deletions=pr_info.get("deletions", 0),
            comments=pr_info.get("comments", 0),
            reviews=0,
            created_at=pr_info["created_at"],
            updated_at=pr_info["updated_at"],
            created_by=pr_info["user"]["login"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_pr_status_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch PR status: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=PRStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get PR Statistics",
    description="Get statistics for automatically created PRs.",
)
async def get_pr_stats(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> PRStatsResponse:
    """
    Get PR statistics for user.

    **Returns:**
    - Total PRs created, merged, closed
    - Merge rate, success rate
    - Average time to merge
    - Incidents with PRs
    """
    try:
        user = current_user_data["user"]

        # Get all PRs from PullRequestTable for user's repositories
        from app.adapters.database.postgres.models import PullRequestTable, PRStatus as DBPRStatus

        # Get user's repository connections
        repo_connections = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.user_id == user.user_id,
        ).all()

        repo_full_names = [rc.repository_full_name for rc in repo_connections]

        # Query PRs for user's repositories
        prs = db.query(PullRequestTable).filter(
            PullRequestTable.repository_full.in_(repo_full_names)
        ).all()

        total_prs = len(prs)
        merged_prs = len([p for p in prs if p.status == DBPRStatus.MERGED])
        closed_prs = len([p for p in prs if p.status == DBPRStatus.CLOSED])
        open_prs = len([p for p in prs if p.status == DBPRStatus.OPEN])
        draft_prs = len([p for p in prs if p.status == DBPRStatus.DRAFT])

        # Calculate total files changed
        total_files_changed = sum(p.files_changed or 0 for p in prs)

        # Calculate average time to merge for merged PRs
        merge_times = []
        for pr in prs:
            if pr.status == DBPRStatus.MERGED and pr.merged_at and pr.created_at:
                merge_duration = (pr.merged_at - pr.created_at).total_seconds() / 3600  # Convert to hours
                merge_times.append(merge_duration)

        avg_time_to_merge_hours = sum(merge_times) / len(merge_times) if merge_times else None

        # Get incidents with PRs
        incident_ids = set(p.incident_id for p in prs)
        incidents_with_prs = len(incident_ids)

        # Count incidents that were auto-fixed (have merged PRs)
        merged_incident_ids = set(p.incident_id for p in prs if p.status == DBPRStatus.MERGED)
        incidents_auto_fixed = len(merged_incident_ids)

        # Calculate statistics
        merge_rate = (merged_prs / total_prs * 100) if total_prs > 0 else 0.0
        success_rate = (merged_prs / total_prs * 100) if total_prs > 0 else 0.0
        avg_files_changed = (total_files_changed / total_prs) if total_prs > 0 else 0.0

        return PRStatsResponse(
            total_prs_created=total_prs,
            merged_prs=merged_prs,
            closed_without_merge=closed_prs,
            open_prs=open_prs,
            draft_prs=draft_prs,
            merge_rate=merge_rate,
            avg_time_to_merge_hours=avg_time_to_merge_hours,
            avg_files_changed=avg_files_changed,
            success_rate=success_rate,
            incidents_with_prs=incidents_with_prs,
            incidents_auto_fixed=incidents_auto_fixed,
        )

    except Exception as e:
        logger.error(
            "get_pr_stats_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch PR statistics: {str(e)}"
        )
