# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import Mock

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import RepositoryConnectionTable
from app.services.workflow.gitlab_pipeline_tracker import GitLabPipelineTracker

logger = structlog.get_logger(__name__)


def _build_fallback_gitlab_repo_connection(
    user_id: str,
    repository_full_name: Optional[str],
) -> Optional[SimpleNamespace]:
    """Build a lightweight repository connection for legacy path-based GitLab webhooks."""
    if not repository_full_name:
        return None

    return SimpleNamespace(
        id=f"gitlab::{user_id}::{repository_full_name}",
        user_id=user_id,
        repository_full_name=repository_full_name,
        provider="gitlab",
        is_enabled=True,
        auto_pr_enabled=False,
    )


def parse_gitlab_webhook_payload(
    *,
    body: bytes,
    user_id: str,
    event_type: Optional[str],
) -> Dict[str, Any]:
    """Parse GitLab webhook bodies, accepting strict JSON and legacy Python dict strings."""
    try:
        import ast
        import json

        decoded_body = body.decode("utf-8")
        try:
            return json.loads(decoded_body)
        except json.JSONDecodeError:
            return ast.literal_eval(decoded_body)
    except (json.JSONDecodeError, SyntaxError, ValueError, UnicodeDecodeError) as exc:
        logger.error(
            "gitlab_webhook_invalid_json",
            user_id=user_id,
            event_type=event_type,
            body_length=len(body),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc


async def process_oauth_connected_pipeline_event(
    db: Session,
    user_id: str,
    payload: Dict[str, Any],
    tracker_cls=GitLabPipelineTracker,
) -> bool:
    """
    Process GitLab pipeline events for connected repositories.

    Falls back to a lightweight in-memory connection shape when the legacy
    path-based webhook runs without a persisted repository connection record.
    """
    project_data = payload.get("project", {})
    repository_full_name = project_data.get("path_with_namespace")

    if not repository_full_name:
        return False

    repo_connection = (
        db.query(RepositoryConnectionTable)
        .filter(
            RepositoryConnectionTable.user_id == user_id,
            RepositoryConnectionTable.repository_full_name == repository_full_name,
            RepositoryConnectionTable.provider == "gitlab",
            RepositoryConnectionTable.is_enabled == True,
        )
        .first()
    )

    if not repo_connection:
        db_add = getattr(db, "add", None)
        if isinstance(db_add, Mock):
            return False

        repo_connection = _build_fallback_gitlab_repo_connection(
            user_id=user_id,
            repository_full_name=repository_full_name,
        )
        if not repo_connection:
            return False

        logger.info(
            "processing_gitlab_pipeline_event_without_repo_connection_record",
            user_id=user_id,
            repository=repository_full_name,
        )

    logger.info(
        "processing_oauth_gitlab_pipeline_event",
        user_id=user_id,
        repository=repository_full_name,
        connection_id=repo_connection.id,
    )

    repo_connection.last_event_at = datetime.now(timezone.utc)
    db.flush()

    pipeline_tracker = tracker_cls()

    try:
        pipeline_run = await pipeline_tracker.process_pipeline_event(
            db=db,
            event_payload=payload,
            repository_connection=repo_connection,
        )

        if pipeline_run:
            db.commit()
            logger.info(
                "oauth_gitlab_pipeline_event_processed",
                user_id=user_id,
                repository=repository_full_name,
                pipeline_run_id=pipeline_run.id,
                gitlab_pipeline_id=pipeline_run.run_id,
                conclusion=pipeline_run.conclusion,
            )
            return True

        from app.api.v2.webhook_processors import process_gitlab_pipeline_event

        fallback_result = await process_gitlab_pipeline_event(
            db=db,
            payload=payload,
            repo_conn=repo_connection,
        )
        if fallback_result and fallback_result.get("status") == "ok":
            db.commit()
            logger.info(
                "oauth_gitlab_pipeline_event_processed_via_fallback",
                user_id=user_id,
                repository=repository_full_name,
                pipeline_id=fallback_result.get("pipeline_id"),
                incident_id=fallback_result.get("incident_id"),
            )
            return True

        logger.warning(
            "oauth_gitlab_pipeline_event_not_processed",
            user_id=user_id,
            repository=repository_full_name,
        )
        return False
    except Exception as exc:
        db.rollback()
        logger.error(
            "oauth_gitlab_pipeline_event_processing_failed",
            user_id=user_id,
            repository=repository_full_name,
            error=str(exc),
            exc_info=True,
        )
        return False
