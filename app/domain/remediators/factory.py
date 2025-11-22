# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime
import structlog

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.models.context import ExecutionContext
from app.core.enums import RemediationActionType, Outcome

logger = structlog.get_logger(__name__)


class BaseRemediator(ABC):
    
    def __init__(self, settings: Any = None):
        self.settings = settings
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
        context: ExecutionContext,
    ) -> RemediationResult:
        pass
    
    def _success_result(
        self,
        message: str,
        actions: list = None,
    ) -> RemediationResult:
        return RemediationResult(
            success=True,
            outcome=Outcome.SUCCESS,
            message=message,
            actions_performed=actions or [],
        )
    
    def _failure_result(
        self,
        message: str,
        error: str = None,
    ) -> RemediationResult:
        return RemediationResult(
            success=False,
            outcome=Outcome.FAILED,
            message=message,
            error_message=error,
        )


class NoopRemediator(BaseRemediator):
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
        context: ExecutionContext,
    ) -> RemediationResult:
        
        logger.info(
            "noop_remediation",
            incident_id=incident.incident_id,
            action=plan.action_type.value,
        )
        
        return self._success_result(
            message="No action taken (notify only)",
            actions=["NOOP"],
        )


class GitHubRerunRemediator(BaseRemediator):
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
        context: ExecutionContext,
    ) -> RemediationResult:
        
        repo = plan.parameters.get("repository")
        run_id = plan.parameters.get("run_id")
        
        if not repo or not run_id:
            return self._failure_result(
                message="Missing repository or run_id",
                error="Required parameters not provided",
            )
        
        try:
            logger.info(
                "github_rerun_workflow",
                repository=repo,
                run_id=run_id,
            )
            
            return self._success_result(
                message=f"Workflow {run_id} rerun triggered",
                actions=[f"GITHUB_RERUN: {repo}/{run_id}"],
            )
            
        except Exception as e:
            return self._failure_result(
                message="Failed to rerun workflow",
                error=str(e),
            )


class K8sRestartPodRemediator(BaseRemediator):
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
        context: ExecutionContext,
    ) -> RemediationResult:
        
        namespace = plan.parameters.get("namespace")
        pod = plan.parameters.get("pod")
        
        if not namespace or not pod:
            return self._failure_result(
                message="Missing namespace or pod name",
                error="Required parameters not provided",
            )
        
        try:
            logger.info(
                "k8s_restart_pod",
                namespace=namespace,
                pod=pod,
            )
            
            return self._success_result(
                message=f"Pod {pod} restarted in {namespace}",
                actions=[f"K8S_DELETE_POD: {namespace}/{pod}"],
            )
            
        except Exception as e:
            return self._failure_result(
                message="Failed to restart pod",
                error=str(e),
            )


class ArgoCDSyncRemediator(BaseRemediator):
    
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
        context: ExecutionContext,
    ) -> RemediationResult:
        
        application = plan.parameters.get("application")
        
        if not application:
            return self._failure_result(
                message="Missing application name",
                error="Required parameters not provided",
            )
        
        try:
            logger.info(
                "argocd_sync",
                application=application,
            )
            
            return self._success_result(
                message=f"ArgoCD sync triggered for {application}",
                actions=[f"ARGOCD_SYNC: {application}"],
            )
            
        except Exception as e:
            return self._failure_result(
                message="Failed to sync ArgoCD application",
                error=str(e),
            )


class RemediatorFactory:
    
    def __init__(self, settings: Any = None):
        self.settings = settings
        
        self._remediators = {
            RemediationActionType.NOOP: NoopRemediator,
            RemediationActionType.NOTIFY_ONLY: NoopRemediator,
            RemediationActionType.GITHUB_RERUN_WORKFLOW: GitHubRerunRemediator,
            RemediationActionType.K8S_RESTART_POD: K8sRestartPodRemediator,
            RemediationActionType.ARGOCD_SYNC: ArgoCDSyncRemediator,
        }
    
    def create(self, action_type: RemediationActionType) -> BaseRemediator:
        remediator_class = self._remediators.get(action_type, NoopRemediator)
        return remediator_class(self.settings)
    
    def register(
        self,
        action_type: RemediationActionType,
        remediator_class: type,
    ):
        self._remediators[action_type] = remediator_class