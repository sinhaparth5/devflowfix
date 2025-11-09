# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import (
    IncidentSource,
    Severity,
    Outcome, 
    Fixability,
    FailureType
)

class IncidentBase(BaseModel):
    """ Base incident schema with common fields. """
    source: IncidentSource = Field(..., description="Source platform")
    severity: Severity = Field(..., description="Incident severity")
    error_log: str = Field(..., description="Error log or message")
    failure_type: Optional[FailureType] = Field(None, description="Type of failure")
    context: dict = Field(default_factory=dict, description="Additional context")
    tags: list[str] = Field(default_factory=list, description="Tags")

class IncidentCreate(IncidentBase):
    """ Schema for creating a new incident """
    timestamp: Optional[datetime] = Field(None, description="Incident timestamp")
    error_message: Optional[str] = Field(None, description="Short error message")
    stack_trace: Optional[str] = Field(None, description="Stack trace if available")

class IncidentUpdate(BaseModel):
    """ Schema for updating an incident """
    severity: Optional[Severity] = None
    root_cause: Optional[str] = None
    fixability: Optional[Fixability] = None
    confidence: Optional[float] = None
    outcome: Optional[Outcome] = None
    outcome_message: Optional[str] = None
    tags: Optional[list[str]] = None

    model_config = ConfigDict(extra="forbid")

class IncidentResponse(IncidentBase):
    """ Schema for incident in API responses. """
    incident_id: str
    timestamp: datetime
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None

    # Analysis
    root_cause: Optional[str] = None
    fixability: Optional[Fixability] = None
    confidence: Optional[float] = None

    # Remediation
    remediation_executed: bool = False
    remediation_start_time: Optional[datetime] = None
    remediation_end_time: Optional[datetime] = None
    
    # Outcome
    outcome: Optional[Outcome] = None
    outcome_message: Optional[str] = None
    resolution_time_seconds: Optional[int] = None

    # Feedback
    approved_by: Optional[str] = None
    approval_timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class IncidentDetail(IncidentResponse):
    """ Detailed incident schema with all fields """
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    similar_incidents: list[dict] = Field(default_factory=list)
    remediation_plan: Optional[dict] = None
    human_feedback: Optional[dict] = None
    raw_payload: dict = Field(default_factory=dict)

class IncidentListResponse(BaseModel):
    """ Paginated list of incidents """
    incidents: list[IncidentResponse]
    total: int
    skip: int
    limit: int
    has_more: bool

class IncidentStats(BaseModel):
    """ Incident statistics """
    total_incidents: int
    resolved_incidents: int
    pending_incidents: int
    failed_incidents: int
    escalated_incidents: int
    success_rate: float
    average_resolution_time_seconds: Optional[float] = None
    incidents_by_source: dict[str, int] = Field(default_factory=dict)
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    incidents_by_failure_type: dict[str, int] = Field(default_factory=dict)

