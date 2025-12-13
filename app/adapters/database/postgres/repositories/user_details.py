# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import UserDetailsTable
from app.exceptions import DatabaseError

logger = structlog.get_logger()


class UserDetailsRepository:
    """Repository for user details database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, user_details: UserDetailsTable) -> UserDetailsTable:
        """Create new user details."""
        try:
            self.db.add(user_details)
            self.db.commit()
            self.db.refresh(user_details)
            logger.info("user_details_created", user_id=user_details.user_id)
            return user_details
        except Exception as e:
            self.db.rollback()
            logger.error("user_details_creation_failed", error=str(e))
            raise DatabaseError("create", str(e))

    def get_by_user_id(self, user_id: str) -> Optional[UserDetailsTable]:
        """Get user details by user ID."""
        return self.db.query(UserDetailsTable).filter(
            UserDetailsTable.user_id == user_id
        ).first()

    def update(self, user_details: UserDetailsTable) -> UserDetailsTable:
        """Update existing user details."""
        try:
            user_details.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(user_details)
            return user_details
        except Exception as e:
            self.db.rollback()
            logger.error("user_details_update_failed", user_id=user_details.user_id, error=str(e))
            raise DatabaseError("update", str(e))

    def delete(self, user_id: str) -> bool:
        """Delete user details."""
        user_details = self.get_by_user_id(user_id)
        if user_details:
            self.db.delete(user_details)
            self.db.commit()
            return True
        return False

    def upsert(
        self,
        user_id: str,
        country: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        facebook_link: Optional[str] = None,
        twitter_link: Optional[str] = None,
        linkedin_link: Optional[str] = None,
        instagram_link: Optional[str] = None,
        github_link: Optional[str] = None,
    ) -> UserDetailsTable:
        """Create or update user details."""
        user_details = self.get_by_user_id(user_id)

        if user_details:
            # Update existing
            if country is not None:
                user_details.country = country
            if city is not None:
                user_details.city = city
            if postal_code is not None:
                user_details.postal_code = postal_code
            if facebook_link is not None:
                user_details.facebook_link = facebook_link
            if twitter_link is not None:
                user_details.twitter_link = twitter_link
            if linkedin_link is not None:
                user_details.linkedin_link = linkedin_link
            if instagram_link is not None:
                user_details.instagram_link = instagram_link
            if github_link is not None:
                user_details.github_link = github_link

            return self.update(user_details)
        else:
            # Create new
            user_details = UserDetailsTable(
                user_id=user_id,
                country=country,
                city=city,
                postal_code=postal_code,
                facebook_link=facebook_link,
                twitter_link=twitter_link,
                linkedin_link=linkedin_link,
                instagram_link=instagram_link,
                github_link=github_link,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            return self.create(user_details)

    def get_by_country(self, country: str) -> list[UserDetailsTable]:
        """Get all user details by country."""
        return self.db.query(UserDetailsTable).filter(
            UserDetailsTable.country == country
        ).all()

    def get_by_city(self, country: str, city: str) -> list[UserDetailsTable]:
        """Get all user details by country and city."""
        return self.db.query(UserDetailsTable).filter(
            UserDetailsTable.country == country,
            UserDetailsTable.city == city
        ).all()
