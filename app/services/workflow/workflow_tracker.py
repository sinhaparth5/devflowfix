# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Workflow Run Tracker Service

Handles workflow run tracking, failure detection, and integration with incident system.
"""

import uuid
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import structlog

from app.adapters.database.postgres.models import (
    WorkflowRunTable,
    RepositoryConnectionTable,
    IncidentTable,
)
from app.services.oauth.token_manager import TokenManager

logger = structlog.get_logger(__name__)


class WorkflowTracker:
    """
    Tracks GitHub workflow runs and detects failures.

    Responsibilities:
    - Process workflow_run webhook events
    - Track workflow runs in database
    - Detect failures and create incidents
    - Fetch workflow/job details from GitHub API
    - Link workflow runs to repository connections
    """

    def __init__(self, token_manager: TokenManager):
        """
        Initialize workflow tracker.

        Args:
            token_manager: Token manager for OAuth token access
        """
        self.token_manager = token_manager

    def generate_workflow_run_id(self) -> str:
        """
        Generate unique workflow run tracking ID.

        Returns:
            ID with format: wfr_<32_hex_chars>
        """
        return f"wfr_{uuid.uuid4().hex}"

    async def process_workflow_run_event(
        self,
        db: Session,
        event_payload: Dict[str, Any],
        repository_connection: RepositoryConnectionTable,
    ) -> Optional[WorkflowRunTable]:
        """
        Process a workflow_run webhook event.

        Args:
            db: Database session
            event_payload: GitHub webhook event payload
            repository_connection: Repository connection record

        Returns:
            Created or updated workflow run record
        """
        action = event_payload.get("action")
        workflow_run = event_payload.get("workflow_run", {})
        repository = event_payload.get("repository", {})

        run_id = str(workflow_run.get("id"))
        run_number = workflow_run.get("run_number")
        status = workflow_run.get("status")
        conclusion = workflow_run.get("conclusion")

        logger.info(
            "processing_workflow_run_event",
            action=action,
            run_id=run_id,
            run_number=run_number,
            status=status,
            conclusion=conclusion,
            repository=repository.get("full_name"),
        )

        # Check if we're already tracking this run
        existing_run = (
            db.query(WorkflowRunTable)
            .filter(
                and_(
                    WorkflowRunTable.repository_connection_id == repository_connection.id,
                    WorkflowRunTable.run_id == run_id,
                )
            )
            .first()
        )

        head_commit = workflow_run.get("head_commit", {})

        if existing_run:
            # Update existing run
            existing_run.status = status
            existing_run.conclusion = conclusion
            existing_run.updated_at = datetime.now(timezone.utc)

            if workflow_run.get("run_started_at"):
                existing_run.started_at = datetime.fromisoformat(
                    workflow_run["run_started_at"].replace("Z", "+00:00")
                )

            if workflow_run.get("updated_at"):
                existing_run.completed_at = datetime.fromisoformat(
                    workflow_run["updated_at"].replace("Z", "+00:00")
                )

            db.flush()

            logger.info(
                "workflow_run_updated",
                tracking_id=existing_run.id,
                run_id=run_id,
                status=status,
                conclusion=conclusion,
            )

            # Check if workflow failed and create/update incident
            if conclusion == "failure" and not existing_run.incident_id:
                await self._create_incident_for_failure(
                    db=db,
                    workflow_run_record=existing_run,
                    workflow_run_data=workflow_run,
                    repository_connection=repository_connection,
                )

            return existing_run
        else:
            # Create new workflow run tracking record
            new_run = WorkflowRunTable(
                id=self.generate_workflow_run_id(),
                repository_connection_id=repository_connection.id,
                run_id=run_id,
                run_number=run_number,
                workflow_name=workflow_run.get("name", "Unknown"),
                workflow_id=str(workflow_run.get("workflow_id", "")),
                status=status,
                conclusion=conclusion,
                branch=workflow_run.get("head_branch", "unknown"),
                commit_sha=workflow_run.get("head_sha", ""),
                commit_message=head_commit.get("message"),
                author=head_commit.get("author", {}).get("name"),
                started_at=(
                    datetime.fromisoformat(workflow_run["run_started_at"].replace("Z", "+00:00"))
                    if workflow_run.get("run_started_at")
                    else None
                ),
                completed_at=(
                    datetime.fromisoformat(workflow_run["updated_at"].replace("Z", "+00:00"))
                    if workflow_run.get("updated_at") and status == "completed"
                    else None
                ),
                run_url=workflow_run.get("html_url"),
                event_payload=event_payload,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(new_run)
            db.flush()

            logger.info(
                "workflow_run_created",
                tracking_id=new_run.id,
                run_id=run_id,
                run_number=run_number,
                status=status,
                conclusion=conclusion,
            )

            # Check if workflow failed and create incident
            if conclusion == "failure":
                await self._create_incident_for_failure(
                    db=db,
                    workflow_run_record=new_run,
                    workflow_run_data=workflow_run,
                    repository_connection=repository_connection,
                )

            return new_run

    async def _create_incident_for_failure(
        self,
        db: Session,
        workflow_run_record: WorkflowRunTable,
        workflow_run_data: Dict[str, Any],
        repository_connection: RepositoryConnectionTable,
    ) -> Optional[IncidentTable]:
        """
        Create an incident for a failed workflow run.

        Args:
            db: Database session
            workflow_run_record: Workflow run tracking record
            workflow_run_data: GitHub workflow run data
            repository_connection: Repository connection

        Returns:
            Created incident record
        """
        try:
            # Generate incident ID
            incident_id = f"inc_{uuid.uuid4().hex}"

            # Build incident description
            description = (
                f"Workflow '{workflow_run_record.workflow_name}' failed in repository "
                f"{repository_connection.repository_full_name} on branch {workflow_run_record.branch}.\n\n"
                f"Run #{workflow_run_record.run_number}\n"
                f"Commit: {workflow_run_record.commit_sha[:7]}\n"
            )

            if workflow_run_record.commit_message:
                description += f"Message: {workflow_run_record.commit_message}\n"

            if workflow_run_record.author:
                description += f"Author: {workflow_run_record.author}\n"

            # Create incident
            incident = IncidentTable(
                incident_id=incident_id,
                user_id=repository_connection.user_id,
                title=f"Workflow failure: {workflow_run_record.workflow_name}",
                description=description,
                severity="high",
                status="open",
                source="github_oauth",
                source_url=workflow_run_record.run_url,
                repository=repository_connection.repository_full_name,
                branch=workflow_run_record.branch,
                commit_sha=workflow_run_record.commit_sha,
                workflow_name=workflow_run_record.workflow_name,
                job_name=None,  # Will be populated when we fetch job details
                error_message=None,  # Will be populated from logs
                stack_trace=None,  # Will be populated from logs
                metadata={
                    "workflow_run_id": workflow_run_record.run_id,
                    "workflow_run_tracking_id": workflow_run_record.id,
                    "repository_connection_id": repository_connection.id,
                    "run_number": workflow_run_record.run_number,
                    "workflow_id": workflow_run_record.workflow_id,
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(incident)

            # Link incident to workflow run
            workflow_run_record.incident_id = incident_id

            db.flush()

            logger.info(
                "incident_created_for_workflow_failure",
                incident_id=incident_id,
                workflow_run_id=workflow_run_record.id,
                repository=repository_connection.repository_full_name,
            )

            return incident

        except Exception as e:
            logger.error(
                "failed_to_create_incident",
                error=str(e),
                workflow_run_id=workflow_run_record.id,
                exc_info=True,
            )
            return None

    async def get_workflow_run_details(
        self,
        access_token: str,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Get detailed workflow run information from GitHub API.

        Args:
            access_token: GitHub OAuth access token
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID

        Returns:
            Workflow run details from GitHub API
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            return response.json()

    async def get_workflow_run_jobs(
        self,
        access_token: str,
        owner: str,
        repo: str,
        run_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Get jobs for a workflow run from GitHub API.

        Args:
            access_token: GitHub OAuth access token
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID

        Returns:
            List of job objects
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            data = response.json()
            return data.get("jobs", [])

    async def get_workflow_run_logs(
        self,
        access_token: str,
        owner: str,
        repo: str,
        run_id: int,
    ) -> bytes:
        """
        Download workflow run logs from GitHub API.

        Args:
            access_token: GitHub OAuth access token
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID

        Returns:
            Workflow run logs (ZIP archive)
        """
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            return response.content

    async def rerun_workflow(
        self,
        access_token: str,
        owner: str,
        repo: str,
        run_id: int,
        rerun_failed_jobs: bool = False,
    ) -> bool:
        """
        Rerun a workflow run or its failed jobs.

        Args:
            access_token: GitHub OAuth access token
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            rerun_failed_jobs: If True, only rerun failed jobs

        Returns:
            True if successful
        """
        endpoint = (
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs"
            if rerun_failed_jobs
            else f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/rerun"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code == 201:
                logger.info(
                    "workflow_rerun_triggered",
                    owner=owner,
                    repo=repo,
                    run_id=run_id,
                    failed_only=rerun_failed_jobs,
                )
                return True
            else:
                logger.error(
                    "workflow_rerun_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return False

    async def get_workflow_runs_for_repository(
        self,
        db: Session,
        repository_connection_id: str,
        status_filter: Optional[str] = None,
        conclusion_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[WorkflowRunTable]:
        """
        Get workflow runs for a repository connection.

        Args:
            db: Database session
            repository_connection_id: Repository connection ID
            status_filter: Filter by status (queued, in_progress, completed)
            conclusion_filter: Filter by conclusion (success, failure, cancelled, etc.)
            limit: Maximum number of runs to return

        Returns:
            List of workflow run records
        """
        query = db.query(WorkflowRunTable).filter(
            WorkflowRunTable.repository_connection_id == repository_connection_id
        )

        if status_filter:
            query = query.filter(WorkflowRunTable.status == status_filter)

        if conclusion_filter:
            query = query.filter(WorkflowRunTable.conclusion == conclusion_filter)

        runs = query.order_by(desc(WorkflowRunTable.created_at)).limit(limit).all()

        return runs

    async def get_workflow_run_stats(
        self,
        db: Session,
        user_id: str,
        repository_connection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get workflow run statistics for a user.

        Args:
            db: Database session
            user_id: User ID
            repository_connection_id: Optional repository connection filter

        Returns:
            Dictionary with statistics
        """
        query = (
            db.query(WorkflowRunTable)
            .join(
                RepositoryConnectionTable,
                WorkflowRunTable.repository_connection_id == RepositoryConnectionTable.id,
            )
            .filter(RepositoryConnectionTable.user_id == user_id)
        )

        if repository_connection_id:
            query = query.filter(
                WorkflowRunTable.repository_connection_id == repository_connection_id
            )

        all_runs = query.all()

        total_runs = len(all_runs)
        failed_runs = len([r for r in all_runs if r.conclusion == "failure"])
        successful_runs = len([r for r in all_runs if r.conclusion == "success"])
        in_progress_runs = len([r for r in all_runs if r.status == "in_progress"])

        # Calculate average duration
        completed_runs_with_duration = [
            r for r in all_runs
            if r.started_at and r.completed_at
        ]

        avg_duration = None
        if completed_runs_with_duration:
            total_duration = sum(
                (r.completed_at - r.started_at).total_seconds()
                for r in completed_runs_with_duration
            )
            avg_duration = total_duration / len(completed_runs_with_duration)

        # Calculate failure rate
        completed_runs = len([r for r in all_runs if r.status == "completed"])
        failure_rate = (failed_runs / completed_runs * 100) if completed_runs > 0 else 0.0

        # Count tracked repositories
        tracked_repos = (
            db.query(RepositoryConnectionTable.id)
            .filter(
                and_(
                    RepositoryConnectionTable.user_id == user_id,
                    RepositoryConnectionTable.is_enabled == True,
                )
            )
            .count()
        )

        return {
            "total_runs": total_runs,
            "failed_runs": failed_runs,
            "successful_runs": successful_runs,
            "in_progress_runs": in_progress_runs,
            "avg_duration_seconds": avg_duration,
            "failure_rate": failure_rate,
            "repositories_tracked": tracked_repos,
        }
