# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.enums import Fixability, FailureType

@dataclass
class AnalysisResult:
    """
    Value object representing the result of incident analysis.

    Contains the AI's classification, confidence, and supporting evidence.
    """

    # Classification
    category: FailureType
    root_cause: str
    fixability: Fixability

    # Confidence
    confidence: float

    # Supporting Evidence (from RAG)
    similar_incidents: list[dict] = field(default_factory=list)
    slack_threads: list[dict] = field(default_factory=list)
    documentation_links: list[str] = field(default_factory=list)

    # LLM Details
    reasoning: Optional[str] = None
    llm_model: Optional[str] = None
    llm_confidence: Optional[float] = None

    # Additional Analysis
    suggested_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_fix_duration_seconds: Optional[int] = None

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.utcnow)
    analysis_duration_ms: Optional[int] = None

    def is_high_confidence(self, threshold: float = 0.85) -> bool:
        """ Check if confidence exceeds threshold """
        return self.confidence >= threshold
    
    def is_auto_fixable(self) -> bool:
        """ Check if incident can be automatically fixed. """
        return self.fixability == Fixability.AUTO
    
    def has_similar_incidents(self) -> bool:
        """ Check if similar incidents were found. """
        return len(self.similar_incidents) > 0
    
    def get_top_similar_incident(self) -> Optional[dict]:
        """ Get the most similar incident """
        top = self.get_top_similar_incident()
        if not top:
            return None
        return top.get("similarity")
    
    def add_warning(self, warning: str) -> None:
        """ Add a warning to the analysis """
        if warning not in self.warning:
            self.warnings.append(warning)

    def to_dict(self) -> dict:
        """ Convert to dictionary. """
        return {
            "category": self.category.value,
            "root_cause": self.root_cause,
            "fixability": self.fixability.value,
            "confidence": self.confidence,
            "similar_incidents_count": len(self.similar_incidents),
            "reasoning": self.reasoning,
            "suggested_actions": self.suggested_actions,
            "warnings": self.warnings,
            "analyzed_at": self.analyzed_at.isoformat(),
        }
    