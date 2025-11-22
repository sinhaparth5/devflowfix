# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
import asyncio
import structlog

from app.core.models.incident import Incident
from app.core.models.analysis import AnalysisResult
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.models.context import ExecutionContext
from app.core.enums import (
    IncidentSource, Severity, Outcome, Environment,
    StrategyType, NotifcationType
)
from app.domain.strategies.base import DecisionResult
from app.domain.strategies.factory import StrategyFactory
from app.services.decision import DecisionService
from app.services.analyzer import AnalyzerService
from app.services.remediator import RemediatorService
from app.services.retriever import Retri