# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from app.core.events.base import BaseEvent, EventType
from app.core.enums import IncidentSource, Severity, FailureType

logger = structlog.get_logger(__name__)

@dataclass
class GitHubWorkflowEvent(BaseEvent):
    """
    GitHub workflow run event.
    
    Parses workflow_run webhook events from GitHub Actions.
    """
    # GitHub-specific fields
    workflow_id: Optional[int] = None
    run_id: Optional[int] = None
    run_number: Optional[int] = None
    run_attempt: Optional[int] = None
    action: Optional[str] = None  # requested, in_progress, completed
    conclusion: Optional[str] = None  # success, failure, cancelled, skipped
    html_url: Optional[str] = None
    logs_url: Optional[str] = None
    
    # Repository info
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    
    # Actor info
    actor: Optional[str] = None
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    
    def __post_init__(self):
        """Initialize and parse after dataclass creation."""
        self.source = IncidentSource.GITHUB
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        self.parse()
    
    def parse(self) -> None:
        """
        Parse GitHub workflow_run webhook payload.
        
        Extracts relevant information from the GitHub webhook payload.
        
        Raises:
            ValueError: If payload is missing required fields
        """
        try:
            # Get workflow_run object
            workflow_run = self.raw_payload.get("workflow_run", {})
            if not workflow_run:
                raise ValueError("Missing 'workflow_run' in payload")
            
            # Basic workflow info
            self.workflow_id = workflow_run.get("workflow_id")
            self.run_id = workflow_run.get("id")
            self.run_number = workflow_run.get("run_number")
            self.run_attempt = workflow_run.get("run_attempt", 1)
            self.workflow_name = workflow_run.get("name")
            self.html_url = workflow_run.get("html_url")
            
            # Action and conclusion
            self.action = self.raw_payload.get("action")
            self.conclusion = workflow_run.get("conclusion")
            
            # Repository info
            repository = self.raw_payload.get("repository", {})
            self.repository = repository.get("full_name")
            self.repo_owner = repository.get("owner", {}).get("login")
            self.repo_name = repository.get("name")
            
            # Branch and commit
            self.branch = workflow_run.get("head_branch")
            self.commit_sha = workflow_run.get("head_sha")
            
            # Actor
            actor = workflow_run.get("actor", {})
            self.actor = actor.get("login")
            
            # Event ID
            self.event_id = f"gh_wf_{self.run_id}"
            
            # Timing
            if workflow_run.get("run_started_at"):
                self.started_at = self._parse_github_timestamp(
                    workflow_run.get("run_started_at")
                )
            if workflow_run.get("updated_at"):
                self.completed_at = self._parse_github_timestamp(
                    workflow_run.get("updated_at")
                )
            
            # Calculate duration
            if self.started_at and self.completed_at:
                self.duration_seconds = int(
                    (self.completed_at - self.started_at).total_seconds()
                )
            
            # Determine event type and severity
            self._determine_event_type()
            self._extract_error_message()
            
            logger.debug(
                "github_event_parsed",
                event_id=self.event_id,
                workflow=self.workflow_name,
                conclusion=self.conclusion,
                repository=self.repository,
            )
            
        except Exception as e:
            logger.error(
                "github_event_parse_failed",
                error=str(e),
                payload_keys=list(self.raw_payload.keys()),
            )
            raise ValueError(f"Failed to parse GitHub webhook payload: {e}")
    
    def _determine_event_type(self) -> None:
        """Determine specific event type based on conclusion."""
        if self.conclusion == "failure":
            self.event_type = EventType.GITHUB_WORKFLOW_FAILED
            self.severity = Severity.HIGH
            self.failure_type = FailureType.BUILD_FAILURE.value
        elif self.conclusion == "success":
            self.event_type = EventType.GITHUB_WORKFLOW_SUCCESS
            self.severity = Severity.LOW
        else:
            # cancelled, skipped, timed_out, action_required, etc.
            self.event_type = EventType.GITHUB_WORKFLOW_FAILED
            self.severity = Severity.MEDIUM
    
    def _extract_error_message(self) -> None:
        """Extract error message from workflow run."""
        if self.conclusion == "failure":
            self.error_message = (
                f"Workflow '{self.workflow_name}' failed in {self.repository} "
                f"(run #{self.run_number}, attempt #{self.run_attempt})"
            )
        elif self.conclusion == "cancelled":
            self.error_message = f"Workflow '{self.workflow_name}' was cancelled"
        elif self.conclusion == "timed_out":
            self.error_message = f"Workflow '{self.workflow_name}' timed out"
            self.failure_type = FailureType.TIMEOUT_ERROR.value
        else:
            self.error_message = (
                f"Workflow '{self.workflow_name}' completed with status: {self.conclusion}"
            )
    
    def _parse_github_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse GitHub timestamp string to datetime.
        
        Args:
            timestamp_str: ISO format timestamp from GitHub
            
        Returns:
            Parsed datetime object
        """
        try:
            # GitHub uses ISO 8601 format: 2024-01-01T12:00:00Z
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.utcnow()
    
    def is_failure_event(self) -> bool:
        """
        Check if workflow failed.
        
        Returns:
            True if workflow conclusion is failure, cancelled, or timed_out
        """
        return self.conclusion in ["failure", "cancelled", "timed_out"]
    
    def get_context(self) -> Dict[str, Any]:
        """
        Get context information for incident creation.
        
        Returns:
            Dictionary with GitHub workflow context
        """
        return {
            "source": "github",
            "repository": self.repository,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "workflow_name": self.workflow_name,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "run_number": self.run_number,
            "run_attempt": self.run_attempt,
            "conclusion": self.conclusion,
            "action": self.action,
            "actor": self.actor,
            "html_url": self.html_url,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    def get_logs_url(self) -> Optional[str]:
        """
        Get URL to workflow run logs.
        
        Returns:
            URL to logs or None
        """
        if self.logs_url:
            return self.logs_url
        if self.html_url:
            return self.html_url
        if self.repository and self.run_id:
            return f"https://github.com/{self.repository}/actions/runs/{self.run_id}"
        return None
    
    def get_summary(self) -> str:
        """
        Get human-readable summary.
        
        Returns:
            Summary string
        """
        status = "✅" if self.conclusion == "success" else "❌"
        return (
            f"{status} GitHub workflow '{self.workflow_name}' "
            f"{self.conclusion} in {self.repository} "
            f"(run #{self.run_number})"
        )

@dataclass
class GitHubWorkflowFailedEvent(GitHubWorkflowEvent):
    """
    Specialized event for failed GitHub workflows.
    
    Convenience class that pre-sets event type to failure.
    """
    def __post_init__(self):
        """Initialize as failed event."""
        self.event_type = EventType.GITHUB_WORKFLOW_FAILED
        self.source = IncidentSource.GITHUB
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        self.parse()
        
        # Override to ensure it's marked as failure
        if self.conclusion not in ["failure", "cancelled", "timed_out"]:
            logger.warning(
                "github_failed_event_not_failure",
                event_id=self.event_id,
                conclusion=self.conclusion,
            )

@dataclass
class GitHubWorkflowJobEvent(BaseEvent):
    """
    GitHub workflow job event.
    
    Parses workflow_job webhook events for individual job failures.
    """
    # Job-specific fields
    job_id: Optional[int] = None
    job_name: Optional[str] = None
    job_status: Optional[str] = None  # queued, in_progress, completed
    job_conclusion: Optional[str] = None  # success, failure, cancelled, skipped
    steps: Optional[list] = None
    
    def __post_init__(self):
        """Initialize and parse after dataclass creation."""
        self.source = IncidentSource.GITHUB
        self.event_type = EventType.GITHUB_WORKFLOW_FAILED
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        self.parse()
    
    def parse(self) -> None:
        """
        Parse GitHub workflow_job webhook payload.
        
        Raises:
            ValueError: If payload is missing required fields
        """
        try:
            # Get workflow_job object
            workflow_job = self.raw_payload.get("workflow_job", {})
            if not workflow_job:
                raise ValueError("Missing 'workflow_job' in payload")
            
            # Job info
            self.job_id = workflow_job.get("id")
            self.job_name = workflow_job.get("name")
            self.job_status = workflow_job.get("status")
            self.job_conclusion = workflow_job.get("conclusion")
            self.html_url = workflow_job.get("html_url")
            
            # Steps
            self.steps = workflow_job.get("steps", [])
            
            # Repository info
            repository = self.raw_payload.get("repository", {})
            self.repository = repository.get("full_name")
            
            # Event ID
            self.event_id = f"gh_job_{self.job_id}"
            
            # Determine severity
            if self.job_conclusion == "failure":
                self.severity = Severity.HIGH
                self.error_message = f"Job '{self.job_name}' failed in {self.repository}"
            
            # Extract failed step
            self._extract_failed_step()
            
        except Exception as e:
            logger.error("github_job_event_parse_failed", error=str(e))
            raise ValueError(f"Failed to parse GitHub job webhook payload: {e}")
    
    def _extract_failed_step(self) -> None:
        """Extract information about failed step."""
        if not self.steps:
            return
        
        for step in self.steps:
            if step.get("conclusion") == "failure":
                step_name = step.get("name")
                self.error_message = (
                    f"Job '{self.job_name}' failed at step '{step_name}' "
                    f"in {self.repository}"
                )
                break
    
    def is_failure_event(self) -> bool:
        """Check if job failed."""
        return self.job_conclusion in ["failure", "cancelled", "timed_out"]
    
    def get_context(self) -> Dict[str, Any]:
        """Get context for incident creation."""
        return {
            "source": "github",
            "repository": self.repository,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "job_status": self.job_status,
            "job_conclusion": self.job_conclusion,
            "html_url": self.html_url,
            "failed_steps": [
                s.get("name") for s in self.steps 
                if s.get("conclusion") == "failure"
            ] if self.steps else [],
        }