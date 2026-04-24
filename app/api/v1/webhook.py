# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.api.shared.webhooks import generate_webhook_secret, verify_github_signature, verify_gitlab_token
from app.api.v1.gitlab_webhook_handlers import (
    parse_gitlab_webhook_payload,
    process_oauth_connected_pipeline_event as _process_oauth_connected_pipeline_event,
)
from app.api.v1.webhook_processing import process_webhook_async, process_webhook_sync
from app.api.v1.webhook_provider_handlers import (
    process_oauth_connected_workflow_event,
    receive_argocd_webhook_impl,
    receive_generic_webhook_impl,
    receive_github_webhook_impl,
    receive_github_webhook_sync_impl,
    receive_gitlab_webhook_impl,
    receive_kubernetes_webhook_impl,
    verify_github_webhook_signature as verify_github_webhook_signature_impl,
)
from app.api.v1.webhook_secret_handlers import (
    create_webhook_secret_impl,
    generate_my_webhook_secret_impl,
    get_my_webhook_info_impl,
    get_webhook_secret_info_impl,
    test_my_webhook_signature_impl,
    test_webhook_signature_impl,
    webhook_health_payload,
)
from app.auth import get_current_active_user
from app.core.schemas.webhook import WebhookPayload, WebhookResponse
from app.dependencies import get_db, get_event_processor
from app.services.event_processor import EventProcessor
from app.services.workflow.gitlab_pipeline_tracker import GitLabPipelineTracker

router = APIRouter()


async def process_oauth_connected_pipeline_event(
    db: Session,
    user_id: str,
    payload: Dict[str, Any],
) -> bool:
    return await _process_oauth_connected_pipeline_event(
        db=db,
        user_id=user_id,
        payload=payload,
        tracker_cls=GitLabPipelineTracker,
    )


async def verify_github_webhook_signature(
    user_id: str,
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: Session = Depends(get_db),
) -> bytes:
    return await verify_github_webhook_signature_impl(
        user_id=user_id,
        request=request,
        signature_header=x_hub_signature_256,
        db=db,
        verify_github_signature=verify_github_signature,
    )


@router.post(
    "/webhook/github/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint",
    tags=["Webhooks"],
)
async def receive_github_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(...),
    x_github_delivery: Optional[str] = Header(None),
    body: bytes = Depends(verify_github_webhook_signature),
    event_processor: EventProcessor = Depends(get_event_processor),
    db: Session = Depends(get_db),
) -> WebhookResponse:
    del request
    return await receive_github_webhook_impl(
        user_id=user_id,
        x_github_event=x_github_event,
        x_github_delivery=x_github_delivery,
        body=body,
        background_tasks=background_tasks,
        event_processor=event_processor,
        db=db,
        process_webhook_sync=process_webhook_sync,
    )


@router.post(
    "/webhook/github/{user_id}/sync",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook endpoint (synchronous)",
    tags=["Webhooks"],
)
async def receive_github_webhook_sync(
    user_id: str,
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: Optional[str] = Header(None),
    body: bytes = Depends(verify_github_webhook_signature),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    del request
    return await receive_github_webhook_sync_impl(
        user_id=user_id,
        x_github_event=x_github_event,
        x_github_delivery=x_github_delivery,
        body=body,
        event_processor=event_processor,
    )


@router.post(
    "/webhook/argocd/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="ArgoCD webhook endpoint",
    tags=["Webhooks"],
)
async def receive_argocd_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    del request, db
    return await receive_argocd_webhook_impl(
        user_id=user_id,
        payload=payload,
        background_tasks=background_tasks,
        event_processor=event_processor,
        process_webhook_sync=process_webhook_sync,
    )


@router.post(
    "/webhook/kubernetes/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Kubernetes event webhook endpoint",
    tags=["Webhooks"],
)
async def receive_kubernetes_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    del request, db
    return await receive_kubernetes_webhook_impl(
        user_id=user_id,
        payload=payload,
        background_tasks=background_tasks,
        event_processor=event_processor,
        process_webhook_sync=process_webhook_sync,
    )


@router.post(
    "/webhook/gitlab/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitLab webhook endpoint",
    tags=["Webhooks"],
)
async def receive_gitlab_webhook(
    user_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_gitlab_event: Optional[str] = Header(None, alias="X-Gitlab-Event"),
    x_gitlab_token: Optional[str] = Header(None, alias="X-Gitlab-Token"),
    db: Session = Depends(get_db),
    event_processor: EventProcessor = Depends(get_event_processor),
) -> WebhookResponse:
    del background_tasks, x_gitlab_token, event_processor
    body = await request.body()
    return await receive_gitlab_webhook_impl(
        user_id=user_id,
        body=body,
        x_gitlab_event=x_gitlab_event,
        process_oauth_connected_pipeline_event=process_oauth_connected_pipeline_event,
        parse_gitlab_webhook_payload=parse_gitlab_webhook_payload,
        db=db,
    )


@router.post(
    "/webhook/generic/{user_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Generic webhook endpoint",
    tags=["Webhooks"],
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
    del request, db
    return await receive_generic_webhook_impl(
        user_id=user_id,
        payload=payload,
        x_webhook_source=x_webhook_source,
        background_tasks=background_tasks,
        event_processor=event_processor,
        process_webhook_sync=process_webhook_sync,
    )


@router.post(
    "/webhook/secret/generate/me",
    status_code=status.HTTP_201_CREATED,
    summary="Generate webhook secret for authenticated user",
    tags=["Webhooks", "Security"],
)
async def generate_my_webhook_secret(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    return await generate_my_webhook_secret_impl(current_user_data=current_user_data, db=db)


@router.post(
    "/webhook/secret/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generate webhook secret (admin)",
    tags=["Webhooks", "Security", "Admin"],
)
async def create_webhook_secret(
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return await create_webhook_secret_impl(user_id=user_id, db=db)


@router.get(
    "/webhook/secret/info/me",
    status_code=status.HTTP_200_OK,
    summary="Get my webhook configuration",
    tags=["Webhooks", "Security"],
)
async def get_my_webhook_info(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    del db
    return await get_my_webhook_info_impl(current_user_data=current_user_data)


@router.get(
    "/webhook/secret/info",
    status_code=status.HTTP_200_OK,
    summary="Get webhook secret information (admin)",
    tags=["Webhooks", "Security", "Admin"],
)
async def get_webhook_secret_info(
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return await get_webhook_secret_info_impl(user_id=user_id, db=db)


@router.post(
    "/webhook/secret/test/me",
    status_code=status.HTTP_200_OK,
    summary="Test my webhook signature",
    tags=["Webhooks", "Security"],
)
async def test_my_webhook_signature(
    request: Request,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> Dict[str, Any]:
    del db
    return await test_my_webhook_signature_impl(request=request, current_user_data=current_user_data)


@router.post(
    "/webhook/secret/test",
    status_code=status.HTTP_200_OK,
    summary="Test webhook signature (admin)",
    tags=["Webhooks", "Security", "Admin"],
)
async def test_webhook_signature(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return await test_webhook_signature_impl(request=request, user_id=user_id, db=db)


@router.get(
    "/webhook/health",
    status_code=status.HTTP_200_OK,
    summary="Webhook health check",
    tags=["Webhooks"],
)
async def webhook_health() -> Dict[str, Any]:
    return webhook_health_payload()
