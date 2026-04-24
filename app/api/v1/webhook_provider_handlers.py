# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import BackgroundTasks, HTTPException, Request, status
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import LogCategory, RepositoryConnectionTable
from app.api.v1.webhook_payloads import (
    extract_argocd_payload,
    extract_github_payload,
    extract_kubernetes_payload,
    is_argocd_failure_event,
    is_github_failure_event,
    is_kubernetes_failure_event,
)
from app.core.config import settings
from app.core.enums import IncidentSource
from app.core.schemas.webhook import WebhookResponse
from app.services.event_processor import EventProcessor
from app.services.oauth.token_manager import get_token_manager
from app.services.workflow.workflow_tracker import WorkflowTracker
from app.utils.app_logger import AppLogger

logger = structlog.get_logger(__name__)


async def process_oauth_connected_workflow_event(
    db: Session,
    user_id: str,
    payload: Dict[str, Any],
    event_type: str,
) -> bool:
    if event_type != "workflow_run":
        return False

    repository_full_name = payload.get("repository", {}).get("full_name")
    if not repository_full_name:
        return False

    repo_connection = (
        db.query(RepositoryConnectionTable)
        .filter(
            RepositoryConnectionTable.user_id == user_id,
            RepositoryConnectionTable.repository_full_name == repository_full_name,
            RepositoryConnectionTable.is_enabled == True,
        )
        .first()
    )
    if not repo_connection:
        return False

    logger.info(
        "processing_oauth_workflow_event",
        user_id=user_id,
        repository=repository_full_name,
        connection_id=repo_connection.id,
        event_type=event_type,
    )
    repo_connection.last_event_at = datetime.now(timezone.utc)
    db.flush()

    token_manager = get_token_manager(settings.oauth_token_encryption_key)
    workflow_tracker = WorkflowTracker(token_manager=token_manager)
    try:
        workflow_run = await workflow_tracker.process_workflow_run_event(
            db=db,
            event_payload=payload,
            repository_connection=repo_connection,
        )
        if workflow_run:
            db.commit()
            logger.info(
                "oauth_workflow_event_processed",
                user_id=user_id,
                repository=repository_full_name,
                workflow_run_id=workflow_run.id,
                github_run_id=workflow_run.run_id,
                conclusion=workflow_run.conclusion,
            )
            return True
        logger.warning("oauth_workflow_event_not_processed", user_id=user_id, repository=repository_full_name)
        return False
    except Exception as exc:
        db.rollback()
        logger.error(
            "oauth_workflow_event_processing_failed",
            user_id=user_id,
            repository=repository_full_name,
            error=str(exc),
            exc_info=True,
        )
        return False


