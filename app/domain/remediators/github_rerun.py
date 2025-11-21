# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub Workflow Rerun Remediator

Remediates GitHub Actions workflow failures by rerunning failed jobs.
Extracts repository and run information from incident context and triggers rerun.
"""

import traceback
from typing import Optional
from datetime import datetime

from app.domain.remediators.base import BaseRemediator
from app.adapters.external.github.actions import GitHubActionsAdapter, WorkflowConclusion
from app.adapters.external.github.client import GitHubClient
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import RemediationActionType, Outcome
from app.core.config import Settings
from app.exceptions import RemediationFailedError, RemediationTimeoutError, GitHubAPIError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GitHubRerunRemediator(BaseRemediator):
    """
    Remediator for GitHub Actions workflow failures.
    
    Extracts repository and workflow run information from incident context,
    then triggers a rerun of failed jobs and waits for completion.
    
    Required incident context fields:
    - owner: Repository owner (from incident.context or plan.parameters)
    - repo: Repository name (from incident.context or plan.parameters)
    - run_id: Workflow run ID (from incident.context or plan.parameters)
    
    Optional parameters:
    - wait_for_completion: Whether to wait for workflow to complete (default: True)
    - timeout: Max time to wait in seconds (default: 600)
    - poll_interval: Seconds between status checks (default: 10)
    - rerun_failed_only: Only rerun failed jobs vs entire workflow (default: True)
    
    Example:
        ```python
        remediator = GitHubRerunRemediator()
        
        incident = Incident(
            source=IncidentSource.GITHUB,
            context={
                "owner": "myorg",
                "repo": "myrepo",
                "run_id": 123456789,
            }
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        )
        
        result = await remediator.execute(incident, plan)
        ```
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        github_client: Optional[GitHubClient] = None,
    ):
        """
        Initialize GitHub rerun remediator.
        
        Args:
            settings: Application settings
            github_client: GitHub API client (creates new if not provided)
        """
        super().__init__(settings)
        self._github_client = github_client
        self._adapter: Optional[GitHubActionsAdapter] = None
    
    def get_action_type(self) -> RemediationActionType:
        """Get the action type this remediator handles."""
        return RemediationActionType.GITHUB_RERUN_WORKFLOW
    
    async def _get_adapter(self) -> GitHubActionsAdapter:
        """Get or create GitHub Actions adapter."""
        if self._adapter is None:
            if self._github_client:
                self._adapter = GitHubActionsAdapter(client=self._github_client)
            else:
                self._adapter = GitHubActionsAdapter(settings=self.settings)
        return self._adapter
    
    def _extract_parameters(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> dict:
        """
        Extract required parameters from incident context and plan.
        
        Tries multiple sources in order:
        1. Plan parameters (explicit override)
        2. Incident context
        3. Incident raw_payload
        
        Args:
            incident: Incident to extract from
            plan: Remediation plan
            
        Returns:
            Dictionary with owner, repo, run_id, and optional parameters
            
        Raises:
            ValueError: If required parameters are missing
        """
        params = {}
        
        params["owner"] = (
            plan.get_parameter("owner")
            or incident.context.get("owner")
            or incident.context.get("repository_owner")
            or incident.raw_payload.get("repository", {}).get("owner", {}).get("login")
        )
        
        params["repo"] = (
            plan.get_parameter("repo")
            or incident.context.get("repo")
            or incident.context.get("repository")
            or incident.context.get("repository_name")
            or incident.raw_payload.get("repository", {}).get("name")
        )
        
        params["run_id"] = (
            plan.get_parameter("run_id")
            or incident.context.get("run_id")
            or incident.context.get("workflow_run_id")
            or incident.raw_payload.get("workflow_run", {}).get("id")
        )
        
        missing = []
        for key in ["owner", "repo", "run_id"]:
            if not params.get(key):
                missing.append(key)
        
        if missing:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing)}. "
                f"Provide in plan.parameters or incident.context"
            )
        
        if isinstance(params["run_id"], str):
            try:
                params["run_id"] = int(params["run_id"])
            except ValueError:
                raise ValueError(f"run_id must be numeric, got: {params['run_id']}")
        
        params["wait_for_completion"] = plan.get_parameter("wait_for_completion", True)
        params["timeout"] = plan.get_parameter("timeout", 600.0)
        params["poll_interval"] = plan.get_parameter("poll_interval", 10.0)
        params["rerun_failed_only"] = plan.get_parameter("rerun_failed_only", True)
        
        return params
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """
        Execute GitHub workflow rerun remediation.
        
        Args:
            incident: Incident with GitHub workflow failure
            plan: Remediation plan
            
        Returns:
            RemediationResult with success status and details
        """
        self._log_execution_start(incident, plan)
        start_time = datetime.now()
        
        try:
            params = self._extract_parameters(incident, plan)
            
            owner = params["owner"]
            repo = params["repo"]
            run_id = params["run_id"]
            wait_for_completion = params["wait_for_completion"]
            timeout = params["timeout"]
            poll_interval = params["poll_interval"]
            rerun_failed_only = params["rerun_failed_only"]
            
            self.logger.info(
                "github_rerun_start",
                incident_id=incident.incident_id,
                owner=owner,
                repo=repo,
                run_id=run_id,
                wait_for_completion=wait_for_completion,
                rerun_failed_only=rerun_failed_only,
            )
            
            adapter = await self._get_adapter()
            
            rerun_result = await adapter.rerun_workflow(
                owner=owner,
                repo=repo,
                run_id=run_id,
                wait_for_completion=wait_for_completion,
                timeout=timeout,
                poll_interval=poll_interval,
                rerun_failed_only=rerun_failed_only,
            )
            
            duration = (datetime.now() - start_time).seconds
            
            actions = [
                f"Triggered rerun of workflow run {run_id} for {owner}/{repo}",
            ]
            
            if rerun_failed_only:
                actions.append("Reran only failed jobs")
            else:
                actions.append("Reran entire workflow")
            
            if wait_for_completion:
                actions.append(f"Waited for workflow completion ({rerun_result.get('duration', 0):.1f}s)")
            
            metadata = {
                "owner": owner,
                "repo": repo,
                "run_id": run_id,
                "workflow_url": rerun_result.get("url"),
                "workflow_name": rerun_result.get("workflow_name"),
                "run_number": rerun_result.get("run_number"),
                "rerun_failed_only": rerun_failed_only,
            }
            
            if wait_for_completion:
                workflow_success = rerun_result.get("success")
                
                if workflow_success:
                    result = self._create_success_result(
                        message=f"Workflow rerun succeeded for {owner}/{repo} run {run_id}",
                        duration_seconds=duration,
                        actions_performed=actions + ["Workflow completed successfully"],
                        metadata=metadata,
                    )
                else:
                    failure_reason = rerun_result.get("failure_reason", "Unknown failure")
                    failed_jobs = rerun_result.get("failed_jobs", [])
                    
                    metadata["failure_reason"] = failure_reason
                    metadata["failed_jobs"] = failed_jobs
                    metadata["failed_job_count"] = len(failed_jobs)
                    
                    result = self._create_failure_result(
                        message=f"Workflow rerun failed for {owner}/{repo} run {run_id}",
                        error_message=failure_reason,
                        duration_seconds=duration,
                        actions_performed=actions + [f"Workflow failed: {failure_reason}"],
                        metadata=metadata,
                        rollback_required=False,
                    )
            else:
                result = self._create_success_result(
                    message=f"Workflow rerun triggered for {owner}/{repo} run {run_id} (not waiting)",
                    duration_seconds=duration,
                    actions_performed=actions,
                    metadata=metadata,
                )
            
            self._log_execution_complete(incident, result)
            return result
        
        except ValueError as e:
            duration = (datetime.now() - start_time).seconds
            result = self._create_failure_result(
                message="Parameter validation failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            self._log_execution_complete(incident, result)
            return result
        
        except RemediationTimeoutError as e:
            duration = (datetime.now() - start_time).seconds
            result = self._create_failure_result(
                message="Workflow rerun timed out",
                error_message=str(e),
                duration_seconds=duration,
                actions_performed=["Triggered workflow rerun", "Timed out waiting for completion"],
                metadata={"timeout": timeout},
            )
            self._log_execution_complete(incident, result)
            return result
        
        except GitHubAPIError as e:
            duration = (datetime.now() - start_time).seconds
            result = self._create_failure_result(
                message="GitHub API error during workflow rerun",
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                duration_seconds=duration,
            )
            self._log_execution_complete(incident, result)
            return result
        
        except Exception as e:
            duration = (datetime.now() - start_time).seconds
            self.logger.error(
                "github_rerun_unexpected_error",
                incident_id=incident.incident_id,
                error=str(e),
                traceback=traceback.format_exc(),
            )
            
            result = self._create_failure_result(
                message="Unexpected error during workflow rerun",
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                duration_seconds=duration,
            )
            self._log_execution_complete(incident, result)
            return result
    
    async def close(self):
        """Close adapter and client resources."""
        if self._adapter:
            await self._adapter.close()
