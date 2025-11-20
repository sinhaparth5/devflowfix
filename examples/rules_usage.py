# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Example usage of the business rule classes.

This demonstrates how to use the business rules in the
remediation decision pipeline.
"""

import asyncio
from datetime import datetime

from app.domain.rules import (
    ConfidenceRule,
    BlastRadiusRule,
    BlacklistRule,
)
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    RemediationActionType,
    RiskLevel,
)


async def example_rules_workflow():
    """
    Example workflow showing all three rules in action.
    """
    
    # Create a sample incident
    incident = Incident(
        incident_id="inc_rules_001",
        source=IncidentSource.KUBERNETES,
        severity=Severity.HIGH,
        failure_type=FailureType.CRASH_LOOP_BACKOFF,
        error_log="pod continuously crashing with exit code 1",
        error_message="CrashLoopBackOff",
        confidence=0.92,  # 92% confidence
        context={
            "service": "payment-service",
            "namespace": "production",
            "environment": "prod",
            "pod": "payment-service-7d9f8c9b-xk2zj",
        },
    )
    
    # Create a remediation plan
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
    
    print("=" * 70)
    print("BUSINESS RULES EVALUATION")
    print("=" * 70)
    print(f"\nIncident: {incident.incident_id}")
    print(f"Service: {incident.get_service_name()}")
    print(f"Failure: {incident.failure_type.value}")
    print(f"Action: {plan.action_type.value}")
    print(f"Confidence: {incident.confidence:.2%}")
    
    # 1. Confidence Rule
    print("\n" + "-" * 70)
    print("1. CONFIDENCE RULE")
    print("-" * 70)
    
    confidence_rule = ConfidenceRule()
    confidence_result = await confidence_rule.evaluate(incident, plan)
    
    print(f"Result: {'✓ PASSED' if confidence_result.passed else '✗ FAILED'}")
    print(f"Message: {confidence_result.message}")
    if confidence_result.reason:
        print(f"Reason: {confidence_result.reason}")
    
    # 2. Blacklist Rule
    print("\n" + "-" * 70)
    print("2. BLACKLIST RULE")
    print("-" * 70)
    
    blacklist_rule = BlacklistRule()
    blacklist_result = await blacklist_rule.evaluate(incident, plan)
    
    print(f"Result: {'✓ PASSED' if blacklist_result.passed else '✗ FAILED'}")
    print(f"Message: {blacklist_result.message}")
    if blacklist_result.reason:
        print(f"Reason: {blacklist_result.reason}")
    
    # 3. Blast Radius Rule
    print("\n" + "-" * 70)
    print("3. BLAST RADIUS RULE")
    print("-" * 70)
    
    blast_radius_rule = BlastRadiusRule()
    blast_radius_result = await blast_radius_rule.evaluate(incident, plan)
    
    print(f"Result: {'✓ PASSED' if blast_radius_result.passed else '✗ FAILED'}")
    print(f"Message: {blast_radius_result.message}")
    
    # Show statistics
    stats = blast_radius_rule.get_statistics()
    print(f"\nBlast Radius Stats:")
    print(f"  Daily fixes: {stats['total_daily_fixes']}/{stats['max_daily_global']}")
    print(f"  Hourly fixes by service: {stats['hourly_fixes_by_service']}")
    
    # 4. Final Decision
    print("\n" + "-" * 70)
    print("4. FINAL DECISION")
    print("-" * 70)
    
    all_passed = all([
        confidence_result.passed,
        blacklist_result.passed,
        blast_radius_result.passed,
    ])
    
    if all_passed:
        print("✓ ALL RULES PASSED - Remediation can proceed")
        blast_radius_rule.record_execution(incident)
    else:
        print("✗ SOME RULES FAILED - Remediation blocked")
        print("\nFailed rules:")
        if not confidence_result.passed:
            print(f"  - Confidence Rule: {confidence_result.message}")
        if not blacklist_result.passed:
            print(f"  - Blacklist Rule: {blacklist_result.message}")
        if not blast_radius_result.passed:
            print(f"  - Blast Radius Rule: {blast_radius_result.message}")
    
    print("\n" + "=" * 70)


async def example_blacklisted_combination():
    """
    Example showing a blacklisted combination being rejected.
    """
    
    print("\n" + "=" * 70)
    print("BLACKLISTED COMBINATION EXAMPLE")
    print("=" * 70)
    
    # OOM killed with restart action (blacklisted!)
    incident = Incident(
        incident_id="inc_blacklist_001",
        source=IncidentSource.KUBERNETES,
        severity=Severity.HIGH,
        failure_type=FailureType.OOM_KILLED,
        error_log="Pod killed due to OOM",
        error_message="OOMKilled",
        confidence=0.95,  # High confidence
        context={
            "service": "memory-hog-service",
            "environment": "prod",
        },
    )
    
    # Try to restart the pod (wrong action!)
    plan = RemediationPlan(
        action_type=RemediationActionType.K8S_RESTART_POD,
        risk_level=RiskLevel.LOW,
    )
    
    print(f"\nIncident: OOM Killed")
    print(f"Proposed Action: Restart Pod")
    print(f"Confidence: {incident.confidence:.2%}")
    
    blacklist_rule = BlacklistRule()
    result = await blacklist_rule.evaluate(incident, plan)
    
    print(f"\nBlacklist Rule Result: {'✓ PASSED' if result.passed else '✗ FAILED'}")
    print(f"Message: {result.message}")
    if result.reason:
        print(f"Reason: {result.reason}")
    
    if not result.passed:
        print("\n⚠️  This combination is blacklisted!")
        print("Suggested action: Increase memory limits instead of restarting")
    
    print("\n" + "=" * 70)


async def example_low_confidence():
    """
    Example showing low confidence being rejected.
    """
    
    print("\n" + "=" * 70)
    print("LOW CONFIDENCE EXAMPLE")
    print("=" * 70)
    
    # Low confidence incident
    incident = Incident(
        incident_id="inc_lowconf_001",
        source=IncidentSource.KUBERNETES,
        severity=Severity.MEDIUM,
        failure_type=FailureType.IMAGE_PULL_BACKOFF,
        error_log="Failed to pull image",
        confidence=0.75,  # Low confidence for production
        context={
            "service": "api-service",
            "environment": "prod",
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.K8S_RESTART_POD,
        risk_level=RiskLevel.LOW,
    )
    
    print(f"\nIncident: Image Pull Backoff")
    print(f"Environment: Production")
    print(f"Confidence: {incident.confidence:.2%}")
    print(f"Required: 95%+ for production")
    
    confidence_rule = ConfidenceRule()
    result = await confidence_rule.evaluate(incident, plan)
    
    print(f"\nConfidence Rule Result: {'✓ PASSED' if result.passed else '✗ FAILED'}")
    print(f"Message: {result.message}")
    if result.reason:
        print(f"Reason: {result.reason}")
    
    if not result.passed:
        print("\n⚠️  Confidence too low for production auto-fix!")
        print("Recommended: Escalate to human for review")
    
    print("\n" + "=" * 70)


async def example_blast_radius_exceeded():
    """
    Example showing blast radius limit being exceeded.
    """
    
    print("\n" + "=" * 70)
    print("BLAST RADIUS EXCEEDED EXAMPLE")
    print("=" * 70)
    
    blast_radius_rule = BlastRadiusRule()
    service_name = "flaky-service"
    
    print(f"\nSimulating multiple fixes for: {service_name}")
    print(f"Limit: 10 fixes per hour per service\n")
    
    for i in range(12):  # Try 12 fixes (limit is 10)
        incident = Incident(
            incident_id=f"inc_blast_{i:03d}",
            source=IncidentSource.KUBERNETES,
            severity=Severity.MEDIUM,
            failure_type=FailureType.CRASH_LOOP_BACKOFF,
            error_log=f"Test error {i}",
            confidence=0.95,
            context={"service": service_name},
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.K8S_RESTART_POD,
            risk_level=RiskLevel.LOW,
        )
        
        result = await blast_radius_rule.evaluate(incident, plan)
        
        if result.passed:
            print(f"Fix #{i+1:2d}: ✓ ALLOWED - Executing...")
            blast_radius_rule.record_execution(incident)
        else:
            print(f"Fix #{i+1:2d}: ✗ BLOCKED - {result.message}")
            print(f"\n⚠️  Blast radius limit exceeded!")
            print(f"The service has had too many fixes recently.")
            print(f"This suggests a deeper issue that needs investigation.")
            break
    
    # Show final statistics
    stats = blast_radius_rule.get_statistics()
    print(f"\nFinal Statistics:")
    print(f"  Service '{service_name}': {stats['hourly_fixes_by_service'].get(service_name, 0)} fixes")
    print(f"  Global total: {stats['total_daily_fixes']} fixes today")
    
    print("\n" + "=" * 70)


async def example_rules_engine():
    """
    Example of combining all rules in a rules engine.
    """
    
    print("\n" + "=" * 70)
    print("RULES ENGINE EXAMPLE")
    print("=" * 70)
    
    # Create all rules
    rules = [
        ConfidenceRule(),
        BlacklistRule(),
        BlastRadiusRule(),
    ]
    
    # Test multiple incidents
    test_cases = [
        {
            "name": "Good Case - All Pass",
            "incident": Incident(
                incident_id="inc_good",
                failure_type=FailureType.CRASH_LOOP_BACKOFF,
                confidence=0.96,
                context={"service": "service-a", "environment": "prod"},
            ),
            "plan": RemediationPlan(action_type=RemediationActionType.K8S_RESTART_POD),
        },
        {
            "name": "Low Confidence",
            "incident": Incident(
                incident_id="inc_lowconf",
                failure_type=FailureType.CRASH_LOOP_BACKOFF,
                confidence=0.70,
                context={"service": "service-b", "environment": "prod"},
            ),
            "plan": RemediationPlan(action_type=RemediationActionType.K8S_RESTART_POD),
        },
        {
            "name": "Blacklisted Action",
            "incident": Incident(
                incident_id="inc_blacklist",
                failure_type=FailureType.OOM_KILLED,
                confidence=0.96,
                context={"service": "service-c", "environment": "prod"},
            ),
            "plan": RemediationPlan(action_type=RemediationActionType.K8S_RESTART_POD),
        },
    ]
    
    for test_case in test_cases:
        print(f"\nTest Case: {test_case['name']}")
        print("-" * 70)
        
        results = []
        for rule in rules:
            result = await rule.evaluate(test_case["incident"], test_case["plan"])
            results.append(result)
            status = "✓" if result.passed else "✗"
            print(f"  {status} {result.rule_name}: {result.message}")
        
        all_passed = all(r.passed for r in results)
        print(f"\nDecision: {'✓ AUTO-FIX' if all_passed else '✗ ESCALATE'}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Run all examples
    asyncio.run(example_rules_workflow())
    asyncio.run(example_blacklisted_combination())
    asyncio.run(example_low_confidence())
    asyncio.run(example_blast_radius_exceeded())
    asyncio.run(example_rules_engine())
