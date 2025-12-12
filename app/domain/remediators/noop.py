# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
No-Op Remediator

A remediator that performs no action, used for notification-only incidents.
"""

from typing import Optional

from app.domain.remediators.base import BaseRemediator
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import RemediationActionType
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class NoopRemediator(BaseRemediator):
    """
    No-operation remediator.

    This remediator performs no actual remediation action.
    Used for incidents that only require notification without remediation.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize no-op remediator."""
        super().__init__(settings)

    def get_action_type(self) -> RemediationActionType:
        """Get the action type this remediator handles."""
        return RemediationActionType.NOOP

    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """
        Execute no-op remediation.

        Args:
            incident: Incident to process
            plan: Remediation plan (ignored)

        Returns:
            RemediationResult indicating no action taken
        """
        self.logger.info(
            "noop_remediation",
            incident_id=incident.incident_id,
            action=plan.action_type.value,
        )

        return self._create_success_result(
            message="No action taken (notify only)",
            actions_performed=["NOOP"],
        )
