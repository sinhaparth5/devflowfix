# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Webhook Processing API Endpoints

Universal webhook endpoints for receiving events from GitHub and GitLab.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
import structlog
import json

from app.core.config import get_settings
from app.dependencies import get_db
from app.services.webhook.webhook_manager import WebhookManager
from app.services.oauth.token_manager import get_token_manager
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.adapters.database.postgres.models import (
    RepositoryConnectionTable,
    WorkflowRunTable,
    IncidentTable,
)

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
    """
    Process GitHub webhook events.

    **Flow:**
    1. Extract repository from payload
    2. Look up repository connection in database
    3. Verify webhook signature
    4. Route event to appropriate processor
    5. Return 200 OK

    **Headers:**
    - X-GitHub-Event: Event type (workflow_run, pull_request, push)
    - X-Hub-Signature-256: HMAC signature for verification
    - X-GitHub-Delivery: Unique delivery ID

    **Response:**
    - 200 OK if processed successfully
    - 401 Unauthorized if signature verification fails
    - 404 Not Found if repository not connected
    - 400 Bad Request if payload is invalid
    """
    try:
        # Get request headers
        event_type = request.headers.get("X-GitHub-Event")
        signature = request.headers.get("X-Hub-Signature-256")
        delivery_id = request.headers.get("X-GitHub-Delivery")

        logger.info(
            "github_webhook_received",
            event_type=event_type,
            delivery_id=delivery_id,
        )

        # Check if signature header exists
        if not signature:
            logger.error("missing_signature_header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header. Webhook secret not configured in GitHub."
            )

        # Get raw body for signature verification
        body = await request.body()

        # Parse JSON payload
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error("invalid_webhook_payload", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )

        # Extract repository information
        if "repository" not in payload:
            logger.error("missing_repository_in_payload")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing repository information in payload"
            )

        repository_full_name = payload["repository"]["full_name"]

        # Look up repository connection
        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.repository_full_name == repository_full_name,
            RepositoryConnectionTable.provider == "github",
        ).first()

        if not repo_conn:
            logger.warning(
                "webhook_for_unknown_repository",
                repository=repository_full_name,
            )
            return {"status": "ok", "message": "Repository not connected"}

        # Check if webhook secret exists in database
        if not repo_conn.webhook_secret:
            logger.error(
                "missing_webhook_secret_in_db",
                repository=repository_full_name,
                connection_id=repo_conn.id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook secret not found. Please reconnect the repository."
            )

        # Get token manager for secret decryption
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        # Decrypt webhook secret
        try:
            webhook_secret = token_manager.decrypt_token(repo_conn.webhook_secret)
        except Exception as e:
            logger.error(
                "webhook_secret_decryption_failed",
                repository=repository_full_name,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt webhook secret. Please reconnect the repository."
            )

        # Verify signature
        try:
            is_valid = WebhookManager.verify_github_signature(
                payload=body,
                signature=signature,
                secret=webhook_secret,
            )

            if not is_valid:
                logger.error(
                    "webhook_signature_verification_failed",
                    repository=repository_full_name,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
        except ValueError as e:
            logger.error(
                "webhook_signature_invalid_format",
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )

        # Update last delivery time
        from datetime import datetime, timezone
        repo_conn.webhook_last_delivery_at = datetime.now(timezone.utc)

        # Route to appropriate event processor
        if event_type == "workflow_run":
            result = await process_workflow_run_event(db, payload, repo_conn)
        elif event_type == "pull_request":
            result = await process_pull_request_event(db, payload, repo_conn)
        elif event_type == "push":
            result = await process_push_event(db, payload, repo_conn)
        else:
            logger.info(
                "unhandled_webhook_event",
                event_type=event_type,
                repository=repository_full_name,
            )
            result = {"status": "ok", "message": f"Event type {event_type} not processed"}

        db.commit()

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "webhook_processing_error",
            error=str(e),
            exc_info=True,
        )
        # Return 200 to prevent GitHub retries
        return {"status": "error", "message": str(e)}


