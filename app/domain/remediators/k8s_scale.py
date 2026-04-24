# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
from datetime import datetime

from app.core.config import Settings
from app.core.enums import RemediationActionType
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.domain.remediators.base import BaseRemediator


class K8sScaleRemediator(BaseRemediator):
    def __init__(self, settings: Optional[Settings] = None):
        super().__init__(settings)

    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.K8S_SCALE_DEPLOYMENT

    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        self._log_execution_start(incident, plan)
        start_time = datetime.now()

        namespace = plan.parameters.get("namespace") or incident.get_namespace()
        deployment = plan.parameters.get("deployment") or incident.context.get("deployment")
        replicas = plan.parameters.get("replicas")
        if not namespace or not deployment or replicas is None:
            result = self._create_failure_result(
                message="Missing Kubernetes scaling parameters",
                error_message="namespace, deployment, and replicas are required",
                duration_seconds=(datetime.now() - start_time).seconds,
            )
            self._log_execution_complete(incident, result)
            return result

        result = self._create_success_result(
            message=f"Scaling requested for deployment {deployment} to {replicas} replicas",
            duration_seconds=(datetime.now() - start_time).seconds,
            actions_performed=[f"K8S_SCALE_DEPLOYMENT: {namespace}/{deployment} -> {replicas}"],
            metadata={"namespace": namespace, "deployment": deployment, "replicas": replicas},
        )
        self._log_execution_complete(incident, result)
        return result
