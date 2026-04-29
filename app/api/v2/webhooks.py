# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Webhook Processing API Endpoints.

Universal endpoint layer for receiving events from GitHub and GitLab.
Event-specific processing lives in ``webhook_processors.py``.
"""

from typing import Any, Dict
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
import structlog

from app.api.shared.webhooks import verify_github_signature, verify_gitlab_token
from app.api.v2.webhook_processors import (
    process_gitlab_merge_request_event,
    process_gitlab_pipeline_event,
    process_gitlab_push_event,
    process_pull_request_event,
    process_push_event,
    process_workflow_run_event,
)
from app.core.config import get_settings
from app.dependencies import get_db
from app.services.oauth.token_manager import get_token_manager
from app.adapters.database.postgres.models import RepositoryConnectionTable

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
settings = get_settings()


@router.post(
    "/github",
    status_code=status.HTTP_200_OK,
    summary="GitHub Webhook Endpoint",
    description="Universal endpoint for receiving GitHub webhook events.",
)
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        event_type = request.headers.get("X-GitHub-Event")
        signature = request.headers.get("X-Hub-Signature-256")
        delivery_id = request.headers.get("X-GitHub-Delivery")

        logger.info("github_webhook_received", event_type=event_type, delivery_id=delivery_id)

        if not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header. Webhook secret not configured in GitHub.",
            )

        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

        repository = payload.get("repository", {})
        repository_full_name = repository.get("full_name")
        if not repository_full_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing repository information in payload",
            )

        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.repository_full_name == repository_full_name,
            RepositoryConnectionTable.provider == "github",
        ).first()
        if not repo_conn:
            logger.warning("webhook_for_unknown_repository", repository=repository_full_name)
            return {"status": "ok", "message": "Repository not connected"}

        if not repo_conn.webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook secret not found. Please reconnect the repository.",
            )

        token_manager = get_token_manager(settings.oauth_token_encryption_key)
        try:
            webhook_secret = token_manager.decrypt_token(repo_conn.webhook_secret)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt webhook secret. Please reconnect the repository.",
            )

        if not verify_github_signature(body, signature, webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

        from datetime import datetime, timezone

        repo_conn.webhook_last_delivery_at = datetime.now(timezone.utc)

        if event_type == "workflow_run":
            result = await process_workflow_run_event(db, payload, repo_conn)
        elif event_type == "pull_request":
            result = await process_pull_request_event(db, payload, repo_conn)
        elif event_type == "push":
            result = await process_push_event(db, payload, repo_conn)
        else:
            result = {"status": "ok", "message": f"Event type {event_type} not processed"}

        db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("webhook_processing_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal webhook processing error",
        ) from exc


@router.post(
    "/gitlab",
    status_code=status.HTTP_200_OK,
    summary="GitLab Webhook Endpoint",
    description="Universal endpoint for receiving GitLab webhook events.",
)
async def gitlab_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        event_type = request.headers.get("X-Gitlab-Event")
        token = request.headers.get("X-Gitlab-Token")

        logger.info("gitlab_webhook_received", event_type=event_type)

        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

        project_path = payload.get("project", {}).get("path_with_namespace")
        if not project_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing project information in payload",
            )

        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.repository_full_name == project_path,
            RepositoryConnectionTable.provider == "gitlab",
        ).first()
        if not repo_conn:
            logger.warning("webhook_for_unknown_project", project=project_path)
            return {"status": "ok", "message": "Project not connected"}

        token_manager = get_token_manager(settings.oauth_token_encryption_key)
        webhook_secret = token_manager.decrypt_token(repo_conn.webhook_secret)
        if not verify_gitlab_token(token, webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")

        from datetime import datetime, timezone

        repo_conn.webhook_last_delivery_at = datetime.now(timezone.utc)
        db.commit()

        if event_type == "Pipeline Hook":
            return await process_gitlab_pipeline_event(db, payload, repo_conn)
        if event_type == "Merge Request Hook":
            return await process_gitlab_merge_request_event(db, payload, repo_conn)
        if event_type == "Push Hook":
            return await process_gitlab_push_event(db, payload, repo_conn)
        return {"status": "ok", "message": f"Event type {event_type} not processed"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("gitlab_webhook_processing_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal webhook processing error",
        ) from exc
