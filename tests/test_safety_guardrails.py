# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Test script for safety guardrails.

This script tests the three main safety mechanisms:
1. Blast radius limit (11 fixes in an hour should block)
2. Confidence threshold (low confidence should escalate)
3. Blacklist rule (dangerous combinations should refuse)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.domain.validators import (
    PreRemediationValidator,
    BlastRadiusValidator,
)
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
from app.core.config import Settings


def print_header(title: str, char: str = "="):
    """Print a formatted header."""
    print(f"\n{char * 80}")
    print(f"{title:^80}")
    print(f"{char * 80}\n")


def print_subheader(title: str):
    """Print a formatted subheader."""
    print(f"\n{'-' * 80}")
    print(f"{title}")
    print(f"{'-' * 80}")


def print_result(passed: bool, message: str, details: str = ""):
    """Print a test result."""
    status = "✓ PASSED" if passed else "✗ FAILED"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset}: {message}")
    if details:
        print(f"  → {details}")


async def test_blast_radius_limit():
    """
    Test 1: Try to execute 11 fixes in an hour → Should block the 11th
    """
    print_header("TEST 1: BLAST RADIUS LIMIT (11 FIXES IN AN HOUR)")
    
    print("Testing both BlastRadiusValidator and BlastRadiusRule...")
    print("Expected: First 10 fixes allowed, 11th should be blocked\n")
    
    print_subheader("Using BlastRadiusValidator")
    
    validator = BlastRadiusValidator()
    service_name = "test-service-validator"
    
    allowed_count = 0
    blocked_count = 0
    
    for i in range(12):  
        incident = Incident(
            incident_id=f"inc_blast_val_{i:03d}",
            source=IncidentSource.KUBERNETES,
            severity=Severity.MEDIUM,
            failure_type=FailureType.CRASH_LOOP_BACKOFF,
            error_log=f"Test crash loop {i}",
            error_message="CrashLoopBackOff",
            confidence=0.95,
            context={
                "service": service_name,
                "environment": "staging",
                "namespace": "test",
            },
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.K8S_RESTART_POD,
            risk_level=RiskLevel.LOW,
            estimated_duration_seconds=30,
        )
        
        result = await validator.validate(incident, plan)
        
        if result.passed:
            allowed_count += 1
            validator.record_execution_start(incident)
            validator.record_execution_end(incident, success=True)
            print(f"  Fix #{i+1:2d}: ✓ ALLOWED")
        else:
            blocked_count += 1
            print(f"  Fix #{i+1:2d}: ✗ BLOCKED - {result.message}")
            for check in result.get_failed_checks():
                print(f"           Reason: {check.message}")
            break
    
    # Verify results
    print(f"\nResults:")
    print(f"  Allowed: {allowed_count}")
    print(f"  Blocked: {blocked_count}")
    
    validator_passed = allowed_count == 10 and blocked_count == 1
    print_result(
        validator_passed,
        "BlastRadiusValidator correctly blocked 11th fix",
        f"Allowed {allowed_count}/10, blocked {blocked_count}"
    )
    
    print_subheader("Using BlastRadiusRule")
    
    rule = BlastRadiusRule()
    service_name_rule = "test-service-rule"
    
    allowed_count_rule = 0
    blocked_count_rule = 0
    
    for i in range(12): 
        incident = Incident(
            incident_id=f"inc_blast_rule_{i:03d}",
            source=IncidentSource.KUBERNETES,
            severity=Severity.MEDIUM,
            failure_type=FailureType.CRASH_LOOP_BACKOFF,
            error_log=f"Test crash loop {i}",
            confidence=0.95,
            context={
                "service": service_name_rule,
                "environment": "staging",
            },
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.K8S_RESTART_POD,
            risk_level=RiskLevel.LOW,
        )
        
        result = await rule.evaluate(incident, plan)
        
        if result.passed:
            allowed_count_rule += 1
            rule.record_execution(incident)
            print(f"  Fix #{i+1:2d}: ✓ ALLOWED")
        else:
            blocked_count_rule += 1
            print(f"  Fix #{i+1:2d}: ✗ BLOCKED - {result.message}")
            if result.reason:
                print(f"           Reason: {result.reason}")
            break
    
    stats = rule.get_statistics()
    print(f"\nStatistics:")
    print(f"  Service '{service_name_rule}': {stats['hourly_fixes_by_service'].get(service_name_rule, 0)}/10 fixes")
    print(f"  Global total: {stats['total_daily_fixes']} fixes")
    
    rule_passed = allowed_count_rule == 10 and blocked_count_rule == 1
    print_result(
        rule_passed,
        "BlastRadiusRule correctly blocked 11th fix",
        f"Allowed {allowed_count_rule}/10, blocked {blocked_count_rule}"
    )
    
    overall_passed = validator_passed and rule_passed
    print_result(
        overall_passed,
        "TEST 1 OVERALL",
        "Both validator and rule correctly enforce blast radius limits"
    )
    
    return overall_passed


