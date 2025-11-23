# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status, Header, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import structlog

from app.core.schemas.webhook import WebhookPayload, WebhookResponse
from app.core.config import settings
from app.core.enums import IncidentSource, Severity, FailureType
from app.services.event_processor import EventProcessor
from app.dependencies import get_db, get_event_processor

logger = structlog.get_logger(__name__)

router = APIRouter()


async def verify_github_webhook_signature(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
) -> bytes:
    """
    Verify GitHub webhook signature before processing.
    This dependency runs before database session creation to avoid false database errors.
    
    Returns the request body if signature is valid.
    Raises HTTPException if signature is invalid.
    """
    body = await request.body()
    
    # Convert header to string if needed
    signature_header = str(x_hub_signature_256) if x_hub_signature_256 else None
    
    if settings.github_webhook_secret:
        if not _verify_github_signature(body, signature_header, settings.github_webhook_secret):
            logger.error(
                "github_webhook_invalid_signature",
                has_signature=bool(signature_header),
                signature_prefix=signature_header[:20] if signature_header else None,
                body_length=len(body),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )
    
    return body


def _verify_github_signature(body: bytes, signature: str, secret: str) -> bool:
    import hmac
    import hashlib
    
    # Convert signature to string if it's not already
    if signature is not None:
        signature = str(signature)
    
    if not signature or not secret:
        logger.warning(
            "github_signature_verification_missing_data",
            has_signature=bool(signature),
            has_secret=bool(secret),
        )
        return False
    
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    received_signature = signature
    if signature.startswith("sha256="):
        received_signature = signature[7:]
    
    logger.info(
        "github_signature_verification",
        received_signature=received_signature[:16] + "...",
        expected_signature=expected[:16] + "...",
        signature_match=hmac.compare_digest(expected, received_signature),
    )
    
    return hmac.compare_digest(expected, received_signature)


def _is_github_failure_event(event_type: str, payload: Dict[str, Any]) -> bool:
    if event_type == "workflow_run":
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")
        status_value = workflow_run.get("status")
        return status_value == "completed" and conclusion in ["failure", "timed_out", "action_required"]
    
    if event_type == "check_run":
        conclusion = payload.get("check_run", {}).get("conclusion")
        return conclusion in ["failure", "timed_out"]
    
    return False


def _is_argocd_failure_event(payload: Dict[str, Any]) -> bool:
    app_status = payload.get("application", {}).get("status", {})
    sync_status = app_status.get("sync", {}).get("status", "").lower()
    health_status = app_status.get("health", {}).get("status", "").lower()
    
    return sync_status in ["unknown", "outofsync"] or health_status in ["degraded", "missing", "unknown"]


def _is_kubernetes_failure_event(payload: Dict[str, Any]) -> bool:
    event_type = payload.get("type", "").lower()
    reason = payload.get("reason", "").lower()
    
    failure_reasons = [
        "backoff", "failed", "unhealthy", "evicted",
        "oomkilled", "crashloopbackoff", "imagepullbackoff",
        "error", "killing",
    ]
    
    if event_type == "warning":
        return True
    
    return any(r in reason for r in failure_reasons)


