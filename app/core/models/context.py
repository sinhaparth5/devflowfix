# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.enums import Environment, ApprovalStatus

@dataclass
class ExecutionContext:
    """
    Value object representing the context for executing a remediation.
    
    Contains environment, constraints, and execution parameters.
    """

    # Environment
    environment: Environment = Environment.DEVELOPMENT

    # Execution Mode
    dry_run: bool = False

    # Approval
    requires_approval: bool = False
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    approval_timeout_minutes: int = 30
    approver: Optional[str] = None

    # Timing Constraints
    execution_timeout_seconds: int = 300
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5

    # Target Information
    repository: Optional[str] = None
    branch: Optional[str] = None
    cluster: Optional[str] = None
    namespace: Optional[str] = None
    service: Optional[str] = None

    # Safety Limits
    max_concurrent_executions: int = 5
    blast_radius_limit: int = 10

    # Rollback Configuration
    enable_rollback: bool = True
    rollback_on_failure: bool = True
    snapshot_ttl_hours: int = 24

    # Notificaiton Preferences
    notify_on_start: bool = False
    notify_on_success: bool = True
    notify_on_failure: bool = True
    notification_channel: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    correlation_id: Optional[str] = None
    tags: dict = field(default_factory=dict)

    def is_production(self) -> bool:
        """ Check if executing in production environment """
        return self.environment == Environment.PRODUCTION
    
    def is_dry_run(self) -> bool:
        """ Check if this is a dry run (simulation only) """
        return self.dry_run
    
    def needs_approval(self) -> bool:
        """ Check if approval is required """
        return self.requires_approval
    
    def is_approved(self) -> bool:
        """ Check if execution has been approved. """
        return self.approval_status == ApprovalStatus.APPROVED

    def is_approval_pending(self) -> bool:
        """ Check if approval is pending """
        return self.approval_status == ApprovalStatus.PENDING
    
    def is_safe_to_execute(self) -> bool:
        """
        Check if safe to execute based on context.
        
        Returns:
            True if safe to execute
        """
        # If approval required, must be approved
        if self.requires_approval and not self.is_approved():
            return False

        # Dry runs are always safe
        if self.dry_run:
            return True
        
        # Check if rollback is enabled for production
        if self.is_production() and not self.enable_rollback:
            return False
        
        return True
    
    def approve(self, approver: str) -> None:
        """
        Approve the execution.

        Args:
            approver: Username or ID of the approver
        """
        self.approval_status = ApprovalStatus.APPROVED
        self.approver = approver
    
    def reject(self, approver: str) -> None:
        """
        Reject the execution.
        
        Args:
            approver: Username or ID of the rejector
        """
        self.approval_status = ApprovalStatus.REJECTED
        self.approver = approver

    def mark_approval_timeout(self) -> None:
        """ Mark approval as timed out. """
        self.approval_status = ApprovalStatus.TIMEOUT

    def get_target_identifier(self) -> str:
        """
        Get a human-readable identifier for the target.
        
        Returns:
            String identifying the target (repo, service, etc.)
        """
        if self.repository:
            return self.repository
        if self.service:
            return f"{self.namespace}/{self.service}" if self.namespace else self.service
        if self.cluster:
            return self.cluster
        return "unknown"
    
    def add_tag(self, key: str, value: str) -> None:
        """ Add a tag to the context """
        self.tags[key] = value

    def get_tag(self, key: str, default: any = None) -> any:
        return self.tags.get(key, default)
    
    def to_dict(self) -> dict:
        """ Convert to dictionary """
        return {
            "environment": self.environment.value,
            "dry_run": self.dry_run,
            "requires_approval": self.requires_approval,
            "approval_status": self.approval_status.value,
            "execution_timeout_seconds": self.execution_timeout_seconds,
            "target": self.get_target_identifier(),
            "enable_rollback": self.enable_rollback,
        }
    
    def __repr__(self) -> str:
        """ String representation """
        return (
            f"ExecutionContext("
            f"env={self.environment.value}, "
            f"dry_run={self.dry_run}, "
            f"target={self.get_target_identifier()})"
        )