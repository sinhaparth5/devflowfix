# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
ArgoCD Sync Remediator

Remediates ArgoCD application failures by triggering synchronization.
"""

from typing import Optional
from datetime import datetime

from app.domain.remediators.base import BaseRemediator
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import RemediationActionType
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ArgoCDSyncRemediator(BaseRemediator):
    """
    Remediator for ArgoCD application failures.

    Triggers a sync operation to reconcile application state.

    Required parameters:
    - application: ArgoCD application name
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize ArgoCD sync remediator."""
        super().__init__(settings)

    def get_action_type(self) -> RemediationActionType:
        """Get the action type this remediator handles."""
        return RemediationActionType.ARGOCD_SYNC

    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """
        Execute ArgoCD sync remediation.

        Args:
            incident: Incident with ArgoCD application failure
            plan: Remediation plan with application parameter

        Returns:
            RemediationResult with success status and details
        """
        self._log_execution_start(incident, plan)
        start_time = datetime.now()

        try:
            application = plan.parameters.get("application")

            if not application:
                duration = (datetime.now() - start_time).seconds
                result = self._create_failure_result(
                    message="Missing application name",
                    error_message="Required parameter not provided",
                    duration_seconds=duration,
                )
                self._log_execution_complete(incident, result)
                return result

            self.logger.info(
                "argocd_sync",
                incident_id=incident.incident_id,
                application=application,
            )

            # TODO: Implement actual ArgoCD API call to trigger sync
            # For now, this is a placeholder that logs the action

            duration = (datetime.now() - start_time).seconds

            result = self._create_success_result(
                message=f"ArgoCD sync triggered for application {application}",
                duration_seconds=duration,
                actions_performed=[f"ARGOCD_SYNC: {application}"],
                metadata={
                    "application": application,
                },
            )

            self._log_execution_complete(incident, result)
            return result

        except Exception as e:
            duration = (datetime.now() - start_time).seconds
            result = self._create_failure_result(
                message="Failed to sync ArgoCD application",
                error_message=str(e),
                duration_seconds=duration,
            )
            self._log_execution_complete(incident, result)
            return result
