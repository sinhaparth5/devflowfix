# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Any, Dict

import structlog

from app.core.enums import IncidentSource
from app.services.event_processor import EventProcessor
from app.services.github_log_parser import GitHubLogExtractor

logger = structlog.get_logger(__name__)


async def process_webhook_async(
    event_processor: EventProcessor,
    payload: Dict[str, Any],
    source: IncidentSource,
    incident_id: str,
    user_id: str,
) -> None:
    try:
        if source == IncidentSource.GITHUB:
            try:
                context = payload.get("context", {})
                repo = context.get("repository", "")
                run_id = context.get("run_id")
                if repo and run_id and "/" in repo:
                    owner, repo_name = repo.split("/", 1)
                    log_extractor = GitHubLogExtractor()
                    workflow_logs = await log_extractor.fetch_and_parse_logs(
                        owner=owner,
                        repo=repo_name,
                        run_id=run_id,
                    )
                    if workflow_logs:
                        payload["error_log"] = (
                            f"GitHub Workflow Failed\n"
                            f"Repository: {context.get('repository', 'unknown')}\n"
                            f"Branch: {context.get('branch', 'unknown')}\n\n"
                            f"--- EXTRACTED ERRORS ---\n"
                            f"{workflow_logs}"
                        )
                        logger.info(
                            "github_logs_added_to_payload",
                            incident_id=incident_id,
                            log_length=len(workflow_logs),
                        )
                else:
                    logger.warning(
                        "github_logs_missing_context",
                        incident_id=incident_id,
                        has_repo=bool(repo),
                        has_run_id=bool(run_id),
                    )
            except Exception as exc:
                logger.warning("github_logs_fetch_failed", incident_id=incident_id, error=str(exc))

        result = await event_processor.process(payload=payload, source=source)
        logger.info(
            "webhook_processing_complete",
            incident_id=result.incident_id,
            success=result.success,
            outcome=result.outcome.value,
            user_id=user_id,
        )
    except Exception as exc:
        logger.error(
            "webhook_processing_failed",
            incident_id=incident_id,
            user_id=user_id,
            error=str(exc),
            exc_info=True,
        )


def process_webhook_sync(
    event_processor: EventProcessor,
    payload: Dict[str, Any],
    source: IncidentSource,
    incident_id: str,
    user_id: str,
) -> None:
    import asyncio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            process_webhook_async(
                event_processor=event_processor,
                payload=payload,
                source=source,
                incident_id=incident_id,
                user_id=user_id,
            )
        )
    except Exception as exc:
        logger.error(
            "webhook_sync_wrapper_failed",
            incident_id=incident_id,
            user_id=user_id,
            error=str(exc),
            exc_info=True,
        )
    finally:
        try:
            loop.close()
        except Exception:
            pass