def _extract_github_payload(payload: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    if event_type == "workflow_run":
        workflow_run = payload.get("workflow_run", {})
        repository = payload.get("repository", {})
        
        branch = workflow_run.get("head_branch", "")
        if branch in ["main", "master", "production"]:
            severity = "critical"
        elif branch in ["staging", "develop"]:
            severity = "high"
        else:
            severity = "medium"
        
        error_log = f"Workflow '{workflow_run.get('name')}' failed\n"
        error_log += f"Conclusion: {workflow_run.get('conclusion')}\n"
        error_log += f"Repository: {repository.get('full_name')}\n"
        error_log += f"Branch: {branch}\n"
        error_log += f"Commit: {workflow_run.get('head_sha', '')[:8]}\n"
        error_log += f"URL: {workflow_run.get('html_url')}"
        
        return {
            "severity": severity,
            "error_log": error_log,
            "error_message": f"Workflow failed: {workflow_run.get('conclusion')}",
            "context": {
                "repository": repository.get("full_name"),
                "workflow": workflow_run.get("name"),
                "workflow_id": workflow_run.get("workflow_id"),
                "run_id": workflow_run.get("id"),
                "run_number": workflow_run.get("run_number"),
                "branch": branch,
                "commit_sha": workflow_run.get("head_sha"),
                "html_url": workflow_run.get("html_url"),
            },
        }
    
    return payload


def _extract_argocd_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    app = payload.get("application", {})
    metadata = app.get("metadata", {})
    app_status = app.get("status", {})
    
    sync_status = app_status.get("sync", {}).get("status", "Unknown")
    health_status = app_status.get("health", {}).get("status", "Unknown")
    
    error_log = f"ArgoCD Application '{metadata.get('name')}' unhealthy\n"
    error_log += f"Sync Status: {sync_status}\n"
    error_log += f"Health Status: {health_status}\n"
    
    conditions = app_status.get("conditions", [])
    for condition in conditions:
        error_log += f"Condition: {condition.get('type')} - {condition.get('message', '')}\n"
    
    return {
        "severity": "high" if health_status.lower() == "degraded" else "medium",
        "error_log": error_log,
        "error_message": f"ArgoCD sync failed: {sync_status}",
        "context": {
            "application": metadata.get("name"),
            "namespace": metadata.get("namespace"),
            "sync_status": sync_status,
            "health_status": health_status,
            "revision": app_status.get("sync", {}).get("revision"),
        },
    }


def _extract_kubernetes_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    involved_object = payload.get("involvedObject", payload.get("involved_object", {}))
    
    reason = payload.get("reason", "Unknown")
    message = payload.get("message", "")
    
    if reason.lower() in ["oomkilled", "crashloopbackoff"]:
        severity = "critical"
    elif reason.lower() in ["backoff", "unhealthy", "failed"]:
        severity = "high"
    else:
        severity = "medium"
    
    error_log = f"Kubernetes Event: {reason}\n"
    error_log += f"Message: {message}\n"
    error_log += f"Object: {involved_object.get('kind')}/{involved_object.get('name')}\n"
    error_log += f"Namespace: {involved_object.get('namespace')}"
    
    return {
        "severity": severity,
        "error_log": error_log,
        "error_message": message,
        "context": {
            "namespace": involved_object.get("namespace"),
            "pod": involved_object.get("name") if involved_object.get("kind") == "Pod" else None,
            "kind": involved_object.get("kind"),
            "reason": reason,
        },
    }


@router.post(
    "/webhook/github",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint",
    tags=["Webhook"],
)
async def receive_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(...),
    x_github_delivery: Optional[str] = Header(None),
    body: bytes = Depends(verify_github_webhook_signature),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events.
    
    Signature verification happens via the verify_github_webhook_signature dependency
    BEFORE the database session is created, preventing false database_session_error logs.
    """
    
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
    
    logger.info(
        "github_webhook_received",
        incident_id=incident_id,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
    )
    
    if x_github_event == "ping":
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="GitHub webhook ping received",
        )
    
    try:
        import json
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {e}",
        )
    
    if not _is_github_failure_event(x_github_event, payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Event {x_github_event} acknowledged (not a failure)",
        )
    
    normalized_payload = _extract_github_payload(payload, x_github_event)
    normalized_payload["raw_payload"] = payload
    
    background_tasks.add_task(
        _process_webhook_async,
        event_processor,
        normalized_payload,
        IncidentSource.GITHUB,
        incident_id,
    )
    
    logger.info(
        "github_webhook_queued",
        incident_id=incident_id,
        event_type=x_github_event,
    )
    
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message=f"GitHub failure detected, processing started",
    )


@router.post(
    "/webhook/github/sync",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint (synchronous)",
    tags=["Webhook"],
)
async def receive_github_webhook_sync(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: Optional[str] = Header(None),
    body: bytes = Depends(verify_github_webhook_signature),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events synchronously.
    
    Signature verification happens via dependency before database session creation.
    """
    
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
    
    if x_github_event == "ping":
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="GitHub webhook ping received",
        )
    
    try:
        import json
        payload = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {e}",
        )
    
    if not _is_github_failure_event(x_github_event, payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Event {x_github_event} acknowledged (not a failure)",
        )
    
    normalized_payload = _extract_github_payload(payload, x_github_event)
    normalized_payload["raw_payload"] = payload
    
    result = await event_processor.process(
        payload=normalized_payload,
        source=IncidentSource.GITHUB,
    )
    
    return WebhookResponse(
        incident_id=result.incident_id,
        acknowledged=True,
        queued=False,
        message=result.message,
    )


