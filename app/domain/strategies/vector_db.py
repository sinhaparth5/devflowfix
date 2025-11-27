# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import structlog

from app.domain.strategies.base import BaseStrategy
from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext

logger = structlog.get_logger(__name__)

class VectorDBStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(
            min_confidence=0.80,
            max_blast_radius=12,
            enable_approval_flow=True,
        )

        self.high_similarity_threshold = 0.90
        self.medium_similarity_threshold = 0.75

    def calculate_confidence(self, 
                            analysis: AnalysisResult, 
                            incident: Incident, 
                            context: ExecutionContext
                            ) -> float:
        if not analysis.similar_incidents:
            return analysis.confidence * 0.7
        
        top_similarity = analysis.similar_incidents[0].get("similarity", 0)

        if top_similarity >= self.high_similarity_threshold:
            confidence_boost = 0.95
        elif top_similarity >= self.medium_similarity_threshold:
            confidence_boost = 0.85
        else:
            confidence_boost = max(top_similarity, 0.6)

        num_similar = len(analysis.similar_incidents)
        if num_similar >= 5:
            confidence_boost = min(confidence_boost * 1.05, 1.0)
        elif num_similar >= 3:
            confidence_boost = min(confidence_boost * 1.02, 1.0)

        success_rate = self._calculate_success_rate(analysis.similar_incidents)
        if success_rate > 0.8:
            confidence_boost = min(confidence_boost * 1.03, 1.0)

        recency_boost = self._caluclate_recency_boost(analysis.similar_incidents)
        confidence_boost = min(confidence_boost + recency_boost, 1.0)

        final_confidence = (analysis.confidence * 0.4) + (confidence_boost * 0.6)

        if context.is_production():
            final_confidence *= 0.98

        logger.debug(
            "vector_confidence_calculated",
            top_similarity=top_similarity,
            num_similar=num_similar,
            success_rate=success_rate,
            final=final_confidence,
        )

        return final_confidence
    
    def should_trust_source(self, 
                            analysis: AnalysisResult, 
                            incident: Incident,
                            ) -> bool:
        if not analysis.similar_incidents:
            return False
        
        top_similarity = analysis.similar_incidents[0].get("similarity", 0)
        if top_similarity < 0.70:
            return False
        
        if len(analysis.similar_incidents) < 2:
            return top_similarity > 0.85
        
        successful_similar = [
            inc for inc in analysis.similar_incidents
            if inc.get("outcome") == "success"
        ]

        if not successful_similar:
            return False
        
        return len(successful_similar) >= 2 or top_similarity > 0.90
    
    def _calculate_recency_boost(self, similar_incident: list) -> float:
        if not similar_incident:
            return 0.0
        
        recent_count = 0
        for inc in similar_incident[:5]:
            resolved_at = inc.get("resolved_at")
            if resolved_at:
                from datetime import datetime, timezone, timedelta
                if isinstance(resolved_at, str):
                    resolved_at = datetime.fromisoformat(resolved_at)

                    age_days = (datetime.now(timezone.utc) - resolved_at).days

                    if age_days <= 7:
                        recent_count += 1

        if recent_count >= 3:
            return 0.05
        elif recent_count >= 1:
            return 0.02
        
        return 0.0