async def verify_github_webhook_signature(
    user_id: str,
    request: Request,
    signature_header: Optional[str],
    db: Session,
    verify_github_signature: Callable[[bytes, str, str], bool],
) -> bytes:
    body = await request.body()
    logger.debug(
        "github_webhook_signature_verification_start",
        user_id=user_id,
        body_length=len(body),
        has_signature=bool(signature_header),
        content_type=request.headers.get("content-type"),
    )
    if not signature_header:
        logger.error("github_webhook_no_signature", user_id=user_id, body_length=len(body))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header. Configure webhook secret in GitHub repository settings.",
        )

    from app.adapters.database.postgres.repositories.users import UserRepository

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        logger.error("github_webhook_user_not_found", user_id=user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")
    if not user.is_active:
        logger.error("github_webhook_user_inactive", user_id=user_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User '{user_id}' is not active.")
    if not user.github_webhook_secret:
        logger.error("github_webhook_no_secret_configured", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No webhook secret configured for user '{user_id}'. Generate one using POST /api/v1/webhook/secret/generate",
        )

    if not verify_github_signature(body, signature_header, user.github_webhook_secret):
        logger.error(
            "github_webhook_invalid_signature",
            user_id=user_id,
            signature_prefix=signature_header[:20] if signature_header else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature. Signature does not match configured secret.",
        )

    logger.info("github_webhook_authenticated", user_id=user_id, email=user.email)
    return body


async def receive_github_webhook_impl(
    *,
    user_id: str,
    x_github_event: str,
    x_github_delivery: Optional[str],
    body: bytes,
    background_tasks: BackgroundTasks,
    event_processor: EventProcessor,
    db: Session,
    process_webhook_sync: Callable[..., None],
) -> WebhookResponse:
    incident_id = f"gh_{x_github_delivery or int(datetime.now(timezone.utc).timestamp() * 1000)}"
    app_logger = AppLogger(db, incident_id=incident_id, user_id=user_id)
    app_logger.webhook_received(
        f"GitHub {x_github_event} webhook received",
        details={"event_type": x_github_event, "delivery_id": x_github_delivery, "body_size": len(body) if body else 0},
    )

    logger.info(
        "github_webhook_received",
        incident_id=incident_id,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
        user_id=user_id,
    )
    if x_github_event == "ping":
        return WebhookResponse(incident_id=incident_id, acknowledged=True, queued=False, message="GitHub webhook ping received")
    if not body:
        logger.warning("github_webhook_empty_body", user_id=user_id, event_type=x_github_event, delivery_id=x_github_delivery)
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Empty body received for event {x_github_event}",
        )

    try:
        import json

        payload = json.loads(body.decode("utf-8"))
        app_logger.webhook_parsed(
            "Webhook payload parsed successfully",
            details={"event_type": x_github_event, "payload_keys": list(payload.keys())[:10]},
        )
        oauth_processed = await process_oauth_connected_workflow_event(
            db=db,
            user_id=user_id,
            payload=payload,
            event_type=x_github_event,
        )
        if oauth_processed:
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message="OAuth workflow event processed successfully",
            )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        app_logger.error(
            f"Failed to parse webhook JSON: {str(exc)}",
            error_obj=exc,
            category=LogCategory.WEBHOOK,
            stage="webhook_parsing",
        )
        logger.error(
            "github_webhook_invalid_json",
            user_id=user_id,
            event_type=x_github_event,
            body_length=len(body),
            body_preview=body[:200].decode("utf-8", errors="replace") if body else None,
            error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON payload: {exc}") from exc

    if not is_github_failure_event(x_github_event, payload):
        app_logger.info(
            f"Event {x_github_event} is not a failure event, skipping",
            category=LogCategory.WEBHOOK,
            stage="webhook_filtered",
        )
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Event {x_github_event} acknowledged (not a failure)",
        )

    normalized_payload = extract_github_payload(payload, x_github_event)
    normalized_payload["raw_payload"] = payload
    normalized_payload.setdefault("context", {})["user_id"] = user_id

    app_logger.info(
        "Webhook queued for background processing",
        category=LogCategory.WEBHOOK,
        stage="webhook_queued",
        details={"source": "github", "event_type": x_github_event},
    )
    background_tasks.add_task(
        process_webhook_sync,
        event_processor,
        normalized_payload,
        IncidentSource.GITHUB,
        incident_id,
        user_id,
    )
    logger.info("github_webhook_queued", incident_id=incident_id, event_type=x_github_event, user_id=user_id)
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message="GitHub failure detected, processing started",
    )


async def receive_github_webhook_sync_impl(
    *,
    user_id: str,
    x_github_event: str,
    x_github_delivery: Optional[str],
    body: bytes,
    event_processor: EventProcessor,
) -> WebhookResponse:
    incident_id = f"gh_{x_github_delivery or int(datetime.now(timezone.utc).timestamp() * 1000)}"
    if x_github_event == "ping":
        return WebhookResponse(incident_id=incident_id, acknowledged=True, queued=False, message="GitHub webhook ping received")
    if not body:
        logger.warning("github_webhook_empty_body_sync", user_id=user_id, event_type=x_github_event, delivery_id=x_github_delivery)
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Empty body received for event {x_github_event}",
        )

    try:
        import json

        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error(
            "github_webhook_invalid_json_sync",
            user_id=user_id,
            event_type=x_github_event,
            body_length=len(body),
            body_preview=body[:200].decode("utf-8", errors="replace") if body else None,
            error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON payload: {exc}") from exc

    if not is_github_failure_event(x_github_event, payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Event {x_github_event} acknowledged (not a failure)",
        )

    normalized_payload = extract_github_payload(payload, x_github_event)
    normalized_payload["raw_payload"] = payload
    normalized_payload.setdefault("context", {})["user_id"] = user_id
    result = await event_processor.process(payload=normalized_payload, source=IncidentSource.GITHUB)
    return WebhookResponse(
        incident_id=result.incident_id,
        acknowledged=True,
        queued=False,
        message=result.message,
    )


async def receive_argocd_webhook_impl(
    *,
    user_id: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    event_processor: EventProcessor,
    process_webhook_sync: Callable[..., None],
) -> WebhookResponse:
    incident_id = f"argo_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    app_name = payload.get("application", {}).get("metadata", {}).get("name", "unknown")
    logger.info("argocd_webhook_received", incident_id=incident_id, application=app_name, user_id=user_id)
    if not is_argocd_failure_event(payload):
        return WebhookResponse(incident_id=incident_id, acknowledged=True, queued=False, message="ArgoCD event acknowledged (not a failure)")
    normalized_payload = extract_argocd_payload(payload)
    normalized_payload["raw_payload"] = payload
    normalized_payload.setdefault("context", {})["user_id"] = user_id
    background_tasks.add_task(
        process_webhook_sync,
        event_processor,
        normalized_payload,
        IncidentSource.ARGOCD,
        incident_id,
        user_id,
    )
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message=f"ArgoCD failure detected for {app_name}, processing started",
    )