@router.post(
    "/webhook/argocd",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="ArgoCD webhook endpoint",
    tags=["Webhook"],
)
async def receive_argocd_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    
    incident_id = f"argo_{int(datetime.utcnow().timestamp() * 1000)}"
    
    app_name = payload.get("application", {}).get("metadata", {}).get("name", "unknown")
    
    logger.info(
        "argocd_webhook_received",
        incident_id=incident_id,
        application=app_name,
    )
    
    if not _is_argocd_failure_event(payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"ArgoCD event acknowledged (not a failure)",
        )
    
    normalized_payload = _extract_argocd_payload(payload)
    normalized_payload["raw_payload"] = payload
    
    background_tasks.add_task(
        _process_webhook_async,
        event_processor,
        normalized_payload,
        IncidentSource.ARGOCD,
        incident_id,
    )
    
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message=f"ArgoCD failure detected for {app_name}, processing started",
    )


@router.post(
    "/webhook/kubernetes",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Kubernetes event webhook endpoint",
    tags=["Webhook"],
)
async def receive_kubernetes_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    
    incident_id = f"k8s_{int(datetime.utcnow().timestamp() * 1000)}"
    
    reason = payload.get("reason", "Unknown")
    
    logger.info(
        "kubernetes_webhook_received",
        incident_id=incident_id,
        reason=reason,
    )
    
    if not _is_kubernetes_failure_event(payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Kubernetes event acknowledged (not a failure)",
        )
    
    normalized_payload = _extract_kubernetes_payload(payload)
    normalized_payload["raw_payload"] = payload
    
    background_tasks.add_task(
        _process_webhook_async,
        event_processor,
        normalized_payload,
        IncidentSource.KUBERNETES,
        incident_id,
    )
    
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message=f"Kubernetes failure detected ({reason}), processing started",
    )


@router.post(
    "/webhook/generic",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Generic webhook endpoint",
    tags=["Webhook"],
)
async def receive_generic_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    x_webhook_source: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    
    incident_id = f"gen_{int(datetime.utcnow().timestamp() * 1000)}"
    
    source_map = {
        "github": IncidentSource.GITHUB,
        "argocd": IncidentSource.ARGOCD,
        "kubernetes": IncidentSource.KUBERNETES,
        "k8s": IncidentSource.KUBERNETES,
        "gitlab": IncidentSource.GITLAB,
        "jenkins": IncidentSource.JENKINS,
    }
    
    source = source_map.get((x_webhook_source or "").lower(), IncidentSource.MANUAL)
    
    logger.info(
        "generic_webhook_received",
        incident_id=incident_id,
        source=source.value,
    )
    
    if not payload.get("error_log") and not payload.get("message"):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="Webhook acknowledged (no error_log provided)",
        )
    
    if not payload.get("error_log"):
        payload["error_log"] = payload.get("message", str(payload))
    
    background_tasks.add_task(
        _process_webhook_async,
        event_processor,
        payload,
        source,
        incident_id,
    )
    
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message=f"Generic webhook received, processing started",
    )


async def _process_webhook_async(
    event_processor: EventProcessor,
    payload: Dict[str, Any],
    source: IncidentSource,
    incident_id: str,
):
    try:
        result = await event_processor.process(
            payload=payload,
            source=source,
        )
        
        logger.info(
            "webhook_processing_complete",
            incident_id=result.incident_id,
            success=result.success,
            outcome=result.outcome.value,
        )
        
    except Exception as e:
        logger.error(
            "webhook_processing_failed",
            incident_id=incident_id,
            error=str(e),
            exc_info=True,
        )


