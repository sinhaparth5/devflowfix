# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status, Header, Depends, BackgroundTasks
from sqlalchemy.orm import Session
import structlog
import secrets
import base64
import hmac
import hashlib

from app.core.schemas.webhook import WebhookPayload, WebhookResponse
from app.core.config import settings
from app.core.enums import IncidentSource
from app.services.event_processor import EventProcessor
from app.dependencies import get_db, get_event_processor

try:
    from app.api.v1.auth import get_current_active_user
except ImportError:
    async def get_current_active_user() -> dict:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication module not available"
        )

logger = structlog.get_logger(__name__)
router = APIRouter()


def generate_webhook_secret() -> str:
    """
    Generate a cryptographically secure random webhook secret.
    
    Returns:
        URL-safe base64-encoded 256-bit random string
    """
    random_bytes = secrets.token_bytes(32)
    secret = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return secret


def verify_github_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify GitHub webhook HMAC-SHA256 signature.
    """
    if not signature_header or not secret:
        logger.warning(
            "signature_verification_missing_data",
            has_signature=bool(signature_header),
            has_secret=bool(secret),
        )
        return False
    
    expected_signature = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    received_signature = signature_header
    if signature_header.startswith("sha256="):
        received_signature = signature_header[7:]
    
    is_valid = hmac.compare_digest(expected_signature, received_signature)
    
    logger.debug(
        "signature_verification_result",
        signature_match=is_valid,
        expected_prefix=expected_signature[:16] + "...",
        received_prefix=received_signature[:16] + "...",
    )
    
    return is_valid


async def verify_github_webhook_signature(
    user_id: str,
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
) -> bytes:
    """
    Path-based webhook authentication with user lookup.
    """
    body = await request.body()
    
    if not x_hub_signature_256:
        logger.error(
            "github_webhook_no_signature",
            user_id=user_id,
            body_length=len(body),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header. Configure webhook secret in GitHub repository settings.",
        )
    
    from app.adapters.database.postgres.repositories.users import UserRepository
    
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    
    if not user:
        logger.error(
            "github_webhook_user_not_found",
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )
    
    if not user.is_active:
        logger.error(
            "github_webhook_user_inactive",
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{user_id}' is not active.",
        )
    
    if not user.github_webhook_secret:
        logger.error(
            "github_webhook_no_secret_configured",
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No webhook secret configured for user '{user_id}'. Generate one using POST /api/v1/webhook/secret/generate",
        )
    
    is_valid = verify_github_signature(body, x_hub_signature_256, user.github_webhook_secret)
    
    if not is_valid:
        logger.error(
            "github_webhook_invalid_signature",
            user_id=user_id,
            signature_prefix=x_hub_signature_256[:20] if x_hub_signature_256 else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature. Signature does not match configured secret.",
        )
    
    logger.info(
        "github_webhook_authenticated",
        user_id=user_id,
        email=user.email,
    )
    
    return body


def is_github_failure_event(event_type: str, payload: Dict[str, Any]) -> bool:
    """
    Determine if GitHub webhook event represents a failure.
    """
    if event_type == "workflow_run":
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")
        status_value = workflow_run.get("status")
        return status_value == "completed" and conclusion in ["failure", "timed_out", "action_required"]
    
    if event_type == "check_run":
        conclusion = payload.get("check_run", {}).get("conclusion")
        return conclusion in ["failure", "timed_out"]
    
    return False


def is_argocd_failure_event(payload: Dict[str, Any]) -> bool:
    """
    Determine if ArgoCD webhook event represents a failure.
    """
    app_status = payload.get("application", {}).get("status", {})
    sync_status = app_status.get("sync", {}).get("status", "").lower()
    health_status = app_status.get("health", {}).get("status", "").lower()
    
    return sync_status in ["unknown", "outofsync"] or health_status in ["degraded", "missing", "unknown"]


def is_kubernetes_failure_event(payload: Dict[str, Any]) -> bool:
    """
    Determine if Kubernetes webhook event represents a failure.
    """
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


def extract_github_payload(payload: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    """
    Extract and normalize GitHub webhook payload.
    """
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
        
        error_log = (
            f"Workflow '{workflow_run.get('name')}' failed\n"
            f"Conclusion: {workflow_run.get('conclusion')}\n"
            f"Repository: {repository.get('full_name')}\n"
            f"Branch: {branch}\n"
            f"Commit: {workflow_run.get('head_sha', '')[:8]}\n"
            f"URL: {workflow_run.get('html_url')}"
        )
        
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


def extract_argocd_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize ArgoCD webhook payload.
    """
    app = payload.get("application", {})
    metadata = app.get("metadata", {})
    app_status = app.get("status", {})
    
    sync_status = app_status.get("sync", {}).get("status", "Unknown")
    health_status = app_status.get("health", {}).get("status", "Unknown")
    
    error_log = (
        f"ArgoCD Application '{metadata.get('name')}' unhealthy\n"
        f"Sync Status: {sync_status}\n"
        f"Health Status: {health_status}\n"
    )
    
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


