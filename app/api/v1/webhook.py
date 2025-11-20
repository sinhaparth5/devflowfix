# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status, Header, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import structlog

from app.core.schemas.webhook import WebhookPayload, WebhookResponse
from app.core.config import settings
from app.core.enums import IncidentSource, Severity, FailureType, Fixability, Outcome
from app.adapters.external.github.webhooks import GitHubWebhookClient, WebhookSignatureError
from app.adapters.database.postgres.repositories.incident import IncidentRepository
from app.dependencies import get_db

logger = structlog.get_logger(__name__)

router = APIRouter()

@router.post(
    "/webhook",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Generic webhook endpoint",
    description="Accepts webhook event from external system",
    tags=["Webhook"],
)
async def receive_webhook(
    request: Request,
    payload: Dict[str, Any],
    x_webhook_source: str | None = Header(None, description="Webhook source identifier"),
    x_github_event: str | None = Header(None, description="GitHub event page"),
    x_signature: str | None = Header(None, description="GitHub signature"),
) -> WebhookResponse:
    """
    Receive and process webhook events.

    This endpoint accepts webhook from various source and logs them for processing.
    In production, this would trigger event processing pipelines.

    Args:
        request: FastAPI request object
        payload: JSON payload from webhook
        x_webhook_source: Optional source identifier
        x_github_event: GitHub-specific event type
        x_signatiure: Webhook signature for verification

    Returns:
        WebhookRespone with acknowledgement

    Raises:
        HTTPException: If payload is invalid or processing failed
    """
    incident_id = f"wh_{int(datetime.utcnow().timestamp() * 1000)}"

    source = x_webhook_source or "unknown"
    if x_github_event:
        source = "github"

    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "webhook_received",
        incident_id=incident_id,
        source=source,
        client_ip=client_ip,
        event_type=x_github_event,
        payload_size=len(str(payload)),
        headers={
            "x-webhook-source": x_webhook_source,
            "x-github-event": x_github_event,
            "x-signature": "***" if x_signature else None,
        },
    )

    logger.debug(
        "webhook_payload",
        incident_id=incident_id,
        source=source,
        payload=payload
    )

    # Validate payload is not empty
    if not payload:
        logger.warning(
            "webhook_empty_payload",
            incident_id=incident_id,
            source=source,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload cannot be empty",
        )
    
    # TODO: In production, features need to be added
    # Signature verification
    # Queue the event for async processing
    # Rate limiting per source
    # Deduplication
    # Schema validation based on source

    logger.info(
        "webhook_acknowledged",
        incident_id=incident_id,
        source=source,
    )

    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=False,
        message=f"Webhook received from {source}",
    )