@router.post(
    "/webhook/generate-signature",
    status_code=status.HTTP_200_OK,
    summary="Generate GitHub webhook signature",
    description="Generate HMAC-SHA256 signature for webhook payload validation and testing",
    tags=["Webhook"],
)
async def generate_webhook_signature(
    request: Request,
) -> Dict[str, Any]:
    """
    Generate a GitHub webhook signature for the provided payload.
    
    This endpoint helps you:
    - Test webhook integration locally
    - Verify signature generation is working correctly
    - Debug signature validation issues
    
    The signature is computed using HMAC-SHA256 with your configured webhook secret.
    
    Example usage:
    ```bash
    curl -X POST http://localhost:8000/api/v1/webhook/generate-signature \\
      -H "Content-Type: application/json" \\
      -d '{"action": "completed", "workflow_run": {...}}'
    ```
    
    Returns:
    - payload_hash: SHA256 hash of the payload
    - signature: HMAC-SHA256 signature (without sha256= prefix)
    - full_header: Complete X-Hub-Signature-256 header value
    - payload_size: Size of the payload in bytes
    """
    import hmac
    import hashlib
    
    body = await request.body()
    
    if not settings.github_webhook_secret:
        logger.warning("generate_signature_no_secret_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook secret not configured. Set GITHUB_WEBHOOK_SECRET environment variable.",
        )
    
    # Compute signature
    signature = hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    # Compute payload hash for reference
    payload_hash = hashlib.sha256(body).hexdigest()
    
    logger.info(
        "webhook_signature_generated",
        payload_size=len(body),
        signature_prefix=signature[:16] + "...",
    )
    
    return {
        "success": True,
        "payload_hash": payload_hash,
        "signature": signature,
        "full_header": f"sha256={signature}",
        "payload_size": len(body),
        "secret_configured": True,
        "usage": {
            "header_name": "X-Hub-Signature-256",
            "header_value": f"sha256={signature}",
            "example": f'curl -H "X-Hub-Signature-256: sha256={signature}" ...',
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get(
    "/webhook/signature-info",
    status_code=status.HTTP_200_OK,
    summary="Get webhook signature configuration info",
    description="Get information about webhook signature configuration and how to generate signatures",
    tags=["Webhook"],
)
async def get_signature_info() -> Dict[str, Any]:
    """
    Get information about webhook signature configuration.
    
    Returns details about:
    - Whether webhook secret is configured
    - How to generate signatures
    - Example payload and signature generation
    """
    import hmac
    import hashlib
    import json
    
    has_secret = bool(settings.github_webhook_secret)
    
    # Example payload
    example_payload = {
        "action": "completed",
        "workflow_run": {
            "id": 123456,
            "name": "CI",
            "conclusion": "failure",
            "head_branch": "main",
        }
    }
    
    example_payload_json = json.dumps(example_payload, separators=(',', ':'))
    example_signature = None
    
    if has_secret:
        example_signature = hmac.new(
            settings.github_webhook_secret.encode(),
            example_payload_json.encode(),
            hashlib.sha256,
        ).hexdigest()
    
    return {
        "secret_configured": has_secret,
        "secret_length": len(settings.github_webhook_secret) if has_secret else 0,
        "algorithm": "HMAC-SHA256",
        "header_name": "X-Hub-Signature-256",
        "header_format": "sha256=<signature>",
        "example": {
            "payload": example_payload,
            "payload_json": example_payload_json,
            "signature": example_signature if has_secret else "SECRET_NOT_CONFIGURED",
            "full_header": f"sha256={example_signature}" if has_secret else "sha256=SECRET_NOT_CONFIGURED",
        },
        "endpoints": {
            "generate": "/api/v1/webhook/generate-signature (POST with JSON body)",
            "verify": "/api/v1/webhook/github (POST with X-Hub-Signature-256 header)",
        },
        "usage_instructions": {
            "step_1": "POST your JSON payload to /api/v1/webhook/generate-signature",
            "step_2": "Copy the 'full_header' value from the response",
            "step_3": "Use it as X-Hub-Signature-256 header when calling /api/v1/webhook/github",
            "step_4": "Check logs for 'github_signature_verification' to see validation details",
        },
    }


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
        "features": {
            "github": True,
            "argocd": True,
            "kubernetes": True,
            "generic": True,
            "signature_generator": True,
        },
    }