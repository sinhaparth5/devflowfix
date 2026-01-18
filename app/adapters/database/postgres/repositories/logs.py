# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import ApplicationLogTable
from app.exceptions import DatabaseError

logger = structlog.get_logger()


class ApplicationLogRepository:
    """Repository for application/workflow log database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, log: ApplicationLogTable) -> ApplicationLogTable:
        """Create a new application log entry."""
        try:
            self.db.add(log)
            self.db.commit()
            self.db.refresh(log)
            return log
        except Exception as e:
            self.db.rollback()
            logger.error("application_log_creation_failed", error=str(e))
            raise DatabaseError("create", str(e))

    def get_by_incident(
        self,
        incident_id: str,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
        category: Optional[str] = None,
    ) -> tuple[list[ApplicationLogTable], int]:
        """Get application logs for an incident."""
        query = self.db.query(ApplicationLogTable).filter(
            ApplicationLogTable.incident_id == incident_id
        )

        if level:
            query = query.filter(ApplicationLogTable.level == level)
        if category:
            query = query.filter(ApplicationLogTable.category == category)

        total = query.count()
        logs = query.order_by(ApplicationLogTable.created_at.asc()).offset(skip).limit(limit).all()

        return logs, total

    def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[ApplicationLogTable], int]:
        """Get application logs for a user."""
        query = self.db.query(ApplicationLogTable).filter(
            ApplicationLogTable.user_id == user_id
        )

        if level:
            query = query.filter(ApplicationLogTable.level == level)
        if category:
            query = query.filter(ApplicationLogTable.category == category)
        if start_date:
            query = query.filter(ApplicationLogTable.created_at >= start_date)
        if end_date:
            query = query.filter(ApplicationLogTable.created_at <= end_date)

        total = query.count()
        logs = query.order_by(ApplicationLogTable.created_at.desc()).offset(skip).limit(limit).all()

        return logs, total

    def get_recent(
        self,
        limit: int = 100,
        level: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[ApplicationLogTable]:
        """Get recent application logs."""
        query = self.db.query(ApplicationLogTable)

        if level:
            query = query.filter(ApplicationLogTable.level == level)
        if category:
            query = query.filter(ApplicationLogTable.category == category)

        return query.order_by(ApplicationLogTable.created_at.desc()).limit(limit).all()

    def get_by_stage(
        self,
        stage: str,
        incident_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ApplicationLogTable]:
        """Get logs by workflow stage."""
        query = self.db.query(ApplicationLogTable).filter(
            ApplicationLogTable.stage == stage
        )

        if incident_id:
            query = query.filter(ApplicationLogTable.incident_id == incident_id)

        return query.order_by(ApplicationLogTable.created_at.desc()).limit(limit).all()

    def delete_old_logs(self, days: int = 30) -> int:
        """Delete logs older than specified days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = self.db.query(ApplicationLogTable).filter(
            ApplicationLogTable.created_at < cutoff_date
        ).delete()
        self.db.commit()
        return deleted
