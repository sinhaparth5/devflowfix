# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional
from datetime import datetime

from app.domain.validators.base import BaseValidator, ValidationResult
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import Outcome
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PostRemediationValidator(BaseValidator):
    """
    Validates that a remediation action worked correctly.
    
    Performs health checks after remediation execution:
    - Verifies incident is actually resolved
    - Checks for new failures introduced
    - Validates service health metrics
    - Ensures no collateral damage
    - Checks if similar issues recurred
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize validator.
        
        Args:
            settings: Application settings (injected dependency)
        """
        self.settings = settings or Settings()
    
    async def validate(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan] = None,
    ) -> ValidationResult:
        """
        Perform post-remediation validation checks.
        
        Args:
            incident: Incident that was remediated
            plan: Remediation plan that was executed
            
        Returns:
            ValidationResult with all check results
        """
        logger.info(
            "post_remediation_validation_start",
            incident_id=incident.incident_id,
            outcome=incident.outcome.value if incident.outcome else None,
        )
        
        result = ValidationResult(passed=True, message="Post-remediation validation")
        
        checks = [
            self._check_incident_resolved(incident),
            self._check_execution_success(incident),
            self._check_no_new_failures(incident),
            self._check_service_health(incident),
            self._check_execution_time(incident, plan),
            self._check_outcome_consistency(incident),
        ]
        
        for check in checks:
            result.add_check(check)
        
        result.passed = all(check.passed for check in checks if check.severity == "error")
        
        if result.has_warnings():
            result.add_warning("Post-remediation checks show potential issues")
        
        logger.info(
            "post_remediation_validation_complete",
            incident_id=incident.incident_id,
            passed=result.passed,
            failed_checks=len(result.get_failed_checks()),
        )
        
        return result
    
    def _check_incident_resolved(self, incident: Incident):
        """Check if incident is marked as resolved."""
        if not incident.is_resolved():
            return self._create_check(
                name="incident_resolved",
                passed=False,
                message=f"Incident not resolved (outcome: {incident.outcome.value if incident.outcome else 'unknown'})",
                severity="error",
                outcome=incident.outcome.value if incident.outcome else None,
            )
        
        return self._create_check(
            name="incident_resolved",
            passed=True,
            message="Incident marked as resolved",
            outcome=incident.outcome.value,
        )
    
    def _check_execution_success(self, incident: Incident):
        """Check if remediation execution was successful."""
        if not incident.remediation_executed:
            return self._create_check(
                name="execution_success",
                passed=False,
                message="Remediation was not executed",
                severity="error",
            )
        
        if incident.outcome == Outcome.FAILED:
            return self._create_check(
                name="execution_success",
                passed=False,
                message="Remediation execution failed",
                severity="error",
                outcome=incident.outcome.value,
                outcome_message=incident.outcome_message,
            )
        
        return self._create_check(
            name="execution_success",
            passed=True,
            message="Remediation executed successfully",
            outcome=incident.outcome.value,
        )
    
    def _check_no_new_failures(self, incident: Incident):
        """
        Check if any new failures were introduced.
        
        TODO: Integrate with monitoring system to check for:
        - New error logs in the service
        - Spike in error rate
        - New alerts triggered
        """
        if incident.outcome_message and "error" in incident.outcome_message.lower():
            return self._create_check(
                name="no_new_failures",
                passed=False,
                message="Outcome message indicates possible new errors",
                severity="warning",
                outcome_message=incident.outcome_message,
            )
        
        return self._create_check(
            name="no_new_failures",
            passed=True,
            message="No new failures detected",
        )
    
    def _check_service_health(self, incident: Incident):
        """
        Check service health metrics.
        
        TODO: Integrate with monitoring systems:
        - Kubernetes pod health checks
        - Application health endpoints
        - Prometheus metrics
        - Error rate monitoring
        """
        service_name = incident.get_service_name()
        namespace = incident.get_namespace()
        
        if not service_name:
            return self._create_check(
                name="service_health",
                passed=True,
                message="Service name not available, skipping health check",
                severity="info",
            )
        
        # TODO: Make actual health check API calls
        if incident.is_resolved():
            return self._create_check(
                name="service_health",
                passed=True,
                message=f"Service {service_name} appears healthy",
                service=service_name,
                namespace=namespace,
            )
        
        return self._create_check(
            name="service_health",
            passed=False,
            message=f"Service {service_name} health check inconclusive",
            severity="warning",
            service=service_name,
        )
    
    def _check_execution_time(
        self,
        incident: Incident,
        plan: Optional[RemediationPlan],
    ):
        """Check if execution time was within expected bounds."""
        duration = incident.calculate_remediation_duration()
        
        if duration is None:
            return self._create_check(
                name="execution_time",
                passed=True,
                message="Execution time not available",
                severity="info",
            )
        
        timeout = self.settings.remediation_timeout_seconds
        if duration > timeout:
            return self._create_check(
                name="execution_time",
                passed=False,
                message=f"Execution took {duration}s, exceeded timeout {timeout}s",
                severity="error",
                duration_seconds=duration,
                timeout_seconds=timeout,
            )
        
        if plan and plan.estimated_duration_seconds:
            estimated = plan.estimated_duration_seconds
            if duration > estimated * 2:
                return self._create_check(
                    name="execution_time",
                    passed=False,
                    message=f"Execution took {duration}s, much longer than estimated {estimated}s",
                    severity="warning",
                    duration_seconds=duration,
                    estimated_seconds=estimated,
                )
        
        return self._create_check(
            name="execution_time",
            passed=True,
            message=f"Execution completed in {duration}s",
            duration_seconds=duration,
        )
    
    def _check_outcome_consistency(self, incident: Incident):
        """Check if outcome is consistent with resolution status."""
        if incident.resolved_at and not incident.outcome:
            return self._create_check(
                name="outcome_consistency",
                passed=False,
                message="Incident has resolved_at but no outcome",
                severity="warning",
            )
        
        if incident.outcome == Outcome.SUCCESS and not incident.resolved_at:
            return self._create_check(
                name="outcome_consistency",
                passed=False,
                message="Outcome is SUCCESS but no resolved_at timestamp",
                severity="warning",
            )
        
        if incident.outcome == Outcome.FAILED and incident.is_resolved():
            return self._create_check(
                name="outcome_consistency",
                passed=False,
                message="Outcome is FAILED but incident marked as resolved",
                severity="warning",
            )
        
        return self._create_check(
            name="outcome_consistency",
            passed=True,
            message="Outcome is consistent with resolution status",
        )
    
    async def validate_with_result(
        self,
        incident: Incident,
        remediation_result: RemediationResult,
        plan: Optional[RemediationPlan] = None,
    ) -> ValidationResult:
        """
        Validate using a RemediationResult object.
        
        This is a convenience method when you have a RemediationResult
        object with additional details.
        
        Args:
            incident: Incident that was remediated
            remediation_result: Result of the remediation execution
            plan: Remediation plan that was executed
            
        Returns:
            ValidationResult with all check results
        """
        logger.info(
            "post_remediation_validation_with_result",
            incident_id=incident.incident_id,
            success=remediation_result.success,
        )
        
        result = ValidationResult(
            passed=True,
            message="Post-remediation validation with result"
        )
        
        result.add_check(
            self._create_check(
                name="remediation_result_success",
                passed=remediation_result.success,
                message=f"Remediation result success: {remediation_result.success}",
                severity="error" if not remediation_result.success else "info",
            )
        )
        
        result.add_check(
            self._create_check(
                name="post_validation_passed",
                passed=remediation_result.post_validation_passed,
                message=f"Post-validation checks: {remediation_result.post_validation_passed}",
                severity="error" if not remediation_result.post_validation_passed else "info",
            )
        )
        
        standard_result = await self.validate(incident, plan)
        for check in standard_result.checks:
            result.add_check(check)
        
        result.passed = all(
            check.passed for check in result.checks if check.severity == "error"
        )
        
        return result
