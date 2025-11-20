# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Confidence Scorer - Combines multiple signals to calculate final confidence.

This module implements a weighted scoring system that combines:
- LLM confidence (40% weight)
- Similarity score from RAG (30% weight)
- Historical success rate (30% weight)

The scorer also applies adjustments based on:
- Recency of similar incidents
- Source type and reliability
- Number of supporting data points
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from app.core.enums import ConfidenceLevel, IncidentSource
from app.core.schemas.analysis import ConfidenceBreakdown
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ConfidenceScorer:
    """
    Calculate final confidence scores by combining multiple signals.
    
    Uses a weighted average approach:
    - 40% from LLM's own confidence assessment
    - 30% from vector similarity scores (RAG)
    - 30% from historical success rate of similar incidents
    
    Additional adjustments:
    - Recency boost for recent similar incidents
    - Source reliability factor
    - Penalty for insufficient data points
    """
    
    WEIGHT_LLM = 0.4
    WEIGHT_SIMILARITY = 0.3
    WEIGHT_HISTORICAL = 0.3
    
    RECENCY_HALF_LIFE_DAYS = 30 
    
    MIN_SIMILAR_INCIDENTS = 3
    
    SOURCE_RELIABILITY = {
        IncidentSource.GITHUB: 1.0,
        IncidentSource.ARGOCD: 1.0,
        IncidentSource.KUBERNETES: 0.95,
        IncidentSource.GITLAB: 1.0,
        IncidentSource.JENKINS: 0.9,
        IncidentSource.MANUAL: 0.8,
    }
    
    def __init__(self):
        """Initialize the confidence scorer."""
        logger.info(
            "ConfidenceScorer initialized",
            extra={
                "weight_llm": self.WEIGHT_LLM,
                "weight_similarity": self.WEIGHT_SIMILARITY,
                "weight_historical": self.WEIGHT_HISTORICAL,
            }
        )
    
    def calculate_confidence(
        self,
        llm_confidence: float,
        similar_incidents: List[Dict[str, Any]],
        source: Optional[IncidentSource] = None,
    ) -> ConfidenceBreakdown:
        """
        Calculate final confidence score from multiple signals.
        
        Args:
            llm_confidence: Confidence score from LLM (0.0-1.0)
            similar_incidents: List of similar incidents from RAG with metadata
            source: Source of the incident (for reliability adjustment)
            
        Returns:
            ConfidenceBreakdown with detailed scoring information
        """
        logger.debug(
            "Calculating confidence score",
            extra={
                "llm_confidence": llm_confidence,
                "num_similar": len(similar_incidents),
                "source": source.value if source else None,
            }
        )
        
        llm_conf = max(0.0, min(1.0, llm_confidence))
        
        similarity_score = self._calculate_similarity_score(similar_incidents)
        
        historical_rate = self._calculate_historical_success_rate(similar_incidents)
        
        base_score = (
            self.WEIGHT_LLM * llm_conf +
            self.WEIGHT_SIMILARITY * similarity_score +
            self.WEIGHT_HISTORICAL * historical_rate
        )
        
        llm_contribution = self.WEIGHT_LLM * llm_conf
        similarity_contribution = self.WEIGHT_SIMILARITY * similarity_score
        historical_contribution = self.WEIGHT_HISTORICAL * historical_rate
        
        recency_boost = self._calculate_recency_boost(similar_incidents)
        
        source_penalty = self._calculate_source_penalty(source)
        
        final_score = base_score * (1.0 + recency_boost) * (1.0 - source_penalty)
        
        final_score = max(0.0, min(1.0, final_score))
        
        level = ConfidenceLevel.from_score(final_score)
        
        signals = {
            "llm": llm_contribution,
            "similarity": similarity_contribution,
            "historical": historical_contribution,
        }
        dominant_signal = max(signals, key=signals.get)
        weakest_signal = min(signals, key=signals.get)
        
        logger.info(
            f"Confidence calculated: {final_score:.3f} ({level.value})",
            extra={
                "final_score": final_score,
                "level": level.value,
                "llm_contribution": llm_contribution,
                "similarity_contribution": similarity_contribution,
                "historical_contribution": historical_contribution,
                "recency_boost": recency_boost,
                "source_penalty": source_penalty,
            }
        )
        
        return ConfidenceBreakdown(
            final_score=final_score,
            level=level,
            llm_confidence=llm_conf,
            llm_contribution=llm_contribution,
            similarity_score=similarity_score,
            similarity_contribution=similarity_contribution,
            historical_success_rate=historical_rate,
            historical_contribution=historical_contribution,
            recency_boost=recency_boost,
            source_penalty=source_penalty,
            num_similar_incidents=len(similar_incidents),
            dominant_signal=dominant_signal,
            weakest_signal=weakest_signal,
        )
    
    def _calculate_similarity_score(
        self,
        similar_incidents: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate aggregate similarity score from similar incidents.
        
        Uses a weighted average of similarity scores, giving more weight
        to top matches.
        
        Args:
            similar_incidents: List of similar incidents with 'similarity' scores
            
        Returns:
            Aggregate similarity score (0.0-1.0)
        """
        if not similar_incidents:
            return 0.0
        
        similarities = []
        for incident in similar_incidents[:5]: 
            similarity = incident.get("similarity", 0.0)
            if isinstance(similarity, (int, float)):
                similarities.append(float(similarity))
        
        if not similarities:
            return 0.0
        
        weights = [0.4, 0.25, 0.2, 0.1, 0.05]
        
        total_score = 0.0
        total_weight = 0.0
        
        for i, similarity in enumerate(similarities):
            weight = weights[i] if i < len(weights) else 0.05
            total_score += similarity * weight
            total_weight += weight
        
        if total_weight > 0:
            score = total_score / total_weight
        else:
            score = 0.0
        
        if len(similarities) < self.MIN_SIMILAR_INCIDENTS:
            penalty = len(similarities) / self.MIN_SIMILAR_INCIDENTS
            score *= penalty
        
        return max(0.0, min(1.0, score))
    
    def _calculate_historical_success_rate(
        self,
        similar_incidents: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate success rate from historical similar incidents.
        
        Args:
            similar_incidents: List of similar incidents with 'outcome' field
            
        Returns:
            Success rate (0.0-1.0)
        """
        if not similar_incidents:
            return 0.0
        
        relevant_incidents = similar_incidents[:10]
        
        total = 0
        successful = 0
        
        for incident in relevant_incidents:
            outcome = incident.get("outcome", "").lower()
            
            if outcome:
                total += 1
                if outcome == "success":
                    successful += 1
        
        if total == 0:
            return 0.5  
        
        success_rate = successful / total
        
        confidence_adjustment = min(1.0, total / 10.0) 
        
        adjusted_rate = 0.5 + (success_rate - 0.5) * confidence_adjustment
        
        return max(0.0, min(1.0, adjusted_rate))
    
    def _calculate_recency_boost(
        self,
        similar_incidents: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate boost based on recency of similar incidents.
        
        Recent incidents are more relevant than old ones.
        
        Args:
            similar_incidents: List of similar incidents with 'resolved_at' timestamps
            
        Returns:
            Recency boost factor (-0.1 to +0.1)
        """
        if not similar_incidents:
            return 0.0
        
        now = datetime.utcnow()
        recency_scores = []
        
        for incident in similar_incidents[:5]: 
            resolved_at = incident.get("resolved_at")
            
            if resolved_at:
                if isinstance(resolved_at, str):
                    try:
                        resolved_at = datetime.fromisoformat(resolved_at.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        continue
                
                age_days = (now - resolved_at).total_seconds() / 86400
                
                decay_factor = 0.5 ** (age_days / self.RECENCY_HALF_LIFE_DAYS)
                recency_scores.append(decay_factor)
        
        if not recency_scores:
            return 0.0
        
        avg_recency = sum(recency_scores) / len(recency_scores)
        
        boost = (avg_recency - 0.5) * 0.2
        
        return max(-0.1, min(0.1, boost))
    
    def _calculate_source_penalty(
        self,
        source: Optional[IncidentSource]
    ) -> float:
        """
        Calculate penalty based on source reliability.
        
        Some sources are more reliable than others.
        
        Args:
            source: Incident source
            
        Returns:
            Penalty factor (0.0-0.2)
        """
        if not source:
            return 0.1 
        
        reliability = self.SOURCE_RELIABILITY.get(source, 0.8)
        
        penalty = (1.0 - reliability)
        
        return max(0.0, min(0.2, penalty))
    
    def calculate_simple_confidence(
        self,
        llm_confidence: float,
        similarity_score: float,
        historical_success_rate: float,
    ) -> float:
        """
        Calculate confidence with explicit component values.
        
        Useful when you already have the individual scores calculated.
        
        Args:
            llm_confidence: LLM confidence (0.0-1.0)
            similarity_score: Similarity score (0.0-1.0)
            historical_success_rate: Historical success rate (0.0-1.0)
            
        Returns:
            Final confidence score (0.0-1.0)
        """
        llm_conf = max(0.0, min(1.0, llm_confidence))
        sim_score = max(0.0, min(1.0, similarity_score))
        hist_rate = max(0.0, min(1.0, historical_success_rate))
        
        final_score = (
            self.WEIGHT_LLM * llm_conf +
            self.WEIGHT_SIMILARITY * sim_score +
            self.WEIGHT_HISTORICAL * hist_rate
        )
        
        return max(0.0, min(1.0, final_score))
    
    def get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """
        Convert numeric confidence to a confidence level.
        
        Args:
            confidence: Numeric confidence score (0.0-1.0)
            
        Returns:
            ConfidenceLevel enum
        """
        return ConfidenceLevel.from_score(confidence)
    
    def explain_confidence(
        self,
        breakdown: ConfidenceBreakdown
    ) -> str:
        """
        Generate human-readable explanation of confidence score.
        
        Args:
            breakdown: ConfidenceBreakdown object
            
        Returns:
            Explanation string
        """
        parts = [
            f"Final Confidence: {breakdown.final_score:.2f} ({breakdown.level.value})",
            "",
            "Components:",
            f"  • LLM Confidence: {breakdown.llm_confidence:.2f} (contributes {breakdown.llm_contribution:.2f})",
            f"  • Similarity Score: {breakdown.similarity_score:.2f} (contributes {breakdown.similarity_contribution:.2f})",
            f"  • Historical Success: {breakdown.historical_success_rate:.2f} (contributes {breakdown.historical_contribution:.2f})",
            "",
            "Adjustments:",
            f"  • Recency Boost: {breakdown.recency_boost:+.2f}",
            f"  • Source Penalty: {breakdown.source_penalty:.2f}",
            "",
            f"Based on {breakdown.num_similar_incidents} similar incident(s)",
            f"Dominant signal: {breakdown.dominant_signal}",
            f"Weakest signal: {breakdown.weakest_signal}",
        ]
        
        return "\n".join(parts)


def score_confidence(
    llm_confidence: float,
    similar_incidents: List[Dict[str, Any]],
    source: Optional[IncidentSource] = None,
) -> Tuple[float, ConfidenceBreakdown]:
    """
    Convenience function to calculate confidence score.
    
    Args:
        llm_confidence: LLM confidence (0.0-1.0)
        similar_incidents: List of similar incidents
        source: Incident source
        
    Returns:
        Tuple of (final_score, breakdown)
    """
    scorer = ConfidenceScorer()
    breakdown = scorer.calculate_confidence(llm_confidence, similar_incidents, source)
    return breakdown.final_score, breakdown
