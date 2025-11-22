# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
import structlog

from app.domain.rules.base import BaseRule
from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext
from app.core.enums import Environment, Severity

logger = structlog.get_logger(__name__)


class EnvironmentRule(BaseRule):
    
    def __init__(self):
        pass

    @property
    def name(self) -> str:
        """ Get the rule name """
        return "EnvironmentRule"
    
    def evaluate(
        self,
        incident: Incident,
        context: ExecutionContext,
        analysis: Optional[AnalysisResult] = None,
    ) -> bool:
        
        if context.environment == Environment.PRODUCTION:
            if not context.enable_rollback:
                return self._set_failure(
                    "Production requires rollback capability"
                )
            
            if incident.severity == Severity.CRITICAL:
                if not analysis or analysis.confidence < 0.95:
                    return self._set_failure(
                        "Critical production incidents require 95%+ confidence"
                    )
            
            if context.dry_run:
                return self._set_failure(
                    "Production cannot run in dry-run mode"
                )
        
        if context.environment == Environment.TEST:
            return True
        
        return True