def extract_kubernetes_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize Kubernetes webhook payload.
    """
    involved_object = payload.get("involvedObject", payload.get("involved_object", {}))
    
    reason = payload.get("reason", "Unknown")
    message = payload.get("message", "")
    
    if reason.lower() in ["oomkilled", "crashloopbackoff"]:
        severity = "critical"
    elif reason.lower() in ["backoff", "unhealthy", "failed"]:
        severity = "high"
    else:
        severity = "medium"
    
    error_log = (
        f"Kubernetes Event: {reason}\n"
        f"Message: {message}\n"
        f"Object: {involved_object.get('kind')}/{involved_object.get('name')}\n"
        f"Namespace: {involved_object.get('namespace')}"
    )
    
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
    "/webhook/github/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint",
    tags=["Webhook"],
)
async def receive_github_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(...),
    x_github_delivery: Optional[str] = Header(None),
    body: bytes = Depends(verify_github_webhook_signature),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events with path-based authentication.
    """
    incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
    
    logger.info(
        "github_webhook_received",
        incident_id=incident_id,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
        user_id=user_id,
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
        logger.error(
            "github_webhook_invalid_json",
            user_id=user_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {e}",
        )
    
    if not is_github_failure_event(x_github_event, payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Event {x_github_event} acknowledged (not a failure)",
        )
    
    normalized_payload = extract_github_payload(payload, x_github_event)
    normalized_payload["raw_payload"] = payload
    normalized_payload["user_id"] = user_id
    
    background_tasks.add_task(
        process_webhook_async,
        event_processor,
        normalized_payload,
        IncidentSource.GITHUB,
        incident_id,
        user_id,
    )
    
    logger.info(
        "github_webhook_queued",
        incident_id=incident_id,
        event_type=x_github_event,
        user_id=user_id,
    )
    
    return WebhookResponse(
        incident_id=incident_id,
        acknowledged=True,
        queued=True,
        message="GitHub failure detected, processing started",
    )


@router.post(
    "/webhook/github/{user_id}/sync",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint (synchronous)",
    tags=["Webhook"],
)
async def receive_github_webhook_sync(
    user_id: str,
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: Optional[str] = Header(None),
    body: bytes = Depends(verify_github_webhook_signature),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events synchronously.
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
    
    if not is_github_failure_event(x_github_event, payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message=f"Event {x_github_event} acknowledged (not a failure)",
        )
    
    normalized_payload = extract_github_payload(payload, x_github_event)
    normalized_payload["raw_payload"] = payload
    normalized_payload["user_id"] = user_id
    
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
    "/webhook/argocd/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="ArgoCD webhook endpoint",
    tags=["Webhook"],
)
async def receive_argocd_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive ArgoCD webhook events with path-based user identification.
    """
    incident_id = f"argo_{int(datetime.utcnow().timestamp() * 1000)}"
    
    app_name = payload.get("application", {}).get("metadata", {}).get("name", "unknown")
    
    logger.info(
        "argocd_webhook_received",
        incident_id=incident_id,
        application=app_name,
        user_id=user_id,
    )
    
    if not is_argocd_failure_event(payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="ArgoCD event acknowledged (not a failure)",
        )
    
    normalized_payload = extract_argocd_payload(payload)
    normalized_payload["raw_payload"] = payload
    normalized_payload["user_id"] = user_id
    
    background_tasks.add_task(
        process_webhook_async,
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


@router.post(
    "/webhook/kubernetes/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Kubernetes event webhook endpoint",
    tags=["Webhook"],
)
async def receive_kubernetes_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive Kubernetes webhook events with path-based user identification.
    """
    incident_id = f"k8s_{int(datetime.utcnow().timestamp() * 1000)}"
    
    reason = payload.get("reason", "Unknown")
    
    logger.info(
        "kubernetes_webhook_received",
        incident_id=incident_id,
        reason=reason,
        user_id=user_id,
    )
    
    if not is_kubernetes_failure_event(payload):
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=False,
            message="Kubernetes event acknowledged (not a failure)",
        )
    
    normalized_payload = extract_kubernetes_payload(payload)
    normalized_payload["raw_payload"] = payload
    normalized_payload["user_id"] = user_id
    
    background_tasks.add_task(
        process_webhook_async,
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


@router.post(
    "/webhook/generic/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Generic webhook endpoint",
    tags=["Webhook"],
)
async def receive_generic_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    x_webhook_source: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive generic webhook events with path-based user identification.
    """
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
        user_id=user_id,
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
    
    payload["user_id"] = user_id
    
    background_tasks.add_task(
        process_webhook_async,
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


async def process_webhook_async(
    event_processor: EventProcessor,
    payload: Dict[str, Any],
    source: IncidentSource,
    incident_id: str,
    user_id: str,
) -> None:
    """
    Process webhook event asynchronously.
    """
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
            user_id=user_id,
        )
        
    except Exception as e:
        logger.error(
            "webhook_processing_failed",
            incident_id=incident_id,
            user_id=user_id,
            error=str(e),
            exc_info=True,
        )


@router.post(
    "/webhook/secret/generate/me",
    status_code=status.HTTP_201_CREATED,
    summary="Generate webhook secret for authenticated user",
    tags=["Webhook", "Security"],
)
async def generate_my_webhook_secret(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Generate new webhook secret for authenticated user with complete GitHub setup instructions.
    """
    user = current_user_data["user"]
    
    new_secret = generate_webhook_secret()
    
    user.github_webhook_secret = new_secret
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    logger.info(
        "webhook_secret_generated_for_authenticated_user",
        user_id=user.user_id,
        email=user.email,
        secret_length=len(new_secret),
    )
    
    base_url = settings.api_url if hasattr(settings, 'api_url') else "https://devflowfix-new-production.up.railway.app"
    webhook_url = f"{base_url}/api/v1/webhook/github/{user.user_id}"
    
    return {
        "success": True,
        "message": "Webhook secret generated successfully",
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "full_name": user.full_name,
        },
        "webhook_secret": new_secret,
        "webhook_url": webhook_url,
        "secret_length": len(new_secret),
        "algorithm": "HMAC-SHA256",
        "created_at": datetime.utcnow().isoformat(),
        "github_configuration": {
            "payload_url": webhook_url,
            "content_type": "application/json",
            "secret": new_secret,
            "ssl_verification": "Enable SSL verification",
            "events": ["workflow_run", "check_run"],
            "active": True,
        },
        "setup_instructions": {
            "step_1": {
                "action": "Copy your webhook secret",
                "value": new_secret,
                "note": "Save this secret now - it will not be shown again",
            },
            "step_2": {
                "action": "Go to your GitHub repository",
                "url": "https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks",
            },
            "step_3": {
                "action": "Click 'Add webhook'",
            },
            "step_4": {
                "action": "Configure webhook settings",
                "payload_url": webhook_url,
                "content_type": "application/json",
                "secret": new_secret,
            },
            "step_5": {
                "action": "Select events",
                "individual_events": [
                    "Workflow runs",
                    "Check runs"
                ],
                "note": "Uncheck 'Just the push event' and select individual events",
            },
            "step_6": {
                "action": "Ensure 'Active' is checked",
            },
            "step_7": {
                "action": "Click 'Add webhook'",
            },
        },
        "test_configuration": {
            "description": "Test your webhook configuration",
            "curl_command": f'''curl -X POST "{webhook_url}" \\
  -H "Content-Type: application/json" \\
  -H "X-Hub-Signature-256: sha256=<signature>" \\
  -H "X-GitHub-Event: workflow_run" \\
  -d '{{"action":"completed","workflow_run":{{"conclusion":"failure"}}}}'
''',
            "generate_test_signature": f"{base_url}/api/v1/webhook/secret/test/me",
        },
    }


