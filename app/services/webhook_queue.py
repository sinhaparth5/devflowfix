# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog

from app.adapters.cache.redis import get_redis_cache
from app.adapters.database.postgres.models import JobStatus, JobType
from app.adapters.database.postgres.repositories.jobs import JobRepository
from app.core.config import settings
from app.core.enums import IncidentSource

logger = structlog.get_logger(__name__)


@dataclass
class WebhookQueueItem:
    payload: Dict[str, Any]
    source: IncidentSource
    incident_id: str
    user_id: str
    job_id: str
    dedup_key: Optional[str] = None
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WebhookEnqueueResult:
    queued: bool
    reason: str
    job_id: Optional[str] = None


class WebhookQueueService:
    """Bounded in-process worker queue for webhook processing."""

    def __init__(self) -> None:
        self.max_size = settings.webhook_queue_max_size
        self.worker_count = settings.webhook_queue_workers
        self.dedup_ttl_seconds = settings.webhook_dedup_ttl_seconds
        self.queue: asyncio.Queue[WebhookQueueItem] = asyncio.Queue(maxsize=self.max_size)
        self._workers: list[asyncio.Task] = []
        self._started = False
        self._start_lock = asyncio.Lock()
        self._redis = get_redis_cache()

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return

            for idx in range(self.worker_count):
                self._workers.append(asyncio.create_task(self._worker_loop(idx + 1)))

            self._started = True
            logger.info(
                "webhook_queue_started",
                worker_count=self.worker_count,
                max_size=self.max_size,
                dedup_ttl_seconds=self.dedup_ttl_seconds,
            )

    async def stop(self) -> None:
        if not self._started:
            return

        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False
        logger.info("webhook_queue_stopped")

    async def enqueue(
        self,
        *,
        payload: Dict[str, Any],
        source: IncidentSource,
        incident_id: str,
        user_id: str,
        dedup_key: Optional[str] = None,
    ) -> WebhookEnqueueResult:
        if not self._started:
            await self.start()

        if dedup_key:
            created = await self._redis.set_if_absent(
                key=f"webhook:dedup:{dedup_key}",
                value=incident_id,
                ttl=self.dedup_ttl_seconds,
            )
            if not created:
                logger.info(
                    "webhook_queue_duplicate_dropped",
                    incident_id=incident_id,
                    source=source.value,
                    user_id=user_id,
                    dedup_key=dedup_key,
                )
                return WebhookEnqueueResult(queued=False, reason="duplicate")

        job_id = self._create_job_record(
            user_id=user_id,
            source=source,
            incident_id=incident_id,
            payload=payload,
            dedup_key=dedup_key,
        )

        item = WebhookQueueItem(
            payload=payload,
            source=source,
            incident_id=incident_id,
            user_id=user_id,
            job_id=job_id,
            dedup_key=dedup_key,
        )

        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning(
                "webhook_queue_full",
                incident_id=incident_id,
                source=source.value,
                user_id=user_id,
                job_id=job_id,
                queue_size=self.queue.qsize(),
                max_size=self.max_size,
            )
            self._mark_job_failed(job_id, "Webhook queue is full")
            return WebhookEnqueueResult(queued=False, reason="queue_full", job_id=job_id)

        logger.info(
            "webhook_queue_enqueued",
            incident_id=incident_id,
            source=source.value,
            user_id=user_id,
            job_id=job_id,
            queue_size=self.queue.qsize(),
        )
        return WebhookEnqueueResult(queued=True, reason="queued", job_id=job_id)

    def _create_job_record(
        self,
        *,
        user_id: str,
        source: IncidentSource,
        incident_id: str,
        payload: Dict[str, Any],
        dedup_key: Optional[str],
    ) -> str:
        from app.dependencies import get_session_local

        SessionLocal = get_session_local()
        db = SessionLocal()
        try:
            job_id = f"job_{uuid4().hex[:12]}"
            repo = payload.get("context", {}).get("repository")
            run_id = payload.get("context", {}).get("run_id")
            JobRepository(db).create(
                job_id=job_id,
                user_id=user_id,
                job_type=JobType.INCIDENT_ANALYSIS,
                parameters={
                    "incident_id": incident_id,
                    "source": source.value,
                    "repository": repo,
                    "run_id": run_id,
                },
                job_metadata={
                    "dedup_key": dedup_key,
                    "queue": "webhook",
                },
            )
            return job_id
        finally:
            db.close()

    def _update_job_progress(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        current_step: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        from app.dependencies import get_session_local

        SessionLocal = get_session_local()
        db = SessionLocal()
        try:
            repo = JobRepository(db)
            if status is not None:
                repo.update_status(job_id, status, error_message=error_message)
            if progress is not None or current_step is not None:
                repo.update_progress(
                    job_id,
                    progress=progress if progress is not None else 0,
                    current_step=current_step,
                )
            if result is not None:
                repo.set_result(job_id, result)
        finally:
            db.close()

    def _mark_job_failed(self, job_id: str, message: str) -> None:
        self._update_job_progress(
            job_id,
            status=JobStatus.FAILED,
            progress=0,
            current_step="failed",
            error_message=message,
        )

    async def _worker_loop(self, worker_id: int) -> None:
        from app.api.v1.webhook_processing import process_webhook_async
        from app.dependencies import get_event_processor, get_session_local

        logger.info("webhook_worker_started", worker_id=worker_id)
        try:
            while True:
                item = await self.queue.get()
                started_at = datetime.now(timezone.utc)
                self._update_job_progress(
                    item.job_id,
                    status=JobStatus.PROCESSING,
                    progress=10,
                    current_step="processing_webhook",
                )

                SessionLocal = get_session_local()
                db = SessionLocal()
                try:
                    event_processor = get_event_processor(db)
                    result = await process_webhook_async(
                        event_processor=event_processor,
                        payload=item.payload,
                        source=item.source,
                        incident_id=item.incident_id,
                        user_id=item.user_id,
                    )
                    if result.get("success"):
                        self._update_job_progress(
                            item.job_id,
                            status=JobStatus.COMPLETED,
                            progress=100,
                            current_step=result.get("stage") or "completed",
                            result=result,
                        )
                    else:
                        self._update_job_progress(
                            item.job_id,
                            status=JobStatus.FAILED,
                            progress=100,
                            current_step=result.get("stage") or "failed",
                            result=result,
                            error_message=result.get("error") or result.get("message"),
                        )
                        logger.warning(
                            "webhook_worker_processing_unsuccessful",
                            worker_id=worker_id,
                            incident_id=item.incident_id,
                            user_id=item.user_id,
                            job_id=item.job_id,
                            stage=result.get("stage"),
                            message=result.get("message"),
                            error=result.get("error"),
                        )
                except Exception as exc:
                    self._update_job_progress(
                        item.job_id,
                        status=JobStatus.FAILED,
                        progress=100,
                        current_step="failed",
                        error_message=str(exc),
                    )
                    logger.error(
                        "webhook_worker_processing_failed",
                        worker_id=worker_id,
                        incident_id=item.incident_id,
                        source=item.source.value,
                        user_id=item.user_id,
                        job_id=item.job_id,
                        error=str(exc),
                        exc_info=True,
                    )
                finally:
                    db.close()
                    self.queue.task_done()
                    logger.info(
                        "webhook_worker_finished",
                        worker_id=worker_id,
                        incident_id=item.incident_id,
                        source=item.source.value,
                        user_id=item.user_id,
                        job_id=item.job_id,
                        duration_ms=int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
                        queue_size=self.queue.qsize(),
                    )
        except asyncio.CancelledError:
            logger.info("webhook_worker_stopped", worker_id=worker_id)
            raise


_webhook_queue_service: Optional[WebhookQueueService] = None


def get_webhook_queue_service() -> WebhookQueueService:
    global _webhook_queue_service
    if _webhook_queue_service is None:
        _webhook_queue_service = WebhookQueueService()
    return _webhook_queue_service
