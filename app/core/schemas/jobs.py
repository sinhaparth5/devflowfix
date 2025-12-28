# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Background job tracking schemas.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Background job status."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Types of background jobs."""
    INCIDENT_ANALYSIS = "incident_analysis"
    INCIDENT_REANALYSIS = "incident_reanalysis"
    EXPORT_CSV = "export_csv"
    EXPORT_PDF = "export_pdf"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
    PR_CREATION = "pr_creation"


class JobCreate(BaseModel):
    """Schema for creating a background job."""
    job_type: JobType = Field(..., description="Type of job")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Job parameters"
    )


class JobResponse(BaseModel):
    """Schema for background job response."""

    job_id: str = Field(..., description="Unique job identifier")
    job_type: JobType = Field(..., description="Type of job")
    status: JobStatus = Field(..., description="Current job status")

    # Progress tracking
    progress: int = Field(0, ge=0, le=100, description="Progress percentage")
    current_step: Optional[str] = Field(None, description="Current step description")

    # Timing
    created_at: datetime = Field(..., description="When job was created")
    started_at: Optional[datetime] = Field(None, description="When job started processing")
    completed_at: Optional[datetime] = Field(None, description="When job completed")
    estimated_completion: Optional[datetime] = Field(
        None,
        description="Estimated completion time"
    )

    # Results
    result: Optional[Dict[str, Any]] = Field(None, description="Job result data")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    # Metadata
    user_id: str = Field(..., description="User who created the job")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job parameters")

    # URLs
    status_url: str = Field(..., description="URL to check job status")
    result_url: Optional[str] = Field(None, description="URL to download result")


class JobProgressUpdate(BaseModel):
    """Schema for updating job progress."""
    progress: int = Field(..., ge=0, le=100, description="Progress percentage")
    current_step: Optional[str] = Field(None, description="Current step description")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion")


class JobListResponse(BaseModel):
    """Schema for listing jobs."""
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int
