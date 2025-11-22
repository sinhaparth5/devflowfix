# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, time
from typing import Optional
import structlog

from app.domain.rules.base import BaseRule
from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext

logger = structlog.get_logger(__name__)


class TimeWindowRule(BaseRule):
    
    def __init__(
        self,
        allowed_start: time = time(0, 0),
        allowed_end: time = time(23, 59),
        block_weekends: bool = False,
        block_business_hours: bool = False,
    ):
        self.allowed_start = allowed_start
        self.allowed_end = allowed_end
        self.block_weekends = block_weekends
        self.block_business_hours = block_business_hours

    @property
    def name(self) -> str:
        """ Get the rule name. """
        return "TimeWindowRule"
    
    def evaluate(
        self,
        incident: Incident,
        context: ExecutionContext,
        analysis: Optional[AnalysisResult] = None,
    ) -> bool:
        
        now = datetime.utcnow()
        current_time = now.time()
        
        if not (self.allowed_start <= current_time <= self.allowed_end):
            return self._set_failure(
                f"Current time {current_time} outside allowed window "
                f"{self.allowed_start}-{self.allowed_end}"
            )
        
        if self.block_weekends and now.weekday() >= 5:
            return self._set_failure("Weekend deployments are blocked")
        
        if self.block_business_hours:
            business_start = time(9, 0)
            business_end = time(17, 0)
            
            if business_start <= current_time <= business_end:
                if now.weekday() < 5:
                    return self._set_failure("Business hours deployments are blocked")
        
        return True