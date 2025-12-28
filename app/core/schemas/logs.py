# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ApplicationLogResponse(BaseModel):
    """Schema for application log in API responses."""
    log_id: str
    incident_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    level: str
    category: str
    message: str
    stage: Optional[str] = None
    details: dict = Field(default_factory=dict)
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    llm_response_time_ms: Optional[int] = None
    created_at: datetime
    duration_ms: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ApplicationLogListResponse(BaseModel):
    """Paginated list of application logs."""
    logs: list[ApplicationLogResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class ApplicationLogCreate(BaseModel):
    """Schema for creating an application log."""
    incident_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    level: str = Field(..., description="Log level: debug, info, warning, error, critical")
    category: str = Field(..., description="Log category: webhook, llm, analysis, remediation, github, database, system")
    message: str = Field(..., description="Log message")
    stage: Optional[str] = Field(None, description="Workflow stage")
    details: dict = Field(default_factory=dict, description="Additional details")
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    llm_response_time_ms: Optional[int] = None
    duration_ms: Optional[int] = None


class LogFilterRequest(BaseModel):
    """Schema for filtering logs."""
    incident_id: Optional[str] = None
    user_id: Optional[str] = None
    level: Optional[str] = None
    category: Optional[str] = None
    stage: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
