# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Background Jobs Endpoints

REST API for managing background jobs like exports, bulk operations, and long-running tasks.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Depends, status as http_status, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import structlog
import uuid
import os

from app.dependencies import get_db
from app.auth import get_current_active_user
from app.adapters.database.postgres.repositories.jobs import JobRepository
from app.core.schemas.jobs import (
    JobCreate,
    JobResponse,
    JobProgressUpdate,
    JobListResponse,
    JobStatus,
    JobType,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.post(
    "",
    response_model=JobResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a background job",
    description="Create a new background job for long-running operations",
)
async def create_job(
    job_data: JobCreate,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> JobResponse:
    """
    Create a new background job.

    This endpoint creates a job that will be processed asynchronously.
    Use this for:
    - CSV/PDF exports
    - Bulk updates
    - Incident reanalysis
    - PR creation
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        # Generate job ID
        job_id = f"job_{uuid.uuid4().hex[:16]}"

        # Create job
        job = job_repo.create(
            job_id=job_id,
            user_id=user.user_id,
            job_type=job_data.job_type,
            parameters=job_data.parameters,
        )

        logger.info(
            "job_created",
            job_id=job_id,
            job_type=job_data.job_type.value,
            user_id=user.user_id,
        )

        # Build URLs
        base_url = str(request.base_url).rstrip("/")
        status_url = f"{base_url}/api/v1/jobs/{job_id}"
        result_url = None  # Will be set when job completes

        return JobResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            current_step=job.current_step,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            estimated_completion=job.estimated_completion,
            result=job.result,
            error_message=job.error_message,
            user_id=job.user_id,
            parameters=job.parameters,
            status_url=status_url,
            result_url=result_url,
        )

    except Exception as e:
        logger.error("job_creation_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create job: {str(e)}",
        )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status",
    description="Get the current status and progress of a background job",
)
async def get_job_status(
    job_id: str,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> JobResponse:
    """
    Get the status of a background job.

    Returns the current progress, status, and results (if completed).
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        # Get job with ownership check
        job = job_repo.get_by_id(job_id, user_id=user.user_id)

        if not job:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Job not found or access denied: {job_id}",
            )

        # Build URLs
        base_url = str(request.base_url).rstrip("/")
        status_url = f"{base_url}/api/v1/jobs/{job_id}"
        result_url = None

        if job.status == JobStatus.COMPLETED and job.result_file_path:
            result_url = f"{base_url}/api/v1/jobs/{job_id}/download"

        return JobResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            current_step=job.current_step,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            estimated_completion=job.estimated_completion,
            result=job.result,
            error_message=job.error_message,
            user_id=job.user_id,
            parameters=job.parameters,
            status_url=status_url,
            result_url=result_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("job_status_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )


@router.get(
    "",
    response_model=JobListResponse,
    summary="List background jobs",
    description="List all background jobs for the current user",
)
async def list_jobs(
    job_type: Optional[JobType] = Query(None, description="Filter by job type"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> JobListResponse:
    """
    List background jobs for the current user.

    Supports filtering by job type and status.
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        # Calculate offset
        skip = (page - 1) * page_size

        # Get jobs with filters
        jobs = job_repo.list_jobs(
            user_id=user.user_id,
            job_type=job_type,
            status=status,
            limit=page_size,
            offset=skip,
        )

        # Get total count
        total = job_repo.count_jobs(
            user_id=user.user_id,
            job_type=job_type,
            status=status,
        )

        # Convert to response models
        job_responses = []
        for job in jobs:
            job_responses.append(
                JobResponse(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status=job.status,
                    progress=job.progress,
                    current_step=job.current_step,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    estimated_completion=job.estimated_completion,
                    result=job.result,
                    error_message=job.error_message,
                    user_id=job.user_id,
                    parameters=job.parameters,
                    status_url=f"/api/v1/jobs/{job.job_id}",
                    result_url=f"/api/v1/jobs/{job.job_id}/download" if job.status == JobStatus.COMPLETED and job.result_file_path else None,
                )
            )

        logger.info(
            "jobs_listed",
            user_id=user.user_id,
            count=len(jobs),
            total=total,
        )

        return JobListResponse(
            jobs=job_responses,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error("jobs_list_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}",
        )


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a job",
    description="Cancel a queued or running background job",
)
async def cancel_job(
    job_id: str,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> JobResponse:
    """
    Cancel a background job.

    Only queued or processing jobs can be cancelled.
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        # Cancel job with ownership check
        job = job_repo.cancel_job(job_id, user_id=user.user_id)

        if not job:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Job not found, already completed, or cannot be cancelled: {job_id}",
            )

        logger.info("job_cancelled", job_id=job_id, user_id=user.user_id)

        # Build URLs
        base_url = str(request.base_url).rstrip("/")
        status_url = f"{base_url}/api/v1/jobs/{job_id}"

        return JobResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            current_step=job.current_step,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            estimated_completion=job.estimated_completion,
            result=job.result,
            error_message=job.error_message,
            user_id=job.user_id,
            parameters=job.parameters,
            status_url=status_url,
            result_url=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("job_cancel_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job: {str(e)}",
        )


@router.delete(
    "/{job_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a job",
    description="Delete a completed or failed background job",
)
async def delete_job(
    job_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Delete a background job.

    Only completed, failed, or cancelled jobs can be deleted.
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        # Delete job with ownership check
        success = job_repo.delete(job_id, user_id=user.user_id)

        if not success:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Job not found or access denied: {job_id}",
            )

        logger.info("job_deleted", job_id=job_id, user_id=user.user_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("job_delete_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job: {str(e)}",
        )


@router.get(
    "/stats/overview",
    summary="Get job statistics",
    description="Get statistics about background jobs for the current user",
)
async def get_job_statistics(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get statistics about background jobs.

    Returns counts by status, type, and success rate.
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        stats = job_repo.get_job_statistics(user_id=user.user_id)

        logger.info("job_statistics_retrieved", user_id=user.user_id)

        return {
            "success": True,
            "statistics": stats,
        }

    except Exception as e:
        logger.error("job_statistics_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve job statistics: {str(e)}",
        )


@router.get(
    "/active",
    summary="Get active jobs",
    description="Get all currently running or queued jobs",
)
async def get_active_jobs(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get all active (queued or processing) jobs for the current user.
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        jobs = job_repo.get_active_jobs(user_id=user.user_id)

        # Convert to response models
        job_responses = []
        for job in jobs:
            job_responses.append(
                JobResponse(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status=job.status,
                    progress=job.progress,
                    current_step=job.current_step,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    estimated_completion=job.estimated_completion,
                    result=job.result,
                    error_message=job.error_message,
                    user_id=job.user_id,
                    parameters=job.parameters,
                    status_url=f"/api/v1/jobs/{job.job_id}",
                    result_url=None,
                )
            )

        logger.info("active_jobs_retrieved", user_id=user.user_id, count=len(jobs))

        return {
            "success": True,
            "count": len(jobs),
            "jobs": job_responses,
        }

    except Exception as e:
        logger.error("active_jobs_error", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve active jobs: {str(e)}",
        )


@router.get(
    "/{job_id}/download",
    summary="Download job result file",
    description="Download the result file from a completed export job",
)
async def download_job_result(
    job_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Download the result file from a completed job.

    Only works for completed export jobs that have generated files.
    """
    try:
        user = current_user["user"]
        job_repo = JobRepository(db)

        # Get job with ownership check
        job = job_repo.get_by_id(job_id, user_id=user.user_id)

        if not job:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Job not found or access denied: {job_id}",
            )

        # Check if job is completed
        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Job is not completed. Current status: {job.status.value}",
            )

        # Check if job has a result file
        if not job.result_file_path or not os.path.exists(job.result_file_path):
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Result file not found for this job",
            )

        # Determine media type from file type
        media_type = job.result_file_type or "application/octet-stream"
        
        # Get filename from path
        filename = os.path.basename(job.result_file_path)

        logger.info(
            "job_result_downloaded",
            job_id=job_id,
            user_id=user.user_id,
            filename=filename,
        )

        return FileResponse(
            path=job.result_file_path,
            media_type=media_type,
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("job_download_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download job result: {str(e)}",
        )
