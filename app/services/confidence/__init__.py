# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Confidence Scoring Module

Provides confidence scoring functionality that combines multiple signals:
- LLM confidence assessments
- Vector similarity scores from RAG
- Historical success rates

The scorer uses weighted averaging and applies adjustments for:
- Recency of similar incidents
- Source reliability
- Sample size confidence intervals
"""

from app.services.confidence.scorer import (
    ConfidenceScorer,
    score_confidence,
)

__all__ = [
    "ConfidenceScorer",
    "score_confidence",
]
