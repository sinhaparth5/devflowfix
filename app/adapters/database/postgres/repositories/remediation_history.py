# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Repository for remediation history CRUD operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from app.adapters.database.postgres.models import RemediationHistoryTable


class RemediationHistoryRepository:
    """Repository for managing remediation history database operations."""
    
    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def create(
        self,
        history_id: str,
        incident_id: str,
        attempt_number: int,
        action_type: str,
        executed_at: datetime,
        success: bool,
        outcome: str,
        duration_seconds: Optional[int] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None,
        executed_by: Optional[str] = None,
        environment: str = "dev",
        dry_run: bool = False,
        actions_performed: Optional[List[str]] = None,
        pre_validation_passed: bool = True,
        post_validation_passed: bool = True,
        validation_details: Optional[Dict[str, Any]] = None,
        rollback_required: bool = False,
        rollback_performed: bool = False,
        rollback_snapshot_id: Optional[str] = None,
        execution_logs: Optional[List[str]] = None,
        remediation_metadata: Optional[Dict[str, Any]] = None,
    ) -> RemediationHistoryTable:
        """
        Create a new remediation history entry in the database.
        
        Args:
            history_id: Unique identifier for the history entry
            incident_id: ID of the related incident
            attempt_number: Attempt number (1, 2, 3, etc.)
            action_type: Type of remediation action performed
            executed_at: When the remediation was executed
            success: Whether the remediation succeeded
            outcome: Outcome of the remediation
            duration_seconds: Duration in seconds
            message: Success message
            error_message: Error message if failed
            executed_by: Who executed it (system or username)
            environment: Environment (dev, staging, prod)
            dry_run: Whether this was a dry run
            actions_performed: List of actions performed
            pre_validation_passed: Whether pre-validation passed
            post_validation_passed: Whether post-validation passed
            validation_details: Validation details
            rollback_required: Whether rollback was required
            rollback_performed: Whether rollback was performed
            rollback_snapshot_id: ID of the rollback snapshot
            execution_logs: List of execution logs
            remediation_metadata: Additional metadata
            
        Returns:
            Created RemediationHistoryTable object
        """
        history = RemediationHistoryTable(
            history_id=history_id,
            incident_id=incident_id,
            attempt_number=attempt_number,
            action_type=action_type,
            executed_at=executed_at,
            duration_seconds=duration_seconds,
            success=success,
            outcome=outcome,
            message=message,
            error_message=error_message,
            executed_by=executed_by,
            environment=environment,
            dry_run=dry_run,
            actions_performed=actions_performed,
            pre_validation_passed=pre_validation_passed,
            post_validation_passed=post_validation_passed,
            validation_details=validation_details,
            rollback_required=rollback_required,
            rollback_performed=rollback_performed,
            rollback_snapshot_id=rollback_snapshot_id,
            execution_logs=execution_logs,
            remediation_metadata=remediation_metadata,
        )
        
        self.session.add(history)
        self.session.commit()
        self.session.refresh(history)
        
        return history
    
    def get_by_id(self, history_id: str) -> Optional[RemediationHistoryTable]:
        """
        Retrieve a remediation history entry by its ID.
        
        Args:
            history_id: The unique identifier of the history entry
            
        Returns:
            RemediationHistoryTable object if found, None otherwise
        """
        stmt = select(RemediationHistoryTable).where(RemediationHistoryTable.history_id == history_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_incident_id(
        self, 
        incident_id: str,
        order_by_attempt: bool = True,
    ) -> List[RemediationHistoryTable]:
        """
        Retrieve all remediation history entries for a specific incident.
        
        Args:
            incident_id: The unique identifier of the incident
            order_by_attempt: Whether to order by attempt number (default: True)
            
        Returns:
            List of RemediationHistoryTable objects
        """
        stmt = select(RemediationHistoryTable).where(RemediationHistoryTable.incident_id == incident_id)
        
        if order_by_attempt:
            stmt = stmt.order_by(RemediationHistoryTable.attempt_number.asc())
        else:
            stmt = stmt.order_by(RemediationHistoryTable.executed_at.desc())
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_latest_attempt(self, incident_id: str) -> Optional[RemediationHistoryTable]:
        """
        Get the latest remediation attempt for an incident.
        
        Args:
            incident_id: The unique identifier of the incident
            
        Returns:
            Latest RemediationHistoryTable object if found, None otherwise
        """
        stmt = (
            select(RemediationHistoryTable)
            .where(RemediationHistoryTable.incident_id == incident_id)
            .order_by(RemediationHistoryTable.attempt_number.desc())
            .limit(1)
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def list_history(
        self,
        success: Optional[bool] = None,
        environment: Optional[str] = None,
        action_type: Optional[str] = None,
        dry_run: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RemediationHistoryTable]:
        """
        List remediation history entries with optional filtering.
        
        Args:
            success: Filter by success flag
            environment: Filter by environment
            action_type: Filter by action type
            dry_run: Filter by dry_run flag
            limit: Maximum number of results to return (default: 100)
            offset: Number of results to skip (default: 0)
            
        Returns:
            List of RemediationHistoryTable objects
        """
        stmt = select(RemediationHistoryTable)
        
        # Apply filters
        conditions = []
        if success is not None:
            conditions.append(RemediationHistoryTable.success == success)
        if environment:
            conditions.append(RemediationHistoryTable.environment == environment)
        if action_type:
            conditions.append(RemediationHistoryTable.action_type == action_type)
        if dry_run is not None:
            conditions.append(RemediationHistoryTable.dry_run == dry_run)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Order by executed_at descending (newest first)
        stmt = stmt.order_by(RemediationHistoryTable.executed_at.desc())
        
        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def update(
        self,
        history_id: str,
        success: Optional[bool] = None,
        outcome: Optional[str] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        rollback_performed: Optional[bool] = None,
        execution_logs: Optional[List[str]] = None,
    ) -> Optional[RemediationHistoryTable]:
        """
        Update an existing remediation history entry.
        
        Args:
            history_id: The unique identifier of the history entry to update
            success: New success flag
            outcome: New outcome
            message: New message
            error_message: New error message
            duration_seconds: New duration
            rollback_performed: New rollback_performed flag
            execution_logs: New execution logs
            
        Returns:
            Updated RemediationHistoryTable object if found, None otherwise
        """
        history = self.get_by_id(history_id)
        if not history:
            return None
        
        # Update fields if provided
        if success is not None:
            history.success = success
        if outcome is not None:
            history.outcome = outcome
        if message is not None:
            history.message = message
        if error_message is not None:
            history.error_message = error_message
        if duration_seconds is not None:
            history.duration_seconds = duration_seconds
        if rollback_performed is not None:
            history.rollback_performed = rollback_performed
        if execution_logs is not None:
            history.execution_logs = execution_logs
        
        self.session.commit()
        self.session.refresh(history)
        
        return history
    
    def delete(self, history_id: str) -> bool:
        """
        Delete a remediation history entry by ID.
        
        Args:
            history_id: The unique identifier of the history entry to delete
            
        Returns:
            True if deleted, False if not found
        """
        history = self.get_by_id(history_id)
        if not history:
            return False
        
        self.session.delete(history)
        self.session.commit()
        
        return True
    
    def count_successful_remediations(
        self, 
        incident_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> int:
        """
        Count successful remediation attempts.
        
        Args:
            incident_id: Optional incident ID to filter by
            environment: Optional environment to filter by
            
        Returns:
            Count of successful remediation attempts
        """
        stmt = select(func.count()).select_from(RemediationHistoryTable).where(
            RemediationHistoryTable.success == True
        )
        
        if incident_id:
            stmt = stmt.where(RemediationHistoryTable.incident_id == incident_id)
        if environment:
            stmt = stmt.where(RemediationHistoryTable.environment == environment)
        
        result = self.session.execute(stmt)
        return result.scalar_one()
    
    def count_failed_remediations(
        self, 
        incident_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> int:
        """
        Count failed remediation attempts.
        
        Args:
            incident_id: Optional incident ID to filter by
            environment: Optional environment to filter by
            
        Returns:
            Count of failed remediation attempts
        """
        stmt = select(func.count()).select_from(RemediationHistoryTable).where(
            RemediationHistoryTable.success == False
        )
        
        if incident_id:
            stmt = stmt.where(RemediationHistoryTable.incident_id == incident_id)
        if environment:
            stmt = stmt.where(RemediationHistoryTable.environment == environment)
        
        result = self.session.execute(stmt)
        return result.scalar_one()
    
    def get_average_duration(
        self,
        action_type: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Optional[float]:
        """
        Get average remediation duration.
        
        Args:
            action_type: Optional action type to filter by
            environment: Optional environment to filter by
            
        Returns:
            Average duration in seconds or None if no data
        """
        stmt = select(func.avg(RemediationHistoryTable.duration_seconds)).where(
            RemediationHistoryTable.duration_seconds != None
        )
        
        if action_type:
            stmt = stmt.where(RemediationHistoryTable.action_type == action_type)
        if environment:
            stmt = stmt.where(RemediationHistoryTable.environment == environment)
        
        result = self.session.execute(stmt)
        avg = result.scalar_one()
        return float(avg) if avg is not None else None
    
    def get_recent_history(self, days: int = 7, limit: int = 100) -> List[RemediationHistoryTable]:
        """
        Get recent remediation history from the last N days.
        
        Args:
            days: Number of days to look back (default: 7)
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of recent RemediationHistoryTable objects
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = (
            select(RemediationHistoryTable)
            .where(RemediationHistoryTable.executed_at >= cutoff_date)
            .order_by(RemediationHistoryTable.executed_at.desc())
            .limit(limit)
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_rollback_history(self, limit: int = 100) -> List[RemediationHistoryTable]:
        """
        Get all remediation attempts that required rollback.
        
        Args:
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of RemediationHistoryTable objects that required rollback
        """
        stmt = (
            select(RemediationHistoryTable)
            .where(RemediationHistoryTable.rollback_required == True)
            .order_by(RemediationHistoryTable.executed_at.desc())
            .limit(limit)
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_success_rate_by_action_type(self) -> Dict[str, float]:
        """
        Calculate success rate for each action type.
        
        Returns:
            Dictionary mapping action type to success rate (0.0-1.0)
        """
        # Get all distinct action types
        action_types_stmt = select(RemediationHistoryTable.action_type).distinct()
        action_types_result = self.session.execute(action_types_stmt)
        action_types = [row[0] for row in action_types_result.all()]
        
        success_rates = {}
        for action_type in action_types:
            total_stmt = select(func.count()).select_from(RemediationHistoryTable).where(
                RemediationHistoryTable.action_type == action_type
            )
            total = self.session.execute(total_stmt).scalar_one()
            
            success_stmt = select(func.count()).select_from(RemediationHistoryTable).where(
                and_(
                    RemediationHistoryTable.action_type == action_type,
                    RemediationHistoryTable.success == True
                )
            )
            success = self.session.execute(success_stmt).scalar_one()
            
            success_rates[action_type] = success / total if total > 0 else 0.0
        
        return success_rates
