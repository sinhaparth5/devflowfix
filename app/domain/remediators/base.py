# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Base Remediator Abstract Class

Defines the interface for all remediation actions.
Each remediator implements a specific remediation strategy (e.g., restart pod, rerun workflow).
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import Outcome, RemediationActionType
from app.core.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BaseRemediator(ABC):
    """
    Abstract base class for all remediators.
    
    Each remediator implements a specific remediation action:
    - GitHub Actions rerun workflow
    - Kubernetes restart pod
    - ArgoCD sync application
    - etc.
    
    Subclasses must implement:
    - execute(): Perform the actual remediation
    - get_action_type(): Return the action type this remediator handles
    
    Optional overrides:
    - validate_parameters(): Validate plan parameters before execution
    - can_handle(): Check if this remediator can handle the incident
    
    Example:
        ```python
        class GitHubRerunRemediator(BaseRemediator):
            def get_action_type(self) -> RemediationActionType:
                return RemediationActionType.GITHUB_RERUN_WORKFLOW
            
            async def execute(
                self,
                incident: Incident,
                plan: RemediationPlan
            ) -> RemediationResult:
                # Implementation here
                pass
        ```
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize remediator.
        
        Args:
            settings: Application settings (injected dependency)
        """
        self.settings = settings or Settings()
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    def get_action_type(self) -> RemediationActionType:
        """
        Get the action type this remediator handles.
        
        Returns:
            RemediationActionType enum value
        """
        pass
    
    @abstractmethod
    async def execute(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """
        Execute the remediation action.
        
        This is the main method that performs the actual remediation.
        Subclasses must implement this method with their specific logic.
        
        Args:
            incident: Incident to remediate
            plan: Remediation plan with action parameters
            
        Returns:
            RemediationResult with outcome and details
            
        Raises:
            RemediationFailedError: If remediation fails
            ValidationFailedError: If validation fails
        """
        pass
    
    def validate_parameters(self, plan: RemediationPlan) -> None:
        """
        Validate remediation plan parameters.
        
        Override this method to add parameter validation specific to the remediator.
        Raises exception if parameters are invalid.
        
        Args:
            plan: Remediation plan to validate
            
        Raises:
            ValueError: If parameters are invalid
        """
        pass
    
    def can_handle(self, incident: Incident, plan: RemediationPlan) -> bool:
        """
        Check if this remediator can handle the given incident and plan.
        
        Default implementation checks if plan's action_type matches this remediator's type.
        Override for more complex logic.
        
        Args:
            incident: Incident to check
            plan: Remediation plan to check
            
        Returns:
            True if this remediator can handle the incident
        """
        return plan.action_type == self.get_action_type()
    
    def _create_success_result(
        self,
        message: str,
        duration_seconds: Optional[int] = None,
        actions_performed: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> RemediationResult:
        """
        Helper to create a successful remediation result.
        
        Args:
            message: Success message
            duration_seconds: Duration of execution
            actions_performed: List of actions performed
            metadata: Additional metadata
            
        Returns:
            RemediationResult indicating success
        """
        return RemediationResult(
            success=True,
            outcome=Outcome.SUCCESS,
            message=message,
            duration_seconds=duration_seconds,
            actions_performed=actions_performed or [],
            metadata=metadata or {},
            pre_validation_passed=True,
            post_validation_passed=True,
        )
    
    def _create_failure_result(
        self,
        message: str,
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        actions_performed: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        rollback_required: bool = False,
    ) -> RemediationResult:
        """
        Helper to create a failed remediation result.
        
        Args:
            message: Failure message
            error_message: Detailed error message
            error_traceback: Error traceback
            duration_seconds: Duration of execution
            actions_performed: List of actions performed before failure
            metadata: Additional metadata
            rollback_required: Whether rollback is needed
            
        Returns:
            RemediationResult indicating failure
        """
        return RemediationResult(
            success=False,
            outcome=Outcome.FAILED,
            message=message,
            error_message=error_message,
            error_traceback=error_traceback,
            duration_seconds=duration_seconds,
            actions_performed=actions_performed or [],
            metadata=metadata or {},
            rollback_required=rollback_required,
        )
    
    def _log_execution_start(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> None:
        """
        Log remediation execution start.
        
        Args:
            incident: Incident being remediated
            plan: Remediation plan being executed
        """
        self.logger.info(
            "remediation_execution_start",
            incident_id=incident.incident_id,
            action_type=plan.action_type.value,
            risk_level=plan.risk_level.value,
            parameters=plan.parameters,
        )
    
    def _log_execution_complete(
        self,
        incident: Incident,
        result: RemediationResult,
    ) -> None:
        """
        Log remediation execution completion.
        
        Args:
            incident: Incident that was remediated
            result: Remediation result
        """
        log_level = "info" if result.success else "error"
        log_method = getattr(self.logger, log_level)
        
        log_method(
            "remediation_execution_complete",
            incident_id=incident.incident_id,
            success=result.success,
            outcome=result.outcome.value,
            duration=result.duration_seconds,
            message=result.message,
        )
    
    async def __call__(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> RemediationResult:
        """
        Make remediator callable.
        
        Allows using: result = await remediator(incident, plan)
        
        Args:
            incident: Incident to remediate
            plan: Remediation plan
            
        Returns:
            RemediationResult
        """
        return await self.execute(incident, plan)
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}({self.get_action_type().value})"
    
    def __repr__(self) -> str:
        """Developer representation."""
        return f"<{self.__class__.__name__} action_type={self.get_action_type().value}>"
