# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.enums import RemediationActionType, RiskLevel, Outcome

@dataclass
class RemediationPlan:
    """
    Value object representing a plan to fix an incident.

    Contains the action to execute and its parameters
    """
    # Action Details
    action_type: RemediationActionType
    parameters: dict = field(default_factory=dict)

    # Risk Assessment
    risk_level: RiskLevel = RiskLevel.MEDIUM
    estimated_duration_seconds: int = 60
    
    # Prerequisites
    requires_approval: bool = False
    requires_rollback_snapshot = True

    # Validation
    pre_validation_checks: list[str] = field(default_factory=list)
    post_validation_checks: list[str] = field(default_factory=list)

    # Context
    reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_safe_to_execute(self) -> bool:
        """ Check if plan safe to execute without approval. """
        return self.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
    
    def is_high_risk(self) -> bool:
        """ Check if plan is high risk """
        return self.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    
    def add_parameter(self, key: str, value: any) -> None:
        """ Add a parameter to the plan """
        self.parameters[key] = value

    def get_parameter(self, key: str, default: any = None) -> any:
        """ Get a parameter value. """
        return self.parameters.get(key, default)
    
    def to_dict(self) -> dict:
        """ Convert to dictornary """
        return {
            "action_type": self.action_type.value,
            "parameters": self.parameters,
            "risk_level": self.risk_level.value,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }
    
@dataclass
class RemediationResult:
    """
    Value object representing the result of a rememdiation execution.

    Contains the outcome and any error details.
    """

    # Outcome
    success: bool
    outcome: Outcome

    # Timing
    executed_at: datetime = field(default_factory=datetime.utcnow)
    duration_seconds: Optional[int] = None

    # Details
    message: Optional[str] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None

    # Actions Taken
    actions_performed: list[str] = field(default_factory=list)

    # Validation Results
    pre_validation_passed: bool = True
    post_validation_passed: bool = True
    validation_details: dict = field(default_factory=dict)

    # Rollback
    rollback_required: bool = False
    rollback_performed: bool = False
    rollback_snapshot_id: Optional[str] = None

    # Metadata
    execution_logs: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def is_successful(self) -> bool:
        """ Check if remediation was successful. """
        return self.success and self.outcome == Outcome.SUCCESS
    
    def is_failed(self) -> bool:
        """ Check if remediation failed """
        return not self.success or self.outcome == Outcome.FAILED
    
    def needs_rollback(self) -> bool:
        """ Check if rollback is needed. """
        return self.rollback_required and not self.rollback_performed
    
    def add_action_performed(self, action: str) -> None:
        """ Record an action that was performed """
        self.actions_performed.append(action)

    def add_log(self, log: str) -> None:
        """ And an execution log entry. """
        timestamp = datetime.utcnow().isoformat()
        self.execution_logs.append(f"[{timestamp}] {log}")

    def set_error(self, error_message: str, traceback: Optional[str] = None) -> None:
        """ Set error details """
        self.success = False
        self.outcome = Outcome.FAILED
        self.error_message = error_message
        self.error_traceback = traceback

    def to_dict(self) -> dict:
        """ Convert to dictionary. """
        return {
            "success": self.success,
            "outcome": self.outcome.value,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
            "error_message": self.error_message,
            "actions_performed": self.actions_performed,
            "rollback_required": self.rollback_required,
            "executed_at": self.executed_at.isoformat(),
        }
    
@dataclass
class RollbackSnapshot:
    """
    Value object representing a snapshot for rollback.

    Captures system state before remediation for potential rollback.
    """

    # Identity
    snapshot_id: str
    incident_id: str

    # Snapshot Data
    snapshot_data: dict = field(default_factory=dict)
    snapshot_type: str = "generic"

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at : Optional[datetime] = None

    # Status
    is_restored: bool = False
    restored_at: Optional[datetime] = None

    # Metadata
    description: Optional[str] = None

    def is_expired(self) -> bool:
        """ Check if snapshot has expired """
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def mark_restored(self) -> None:
        """ Mark snapshot as restored """
        self.is_restored = True
        self.restored_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """ Convert to dictionary """
        return {
            "snapshot_id": self.snapshot_id,
            "incident_id": self.incident_id,
            "snapshot_type": self.snapshot_type,
            "created_at": self.created_at.isoformat(),
            "is_restored": self.is_restored,
        }

