# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub Rerun Remediator Usage Examples

Demonstrates how to use GitHubRerunRemediator for workflow remediation.
"""

import asyncio
from datetime import datetime

from app.domain.remediators.github_rerun import GitHubRerunRemediator
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    RemediationActionType,
    RiskLevel,
)


async def example_basic_rerun():
    """Example: Basic workflow rerun with incident context."""
    print("\n" + "=" * 70)
    print("Example 1: Basic Workflow Rerun")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_001",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Workflow run failed",
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 123456789,
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        
        print(f"Success: {result.success}")
        print(f"Outcome: {result.outcome}")
        print(f"Message: {result.message}")
        print(f"Duration: {result.duration_seconds}s")
        print(f"\nActions performed:")
        for action in result.actions_performed:
            print(f"  - {action}")
        
        if result.metadata:
            print(f"\nMetadata:")
            print(f"  Workflow URL: {result.metadata.get('workflow_url')}")
            print(f"  Workflow Name: {result.metadata.get('workflow_name')}")
    
    finally:
        await remediator.close()


async def example_with_plan_parameters():
    """Example: Override parameters in plan."""
    print("\n" + "=" * 70)
    print("Example 2: Plan Parameters Override")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_002",
        source=IncidentSource.GITHUB,
        severity=Severity.MEDIUM,
        failure_type=FailureType.TEST_FAILURE,
        error_message="Tests failed",
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    plan.add_parameter("owner", "myorg")
    plan.add_parameter("repo", "myrepo")
    plan.add_parameter("run_id", 987654321)
    plan.add_parameter("wait_for_completion", True)
    plan.add_parameter("timeout", 300.0) 
    plan.add_parameter("rerun_failed_only", True)
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        print(f"Result: {result.success}")
        print(f"Message: {result.message}")
    
    finally:
        await remediator.close()


async def example_trigger_without_waiting():
    """Example: Trigger rerun without waiting for completion."""
    print("\n" + "=" * 70)
    print("Example 3: Trigger Without Waiting")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_003",
        source=IncidentSource.GITHUB,
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 111222333,
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.LOW,
    )
    plan.add_parameter("wait_for_completion", False) 
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        
        print(f"Triggered: {result.success}")
        print(f"Message: {result.message}")
        print("Not waiting for completion - remediation continues async")
    
    finally:
        await remediator.close()


async def example_from_webhook_payload():
    """Example: Extract from GitHub webhook payload."""
    print("\n" + "=" * 70)
    print("Example 4: Extract from Webhook Payload")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_004",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed",
        raw_payload={
            "repository": {
                "name": "myrepo",
                "owner": {
                    "login": "myorg"
                }
            },
            "workflow_run": {
                "id": 444555666,
                "name": "CI Pipeline",
                "conclusion": "failure",
            }
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        
        print(f"Success: {result.success}")
        print(f"Extracted from webhook payload:")
        print(f"  Owner: {result.metadata.get('owner')}")
        print(f"  Repo: {result.metadata.get('repo')}")
        print(f"  Run ID: {result.metadata.get('run_id')}")
    
    finally:
        await remediator.close()


async def example_missing_parameters():
    """Example: Handle missing parameters."""
    print("\n" + "=" * 70)
    print("Example 5: Missing Parameters Error")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_005",
        source=IncidentSource.GITHUB,
        context={
            "owner": "myorg",
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        
        print(f"Success: {result.success}")
        print(f"Error: {result.error_message}")
        print(f"Message: {result.message}")
    
    finally:
        await remediator.close()


async def example_rerun_entire_workflow():
    """Example: Rerun entire workflow instead of just failed jobs."""
    print("\n" + "=" * 70)
    print("Example 6: Rerun Entire Workflow")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_006",
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
    )
    plan.add_parameter("rerun_failed_only", False)
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        
        print(f"Success: {result.success}")
        print(f"Reran entire workflow: {not result.metadata.get('rerun_failed_only')}")
    
    finally:
        await remediator.close()


async def example_with_custom_timeout():
    """Example: Custom timeout and poll interval."""
    print("\n" + "=" * 70)
    print("Example 7: Custom Timeout Configuration")
    print("=" * 70)
    
    incident = Incident(
        incident_id="inc_github_007",
        source=IncidentSource.GITHUB,
        context={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 123123123,
        },
    )
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    plan.add_parameter("wait_for_completion", True)
    plan.add_parameter("timeout", 1800.0)  
    plan.add_parameter("poll_interval", 30.0) 
    
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        print(f"Result: {result.success}")
        print(f"Configured with 30min timeout, 30s poll interval")
    
    finally:
        await remediator.close()


async def example_multiple_incidents():
    """Example: Remediate multiple incidents in parallel."""
    print("\n" + "=" * 70)
    print("Example 8: Parallel Remediations")
    print("=" * 70)
    
    incidents = [
        Incident(
            incident_id=f"inc_github_{i:03d}",
            source=IncidentSource.GITHUB,
            severity=Severity.MEDIUM,
            context={
                "owner": "myorg",
                "repo": f"repo{i}",
                "run_id": 100000 + i,
            },
        )
        for i in range(1, 4)
    ]
    
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
    )
    plan.add_parameter("wait_for_completion", True)
    plan.add_parameter("timeout", 300.0)
    
    remediator = GitHubRerunRemediator()
    
    try:
        tasks = [
            remediator.execute(incident, plan)
            for incident in incidents
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        print(f"Remediated {len(incidents)} incidents:")
        for incident, result in zip(incidents, results):
            if isinstance(result, Exception):
                print(f"  ✗ {incident.incident_id}: {result}")
            elif result.success:
                print(f"  ✓ {incident.incident_id}: Success")
            else:
                print(f"  ✗ {incident.incident_id}: {result.error_message}")
    
    finally:
        await remediator.close()


async def example_complete_workflow():
    """Example: Complete remediation workflow with logging."""
    print("\n" + "=" * 70)
    print("Example 9: Complete Remediation Workflow")
    print("=" * 70)
    
    print("1. Incident detected from GitHub webhook")
    incident = Incident(
        incident_id="inc_github_complete",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        failure_type=FailureType.BUILD_FAILURE,
        error_message="Build failed: npm test exited with code 1",
        context={
            "owner": "myorg",
            "repo": "my-app",
            "run_id": 987654321,
            "workflow_name": "CI/CD Pipeline",
            "branch": "main",
            "commit_sha": "abc123",
        },
        confidence=0.92, 
    )
    
    print(f"   Incident: {incident.incident_id}")
    print(f"   Confidence: {incident.confidence:.0%}")
    
    print("\n2. Creating remediation plan")
    plan = RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        risk_level=RiskLevel.MEDIUM,
        reason="Transient test failure detected, rerunning failed jobs",
    )
    plan.add_parameter("wait_for_completion", True)
    plan.add_parameter("timeout", 600.0)
    plan.add_parameter("rerun_failed_only", True)
    
    print(f"   Action: {plan.action_type.value}")
    print(f"   Risk: {plan.risk_level.value}")
    
    print("\n3. Executing remediation")
    remediator = GitHubRerunRemediator()
    
    try:
        result = await remediator.execute(incident, plan)
        
        print("\n4. Remediation Results")
        print(f"   Success: {result.success}")
        print(f"   Outcome: {result.outcome.value}")
        print(f"   Duration: {result.duration_seconds}s")
        print(f"   Message: {result.message}")
        
        if result.success:
            print(f"\n   ✓ Incident resolved automatically")
            print(f"   Workflow: {result.metadata.get('workflow_url')}")
        else:
            print(f"\n   ✗ Remediation failed")
            print(f"   Reason: {result.error_message}")
            print(f"   Next: Escalate to human")
    
    finally:
        await remediator.close()


async def main():
    """Run all examples."""
    examples = [
        example_basic_rerun,
        example_with_plan_parameters,
        example_trigger_without_waiting,
        example_from_webhook_payload,
        example_missing_parameters,
        example_rerun_entire_workflow,
        example_with_custom_timeout,
        example_multiple_incidents,
        example_complete_workflow,
    ]
    
    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"Example failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
