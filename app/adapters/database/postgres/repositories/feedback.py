# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Repository for feedback CRUD operations."""

from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.adapters.database.postgres.models import FeedbackTable


class FeedbackRepository:
    """Repository for managing feedback database operations."""
    
    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def create(
        self,
        feedback_id: str,
        incident_id: str,
        helpful: bool,
        comment: Optional[str] = None,
        user: Optional[str] = None,
        user_email: Optional[str] = None,
        rating: Optional[int] = None,
        categories: Optional[List[str]] = None,
    ) -> FeedbackTable:
        """
        Create a new feedback entry in the database.
        
        Args:
            feedback_id: Unique identifier for the feedback
            incident_id: ID of the related incident
            helpful: Whether the remediation was helpful
            comment: Optional comment from the user
            user: Username of the person providing feedback
            user_email: Email of the person providing feedback
            rating: Optional 1-5 star rating
            categories: Optional categories for the feedback
            
        Returns:
            Created FeedbackTable object
        """
        feedback = FeedbackTable(
            feedback_id=feedback_id,
            incident_id=incident_id,
            helpful=helpful,
            comment=comment,
            user=user,
            user_email=user_email,
            rating=rating,
            categories=categories,
        )
        
        self.session.add(feedback)
        self.session.commit()
        self.session.refresh(feedback)
        
        return feedback
    
    def get_by_id(self, feedback_id: str) -> Optional[FeedbackTable]:
        """
        Retrieve a feedback entry by its ID.
        
        Args:
            feedback_id: The unique identifier of the feedback
            
        Returns:
            FeedbackTable object if found, None otherwise
        """
        stmt = select(FeedbackTable).where(FeedbackTable.feedback_id == feedback_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_incident_id(self, incident_id: str) -> List[FeedbackTable]:
        """
        Retrieve all feedback entries for a specific incident.
        
        Args:
            incident_id: The unique identifier of the incident
            
        Returns:
            List of FeedbackTable objects
        """
        stmt = (
            select(FeedbackTable)
            .where(FeedbackTable.incident_id == incident_id)
            .order_by(FeedbackTable.created_at.desc())
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def list_feedback(
        self,
        helpful: Optional[bool] = None,
        min_rating: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FeedbackTable]:
        """
        List feedback entries with optional filtering.
        
        Args:
            helpful: Filter by helpful flag
            min_rating: Filter by minimum rating
            limit: Maximum number of results to return (default: 100)
            offset: Number of results to skip (default: 0)
            
        Returns:
            List of FeedbackTable objects
        """
        stmt = select(FeedbackTable)
        
        # Apply filters
        if helpful is not None:
            stmt = stmt.where(FeedbackTable.helpful == helpful)
        if min_rating is not None:
            stmt = stmt.where(FeedbackTable.rating >= min_rating)
        
        # Order by created_at descending (newest first)
        stmt = stmt.order_by(FeedbackTable.created_at.desc())
        
        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def update(
        self,
        feedback_id: str,
        helpful: Optional[bool] = None,
        comment: Optional[str] = None,
        rating: Optional[int] = None,
        categories: Optional[List[str]] = None,
    ) -> Optional[FeedbackTable]:
        """
        Update an existing feedback entry.
        
        Args:
            feedback_id: The unique identifier of the feedback to update
            helpful: New helpful flag
            comment: New comment
            rating: New rating
            categories: New categories
            
        Returns:
            Updated FeedbackTable object if found, None otherwise
        """
        feedback = self.get_by_id(feedback_id)
        if not feedback:
            return None
        
        # Update fields if provided
        if helpful is not None:
            feedback.helpful = helpful
        if comment is not None:
            feedback.comment = comment
        if rating is not None:
            feedback.rating = rating
        if categories is not None:
            feedback.categories = categories
        
        self.session.commit()
        self.session.refresh(feedback)
        
        return feedback
    
    def delete(self, feedback_id: str) -> bool:
        """
        Delete a feedback entry by ID.
        
        Args:
            feedback_id: The unique identifier of the feedback to delete
            
        Returns:
            True if deleted, False if not found
        """
        feedback = self.get_by_id(feedback_id)
        if not feedback:
            return False
        
        self.session.delete(feedback)
        self.session.commit()
        
        return True
    
    def count_helpful(self, incident_id: Optional[str] = None) -> int:
        """
        Count helpful feedback entries.
        
        Args:
            incident_id: Optional incident ID to filter by
            
        Returns:
            Count of helpful feedback entries
        """
        stmt = select(func.count()).select_from(FeedbackTable).where(FeedbackTable.helpful == True)
        
        if incident_id:
            stmt = stmt.where(FeedbackTable.incident_id == incident_id)
        
        result = self.session.execute(stmt)
        return result.scalar_one()
    
    def count_not_helpful(self, incident_id: Optional[str] = None) -> int:
        """
        Count not helpful feedback entries.
        
        Args:
            incident_id: Optional incident ID to filter by
            
        Returns:
            Count of not helpful feedback entries
        """
        stmt = select(func.count()).select_from(FeedbackTable).where(FeedbackTable.helpful == False)
        
        if incident_id:
            stmt = stmt.where(FeedbackTable.incident_id == incident_id)
        
        result = self.session.execute(stmt)
        return result.scalar_one()
    
    def get_average_rating(self, incident_id: Optional[str] = None) -> Optional[float]:
        """
        Get average rating across feedback entries.
        
        Args:
            incident_id: Optional incident ID to filter by
            
        Returns:
            Average rating or None if no ratings exist
        """
        stmt = select(func.avg(FeedbackTable.rating)).where(FeedbackTable.rating != None)
        
        if incident_id:
            stmt = stmt.where(FeedbackTable.incident_id == incident_id)
        
        result = self.session.execute(stmt)
        avg = result.scalar_one()
        return float(avg) if avg is not None else None
    
    def get_recent_feedback(self, days: int = 7, limit: int = 50) -> List[FeedbackTable]:
        """
        Get recent feedback from the last N days.
        
        Args:
            days: Number of days to look back (default: 7)
            limit: Maximum number of results (default: 50)
            
        Returns:
            List of recent FeedbackTable objects
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = (
            select(FeedbackTable)
            .where(FeedbackTable.created_at >= cutoff_date)
            .order_by(FeedbackTable.created_at.desc())
            .limit(limit)
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_feedback_by_user(self, user: str, limit: int = 100) -> List[FeedbackTable]:
        """
        Get all feedback entries from a specific user.
        
        Args:
            user: Username to filter by
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of FeedbackTable objects from the user
        """
        stmt = (
            select(FeedbackTable)
            .where(FeedbackTable.user == user)
            .order_by(FeedbackTable.created_at.desc())
            .limit(limit)
        )
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
