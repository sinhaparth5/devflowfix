#!/usr/bin/env python3
"""
Simple test script for RemediatorService

Tests basic functionality without GitHub API calls.
"""

import asyncio
from datetime import datetime

from app.services.remediator import RemediatorService
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    RemediationActionType,
    RiskLevel,
    Outcome,
)
from app.domain.remediators.base import BaseRemediator


class MockRemediator(BaseRemediator):
    """Mock remediator for testing without external dependencies."""
    
    def get_action_type(self) -> RemediationActionType:
        return RemediationActionType.GITHUB_RERUN_WORKFLOW
    
    async def execute(
        self, 
        incident: Incident, 
        plan: RemediationPlan
    ) -> RemediationResult:
        """Mock execution that always succeeds."""
        await asyncio.sleep(0.1)  # Simulate work
        
        return self._create_success_result(
            message="Mock remediation completed successfully",
            duration_seconds=1,
            actions_performed=["Simulated service restart"]
        )


async def test_basic_remediation():
    """Test basic remediation with all validations."""
    print("\n" + "=" * 70)
    print("Test 1: Basic Remediation with Full Validation")
    print("=" * 70)
    
    # Create incident with all required fields
    incident = Incident(
        incident_id="inc_test_001",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed due to test timeout",
        error_log="Error: Test suite timed out after 30 minutes",
        stack_trace="at test_suite.py:42",
        context={
            "service": "api-service",
            "environment": "staging",  # Lower threshold for staging (85%)
            "repository": "myorg/myrepo",
            "branch": "main",
        },
        confidence=0.92,  # Above staging threshold
    )
    
    # Create plan
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        parameters={"service_name": "api-service"},
        risk_level=RiskLevel.MEDIUM,
        estimated_duration_seconds=60,
        requires_approval=False,
        reason="Restart service to clear timeout state",
    )
    
    # Create mock remediator
    remediator = MockRemediator()
    
    # Create service
    service = RemediatorService()
    
    # Execute remediation
    result = await service.execute_remediation(
        incident=incident,
        plan=plan,
        remediator=remediator,
        skip_post_validation=True  # Skip post-validation for mock test
    )
    
    # Print results
    print(f"\nSuccess: {result.success}")
    print(f"Outcome: {result.outcome.value}")
    print(f"Duration: {result.duration_seconds}s")
    print(f"Pre-validation passed: {result.pre_validation_passed}")
    print(f"Post-validation passed: {result.post_validation_passed}")
    
    if result.execution_logs:
        print("\nExecution logs:")
        for log in result.execution_logs:
            print(f"  - {log}")
    
    if result.success:
        print("\n✓ Remediation completed successfully!")
    else:
        print(f"\n✗ Remediation failed: {result.error_message}")


async def test_pre_validation_failure():
    """Test that pre-validation blocks unsafe remediations."""
    print("\n" + "=" * 70)
    print("Test 2: Pre-Validation Failure (Low Confidence)")
    print("=" * 70)
    
    # Create incident with low confidence
    incident = Incident(
        incident_id="inc_test_002",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed",
        error_log="Error logs here",
        context={
            "service": "api-service",
            "environment": "production",  # Production requires 95%
        },
        confidence=0.60,  # Way below threshold
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        parameters={},
        risk_level=RiskLevel.MEDIUM,
    )
    
    remediator = MockRemediator()
    service = RemediatorService()
    
    result = await service.execute_remediation(
        incident=incident,
        plan=plan,
        remediator=remediator
    )
    
    print(f"\nSuccess: {result.success}")
    print(f"Pre-validation passed: {result.pre_validation_passed}")
    print(f"Message: {result.message}")
    
    if result.validation_details and 'pre_validation' in result.validation_details:
        pre_val = result.validation_details['pre_validation']
        if not pre_val.get('passed'):
            print("\nValidation details:")
            print(f"  pre_validation: {pre_val.get('passed')}")
            if 'failed_checks' in pre_val:
                print("    Failed checks:")
                for check, msg in pre_val['failed_checks'].items():
                    print(f"      - {check}: {msg}")


