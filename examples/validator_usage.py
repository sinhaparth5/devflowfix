# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Example usage of the validator classes.

This demonstrates how to use the safety guardrail validators
in the remediation pipeline.
"""

import asyncio
from datetime import datetime

from app.domain.validators import (
    PreRemediationValidator,
    PostRemediationValidator,
    BlastRadiusValidator,
)
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


async def example_validation_workflow():
    """
    Example workflow showing all three validators in action.
    """
    
    incident = Incident(
        incident_id="inc_test_001",
        source=IncidentSource.KUBERNETES,
        severity=Severity.HIGH,
        failure_type=FailureType.CRASH_LOOP_BACKOFF,
        error_log="pod continuously crashing with exit code 1",
        error_message="CrashLoopBackOff",
        confidence=0.92,
        context={
            "service": "payment-service",
            "namespace": "production",
            "environment": "prod",
            "pod": "payment-service-7d9f8c9b-xk2zj",
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.K8S_RESTART_POD,
        parameters={
            "pod_name": "payment-service-7d9f8c9b-xk2zj",
            "namespace": "production",
        },
        risk_level=RiskLevel.MEDIUM,
        estimated_duration_seconds=30,
        requires_approval=False,
    )
    
    print("=" * 60)
    print("VALIDATION WORKFLOW EXAMPLE")
    print("=" * 60)
    
    print("\n1. PRE-REMEDIATION VALIDATION")
    print("-" * 60)
    
    pre_validator = PreRemediationValidator()
    pre_result = await pre_validator.validate(incident, plan)
    
    print(f"Overall Result: {'✓ PASSED' if pre_result.passed else '✗ FAILED'}")
    print(f"Message: {pre_result.message}")
    print(f"\nChecks performed: {len(pre_result.checks)}")
    
    for check in pre_result.checks:
        status = "✓" if check.passed else "✗"
        print(f"  {status} {check.name}: {check.message}")
    
    if not pre_result.passed:
        print("\n⚠️  Pre-validation failed. Remediation should not proceed.")
        return
    
    print("\n2. BLAST RADIUS VALIDATION")
    print("-" * 60)
    
    blast_validator = BlastRadiusValidator()
    blast_result = await blast_validator.validate(incident, plan)
    
    print(f"Overall Result: {'✓ PASSED' if blast_result.passed else '✗ FAILED'}")
    print(f"Message: {blast_result.message}")
    print(f"\nChecks performed: {len(blast_result.checks)}")
    
    for check in blast_result.checks:
        status = "✓" if check.passed else "✗"
        print(f"  {status} {check.name}: {check.message}")
    
    if not blast_result.passed:
        print("\n⚠️  Blast radius limit exceeded. Too many recent fixes.")
        return
    
    blast_validator.record_execution_start(incident)
    
    print("\n3. EXECUTING REMEDIATION")
    print("-" * 60)
    print("Executing remediation action: K8S_RESTART_POD")
    print("(simulated execution)")
    
    incident.start_remediation()
    await asyncio.sleep(0.1)  
    incident.end_remediation(success=True, message="Pod restarted successfully")
    
    blast_validator.record_execution_end(incident, success=True)
    
    print("\n4. POST-REMEDIATION VALIDATION")
    print("-" * 60)
    
    post_validator = PostRemediationValidator()
    post_result = await post_validator.validate(incident, plan)
    
    print(f"Overall Result: {'✓ PASSED' if post_result.passed else '✗ FAILED'}")
    print(f"Message: {post_result.message}")
    print(f"\nChecks performed: {len(post_result.checks)}")
    
    for check in post_result.checks:
        status = "✓" if check.passed else "✗"
        print(f"  {status} {check.name}: {check.message}")
    
    print("\n5. BLAST RADIUS STATISTICS")
    print("-" * 60)
    
    stats = blast_validator.get_statistics()
    print(f"Concurrent executions: {stats['concurrent_executions']}/{stats['max_concurrent']}")
    print(f"Total daily fixes: {stats['total_daily_fixes']}/{stats['max_daily_global']}")
    print(f"\nHourly fixes by service:")
    for service, count in stats['hourly_fixes_by_service'].items():
        print(f"  - {service}: {count}/{stats['max_hourly_per_service']}")
    
    print("\n" + "=" * 60)
    print("VALIDATION WORKFLOW COMPLETED SUCCESSFULLY")
    print("=" * 60)


async def example_blast_radius_exceeded():
    """
    Example showing what happens when blast radius limits are exceeded.
    """
    
    print("\n" + "=" * 60)
    print("BLAST RADIUS LIMIT EXCEEDED EXAMPLE")
    print("=" * 60)
    
    blast_validator = BlastRadiusValidator()
    
    service_name = "api-gateway"
    
    for i in range(12):  
        incident = Incident(
            incident_id=f"inc_test_{i:03d}",
            source=IncidentSource.KUBERNETES,
            severity=Severity.MEDIUM,
            failure_type=FailureType.IMAGE_PULL_BACKOFF,
            error_log=f"Test error {i}",
            confidence=0.95,
            context={"service": service_name},
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.K8S_RESTART_POD,
            risk_level=RiskLevel.LOW,
        )
        
        result = await blast_validator.validate(incident, plan)
        
        if result.passed:
            print(f"Fix #{i+1}: ✓ ALLOWED")
            blast_validator.record_execution_start(incident)
            blast_validator.record_execution_end(incident, success=True)
        else:
            print(f"Fix #{i+1}: ✗ BLOCKED - {result.message}")
            for check in result.get_failed_checks():
                print(f"  Reason: {check.message}")
            break
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(example_validation_workflow())
    asyncio.run(example_blast_radius_exceeded())