@router.post(
    "/webhook/secret/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generate webhook secret (admin)",
    tags=["Webhook", "Security", "Admin"],
)
async def create_webhook_secret(
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate new webhook secret for specific user (admin endpoint).
    """
    from app.adapters.database.postgres.repositories.users import UserRepository
    
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )
    
    new_secret = generate_webhook_secret()
    
    user.github_webhook_secret = new_secret
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    logger.info(
        "webhook_secret_generated_admin",
        user_id=user_id,
        secret_length=len(new_secret),
    )
    
    base_url = settings.api_url if hasattr(settings, 'api_url') else "https://devflowfix-new-production.up.railway.app"
    webhook_url = f"{base_url}/api/v1/webhook/github/{user_id}"
    
    return {
        "success": True,
        "user_id": user_id,
        "webhook_secret": new_secret,
        "webhook_url": webhook_url,
        "secret_length": len(new_secret),
        "algorithm": "HMAC-SHA256",
        "created_at": datetime.utcnow().isoformat(),
        "instructions": {
            "step_1": "Save this secret now - it will not be shown again",
            "step_2": f"Copy the webhook_secret value: {new_secret}",
            "step_3": "Go to GitHub repository Settings > Webhooks",
            "step_4": f"Set Payload URL to: {webhook_url}",
            "step_5": "Set Content type to: application/json",
            "step_6": "Paste the secret in Secret field",
            "step_7": "Select events: workflow_run, check_run",
            "step_8": "Save webhook configuration",
        },
    }


@router.get(
    "/webhook/secret/info/me",
    status_code=status.HTTP_200_OK,
    summary="Get my webhook configuration",
    tags=["Webhook", "Security"],
)
async def get_my_webhook_info(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Get webhook configuration for authenticated user.
    """
    user = current_user_data["user"]
    
    has_secret = bool(user.github_webhook_secret)
    secret_preview = None
    
    if has_secret and user.github_webhook_secret:
        secret = user.github_webhook_secret
        if len(secret) > 8:
            secret_preview = f"{secret[:4]}...{secret[-4:]}"
        else:
            secret_preview = "****"
    
    base_url = settings.api_url if hasattr(settings, 'api_url') else "https://devflowfix-new-production.up.railway.app"
    webhook_url = f"{base_url}/api/v1/webhook/github/{user.user_id}"
    
    return {
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "full_name": user.full_name,
        },
        "webhook_configuration": {
            "secret_configured": has_secret,
            "secret_preview": secret_preview,
            "secret_length": len(user.github_webhook_secret) if has_secret else 0,
            "webhook_url": webhook_url,
            "last_updated": user.updated_at.isoformat() if user.updated_at else None,
        },
        "github_settings": {
            "payload_url": webhook_url,
            "content_type": "application/json",
            "events": ["workflow_run", "check_run"],
            "ssl_verification": "enabled",
        },
        "status": {
            "ready": has_secret,
            "message": "Webhook configured and ready" if has_secret else "No webhook secret configured - generate one first",
        },
        "actions": {
            "generate_new_secret": f"{base_url}/api/v1/webhook/secret/generate/me",
            "test_signature": f"{base_url}/api/v1/webhook/secret/test/me",
            "webhook_endpoint": webhook_url,
        },
    }


