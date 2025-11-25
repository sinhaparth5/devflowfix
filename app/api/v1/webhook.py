# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status, Header, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import structlog
import secrets
import base64

from app.core.schemas.webhook import WebhookPayload, WebhookResponse
from app.core.config import settings
from app.core.enums import IncidentSource, Severity, FailureType
from app.services.event_processor import EventProcessor
from app.dependencies import get_db, get_event_processor

logger = structlog.get_logger(__name__)

router = APIRouter()


def generate_webhook_secret() -> str:
    """
    Generate a cryptographically secure random webhook secret.
    
    Returns a URL-safe base64-encoded string (43 characters).
    Similar to: 1zCC4or5bOkGQJYBi8uRUcJVpxvWS3nAoTJ0hYb7RoI
    """
    random_bytes = secrets.token_bytes(32)  # 32 bytes = 256 bits
    secret = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return secret


async def verify_github_webhook_signature(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
) -> tuple[bytes, Optional[str]]:
    """
    Verify GitHub webhook signature and identify user.
    
    Works like email/password authentication:
    1. GitHub sends webhook with signature in X-Hub-Signature-256 header
    2. We try to verify the signature against ALL user secrets in database
    3. If signature matches any user's secret, that user is authenticated
    4. Returns (request body, user_id) if authenticated
    
    This is secure because:
    - The webhook secret is cryptographically random (256 bits)
    - Signature uses HMAC-SHA256 (impossible to forge without secret)
    - Each user has unique secret
    - Secret lookup identifies the user (like password identifies user)
    
    Raises HTTPException if signature is invalid or no matching user found.
    """
    body = await request.body()
    signature_header = str(x_hub_signature_256) if x_hub_signature_256 else None
    
    if not signature_header:
        logger.error(
            "github_webhook_no_signature",
            body_length=len(body),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header. Please configure webhook secret in your GitHub repository settings.",
        )
    
    from app.adapters.database.postgres.repositories.users import UserRepository
    user_repo = UserRepository(db)
    
    from sqlalchemy import select, and_
    from app.adapters.database.postgres.models import UserTable
    
    stmt = select(UserTable).where(
        and_(
            UserTable.github_webhook_secret.isnot(None),
            UserTable.is_active == True
        )
    )
    result = db.execute(stmt)
    users_with_secrets = result.scalars().all()
    
    if not users_with_secrets:
        logger.error(
            "github_webhook_no_users_configured",
            has_signature=bool(signature_header),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No users have configured webhook secrets. Please generate a secret first using POST /api/v1/webhook/secret/generate",
        )
    
    # Try to verify signature against each user's secret (like trying passwords)
    authenticated_user = None
    for user in users_with_secrets:
        if _verify_github_signature(body, signature_header, user.github_webhook_secret):
            authenticated_user = user
            break
    
    if not authenticated_user:
        logger.error(
            "github_webhook_invalid_signature",
            has_signature=bool(signature_header),
            signature_prefix=signature_header[:20] if signature_header else None,
            body_length=len(body),
            users_checked=len(users_with_secrets),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature. The signature does not match any configured user webhook secret.",
        )
    
    logger.info(
        "github_webhook_authenticated",
        user_id=authenticated_user.user_id,
        email=authenticated_user.email,
        signature_verified=True,
    )
    
    return body, authenticated_user.user_id


def _verify_github_signature(body: bytes, signature: str, secret: str) -> bool:
    import hmac
    import hashlib
    
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
    verified_data: tuple[bytes, Optional[str]] = Depends(verify_github_webhook_signature),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events.
    
    Authentication Flow (like email/password login):
    1. GitHub sends webhook with payload + signature in X-Hub-Signature-256 header
    2. System verifies signature against all user webhook secrets in database
    3. Matching secret identifies and authenticates the user automatically
    4. No user_id header needed - the secret IS the authentication
    
    Security: Each user has a unique cryptographic secret (256-bit random).
    The HMAC-SHA256 signature proves the webhook came from someone with that secret.
    """
    body, user_id = verified_data
    
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
    verified_data: tuple[bytes, Optional[str]] = Depends(verify_github_webhook_signature),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    """
    Receive and process GitHub webhook events synchronously.
    
    Signature verification happens via dependency.
    """
    body, user_id = verified_data
    
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
    "/webhook/secret/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generate or regenerate GitHub webhook secret",
    description="Generate a new cryptographically secure webhook secret for a user. This replaces any existing secret.",
    tags=["Webhook", "Security"],
)
async def create_webhook_secret(
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate a new webhook secret for a user.
    
    This endpoint:
    - Generates a cryptographically secure random secret (256 bits)
    - Stores it in the user's database record
    - Returns the secret to the user (ONLY time it will be shown in plain text)
    
    **IMPORTANT**: Save this secret immediately! You'll need to configure it in your GitHub webhook settings.
    
    The secret will be used to verify webhook signatures using HMAC-SHA256.
    
    Example usage:
    ```bash
    curl -X POST "http://localhost:8000/api/v1/webhook/secret/generate?user_id=shine"
    ```
    
    Returns:
    - webhook_secret: The generated secret (save this!)
    - user_id: The user ID
    - instructions: How to configure GitHub webhook
    """
    from app.adapters.database.postgres.repositories.users import UserRepository
    
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )
    
    # Generate new secret
    new_secret = generate_webhook_secret()
    
    # Update user record
    user.github_webhook_secret = new_secret
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    logger.info(
        "webhook_secret_generated",
        user_id=user_id,
        secret_length=len(new_secret),
    )
    
    return {
        "success": True,
        "user_id": user_id,
        "webhook_secret": new_secret,
        "secret_length": len(new_secret),
        "algorithm": "HMAC-SHA256",
        "created_at": datetime.utcnow().isoformat(),
        "instructions": {
            "step_1": "⚠️ SAVE THIS SECRET NOW - It won't be shown again!",
            "step_2": "Copy the 'webhook_secret' value above",
            "step_3": "Go to your GitHub repository → Settings → Webhooks",
            "step_4": "Add or edit your webhook",
            "step_5": "Paste the secret in the 'Secret' field",
            "step_6": "Set Payload URL to your DevFlowFix webhook endpoint",
            "step_7": "Set Content type to 'application/json'",
            "step_8": "Select events: workflow_run, check_run",
            "authentication": "🔐 The webhook secret authenticates you automatically - no user_id needed!",
            "how_it_works": "GitHub signs each webhook with your secret. We verify the signature and identify you from our database.",
        },
        "webhook_endpoint": {
            "url": f"{settings.api_url}/api/v1/webhook/github" if hasattr(settings, 'api_url') else "/api/v1/webhook/github",
            "method": "POST",
            "headers_sent_by_github": {
                "X-Hub-Signature-256": "sha256=<computed_signature>",
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "<unique_delivery_id>",
            },
            "note": "GitHub automatically sends X-Hub-Signature-256 header. No custom headers needed from you!",
        },
    }


