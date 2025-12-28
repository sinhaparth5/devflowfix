# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import structlog
import asyncio
import json

from app.dependencies import get_db
from app.adapters.database.postgres.repositories.users import ApplicationLogRepository
from app.api.v1.auth import get_current_active_user
from app.core.schemas.logs import ApplicationLogResponse, ApplicationLogListResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/logs", tags=["Application Logs"])


def get_app_log_repo(db: Session = Depends(get_db)) -> ApplicationLogRepository:
    """Get application log repository."""
    return ApplicationLogRepository(db)


# SSE Streaming for Application Logs

async def application_log_stream(
    user_id: Optional[str],
    incident_id: Optional[str],
    level: Optional[str],
    category: Optional[str],
    app_log_repo: ApplicationLogRepository,
) -> AsyncIterator[str]:
    """
    Stream application logs in real-time using Server-Sent Events.

    Polls database every 2 seconds for new logs.
    """
    last_log_time = datetime.now(timezone.utc)

    try:
        while True:
            # Fetch new logs since last check
            if user_id:
                logs, _ = app_log_repo.get_by_user(
                    user_id=user_id,
                    level=level,
                    category=category,
                    start_date=last_log_time,
                    limit=50
                )
            elif incident_id:
                logs, _ = app_log_repo.get_by_incident(
                    incident_id=incident_id,
                    level=level,
                    category=category,
                    limit=50
                )
                # Filter by date manually for incident logs
                logs = [log for log in logs if log.created_at >= last_log_time]
            else:
                logs = app_log_repo.get_recent(
                    limit=50,
                    level=level,
                    category=category
                )
                # Filter by date manually
                logs = [log for log in logs if log.created_at >= last_log_time]

            # Send each new log as SSE event
            for log in reversed(logs):  # Oldest first
                log_data = {
                    "log_id": log.log_id,
                    "incident_id": log.incident_id,
                    "user_id": log.user_id,
                    "level": log.level,
                    "category": log.category,
                    "message": log.message,
                    "stage": log.stage,
                    "details": log.details,
                    "error": log.error,
                    "stack_trace": log.stack_trace,
                    "llm_model": log.llm_model,
                    "llm_tokens_used": log.llm_tokens_used,
                    "llm_response_time_ms": log.llm_response_time_ms,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "duration_ms": log.duration_ms,
                }

                # SSE format: "data: {json}\n\n"
                yield f"data: {json.dumps(log_data)}\n\n"

                # Update last log time
                if log.created_at:
                    last_log_time = max(last_log_time, log.created_at)

            # Wait before checking for new logs
            await asyncio.sleep(2)

    except asyncio.CancelledError:
        # Client disconnected
        logger.info("application_log_stream_closed", user_id=user_id, incident_id=incident_id)
        yield f"data: {json.dumps({'event': 'stream_closed'})}\n\n"


@router.get(
    "/stream",
    summary="Stream application logs in real-time (SSE)",
    responses={
        200: {
            "description": "Event stream of application logs",
            "content": {"text/event-stream": {}}
        }
    },
)
async def stream_application_logs(
    incident_id: Optional[str] = Query(None, description="Filter by incident ID"),
    level: Optional[str] = Query(None, description="Filter by log level (debug, info, warning, error, critical)"),
    category: Optional[str] = Query(None, description="Filter by category (webhook, llm, analysis, etc.)"),
    current_user: dict = Depends(get_current_active_user),
    app_log_repo: ApplicationLogRepository = Depends(get_app_log_repo),
):
    """
    Stream application/workflow logs for the current user in real-time using Server-Sent Events (SSE).

    This tracks the entire CI/CD failure detection workflow:
    - Webhook received
    - LLM analysis in progress
    - Error detection
    - Remediation execution
    - GitHub PR creation
    - Workflow completion

    **Frontend Usage (TypeScript):**
    ```typescript
    const eventSource = new EventSource(
      '/api/v1/logs/stream?incident_id=inc_123&level=info',
      {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      }
    );

    eventSource.onmessage = (event) => {
      const log = JSON.parse(event.data);
      console.log(`[${log.level}] ${log.category}: ${log.message}`);

      // Update UI based on workflow stage
      if (log.stage === 'webhook_received') {
        showNotification('Incident detected!');
      } else if (log.stage === 'llm_analyzing') {
        showSpinner('AI analyzing...');
      } else if (log.stage === 'remediation_complete') {
        showSuccess('Fixed!');
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      eventSource.close();
    };
    ```

    **Query Parameters:**
    - `incident_id`: Filter logs for specific incident
    - `level`: Filter by log level (debug, info, warning, error, critical)
    - `category`: Filter by category (webhook, llm, analysis, remediation, github, database, system)

    **Returns:**
    - Event stream of application log entries as JSON
    - Each event contains: log_id, level, category, message, stage, llm details, timing, etc.
    """
    logger.info(
        "application_log_stream_started",
        user_id=current_user["user"].user_id,
        incident_id=incident_id,
        level=level,
        category=category,
    )

    return StreamingResponse(
        application_log_stream(
            user_id=current_user["user"].user_id,
            incident_id=incident_id,
            level=level,
            category=category,
            app_log_repo=app_log_repo,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        },
    )


@router.get(
    "/",
    response_model=ApplicationLogListResponse,
    summary="Get application logs (paginated)",
)
async def get_application_logs(
    incident_id: Optional[str] = Query(None, description="Filter by incident ID"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    category: Optional[str] = Query(None, description="Filter by category"),
    skip: int = Query(0, ge=0, description="Number of logs to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max logs to return"),
    current_user: dict = Depends(get_current_active_user),
    app_log_repo: ApplicationLogRepository = Depends(get_app_log_repo),
):
    """
    Get application logs with pagination.

    This is for fetching historical logs, not real-time streaming.
    Use `/logs/stream` for real-time updates.
    """
    if incident_id:
        logs, total = app_log_repo.get_by_incident(
            incident_id=incident_id,
            level=level,
            category=category,
            skip=skip,
            limit=limit,
        )
    else:
        logs, total = app_log_repo.get_by_user(
            user_id=current_user["user"].user_id,
            level=level,
            category=category,
            skip=skip,
            limit=limit,
        )

    return ApplicationLogListResponse(
        logs=[ApplicationLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(logs)) < total,
    )
