# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Repository for incident CRUD operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_, or_, func

from app.adapters.database.postgres.models import IncidentTable


class IncidentRepository:
    """Repository for managing incident database operations."""
    
    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def create(
        self,
        incident_id: str,
        timestamp: datetime,
        source: str,
        severity: str,
        error_log: str,
        failure_type: Optional[str] = None,
        error_message: Optional[str] = None,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        root_cause: Optional[str] = None,
        fixability: Optional[str] = None,
        confidence: Optional[float] = None,
        embedding: Optional[list] = None,
        similar_incidents: Optional[list] = None,
        remediation_plan: Optional[Dict[str, Any]] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> IncidentTable:
        """
        Create a new incident in the database.
        
        Args:
            incident_id: Unique identifier for the incident
            timestamp: When the incident occurred
            source: Source of the incident (e.g., 'github', 'jenkins', 'kubernetes')
            severity: Severity level (e.g., 'critical', 'high', 'medium', 'low')
            error_log: The error log text
            failure_type: Type of failure (optional)
            error_message: Extracted error message (optional)
            stack_trace: Stack trace if available (optional)
            context: Additional context as JSON (optional)
            root_cause: Identified root cause (optional)
            fixability: Fixability assessment (optional)
            confidence: Confidence score (optional)
            embedding: Vector embedding for RAG (optional)
            similar_incidents: List of similar incidents (optional)
            remediation_plan: Remediation plan details (optional)
            raw_payload: Raw event payload (optional)
            tags: List of tags (optional)
            
        Returns:
            Created IncidentTable object
        """
        incident = IncidentTable(
            incident_id=incident_id,
            timestamp=timestamp,
            source=source,
            severity=severity,
            error_log=error_log,
            failure_type=failure_type,
            error_message=error_message,
            stack_trace=stack_trace,
            context=context or {},
            root_cause=root_cause,
            fixability=fixability,
            confidence=confidence,
            embedding=embedding,
            similar_incidents=similar_incidents,
            remediation_plan=remediation_plan,
            raw_payload=raw_payload or {},
            tags=tags or [],
        )
        
        self.session.add(incident)
        self.session.commit()
        self.session.refresh(incident)
        
        return incident
    
    def get_by_id(self, incident_id: str) -> Optional[IncidentTable]:
        """
        Retrieve an incident by its ID.
        
        Args:
            incident_id: The unique identifier of the incident
            
        Returns:
            IncidentTable object if found, None otherwise
        """
        stmt = select(IncidentTable).where(IncidentTable.incident_id == incident_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def list_incidents(
        self,
        outcome: Optional[str] = None,
        severity: Optional[str] = None,
        source: Optional[str] = None,
        failure_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[IncidentTable]:
        """
        List incidents with optional filtering.
        
        Args:
            outcome: Filter by outcome (e.g., 'success', 'failed', 'pending')
            severity: Filter by severity level
            source: Filter by source
            failure_type: Filter by failure type
            limit: Maximum number of results to return (default: 100)
            offset: Number of results to skip (default: 0)
            
        Returns:
            List of IncidentTable objects
        """
        stmt = select(IncidentTable)
        
        # Apply filters
        conditions = []
        if outcome:
            conditions.append(IncidentTable.outcome == outcome)
        if severity:
            conditions.append(IncidentTable.severity == severity)
        if source:
            conditions.append(IncidentTable.source == source)
        if failure_type:
            conditions.append(IncidentTable.failure_type == failure_type)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Order by created_at descending (newest first)
        stmt = stmt.order_by(IncidentTable.created_at.desc())
        
        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def update(
        self,
        incident_id: str,
        failure_type: Optional[str] = None,
        error_message: Optional[str] = None,
        severity: Optional[str] = None,
        root_cause: Optional[str] = None,
        fixability: Optional[str] = None,
        confidence: Optional[float] = None,
        embedding: Optional[list] = None,
        similar_incidents: Optional[list] = None,
        remediation_plan: Optional[Dict[str, Any]] = None,
        remediation_executed: Optional[bool] = None,
        remediation_start_time: Optional[datetime] = None,
        remediation_end_time: Optional[datetime] = None,
        outcome: Optional[str] = None,
        outcome_message: Optional[str] = None,
        resolution_time_seconds: Optional[int] = None,
        resolved_at: Optional[datetime] = None,
        human_feedback: Optional[Dict[str, Any]] = None,
        approved_by: Optional[str] = None,
        approval_timestamp: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[IncidentTable]:
        """
        Update an existing incident.
        
        Args:
            incident_id: The unique identifier of the incident to update
            failure_type: New failure type
            error_message: New error message
            severity: New severity level
            root_cause: Identified root cause
            fixability: Fixability assessment
            confidence: Confidence score
            embedding: Vector embedding
            similar_incidents: List of similar incidents
            remediation_plan: Remediation plan details
            remediation_executed: Whether remediation was executed
            remediation_start_time: When remediation started
            remediation_end_time: When remediation ended
            outcome: Final outcome
            outcome_message: Outcome message
            resolution_time_seconds: Time to resolve
            resolved_at: When incident was resolved
            human_feedback: Human feedback data
            approved_by: Who approved the remediation
            approval_timestamp: When it was approved
            tags: List of tags
            
        Returns:
            Updated IncidentTable object if found, None otherwise
        """
        # First, get the incident
        incident = self.get_by_id(incident_id)
        if not incident:
            return None
        
        # Update fields if provided
        if failure_type is not None:
            incident.failure_type = failure_type
        if error_message is not None:
            incident.error_message = error_message
        if severity is not None:
            incident.severity = severity
        if root_cause is not None:
            incident.root_cause = root_cause
        if fixability is not None:
            incident.fixability = fixability
        if confidence is not None:
            incident.confidence = confidence
        if embedding is not None:
            incident.embedding = embedding
        if similar_incidents is not None:
            incident.similar_incidents = similar_incidents
        if remediation_plan is not None:
            incident.remediation_plan = remediation_plan
        if remediation_executed is not None:
            incident.remediation_executed = remediation_executed
        if remediation_start_time is not None:
            incident.remediation_start_time = remediation_start_time
        if remediation_end_time is not None:
            incident.remediation_end_time = remediation_end_time
        if outcome is not None:
            incident.outcome = outcome
        if outcome_message is not None:
            incident.outcome_message = outcome_message
        if resolution_time_seconds is not None:
            incident.resolution_time_seconds = resolution_time_seconds
        if resolved_at is not None:
            incident.resolved_at = resolved_at
        if human_feedback is not None:
            incident.human_feedback = human_feedback
        if approved_by is not None:
            incident.approved_by = approved_by
        if approval_timestamp is not None:
            incident.approval_timestamp = approval_timestamp
        if tags is not None:
            incident.tags = tags
        
        # Update the updated_at timestamp
        incident.updated_at = datetime.utcnow()
        
        self.session.commit()
        self.session.refresh(incident)
        
        return incident
    
    def delete(self, incident_id: str) -> bool:
        """
        Delete an incident by ID.
        
        Args:
            incident_id: The unique identifier of the incident to delete
            
        Returns:
            True if deleted, False if not found
        """
        incident = self.get_by_id(incident_id)
        if not incident:
            return False
        
        self.session.delete(incident)
        self.session.commit()
        
        return True
    
    def count_by_outcome(self, outcome: str) -> int:
        """
        Count incidents by outcome.
        
        Args:
            outcome: Outcome to filter by
            
        Returns:
            Count of incidents with the given outcome
        """
        stmt = select(func.count()).select_from(IncidentTable).where(IncidentTable.outcome == outcome)
        result = self.session.execute(stmt)
        return result.scalar_one()
    
    def get_recent_incidents(self, days: int = 7, limit: int = 50) -> List[IncidentTable]:
        """
        Get recent incidents from the last N days.
        
        Args:
            days: Number of days to look back (default: 7)
            limit: Maximum number of results (default: 50)
            
        Returns:
            List of recent IncidentTable objects
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = (
            select(IncidentTable)
            .where(IncidentTable.created_at >= cutoff_date)
            .order_by(IncidentTable.created_at.desc())
            .limit(limit)
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_unresolved_incidents(self, limit: int = 100) -> List[IncidentTable]:
        """
        Get all unresolved incidents (outcome is null or pending).
        
        Args:
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of unresolved IncidentTable objects
        """
        stmt = (
            select(IncidentTable)
            .where(or_(IncidentTable.outcome == None, IncidentTable.outcome == 'pending'))
            .order_by(IncidentTable.created_at.desc())
            .limit(limit)
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def search_by_similarity(
        self,
        embedding: list,
        limit: int = 10,
        min_confidence: Optional[float] = None,
    ) -> List[IncidentTable]:
        """
        Search for similar incidents using vector similarity.
        
        Args:
            embedding: Query embedding vector
            limit: Maximum number of results (default: 10)
            min_confidence: Minimum confidence threshold (optional)
            
        Returns:
            List of similar IncidentTable objects
        """
        stmt = select(IncidentTable).where(IncidentTable.embedding != None)
        
        if min_confidence is not None:
            stmt = stmt.where(IncidentTable.confidence >= min_confidence)
        
        # Order by vector similarity (cosine distance)
        # Note: This requires pgvector extension
        stmt = stmt.order_by(IncidentTable.embedding.cosine_distance(embedding))
        stmt = stmt.limit(limit)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_incidents_by_tags(self, tags: List[str], limit: int = 100) -> List[IncidentTable]:
        """
        Get incidents that have any of the specified tags.
        
        Args:
            tags: List of tags to search for
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of IncidentTable objects with matching tags
        """
        # JSON contains operator for PostgreSQL
        stmt = select(IncidentTable)
        
        # Check if any of the provided tags exist in the tags array
        conditions = [IncidentTable.tags.contains([tag]) for tag in tags]
        stmt = stmt.where(or_(*conditions))
        
        stmt = stmt.order_by(IncidentTable.created_at.desc()).limit(limit)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