async def receive_kubernetes_webhook_impl(
    *,
    user_id: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    event_processor: EventProcessor,
    process_webhook_sync: Callable[..., None],
) -> WebhookResponse:
    incident_id = f"k8s_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    reason = payload.get("reason", "Unknown")
    logger.info("kubernetes_webhook_received", incident_id=incident_id, reason=reason, user_id=user_id)
    if not is_kubernetes_failure_event(payload):
        return WebhookResponse(incident_id=incident_id, acknowledged=True, queued=False, message="Kubernetes event acknowledged (not a failure)")
    normalized_payload = extract_kubernetes_payload(payload)
    normalized_payload["raw_payload"] = payload
    normalized_payload.setdefault("context", {})["user_id"] = user_id
    background_tasks.add_task(
        process_webhook_sync,
        event_processor,
        normalized_payload,
        IncidentSource.KUBERNETES,
        incident_id,
        user_id,
    )
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message=f"Kubernetes failure detected ({reason}), processing started",
    )


async def receive_gitlab_webhook_impl(
    *,
    user_id: str,
    body: bytes,
    x_gitlab_event: Optional[str],
    process_oauth_connected_pipeline_event: Callable[..., Any],
    parse_gitlab_webhook_payload: Callable[..., Dict[str, Any]],
    db: Session,
) -> WebhookResponse:
    incident_id = f"gl_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    logger.info(
        "gitlab_webhook_received",
        incident_id=incident_id,
        event_type=x_gitlab_event,
        user_id=user_id,
        body_length=len(body),
    )
    payload = parse_gitlab_webhook_payload(body=body, user_id=user_id, event_type=x_gitlab_event)
    object_kind = payload.get("object_kind")
    if object_kind == "pipeline":
        oauth_processed = await process_oauth_connected_pipeline_event(db=db, user_id=user_id, payload=payload)
        if oauth_processed:
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message="OAuth GitLab pipeline event processed successfully",
            )

    logger.info(
        "gitlab_webhook_acknowledged",
        incident_id=incident_id,
        event_type=x_gitlab_event,
        object_kind=object_kind,
        user_id=user_id,
    )
    return WebhookResponse(incident_id=incident_id, acknowledged=True, queued=False, message="GitLab event acknowledged")


async def receive_generic_webhook_impl(
    *,
    user_id: str,
    payload: Dict[str, Any],
    x_webhook_source: Optional[str],
    background_tasks: BackgroundTasks,
    event_processor: EventProcessor,
    process_webhook_sync: Callable[..., None],
) -> WebhookResponse:
    incident_id = f"gen_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    source_map = {
        "github": IncidentSource.GITHUB,
        "argocd": IncidentSource.ARGOCD,
        "kubernetes": IncidentSource.KUBERNETES,
        "k8s": IncidentSource.KUBERNETES,
        "gitlab": IncidentSource.GITLAB,
        "jenkins": IncidentSource.JENKINS,
    }
    source = source_map.get((x_webhook_source or "").lower(), IncidentSource.MANUAL)
    logger.info("generic_webhook_received", incident_id=incident_id, source=source.value, user_id=user_id)
    if not payload.get("error_log") and not payload.get("message"):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="Webhook acknowledged (no error_log provided)",
        )
    if not payload.get("error_log"):
        payload["error_log"] = payload.get("message", str(payload))
    payload.setdefault("context", {})["user_id"] = user_id
    background_tasks.add_task(
        process_webhook_sync,
        event_processor,
        payload,
        source,
        incident_id,
        user_id,
    )
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message="Generic webhook received, processing started",
    )
