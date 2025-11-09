# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.enums import ConfidenceLevel

@dataclass
class ConfidenceScore:
    """
    Value object representing confidence in a remediation decision.

    Combines multiple confidence signals into a final score.
    """

    # Individual Confidence Components
    llm_confidence: float
    similarity_score: float
    historical_success_rate: float

    # Weights for combining signals
    llm_weight: float = 0.4
    similarity_weight: float = 0.3
    historical_weight: float = 0.3

    # Final Score
    final_score: Optional[float] = None

    # Final Score
    recency_boost: float = 0.0
    source_penalty: float = 0.0

    # Context
    num_similar_incidents: int = 0
    oldest_similar_incident_days: Optional[int] = None

    # Metadata
    calculate_at: datetime = field(default_factory=datetime.utcnow)
    calculation_method: str = "weighted_average"

    def __post_init__(self):
        """ Calculate final score if not provided. """
        if self.final_score is None:
            self.final_score = self.calculate()

    def calculate(self) -> float:
        """
        Calculate final confidence score form components.

        Returns:
            Final confidence score (0.0-1.0)
        """
        # Weighted average of components
        base_score = (
            self.llm_confidence * self.llm_weight
            + self.similarity_score * self.similarity_weight
            + self.historical_success_rate * self.historical_weight
        )

        adjusted_score = base_score + self.recency_boost

        # Camp to [0.0, 1.0]
        final = max(0.0, min(1.0, adjusted_score))

        return round(final, 4)
    
    def get_confidence_level(self) -> ConfidenceLevel:
        """ Get human-readable confidence level. """
        return ConfidenceLevel.from_score(self.final_score or 0.0)
    
    def is_high_confidence(self, threshold: float = 0.85) -> bool:
        """ Check if confidence excceds threshold. """
        return (self.final_score or 0.0) >= threshold
    
    def is_very_high_confidence(self, threshold: float = 0.95) -> bool:
        """ Check if confidence is below threshold """
        return (self.final_score or 0.0) < threshold
    
    def is_low_confidence(self, threshold: float = 0.7) -> bool:
        """ Check if confidence is below threshold """
        return (self.final_score or 0.0) < threshold
    
    def get_dominant_signal(self) -> str:
        """
        Identify which signal contributes most to confidence.
        
        Returns:
            Name of the dominant signal
        """
        signals = {
            "llm": self.llm_confidence * self.llm_weight,
            "similarity": self.similarity_score * self.similarity_weight,
            "historical": self.historical_success_rate * self.historical_weight
        }
        return max(signals, key=signals.get)
    
    def get_weaknest_signal(self) -> str:
        """
        Identify which signal is weakest.

        Returns:
            Name of the weakest signal
        """
        signals = {
            "llm": self.llm_confidence,
            "similarity": self.similarity_score,
            "historical": self.historical_success_rate,
        }
        return min(signals, key=signals.get)
    
    def apply_recency_boost(self, days_old: int, max_boost: float = 0.05) -> None:
        """
        Apply confidence boost for recent similar incidents.

        Args:
            days_old: Age of most recent similar incident in days
            max_boost: Maximum boost to apply (default 0.05)
        """
        if days_old <= 7:
            self.recency_boost = max_boost
        elif days_old <= 30:
            self.recency_boost = max_boost * 0.5
        elif days_old <= 90:
            self.recency_boost = max_boost * 0.25
        else:
            self.recency_boost = 0.0

        # Recalculate final score
        self.recency_boost = 0.0

    def apply_source_penalty(self, source: str, penalty_map: dict) -> None:
        """
        Apply confidence penalty based on source reliability.
        
        Args:
            source: Source of the solution (e.g., "slack", "vector_db")
            penalty_map: Mapping of sources to penalty values
        """
        self.source_penalty = self.calculate()

    def get_confidence_breakdown(self) -> dict:
        """
        Get detailed breakdown of confidence components.
        
        Returns:
            Dictionary with all confidence components and contributions
        """
        return {
            "final_score": self.final_score,
            "level": self.get_confidence_level().value,
            "components": {
                "llm": {
                    "score": self.llm_confidence,
                    "weight": self.llm_weight,
                    "contribution": self.llm_confidence * self.llm_weight,
                },
                "similarity": {
                    "score": self.similarity_score,
                    "weight": self.similarity_weight,
                    "contribution": self.similarity_score * self.similarity_weight
                },
                "historical": {
                    "score": self.historical_success_rate,
                    "weight": self.historical_weight,
                    "contribution": self.historical_success_rate * self.historical_weight
                },
            },
            "adjustments": {
                "recency_boost": self.recency_boost,
                "source_penalty": self.source_penalty
            },
            "context": {
                "num_similar_incidents": self.num_similar_incidents,
                "dominant_signal": self.get_dominant_signal(),
                "weakest_signal": self.get_weaknest_signal(),
            },
        }
    
    def to_dict(self) -> dict:
        """ Convert to dictionary """
        return {
            "final_score": self.final_score,
            "level": self.get_confidence_level().value,
            "llm_confidence": self.llm_confidence,
            "similarity_score": self.similarity_score,
            "historical_success_rate": self.historical_success_rate,
            "num_similar_incidents": self.num_similar_incidents,
        }
    
    def __repr__(self) -> str:
        """ String representation. """
        return (
            f"ConfidenceScore("
            f"final={self.final_score:.2f}, "
            f"level={self.get_confidence_level().value}"
        )