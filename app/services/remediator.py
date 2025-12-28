# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Remediator Service

Orchestrates the complete remediation workflow:
1. Pre-validation checks (safety guardrails)
2. Execution of remediation action
3. Post-validation checks (verify success)
4. Rollback handling on failure

This is the main entry point for executing remediations.
"""

import traceback
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import Outcome
from app.core.config import Settings
from app.domain.remediators.base import BaseRemediator
from app.domain.validators.pre_remediation import PreRemediationValidator
from app.domain.validators.post_remediation import PostRemediationValidator
from app.domain.validators.blast_radius import BlastRadiusValidator
from app.exceptions import (
    RemediationFailedError,
    ValidationFailedError,
    RollbackFailedError,
)
from app.utils.logging import get_logger
from app.utils.app_logger import AppLogger
from app.adapters.database.postgres.models import LogCategory

logger = get_logger(__name__)


class RemediatorService:
    """
    Service for orchestrating remediation execution.
    
    Handles the complete remediation workflow:
    - Pre-validation (safety checks)
    - Execution (actual remediation)
    - Post-validation (verify success)
    - Rollback (if needed)
    
    Example:
        ```python
        service = RemediatorService()
        
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=github_rerun_remediator,
        )
        
        if result.success:
            print("Remediation succeeded!")
        else:
            print(f"Remediation failed: {result.error_message}")
        ```
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        pre_validator: Optional[PreRemediationValidator] = None,
        post_validator: Optional[PostRemediationValidator] = None,
        blast_radius_validator: Optional[BlastRadiusValidator] = None,
    ):
        """
        Initialize remediator service.
        
        Args:
            settings: Application settings
            pre_validator: Pre-remediation validator (creates default if not provided)
            post_validator: Post-remediation validator (creates default if not provided)
            blast_radius_validator: Blast radius validator (creates default if not provided)
        """
        self.settings = settings or Settings()
        self.pre_validator = pre_validator or PreRemediationValidator(settings=self.settings)
        self.post_validator = post_validator or PostRemediationValidator(settings=self.settings)
        self.blast_radius_validator = blast_radius_validator or BlastRadiusValidator()
    
    async def execute_remediation(
        self,
        incident: Incident,
        plan: RemediationPlan,
        remediator: BaseRemediator,
        skip_pre_validation: bool = False,
        skip_post_validation: bool = False,
        skip_blast_radius_check: bool = False,
        db: Optional[Session] = None,
        user_id: Optional[str] = None,
    ) -> RemediationResult:
        """
        Execute remediation with full validation workflow.
        
        Workflow:
        1. Pre-validation checks (unless skipped)
        2. Blast radius validation (unless skipped)
        3. Execute remediation action
        4. Post-validation checks (unless skipped)
        5. Rollback on failure (if needed)
        
        Args:
            incident: Incident to remediate
            plan: Remediation plan to execute
            remediator: Remediator instance to use
            skip_pre_validation: Skip pre-validation checks
            skip_post_validation: Skip post-validation checks
            skip_blast_radius_check: Skip blast radius validation
            
        Returns:
            RemediationResult with complete execution details
        """
        start_time = datetime.now()
        execution_logs = []

        # Create application logger
        app_logger = None
        if db:
            app_logger = AppLogger(
                db=db,
                incident_id=incident.incident_id,
                user_id=user_id or incident.context.get("user_id"),
            )

        logger.info(
            "remediation_service_start",
            incident_id=incident.incident_id,
            action_type=plan.action_type.value,
            risk_level=plan.risk_level.value,
        )

        # Log remediation start
        if app_logger:
            app_logger.remediation_start(
                f"Starting remediation for {plan.action_type.value}",
                details={
                    "action_type": plan.action_type.value,
                    "risk_level": plan.risk_level.value,
                    "confidence": plan.confidence,
                }
            )

        try:
            # Step 1: Pre-validation checks
            if not skip_pre_validation:
                logger.info(
                    "pre_validation_start",
                    incident_id=incident.incident_id,
                )
                
                pre_validation_result = await self.pre_validator.validate(incident, plan)
                execution_logs.append(f"Pre-validation: {'PASSED' if pre_validation_result.passed else 'FAILED'}")
                
                if not pre_validation_result.passed:
                    logger.warning(
                        "pre_validation_failed",
                        incident_id=incident.incident_id,
                        failed_checks=[c.name for c in pre_validation_result.get_failed_checks()],
                    )
                    
                    duration = (datetime.now() - start_time).seconds
                    return RemediationResult(
                        success=False,
                        outcome=Outcome.FAILED,
                        message="Pre-validation checks failed",
                        error_message=pre_validation_result.message,
                        duration_seconds=duration,
                        pre_validation_passed=False,
                        validation_details={
                            "pre_validation": {
                                "passed": False,
                                "checks": [
                                    {
                                        "name": c.name,
                                        "passed": c.passed,
                                        "message": c.message,
                                        "severity": c.severity,
                                    }
                                    for c in pre_validation_result.checks
                                ],
                            }
                        },
                        execution_logs=execution_logs,
                    )
            
            if not skip_blast_radius_check:
                logger.info(
                    "blast_radius_check_start",
                    incident_id=incident.incident_id,
                )
                
                blast_radius_result = await self.blast_radius_validator.validate(incident, plan)
                execution_logs.append(f"Blast radius check: {'PASSED' if blast_radius_result.passed else 'FAILED'}")
                
                if not blast_radius_result.passed:
                    logger.warning(
                        "blast_radius_exceeded",
                        incident_id=incident.incident_id,
                        failed_checks=[c.name for c in blast_radius_result.get_failed_checks()],
                    )
                    
                    duration = (datetime.now() - start_time).seconds
                    return RemediationResult(
                        success=False,
                        outcome=Outcome.FAILED,
                        message="Blast radius limit exceeded",
                        error_message=blast_radius_result.message,
                        duration_seconds=duration,
                        pre_validation_passed=True,
                        validation_details={
                            "blast_radius": {
                                "passed": False,
                                "checks": [
                                    {
                                        "name": c.name,
                                        "passed": c.passed,
                                        "message": c.message,
                                        "severity": c.severity,
                                    }
                                    for c in blast_radius_result.checks
                                ],
                            }
                        },
                        execution_logs=execution_logs,
                    )
                
                self.blast_radius_validator.record_execution_start(incident)
            
            logger.info(
                "remediation_execution_start",
                incident_id=incident.incident_id,
                remediator=str(remediator),
            )
            execution_logs.append(f"Executing remediation: {remediator.get_action_type().value}")

            # Log remediation executing
            if app_logger:
                app_logger.remediation_executing(
                    f"Executing {remediator.get_action_type().value} remediation",
                    details={
                        "remediator": str(remediator),
                        "action_type": remediator.get_action_type().value,
                    }
                )

            remediation_result = await remediator.execute(incident, plan)
            
            execution_logs.extend(remediation_result.execution_logs)
            execution_logs.append(f"Remediation execution: {'SUCCESS' if remediation_result.success else 'FAILED'}")
            
            if not skip_blast_radius_check:
                if remediation_result.success:
                    self.blast_radius_validator.record_execution_end(incident, success=True)
                else:
                    self.blast_radius_validator.record_execution_end(incident, success=False)
            
            if not remediation_result.success:
                logger.error(
                    "remediation_execution_failed",
                    incident_id=incident.incident_id,
                    error=remediation_result.error_message,
                )
                
                if remediation_result.rollback_required:
                    execution_logs.append("Rollback required due to failure")
                    rollback_success = await self._handle_rollback(incident, plan)
                    remediation_result.rollback_performed = rollback_success
                    execution_logs.append(f"Rollback: {'SUCCESS' if rollback_success else 'FAILED'}")
                
                remediation_result.execution_logs = execution_logs
                return remediation_result
            
            if not skip_post_validation:
                logger.info(
                    "post_validation_start",
                    incident_id=incident.incident_id,
                )
                
                post_validation_result = await self.post_validator.validate(incident, plan)
                execution_logs.append(f"Post-validation: {'PASSED' if post_validation_result.passed else 'FAILED'}")
                
                if not post_validation_result.passed:
                    logger.warning(
                        "post_validation_failed",
                        incident_id=incident.incident_id,
                        failed_checks=[c.name for c in post_validation_result.get_failed_checks()],
                    )
                    
                    remediation_result.success = False
                    remediation_result.outcome = Outcome.FAILED
                    remediation_result.post_validation_passed = False
                    remediation_result.error_message = "Post-validation checks failed"
                    remediation_result.validation_details["post_validation"] = {
                        "passed": False,
                        "checks": [
                            {
                                "name": c.name,
                                "passed": c.passed,
                                "message": c.message,
                                "severity": c.severity,
                            }
                            for c in post_validation_result.checks
                        ],
                    }
                    
                    if plan.requires_rollback_snapshot:
                        execution_logs.append("Rollback required due to post-validation failure")
                        rollback_success = await self._handle_rollback(incident, plan)
                        remediation_result.rollback_performed = rollback_success
                        remediation_result.rollback_required = True
                        execution_logs.append(f"Rollback: {'SUCCESS' if rollback_success else 'FAILED'}")
                else:
                    remediation_result.post_validation_passed = True
            
            # Update final result
            duration = (datetime.now() - start_time).seconds
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            remediation_result.duration_seconds = duration
            remediation_result.execution_logs = execution_logs

            logger.info(
                "remediation_service_complete",
                incident_id=incident.incident_id,
                success=remediation_result.success,
                outcome=remediation_result.outcome.value,
                duration=duration,
            )

            # Log remediation completion
            if app_logger:
                if remediation_result.success:
                    app_logger.remediation_complete(
                        f"Remediation completed successfully: {remediation_result.outcome.value}",
                        duration_ms=duration_ms,
                        details={
                            "outcome": remediation_result.outcome.value,
                            "action_type": plan.action_type.value,
                            "success": True,
                        }
                    )
                else:
                    app_logger.error(
                        f"Remediation failed: {remediation_result.error_message}",
                        category=LogCategory.REMEDIATION,
                        stage="remediation_executing",
                        details={
                            "outcome": remediation_result.outcome.value,
                            "error": remediation_result.error_message,
                        }
                    )

            return remediation_result
        
        except Exception as e:
            logger.error(
                "remediation_service_error",
                incident_id=incident.incident_id,
                error=str(e),
                traceback=traceback.format_exc(),
            )

            # Log unexpected error
            if app_logger:
                app_logger.error(
                    f"Unexpected error during remediation: {str(e)}",
                    error_obj=e,
                    category=LogCategory.REMEDIATION,
                    stage="remediation_executing",
                )

            duration = (datetime.now() - start_time).seconds
            execution_logs.append(f"ERROR: {str(e)}")

            return RemediationResult(
                success=False,
                outcome=Outcome.FAILED,
                message="Unexpected error during remediation workflow",
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                duration_seconds=duration,
                execution_logs=execution_logs,
            )
    
    async def _handle_rollback(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> bool:
        """
        Handle rollback of failed remediation.
        
        Args:
            incident: Incident being remediated
            plan: Remediation plan that failed
            
        Returns:
            True if rollback succeeded, False otherwise
        """
        logger.info(
            "rollback_start",
            incident_id=incident.incident_id,
            action_type=plan.action_type.value,
        )
        
        try:
            # TODO: Implement actual rollback logic
            # For now, just log the attempt
            logger.warning(
                "rollback_not_implemented",
                incident_id=incident.incident_id,
                message="Rollback functionality not yet implemented",
            )
            
            # Placeholder - would call RollbackService here
            return False
        
        except Exception as e:
            logger.error(
                "rollback_error",
                incident_id=incident.incident_id,
                error=str(e),
                traceback=traceback.format_exc(),
            )
            return False
    
    async def validate_plan(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> Dict[str, Any]:
        """
        Validate a remediation plan without executing it.
        
        Runs all validation checks and returns results.
        
        Args:
            incident: Incident to validate against
            plan: Remediation plan to validate
            
        Returns:
            Dictionary with validation results
        """
        logger.info(
            "validate_plan_start",
            incident_id=incident.incident_id,
            action_type=plan.action_type.value,
        )
        
        results = {
            "overall_passed": True,
            "checks": {},
        }
        
        pre_result = await self.pre_validator.validate(incident, plan)
        results["checks"]["pre_validation"] = {
            "passed": pre_result.passed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "severity": c.severity,
                }
                for c in pre_result.checks
            ],
        }
        
        if not pre_result.passed:
            results["overall_passed"] = False
        
        blast_result = await self.blast_radius_validator.validate(incident, plan)
        results["checks"]["blast_radius"] = {
            "passed": blast_result.passed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "severity": c.severity,
                }
                for c in blast_result.checks
            ],
        }
        
        if not blast_result.passed:
            results["overall_passed"] = False
        
        logger.info(
            "validate_plan_complete",
            incident_id=incident.incident_id,
            overall_passed=results["overall_passed"],
        )
        
        return results
