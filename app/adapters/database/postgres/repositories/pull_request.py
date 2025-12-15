# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Pull Request Repository

Database access layer for PR management tables.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
import structlog

from app.adapters.database.postgres.models import (
    PullRequestTable,
    PRCreationLogTable,
    GitHubTokenTable,
    PRStatus,
)

logger = structlog.get_logger(__name__)


class PullRequestRepository:
    """
    Repository for Pull Request operations.

    Provides database access for PR tracking and management.
    """

    def __init__(self, db: Session):
        """
        Initialize repository.

        Args:
            db: Database session
        """
        self.db = db

    def create_pull_request(
        self,
        pr_data: Dict[str, Any],
    ) -> PullRequestTable:
        """
        Create a new pull request record.

        Args:
            pr_data: Pull request data dictionary

        Returns:
            Created pull request record
        """
        pr_record = PullRequestTable(**pr_data)
        self.db.add(pr_record)
        self.db.commit()
        self.db.refresh(pr_record)

        logger.info(
            "pull_request_created",
            pr_id=pr_record.id,
            incident_id=pr_record.incident_id,
            pr_number=pr_record.pr_number,
        )

        return pr_record

    def get_pull_request(self, pr_id: str) -> Optional[PullRequestTable]:
        """
        Get pull request by ID.

        Args:
            pr_id: Pull request ID

        Returns:
            Pull request record or None
        """
        return self.db.query(PullRequestTable).filter(
            PullRequestTable.id == pr_id
        ).first()

    def get_pull_request_by_number(
        self,
        repository_full: str,
        pr_number: int,
    ) -> Optional[PullRequestTable]:
        """
        Get pull request by repository and PR number.

        Args:
            repository_full: Full repository name (owner/repo)
            pr_number: GitHub PR number

        Returns:
            Pull request record or None
        """
        return self.db.query(PullRequestTable).filter(
            PullRequestTable.repository_full == repository_full,
            PullRequestTable.pr_number == pr_number,
        ).first()

    def list_pull_requests(
        self,
        incident_id: Optional[str] = None,
        repository: Optional[str] = None,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[PullRequestTable], int]:
        """
        List pull requests with filters.

        Args:
            incident_id: Filter by incident ID
            repository: Filter by repository (owner/repo)
            status_filter: Filter by status
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (list of PRs, total count)
        """
        query = self.db.query(PullRequestTable)

        if incident_id:
            query = query.filter(PullRequestTable.incident_id == incident_id)

        if repository:
            query = query.filter(PullRequestTable.repository_full == repository)

        if status_filter:
            query = query.filter(PullRequestTable.status == status_filter)

        total = query.count()
        prs = query.order_by(desc(PullRequestTable.created_at)).offset(skip).limit(limit).all()

        logger.debug(
            "pull_requests_listed",
            count=len(prs),
            total=total,
            incident_id=incident_id,
            repository=repository,
        )

        return prs, total

    def update_pull_request_status(
        self,
        pr_id: str,
        status: PRStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[PullRequestTable]:
        """
        Update pull request status.

        Args:
            pr_id: Pull request ID
            status: New status
            metadata: Optional metadata to merge

        Returns:
            Updated pull request record or None
        """
        pr = self.get_pull_request(pr_id)
        if not pr:
            return None

        pr.status = status
        pr.updated_at = datetime.now(timezone.utc)

        if status == PRStatus.MERGED:
            pr.merged_at = datetime.now(timezone.utc)
        elif status == PRStatus.CLOSED:
            pr.closed_at = datetime.now(timezone.utc)

        if metadata:
            pr.extra_metadata = pr.extra_metadata or {}
            pr.extra_metadata.update(metadata)

        self.db.commit()
        self.db.refresh(pr)

        logger.info(
            "pull_request_status_updated",
            pr_id=pr_id,
            status=status.value,
        )

        return pr

    def get_pull_requests_by_incident(
        self,
        incident_id: str,
    ) -> List[PullRequestTable]:
        """
        Get all pull requests for an incident.

        Args:
            incident_id: Incident ID

        Returns:
            List of pull request records
        """
        return self.db.query(PullRequestTable).filter(
            PullRequestTable.incident_id == incident_id
        ).order_by(desc(PullRequestTable.created_at)).all()

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get pull request statistics.

        Returns:
            Dictionary with statistics
        """
        total_prs = self.db.query(PullRequestTable).count()

        status_counts = {}
        for status in PRStatus:
            count = self.db.query(PullRequestTable).filter(
                PullRequestTable.status == status
            ).count()
            status_counts[status.value] = count

        merged_prs = self.db.query(PullRequestTable).filter(
            PullRequestTable.status == PRStatus.MERGED
        ).count()

        avg_files_changed = self.db.query(
            func.avg(PullRequestTable.files_changed)
        ).scalar() or 0

        total_additions = self.db.query(
            func.sum(PullRequestTable.additions)
        ).scalar() or 0

        total_deletions = self.db.query(
            func.sum(PullRequestTable.deletions)
        ).scalar() or 0

        logger.debug(
            "pull_request_statistics_retrieved",
            total=total_prs,
            merged=merged_prs,
        )

        return {
            "total_prs": total_prs,
            "merged_count": merged_prs,
            "merge_rate": (merged_prs / total_prs * 100) if total_prs > 0 else 0,
            "status_distribution": status_counts,
            "avg_files_per_pr": float(avg_files_changed),
            "total_additions": int(total_additions),
            "total_deletions": int(total_deletions),
        }


class PRCreationLogRepository:
    """
    Repository for PR creation log operations.

    Provides database access for PR creation audit logs.
    """

    def __init__(self, db: Session):
        """
        Initialize repository.

        Args:
            db: Database session
        """
        self.db = db

    def create_log(
        self,
        log_data: Dict[str, Any],
    ) -> PRCreationLogTable:
        """
        Create a PR creation log entry.

        Args:
            log_data: Log data dictionary

        Returns:
            Created log record
        """
        log_record = PRCreationLogTable(**log_data)
        self.db.add(log_record)
        self.db.commit()
        self.db.refresh(log_record)

        logger.debug(
            "pr_creation_log_created",
            log_id=log_record.id,
            incident_id=log_record.incident_id,
            status=log_record.status,
        )

        return log_record

    def get_logs_by_incident(
        self,
        incident_id: str,
    ) -> List[PRCreationLogTable]:
        """
        Get all creation logs for an incident.

        Args:
            incident_id: Incident ID

        Returns:
            List of log records
        """
        return self.db.query(PRCreationLogTable).filter(
            PRCreationLogTable.incident_id == incident_id
        ).order_by(desc(PRCreationLogTable.created_at)).all()

    def get_logs_by_pr(
        self,
        pr_id: str,
    ) -> List[PRCreationLogTable]:
        """
        Get all creation logs for a PR.

        Args:
            pr_id: Pull request ID

        Returns:
            List of log records
        """
        return self.db.query(PRCreationLogTable).filter(
            PRCreationLogTable.pr_id == pr_id
        ).order_by(desc(PRCreationLogTable.created_at)).all()


class GitHubTokenRepository:
    """
    Repository for GitHub token operations.

    Provides database access for encrypted GitHub tokens.
    """

    def __init__(self, db: Session):
        """
        Initialize repository.

        Args:
            db: Database session
        """
        self.db = db

    def create_token(
        self,
        token_data: Dict[str, Any],
    ) -> GitHubTokenTable:
        """
        Create a new GitHub token record.

        Args:
            token_data: Token data dictionary

        Returns:
            Created token record
        """
        token_record = GitHubTokenTable(**token_data)
        self.db.add(token_record)
        self.db.commit()
        self.db.refresh(token_record)

        logger.info(
            "github_token_created",
            token_id=token_record.id,
            repository=token_record.repository_full,
        )

        return token_record

    def get_token(
        self,
        repository_full: str,
    ) -> Optional[GitHubTokenTable]:
        """
        Get token by repository.

        Args:
            repository_full: Full repository name (owner/repo or owner/*)

        Returns:
            Token record or None
        """
        return self.db.query(GitHubTokenTable).filter(
            GitHubTokenTable.repository_full == repository_full,
            GitHubTokenTable.is_active == True,
            GitHubTokenTable.is_valid == True,
        ).first()

    def get_token_by_owner(
        self,
        owner: str,
        repo: Optional[str] = None,
    ) -> Optional[GitHubTokenTable]:
        """
        Get token by owner and optionally repo.

        Tries repo-specific token first, then org-level token.

        Args:
            owner: Repository owner
            repo: Repository name (optional)

        Returns:
            Token record or None
        """
        # Try repo-specific token first
        if repo:
            repo_specific = f"{owner}/{repo}"
            token = self.get_token(repo_specific)
            if token:
                return token

        # Fall back to org-level token
        org_token = f"{owner}/*"
        return self.get_token(org_token)

    def update_token(
        self,
        repository_full: str,
        token_data: Dict[str, Any],
    ) -> Optional[GitHubTokenTable]:
        """
        Update existing token.

        Args:
            repository_full: Full repository name
            token_data: Token data to update

        Returns:
            Updated token record or None
        """
        token = self.get_token(repository_full)
        if not token:
            return None

        for key, value in token_data.items():
            if hasattr(token, key):
                setattr(token, key, value)

        token.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(token)

        logger.info(
            "github_token_updated",
            token_id=token.id,
            repository=repository_full,
        )

        return token

    def update_last_used(
        self,
        token_id: str,
    ) -> None:
        """
        Update last used timestamp for a token.

        Args:
            token_id: Token ID
        """
        token = self.db.query(GitHubTokenTable).filter(
            GitHubTokenTable.id == token_id
        ).first()

        if token:
            token.last_used_at = datetime.now(timezone.utc)
            self.db.commit()

    def deactivate_token(
        self,
        token_id: str,
    ) -> bool:
        """
        Deactivate a token (soft delete).

        Args:
            token_id: Token ID

        Returns:
            True if deactivated, False otherwise
        """
        token = self.db.query(GitHubTokenTable).filter(
            GitHubTokenTable.id == token_id
        ).first()

        if not token:
            logger.warning("token_not_found_for_deactivation", token_id=token_id)
            return False

        token.is_active = False
        self.db.commit()

        logger.info("github_token_deactivated", token_id=token_id)
        return True

    def list_tokens(
        self,
        owner: Optional[str] = None,
        active_only: bool = True,
    ) -> List[GitHubTokenTable]:
        """
        List tokens with filters.

        Args:
            owner: Filter by owner (optional)
            active_only: Only list active tokens

        Returns:
            List of token records
        """
        query = self.db.query(GitHubTokenTable)

        if owner:
            query = query.filter(GitHubTokenTable.repository_owner == owner)

        if active_only:
            query = query.filter(GitHubTokenTable.is_active == True)

        return query.order_by(desc(GitHubTokenTable.created_at)).all()
