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


def _verify_github_signature(body: bytes, signature: str, secret: str) -> bool:
    import hmac
    import hashlib
    
    if not signature or not secret:
        return False
    
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    if signature.startswith("sha256="):
        signature = signature[7:]
    
    return hmac.compare_digest(expected, signature)


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
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
    body = await request.body()
    
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
    
    if settings.github_webhook_secret:
        if not _verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            logger.error("github_webhook_invalid_signature", incident_id=incident_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
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
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
    body = await request.body()
    
    if x_github_event == "ping":
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="GitHub webhook ping received",
        )
    
    if settings.github_webhook_secret:
        if not _verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
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
        },
    }