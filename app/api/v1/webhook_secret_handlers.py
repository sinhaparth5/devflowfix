# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Any, Dict
import hashlib
import hmac

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
import structlog

from app.api.shared.webhooks import generate_webhook_secret
from app.core.config import settings

logger = structlog.get_logger(__name__)


def _base_url() -> str:
    return settings.api_url if hasattr(settings, "api_url") else "https://devflowfix-new-production.up.railway.app"


async def generate_my_webhook_secret_impl(current_user_data: dict, db: Session) -> Dict[str, Any]:
    user = current_user_data["user"]
    db_user = current_user_data["db_user"]
    new_secret = generate_webhook_secret()
    db_user.github_webhook_secret = new_secret
    db_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_user)
    logger.info("webhook_secret_generated_for_authenticated_user", user_id=user.user_id, email=user.email, secret_length=len(new_secret))
    base_url = _base_url()
    webhook_url = f"{base_url}/api/v1/webhook/github/{db_user.user_id}"
    return {
        "success": True,
        "message": "Webhook secret generated successfully",
        "user": {"user_id": db_user.user_id, "email": db_user.email, "full_name": db_user.full_name},
        "webhook_secret": new_secret,
        "webhook_url": webhook_url,
        "secret_length": len(new_secret),
        "algorithm": "HMAC-SHA256",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "github_configuration": {
            "payload_url": webhook_url,
            "content_type": "application/json",
            "secret": new_secret,
            "ssl_verification": "Enable SSL verification",
            "events": ["workflow_run", "check_run"],
            "active": True,
        },
        "setup_instructions": {
            "step_1": {"action": "Copy your webhook secret", "value": new_secret, "note": "Save this secret now - it will not be shown again"},
            "step_2": {"action": "Go to your GitHub repository", "url": "https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks"},
            "step_3": {"action": "Click 'Add webhook'"},
            "step_4": {"action": "Configure webhook settings", "payload_url": webhook_url, "content_type": "application/json", "secret": new_secret},
            "step_5": {"action": "Select events", "individual_events": ["Workflow runs", "Check runs"], "note": "Uncheck 'Just the push event' and select individual events"},
            "step_6": {"action": "Ensure 'Active' is checked"},
            "step_7": {"action": "Click 'Add webhook'"},
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


async def create_webhook_secret_impl(user_id: str, db: Session) -> Dict[str, Any]:
    from app.adapters.database.postgres.repositories.users import UserRepository

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found")
    new_secret = generate_webhook_secret()
    user.github_webhook_secret = new_secret
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info("webhook_secret_generated_admin", user_id=user_id, secret_length=len(new_secret))
    base_url = _base_url()
    webhook_url = f"{base_url}/api/v1/webhook/github/{user_id}"
    return {
        "success": True,
        "user_id": user_id,
        "webhook_secret": new_secret,
        "webhook_url": webhook_url,
        "secret_length": len(new_secret),
        "algorithm": "HMAC-SHA256",
        "created_at": datetime.now(timezone.utc).isoformat(),
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


async def get_my_webhook_info_impl(current_user_data: dict) -> Dict[str, Any]:
    db_user = current_user_data["db_user"]
    has_secret = bool(db_user.github_webhook_secret)
    secret_preview = None
    if has_secret and db_user.github_webhook_secret:
        secret_preview = f"{db_user.github_webhook_secret[:4]}...{db_user.github_webhook_secret[-4:]}" if len(db_user.github_webhook_secret) > 8 else "****"
    base_url = _base_url()
    webhook_url = f"{base_url}/api/v1/webhook/github/{db_user.user_id}"
    return {
        "user": {"user_id": db_user.user_id, "email": db_user.email, "full_name": db_user.full_name},
        "webhook_configuration": {
            "secret_configured": has_secret,
            "secret_preview": secret_preview,
            "secret_length": len(db_user.github_webhook_secret) if has_secret else 0,
            "webhook_url": webhook_url,
            "last_updated": db_user.updated_at.isoformat() if db_user.updated_at else None,
        },
        "github_settings": {"payload_url": webhook_url, "content_type": "application/json", "events": ["workflow_run", "check_run"], "ssl_verification": "enabled"},
        "status": {"ready": has_secret, "message": "Webhook configured and ready" if has_secret else "No webhook secret configured - generate one first"},
        "actions": {
            "generate_new_secret": f"{base_url}/api/v1/webhook/secret/generate/me",
            "test_signature": f"{base_url}/api/v1/webhook/secret/test/me",
            "webhook_endpoint": webhook_url,
        },
    }


async def get_webhook_secret_info_impl(user_id: str, db: Session) -> Dict[str, Any]:
    from app.adapters.database.postgres.repositories.users import UserRepository

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found")
    has_secret = bool(user.github_webhook_secret)
    secret_preview = None
    if has_secret and user.github_webhook_secret:
        secret_preview = f"{user.github_webhook_secret[:4]}...{user.github_webhook_secret[-4:]}" if len(user.github_webhook_secret) > 8 else "****"
    base_url = _base_url()
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


async def test_my_webhook_signature_impl(request: Request, current_user_data: dict) -> Dict[str, Any]:
    db_user = current_user_data["db_user"]
    if not db_user.github_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No webhook secret configured. Generate one using POST /api/v1/webhook/secret/generate/me",
        )
    body = await request.body()
    signature = hmac.new(db_user.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    payload_hash = hashlib.sha256(body).hexdigest()
    logger.info("webhook_test_signature_generated_authenticated", user_id=db_user.user_id, payload_size=len(body), signature_prefix=signature[:16] + "...")
    base_url = _base_url()
    webhook_url = f"{base_url}/api/v1/webhook/github/{db_user.user_id}"
    return {
        "success": True,
        "user": {"user_id": db_user.user_id, "email": db_user.email},
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
  -H "X-GitHub-Delivery: test-{int(datetime.now(timezone.utc).timestamp())}" \\
  --data '@payload.json' ''',
        },
        "verification": {"algorithm": "HMAC-SHA256", "encoding": "hexadecimal", "constant_time_comparison": True},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def test_webhook_signature_impl(request: Request, user_id: str, db: Session) -> Dict[str, Any]:
    from app.adapters.database.postgres.repositories.users import UserRepository

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found")
    if not user.github_webhook_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No webhook secret configured for user '{user_id}'")
    body = await request.body()
    signature = hmac.new(user.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    payload_hash = hashlib.sha256(body).hexdigest()
    logger.info("webhook_test_signature_generated_admin", user_id=user_id, payload_size=len(body), signature_prefix=signature[:16] + "...")
    base_url = _base_url()
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def webhook_health_payload() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "endpoint": "webhook",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
