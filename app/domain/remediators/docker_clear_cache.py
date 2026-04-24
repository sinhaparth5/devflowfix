# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
from datetime import datetime

from app.core.config import Settings
from app.core.enums import RemediationActionType
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.domain.remediators.base import BaseRemediator


class DockerClearCacheRemediator(BaseRemediator):
    def __init__(self, settings: Optional[Settings] = None):
        super().__init__(settings)

    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.DOCKER_CLEAR_CACHE

    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        self._log_execution_start(incident, plan)
        start_time = datetime.now()

        scope = plan.parameters.get("scope", "builder")
        result = self._create_success_result(
            message=f"Docker cache clear requested for {scope}",
            duration_seconds=(datetime.now() - start_time).seconds,
            actions_performed=[f"DOCKER_CLEAR_CACHE: {scope}"],
            metadata={"scope": scope},
        )
        self._log_execution_complete(incident, result)
        return result
