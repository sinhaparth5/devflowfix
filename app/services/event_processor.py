# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field
import asyncio
import structlog

from app.core.models.incident import Incident
from app.core.models.analysis import AnalysisResult
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.models.context import ExecutionContext
from app.core.enums import (
    IncidentSource, Severity, Outcome, Environment,
    StrategyType, NotificationType
)
from app.domain.strategies.base import DecisionResult
from app.domain.strategies.factory import StrategyFactory
from app.services.decision import DecisionService
from app.services.analyzer import AnalyzerService
from app.services.remediator import RemediatorService
from app.services.retriever import RetrieverService
from app.services.pr_creator import PRCreatorService
from app.adapters.database.postgres.repositories.incident import IncidentRepository
from app.adapters.database.postgres.repositories.vector import VectorRepository
from app.adapters.database.postgres.models import IncidentTable
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
        pr_creator: Optional[PRCreatorService] = None,
        enable_auto_pr: bool = True,
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
        self.pr_creator = pr_creator
        self.enable_auto_pr = enable_auto_pr
        
        logger.info(
            "event_processor_initialized",
            environment=default_environment.value,
            notifications=enable_notifications,
            auto_remediation=enable_auto_remediation,
            auto_pr_enabled=enable_auto_pr,
        )
    
    async def process(
        self,
        payload: Dict[str, Any],
        source: IncidentSource,
        context: Optional[ExecutionContext] = None,
    ) -> ProcessingResult:
        
        start_time = datetime.now(timezone.utc)
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
                    NotificationType.INCIDENT_DETECTED,
                    incident,
                )
            
            context = context or self._create_context(incident)
            
            await self._generate_and_store_embedding(incident)
            
            similar_incidents = await self._retrieve_similar(incident)
            
            analysis = await self._analyze(incident, similar_incidents)
            
            await self._update_incident_analysis(incident, analysis)
            
            if self.enable_notifications and self.notification_service:
                await self._notify(
                    NotificationType.ANALYSIS_COMPLETE,
                    incident,
                    similar_incidents=similar_incidents,
                )
            
            # Generate solutions and attempt any repository-backed follow-up such as PR creation.
            await self._generate_and_log_solutions(incident, analysis)
            
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
            
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
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
            
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
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
            await self._generate_and_log_solutions(incident, analysis)
            
            decision = await self._decide(analysis, incident, context, similar_incidents)
            
            if decision.should_auto_fix and not decision.requires_approval:
                remediation_result = await self._remediate(incident, analysis, context)
                await self._finalize(incident, remediation_result)
            elif decision.requires_approval:
                await self._request_approval(incident, decision)
            else:
                if decision.escalate:
                    await self._escalate(incident, decision)
                else:
                    incident.mark_resolved(Outcome.PENDING, decision.reason)
                    self._persist_incident_state(incident)
                
        except Exception as e:
            logger.exception("background_processing_failed", incident_id=incident.incident_id)
            await self._handle_failure(incident, str(e))
    
    async def _create_incident(
        self,
        payload: Dict[str, Any],
        source: IncidentSource,
    ) -> Incident:
        
        # Sanitize payload to prevent circular references
        sanitized_payload = self._sanitize_payload(payload)
        
        incident = Incident(
            source=source,
            severity=self._extract_severity(payload),
            error_log=self._extract_error_log(payload),
            error_message=payload.get("error_message"),
            context=self._extract_context(payload, source),
            raw_payload=sanitized_payload,
            timestamp=datetime.now(timezone.utc),
        )
        
        # Convert domain model to database model
        incident_table = IncidentTable(
            incident_id=incident.incident_id,
            timestamp=incident.timestamp,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            source=incident.source.value,
            severity=incident.severity.value,
            failure_type=incident.failure_type.value if incident.failure_type else None,
            error_log=incident.error_log,
            error_message=incident.error_message,
            stack_trace=incident.stack_trace,
            context=incident.context,
            raw_payload=incident.raw_payload,
        )
        
        self.incident_repo.create(incident_table)
        
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
                error=str(e) or repr(e),
                error_type=type(e).__name__,
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
                try:
                    safe_item = {
                        "incident_id": inc.incident_id,
                        "similarity": float(similarity) if similarity is not None else 0.0,
                        "outcome": str(inc.outcome) if inc.outcome else None,
                        "root_cause": str(inc.root_cause) if inc.root_cause else None,
                        "remediation_plan": inc.remediation_plan,
                        "resolved_at": inc.resolved_at,
                        "resolution_time_seconds": int(inc.resolution_time_seconds) if inc.resolution_time_seconds else None,
                    }
                    result.append(safe_item)
                except Exception:
                    # Log full traceback for the problematic item but continue processing others
                    logger.exception(
                        "similar_item_conversion_failed",
                        incident_id=getattr(inc, 'incident_id', None),
                        raw_similarity=repr(similarity),
                    )
                    continue
            
            logger.info(
                "similar_incidents_retrieved",
                incident_id=incident.incident_id,
                count=len(result),
            )
            
            return result
            
        except Exception as e:
            logger.exception(
                "similar_retrieval_failed",
                incident_id=incident.incident_id if incident else None,
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
            similar_incidents=similar_incidents if similar_incidents else [],
        )
        
        logger.info(
            "analysis_complete",
            incident_id=incident.incident_id,
            category=analysis.category.value,
            confidence=analysis.confidence,
            fixability=analysis.fixability.value,
        )
        
        return analysis
    
    async def _generate_and_log_solutions(
        self,
        incident: Incident,
        analysis: AnalysisResult,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate and log solutions for the incident using the LLM.
        
        Calls NVIDIA API to generate detailed solutions based on error analysis
        and logs them to the terminal.
        """
        try:
            # Check if we have an LLM client available
            if not self.analyzer or not self.analyzer.llm:
                logger.warning(
                    "solution_generation_skipped_no_llm",
                    incident_id=incident.incident_id,
                )
                await self._record_post_analysis_state(
                    incident,
                    status="skipped",
                    reason="no_llm_available",
                )
                return None
            
            logger.info(
                "solution_generation_start",
                incident_id=incident.incident_id,
                failure_type=analysis.category.value if analysis.category else "unknown",
            )
            
            # Try to extract structured error information from logs for better context
            enriched_context = incident.context.copy()
            if incident.source == IncidentSource.GITHUB and incident.error_log:
                try:
                    from app.services.github_log_parser import GitHubLogParser
                    parser = GitHubLogParser()
                    errors = parser.extract_errors(incident.error_log)
                    
                    # Get list of changed files from context
                    changed_files = enriched_context.get("changed_files", [])
                    
                    # Add file paths and line numbers to context
                    if errors:
                        error_files = {}
                        for error in errors:
                            if error.file_path:
                                # If we have changed_files list, only include errors from those files
                                if changed_files:
                                    # Check if error file matches any changed file
                                    should_include = any(
                                        error.file_path.endswith(changed_file) or 
                                        changed_file.endswith(error.file_path) or
                                        error.file_path in changed_file or
                                        changed_file in error.file_path
                                        for changed_file in changed_files
                                    )
                                    if not should_include:
                                        continue
                                
                                if error.file_path not in error_files:
                                    error_files[error.file_path] = []
                                error_info = {
                                    "error_type": error.error_type,
                                    "message": error.error_message,
                                    "line": error.line_number,
                                }
                                error_files[error.file_path].append(error_info)
                        
                        if error_files:
                            enriched_context["error_files"] = error_files
                            logger.info(
                                "structured_errors_extracted",
                                incident_id=incident.incident_id,
                                files_count=len(error_files),
                                changed_files_count=len(changed_files) if changed_files else 0,
                                filtered_by_changed_files=bool(changed_files),
                            )
                except Exception as parse_error:
                    logger.warning(
                        "failed_to_parse_structured_errors",
                        incident_id=incident.incident_id,
                        error=str(parse_error),
                    )
            
            # Generate solutions using LLM
            repository_code = await self._fetch_repository_code_context(
                incident=incident,
                context=enriched_context,
            )
            solution = await self.analyzer.llm.generate_solution(
                error_log=incident.error_log,
                failure_type=analysis.category.value if analysis.category else "unknown",
                root_cause=analysis.root_cause or "Unknown root cause",
                context=enriched_context,
                repository_code=repository_code,
            )

            # Log solutions to terminal
            logger.info(
                "solution_generated",
                incident_id=incident.incident_id,
                failure_type=analysis.category.value,
            )
            
            # Log immediate fix details
            if solution.get("immediate_fix"):
                immediate_fix = solution["immediate_fix"]
                logger.info(
                    "solution_immediate_fix",
                    incident_id=incident.incident_id,
                    description=immediate_fix.get("description", ""),
                    steps=immediate_fix.get("steps", []),
                    estimated_time=immediate_fix.get("estimated_time_minutes", 0),
                    risk_level=immediate_fix.get("risk_level", "unknown"),
                )
            
            # Log code changes if any
            if solution.get("code_changes"):
                code_changes_list = solution["code_changes"]
                
                # Handle both list and dict formats
                if isinstance(code_changes_list, dict):
                    code_changes_list = [code_changes_list]

                for idx, code_change in enumerate(code_changes_list, 1):
                    if not isinstance(code_change, dict):
                        continue
                    
                    logger.info(
                        "solution_code_changes",
                        incident_id=incident.incident_id,
                        file_index=idx,
                        file_path=code_change.get("file_path", ""),
                        explanation=code_change.get("explanation", ""),
                    )
            
            # Log configuration changes
            if solution.get("configuration_changes"):
                for config in solution["configuration_changes"][:3]:  # Limit to first 3
                    logger.info(
                        "solution_config_change",
                        incident_id=incident.incident_id,
                        file=config.get("file", ""),
                        setting=config.get("setting", ""),
                    )
            
            # Log prevention measures
            if solution.get("prevention_measures"):
                for measure in solution["prevention_measures"][:3]:
                    logger.info(
                        "solution_prevention",
                        incident_id=incident.incident_id,
                        measure=measure.get("measure", ""),
                    )
            
            # Log resources
            if solution.get("resources"):
                for resource in solution["resources"][:3]:
                    logger.info(
                        "solution_resource",
                        incident_id=incident.incident_id,
                        type=resource.get("type", ""),
                        title=resource.get("title", ""),
                    )
            
            logger.info(
                "solution_generation_complete",
                incident_id=incident.incident_id,
                failure_type=analysis.category.value,
                has_code_changes=bool(solution.get("code_changes")),
                has_config_changes=bool(solution.get("configuration_changes")),
            )

            await self._attempt_post_analysis_pr(incident, analysis, solution)
            return solution
            
        except Exception as e:
            logger.error(
                "solution_generation_failed",
                incident_id=incident.incident_id,
                error=str(e),
                exc_info=True,
            )
            await self._record_post_analysis_state(
                incident,
                status="failed",
                reason=str(e),
            )
            return None

    async def _fetch_repository_code_context(
        self,
        incident: Incident,
        context: Dict[str, Any],
        max_files: int = 3,
        max_chars_per_file: int = 4000,
    ) -> Optional[str]:
        """
        Fetch relevant repository files so the LLM can produce concrete code_changes.
        """
        if incident.source != IncidentSource.GITHUB:
            return None

        repository = context.get("repository") or incident.context.get("repository")
        if not repository or "/" not in repository:
            logger.info(
                "repository_code_fetch_skipped",
                incident_id=incident.incident_id,
                reason="missing_repository",
            )
            return None

        candidate_files = self._select_repository_code_files(context)
        if not candidate_files:
            logger.info(
                "repository_code_fetch_skipped",
                incident_id=incident.incident_id,
                reason="no_candidate_files",
            )
            return None

        owner, repo = repository.split("/", 1)
        ref = context.get("commit") or context.get("branch") or incident.context.get("commit") or incident.context.get("branch")
        user_id = context.get("user_id") or incident.context.get("user_id")

        token = None
        if user_id and hasattr(self.incident_repo, "db"):
            try:
                from app.services.github_token_manager import GitHubTokenManager

                token = GitHubTokenManager(db=self.incident_repo.db).get_token(user_id, owner, repo)
            except Exception as token_error:
                logger.warning(
                    "repository_code_token_lookup_failed",
                    incident_id=incident.incident_id,
                    error=str(token_error),
                )

        try:
            import base64

            from app.adapters.external.github.client import GitHubClient

            snippets = []
            async with GitHubClient(token=token) as github_client:
                for file_path in candidate_files[:max_files]:
                    try:
                        current_file = await github_client.get_file_contents(
                            owner=owner,
                            repo=repo,
                            path=file_path,
                            ref=ref,
                        )
                        encoded = current_file.get("content", "")
                        decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
                        snippets.append(
                            f"## File: {file_path}\n```\n{decoded[:max_chars_per_file]}\n```"
                        )
                    except Exception as file_error:
                        logger.warning(
                            "repository_code_file_fetch_failed",
                            incident_id=incident.incident_id,
                            file_path=file_path,
                            error=str(file_error),
                        )

            if not snippets:
                return None

            repository_code = "\n\n".join(snippets)
            logger.info(
                "repository_code_context_fetched",
                incident_id=incident.incident_id,
                files_count=len(snippets),
                chars=len(repository_code),
            )
            return repository_code

        except Exception as fetch_error:
            logger.warning(
                "repository_code_fetch_failed",
                incident_id=incident.incident_id,
                error=str(fetch_error),
            )
            return None

    def _select_repository_code_files(self, context: Dict[str, Any]) -> list[str]:
        candidate_files: list[str] = []

        error_files = context.get("error_files")
        if isinstance(error_files, dict):
            candidate_files.extend(error_files.keys())

        changed_files = context.get("changed_files")
        if isinstance(changed_files, list):
            candidate_files.extend(
                path for path in changed_files if isinstance(path, str)
            )

        workflow_file = context.get("workflow_file")
        if isinstance(workflow_file, str):
            candidate_files.append(workflow_file)

        seen = set()
        selected = []
        for path in candidate_files:
            normalized = path.strip().lstrip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            selected.append(normalized)

        return selected

    async def _attempt_post_analysis_pr(
        self,
        incident: Incident,
        analysis: AnalysisResult,
        solution: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not solution.get("code_changes"):
            await self._record_post_analysis_state(
                incident,
                status="skipped",
                reason="no_code_changes",
            )
            return None

        supported, reason = self._supports_automated_pr(incident)
        if not supported:
            await self._record_post_analysis_state(
                incident,
                status="skipped",
                reason=reason,
            )
            logger.info("auto_pr_skipped", incident_id=incident.incident_id, reason=reason)
            return None

        if not self.enable_auto_pr:
            await self._record_post_analysis_state(
                incident,
                status="skipped",
                reason="auto_pr_disabled",
            )
            logger.info("auto_pr_skipped_disabled", incident_id=incident.incident_id)
            return None

        should_create = self._should_create_pr(analysis, incident, solution)
        logger.info(
            "pr_creation_decision",
            incident_id=incident.incident_id,
            enable_auto_pr=self.enable_auto_pr,
            has_code_changes=bool(solution.get("code_changes")),
            should_create_pr=should_create,
            confidence=analysis.confidence,
            fixability=str(analysis.fixability),
            has_repository=bool(incident.context.get("repository")),
            provider=incident.source.value,
        )

        if not should_create:
            await self._record_post_analysis_state(
                incident,
                status="skipped",
                reason="pr_creation_criteria_not_met",
            )
            return None

        try:
            logger.info(
                "auto_pr_creation_start",
                incident_id=incident.incident_id,
                failure_type=analysis.category.value,
            )

            user_id = incident.context.get("user_id")
            pr_result = await self._create_fix_pr(
                incident=incident,
                analysis=analysis,
                solution=solution,
                user_id=user_id,
            )

            logger.info(
                "auto_pr_create_success",
                incident_id=incident.incident_id,
                pr_number=pr_result.get("number"),
                pr_url=pr_result.get("html_url"),
            )

            incident.context["automated_pr"] = {
                "number": pr_result.get("number"),
                "url": pr_result.get("html_url"),
                "branch": pr_result.get("head", {}).get("ref"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._record_post_analysis_state(
                incident,
                status="pr_created",
                reason="created",
                extra={"pr_number": pr_result.get("number")},
            )
            return pr_result
        except Exception as pr_error:
            logger.error(
                "auto_pr_creation_failed",
                incident_id=incident.incident_id,
                error=str(pr_error),
                exc_info=True,
            )
            await self._record_post_analysis_state(
                incident,
                status="failed",
                reason=f"pr_creation_failed:{pr_error}",
            )
            return None
        
    def _should_create_pr(
            self,
            analysis: AnalysisResult,
            incident: Incident,
            solution: Optional[Dict[str, Any]] = None,
            min_confidence: float = 0.70,
    ) -> bool:
        """
        Determine if an automated fix PR should be created.

        Args:
            analysis: Analysis result with failure classification
            incident: Incident details
            min_confidence: Minimum confidence threshold (default: 0.70)
        
        Returns:
            True if PR should created, False otherwise
        """
        # Log all PR creation criteria for debugging
        logger.info(
            "pr_creation_criteria_check",
            incident_id=incident.incident_id,
            confidence=analysis.confidence,
            min_confidence=min_confidence,
            failure_type=analysis.category.value if analysis.category else "unknown",
            fixability=str(analysis.fixability) if analysis.fixability else "unknown",
            has_repository=bool(incident.context.get("repository")),
            repository=incident.context.get("repository"),
            has_code_changes=bool(solution and solution.get("code_changes")),
        )
        
        if analysis.confidence < min_confidence:
            logger.info(
                "pr_creation_skipped_low_confidence",
                incident_id=incident.incident_id,
                confidence=analysis.confidence,
                threshold=min_confidence,
            )

            return False

        if not incident.context.get("repository"):
            logger.info(
                "pr_creation_skipped_no_repo",
                incident_id=incident.incident_id,
            )
            return False
        
        if incident.context.get("automated_pr"):
            logger.info(
                "pr_creation_skipped_already_exists",
                incident_id=incident.incident_id,
                existing_pr=incident.context["automated_pr"].get("number"),
            )
            return False

        if solution is not None and not solution.get("code_changes"):
            logger.info(
                "pr_creation_skipped_no_code_changes",
                incident_id=incident.incident_id,
            )
            return False
        
        logger.info(
            "pr_creation_criteria_met",
            incident_id=incident.incident_id,
            confidence=analysis.confidence,
            failure_type=analysis.category.value,
            fixability=analysis.fixability.value if hasattr(analysis.fixability, 'value') else str(analysis.fixability),
        )

        return True

    def _supports_automated_pr(self, incident: Incident) -> tuple[bool, str]:
        repository = incident.context.get("repository")
        if not repository:
            return False, "missing_repository_context"

        if incident.source != IncidentSource.GITHUB:
            return False, f"provider_{incident.source.value}_pr_not_supported"

        if not incident.context.get("user_id"):
            return False, "missing_user_id"

        return True, "supported"

    async def _record_post_analysis_state(
        self,
        incident: Incident,
        status: str,
        reason: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        state = {
            "status": status,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            state.update(extra)

        incident.context["post_analysis"] = state
        self._persist_incident_context(incident)
    
    async def _create_fix_pr(
            self,
            incident: Incident,
            analysis: AnalysisResult,
            solution: Dict[str, Any],
            user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from app.services.pr_creator import PRCreatorService

        if not hasattr(self, 'pr_creator') or not self.pr_creator:
            self.pr_creator = PRCreatorService()

        pr_result = await self.pr_creator.create_fix_pr(
            incident=incident,
            analysis=analysis,
            solution=solution,
            user_id=user_id,
        )

        return pr_result

    def _persist_incident_context(self, incident: Incident) -> None:
        incident_table = self.incident_repo.get_by_id(incident.incident_id)
        if not incident_table:
            return

        incident_table.context = incident.context
        self.incident_repo.update(incident_table)

    def _persist_incident_state(self, incident: Incident) -> None:
        incident_table = self.incident_repo.get_by_id(incident.incident_id)
        if not incident_table:
            return

        incident_table.context = incident.context
        incident_table.root_cause = incident.root_cause
        incident_table.failure_type = incident.failure_type.value if incident.failure_type else incident_table.failure_type
        incident_table.fixability = incident.fixability.value if incident.fixability else incident_table.fixability
        incident_table.confidence = incident.confidence
        incident_table.remediation_plan = incident.remediation_plan
        incident_table.remediation_executed = incident.remediation_executed
        incident_table.remediation_start_time = incident.remediation_start_time
        incident_table.remediation_end_time = incident.remediation_end_time
        incident_table.outcome = incident.outcome.value if incident.outcome else None
        incident_table.outcome_message = incident.outcome_message
        incident_table.resolved_at = incident.resolved_at
        incident_table.resolution_time_seconds = incident.resolution_time_seconds
        self.incident_repo.update(incident_table)
    
    async def _update_incident_analysis(
        self,
        incident: Incident,
        analysis: AnalysisResult,
    ):
        # Fetch the database model
        incident_table = self.incident_repo.get_by_id(incident.incident_id)
        if incident_table:
            incident_table.failure_type = analysis.category.value if analysis.category else None
            incident_table.root_cause = analysis.root_cause
            incident_table.fixability = analysis.fixability.value if analysis.fixability else None
            incident_table.confidence = analysis.confidence
            incident_table.similar_incidents = [
                {"id": s.get("incident_id"), "similarity": s.get("similarity")}
                for s in analysis.similar_incidents[:5]
            ]
            
            self.incident_repo.update(incident_table)
    
    async def _decide(
        self,
        analysis: AnalysisResult,
        incident: Incident,
        context: ExecutionContext,
        similar_incidents: list,
    ) -> DecisionResult:
        
        decision = await self.decision_service.decide(
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
                NotificationType.REMEDIATION_STARTED,
                incident,
            )
        
        incident.start_remediation()
        self._persist_incident_state(incident)
        
        result = await self.remediator.execute(
            incident=incident,
            analysis=analysis,
            context=context,
        )
        
        if self.enable_notifications and self.notification_service:
            notification_type = (
                NotificationType.REMEDIATION_SUCCESS
                if result.success
                else NotificationType.REMEDIATION_FAILED
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
        
        self._persist_incident_state(incident)
        
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
            self._persist_incident_state(incident)
            outcome = Outcome.PENDING
        
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
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
        
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
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
        incident.outcome = Outcome.PENDING
        incident.outcome_message = "Awaiting human approval"
        incident.updated_at = datetime.now(timezone.utc)
        self._persist_incident_state(incident)

        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotificationType.APPROVAL_REQUESTED,
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
        self._persist_incident_state(incident)
        
        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotificationType.ESCALATION,
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
        
        # Fetch and update the database model
        incident_table = self.incident_repo.get_by_id(incident.incident_id)
        if incident_table:
            incident_table.outcome = Outcome.FAILED.value
            incident_table.outcome_message = error
            incident_table.resolved_at = incident.resolved_at
            incident_table.resolution_time_seconds = incident.resolution_time_seconds
            self.incident_repo.update(incident_table)
        
        if self.enable_notifications and self.notification_service:
            await self._notify(
                NotificationType.SYSTEM_ERROR,
                incident,
                error=error,
            )
    
    async def _notify(
        self,
        notification_type: NotificationType,
        incident: Incident,
        **kwargs,
    ):
        if not self.notification_service:
            return
        
        try:
            await self.notification_service.notify_incident(
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
    
    def _sanitize_payload(self, payload: Any, depth: int = 0, max_depth: int = 10) -> Any:
        """
        Sanitize payload to prevent circular references and deep nesting.
        
        Args:
            payload: The payload to sanitize
            depth: Current recursion depth
            max_depth: Maximum allowed recursion depth
            
        Returns:
            Sanitized payload safe for JSON serialization
        """
        if depth > max_depth:
            return "[MAX_DEPTH_EXCEEDED]"
        
        if payload is None or isinstance(payload, (str, int, float, bool)):
            return payload
        
        if isinstance(payload, dict):
            sanitized = {}
            for key, value in payload.items():
                try:
                    sanitized[key] = self._sanitize_payload(value, depth + 1, max_depth)
                except (TypeError, RecursionError):
                    sanitized[key] = str(value)
            return sanitized
        
        if isinstance(payload, (list, tuple)):
            return [self._sanitize_payload(item, depth + 1, max_depth) for item in payload]
        
        # For any other type, convert to string
        try:
            return str(payload)
        except Exception:
            return "[UNSERIALIZED_OBJECT]"
    
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
            # Extract modified files from commits
            modified_files = []
            added_files = []
            
            # From workflow_run payload
            if "workflow_run" in payload:
                head_commit = payload.get("workflow_run", {}).get("head_commit", {})
                modified_files.extend(head_commit.get("modified", []))
                added_files.extend(head_commit.get("added", []))
            
            # From push payload
            if "commits" in payload:
                for commit in payload.get("commits", []):
                    modified_files.extend(commit.get("modified", []))
                    added_files.extend(commit.get("added", []))
            
            # From head_commit in push payload
            if "head_commit" in payload:
                head_commit = payload.get("head_commit", {})
                modified_files.extend(head_commit.get("modified", []))
                added_files.extend(head_commit.get("added", []))
            
            # Combine and deduplicate
            all_changed_files = list(set(modified_files + added_files))
            
            context = {
                "repository": payload.get("repository", {}).get("full_name"),
                "workflow": payload.get("workflow_run", {}).get("name"),
                "branch": payload.get("workflow_run", {}).get("head_branch"),
                "commit": payload.get("workflow_run", {}).get("head_sha"),
                "run_id": payload.get("workflow_run", {}).get("id"),
                "changed_files": all_changed_files if all_changed_files else None,
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
