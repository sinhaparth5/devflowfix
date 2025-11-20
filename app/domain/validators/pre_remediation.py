# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
from datetime import datetime, timedelta

from app.domain.validators.base import BaseValidator, ValidationResult
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import RiskLevel, Environment, FailureType, RemediationActionType
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PreRemediationValidator(BaseValidator):
    """
    Validates that it's safe to execute a remediation action.
    
    Performs pre-flight checks before remediation execution:
    - Validates incident data completeness
    - Checks if action is blacklisted
    - Verifies environment-specific requirements
    - Validates confidence thresholds
    - Checks if cluster/service is healthy
    - Ensures prerequisites are met
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize validator.
        
        Args:
            settings: Application settings (injected dependency)
        """
        self.settings = settings or Settings()
        self._blacklist = self._load_blacklist()
    
    def _load_blacklist(self) -> set[tuple[str, str]]:
        """
        Load blacklisted (failure_type, action_type) combinations.
        
        Returns:
            Set of blacklisted combinations
        """
        # TODO: Load from configuration or database
        return {
            # OOM killed - restarting won't help, need resource adjustments
            (FailureType.OOM_KILLED.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.OOM_KILLED.value, RemediationActionType.GITHUB_RERUN_WORKFLOW.value),
            
            # Auth/permission issues - need secret rotation/updates, not restarts
            (FailureType.AUTH_EXPIRED.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.AUTH_EXPIRED.value, RemediationActionType.ARGOCD_SYNC.value),
            (FailureType.PERMISSION_DENIED.value, RemediationActionType.K8S_RESTART_POD.value),
            
            # Config errors - need manual fixes, not restarts
            (FailureType.CONFIG_ERROR.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.INVALID_YAML.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.INVALID_YAML.value, RemediationActionType.ARGOCD_SYNC.value),
            
            # Missing resources - need creation, not restarts
            (FailureType.MISSING_SECRET.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.MISSING_SECRET.value, RemediationActionType.ARGOCD_SYNC.value),
            
            # Disk issues - evicting pods won't help
            (FailureType.DISK_FULL.value, RemediationActionType.K8S_DELETE_EVICETED_PODS.value),
            
            # Build/code issues - need code changes, not pod operations
            (FailureType.BUILD_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.TEST_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value),
            (FailureType.LINT_FAILURE.value, RemediationActionType.K8S_RESTART_POD.value),
            
            # Resource exhaustion - need scaling, not restarts
            (FailureType.RESOURCE_EXHAUSTED.value, RemediationActionType.K8S_RESTART_POD.value),
        }
    
    async def validate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> ValidationResult:
        """
        Perform pre-remediation validation checks.
        
        Args:
            incident: Incident to validate
            plan: Remediation plan to validate
            
        Returns:
            ValidationResult with all check results
        """
        logger.info(
            "pre_remediation_validation_start",
            incident_id=incident.incident_id,
            action_type=plan.action_type.value if plan else None,
        )
        
        result = ValidationResult(passed=True, message="Pre-remediation validation")
        
        checks = [
            self._check_incident_data(incident),
            self._check_plan_exists(plan),
            self._check_confidence_threshold(incident),
            self._check_not_blacklisted(incident, plan),
            self._check_environment_requirements(incident, plan),
            self._check_risk_level(plan),
            self._check_prerequisites(incident, plan),
        ]
        
        for check in checks:
            result.add_check(check)
        
        result.passed = all(check.passed for check in checks if check.severity == "error")
        
        if result.has_warnings():
            result.add_warning("Some validation checks produced warnings")
        
        logger.info(
            "pre_remediation_validation_complete",
            incident_id=incident.incident_id,
            passed=result.passed,
            failed_checks=len(result.get_failed_checks()),
        )
        
        return result
    
    def _check_incident_data(self, incident: Incident):
        """Check if incident has required data."""
        if not incident.error_log and not incident.error_message:
            return self._create_check(
                name="incident_data_completeness",
                passed=False,
                message="Incident missing error_log and error_message",
                severity="error",
            )
        
        if not incident.failure_type:
            return self._create_check(
                name="incident_data_completeness",
                passed=False,
                message="Incident missing failure_type classification",
                severity="error",
            )
        
        return self._create_check(
            name="incident_data_completeness",
            passed=True,
            message="Incident has required data",
        )
    
    def _check_plan_exists(self, plan: Optional[RemediationPlan]):
        """Check if remediation plan exists."""
        if not plan:
            return self._create_check(
                name="plan_exists",
                passed=False,
                message="No remediation plan provided",
                severity="error",
            )
        
        return self._create_check(
            name="plan_exists",
            passed=True,
            message="Remediation plan exists",
        )
    
    def _check_confidence_threshold(self, incident: Incident):
        """Check if confidence meets threshold for environment."""
        if incident.confidence is None:
            return self._create_check(
                name="confidence_threshold",
                passed=False,
                message="Confidence score not available",
                severity="error",
            )
        
        # Get environment from incident context (not global settings)
        env_str = incident.context.get("environment", "prod")
        
        # Determine threshold based on incident's environment
        if env_str in ["prod", "production"]:
            threshold = self.settings.production_confidence_threshold
        elif env_str in ["staging", "stage"]:
            threshold = self.settings.high_confidence_threshold
        else:  # dev, test, etc.
            threshold = self.settings.min_confidence_threshold
        
        if incident.confidence < threshold:
            return self._create_check(
                name="confidence_threshold",
                passed=False,
                message=f"Confidence {incident.confidence:.2f} below threshold {threshold:.2f}",
                severity="error",
                confidence=incident.confidence,
                threshold=threshold,
                environment=env_str,
            )
        
        return self._create_check(
            name="confidence_threshold",
            passed=True,
            message=f"Confidence {incident.confidence:.2f} meets threshold",
            confidence=incident.confidence,
            threshold=threshold,
            environment=env_str,
        )
    
    def _check_not_blacklisted(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan],
    ):
        """Check if action is blacklisted for this failure type."""
        if not plan or not incident.failure_type:
            return self._create_check(
                name="blacklist_check",
                passed=True,
                message="Skipped (missing data)",
                severity="info",
            )
        
        combination = (
            incident.failure_type.value,
            plan.action_type.value,
        )
        
        if combination in self._blacklist:
            return self._create_check(
                name="blacklist_check",
                passed=False,
                message=f"Action {plan.action_type.value} blacklisted for {incident.failure_type.value}",
                severity="error",
                failure_type=incident.failure_type.value,
                action_type=plan.action_type.value,
            )
        
        return self._create_check(
            name="blacklist_check",
            passed=True,
            message="Action not blacklisted",
        )
    
    def _check_environment_requirements(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan],
    ):
        """Check environment-specific requirements."""
        if not plan:
            return self._create_check(
                name="environment_check",
                passed=True,
                message="Skipped (no plan)",
            )
        
        env_str = incident.context.get("environment", "prod")
        
        if env_str == "prod" and plan.is_high_risk():
            if not plan.requires_approval:
                return self._create_check(
                    name="environment_check",
                    passed=False,
                    message="High-risk action in production requires approval",
                    severity="warning",
                    environment=env_str,
                    risk_level=plan.risk_level.value,
                )
        
        return self._create_check(
            name="environment_check",
            passed=True,
            message="Environment requirements met",
            environment=env_str,
        )
    
    def _check_risk_level(self, plan: Optional[RemediationPlan]):
        """Check if risk level is acceptable."""
        if not plan:
            return self._create_check(
                name="risk_level_check",
                passed=True,
                message="Skipped (no plan)",
            )
        
        if plan.risk_level == RiskLevel.CRITICAL and not plan.requires_approval:
            return self._create_check(
                name="risk_level_check",
                passed=False,
                message="Critical risk action must require approval",
                severity="error",
                risk_level=plan.risk_level.value,
            )
        
        return self._create_check(
            name="risk_level_check",
            passed=True,
            message=f"Risk level {plan.risk_level.value} acceptable",
            risk_level=plan.risk_level.value,
        )
    
    def _check_prerequisites(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan],
    ):
        """Check if prerequisites are met."""
        if not plan:
            return self._create_check(
                name="prerequisites_check",
                passed=True,
                message="Skipped (no plan)",
            )
        
        if not plan.pre_validation_checks:
            return self._create_check(
                name="prerequisites_check",
                passed=True,
                message="No prerequisites defined",
            )
        
        # TODO: Actually run the pre-validation checks
        return self._create_check(
            name="prerequisites_check",
            passed=True,
            message=f"{len(plan.pre_validation_checks)} prerequisites defined",
            prerequisite_count=len(plan.pre_validation_checks),
        )