@router.get(
    "/webhook/secret/info",
    status_code=status.HTTP_200_OK,
    summary="Get webhook secret information",
    description="Get information about a user's webhook secret (without revealing the actual secret)",
    tags=["Webhook", "Security"],
)
async def get_webhook_secret_info(
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get information about a user's webhook secret configuration.
    
    Returns metadata about the secret without revealing the actual value.
    
    Example usage:
    ```bash
    curl "http://localhost:8000/api/v1/webhook/secret/info?user_id=shine"
    ```
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
        # Show only first and last 4 characters
        secret = user.github_webhook_secret
        if len(secret) > 8:
            secret_preview = f"{secret[:4]}...{secret[-4:]}"
        else:
            secret_preview = "****"
    
    return {
        "user_id": user_id,
        "secret_configured": has_secret,
        "secret_preview": secret_preview,
        "secret_length": len(user.github_webhook_secret) if has_secret else 0,
        "last_updated": user.updated_at.isoformat() if user.updated_at else None,
        "webhook_endpoint": f"/api/v1/webhook/github",
        "required_headers": {
            "X-Hub-Signature-256": "sha256=<signature>",
            "X-DevFlowFix-User-ID": user_id,
            "X-GitHub-Event": "<event_type>",
        },
        "actions": {
            "generate_new": f"/api/v1/webhook/secret/generate?user_id={user_id}",
            "test_signature": f"/api/v1/webhook/secret/test?user_id={user_id}",
        },
    }


@router.post(
    "/webhook/secret/test",
    status_code=status.HTTP_200_OK,
    summary="Test webhook signature generation",
    description="Generate a test signature for a payload using the user's webhook secret",
    tags=["Webhook", "Security"],
)
async def test_webhook_signature(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate a test signature for the provided payload using the user's webhook secret.
    
    This endpoint helps you:
    - Test your webhook integration
    - Verify signature generation is working correctly
    - Debug signature validation issues
    
    Example usage:
    ```bash
    curl -X POST "http://localhost:8000/api/v1/webhook/secret/test?user_id=shine" \\
      -H "Content-Type: application/json" \\
      -d '{"action": "completed", "workflow_run": {...}}'
    ```
    
    Returns the signature that should match what GitHub sends.
    """
    import hmac
    import hashlib
    
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
            detail=f"No webhook secret configured for user '{user_id}'. Generate one first using POST /api/v1/webhook/secret/generate",
        )
    
    body = await request.body()
    
    # Compute signature
    signature = hmac.new(
        user.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    # Compute payload hash for reference
    payload_hash = hashlib.sha256(body).hexdigest()
    
    logger.info(
        "webhook_test_signature_generated",
        user_id=user_id,
        payload_size=len(body),
        signature_prefix=signature[:16] + "...",
    )
    
    return {
        "success": True,
        "user_id": user_id,
        "payload_hash": payload_hash,
        "signature": signature,
        "full_header": f"sha256={signature}",
        "payload_size": len(body),
        "usage": {
            "header_name": "X-Hub-Signature-256",
            "header_value": f"sha256={signature}",
            "user_id_header": "X-DevFlowFix-User-ID",
            "user_id_value": user_id,
            "example_curl": f'''curl -X POST http://localhost:8000/api/v1/webhook/github \\
  -H "Content-Type: application/json" \\
  -H "X-Hub-Signature-256: sha256={signature}" \\
  -H "X-DevFlowFix-User-ID: {user_id}" \\
  -H "X-GitHub-Event: workflow_run" \\
  --data '@payload.json' ''',
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post(
    "/webhook/generate-signature",
    status_code=status.HTTP_200_OK,
    summary="Generate GitHub webhook signature (legacy - env secret)",
    description="Generate HMAC-SHA256 signature using environment variable secret (deprecated)",
    tags=["Webhook"],
    deprecated=True,
)
async def generate_webhook_signature_legacy(
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