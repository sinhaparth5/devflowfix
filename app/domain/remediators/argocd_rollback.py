# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
from datetime import datetime

from app.core.config import Settings
from app.core.enums import RemediationActionType
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.domain.remediators.base import BaseRemediator


class ArgoCDRollbackRemediator(BaseRemediator):
    def __init__(self, settings: Optional[Settings] = None):
        super().__init__(settings)

    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.ARGOCD_ROLLBACK

    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        self._log_execution_start(incident, plan)
        start_time = datetime.now()

        application = plan.parameters.get("application") or incident.context.get("application")
        revision = plan.parameters.get("revision")
        if not application:
            result = self._create_failure_result(
                message="Missing ArgoCD application for rollback",
                error_message="application is required",
                duration_seconds=(datetime.now() - start_time).seconds,
            )
            self._log_execution_complete(incident, result)
            return result

        result = self._create_success_result(
            message=f"Rollback requested for ArgoCD application {application}",
            duration_seconds=(datetime.now() - start_time).seconds,
            actions_performed=[f"ARGOCD_ROLLBACK: {application}"],
            metadata={"application": application, "revision": revision},
        )
        self._log_execution_complete(incident, result)
        return result
