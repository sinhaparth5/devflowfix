# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import ApprovalStatus, RemediationActionType

class ApprovalRequest(BaseModel):
    """ Reqiest to approve or reject a remediation """
    incident_id: str = Field(..., description="Incident ID")
    approval: bool = Field(..., description="True to approve, False to reject")
    approver: str = Field(..., description="Username or email of approver")
    comment: Optional[str] = Field(None, description="Optional comment")
    execute_immediately: bool = Field(True, description="Execute immediately after approval")

class ApprovalResponse(BaseModel):
    """ Response from approval action. """
    incident_id: str
    approval_status: ApprovalStatus
    approver: str
    approved_at: datetime
    comment: Optional[str] = None

    # If executed
    executed: bool = False
    execution_result: Optional[dict] = None

    message: str

class PendingApproval(BaseModel):
    """ Pending approval details """
    incident_id: str
    requested_at: datetime
    timeout_at: datetime
    time_remaining_seconds: int

    # Incident details
    severity: str
    source: str
    failure_type: Optional[str] = None
    root_cause: Optional[str] = None
    confidence: float

    # Remediation plan
    action_type: RemediationActionType
    risk_level: str
    estimated_duration_seconds: int

    # Context
    repository: Optional[str] = None
    service: Optional[str] = None
    namespace: Optional[str] = None

class PendingApprovalsList(BaseModel):
    """ List of pending approvals. """
    approvals: list[PendingApproval]
    total: int

class ApprovalDecision(BaseModel):
    """ Approval decision with reason. """
    incident_id: str
    approved: bool
    approver: str
    reason: str
    decided_at: datetime

class BulkApprovalRequest(BaseModel):
    """ Request to approve/reject mulitple incidents """
    incident_ids: list[str] = Field(..., min_length=1, max_length=50)
    approved: bool
    approver: str
    comment: Optional[str] = None

class BulkApprovalResponse(BaseModel):
    """ Response from bluk approval. """
    total_requested: int
    approved_count: int
    rejected_count: int
    failed_count: int
    results: list[dict] = Field(default_factory=list)