# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import structlog

from app.domain.strategies.base import BaseStrategy
from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext
from app.core.enums import IncidentSource, Severity

logger = structlog.get_logger(__name__)

class HybridStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(
            min_confidence=0.85,
            max_blast_radius=10,
            enable_approval_flow=True,
        )

        self.signal_weights = {
            "llm": 0.35,
            "vector_similarity": 0.25,
            "historical_success": 0.30,
            "slack_context": 0.10,
        }

    def calculate_confidence(self, 
                            analysis: AnalysisResult, 
                            incident: Incident, 
                            context: ExecutionContext
                            ) -> float:
        signals = {}

        signals["llm"] = analysis.llm_confidence or analysis.confidence

        if analysis.similar_incidents:
            signals["vector_similarity"] = self._calculate_similarity_score(
                analysis.similar_incidents
            )
        else:
            signals["vector_similarity"] = 0.0

        signals["historical_success"] = self._calculate_historical_score(
            analysis.similar_incidents
        )
        signals["slack_context"] = self._calculate_slack_score(
            analysis.slack_threads
        )

        weighted_confidence = sum(
            signals[signal] * self.signal_weights[signal]
            for signal in signals
        )

        weighted_confidence = self._apply_adjustments(
            weighted_confidence,
            incident,
            context,
        )

        logger.debug(
            "hybrid_confidence_calculated",
            signals=signals,
            weights=self.signal_weights,
            final=weighted_confidence,
        )

        return min(weighted_confidence, 0.99)
    
    def should_trust_source(self, 
                            analysis: AnalysisResult, 
                            incident: Incident,
                            ) -> bool:
        trust_score = 0.0

        if incident.source in [IncidentSource.GITHUB, IncidentSource.KUBERNETES, IncidentSource.ARGOCD]:
            trust_score += 0.3

        if analysis.similar_incidents and len(analysis.similar_incidents) >= 2:
            trust_score += 0.3

        if analysis.slack_threads and len(analysis.slack_threads) > 0:
            trust_score += 0.2
        
        if analysis.llm_confidence and analysis.llm_confidence > 0.85:
            trust_score += 0.2

        return trust_score >= 0.6
    
    def _calculate_similarity_score(self, similar_incidents: list) -> float:
        if not similar_incidents:
            return 0.0
        
        top_3 = similar_incidents[:3]
        similarities = [inc.get("similarity", 0) for inc in top_3]

        avg_similarity = sum(similarities) / len(similarities)

        if avg_similarity > 0.9:
            return 0.95
        elif avg_similarity > 0.8:
            return 0.85
        elif avg_similarity > 0.7:
            return 0.75
        else:
            return avg_similarity * 0.9
        
    def _calculate_historical_score(self, similar_incidents: list) -> float:
        if not similar_incidents:
            return 0.5
        
        resolved = [
            inc for inc in similar_incidents
            if inc.get("outcome") == "success"
        ]

        if not resolved:
            return 0.3
        
        success_rate = len(resolved) / len(similar_incidents)

        avg_resolution_time = sum(
            inc.get("resolution_time_seconds", 300)
            for inc in resolved
        ) / len(resolved)

        if avg_resolution_time < 60:
            time_bonus = 0.1
        elif avg_resolution_time < 300:
            time_bonus = 0.05
        else:
            time_bonus = 0.0

        return min(success_rate + time_bonus, 1.0)
    
    def _calculate_slack_score(self, slack_threads: list) -> float:
        if not slack_threads:
            return 0.5
        
        resolved_threads = [
            t for t in slack_threads
            if t.get("resolved", False)
        ]

        if not resolved_threads:
            return 0.6
        
        has_resolution_steps = any(
            "steps" in t or "solution" in str(t).lower()
            for t in resolved_threads
        )

        if has_resolution_steps:
            return 0.9
        
        return 0.75
    
    def _apply_adjustments(
            self,
            confidence: float,
            incident: Incident,
            context: ExecutionContext,
    ) -> float:
        adjusted = confidence

        if incident.severity == Severity.CRITICAL:
            adjusted *= 0.95

        if context.is_production():
            adjusted *= 0.97

        if context.dry_run:
            adjusted = min(adjusted * 1.05, 1.0)

        namespace = incident.get_namespace()
        if namespace and namespace in ["kube-system", "default"]:
            adjusted *= 0.90

        return adjusted
