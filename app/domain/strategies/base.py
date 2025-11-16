# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import structlog

from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.confidence import ConfidenceScore
from app.core.models.context import ExecutionContext
from app.core.enums import Environment, Fixability

logger = structlog.get_logger(__name__)

@dataclass
class DecisionResult:
    should_auto_fix: bool
    confidence: float
    reason: str
    strategy_name: str
    factors: Dict[str, Any]
    requires_approval: bool = False
    escalate: bool = False
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_auto_fix": self.should_auto_fix,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "escalate": self.escalate,
            "factors": self.factors,
            "warnings": self.warnings,
        }
    
class BaseStrategy(ABC):
    def __init__(
            self,
            min_confidence: float = 0.85,
            max_blast_radius: int = 10,
            enable_approval_flow: bool = True,
    ):
        self.min_confidence = min_confidence
        self.max_blast_radius = max_blast_radius
        self.enable_approval_flow = enable_approval_flow
        self.name = self.__class__.__name__

        logger.info(
            "strategy_initialized",
            strategy=self.name,
            min_confidence=min_confidence,
            max_blast_radius=max_blast_radius,
        )
    
    @abstractmethod
    def calculate_confidence(
        self,
        analysis: AnalysisResult,
        incident: Incident,
        context: ExecutionContext,
    ) -> float:
        pass

    @abstractmethod
    def should_trust_source(
        self,
        analysis: AnalysisResult,
        incident: Incident,
    ) -> bool:
        pass

    def decide(
        self,
        analysis: AnalysisResult,
        incident: Incident,
        context: ExecutionContext,
        similar_incidents: Optional[list] = None
    ) -> DecisionResult:
        factors = {}
        warnings = []

        if analysis.fixability != Fixability.AUTO:
            return DecisionResult(
                should_auto_fix=False,
                confidence=0.0,
                reason=f"Fixability is {analysis.fixability.value}, not auto",
                strategy_name=self.name,
                factors={"fixability": analysis.fixability.value},
                escalate=True,
            )
        
        confidence = self.calculate_confidence(analysis, incident, context)
        factors["calculated_confidence"] = confidence
        factors["min_threshold"] = self.min_confidence

        if confidence < self.min_confidence:
            return DecisionResult(
                should_auto_fix=False,
                confidence=confidence,
                reason=f"Confidence {confidence:.2f} below threshold {self.min_confidence}",
                strategy_name=self.name,
                factors=factors,
                requires_approval=True,
            )
        
        trust_source = self.should_trust_source(analysis, incident)
        factors["trust_source"] = trust_source

        if not trust_source:
            warnings.append("Source not fully trusted")

        if context.is_production():
            factors["environment"] = "production"

            if confidence < 0.95:
                return DecisionResult(
                    should_auto_fix=False,
                    confidence=confidence,
                    reason="Production requires 95%+ confidence",
                    strategy_name=self.name,
                    factors=factors,
                    requires_approval=True,
                )
            
        if similar_incidents:
            success_rate = self._calculate_success_rate(similar_incidents)
            factors["similar_success_rate"] = success_rate

            if success_rate < 0.7:
                warnings.append(f"Similar incidents have low success rate: {success_rate:.2f}")

        return DecisionResult(
            should_auto_fix=True,
            confidence=confidence,
            reason="All criteria met for auto-fix",
            strategy_name=self.name,
            factors=factors,
            requires_approval=context.requires_approval,
            warnings=warnings,
        )
    
    def _calculate_success_rate(self, similar_incidents: list) -> float:
        if not similar_incidents:
            return 0.0
        
        successful = sum(
            1 for inc in similar_incidents
            if inc.get("outcome") == "success"
        )
        return successful / len(similar_incidents)
    
    def apply_blast_radius_check(
            self,
            incident: Incident,
            context: ExecutionContext,
    ) -> tuple[bool, str]:
        estimated_radius = self._estimate_blast_radius(incident, context)

        if estimated_radius > self.max_blast_radius:
            return False, f"Blast radius {estimated_radius} exceeds max {self.max_blast_radius}"

        return True, f"Blast radius {estimated_radius} exceeds max {self.max_blast_radius}"
    
    def _estimate_blast_radius(
            self,
            incident: Incident,
            context: ExecutionContext,
    ) -> int:
        radius = 1

        if context.namespace == "production":
            radius *= 3
        
        if incident.severity.value in ["critical", "high"]:
            radius *= 2
        
        service = incident.get_service_name()
        if service and "api" in service.lower():
            radius *= 2

        return radius