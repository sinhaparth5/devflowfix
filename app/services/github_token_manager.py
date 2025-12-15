# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub Token Manager Service

Manages storage and retrieval of GitHub access tokens for multiple repositories.
Supports organization-level and repository-specific tokens.
"""

import os
import json
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import structlog

from app.adapters.database.postgres.models import GitHubTokenTable
from app.core.config import Settings

logger = structlog.get_logger(__name__)


class GitHubTokenManager:
    """
    Securely manages GitHub access tokens for multiple repositories.
    
    Features:
    - Store tokens per-repo or per-organization
    - Encrypt tokens at rest
    - Automatic token validation
    - Token rotation support
    - Audit logging
    
    Example:
        ```python
        manager = GitHubTokenManager()
        
        # Store token for a specific repo
        manager.register_token(
            owner="myorg",
            repo="myrepo",
            token="ghp_xxxxx",
            description="Token for myrepo auto-fix PRs"
        )
        
        # Retrieve token for PR creation
        token = manager.get_token("myorg", "myrepo")
        ```
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize token manager.
        
        Args:
            settings: Application settings with encryption key
        """
        self.settings = settings or Settings()
        self._cipher_suite = self._init_encryption()
        self._session = None
    
    def _init_encryption(self) -> Optional[Fernet]:
        """
        Initialize encryption cipher.
        
        Uses DEVFLOWFIX_ENCRYPTION_KEY from environment if available,
        otherwise tokens are stored unencrypted (not recommended for production).
        """
        encryption_key = os.environ.get("DEVFLOWFIX_ENCRYPTION_KEY")
        
        if encryption_key:
            try:
                return Fernet(encryption_key.encode())
            except Exception as e:
                logger.warning(
                    "encryption_init_failed",
                    error=str(e),
                )
                return None
        
        logger.warning("token_encryption_disabled_no_key")
        return None
    
    def _encrypt_token(self, token: str) -> str:
        """Encrypt token if cipher available, otherwise return as-is."""
        if not self._cipher_suite:
            return token
        
        try:
            encrypted = self._cipher_suite.encrypt(token.encode()).decode()
            return encrypted
        except Exception as e:
            logger.error("token_encryption_failed", error=str(e))
            return token
    
    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token if cipher available."""
        if not self._cipher_suite:
            return encrypted_token
        
        try:
            decrypted = self._cipher_suite.decrypt(encrypted_token.encode()).decode()
            return decrypted
        except Exception as e:
            logger.error("token_decryption_failed", error=str(e))
            return encrypted_token
    
    def register_token(
        self,
        user_id: str,
        owner: str,
        repo: Optional[str],
        token: str,
        description: str = "",
        scopes: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> Dict[str, Any]:
        """
        Register a GitHub access token for a specific user.

        Args:
            user_id: User ID who owns this token
            owner: GitHub organization/user
            repo: Repository name (None for org-level token)
            token: GitHub PAT or token string
            description: Human-readable description
            scopes: Token scopes (repo, workflow, contents, etc.)
            created_by: Who created this token (for audit)

        Returns:
            Token record details
        """
        from app.dependencies import get_db

        repository_full = f"{owner}/{repo}" if repo else f"{owner}/*"

        logger.info(
            "token_registration_start",
            user_id=user_id,
            repository=repository_full,
            description=description,
            created_by=created_by,
        )

        db_gen = get_db()
        db = next(db_gen)
        try:
            # Check if token already exists for THIS USER
            existing = db.query(GitHubTokenTable).filter(
                GitHubTokenTable.user_id == user_id,
                GitHubTokenTable.repository_full == repository_full
            ).first()

            encrypted_token = self._encrypt_token(token)

            if existing:
                # Update existing token
                existing.token = encrypted_token
                existing.description = description
                existing.updated_at = datetime.now(timezone.utc)
                existing.is_active = True
                existing.is_valid = True
                if scopes:
                    existing.scopes = ",".join(scopes)
                    existing.permissions_json = json.dumps({"scopes": scopes})

                db.commit()

                logger.info(
                    "token_updated",
                    repository=repository_full,
                    token_id=existing.id,
                )

                return self._token_to_dict(existing)

            # Create new token record
            token_record = GitHubTokenTable(
                id=f"token_{user_id}_{owner}_{repo or 'org'}_{datetime.now(timezone.utc).timestamp()}",
                user_id=user_id,
                repository_owner=owner,
                repository_name=repo,
                repository_full=repository_full,
                token=encrypted_token,
                is_encrypted=bool(self._cipher_suite),
                description=description,
                created_by=created_by,
                scopes=",".join(scopes) if scopes else None,
                permissions_json=json.dumps({"scopes": scopes}) if scopes else None,
            )

            db.add(token_record)
            db.commit()
            db.refresh(token_record)

            logger.info(
                "token_registered",
                repository=repository_full,
                token_id=token_record.id,
            )

            return self._token_to_dict(token_record)
        except Exception as e:
            logger.error(
                "token_registration_failed",
                repository=repository_full,
                error=str(e),
            )
            raise
        finally:
            db.close()
    
    def get_token(self, user_id: str, owner: str, repo: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a GitHub token for a specific user and repository.

        Tries in order:
        1. Repo-specific token (user_id + owner/repo)
        2. Organization token (user_id + owner/*)

        Args:
            user_id: User ID who owns the token
            owner: Repository owner
            repo: Repository name (optional)

        Returns:
            Decrypted token or None if not found
        """
        from app.dependencies import get_db

        db_gen = get_db()
        db = next(db_gen)
        try:
            # Try repo-specific token first
            if repo:
                repo_specific = f"{owner}/{repo}"
                token_record = db.query(GitHubTokenTable).filter(
                    GitHubTokenTable.user_id == user_id,
                    GitHubTokenTable.repository_full == repo_specific,
                    GitHubTokenTable.is_active == True,
                    GitHubTokenTable.is_valid == True,
                ).first()

                if token_record:
                    # Update last used timestamp
                    token_record.last_used_at = datetime.now(timezone.utc)
                    db.commit()

                    logger.debug(
                        "token_retrieved",
                        user_id=user_id,
                        repository=repo_specific,
                        token_id=token_record.id,
                    )

                    return self._decrypt_token(token_record.token)

            # Fall back to organization token
            org_token = f"{owner}/*"
            token_record = db.query(GitHubTokenTable).filter(
                GitHubTokenTable.user_id == user_id,
                GitHubTokenTable.repository_full == org_token,
                GitHubTokenTable.is_active == True,
                GitHubTokenTable.is_valid == True,
            ).first()

            if token_record:
                token_record.last_used_at = datetime.now(timezone.utc)
                db.commit()

                logger.debug(
                    "token_retrieved_org_level",
                    user_id=user_id,
                    organization=owner,
                    token_id=token_record.id,
                )

                return self._decrypt_token(token_record.token)

            logger.warning(
                "token_not_found",
                user_id=user_id,
                owner=owner,
                repo=repo,
            )

            return None

        except Exception as e:
            logger.error(
                "token_retrieval_failed",
                user_id=user_id,
                owner=owner,
                repo=repo,
                error=str(e),
            )
            return None
        finally:
            db.close()
    
    def list_tokens(
        self,
        user_id: str,
        owner: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        List registered tokens for a specific user.

        Args:
            user_id: User ID to filter tokens
            owner: Filter by owner (optional)
            active_only: Only list active tokens

        Returns:
            List of token records (tokens masked)
        """
        from app.dependencies import get_db

        db_gen = get_db()
        db = next(db_gen)
        try:
            query = db.query(GitHubTokenTable).filter(
                GitHubTokenTable.user_id == user_id
            )

            if owner:
                query = query.filter(GitHubTokenTable.repository_owner == owner)

            if active_only:
                query = query.filter(GitHubTokenTable.is_active == True)

            records = query.all()

            return [
                {
                    "id": record.id,
                    "repository": record.repository_full,
                    "owner": record.repository_owner,
                    "repo": record.repository_name,
                    "token_masked": record.token[:10] + "..." if record.token else "***",
                    "description": record.description,
                    "created_at": record.created_at.isoformat(),
                    "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
                    "is_active": record.is_active,
                    "is_valid": record.is_valid,
                    "scopes": record.scopes,
                }
                for record in records
            ]

        except Exception as e:
            logger.error("token_list_failed", error=str(e))
            return []
        finally:
            db.close()
    
    def deactivate_token(self, token_id: str, user_id: Optional[str] = None) -> bool:
        """
        Deactivate a token (soft delete).

        Args:
            token_id: Token record ID
            user_id: User ID for ownership verification (optional but recommended)

        Returns:
            True if deactivated, False otherwise
        """
        from app.dependencies import get_db

        db_gen = get_db()
        db = next(db_gen)
        try:
            query = db.query(GitHubTokenTable).filter(
                GitHubTokenTable.id == token_id
            )

            # Verify ownership if user_id provided
            if user_id:
                query = query.filter(GitHubTokenTable.user_id == user_id)

            token_record = query.first()

            if not token_record:
                logger.warning(
                    "token_not_found_for_deactivation",
                    token_id=token_id,
                    user_id=user_id,
                )
                return False

            token_record.is_active = False
            db.commit()

            logger.info(
                "token_deactivated",
                token_id=token_id,
                user_id=user_id,
            )
            return True

        except Exception as e:
            logger.error("token_deactivation_failed", token_id=token_id, error=str(e))
            return False
        finally:
            db.close()
    
    def validate_token(self, user_id: str, owner: str, repo: Optional[str] = None) -> bool:
        """
        Validate that a token exists and is active for a user.

        Args:
            user_id: User ID
            owner: Repository owner
            repo: Repository name (optional)

        Returns:
            True if token is valid and working
        """
        token = self.get_token(user_id, owner, repo)
        if not token:
            return False

        # Could add GitHub API test call here
        # For now, just check presence
        return True
    
    def _token_to_dict(self, record: GitHubTokenTable) -> Dict[str, Any]:
        """Convert token record to dictionary."""
        return {
            "id": record.id,
            "repository": record.repository_full,
            "owner": record.repository_owner,
            "repo": record.repository_name,
            "token_masked": record.token[:10] + "..." if record.token else "***",
            "description": record.description,
            "created_at": record.created_at.isoformat(),
            "created_by": record.created_by,
            "is_active": record.is_active,
            "is_valid": record.is_valid,
            "scopes": record.scopes,
        }
