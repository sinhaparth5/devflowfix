# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Integration Tests for Slack Integration

Tests the complete Slack workflow:
1. Low confidence incident → Slack notification + approval request
2. Click approve → Execute remediation
3. High confidence incident → Auto-fix + notification
"""

import asyncio
import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan, RemediationResult
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    Fixability,
    RemediationActionType,
    RiskLevel,
    Outcome,
    ApprovalStatus,
)
from app.core.config import Settings
from app.adapters.external.slack.client import SlackClient
from app.adapters.external.slack.notifications import SlackNotificationAdapter
from app.adapters.external.slack.approvals import SlackApprovalAdapter



@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        slack_token="xoxb-test-token",
        slack_signing_secret="test-signing-secret",
        slack_incidents_channel="#test-incidents",
        slack_approvals_channel="#test-approvals",
    )


@pytest.fixture
def mock_slack_client():
    """Create mock Slack client."""
    client = AsyncMock(spec=SlackClient)
    client.post_message = AsyncMock(return_value={
        "ok": True,
        "ts": "1234567890.123456",
        "channel": "C1234567890",
    })
    client.update_message = AsyncMock(return_value={
        "ok": True,
        "ts": "1234567890.123456",
    })
    return client


@pytest.fixture
def low_confidence_incident():
    """Create low confidence incident for testing."""
    return Incident(
        incident_id="inc_low_conf_001",
        timestamp=datetime.utcnow(),
        source=IncidentSource.GITHUB,
        severity=Severity.MEDIUM,
        failure_type=FailureType.BUILD_FAILURE,
        error_log="Build failed due to dependency conflict",
        error_message="npm ERR! peer dependency conflict",
        root_cause="Conflicting peer dependencies in package.json",
        fixability=Fixability.AUTO,
        confidence=0.72, 
        context={
            "repository": "myorg/myrepo",
            "workflow": "CI Build",
            "job": "build",
            "branch": "main",
        },
    )


@pytest.fixture
def high_confidence_incident():
    """Create high confidence incident for testing."""
    return Incident(
        incident_id="inc_high_conf_001",
        timestamp=datetime.utcnow(),
        source=IncidentSource.GITHUB,
        severity=Severity.LOW,
        failure_type=FailureType.TEST_FAILURE,
        error_log="Flaky test failed on retry",
        error_message="Test 'should handle async operation' failed",
        root_cause="Transient network timeout in integration test",
        fixability=Fixability.AUTO,
        confidence=0.96, 
        context={
            "repository": "myorg/myrepo",
            "workflow": "CI Test",
            "job": "integration-tests",
            "branch": "feature/new-feature",
        },
    )


@pytest.fixture
def remediation_plan():
    """Create remediation plan for testing."""
    return RemediationPlan(
        action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
        reason="Rerun failed GitHub Actions workflow",
        risk_level=RiskLevel.LOW,
        estimated_duration_seconds=300,
        requires_approval=False,
        parameters={
            "owner": "myorg",
            "repo": "myrepo",
            "run_id": 123456,
        },
    )


@pytest.fixture
def similar_incidents():
    """Create similar incidents data for testing."""
    return [
        {
            "incident_id": "inc_similar_001",
            "similarity": 0.89,
            "outcome": "success",
            "root_cause": "npm dependency conflict resolved by updating package-lock.json",
            "resolution_time_seconds": 180,
        },
        {
            "incident_id": "inc_similar_002",
            "similarity": 0.85,
            "outcome": "success",
            "root_cause": "Peer dependency mismatch fixed by version constraint update",
            "resolution_time_seconds": 240,
        },
        {
            "incident_id": "inc_similar_003",
            "similarity": 0.78,
            "outcome": "failed",
            "root_cause": "Dependency conflict required manual intervention",
            "resolution_time_seconds": None,
        },
    ]



@pytest.mark.asyncio
async def test_low_confidence_approval_workflow(
    settings,
    mock_slack_client,
    low_confidence_incident,
    remediation_plan,
    similar_incidents,
):
    """
    Test low confidence incident workflow:
    1. Send notification to #incidents
    2. Send approval request to #approvals
    3. Simulate button click (approve)
    4. Execute remediation
    """
    print("\n=== Test 1: Low Confidence Incident → Approval Workflow ===")
    
    remediation_executed = False
    execution_result = None
    
    async def mock_remediation_callback(incident_id: str, approver: str) -> Dict[str, Any]:
        """Mock remediation execution."""
        nonlocal remediation_executed, execution_result
        print(f"   ✓ Remediation callback triggered for {incident_id} by {approver}")
        remediation_executed = True
        execution_result = {
            "success": True,
            "message": "Workflow rerun initiated successfully",
            "run_id": 123457,
        }
        return execution_result
    
    print("\n1. Sending incident notification to #incidents...")
    notifier = SlackNotificationAdapter(client=mock_slack_client, settings=settings)
    
    notification_response = await notifier.notify_incident(
        incident=low_confidence_incident,
        similar_incidents=similar_incidents,
    )
    
    assert notification_response["ok"] is True
    assert "ts" in notification_response
    print(f"   ✓ Notification sent successfully (ts: {notification_response['ts']})")
    
    mock_slack_client.post_message.assert_called()
    call_args = mock_slack_client.post_message.call_args
    assert call_args.kwargs["channel"] == "#test-incidents"
    assert "blocks" in call_args.kwargs
    print(f"   ✓ Sent to channel: {call_args.kwargs['channel']}")
    
    print("\n2. Sending approval request to #approvals...")
    approval_adapter = SlackApprovalAdapter(
        client=mock_slack_client,
        settings=settings,
        remediation_callback=mock_remediation_callback,
    )
    
    remediation_plan.requires_approval = True
    
    approval_response = await approval_adapter.request_approval(
        incident=low_confidence_incident,
        plan=remediation_plan,
        timeout_minutes=30,
        requestor="DevFlowFix AI",
    )
    
    assert approval_response["ok"] is True
    print(f"   ✓ Approval request sent (ts: {approval_response['ts']})")
    
    call_args = mock_slack_client.post_message.call_args
    blocks = call_args.kwargs["blocks"]
    action_blocks = [b for b in blocks if b.get("type") == "actions"]
    assert len(action_blocks) > 0
    print(f"   ✓ Interactive buttons added to message")
    
    print("\n3. Simulating 'Approve' button click...")
    
    callback_payload = {
        "type": "block_actions",
        "user": {
            "id": "U123456",
            "username": "john.doe",
            "name": "John Doe",
        },
        "actions": [
            {
                "action_id": f"approve_{low_confidence_incident.incident_id}",
                "value": f"approve_{low_confidence_incident.incident_id}",
                "type": "button",
            }
        ],
        "response_url": "https://hooks.slack.com/actions/...",
        "trigger_id": "123456.789012.abcdef",
    }
    
    approval_result = await approval_adapter.handle_callback(callback_payload)
    
    assert approval_result.approval_status == ApprovalStatus.APPROVED
    assert approval_result.approver == "john.doe"
    assert approval_result.executed is True
    assert remediation_executed is True
    print(f"   ✓ Approval processed by: {approval_result.approver}")
    print(f"   ✓ Remediation executed: {approval_result.executed}")
    
    mock_slack_client.update_message.assert_called()
    print(f"   ✓ Approval message updated with decision")
    
    print("\n4. Verifying remediation execution...")
    assert approval_result.execution_result is not None
    assert approval_result.execution_result["success"] is True
    print(f"   ✓ Remediation successful: {approval_result.execution_result['message']}")
    
    print("\n✅ Test 1 PASSED: Low confidence approval workflow complete\n")



@pytest.mark.asyncio
async def test_high_confidence_auto_fix_workflow(
    settings,
    mock_slack_client,
    high_confidence_incident,
    remediation_plan,
):
    """
    Test high confidence incident workflow:
    1. Auto-execute remediation (no approval needed)
    2. Send success notification to #incidents
    """
    print("\n=== Test 2: High Confidence Incident → Auto-fix Workflow ===")
    
    print("\n1. Executing remediation automatically (high confidence)...")
    
    high_confidence_incident.start_remediation()
    
    await asyncio.sleep(0.1) 
    
    high_confidence_incident.end_remediation(
        success=True,
        message="Workflow rerun completed successfully"
    )
    
    assert high_confidence_incident.outcome == Outcome.SUCCESS
    assert high_confidence_incident.remediation_executed is True
    assert high_confidence_incident.resolution_time_seconds is not None
    print(f"   ✓ Remediation executed successfully")
    print(f"   ✓ Resolution time: {high_confidence_incident.resolution_time_seconds}s")
    
    print("\n2. Sending success notification to #incidents...")
    
    notifier = SlackNotificationAdapter(client=mock_slack_client, settings=settings)
    
    notification_response = await notifier.notify_incident(
        incident=high_confidence_incident,
        similar_incidents=[],
    )
    
    assert notification_response["ok"] is True
    print(f"   ✓ Success notification sent (ts: {notification_response['ts']})")
    
    call_args = mock_slack_client.post_message.call_args
    blocks = call_args.kwargs["blocks"]
    
    block_text = str(blocks)
    assert "SUCCESS" in block_text or "✅" in block_text or high_confidence_incident.outcome.value in block_text
    print(f"   ✓ Notification includes success status")
    
    print("\n✅ Test 2 PASSED: High confidence auto-fix workflow complete\n")


@pytest.mark.asyncio
async def test_approval_rejection(
    settings,
    mock_slack_client,
    low_confidence_incident,
    remediation_plan,
):
    """
    Test approval rejection workflow:
    1. Send approval request
    2. Simulate reject button click
    3. Verify remediation is NOT executed
    """
    print("\n=== Test 3: Approval Rejection Workflow ===")
    
    remediation_executed = False
    
    async def mock_remediation_callback(incident_id: str, approver: str) -> Dict[str, Any]:
        """This should NOT be called on rejection."""
        nonlocal remediation_executed
        remediation_executed = True
        return {"success": True}
    
    print("\n1. Sending approval request...")
    
    approval_adapter = SlackApprovalAdapter(
        client=mock_slack_client,
        settings=settings,
        remediation_callback=mock_remediation_callback,
    )
    
    await approval_adapter.request_approval(
        incident=low_confidence_incident,
        plan=remediation_plan,
        timeout_minutes=30,
    )
    
    print(f"   ✓ Approval request sent")
    
    print("\n2. Simulating 'Reject' button click...")
    
    callback_payload = {
        "type": "block_actions",
        "user": {
            "id": "U789012",
            "username": "jane.smith",
            "name": "Jane Smith",
        },
        "actions": [
            {
                "action_id": f"reject_{low_confidence_incident.incident_id}",
                "value": f"reject_{low_confidence_incident.incident_id}",
                "type": "button",
            }
        ],
    }
    
    approval_result = await approval_adapter.handle_callback(callback_payload)
    
    assert approval_result.approval_status == ApprovalStatus.REJECTED
    assert approval_result.approver == "jane.smith"
    assert approval_result.executed is False
    assert remediation_executed is False
    print(f"   ✓ Rejection processed by: {approval_result.approver}")
    print(f"   ✓ Remediation NOT executed (as expected)")
    
    mock_slack_client.update_message.assert_called()
    print(f"   ✓ Approval message updated to show rejection")
    
    print("\n✅ Test 3 PASSED: Approval rejection workflow complete\n")



@pytest.mark.asyncio
async def test_complete_slack_integration_flow(
    settings,
    mock_slack_client,
    low_confidence_incident,
    high_confidence_incident,
    remediation_plan,
    similar_incidents,
):
    """
    Test complete end-to-end Slack integration:
    1. Process low confidence incident → approval → execute
    2. Process high confidence incident → auto-execute → notify
    """
    print("\n=== Test 4: Complete End-to-End Integration ===")
    
    execution_log = []
    
    async def remediation_callback(incident_id: str, approver: str) -> Dict[str, Any]:
        """Track all remediations."""
        execution_log.append({
            "incident_id": incident_id,
            "approver": approver,
            "timestamp": datetime.utcnow(),
        })
        return {"success": True, "message": "Remediation completed"}
    
    notifier = SlackNotificationAdapter(client=mock_slack_client, settings=settings)
    approval_adapter = SlackApprovalAdapter(
        client=mock_slack_client,
        settings=settings,
        remediation_callback=remediation_callback,
    )
    
    print("\n--- Scenario 1: Low Confidence (0.72) ---")
    print("1. Detecting incident...")
    print(f"   Confidence: {low_confidence_incident.confidence:.1%}")
    print(f"   Requires approval: YES")
    
    await notifier.notify_incident(
        incident=low_confidence_incident,
        similar_incidents=similar_incidents,
    )
    print("   ✓ Incident notification sent")
    
    await approval_adapter.request_approval(
        incident=low_confidence_incident,
        plan=remediation_plan,
        timeout_minutes=30,
    )
    print("   ✓ Approval request sent")
    
    callback = {
        "user": {"username": "sre.oncall"},
        "actions": [{
            "action_id": f"approve_{low_confidence_incident.incident_id}",
            "value": f"approve_{low_confidence_incident.incident_id}",
        }],
    }
    result = await approval_adapter.handle_callback(callback)
    print(f"   ✓ Approved by: {result.approver}")
    print(f"   ✓ Remediation executed: {result.executed}")
    
    print("\n--- Scenario 2: High Confidence (0.96) ---")
    print("1. Detecting incident...")
    print(f"   Confidence: {high_confidence_incident.confidence:.1%}")
    print(f"   Requires approval: NO")
    
    print("   ✓ Auto-executing remediation...")
    high_confidence_incident.start_remediation()
    high_confidence_incident.end_remediation(success=True, message="Auto-fixed")
    
    await notifier.notify_incident(
        incident=high_confidence_incident,
        similar_incidents=[],
    )
    print("   ✓ Success notification sent")
    
    print("\n--- Execution Summary ---")
    print(f"Total remediations executed: {len(execution_log)}")
    print(f"With approval: {len([e for e in execution_log if e['approver']])}")
    print(f"Auto-executed: 1 (high confidence)")
    
    assert len(execution_log) == 1  
    assert high_confidence_incident.outcome == Outcome.SUCCESS
    
    print("\n✅ Test 4 PASSED: Complete end-to-end integration successful\n")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SLACK INTEGRATION TEST SUITE")
    print("="*70)
    
    asyncio.run(test_low_confidence_approval_workflow(
        Settings(slack_token="test", slack_incidents_channel="#test", slack_approvals_channel="#test"),
        AsyncMock(spec=SlackClient),
        Incident(
            incident_id="inc_test_001",
            source=IncidentSource.GITHUB,
            severity=Severity.MEDIUM,
            failure_type=FailureType.BUILD_FAILURE,
            error_log="Test error",
            confidence=0.72,
            fixability=Fixability.AUTO,
            root_cause="Test cause",
            context={"repository": "test/repo"},
        ),
        RemediationPlan(
            incident_id="inc_test_001",
            action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
            description="Test",
            risk_level=RiskLevel.LOW,
        ),
        [],
    ))
    
    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70 + "\n")
