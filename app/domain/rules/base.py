# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from abc import ABC, abstractmethod
from typing import Optional
import structlog

from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext

logger = structlog.get_logger(__name__)

class BaseRule(ABC):
    def __init__(self, name: Optional[str] = None):
        self.name = name or self.__class__.__name__
        self.last_failure_reason: Optional[str] = None
        self.escalate_on_failure = False

    @abstractmethod
    def evaluate(
        self,
        incident: Incident,
        context: ExecutionContext,
        analysis: Optional[AnalysisResult] = None,
    ) -> bool:
        pass

    def get_failure_reason(self) -> str:
        return self.last_failure_reason or f"Rule {self.name} failed"
    
    def _set_failure(self, reason: str) -> bool:
        self.last_failure_reason = reason
        logger.debug("rule_failed", rule=self.name, reason=reason)
        return False