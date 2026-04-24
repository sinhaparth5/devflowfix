# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Compatibility layer for legacy imports.

The application now uses ``app.dependencies`` as the single source of truth
for dependency wiring. This module re-exports the supported providers so older
imports continue to work without drifting into a second, inconsistent DI stack.
"""

from app.dependencies import (
    ServiceContainer,
    get_analyzer_service,
    get_db,
    get_decision_service,
    get_engine,
    get_event_processor,
    get_incident_repository,
    get_remediator_service,
    get_retriever_service,
    get_service_container,
    get_settings,
    get_session_local,
    get_vector_repository,
)

__all__ = [
    "ServiceContainer",
    "get_analyzer_service",
    "get_db",
    "get_decision_service",
    "get_engine",
    "get_event_processor",
    "get_incident_repository",
    "get_remediator_service",
    "get_retriever_service",
    "get_service_container",
    "get_settings",
    "get_session_local",
    "get_vector_repository",
]