async def test_blast_radius_limit():
    """Test that blast radius validator limits execution rate."""
    print("\n" + "=" * 70)
    print("Test 3: Blast Radius Rate Limiting")
    print("=" * 70)
    
    remediator = MockRemediator()
    service = RemediatorService()
    
    # Try to execute 12 remediations rapidly
    print("\nAttempting 12 rapid remediations (limit is 10/hour)...")
    success_count = 0
    blocked_count = 0
    
    for i in range(12):
        incident = Incident(
            incident_id=f"inc_blast_{i:03d}",
            source=IncidentSource.GITHUB,
            severity=Severity.HIGH,
            failure_type=FailureType.BUILD_FAILURE,
            error_message="Build failed",
            error_log="Error logs here",
            context={
                "service": "api-service",
                "environment": "staging",
            },
            confidence=0.92,
        )
        
        plan = RemediationPlan(
            action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
            parameters={},
            risk_level=RiskLevel.LOW,
        )
        
        result = await service.execute_remediation(
            incident=incident,
            plan=plan,
            remediator=remediator,
            skip_post_validation=True  # Skip post-validation for mock test
        )
        
        if result.success:
            success_count += 1
            print(f"  Fix #{i+1}: ✓ EXECUTED")
        else:
            blocked_count += 1
            print(f"  Fix #{i+1}: ✗ BLOCKED - {result.message}")
    
    print(f"\nResults: {success_count} executed, {blocked_count} blocked")
    print(f"Expected: First 10 executed, last 2 blocked")
    
    if success_count == 10 and blocked_count == 2:
        print("✓ Blast radius limiting working correctly!")
    else:
        print("✗ Unexpected results")


async def test_validate_plan_only():
    """Test validate_plan method (dry-run validation)."""
    print("\n" + "=" * 70)
    print("Test 4: Validate Plan Only (Dry Run)")
    print("=" * 70)
    
    # Create valid incident
    incident = Incident(
        incident_id="inc_test_004",
        source=IncidentSource.GITHUB,
        severity=Severity.MEDIUM,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed",
        error_log="Error logs here",
        context={
            "service": "api-service",
            "environment": "development",  # Dev threshold is 70%
        },
        confidence=0.85,  # Above dev threshold
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        parameters={},
        risk_level=RiskLevel.LOW,
    )
    
    service = RemediatorService()
    
    # Validate without executing
    validation_result = await service.validate_plan(incident, plan)
    
    print(f"\nOverall valid: {validation_result['overall_passed']}")
    print("\nValidation checks:")
    
    for check_name, check_result in validation_result['checks'].items():
        print(f"\n  {check_name}:")
        print(f"    Passed: {check_result.get('passed')}")
        if not check_result.get('passed') and 'checks' in check_result:
            print("    Failed checks:")
            for check in check_result['checks']:
                if not check['passed']:
                    print(f"      - {check['name']}: {check['message']}")


async def test_skip_validations():
    """Test skipping validation steps."""
    print("\n" + "=" * 70)
    print("Test 5: Skip Validation Steps")
    print("=" * 70)
    
    # Create incident with low confidence (would normally fail)
    incident = Incident(
        incident_id="inc_test_005",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed",
        context={
            "service": "api-service",
            "environment": "production",
        },
        confidence=0.50,  # Very low
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        parameters={},
        risk_level=RiskLevel.LOW,
    )
    
    remediator = MockRemediator()
    service = RemediatorService()
    
    # Execute with validations skipped
    result = await service.execute_remediation(
        incident=incident,
        plan=plan,
        remediator=remediator,
        skip_pre_validation=True,  # Skip pre-validation
        skip_post_validation=True,  # Skip post-validation
    )
    
    print(f"\nSuccess: {result.success}")
    print(f"Pre-validation passed: {result.pre_validation_passed}")
    print(f"Post-validation passed: {result.post_validation_passed}")
    print("\nNote: Validations were skipped, so remediation proceeded despite low confidence")
    
    if result.success:
        print("✓ Remediation completed (validations skipped)")


async def main():
    """Run all tests."""
    print("=" * 70)
    print("RemediatorService Simple Tests")
    print("=" * 70)
    
    tests = [
        ("Basic Remediation", test_basic_remediation),
        ("Pre-Validation Failure", test_pre_validation_failure),
        ("Blast Radius Limiting", test_blast_radius_limit),
        ("Validate Plan Only", test_validate_plan_only),
        ("Skip Validations", test_skip_validations),
    ]
    
    for name, test_func in tests:
        try:
            await test_func()
        except Exception as e:
            print(f"\n✗ Test '{name}' failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("All tests completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
