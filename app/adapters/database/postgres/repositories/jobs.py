# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""Repository for background job CRUD operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_

from app.adapters.database.postgres.models import BackgroundJobTable, JobStatus, JobType


class JobRepository:
    """Repository for managing background job database operations."""

    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def create(
        self,
        job_id: str,
        user_id: str,
        job_type: JobType,
        parameters: Optional[Dict[str, Any]] = None,
        job_metadata: Optional[Dict[str, Any]] = None,
    ) -> BackgroundJobTable:
        """
        Create a new background job entry.

        Args:
            job_id: Unique identifier for the job
            user_id: ID of the user who created the job
            job_type: Type of the job
            parameters: Job parameters
            job_metadata: Additional metadata

        Returns:
            Created BackgroundJobTable object
        """
        job = BackgroundJobTable(
            job_id=job_id,
            user_id=user_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            parameters=parameters or {},
            job_metadata=job_metadata or {},
            progress=0,
        )

        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

        return job

    def get_by_id(self, job_id: str, user_id: Optional[str] = None) -> Optional[BackgroundJobTable]:
        """
        Retrieve a job by its ID.

        Args:
            job_id: The unique identifier of the job
            user_id: Optional user ID for ownership verification

        Returns:
            BackgroundJobTable object if found, None otherwise
        """
        stmt = select(BackgroundJobTable).where(BackgroundJobTable.job_id == job_id)

        if user_id:
            stmt = stmt.where(BackgroundJobTable.user_id == user_id)

        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def list_jobs(
        self,
        user_id: str,
        job_type: Optional[JobType] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[BackgroundJobTable]:
        """
        List jobs for a user with optional filtering.

        Args:
            user_id: User ID to filter by (required for security)
            job_type: Optional filter by job type
            status: Optional filter by status
            limit: Maximum number of results (default: 50)
            offset: Number of results to skip (default: 0)

        Returns:
            List of BackgroundJobTable objects
        """
        stmt = select(BackgroundJobTable).where(BackgroundJobTable.user_id == user_id)

        if job_type:
            stmt = stmt.where(BackgroundJobTable.job_type == job_type)
        if status:
            stmt = stmt.where(BackgroundJobTable.status == status)

        stmt = stmt.order_by(BackgroundJobTable.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def count_jobs(
        self,
        user_id: str,
        job_type: Optional[JobType] = None,
        status: Optional[JobStatus] = None,
    ) -> int:
        """
        Count jobs for a user with optional filtering.

        Args:
            user_id: User ID to filter by
            job_type: Optional filter by job type
            status: Optional filter by status

        Returns:
            Count of jobs
        """
        stmt = select(func.count()).select_from(BackgroundJobTable).where(
            BackgroundJobTable.user_id == user_id
        )

        if job_type:
            stmt = stmt.where(BackgroundJobTable.job_type == job_type)
        if status:
            stmt = stmt.where(BackgroundJobTable.status == status)

        result = self.session.execute(stmt)
        return result.scalar_one()

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> Optional[BackgroundJobTable]:
        """
        Update job status.

        Args:
            job_id: The job ID to update
            status: New status
            error_message: Error message if status is FAILED

        Returns:
            Updated BackgroundJobTable object if found, None otherwise
        """
        job = self.get_by_id(job_id)
        if not job:
            return None

        job.status = status

        # Set timing based on status
        if status == JobStatus.PROCESSING and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            job.completed_at = datetime.now(timezone.utc)
            job.progress = 100 if status == JobStatus.COMPLETED else job.progress

        if error_message:
            job.error_message = error_message

        self.session.commit()
        self.session.refresh(job)

        return job

    def update_progress(
        self,
        job_id: str,
        progress: int,
        current_step: Optional[str] = None,
        estimated_completion: Optional[datetime] = None,
    ) -> Optional[BackgroundJobTable]:
        """
        Update job progress.

        Args:
            job_id: The job ID to update
            progress: Progress percentage (0-100)
            current_step: Current step description
            estimated_completion: Estimated completion time

        Returns:
            Updated BackgroundJobTable object if found, None otherwise
        """
        job = self.get_by_id(job_id)
        if not job:
            return None

        job.progress = max(0, min(100, progress))  # Clamp between 0-100

        if current_step is not None:
            job.current_step = current_step
        if estimated_completion is not None:
            job.estimated_completion = estimated_completion

        self.session.commit()
        self.session.refresh(job)

        return job

    def set_result(
        self,
        job_id: str,
        result: Dict[str, Any],
        result_file_path: Optional[str] = None,
        result_file_size: Optional[int] = None,
        result_file_type: Optional[str] = None,
    ) -> Optional[BackgroundJobTable]:
        """
        Set job result.

        Args:
            job_id: The job ID to update
            result: Result data
            result_file_path: Path to result file (for exports)
            result_file_size: Size of result file in bytes
            result_file_type: MIME type of result file

        Returns:
            Updated BackgroundJobTable object if found, None otherwise
        """
        job = self.get_by_id(job_id)
        if not job:
            return None

        job.result = result

        if result_file_path:
            job.result_file_path = result_file_path
        if result_file_size is not None:
            job.result_file_size = result_file_size
        if result_file_type:
            job.result_file_type = result_file_type

        self.session.commit()
        self.session.refresh(job)

        return job

    def delete(self, job_id: str, user_id: str) -> bool:
        """
        Delete a job by ID (with ownership check).

        Args:
            job_id: The unique identifier of the job to delete
            user_id: User ID for ownership verification

        Returns:
            True if deleted, False if not found
        """
        job = self.get_by_id(job_id, user_id=user_id)
        if not job:
            return False

        self.session.delete(job)
        self.session.commit()

        return True

    def cancel_job(self, job_id: str, user_id: str) -> Optional[BackgroundJobTable]:
        """
        Cancel a running job.

        Args:
            job_id: The job ID to cancel
            user_id: User ID for ownership verification

        Returns:
            Updated BackgroundJobTable object if found, None otherwise
        """
        job = self.get_by_id(job_id, user_id=user_id)
        if not job:
            return None

        # Only allow canceling queued or processing jobs
        if job.status not in (JobStatus.QUEUED, JobStatus.PROCESSING):
            return None

        return self.update_status(job_id, JobStatus.CANCELLED)

    def get_active_jobs(self, user_id: str) -> List[BackgroundJobTable]:
        """
        Get all active (queued or processing) jobs for a user.

        Args:
            user_id: User ID to filter by

        Returns:
            List of active BackgroundJobTable objects
        """
        stmt = (
            select(BackgroundJobTable)
            .where(
                BackgroundJobTable.user_id == user_id,
                or_(
                    BackgroundJobTable.status == JobStatus.QUEUED,
                    BackgroundJobTable.status == JobStatus.PROCESSING,
                )
            )
            .order_by(BackgroundJobTable.created_at.desc())
        )

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_recent_jobs(
        self,
        user_id: str,
        days: int = 7,
        limit: int = 50
    ) -> List[BackgroundJobTable]:
        """
        Get recent jobs from the last N days.

        Args:
            user_id: User ID to filter by
            days: Number of days to look back (default: 7)
            limit: Maximum number of results (default: 50)

        Returns:
            List of recent BackgroundJobTable objects
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(BackgroundJobTable)
            .where(
                BackgroundJobTable.user_id == user_id,
                BackgroundJobTable.created_at >= cutoff_date
            )
            .order_by(BackgroundJobTable.created_at.desc())
            .limit(limit)
        )

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_job_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        Get job statistics for a user.

        Args:
            user_id: User ID to filter by

        Returns:
            Dictionary with job statistics
        """
        total = self.count_jobs(user_id)

        # Count by status
        status_counts = {}
        for status in JobStatus:
            count = self.count_jobs(user_id, status=status)
            status_counts[status.value] = count

        # Count by type
        type_counts = {}
        for job_type in JobType:
            count = self.count_jobs(user_id, job_type=job_type)
            type_counts[job_type.value] = count

        # Calculate success rate
        completed = status_counts.get(JobStatus.COMPLETED.value, 0)
        failed = status_counts.get(JobStatus.FAILED.value, 0)
        finished_total = completed + failed
        success_rate = (completed / finished_total * 100) if finished_total > 0 else 0

        return {
            "total_jobs": total,
            "by_status": status_counts,
            "by_type": type_counts,
            "success_rate": success_rate,
            "active_jobs": len(self.get_active_jobs(user_id)),
        }

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Delete completed/failed jobs older than N days.

        Args:
            days: Number of days to keep jobs (default: 30)

        Returns:
            Number of jobs deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(BackgroundJobTable)
            .where(
                BackgroundJobTable.completed_at < cutoff_date,
                or_(
                    BackgroundJobTable.status == JobStatus.COMPLETED,
                    BackgroundJobTable.status == JobStatus.FAILED,
                    BackgroundJobTable.status == JobStatus.CANCELLED,
                )
            )
        )

        result = self.session.execute(stmt)
        jobs_to_delete = list(result.scalars().all())

        for job in jobs_to_delete:
            self.session.delete(job)

        self.session.commit()

        return len(jobs_to_delete)
