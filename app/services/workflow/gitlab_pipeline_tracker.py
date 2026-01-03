# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitLab Pipeline Tracker Service

Tracks GitLab CI/CD pipeline runs and auto-creates incidents for failures.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc
import structlog
import uuid

from app.adapters.database.postgres.models import (
    WorkflowRunTable,
    IncidentTable,
    RepositoryConnectionTable,
)
from app.core.schemas.workflow import WorkflowRunResponse

logger = structlog.get_logger(__name__)


class GitLabPipelineTracker:
    """
    Tracks GitLab CI/CD pipeline runs and creates incidents for failures.

    Responsibilities:
    - Process GitLab pipeline webhook events
    - Create/update pipeline run records
    - Auto-create incidents for failed pipelines
    - Track pipeline status and metadata
    """

    async def process_pipeline_event(
        self,
        db: Session,
        event_payload: Dict[str, Any],
        repository_connection: RepositoryConnectionTable,
    ) -> Optional[WorkflowRunTable]:
        """
        Process GitLab pipeline webhook event.

        Args:
            db: Database session
            event_payload: GitLab pipeline webhook payload
            repository_connection: Repository connection record

        Returns:
            Created/updated WorkflowRunTable record or None

        GitLab Pipeline Event Payload Structure:
        {
            "object_kind": "pipeline",
            "object_attributes": {
                "id": 123,
                "ref": "main",
                "sha": "abc123",
                "status": "success|failed|running|pending|canceled",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:01:00Z",
                "finished_at": "2025-01-01T00:02:00Z",
                "duration": 120,
                "source": "push|web|merge_request_event",
            },
            "project": {
                "id": 456,
                "name": "my-project",
                "path_with_namespace": "group/my-project",
                "web_url": "https://gitlab.com/group/my-project",
            },
            "user": {
                "id": 789,
                "name": "John Doe",
                "username": "johndoe",
                "email": "john@example.com",
            },
            "commit": {
                "id": "abc123",
                "message": "Fix bug",
                "timestamp": "2025-01-01T00:00:00Z",
                "url": "https://gitlab.com/group/my-project/-/commit/abc123",
                "author": {
                    "name": "John Doe",
                    "email": "john@example.com",
                },
            },
            "builds": [
                {
                    "id": 111,
                    "stage": "test",
                    "name": "rspec",
                    "status": "failed",
                    "created_at": "2025-01-01T00:00:00Z",
                    "started_at": "2025-01-01T00:00:10Z",
                    "finished_at": "2025-01-01T00:01:00Z",
                    "duration": 50,
                    "allow_failure": false,
                    "failure_reason": "script_failure",
                }
            ]
        }
        """
        try:
            # Extract pipeline data
            pipeline = event_payload.get("object_attributes", {})
            project = event_payload.get("project", {})
            commit = event_payload.get("commit", {})
            user = event_payload.get("user", {})
            builds = event_payload.get("builds", [])

            pipeline_id = str(pipeline.get("id"))
            ref = pipeline.get("ref", "main")
            sha = pipeline.get("sha", "")
            status = pipeline.get("status", "unknown")
            created_at_str = pipeline.get("created_at")
            updated_at_str = pipeline.get("updated_at")
            finished_at_str = pipeline.get("finished_at")
            duration = pipeline.get("duration", 0)
            source = pipeline.get("source", "unknown")

            # Parse timestamps
            created_at = (
                datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at_str
                else datetime.now(timezone.utc)
            )
            updated_at = (
                datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at_str
                else None
            )
            finished_at = (
                datetime.fromisoformat(finished_at_str.replace("Z", "+00:00"))
                if finished_at_str
                else None
            )

            # Build pipeline URL
            project_url = project.get("web_url", "")
            pipeline_url = f"{project_url}/-/pipelines/{pipeline_id}" if project_url else ""

            # Map GitLab status to our status/conclusion
            run_status, conclusion = self._map_gitlab_status(status)

            logger.info(
                "processing_gitlab_pipeline_event",
                pipeline_id=pipeline_id,
                status=status,
                ref=ref,
                repository=repository_connection.repository_full_name,
            )

            # Check if run already exists
            existing_run = (
                db.query(WorkflowRunTable)
                .filter(
                    WorkflowRunTable.repository_connection_id == repository_connection.id,
                    WorkflowRunTable.run_id == pipeline_id,
                )
                .first()
            )

            if existing_run:
                # Update existing run
                existing_run.status = run_status
                existing_run.conclusion = conclusion
                existing_run.updated_at = updated_at or datetime.now(timezone.utc)
                existing_run.completed_at = finished_at
                existing_run.event_payload = event_payload

                db.add(existing_run)
                db.flush()

                logger.info(
                    "gitlab_pipeline_updated",
                    run_id=existing_run.id,
                    pipeline_id=pipeline_id,
                    status=run_status,
                    conclusion=conclusion,
                )

                # Create incident if pipeline just failed and no incident exists
                if conclusion == "failure" and not existing_run.incident_id:
                    await self._create_incident_for_failure(
                        db=db,
                        workflow_run=existing_run,
                        event_payload=event_payload,
                        repository_connection=repository_connection,
                        builds=builds,
                    )

                return existing_run

            else:
                # Create new run
                workflow_run = WorkflowRunTable(
                    id=str(uuid.uuid4()),
                    repository_connection_id=repository_connection.id,
                    run_id=pipeline_id,
                    workflow_id=f"gitlab-pipeline-{source}",
                    workflow_name=f"Pipeline ({source})",
                    status=run_status,
                    conclusion=conclusion,
                    branch=ref,
                    commit_sha=sha,
                    commit_message=commit.get("message", "")[:500],  # Truncate
                    author=user.get("username", "unknown"),
                    run_url=pipeline_url,
                    started_at=created_at,
                    completed_at=finished_at,
                    event_payload=event_payload,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )

                db.add(workflow_run)
                db.flush()

                logger.info(
                    "gitlab_pipeline_created",
                    run_id=workflow_run.id,
                    pipeline_id=pipeline_id,
                    status=run_status,
                    conclusion=conclusion,
                )

                # Create incident if pipeline failed
                if conclusion == "failure":
                    await self._create_incident_for_failure(
                        db=db,
                        workflow_run=workflow_run,
                        event_payload=event_payload,
                        repository_connection=repository_connection,
                        builds=builds,
                    )

                return workflow_run

        except Exception as e:
            logger.error(
                "gitlab_pipeline_processing_error",
                error=str(e),
                exc_info=True,
            )
            return None

    def _map_gitlab_status(self, gitlab_status: str) -> tuple[str, Optional[str]]:
        """
        Map GitLab pipeline status to our status/conclusion format.

        GitLab statuses: created, waiting_for_resource, preparing, pending,
                        running, success, failed, canceled, skipped, manual

        Args:
            gitlab_status: GitLab pipeline status

        Returns:
            Tuple of (status, conclusion)
        """
        status_map = {
            "created": ("queued", None),
            "waiting_for_resource": ("queued", None),
            "preparing": ("queued", None),
            "pending": ("queued", None),
            "running": ("in_progress", None),
            "success": ("completed", "success"),
            "failed": ("completed", "failure"),
            "canceled": ("completed", "cancelled"),
            "skipped": ("completed", "skipped"),
            "manual": ("completed", "action_required"),
        }

        return status_map.get(gitlab_status, ("completed", "unknown"))

    async def _create_incident_for_failure(
        self,
        db: Session,
        workflow_run: WorkflowRunTable,
        event_payload: Dict[str, Any],
        repository_connection: RepositoryConnectionTable,
        builds: List[Dict[str, Any]],
    ) -> Optional[IncidentTable]:
        """
        Create incident for failed pipeline.

        Args:
            db: Database session
            workflow_run: Workflow run record
            event_payload: Full event payload
            repository_connection: Repository connection
            builds: List of job/build objects

        Returns:
            Created incident or None
        """
        try:
            pipeline = event_payload.get("object_attributes", {})
            commit = event_payload.get("commit", {})
            project = event_payload.get("project", {})

            # Extract failed jobs
            failed_builds = [b for b in builds if b.get("status") == "failed"]

            # Build failure summary
            failure_summary = self._build_failure_summary(
                pipeline=pipeline,
                failed_builds=failed_builds,
                commit=commit,
            )

            # Determine severity based on branch and failure type
            severity = self._determine_severity(
                branch=pipeline.get("ref", ""),
                failed_builds=failed_builds,
            )

            # Create incident
            incident = IncidentTable(
                incident_id=str(uuid.uuid4()),
                user_id=repository_connection.user_id,
                repository=repository_connection.repository_full_name,
                branch=pipeline.get("ref", "main"),
                commit_sha=pipeline.get("sha", ""),
                workflow_name=f"Pipeline ({pipeline.get('source', 'unknown')})",
                job_name=failed_builds[0].get("name", "unknown") if failed_builds else "pipeline",
                error_message=failure_summary,
                status="open",
                severity=severity,
                source="gitlab_ci",
                metadata={
                    "pipeline_id": pipeline.get("id"),
                    "pipeline_url": f"{project.get('web_url', '')}/-/pipelines/{pipeline.get('id')}",
                    "failed_jobs": [
                        {
                            "id": b.get("id"),
                            "name": b.get("name"),
                            "stage": b.get("stage"),
                            "failure_reason": b.get("failure_reason"),
                        }
                        for b in failed_builds
                    ],
                    "commit_message": commit.get("message", ""),
                    "commit_author": commit.get("author", {}).get("name", ""),
                    "source": pipeline.get("source"),
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(incident)
            db.flush()

            # Link incident to workflow run
            workflow_run.incident_id = incident.incident_id
            db.add(workflow_run)
            db.flush()

            logger.info(
                "gitlab_incident_created",
                incident_id=incident.incident_id,
                pipeline_id=pipeline.get("id"),
                severity=severity,
                failed_jobs=len(failed_builds),
            )

            return incident

        except Exception as e:
            logger.error(
                "gitlab_incident_creation_error",
                error=str(e),
                exc_info=True,
            )
            return None

    def _build_failure_summary(
        self,
        pipeline: Dict[str, Any],
        failed_builds: List[Dict[str, Any]],
        commit: Dict[str, Any],
    ) -> str:
        """
        Build human-readable failure summary.

        Args:
            pipeline: Pipeline object
            failed_builds: List of failed job objects
            commit: Commit object

        Returns:
            Failure summary string
        """
        if not failed_builds:
            return f"GitLab pipeline #{pipeline.get('id')} failed"

        job_names = ", ".join([b.get("name", "unknown") for b in failed_builds[:3]])
        if len(failed_builds) > 3:
            job_names += f" (+{len(failed_builds) - 3} more)"

        summary = f"GitLab pipeline failed: {job_names}"

        # Add failure reasons if available
        failure_reasons = set(
            b.get("failure_reason")
            for b in failed_builds
            if b.get("failure_reason")
        )
        if failure_reasons:
            summary += f" ({', '.join(failure_reasons)})"

        return summary

    def _determine_severity(
        self,
        branch: str,
        failed_builds: List[Dict[str, Any]],
    ) -> str:
        """
        Determine incident severity based on context.

        Args:
            branch: Branch name
            failed_builds: List of failed jobs

        Returns:
            Severity level (critical, high, medium, low)
        """
        # Production branches get higher severity
        production_branches = ["main", "master", "production", "prod"]
        if branch in production_branches:
            return "high"

        # Multiple failed jobs = higher severity
        if len(failed_builds) > 3:
            return "high"

        # Check for critical failure reasons
        critical_reasons = ["unknown_failure", "api_failure", "runner_system_failure"]
        for build in failed_builds:
            if build.get("failure_reason") in critical_reasons:
                return "high"

        # Default to medium
        return "medium"

    async def get_pipeline_runs(
        self,
        db: Session,
        repository_connection_id: str,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[WorkflowRunTable]:
        """
        Get pipeline runs for a repository.

        Args:
            db: Database session
            repository_connection_id: Repository connection ID
            limit: Maximum number of runs to return
            status: Optional status filter

        Returns:
            List of workflow run records
        """
        query = db.query(WorkflowRunTable).filter(
            WorkflowRunTable.repository_connection_id == repository_connection_id
        )

        if status:
            query = query.filter(WorkflowRunTable.status == status)

        runs = query.order_by(desc(WorkflowRunTable.created_at)).limit(limit).all()

        return runs

    async def get_pipeline_stats(
        self,
        db: Session,
        repository_connection_id: str,
    ) -> Dict[str, Any]:
        """
        Get pipeline statistics for a repository.

        Args:
            db: Database session
            repository_connection_id: Repository connection ID

        Returns:
            Statistics dictionary
        """
        runs = db.query(WorkflowRunTable).filter(
            WorkflowRunTable.repository_connection_id == repository_connection_id
        ).all()

        total_runs = len(runs)
        successful_runs = len([r for r in runs if r.conclusion == "success"])
        failed_runs = len([r for r in runs if r.conclusion == "failure"])
        cancelled_runs = len([r for r in runs if r.conclusion == "cancelled"])

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "cancelled_runs": cancelled_runs,
            "success_rate": (successful_runs / total_runs * 100) if total_runs > 0 else 0.0,
            "failure_rate": (failed_runs / total_runs * 100) if total_runs > 0 else 0.0,
        }
