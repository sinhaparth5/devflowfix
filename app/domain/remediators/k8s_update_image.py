# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
from datetime import datetime

from app.core.config import Settings
from app.core.enums import RemediationActionType
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.domain.remediators.base import BaseRemediator


class K8sUpdateImageRemediator(BaseRemediator):
    def __init__(self, settings: Optional[Settings] = None):
        super().__init__(settings)

    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.K8S_UPDATE_IMAGE

    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        self._log_execution_start(incident, plan)
        start_time = datetime.now()

        namespace = plan.parameters.get("namespace") or incident.get_namespace()
        workload = plan.parameters.get("deployment") or incident.context.get("deployment")
        image = plan.parameters.get("image")
        if not namespace or not workload or not image:
            result = self._create_failure_result(
                message="Missing Kubernetes image update parameters",
                error_message="namespace, deployment, and image are required",
                duration_seconds=(datetime.now() - start_time).seconds,
            )
            self._log_execution_complete(incident, result)
            return result

        result = self._create_success_result(
            message=f"Image update requested for {workload}",
            duration_seconds=(datetime.now() - start_time).seconds,
            actions_performed=[f"K8S_UPDATE_IMAGE: {namespace}/{workload} -> {image}"],
            metadata={"namespace": namespace, "deployment": workload, "image": image},
        )
        self._log_execution_complete(incident, result)
        return result
