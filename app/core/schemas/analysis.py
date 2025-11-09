# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import Fixability, FailureType, ConfidenceLevel

class AnalysisRequest(BaseModel):
    """ Request to analyze an incident """
    incident_id: str = Field(..., description="Incident ID to analyze")
    force_reanalysis: bool = Field(False, description='Force re-analysis even if already analyzed')
    include_similar: bool = Field(True, description="Include similar incidents in response")

class AnalysisResponse(BaseModel):
    """ Response from anaylsis. """
    incident_id: str
    category: FailureType
    root_cause: str
    fixability: Fixability
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel

    # Supporting evidence
    similar_incidents_count: int = 0
    slack_threads_count: int = 0

    # Suggestions
    suggested_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_fix_duration_seconds: Optional[int] = None

    # Metadata
    analyzed_at: datetime
    analysis_duration_ms: Optional[int] = None

class AnalysisDetailResponse(AnalysisResponse):
    """ Detailed analysis response with full evidence """
    similar_incidents: list[dict] = Field(default_factory=list)
    slack_threads: list[dict] = Field(default_factory=list)
    documentation_links: list[str] = Field(default_factory=list)

    confidence_breakdown: dict = Field(
        default_factory=dict,
        description="Breakdown of confidence components"
    )

class ConfidenceBreakdown(BaseModel):
    """ Detailed confidence score breakdown """
    final_score: float = Field(..., ge=0.0, le=1.0)
    level: ConfidenceLevel

    # Components
    llm_confidence: float
    llm_contribution: float
    similarity_score: float
    similarity_contribution: float
    historical_success_rate: float
    historical_contribution: float

    # Adjustments
    recency_boost: float = 0.9
    source_penalty: float = 0.0

    # Context
    num_similar_incidents: int
    dominant_signal: str
    weakest_signal: str

class SimilarIncident(BaseModel):
    """ Similar incident from RAG retrieval """
    incident_id: str
    source: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    root_cause: Optional[str] = None
    outcome: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_time_seconds: Optional[int] = None
    context: dict = Field(default_factory=dict)