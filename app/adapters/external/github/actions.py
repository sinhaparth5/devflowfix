# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub Actions Adapter

High-level adapter for GitHub Actions workflow operations including:
- Rerunning workflows and failed jobs
- Waiting for workflow completion with polling
- Checking workflow success/failure status
- Extracting failure information from jobs
"""

import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from enum import Enum

from app.adapters.external.github.client import GitHubClient
from app.core.config import Settings
from app.exceptions import GitHubAPIError, RemediationTimeoutError, RemediationFailedError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class WorkflowStatus(str, Enum):
    """GitHub Actions workflow run status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"
    REQUESTED = "requested"
    PENDING = "pending"


class WorkflowConclusion(str, Enum):
    """GitHub Actions workflow run conclusion."""
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    NEUTRAL = "neutral"
    STARTUP_FAILURE = "startup_failure"


class GitHubActionsAdapter:
    """
    Adapter for GitHub Actions workflow operations.
    
    Provides high-level operations for:
    - Rerunning workflows with automatic retry logic
    - Waiting for workflow completion with configurable polling
    - Checking workflow success/failure
    - Extracting detailed failure information
    
    Example:
        ```python
        adapter = GitHubActionsAdapter()
        
        # Rerun workflow and wait for completion
        result = await adapter.rerun_workflow(
            owner="myorg",
            repo="myrepo",
            run_id=123456,
            wait_for_completion=True,
        )
        
        if result["success"]:
            print("Workflow succeeded!")
        else:
            print(f"Workflow failed: {result['failure_reason']}")
        ```
    """
    
    def __init__(
        self,
        client: Optional[GitHubClient] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize GitHub Actions adapter.
        
        Args:
            client: GitHub API client (creates new if not provided)
            settings: Application settings
        """
        self.settings = settings or Settings()
        self.client = client or GitHubClient(settings=self.settings)
        self._owns_client = client is None
    
    async def rerun_workflow(
        self,
        owner: str,
        repo: str,
        run_id: int,
        wait_for_completion: bool = True,
        timeout: float = 600.0,
        poll_interval: float = 10.0,
        rerun_failed_only: bool = True,
    ) -> Dict[str, Any]:
        """
        Rerun a GitHub Actions workflow and optionally wait for completion.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID to rerun
            wait_for_completion: Whether to wait for workflow to complete
            timeout: Maximum time to wait in seconds (default: 10 minutes)
            poll_interval: Seconds between status checks (default: 10s)
            rerun_failed_only: Only rerun failed jobs (default: True)
            
        Returns:
            Dictionary with:
                - success: bool - Whether workflow succeeded
                - status: str - Final workflow status
                - conclusion: str - Final workflow conclusion
                - run_id: int - New run ID (may differ from input)
                - duration: float - Time taken in seconds
                - url: str - Workflow run URL
                - failure_reason: str - Reason for failure (if failed)
                - failed_jobs: List[Dict] - Details of failed jobs
                
        Raises:
            GitHubAPIError: On API errors
            RemediationTimeoutError: If workflow doesn't complete within timeout
        """
        start_time = datetime.now()
        
        logger.info(
            "github_rerun_workflow_start",
            owner=owner,
            repo=repo,
            run_id=run_id,
            rerun_failed_only=rerun_failed_only,
        )
        
        original_run = await self.client.get_workflow_run(owner, repo, run_id)
        
        if rerun_failed_only:
            await self.client.rerun_failed_jobs(owner, repo, run_id)
        else:
            await self.client.rerun_workflow(owner, repo, run_id)
        
        logger.info(
            "github_rerun_triggered",
            owner=owner,
            repo=repo,
            run_id=run_id,
            workflow_name=original_run.get("name"),
        )
        
        if not wait_for_completion:
            return {
                "success": None,  
                "status": "queued",
                "conclusion": None,
                "run_id": run_id,
                "duration": 0.0,
                "url": original_run.get("html_url"),
                "workflow_name": original_run.get("name"),
            }
        
        result = await self.wait_for_completion(
            owner=owner,
            repo=repo,
            run_id=run_id,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        result["duration"] = duration
        
        logger.info(
            "github_rerun_workflow_complete",
            owner=owner,
            repo=repo,
            run_id=run_id,
            success=result["success"],
            duration=duration,
        )
        
        return result
    
    async def wait_for_completion(
        self,
        owner: str,
        repo: str,
        run_id: int,
        timeout: float = 600.0,
        poll_interval: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Wait for a workflow run to complete.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            timeout: Maximum time to wait in seconds
            poll_interval: Seconds between status checks
            
        Returns:
            Dictionary with workflow completion details
            
        Raises:
            RemediationTimeoutError: If workflow doesn't complete within timeout
        """
        start_time = datetime.now()
        timeout_time = start_time + timedelta(seconds=timeout)
        
        logger.info(
            "github_wait_for_completion_start",
            owner=owner,
            repo=repo,
            run_id=run_id,
            timeout=timeout,
        )
        
        while datetime.now() < timeout_time:
            run = await self.client.get_workflow_run(owner, repo, run_id)
            
            status = run.get("status")
            conclusion = run.get("conclusion")
            
            logger.debug(
                "github_workflow_status_check",
                owner=owner,
                repo=repo,
                run_id=run_id,
                status=status,
                conclusion=conclusion,
            )
            
            if status == WorkflowStatus.COMPLETED.value:
                success = conclusion == WorkflowConclusion.SUCCESS.value
                
                result = {
                    "success": success,
                    "status": status,
                    "conclusion": conclusion,
                    "run_id": run_id,
                    "url": run.get("html_url"),
                    "workflow_name": run.get("name"),
                    "run_number": run.get("run_number"),
                }
                
                if not success:
                    failure_info = await self._get_failure_details(owner, repo, run_id)
                    result.update(failure_info)
                
                return result
            
            await asyncio.sleep(poll_interval)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        logger.error(
            "github_workflow_timeout",
            owner=owner,
            repo=repo,
            run_id=run_id,
            elapsed=elapsed,
            timeout=timeout,
        )
        
        raise RemediationTimeoutError(
            f"Workflow {run_id} did not complete within {timeout}s timeout",
            timeout=timeout,
            elapsed=elapsed,
        )
    
    async def check_workflow_success(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> bool:
        """
        Check if a workflow run succeeded.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            True if workflow completed successfully, False otherwise
        """
        run = await self.client.get_workflow_run(owner, repo, run_id)
        
        status = run.get("status")
        conclusion = run.get("conclusion")
        
        is_complete = status == WorkflowStatus.COMPLETED.value
        is_success = conclusion == WorkflowConclusion.SUCCESS.value
        
        return is_complete and is_success
    
    async def _get_failure_details(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Get detailed failure information for a failed workflow.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Dictionary with failure_reason and failed_jobs
        """
        try:
            jobs = await self.client.list_jobs_for_workflow_run(owner, repo, run_id)
            
            failed_jobs = [
                {
                    "id": job["id"],
                    "name": job["name"],
                    "conclusion": job.get("conclusion"),
                    "started_at": job.get("started_at"),
                    "completed_at": job.get("completed_at"),
                    "url": job.get("html_url"),
                }
                for job in jobs
                if job.get("conclusion") not in [WorkflowConclusion.SUCCESS.value, None]
            ]
            
            if failed_jobs:
                job_names = [job["name"] for job in failed_jobs]
                failure_reason = f"{len(failed_jobs)} job(s) failed: {', '.join(job_names)}"
            else:
                failure_reason = "Workflow failed with no specific job failures"
            
            return {
                "failure_reason": failure_reason,
                "failed_jobs": failed_jobs,
                "total_jobs": len(jobs),
                "failed_job_count": len(failed_jobs),
            }
        
        except Exception as e:
            logger.warning(
                "github_failure_details_error",
                owner=owner,
                repo=repo,
                run_id=run_id,
                error=str(e),
            )
            return {
                "failure_reason": "Failed to retrieve failure details",
                "failed_jobs": [],
                "total_jobs": 0,
                "failed_job_count": 0,
            }
    
    async def get_workflow_logs(
        self,
        owner: str,
        repo: str,
        run_id: int,
        failed_only: bool = True,
    ) -> Dict[int, str]:
        """
        Download logs from workflow jobs.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            failed_only: Only download logs from failed jobs
            
        Returns:
            Dictionary mapping job_id to log content
        """
        jobs = await self.client.list_jobs_for_workflow_run(owner, repo, run_id)
        
        if failed_only:
            jobs = [
                job for job in jobs
                if job.get("conclusion") not in [WorkflowConclusion.SUCCESS.value, None]
            ]
        
        logs = {}
        for job in jobs:
            job_id = job["id"]
            try:
                log_content = await self.client.download_job_logs(owner, repo, job_id)
                logs[job_id] = log_content
                
                logger.debug(
                    "github_job_logs_downloaded",
                    owner=owner,
                    repo=repo,
                    job_id=job_id,
                    log_size=len(log_content),
                )
            
            except Exception as e:
                logger.warning(
                    "github_job_logs_error",
                    owner=owner,
                    repo=repo,
                    job_id=job_id,
                    error=str(e),
                )
        
        return logs
    
    async def get_workflow_status_summary(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Get comprehensive status summary for a workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Detailed status summary including run info and job statuses
        """
        run = await self.client.get_workflow_run(owner, repo, run_id)
        jobs = await self.client.list_jobs_for_workflow_run(owner, repo, run_id)
        
        job_conclusions = {}
        for job in jobs:
            conclusion = job.get("conclusion", "pending")
            job_conclusions[conclusion] = job_conclusions.get(conclusion, 0) + 1
        
        return {
            "run_id": run_id,
            "workflow_name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "run_number": run.get("run_number"),
            "url": run.get("html_url"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "total_jobs": len(jobs),
            "job_conclusions": job_conclusions,
            "success_count": job_conclusions.get(WorkflowConclusion.SUCCESS.value, 0),
            "failure_count": job_conclusions.get(WorkflowConclusion.FAILURE.value, 0),
        }
    
    async def cancel_workflow(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Cancel a running workflow.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Cancellation confirmation
        """
        logger.info(
            "github_cancel_workflow",
            owner=owner,
            repo=repo,
            run_id=run_id,
        )
        
        await self.client.cancel_workflow_run(owner, repo, run_id)
        
        return {
            "cancelled": True,
            "run_id": run_id,
        }
    
    async def close(self) -> None:
        """Close the adapter and underlying client if owned."""
        if self._owns_client:
            await self.client.close()
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