async def process_workflow_run_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """
    Process workflow_run webhook event.

    Creates/updates workflow run records and creates incidents for failures.

    Args:
        db: Database session
        payload: GitHub webhook payload
        repo_conn: Repository connection record

    Returns:
        Processing result
    """
    action = payload.get("action")
    workflow_run_data = payload.get("workflow_run", {})

    logger.info(
        "processing_workflow_run_event",
        repository=repo_conn.repository_full_name,
        action=action,
        run_id=workflow_run_data.get("id"),
        status=workflow_run_data.get("status"),
        conclusion=workflow_run_data.get("conclusion"),
    )

    # Only process completed workflows
    if action != "completed":
        return {"status": "ok", "message": f"Workflow action '{action}' not processed"}

    # Create or update workflow run
    from datetime import datetime, timezone
    import uuid

    run_id = str(workflow_run_data["id"])

    existing_run = db.query(WorkflowRunTable).filter(
        WorkflowRunTable.repository_connection_id == repo_conn.id,
        WorkflowRunTable.run_id == run_id,
    ).first()

    if existing_run:
        # Update existing run
        existing_run.status = workflow_run_data["status"]
        existing_run.conclusion = workflow_run_data.get("conclusion")
        existing_run.updated_at = datetime.now(timezone.utc)
        workflow_run = existing_run
        logger.info("workflow_run_updated", run_id=run_id)
    else:
        # Create new workflow run
        workflow_run = WorkflowRunTable(
            id=str(uuid.uuid4()),
            repository_connection_id=repo_conn.id,
            run_id=run_id,
            run_number=workflow_run_data["run_number"],
            workflow_name=workflow_run_data["name"],
            workflow_id=str(workflow_run_data["workflow_id"]),
            event=workflow_run_data["event"],
            status=workflow_run_data["status"],
            conclusion=workflow_run_data.get("conclusion"),
            branch=workflow_run_data["head_branch"],
            commit_sha=workflow_run_data["head_sha"],
            commit_message=workflow_run_data.get("head_commit", {}).get("message", ""),
            author=workflow_run_data.get("head_commit", {}).get("author", {}).get("name", ""),
            run_started_at=datetime.fromisoformat(workflow_run_data["run_started_at"].replace("Z", "+00:00")) if workflow_run_data.get("run_started_at") else None,
            run_url=workflow_run_data["html_url"],
            logs_url=workflow_run_data.get("logs_url"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(workflow_run)
        logger.info("workflow_run_created", run_id=run_id)

    # Create incident if workflow failed
    if workflow_run_data.get("conclusion") == "failure":
        # Check if incident already exists
        existing_incident = db.query(IncidentTable).filter(
            IncidentTable.workflow_run_id == workflow_run.id,
        ).first()

        if not existing_incident:
            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"

            incident = IncidentTable(
                incident_id=incident_id,
                user_id=repo_conn.user_id,
                workflow_run_id=workflow_run.id,
                repository=repo_conn.repository_full_name,
                workflow_name=workflow_run.workflow_name,
                branch=workflow_run.branch,
                commit_sha=workflow_run.commit_sha,
                run_number=workflow_run.run_number,
                severity="high",
                status="open",
                source="webhook",
                title=f"Workflow '{workflow_run.workflow_name}' failed on {workflow_run.branch}",
                description=f"Workflow run #{workflow_run.run_number} failed.\n\n"
                           f"Commit: {workflow_run.commit_sha[:7]}\n"
                           f"Branch: {workflow_run.branch}\n"
                           f"Message: {workflow_run.commit_message}",
                metadata={
                    "run_url": workflow_run.run_url,
                    "logs_url": workflow_run.logs_url,
                    "event": workflow_run.event,
                    "author": workflow_run.author,
                    "detected_by": "webhook",
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(incident)

            logger.info(
                "incident_created_from_webhook",
                incident_id=incident_id,
                workflow_run_id=workflow_run.id,
                repository=repo_conn.repository_full_name,
            )

            return {
                "status": "ok",
                "action": "incident_created",
                "incident_id": incident_id,
                "workflow_run_id": run_id,
            }

    return {
        "status": "ok",
        "action": "workflow_run_processed",
        "workflow_run_id": run_id,
    }


async def process_pull_request_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """
    Process pull_request webhook event.

    Args:
        db: Database session
        payload: GitHub webhook payload
        repo_conn: Repository connection record

    Returns:
        Processing result
    """
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})

    logger.info(
        "processing_pull_request_event",
        repository=repo_conn.repository_full_name,
        action=action,
        pr_number=pr_data.get("number"),
        state=pr_data.get("state"),
    )

    # For now, just log PR events
    # Future: Track PR status for auto-fix PRs
    return {
        "status": "ok",
        "action": "pull_request_logged",
        "pr_number": pr_data.get("number"),
    }


async def process_push_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """
    Process push webhook event.

    Args:
        db: Database session
        payload: GitHub webhook payload
        repo_conn: Repository connection record

    Returns:
        Processing result
    """
    ref = payload.get("ref")
    commits = payload.get("commits", [])

    logger.info(
        "processing_push_event",
        repository=repo_conn.repository_full_name,
        ref=ref,
        commit_count=len(commits),
    )

    # For now, just log push events
    # Future: Trigger analysis on push
    return {
        "status": "ok",
        "action": "push_logged",
        "ref": ref,
        "commits": len(commits),
    }


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
    """
    Process GitLab webhook events.

    **Headers:**
    - X-Gitlab-Event: Event type (Pipeline Hook, Merge Request Hook, Push Hook)
    - X-Gitlab-Token: Webhook token for verification

    **Response:**
    - 200 OK if processed successfully
    - 401 Unauthorized if token verification fails
    """
    try:
        event_type = request.headers.get("X-Gitlab-Event")
        token = request.headers.get("X-Gitlab-Token")

        logger.info(
            "gitlab_webhook_received",
            event_type=event_type,
        )

        # Get raw body
        body = await request.body()

        # Parse JSON payload
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error("invalid_webhook_payload", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )

        # Extract project information
        project = payload.get("project", {})
        project_path = project.get("path_with_namespace")

        if not project_path:
            logger.error("missing_project_in_payload")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing project information in payload"
            )

        # Look up repository connection
        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.repository_full_name == project_path,
            RepositoryConnectionTable.provider == "gitlab",
        ).first()

        if not repo_conn:
            logger.warning(
                "webhook_for_unknown_project",
                project=project_path,
            )
            return {"status": "ok", "message": "Project not connected"}

        # Get token manager for secret decryption
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        # Decrypt webhook secret
        webhook_secret = token_manager.decrypt_token(repo_conn.webhook_secret)

        # Verify token
        is_valid = WebhookManager.verify_gitlab_signature(
            token_header=token,
            secret=webhook_secret,
        )

        if not is_valid:
            logger.error(
                "gitlab_webhook_token_verification_failed",
                project=project_path,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook token"
            )

        # Update last delivery time
        from datetime import datetime, timezone
        repo_conn.webhook_last_delivery_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "gitlab_webhook_processed",
            event_type=event_type,
            project=project_path,
        )

        # For now, just acknowledge receipt
        # Future: Process GitLab pipeline events similar to GitHub
        return {"status": "ok", "event_type": event_type}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "gitlab_webhook_processing_error",
            error=str(e),
            exc_info=True,
        )
        return {"status": "error", "message": str(e)}
