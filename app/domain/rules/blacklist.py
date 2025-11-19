# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Set
import structlog

from app.domain.rules.base import BaseRule
from app.core.models.analysis import AnalysisResult
from app.core.models.incident import Incident
from app.core.models.context import ExecutionContext

logger = structlog.get_logger(__name__)

class BlacklistRule(BaseRule):
    def __init__(
            self,
            blacklisted_services: Optional[Set[str]] = None,
            blacklisted_namespaces: Optional[Set[str]] = None,
            blacklisted_repos: Optional[Set[str]] = None,       
    ):
        super().__init__("BlacklistRule")

        self.blacklisted_services = blacklisted_services or {
            "payment-service",
            "auth-service",
            "billing-api",   
        }

        self.blacklisted_namespaces = blacklisted_namespaces or {
            "kube-system",
            "kube-public",
            "payment",
            "financial",
        }

        self.blacklisted_repos = blacklisted_repos or {
            "production-configs",
            "secrets-repo",
        }

        self.escalate_on_failure = True

    def evaluate(self, 
                incident: Incident,
                context: ExecutionContext,
                analysis: Optional[AnalysisResult] = None,
                ) -> bool:
        service = incident.get_service_name()
        if service and service in self.blacklisted_services:
            return self._set_failure(f"Service '{service}' is blacklisted")
        
        namespace = incident.get_namespace() or context.namespace
        if namespace and namespace in self.blacklisted_namespaces:
            return self._set_failure(f"Namespace '{namespace}' is blacklisted")
        
        repo = incident.get_repository() or context.repository
        if repo and repo in self.blacklisted_repos:
            return self._set_failure(f"Repository '{repo}' is blacklisted")
        
        return True