@router.get(
    "/webhook/secret/info",
    status_code=status.HTTP_200_OK,
    summary="Get webhook secret information (admin)",
    tags=["Webhook", "Security", "Admin"],
)
async def get_webhook_secret_info(
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get webhook secret configuration information for specific user.
    """
    from app.adapters.database.postgres.repositories.users import UserRepository
    
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )
    
    has_secret = bool(user.github_webhook_secret)
    secret_preview = None
    
    if has_secret and user.github_webhook_secret:
        secret = user.github_webhook_secret
        if len(secret) > 8:
            secret_preview = f"{secret[:4]}...{secret[-4:]}"
        else:
            secret_preview = "****"
    
    base_url = settings.api_url if hasattr(settings, 'api_url') else "https://devflowfix-new-production.up.railway.app"
    webhook_url = f"{base_url}/api/v1/webhook/github/{user_id}"
    
    return {
        "user_id": user_id,
        "secret_configured": has_secret,
        "secret_preview": secret_preview,
        "secret_length": len(user.github_webhook_secret) if has_secret else 0,
        "webhook_url": webhook_url,
        "last_updated": user.updated_at.isoformat() if user.updated_at else None,
        "actions": {
            "generate_new": f"{base_url}/api/v1/webhook/secret/generate?user_id={user_id}",
            "test_signature": f"{base_url}/api/v1/webhook/secret/test?user_id={user_id}",
        },
    }


@router.post(
    "/webhook/secret/test/me",
    status_code=status.HTTP_200_OK,
    summary="Test my webhook signature",
    tags=["Webhook", "Security"],
)
async def test_my_webhook_signature(
    request: Request,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Generate test signature for webhook payload using authenticated user's secret.
    """
    user = current_user_data["user"]
    
    if not user.github_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No webhook secret configured. Generate one using POST /api/v1/webhook/secret/generate/me",
        )
    
    body = await request.body()
    
    signature = hmac.new(
        user.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    payload_hash = hashlib.sha256(body).hexdigest()
    
    logger.info(
        "webhook_test_signature_generated_authenticated",
        user_id=user.user_id,
        payload_size=len(body),
        signature_prefix=signature[:16] + "...",
    )
    
    base_url = settings.api_url if hasattr(settings, 'api_url') else "https://devflowfix-new-production.up.railway.app"
    webhook_url = f"{base_url}/api/v1/webhook/github/{user.user_id}"
    
    return {
        "success": True,
        "user": {
            "user_id": user.user_id,
            "email": user.email,
        },
        "test_results": {
            "payload_hash": payload_hash,
            "signature": signature,
            "full_header_value": f"sha256={signature}",
            "payload_size_bytes": len(body),
        },
        "webhook_url": webhook_url,
        "how_to_use": {
            "description": "Use this signature to test your webhook endpoint",
            "header_name": "X-Hub-Signature-256",
            "header_value": f"sha256={signature}",
            "curl_example": f'''curl -X POST "{webhook_url}" \\
  -H "Content-Type: application/json" \\
  -H "X-Hub-Signature-256: sha256={signature}" \\
  -H "X-GitHub-Event: workflow_run" \\
  -H "X-GitHub-Delivery: test-{int(datetime.utcnow().timestamp())}" \\
  --data '@payload.json' ''',
        },
        "verification": {
            "algorithm": "HMAC-SHA256",
            "encoding": "hexadecimal",
            "constant_time_comparison": True,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post(
    "/webhook/secret/test",
    status_code=status.HTTP_200_OK,
    summary="Test webhook signature (admin)",
    tags=["Webhook", "Security", "Admin"],
)
async def test_webhook_signature(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate test signature for webhook payload using specific user's secret.
    """
    from app.adapters.database.postgres.repositories.users import UserRepository
    
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )
    
    if not user.github_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No webhook secret configured for user '{user_id}'",
        )
    
    body = await request.body()
    
    signature = hmac.new(
        user.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    payload_hash = hashlib.sha256(body).hexdigest()
    
    logger.info(
        "webhook_test_signature_generated_admin",
        user_id=user_id,
        payload_size=len(body),
        signature_prefix=signature[:16] + "...",
    )
    
    base_url = settings.api_url if hasattr(settings, 'api_url') else "https://devflowfix-new-production.up.railway.app"
    webhook_url = f"{base_url}/api/v1/webhook/github/{user_id}"
    
    return {
        "success": True,
        "user_id": user_id,
        "payload_hash": payload_hash,
        "signature": signature,
        "full_header": f"sha256={signature}",
        "payload_size": len(body),
        "webhook_url": webhook_url,
        "usage": {
            "header_name": "X-Hub-Signature-256",
            "header_value": f"sha256={signature}",
            "example_curl": f'''curl -X POST "{webhook_url}" \\
  -H "Content-Type: application/json" \\
  -H "X-Hub-Signature-256: sha256={signature}" \\
  -H "X-GitHub-Event: workflow_run" \\
  --data '@payload.json' ''',
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get(
    "/webhook/health",
    status_code=status.HTTP_200_OK,
    summary="Webhook health check",
    tags=["Webhook"],
)
async def webhook_health() -> Dict[str, Any]:
    """
    Health check endpoint for webhook service.
    """
    return {
        "status": "healthy",
        "endpoint": "webhook",
        "timestamp": datetime.utcnow().isoformat(),
        "features": {
            "github": True,
            "argocd": True,
            "kubernetes": True,
            "generic": True,
            "signature_verification": True,
        },
        "endpoints": {
            "github": "/webhook/github/{user_id}",
            "argocd": "/webhook/argocd/{user_id}",
            "kubernetes": "/webhook/kubernetes/{user_id}",
            "generic": "/webhook/generic/{user_id}",
        },
    }
