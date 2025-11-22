# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
import asyncio
import structlog

from app.core.models.incident import Incident
from app.core.models.analysis import AnalysisResult
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.models.context import ExecutionContext
from app.core.enums import (
    IncidentSource, Severity, Outcome, Environment,
    StrategyType, NotifcationType
)
from app.domain.strategies.base import DecisionResult
from app.domain.strategies.factory import StrategyFactory
from app.services.decision import DecisionService
from app.services.analyzer import AnalyzerService
from app.services.remediator import RemediatorService
from app.services.retriever import RetrieverService
from app.adapters.database.postgres.repositories.incident import IncidentRepository
from app.adapters.database.postgres.repositories.vector import VectorRepository
from app.adapters.external.slack.notifications import SlackNotificationAdapter
from app.adapters.ai.nvidia import EmbeddingAdapter

logger = structlog.get_logger(__name__)


@dataclass
class ProcessingResult:
    incident_id: str
    success: bool
    stage: str
    outcome: Outcome
    message: str
    duration_ms: int
    decision: Optional[DecisionResult] = None
    remediation_result: Optional[RemediationResult] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "success": self.success,
            "stage": self.stage,
            "outcome": self.outcome.value,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


class EventProcessor:
    
    def __init__(
        self,
        incident_repository: IncidentRepository,
        vector_repository: VectorRepository,
        analyzer_service: AnalyzerService,
        decision_service: DecisionService,
        remediator_service: RemediatorService,
        retriever_service: RetrieverService,
        notification_service: Optional[SlackNotificationAdapter] = None,
        embedding_adapter: Optional[EmbeddingAdapter] = None,
        default_environment: Environment = Environment.DEVELOPMENT,
        enable_notifications: bool = True,
        enable_auto_remediation: bool = True,
    ):
        self.incident_repo = incident_repository
        self.vector_repo = vector_repository
        self.analyzer = analyzer_service
        self.decision_service = decision_service
        self.remediator = remediator_service
        self.retriever = retriever_service
        self.notification_service = notification_service
        self.embedding_adapter = embedding_adapter
        self.default_environment = default_environment
        self.enable_notifications = enable_notifications
        self.enable_auto_remediation = enable_auto_remediation
        
        logger.info(
            "event_processor_initialized",
            environment=default_environment.value,
            notifications=enable_notifications,
            auto_remediation=enable_auto_remediation,
        )
    
    async def process(
        self,
        payload: Dict[str, Any],
        source: IncidentSource,
        context: Optional[ExecutionContext] = None,
    ) -> ProcessingResult:
        
        start_time = datetime.utcnow()
        incident = None
        
        try:
            incident = await self._create_incident(payload, source)
            
            logger.info(
                "processing_started",
                incident_id=incident.incident_id,
                source=source.value,
            )
            
            if self.enable_notifications and self.notification_service:
                await self._notify(
                    NotifcationType.INCIDENT_DETECTED,
                    incident,
                )
            
            context = context or self._create_context(incident)
            
            await self._generate_and_store_embedding(incident)
            
            similar_incidents = await self._retrieve_similar(incident)
            
            analysis = await self._analyze(incident, similar_incidents)
            
            await self._update_incident_analysis(incident, analysis)
            
            if self.enable_notifications and self.notification_service:
                await self._notify(
                    NotifcationType.ANALYSIS_COMPLETE,
                    incident,
                    analysis=analysis,
                )
            
            decision = await self._decide(analysis, incident, context, similar_incidents)
            
            if not decision.should_auto_fix:
                return await self._handle_no_auto_fix(
                    incident, decision, start_time
                )
            
            if decision.requires_approval:
                return await self._handle_approval_required(
                    incident, decision, start_time
                )
            
            remediation_result = await self._remediate(incident, analysis, context)
            
            await self._finalize(incident, remediation_result)
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return ProcessingResult(
                incident_id=incident.incident_id,
                success=remediation_result.success,
                stage="completed",
                outcome=remediation_result.outcome,
                message=remediation_result.message or "Processing completed",
                duration_ms=duration_ms,
                decision=decision,
                remediation_result=remediation_result,
                metadata={
                    "confidence": decision.confidence,
                    "strategy": decision.strategy_name,
                    "similar_count": len(similar_incidents) if similar_incidents else 0,
                },
            )
        
        except Exception as e:
            logger.exception(
                "processing_failed",
                incident_id=incident.incident_id if incident else None,
                error=str(e),
            )
            
            if incident:
                await self._handle_failure(incident, str(e))
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return ProcessingResult(
                incident_id=incident.incident_id if incident else "unknown",
                success=False,
                stage="error",
                outcome=Outcome.FAILED,
                message="Processing failed",
                duration_ms=duration_ms,
                error=str(e),
            )
    
    async def process_async(
        self,
        payload: Dict[str, Any],
        source: IncidentSource,
        context: Optional[ExecutionContext] = None,
    ) -> str:
        
        incident = await self._create_incident(payload, source)
        
        asyncio.create_task(
            self._process_background(incident, context or self._create_context(incident))
        )
        
        return incident.incident_id
    
    async def _process_background(
        self,
        incident: Incident,
        context: ExecutionContext,
    ):
        try:
            await self._generate_and_store_embedding(incident)
            similar_incidents = await self._retrieve_similar(incident)
            analysis = await self._analyze(incident, similar_incidents)
            await self._update_incident_analysis(incident, analysis)
            
            decision = await self._decide(analysis, incident, context, similar_incidents)
            
            if decision.should_auto_fix and not decision.requires_approval:
                remediation_result = await self._remediate(incident, analysis, context)
                await self._finalize(incident, remediation_result)
            elif decision.requires_approval:
                await self._request_approval(incident, decision)
            else:
                await self._escalate(incident, decision)
                
        except Exception as e:
            logger.exception("background_processing_failed", incident_id=incident.incident_id)
            await self._handle_failure(incident, str(e))
    
    async def _create_incident(
        self,
        payload: Dict[str, Any],
        source: IncidentSource,
    ) -> Incident:
        
        incident = Incident(
            source=source,
            severity=self._extract_severity(payload),
            error_log=self._extract_error_log(payload),
            error_message=payload.get("error_message"),
            context=self._extract_context(payload, source),
            raw_payload=payload,
            timestamp=datetime.utcnow(),
        )
        
        await self.incident_repo.create(incident)
        
        logger.info(
            "incident_created",
            incident_id=incident.incident_id,
            source=source.value,
            severity=incident.severity.value,
        )
        
        return incident
    
    async def _generate_and_store_embedding(self, incident: Incident):
        if not self.embedding_adapter:
            return
        
        try:
            embedding = await self.embedding_adapter.embed_incident(
                error_log=incident.error_log,
                context=incident.context,
            )
            
            self.vector_repo.store_embedding(incident.incident_id, embedding)
            
            logger.debug(
                "embedding_stored",
                incident_id=incident.incident_id,
            )
        except Exception as e:
            logger.warning(
                "embedding_generation_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )
    
    async def _retrieve_similar(self, incident: Incident) -> list:
        try:
            similar = self.vector_repo.search_by_incident(
                incident_id=incident.incident_id,
                top_k=5,
                similarity_threshold=0.7,
            )
            
            result = []
            for inc, similarity in similar:
                result.append({
                    "incident_id": inc.incident_id,
                    "similarity": similarity,
                    "outcome": inc.outcome,
                    "root_cause": inc.root_cause,
                    "remediation_plan": inc.remediation_plan,
                    "resolved_at": inc.resolved_at,
                    "resolution_time_seconds": inc.resolution_time_seconds,
                })
            
            logger.info(
                "similar_incidents_retrieved",
                incident_id=incident.incident_id,
                count=len(result),
            )
            
            return result
            
        except Exception as e:
            logger.warning(
                "similar_retrieval_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )
            return []
    
    async def _analyze(
        self,
        incident: Incident,
        similar_incidents: list,
    ) -> AnalysisResult:
        
        analysis = await self.analyzer.analyze(
            incident=incident,
            similar_incidents=similar_incidents,
        )
        
        logger.info(
            "analysis_complete",
            incident_id=incident.incident_id,
            category=analysis.category.value,
            confidence=analysis.confidence,
            fixability=analysis.fixability.value,
        )
        
        return analysis
    
    async def _update_incident_analysis(
        self,
        incident: Incident,
        analysis: AnalysisResult,
    ):
        incident.failure_type = analysis.category
        incident.root_cause = analysis.root_cause
        incident.fixability = analysis.fixability
        incident.confidence = analysis.confidence
        incident.similar_incidents = [
            {"id": s.get("incident_id"), "similarity": s.get("similarity")}
            for s in analysis.similar_incidents[:5]
        ]
        
        await self.incident_repo.update(incident)
    
    async def _decide(
        self,
        analysis: AnalysisResult,
        incident: Incident,
        context: ExecutionContext,
        similar_incidents: list,
    ) -> DecisionResult:
        
        decision = self.decision_service.decide(
            analysis=analysis,
            incident=incident,
            context=context,
            similar_incidents=similar_incidents,
        )
        
        logger.info(
            "decision_made",
            incident_id=incident.incident_id,
            should_auto_fix=decision.should_auto_fix,
            confidence=decision.confidence,
            requires_approval=decision.requires_approval,
        )
        
        return decision
    
    async def _remediate(
        self,
        incident: Incident,
        analysis: AnalysisResult,
        context: ExecutionContext,
    ) -> RemediationResult:
        
        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotifcationType.REMEDIATION_STARTED,
                incident,
            )
        
        incident.start_remediation()
        await self.incident_repo.update(incident)
        
        result = await self.remediator.execute(
            incident=incident,
            analysis=analysis,
            context=context,
        )
        
        if self.enable_notifications and self.notification_service:
            notification_type = (
                NotifcationType.REMEDIATION_SUCCESS
                if result.success
                else NotifcationType.REMEDIATION_FAILED
            )
            await self._notify(notification_type, incident, remediation_result=result)
        
        return result
    
    async def _finalize(
        self,
        incident: Incident,
        result: RemediationResult,
    ):
        incident.end_remediation(
            success=result.success,
            message=result.message,
        )
        
        incident.remediation_plan = {
            "actions_performed": result.actions_performed,
            "duration_seconds": result.duration_seconds,
            "rollback_snapshot_id": result.rollback_snapshot_id,
        }
        
        await self.incident_repo.update(incident)
        
        logger.info(
            "incident_finalized",
            incident_id=incident.incident_id,
            outcome=incident.outcome.value,
            resolution_time=incident.resolution_time_seconds,
        )
    
    async def _handle_no_auto_fix(
        self,
        incident: Incident,
        decision: DecisionResult,
        start_time: datetime,
    ) -> ProcessingResult:
        
        if decision.escalate:
            await self._escalate(incident, decision)
            outcome = Outcome.ESCALATED
        else:
            incident.mark_resolved(Outcome.PENDING, decision.reason)
            await self.incident_repo.update(incident)
            outcome = Outcome.PENDING
        
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return ProcessingResult(
            incident_id=incident.incident_id,
            success=True,
            stage="decision",
            outcome=outcome,
            message=decision.reason,
            duration_ms=duration_ms,
            decision=decision,
            metadata={"escalated": decision.escalate},
        )
    
    async def _handle_approval_required(
        self,
        incident: Incident,
        decision: DecisionResult,
        start_time: datetime,
    ) -> ProcessingResult:
        
        await self._request_approval(incident, decision)
        
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return ProcessingResult(
            incident_id=incident.incident_id,
            success=True,
            stage="awaiting_approval",
            outcome=Outcome.PENDING,
            message="Awaiting human approval",
            duration_ms=duration_ms,
            decision=decision,
            metadata={"approval_requested": True},
        )
    
    async def _request_approval(
        self,
        incident: Incident,
        decision: DecisionResult,
    ):
        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotifcationType.APPROVAL_REQUESTED,
                incident,
                decision=decision,
            )
        
        logger.info(
            "approval_requested",
            incident_id=incident.incident_id,
            confidence=decision.confidence,
        )
    
    async def _escalate(
        self,
        incident: Incident,
        decision: DecisionResult,
    ):
        incident.mark_resolved(Outcome.ESCALATED, decision.reason)
        await self.incident_repo.update(incident)
        
        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotifcationType.ESCALATION,
                incident,
                decision=decision,
            )
        
        logger.info(
            "incident_escalated",
            incident_id=incident.incident_id,
            reason=decision.reason,
        )
    
    async def _handle_failure(self, incident: Incident, error: str):
        incident.mark_resolved(Outcome.FAILED, error)
        await self.incident_repo.update(incident)
        
        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotifcationType.SYSTEM_ERROR,
                incident,
                error=error,
            )
    
    async def _notify(
        self,
        notification_type: NotifcationType,
        incident: Incident,
        **kwargs,
    ):
        if not self.notification_service:
            return
        
        try:
            await self.notification_service.send(
                notification_type=notification_type,
                incident=incident,
                **kwargs,
            )
        except Exception as e:
            logger.warning(
                "notification_failed",
                notification_type=notification_type.value,
                error=str(e),
            )
    
    def _create_context(self, incident: Incident) -> ExecutionContext:
        return ExecutionContext(
            environment=self.default_environment,
            namespace=incident.get_namespace(),
            repository=incident.get_repository(),
            service=incident.get_service_name(),
            enable_rollback=True,
            requires_approval=self.default_environment == Environment.PRODUCTION,
        )
    
    def _extract_severity(self, payload: Dict[str, Any]) -> Severity:
        severity_str = payload.get("severity", "medium").lower()
        severity_map = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }
        return severity_map.get(severity_str, Severity.MEDIUM)
    
    def _extract_error_log(self, payload: Dict[str, Any]) -> str:
        if "error_log" in payload:
            return payload["error_log"]
        if "message" in payload:
            return payload["message"]
        if "error" in payload:
            return str(payload["error"])
        return str(payload)
    
    def _extract_context(
        self,
        payload: Dict[str, Any],
        source: IncidentSource,
    ) -> Dict[str, Any]:
        
        context = {}
        
        if source == IncidentSource.GITHUB:
            context = {
                "repository": payload.get("repository", {}).get("full_name"),
                "workflow": payload.get("workflow_run", {}).get("name"),
                "branch": payload.get("workflow_run", {}).get("head_branch"),
                "commit": payload.get("workflow_run", {}).get("head_sha"),
                "run_id": payload.get("workflow_run", {}).get("id"),
            }
        
        elif source == IncidentSource.KUBERNETES:
            context = {
                "namespace": payload.get("involved_object", {}).get("namespace"),
                "pod": payload.get("involved_object", {}).get("name"),
                "kind": payload.get("involved_object", {}).get("kind"),
                "reason": payload.get("reason"),
            }
        
        elif source == IncidentSource.ARGOCD:
            context = {
                "application": payload.get("application"),
                "namespace": "argocd",
                "revision": payload.get("revision"),
                "health": payload.get("health"),
            }
        
        context = {k: v for k, v in context.items() if v is not None}
        
        if "context" in payload and isinstance(payload["context"], dict):
            context.update(payload["context"])
        
        return context