async def test_low_confidence():
    """
    Test 2: Try with low confidence → Should escalate
    """
    print_header("TEST 2: LOW CONFIDENCE THRESHOLD")
    
    print("Testing with confidence below production threshold (95%)")
    print("Expected: Should fail validation and suggest escalation\n")
    
    print_subheader("Using PreRemediationValidator")
    
    incident_validator = Incident(
        incident_id="inc_lowconf_validator",
        source=IncidentSource.KUBERNETES,
        severity=Severity.HIGH,
        failure_type=FailureType.CRASH_LOOP_BACKOFF,
        error_log="Service keeps crashing",
        error_message="CrashLoopBackOff",
        confidence=0.75,  # Low confidence for production
        context={
            "service": "critical-service",
            "environment": "prod",
            "namespace": "production",
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.K8S_RESTART_POD,
        risk_level=RiskLevel.MEDIUM,
        estimated_duration_seconds=30,
    )
    
    validator = PreRemediationValidator()
    result = await validator.validate(incident_validator, plan)
    
    print(f"Incident ID: {incident_validator.incident_id}")
    print(f"Environment: production")
    print(f"Confidence: {incident_validator.confidence:.2%}")
    print(f"Required: 95%+\n")
    
    print(f"Validation Result: {'✓ PASSED' if result.passed else '✗ FAILED'}")
    print(f"Message: {result.message}\n")
    
    print("Failed Checks:")
    for check in result.get_failed_checks():
        print(f"  - {check.name}: {check.message}")
    
    validator_passed = not result.passed 
    print_result(
        validator_passed,
        "PreRemediationValidator correctly rejected low confidence",
        f"Confidence {incident_validator.confidence:.2%} < 95% required"
    )
    
    print_subheader("Using ConfidenceRule")
    
    incident_rule = Incident(
        incident_id="inc_lowconf_rule",
        source=IncidentSource.KUBERNETES,
        severity=Severity.CRITICAL, 
        failure_type=FailureType.OOM_KILLED,
        error_log="Pod killed due to OOM",
        confidence=0.80, 
        context={
            "service": "critical-service",
            "environment": "prod",
        },
    )
    
    rule = ConfidenceRule()
    result = await rule.evaluate(incident_rule, plan)
    
    print(f"Incident ID: {incident_rule.incident_id}")
    print(f"Environment: production")
    print(f"Severity: {incident_rule.severity.value}")
    print(f"Confidence: {incident_rule.confidence:.2%}")
    print(f"Required: 98%+ (critical in production)\n")
    
    print(f"Rule Result: {'✓ PASSED' if result.passed else '✗ FAILED'}")
    print(f"Message: {result.message}")
    if result.reason:
        print(f"Reason: {result.reason}")
    
    rule_passed = not result.passed  
    print_result(
        rule_passed,
        "ConfidenceRule correctly rejected low confidence",
        f"Confidence {incident_rule.confidence:.2%} < 98% required for critical"
    )
    
    overall_passed = validator_passed and rule_passed
    print_result(
        overall_passed,
        "TEST 2 OVERALL",
        "Both validator and rule correctly reject low confidence and suggest escalation"
    )
    
    return overall_passed


async def test_blacklisted_combination():
    """
    Test 3: Try blacklisted combo → Should refuse
    """
    print_header("TEST 3: BLACKLISTED COMBINATIONS")
    
    print("Testing dangerous failure_type + action_type combinations")
    print("Expected: Should refuse to execute blacklisted combinations\n")
    
    test_cases = [
        {
            "name": "OOM Killed + Restart Pod",
            "failure_type": FailureType.OOM_KILLED,
            "action_type": RemediationActionType.K8S_RESTART_POD,
            "should_block": True,
            "reason": "OOM needs resource adjustment, not restart",
        },
        {
            "name": "Auth Expired + Restart Pod",
            "failure_type": FailureType.AUTH_EXPIRED,
            "action_type": RemediationActionType.K8S_RESTART_POD,
            "should_block": True,
            "reason": "Auth issues need secret rotation, not restart",
        },
        {
            "name": "Config Error + Restart Pod",
            "failure_type": FailureType.CONFIG_ERROR,
            "action_type": RemediationActionType.K8S_RESTART_POD,
            "should_block": True,
            "reason": "Config errors need manual fix",
        },
        {
            "name": "Crash Loop + Restart Pod (ALLOWED)",
            "failure_type": FailureType.CRASH_LOOP_BACKOFF,
            "action_type": RemediationActionType.K8S_RESTART_POD,
            "should_block": False,
            "reason": "Valid combination",
        },
    ]
    
    print_subheader("Using PreRemediationValidator")
    
    validator = PreRemediationValidator()
    validator_results = []
    
    for test_case in test_cases:
        incident = Incident(
            incident_id=f"inc_blacklist_{test_case['failure_type'].value}",
            source=IncidentSource.KUBERNETES,
            severity=Severity.HIGH,
            failure_type=test_case["failure_type"],
            error_log=f"Test {test_case['failure_type'].value}",
            confidence=0.96, 
            context={
                "service": "test-service",
                "environment": "staging",
            },
        )
        
        plan = RemediationPlan(
            action_type=test_case["action_type"],
            risk_level=RiskLevel.MEDIUM,
        )
        
        result = await validator.validate(incident, plan)
        
        blacklist_check = next(
            (c for c in result.checks if c.name == "blacklist_check"),
            None
        )
        
        print(f"\n  {test_case['name']}:")
        print(f"    Expected: {'BLOCK' if test_case['should_block'] else 'ALLOW'}")
        print(f"    Result: {'BLOCKED' if not result.passed else 'ALLOWED'}")
        
        if blacklist_check and not blacklist_check.passed:
            print(f"    Reason: {blacklist_check.message}")
        
        if test_case["should_block"]:
            passed = not result.passed
        else:
            passed = result.passed
        
        validator_results.append(passed)
        status = "✓" if passed else "✗"
        print(f"    Status: {status}")
    
    validator_passed = all(validator_results)
    print_result(
        validator_passed,
        "PreRemediationValidator blacklist checks",
        f"{sum(validator_results)}/{len(validator_results)} test cases passed"
    )
    
    print_subheader("Using BlacklistRule")
    
    rule = BlacklistRule()
    rule_results = []
    
    for test_case in test_cases:
        incident = Incident(
            incident_id=f"inc_blacklist_rule_{test_case['failure_type'].value}",
            source=IncidentSource.KUBERNETES,
            severity=Severity.HIGH,
            failure_type=test_case["failure_type"],
            error_log=f"Test {test_case['failure_type'].value}",
            confidence=0.96,
            context={"service": "test-service"},
        )
        
        plan = RemediationPlan(
            action_type=test_case["action_type"],
            risk_level=RiskLevel.MEDIUM,
        )
        
        result = await rule.evaluate(incident, plan)
        
        print(f"\n  {test_case['name']}:")
        print(f"    Expected: {'BLOCK' if test_case['should_block'] else 'ALLOW'}")
        print(f"    Result: {'BLOCKED' if not result.passed else 'ALLOWED'}")
        print(f"    Message: {result.message}")
        if result.reason:
            print(f"    Reason: {result.reason}")
        
        if test_case["should_block"]:
            passed = not result.passed
        else:
            passed = result.passed
        
        rule_results.append(passed)
        status = "✓" if passed else "✗"
        print(f"    Status: {status}")
    
    print(f"\nBlacklist Statistics:")
    print(f"  Total blacklisted combinations: {rule.get_blacklist_size()}")
    
    rule_passed = all(rule_results)
    print_result(
        rule_passed,
        "BlacklistRule correctly identifies dangerous combinations",
        f"{sum(rule_results)}/{len(rule_results)} test cases passed"
    )
    
    overall_passed = validator_passed and rule_passed
    print_result(
        overall_passed,
        "TEST 3 OVERALL",
        "Both validator and rule correctly refuse blacklisted combinations"
    )
    
    return overall_passed


async def main():
    """Run all safety guardrail tests."""
    print_header("SAFETY GUARDRAILS TEST SUITE", "=")
    print("Testing three critical safety mechanisms:")
    print("1. Blast Radius Limit - Prevent too many fixes in short time")
    print("2. Low Confidence - Ensure high confidence before auto-fix")
    print("3. Blacklisted Combinations - Block dangerous action combinations")
    
    test1_passed = await test_blast_radius_limit()
    test2_passed = await test_low_confidence()
    test3_passed = await test_blacklisted_combination()
    
    print_header("TEST SUMMARY", "=")
    
    tests = [
        ("Blast Radius Limit (11 fixes)", test1_passed),
        ("Low Confidence Escalation", test2_passed),
        ("Blacklisted Combinations", test3_passed),
    ]
    
    for test_name, passed in tests:
        print_result(passed, test_name)
    
    all_passed = all(result for _, result in tests)
    passed_count = sum(1 for _, result in tests if result)
    
    print(f"\n{'=' * 80}")
    if all_passed:
        print(f"{'✓ ALL TESTS PASSED':^80}")
        print(f"{'Safety guardrails are working correctly!':^80}")
    else:
        print(f"{'✗ SOME TESTS FAILED':^80}")
        print(f"{f'{passed_count}/{len(tests)} tests passed':^80}")
    print(f"{'=' * 80}\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
