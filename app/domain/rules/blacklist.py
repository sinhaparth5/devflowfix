# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Set, Tuple

from app.domain.rules.base import BaseRule, RuleResult
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import FailureType, RemediationActionType
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BlacklistRule(BaseRule):
    """
    Prevents dangerous (failure_type, action_type) combinations.
    
    Maintains a blacklist of combinations that should never be auto-fixed:
    - Wrong action for failure type (e.g., restart pod for auth issues)
    - Known dangerous combinations that could make things worse
    - Actions that require manual intervention
    
    This is a safety mechanism to prevent the system from taking
    actions that are known to be ineffective or harmful.
    """
    
    def __init__(self):
        """
        Initialize the blacklist rule with default dangerous combinations.
        """
        self._blacklist = self._load_default_blacklist()
    
    @property
    def name(self) -> str:
        """Get the rule name."""
        return "BlacklistRule"
    
    async def evaluate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> RuleResult:
        """
        Evaluate if the incident/plan combination is blacklisted.
        
        Args:
            incident: Incident to evaluate
            plan: Remediation plan to evaluate
            
        Returns:
            RuleResult indicating if the combination is allowed
        """
        logger.info(
            "blacklist_rule_evaluate_start",
            incident_id=incident.incident_id,
            failure_type=incident.failure_type.value if incident.failure_type else None,
            action_type=plan.action_type.value if plan else None,
        )
        
        if not plan:
            return self._create_result(
                passed=True,
                message="No remediation plan provided, skipping blacklist check",
            )
        
        if not incident.failure_type:
            return self._create_result(
                passed=True,
                message="No failure type classified, skipping blacklist check",
            )
        
        combination = (incident.failure_type.value, plan.action_type.value)
        
        if combination in self._blacklist:
            logger.warning(
                "blacklist_rule_failed",
                incident_id=incident.incident_id,
                failure_type=incident.failure_type.value,
                action_type=plan.action_type.value,
            )
            
            return self._create_result(
                passed=False,
                message=f"Blacklisted combination: {incident.failure_type.value} + {plan.action_type.value}",
                reason=self._get_blacklist_reason(combination),
                failure_type=incident.failure_type.value,
                action_type=plan.action_type.value,
            )
        
        logger.info(
            "blacklist_rule_passed",
            incident_id=incident.incident_id,
            failure_type=incident.failure_type.value,
            action_type=plan.action_type.value,
        )
        
        return self._create_result(
            passed=True,
            message="Combination is not blacklisted",
            failure_type=incident.failure_type.value,
            action_type=plan.action_type.value,
        )
    
    def _load_default_blacklist(self) -> Set[Tuple[str, str]]:
        """
        Load default blacklisted combinations.
        
        Returns:
            Set of (failure_type, action_type) tuples that are blacklisted
        """
        # TODO: Load from configuration file or database
        return {
            (FailureType.OOM_KILLED.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.OOM_KILLED.value, RemediationActionType.GITHUB_RERUN_WORKFLOW.value),
            
            (FailureType.AUTH_EXPIRED.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.AUTH_EXPIRED.value, RemediationActionType.ARGOCD_SYNC.value),
            (FailureType.PERMISSION_DENIED.value, RemediationActionType.K8S_RESTART_POD.value),
            
            (FailureType.CONFIG_ERROR.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.INVALID_YAML.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.INVALID_YAML.value, RemediationActionType.ARGOCD_SYNC.value),
            
            (FailureType.MISSING_SECRET.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.MISSING_SECRET.value, RemediationActionType.ARGOCD_SYNC.value),
            
            (FailureType.DISK_FULL.value, RemediationActionType.K8S_DELETE_EVICETED_PODS.value),
            
            (FailureType.BUILD_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.TEST_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.LINT_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value),
            
            (FailureType.RESOURCE_EXHAUSTED.value, RemediationActionType.K8S_RESTART_POD.value),
        }
    
    def _get_blacklist_reason(self, combination: Tuple[str, str]) -> str:
        """
        Get the reason why a combination is blacklisted.
        
        Args:
            combination: (failure_type, action_type) tuple
            
        Returns:
            Human-readable reason
        """
        failure_type, action_type = combination
        
        reasons = {
            (FailureType.OOM_KILLED.value, RemediationActionType.K8S_RESTART_POD.value):
                "OOM killed requires resource limit adjustment, not restart",
            (FailureType.AUTH_EXPIRED.value, RemediationActionType.K8S_RESTART_POD.value):
                "Auth expired requires secret rotation, not restart",
            (FailureType.CONFIG_ERROR.value, RemediationActionType.K8S_RESTART_POD.value):
                "Config error requires manual configuration fix",
            (FailureType.MISSING_SECRET.value, RemediationActionType.K8S_RESTART_POD.value):
                "Missing secret requires secret creation, not restart",
            (FailureType.BUILD_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value):
                "Build failure requires code changes, not pod restart",
        }
        
        return reasons.get(
            combination,
            f"Combination {failure_type} + {action_type} is known to be ineffective or dangerous"
        )
    
    def add_to_blacklist(
        self,
        failure_type: FailureType,
        action_type: RemediationActionType,
    ) -> None:
        """
        Add a combination to the blacklist.
        
        Args:
            failure_type: Failure type to blacklist
            action_type: Action type to blacklist for this failure
        """
        combination = (failure_type.value, action_type.value)
        self._blacklist.add(combination)
        
        logger.info(
            "blacklist_combination_added",
            failure_type=failure_type.value,
            action_type=action_type.value,
        )
    
    def remove_from_blacklist(
        self,
        failure_type: FailureType,
        action_type: RemediationActionType,
    ) -> None:
        """
        Remove a combination from the blacklist.
        
        Args:
            failure_type: Failure type to remove
            action_type: Action type to remove
        """
        combination = (failure_type.value, action_type.value)
        self._blacklist.discard(combination)
        
        logger.info(
            "blacklist_combination_removed",
            failure_type=failure_type.value,
            action_type=action_type.value,
        )
    
    def is_blacklisted(
        self,
        failure_type: FailureType,
        action_type: RemediationActionType,
    ) -> bool:
        """
        Check if a combination is blacklisted.
        
        Args:
            failure_type: Failure type to check
            action_type: Action type to check
            
        Returns:
            True if combination is blacklisted
        """
        combination = (failure_type.value, action_type.value)
        return combination in self._blacklist
    
    def get_blacklist(self) -> Set[Tuple[str, str]]:
        """
        Get the current blacklist.
        
        Returns:
            Set of blacklisted (failure_type, action_type) tuples
        """
        return self._blacklist.copy()
    
    def get_blacklist_size(self) -> int:
        """
        Get the number of blacklisted combinations.
        
        Returns:
            Count of blacklisted combinations
        """
        return len(self._blacklist)
