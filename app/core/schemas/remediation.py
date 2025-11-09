# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import RemediationActionType, RiskLevel, Outcome

class RemediationRequest(BaseModel):
    """ Request to execute remediation. """    
    incident_id: str = Field(..., description="Incident ID to remediate")
    action_type: Optional[RemediationActionType] = Field(
        None,
        description="Specific action to execute (auto-determined if not provided)"
    )
    parameters: dict = Field(default_factory=dict, description="Action-specific parameters")
    dry_run: bool = Field(False, description="Simulate without executing")
    force: bool = Field(False, description="Force execution even if validation fails")

class RemediationPlanResponse(BaseModel):
    """ Remediation plan details. """
    incident_id: str
    action_type: RemediationActionType
    parameters: dict
    risk_level: RiskLevel
    estimated_duration_seconds: int
    requires_approval: bool
    requires_rollback_snapshot: bool
    reason: Optional[str] = None
    
    # Pre-checks
    pre_validation_checks: list[str] = Field(default_factory=list)
    post_validation_checks: list[str] = Field(default_factory=list)

class RemediationResponse(BaseModel):
    """ Response from remediation execution. """    
    incident_id: str
    success: bool
    outcome: Outcome
    
    # Timing
    executed_at: datetime
    duration_seconds: Optional[int] = None
    
    # Details
    message: Optional[str] = None
    error_message: Optional[str] = None
    actions_performed: list[str] = Field(default_factory=list)
    
    # Validation
    pre_validation_passed: bool
    post_validation_passed: bool
    
    # Rollback
    rollback_required: bool = False
    rollback_performed: bool = False
    rollback_snapshot_id: Optional[str] = None

class RemediationStatusResponse(BaseModel):
    """ Current status of remediation. """    
    incident_id: str
    status: str = Field(..., description="Status: pending, in_progress, completed, failed")
    
    # Execution details
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step: Optional[str] = None
    progress_percentage: int = Field(0, ge=0, le=100)
    
    # Results (if completed)
    success: Optional[bool] = None
    outcome: Optional[Outcome] = None
    message: Optional[str] = None

class RollbackRequest(BaseModel):
    """ Request to rollback a remediation. """    
    incident_id: str = Field(..., description="Incident ID to rollback")
    snapshot_id: Optional[str] = Field(None, description="Specific snapshot to restore")
    reason: str = Field(..., description="Reason for rollback")
    force: bool = Field(False, description="Force rollback even if validation fails")

class RollbackResponse(BaseModel):
    """ Response from rollback execution. """    
    incident_id: str
    snapshot_id: str
    success: bool
    message: str
    restored_at: datetime
    restoration_duration_seconds: Optional[int] = None

class ValidationResult(BaseModel):
    """ Result of pre/post validation. """    
    passed: bool
    message: Optional[str] = None
    checks: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class RemediationHistoryItem(BaseModel):
    """ Single remediation attempt in history. """    
    attempt_number: int
    action_type: RemediationActionType
    executed_at: datetime
    duration_seconds: Optional[int] = None
    success: bool
    outcome: Outcome
    message: Optional[str] = None
    executed_by: Optional[str] = None

class RemediationHistoryResponse(BaseModel):
    """ Remediation history for an incident. """    
    incident_id: str
    total_attempts: int
    successful_attempts: int
    failed_attempts: int
    history: list[RemediationHistoryItem]
