# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status, Header
from fastapi.responses import JSONResponse
import structlog

from app.core.schemas.webhook import WebhookPayload, WebhookResponse

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
    description="Dedicated endpoint for GitHub webhook",
    tags=["Webhook"],
)
async def receive_github_webhook(
    request: Request,
    payload: Dict[str, Any],
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> WebhookResponse:
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"

    logger.info(
        "github_webhook_received",
        incident_id=incident_id,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
        has_signature=bool(x_hub_signature_256),
    )

    # TODO: Implement signature verification
    # if not verify_github_signature(payload, x_hub_signature_256):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    logger.debug(
        "github_webhook_payload",
        incident_id=incident_id,
        event_type=x_github_event,
        payload=payload,
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