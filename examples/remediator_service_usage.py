# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Remediator Service Usage Examples

Demonstrates how to use RemediatorService for complete remediation workflows.
"""

import asyncio
from datetime import datetime

from app.services.remediator import RemediatorService
from app.domain.remediators.github_rerun import GitHubRerunRemediator
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    RemediationActionType,
    RiskLevel,
    Outcome,
)


async def example_basic_remediation():
    """Example: Basic remediation with all validations."""
    print("\n" + "=" * 70)
    print("Example 1: Basic Remediation with Full Validation")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_service_001",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed",
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 123456789,
            "service_name": "my-service",
            "environment": "prod",
        },
        confidence=0.95,
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
        reason="Transient test failure detected",
    )
    
    remediator = GitHubRerunRemediator()
    service = RemediatorService()
    
    try:
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=remediator,
        )
        
        print(f"Success: {result.success}")
        print(f"Outcome: {result.outcome.value}")
        print(f"Duration: {result.duration_seconds}s")
        print(f"Pre-validation passed: {result.pre_validation_passed}")
        print(f"Post-validation passed: {result.post_validation_passed}")
        
        print(f"\nExecution logs:")
        for log in result.execution_logs:
            print(f"  - {log}")
        
        if result.success:
            print(f"\n✓ Remediation succeeded")
        else:
            print(f"\n✗ Remediation failed: {result.error_message}")
    
    finally:
        await remediator.close()


async def example_skip_validations():
    """Example: Skip validation steps."""
    print("\n" + "=" * 70)
    print("Example 2: Skip Validation Steps")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_service_002",
        source=IncidentSource.GITHUB,
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 987654321,
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.LOW,
    )
    
    remediator = GitHubRerunRemediator()
    service = RemediatorService()
    
    try:
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=remediator,
            skip_pre_validation=True,
            skip_post_validation=True,
            skip_blast_radius_check=True,
        )
        
        print(f"Result: {result.success}")
        print("All validations were skipped")
    
    finally:
        await remediator.close()


async def example_pre_validation_failure():
    """Example: Handle pre-validation failure."""
    print("\n" + "=" * 70)
    print("Example 3: Pre-Validation Failure")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_service_003",
        source=IncidentSource.GITHUB,
        severity=Severity.CRITICAL,
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 111222333,
            "environment": "prod",
        },
        confidence=0.60,
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.HIGH,
    )
    
    remediator = GitHubRerunRemediator()
    service = RemediatorService()
    
    try:
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=remediator,
        )
        
        print(f"Success: {result.success}")
        print(f"Pre-validation passed: {result.pre_validation_passed}")
        print(f"Message: {result.message}")
        
        if result.validation_details:
            print(f"\nValidation details:")
            for check_type, details in result.validation_details.items():
                print(f"  {check_type}: {details['passed']}")
                if not details['passed']:
                    print(f"    Failed checks:")
                    for check in details.get('checks', []):
                        if not check['passed']:
                            print(f"      - {check['name']}: {check['message']}")
    
    finally:
        await remediator.close()


async def example_blast_radius_exceeded():
    """Example: Blast radius limit exceeded."""
    print("\n" + "=" * 70)
    print("Example 4: Blast Radius Limit Exceeded")
    print("=" * 70)
    
    service = RemediatorService()
    remediator = GitHubRerunRemediator()
    
    service_name = "rapid-service"
    
    results = []
    for i in range(12): 
        incident = Incident(
            incident_id=f"inc_blast_{i:03d}",
            source=IncidentSource.GITHUB,
            context={
                "owner": "myorg",
                "repo": "myrepo",
                "run_id": 100000 + i,
                "service_name": service_name,
            },
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
            risk_level=RiskLevel.MEDIUM,
        )
        
        try:
            result = await service.execute_remediation(
                incident=incident,
                plan=plan,
                remediator=remediator,
                skip_pre_validation=True, 
                skip_post_validation=True,
            )
            
            results.append((i + 1, result))
        
        except Exception as e:
            results.append((i + 1, str(e)))
    
    print("Remediation attempts:")
    for attempt_num, result in results:
        if isinstance(result, str):
            print(f"  Fix #{attempt_num}: ERROR - {result}")
        elif result.success:
            print(f"  Fix #{attempt_num}: ✓ ALLOWED")
        else:
            print(f"  Fix #{attempt_num}: ✗ BLOCKED - {result.message}")
    
    await remediator.close()


async def example_validate_plan_only():
    """Example: Validate plan without executing."""
    print("\n" + "=" * 70)
    print("Example 5: Validate Plan Only")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_service_005",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 444555666,
            "environment": "prod",
        },
        confidence=0.92,
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    
    service = RemediatorService()
    
    validation_results = await service.validate_plan(incident, plan)
    
    print(f"Overall passed: {validation_results['overall_passed']}")
    print(f"\nValidation checks:")
    
    for check_type, details in validation_results['checks'].items():
        print(f"\n  {check_type}:")
        print(f"    Passed: {details['passed']}")
        
        failed_checks = [c for c in details['checks'] if not c['passed']]
        if failed_checks:
            print(f"    Failed checks:")
            for check in failed_checks:
                print(f"      - {check['name']}: {check['message']}")


async def example_with_rollback():
    """Example: Remediation with rollback on failure."""
    print("\n" + "=" * 70)
    print("Example 6: Remediation with Rollback")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_service_006",
        source=IncidentSource.GITHUB,
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 777888999,
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.HIGH,
        requires_rollback_snapshot=True, 
    )
    
    remediator = GitHubRerunRemediator()
    service = RemediatorService()
    
    try:
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=remediator,
        )
        
        print(f"Success: {result.success}")
        print(f"Rollback required: {result.rollback_required}")
        print(f"Rollback performed: {result.rollback_performed}")
        
        if result.rollback_performed:
            print("\n✓ Rollback was executed")
        elif result.rollback_required:
            print("\n⚠ Rollback was required but failed")
    
    finally:
        await remediator.close()


async def example_complete_workflow():
    """Example: Complete remediation workflow."""
    print("\n" + "=" * 70)
    print("Example 7: Complete Remediation Workflow")
    print("=" * 70)
    
    print("1. Incident detected")
    incident = Incident(
        incident_id="inc_complete_workflow",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="npm test failed",
        context={
            "owner": "myorg",
            "repo": "production-app",
            "run_id": 123456789,
            "service_name": "api-service",
            "environment": "prod",
            "branch": "main",
        },
        confidence=0.94,
    )
    print(f"   ID: {incident.incident_id}")
    print(f"   Confidence: {incident.confidence:.0%}")
    
    print("\n2. Creating remediation plan")
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
        estimated_duration_seconds=300,
        requires_approval=False,
        requires_rollback_snapshot=True,
        reason="Transient test failure - safe to retry",
    )
    print(f"   Action: {plan.action_type.value}")
    print(f"   Risk: {plan.risk_level.value}")
    
    print("\n3. Validating plan")
    service = RemediatorService()
    validation = await service.validate_plan(incident, plan)
    print(f"   Validation passed: {validation['overall_passed']}")
    
    if not validation['overall_passed']:
        print("   ✗ Validation failed - aborting")
        return
    
    print("\n4. Executing remediation")
    remediator = GitHubRerunRemediator()
    
    try:
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=remediator,
        )
        
        print("\n5. Results")
        print(f"   Success: {result.success}")
        print(f"   Outcome: {result.outcome.value}")
        print(f"   Duration: {result.duration_seconds}s")
        print(f"   Pre-validation: {'✓' if result.pre_validation_passed else '✗'}")
        print(f"   Post-validation: {'✓' if result.post_validation_passed else '✗'}")
        
        print(f"\n   Execution timeline:")
        for i, log in enumerate(result.execution_logs, 1):
            print(f"     {i}. {log}")
        
        if result.success:
            print(f"\n   ✓ Incident remediated successfully")
            incident.outcome = Outcome.SUCCESS
            incident.resolved_at = datetime.now()
        else:
            print(f"\n   ✗ Remediation failed")
            print(f"   Error: {result.error_message}")
            incident.outcome = Outcome.FAILED
    
    finally:
        await remediator.close()


async def main():
    """Run all examples."""
    examples = [
        example_basic_remediation,
        example_skip_validations,
        example_pre_validation_failure,
        example_blast_radius_exceeded,
        example_validate_plan_only,
        example_with_rollback,
        example_complete_workflow,
    ]
    
    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"Example failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