@router.post(
    "/webhook/github",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint",
    description="Dedicated endpoint for GitHub webhooks with signature verification",
    tags=["Webhook"],
)
async def receive_github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events with HMAC-SHA256 signature verification.
    
    Args:
        request: FastAPI request object
        x_github_event: GitHub event type (e.g., 'ping', 'workflow_run', 'push')
        x_github_delivery: Unique delivery ID for this webhook
        x_hub_signature_256: HMAC-SHA256 signature for verification
        
    Returns:
        WebhookResponse with acknowledgement
        
    Raises:
        HTTPException: If signature verification fails or payload is invalid
    """
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
    
    # Get raw body for signature verification
    body = await request.body()
    
    logger.info(
        "github_webhook_received",
        incident_id=incident_id,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
        has_signature=bool(x_hub_signature_256),
        body_size=len(body),
    )
    
    # Special handling for ping event
    if x_github_event == "ping":
        logger.info(
            "github_webhook_ping",
            incident_id=incident_id,
            delivery_id=x_github_delivery,
        )
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="GitHub webhook ping received successfully"
        )
    
    # Verify signature if webhook secret is configured
    if settings.github_webhook_secret:
        try:
            webhook_client = GitHubWebhookClient(settings.github_webhook_secret)
            
            if not x_hub_signature_256:
                logger.error(
                    "github_webhook_missing_signature",
                    incident_id=incident_id,
                    event_type=x_github_event,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing X-Hub-Signature-256 header"
                )
            
            is_valid = webhook_client.verify_signature(body, x_hub_signature_256)
            
            if not is_valid:
                logger.error(
                    "github_webhook_invalid_signature",
                    incident_id=incident_id,
                    event_type=x_github_event,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
            
            logger.info(
                "github_webhook_signature_verified",
                incident_id=incident_id,
                event_type=x_github_event,
            )
            
        except WebhookSignatureError as e:
            logger.error(
                "github_webhook_signature_error",
                incident_id=incident_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )
    else:
        logger.warning(
            "github_webhook_secret_not_configured",
            incident_id=incident_id,
            message="Webhook secret not configured - skipping signature verification"
        )
    
    # Parse payload
    try:
        import json
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(
            "github_webhook_invalid_payload",
            incident_id=incident_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {e}"
        )
    
    logger.debug(
        "github_webhook_payload",
        incident_id=incident_id,
        event_type=x_github_event,
        payload=payload,
    )
    
    # Process workflow_run failures
    if x_github_event == "workflow_run":
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")
        status_value = workflow_run.get("status")
        
        # Check if it's a failure
        if status_value == "completed" and conclusion in ["failure", "timed_out", "action_required"]:
            logger.info(
                "github_workflow_failure_detected",
                incident_id=incident_id,
                workflow_name=workflow_run.get("name"),
                conclusion=conclusion,
            )
            
            # Extract failure details
            repository = payload.get("repository", {})
            repo_name = repository.get("full_name", "unknown")
            
            # Create incident in database
            try:
                incident_repo = IncidentRepository(db)
                
                # Build context
                context = {
                    "repository": repo_name,
                    "workflow_name": workflow_run.get("name"),
                    "workflow_id": workflow_run.get("workflow_id"),
                    "run_id": workflow_run.get("id"),
                    "run_number": workflow_run.get("run_number"),
                    "branch": workflow_run.get("head_branch"),
                    "commit_sha": workflow_run.get("head_sha"),
                    "commit_message": workflow_run.get("head_commit", {}).get("message"),
                    "author": workflow_run.get("head_commit", {}).get("author", {}).get("name"),
                    "html_url": workflow_run.get("html_url"),
                    "started_at": workflow_run.get("run_started_at"),
                    "completed_at": workflow_run.get("updated_at"),
                }
                
                # Determine severity based on branch
                branch = workflow_run.get("head_branch", "")
                if branch in ["main", "master", "production"]:
                    severity = Severity.CRITICAL
                elif branch in ["staging", "develop"]:
                    severity = Severity.HIGH
                else:
                    severity = Severity.MEDIUM
                
                # Build error log
                error_log = f"Workflow '{workflow_run.get('name')}' failed with conclusion: {conclusion}\n"
                error_log += f"Repository: {repo_name}\n"
                error_log += f"Branch: {branch}\n"
                error_log += f"Commit: {workflow_run.get('head_sha', '')[:8]}\n"
                error_log += f"URL: {workflow_run.get('html_url')}\n"
                
                # Create incident
                db_incident = incident_repo.create(
                    incident_id=incident_id,
                    timestamp=datetime.fromisoformat(workflow_run.get("run_started_at", datetime.utcnow().isoformat()).replace('Z', '+00:00')),
                    source=IncidentSource.GITHUB.value,
                    severity=severity.value,
                    failure_type=FailureType.BUILD_FAILURE.value if "build" in workflow_run.get("name", "").lower() else FailureType.TEST_FAILURE.value,
                    error_log=error_log,
                    error_message=f"Workflow failed: {conclusion}",
                    context=context,
                    fixability=Fixability.UNKNOWN.value,
                    raw_payload=payload,
                    tags=[f"repo:{repo_name}", f"branch:{branch}", f"workflow:{workflow_run.get('name')}"]
                )
                
                db.commit()
                
                logger.info(
                    "incident_created",
                    incident_id=incident_id,
                    repository=repo_name,
                    workflow=workflow_run.get("name"),
                    severity=severity.value,
                )
                
            except Exception as e:
                logger.error(
                    "incident_creation_failed",
                    incident_id=incident_id,
                    error=str(e),
                    exc_info=True,
                )
                # Don't fail the webhook - just log the error
                # db.rollback() will be handled by the dependency cleanup
    
    # TODO: Queue the event for async processing (analysis & remediation)
    
    logger.info(
        "github_webhook_processed",
        incident_id=incident_id,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
    )

    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=False,
        message=f"GitHub webhook received: {x_github_event}"
    )

@router.post(
    "/webhook/argocd",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="ArgoCD webhook endpoint",
    description="Dedicated enpoint for ArgoCD webhooks",
    tags=["Webhook"],
)
async def receive_argocd_webhook(
    request: Request,
    payload: Dict[str, Any],
) -> WebhookResponse:
    incident_id = f"argo_{int(datetime.utcnow().timestamp() * 1000)}"

    app_name = payload.get("application", {}).get("metadata", {}).get("name", "unknown")
    sync_status = payload.get("application", {}).get("status", {}).get("sync", {}).get("status", "unknown")

    logger.info(
        "argocd_webhook_received",
        incident_id=incident_id,
        application=app_name,
        sync_status=sync_status,
    )

    logger.debug(
        "argocd_webhook_payload",
        incident_id=incident_id,
        payload=payload
    )

    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=False,
        message=f"ArgoCD webhook received from {app_name}",
    )

@router.get(
    "/webhook/health",
    status_code=status.HTTP_200_OK,
    summary="Webhook endpoint health check",
    tags=["Webhook"],
)
async def webhook_health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "endpoint": "webhook",
        "timestamp": datetime.utcnow().isoformat(),
    }