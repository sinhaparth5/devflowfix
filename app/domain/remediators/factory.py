# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Remediator Factory

Factory for creating remediator instances based on action type.
"""

from typing import Any

from app.domain.remediators.base import BaseRemediator
from app.domain.remediators.noop import NoopRemediator
from app.domain.remediators.github_rerun import GitHubRerunRemediator
from app.domain.remediators.k8s_restart_pod import K8sRestartPodRemediator
from app.domain.remediators.argocd_sync import ArgoCDSyncRemediator
from app.core.enums import RemediationActionType


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