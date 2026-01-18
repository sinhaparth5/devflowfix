# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, func
import structlog

from app.adapters.database.postgres.models import UserTable, AuditLogTable
from app.exceptions import DatabaseError

logger = structlog.get_logger()


class UserRepository:
    """Repository for user database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, user: UserTable) -> UserTable:
        """Create a new user."""
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            logger.info("user_created", user_id=user.user_id, email=user.email)
            return user
        except Exception as e:
            self.db.rollback()
            logger.error("user_creation_failed", error=str(e))
            raise DatabaseError("create", str(e))

    def get_by_id(self, user_id: str) -> Optional[UserTable]:
        """Get user by ID."""
        return self.db.query(UserTable).filter(UserTable.user_id == user_id).first()

    def get_by_email(self, email: str) -> Optional[UserTable]:
        """Get user by email."""
        return self.db.query(UserTable).filter(
            func.lower(UserTable.email) == email.lower()
        ).first()

    def get_active_by_email(self, email: str) -> Optional[UserTable]:
        """Get active user by email."""
        return self.db.query(UserTable).filter(
            and_(
                func.lower(UserTable.email) == email.lower(),
                UserTable.is_active == True
            )
        ).first()

    def get_by_oauth(self, provider: str, oauth_id: str) -> Optional[UserTable]:
        """Get user by OAuth provider and ID."""
        return self.db.query(UserTable).filter(
            and_(
                UserTable.oauth_provider == provider,
                UserTable.oauth_id == oauth_id
            )
        ).first()

    def update(self, user: UserTable) -> UserTable:
        """Update an existing user."""
        try:
            user.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(user)
            return user
        except Exception as e:
            self.db.rollback()
            logger.error("user_update_failed", user_id=user.user_id, error=str(e))
            raise DatabaseError("update", str(e))

    def delete(self, user_id: str) -> bool:
        """Delete a user (soft delete by deactivating)."""
        user = self.get_by_id(user_id)
        if user:
            user.is_active = False
            user.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            return True
        return False

    def hard_delete(self, user_id: str) -> bool:
        """Permanently delete a user."""
        user = self.get_by_id(user_id)
        if user:
            self.db.delete(user)
            self.db.commit()
            return True
        return False

    def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: Optional[str] = None,
        team_id: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[list[UserTable], int]:
        """List users with filters."""
        query = self.db.query(UserTable)

        if organization_id:
            query = query.filter(UserTable.organization_id == organization_id)
        if team_id:
            query = query.filter(UserTable.team_id == team_id)
        if role:
            query = query.filter(UserTable.role == role)
        if is_active is not None:
            query = query.filter(UserTable.is_active == is_active)

        total = query.count()
        users = query.order_by(UserTable.created_at.desc()).offset(skip).limit(limit).all()

        return users, total

    def update_last_login(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Update last login information."""
        user = self.get_by_id(user_id)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            user.last_login_ip = ip_address
            user.last_login_user_agent = user_agent
            user.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def set_api_key(self, user_id: str, key_hash: str, key_prefix: str) -> None:
        """Set API key hash and prefix."""
        user = self.get_by_id(user_id)
        if user:
            user.api_key_hash = key_hash
            user.api_key_prefix = key_prefix
            user.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def verify_email(self, user_id: str) -> None:
        """Mark user email as verified."""
        user = self.get_by_id(user_id)
        if user:
            user.is_verified = True
            user.updated_at = datetime.now(timezone.utc)
            self.db.commit()


# Note: SessionRepository removed - Zitadel handles session management


class AuditLogRepository:
    """Repository for audit log database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, log: AuditLogTable) -> AuditLogTable:
        """Create a new audit log entry."""
        try:
            self.db.add(log)
            self.db.commit()
            self.db.refresh(log)
            return log
        except Exception as e:
            self.db.rollback()
            logger.error("audit_log_creation_failed", error=str(e))
            raise DatabaseError("create", str(e))

    def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[AuditLogTable], int]:
        """Get audit logs for a user."""
        query = self.db.query(AuditLogTable).filter(AuditLogTable.user_id == user_id)

        if action:
            query = query.filter(AuditLogTable.action == action)
        if start_date:
            query = query.filter(AuditLogTable.created_at >= start_date)
        if end_date:
            query = query.filter(AuditLogTable.created_at <= end_date)

        total = query.count()
        logs = query.order_by(AuditLogTable.created_at.desc()).offset(skip).limit(limit).all()

        return logs, total

    def get_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLogTable], int]:
        """Get audit logs for a resource."""
        query = self.db.query(AuditLogTable).filter(
            and_(
                AuditLogTable.resource_type == resource_type,
                AuditLogTable.resource_id == resource_id
            )
        )

        total = query.count()
        logs = query.order_by(AuditLogTable.created_at.desc()).offset(skip).limit(limit).all()

        return logs, total

    def get_failed_logins(
        self,
        ip_address: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditLogTable]:
        """Get failed login attempts."""
        query = self.db.query(AuditLogTable).filter(
            and_(
                AuditLogTable.action == "login",
                AuditLogTable.success == False
            )
        )

        if ip_address:
            query = query.filter(AuditLogTable.ip_address == ip_address)
        if since:
            query = query.filter(AuditLogTable.created_at >= since)

        return query.order_by(AuditLogTable.created_at.desc()).limit(limit).all()

    def count_failed_logins(
        self,
        ip_address: str,
        since: datetime,
    ) -> int:
        """Count failed login attempts from an IP."""
        return self.db.query(AuditLogTable).filter(
            and_(
                AuditLogTable.action == "login",
                AuditLogTable.success == False,
                AuditLogTable.ip_address == ip_address,
                AuditLogTable.created_at >= since
            )
        ).count()
