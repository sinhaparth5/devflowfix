# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Manual Slack Integration Test Script

Run this script to test the complete Slack workflow:
1. Low confidence incident → Slack notification + approval request
2. Click approve button in Slack → Execute remediation
3. High confidence incident → Auto-fix + notification

Prerequisites:
- Set SLACK_TOKEN in .env
- Set SLACK_SIGNING_SECRET in .env
- Set SLACK_INCIDENTS_CHANNEL (default: #incidents)
- Set SLACK_APPROVALS_CHANNEL (default: #devflowfix-approvals)
"""

import asyncio
from datetime import datetime
from typing import Dict, Any

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    Fixability,
    RemediationActionType,
    RiskLevel,
    Outcome,
)
from app.core.config import Settings
from app.adapters.external.slack.client import SlackClient
from app.adapters.external.slack.notifications import SlackNotificationAdapter
from app.adapters.external.slack.approvals import SlackApprovalAdapter
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SlackIntegrationTester:
    """Test harness for Slack integration."""
    
    def __init__(self):
        self.settings = Settings()
        self.client = SlackClient(settings=self.settings)
        self.notifier = SlackNotificationAdapter(client=self.client, settings=self.settings)
        self.approval_adapter = SlackApprovalAdapter(
            client=self.client,
            settings=self.settings,
            remediation_callback=self.execute_remediation,
        )
        self.execution_log = []
    
    async def execute_remediation(self, incident_id: str, approver: str) -> Dict[str, Any]:
        """
        Mock remediation execution callback.
        
        In production, this would call the actual RemediatorService.
        """
        print(f"\n🔧 EXECUTING REMEDIATION")
        print(f"   Incident: {incident_id}")
        print(f"   Approved by: {approver}")
        
        # Simulate work
        await asyncio.sleep(2)
        
        result = {
            "success": True,
            "message": "Workflow rerun initiated successfully",
            "run_id": 123457,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        self.execution_log.append({
            "incident_id": incident_id,
            "approver": approver,
            "result": result,
        })
        
        print(f"   ✅ Remediation completed successfully")
        return result
    
    def create_low_confidence_incident(self) -> Incident:
        """Create a low confidence test incident."""
        return Incident(
            incident_id=f"inc_low_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.utcnow(),
            source=IncidentSource.GITHUB,
            severity=Severity.MEDIUM,
            failure_type=FailureType.BUILD_FAILURE,
            error_log="""
npm ERR! code ERESOLVE
npm ERR! ERESOLVE could not resolve
npm ERR! 
npm ERR! While resolving: react-scripts@5.0.1
npm ERR! Found: webpack@5.88.0
npm ERR! node_modules/webpack
npm ERR!   webpack@"^5.88.0" from the root project
npm ERR! 
npm ERR! Could not resolve dependency:
npm ERR! peer webpack@"^4.44.2" from webpack-dev-server@3.11.3
            """.strip(),
            error_message="npm ERR! ERESOLVE could not resolve peer dependency conflict",
            stack_trace="Error at build step in GitHub Actions workflow",
            root_cause="Conflicting webpack peer dependencies between react-scripts and webpack-dev-server. Needs package.json update to resolve version constraints.",
            fixability=Fixability.AUTO,
            confidence=0.72,  # Low confidence - requires approval
            context={
                "repository": "devflowfix-new/example-app",
                "workflow": "CI Build and Test",
                "job": "build",
                "branch": "feature/upgrade-dependencies",
                "run_id": "123456789",
                "environment": "staging",
            },
            tags=["build", "dependencies", "npm"],
        )
    
    def create_high_confidence_incident(self) -> Incident:
        """Create a high confidence test incident."""
        return Incident(
            incident_id=f"inc_high_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.utcnow(),
            source=IncidentSource.GITHUB,
            severity=Severity.LOW,
            failure_type=FailureType.TEST_FAILURE,
            error_log="""
FAIL src/components/Dashboard.test.tsx
  ● Dashboard › should handle async data loading

    expect(received).toHaveBeenCalledWith(...)

    Expected: {"status": "success", "data": [...]}
    Received: timeout

      47 |     await waitFor(() => {
      48 |       expect(mockFetch).toHaveBeenCalledWith(expectedPayload);
    > 49 |     }, {timeout: 5000});
         |        ^
      50 |   });
            """.strip(),
            error_message="Test 'Dashboard › should handle async data loading' failed due to timeout",
            stack_trace="at waitFor (src/components/Dashboard.test.tsx:49:8)",
            root_cause="Transient network timeout in integration test. This is a known flaky test that passes on retry. The test expects a response within 5 seconds but occasionally the mock API response is delayed.",
            fixability=Fixability.AUTO,
            confidence=0.96,  # High confidence - auto-fix
            context={
                "repository": "devflowfix-new/frontend-app",
                "workflow": "Integration Tests",
                "job": "test-suite",
                "branch": "main",
                "run_id": "987654321",
                "environment": "development",
            },
            tags=["test", "flaky", "timeout"],
        )
    
    def create_remediation_plan(self, incident: Incident) -> RemediationPlan:
        """Create remediation plan for incident."""
        return RemediationPlan(
            action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
            reason=f"Rerun failed GitHub Actions workflow for {incident.context.get('workflow', 'unknown workflow')}",
            risk_level=RiskLevel.LOW,
            estimated_duration_seconds=180,
            requires_approval=(incident.confidence < 0.85),
            parameters={
                "owner": incident.context.get("repository", "").split("/")[0] if "/" in incident.context.get("repository", "") else "unknown",
                "repo": incident.context.get("repository", "").split("/")[1] if "/" in incident.context.get("repository", "") else "unknown",
                "run_id": incident.context.get("run_id", "unknown"),
            },
            pre_validation_checks=[
                "Verify workflow exists and is accessible",
                "Check user has permission to rerun workflows",
                "Confirm workflow is in a rerunnable state",
            ],
        )
    
    def create_similar_incidents(self) -> list[Dict[str, Any]]:
        """Create mock similar incidents data."""
        return [
            {
                "incident_id": "inc_20241120_143022",
                "similarity": 0.89,
                "outcome": "success",
                "root_cause": "npm dependency conflict resolved by updating package-lock.json",
                "resolution_time_seconds": 180,
            },
            {
                "incident_id": "inc_20241119_091533",
                "similarity": 0.85,
                "outcome": "success",
                "root_cause": "Peer dependency mismatch fixed by adjusting version constraints in package.json",
                "resolution_time_seconds": 240,
            },
            {
                "incident_id": "inc_20241118_164408",
                "similarity": 0.78,
                "outcome": "success",
                "root_cause": "Webpack version conflict - updated to compatible versions",
                "resolution_time_seconds": 300,
            },
        ]
    
    async def test_low_confidence_workflow(self):
        """
        Test Scenario 1: Low Confidence Incident
        
        Flow:
        1. Create low confidence incident (0.72)
        2. Send notification to #incidents
        3. Send approval request to #approvals
        4. Wait for manual approval in Slack
        5. (Approval handler will execute remediation via callback)
        """
        print("\n" + "="*80)
        print("TEST 1: LOW CONFIDENCE INCIDENT → APPROVAL REQUIRED")
        print("="*80)
        
        # Create incident
        incident = self.create_low_confidence_incident()
        plan = self.create_remediation_plan(incident)
        similar = self.create_similar_incidents()
        
        print(f"\n📋 INCIDENT DETAILS:")
        print(f"   ID: {incident.incident_id}")
        print(f"   Source: {incident.source.value}")
        print(f"   Severity: {incident.severity.value}")
        print(f"   Confidence: {incident.confidence:.1%} (LOW - approval required)")
        print(f"   Repository: {incident.context.get('repository')}")
        print(f"   Workflow: {incident.context.get('workflow')}")
        
        # Step 1: Send notification
        print(f"\n📢 STEP 1: Sending incident notification to {self.settings.slack_incidents_channel}")
        try:
            notification_response = await self.notifier.notify_incident(
                incident=incident,
                similar_incidents=similar,
            )
            print(f"   ✅ Notification sent successfully")
            print(f"   Message timestamp: {notification_response.get('ts')}")
            print(f"   Channel: {notification_response.get('channel')}")
        except Exception as e:
            print(f"   ❌ Failed to send notification: {e}")
            return
        
        # Step 2: Send approval request
        print(f"\n🔐 STEP 2: Sending approval request to {self.settings.slack_approvals_channel}")
        try:
            approval_response = await self.approval_adapter.request_approval(
                incident=incident,
                plan=plan,
                timeout_minutes=30,
                requestor="DevFlowFix AI (Test)",
            )
            print(f"   ✅ Approval request sent successfully")
            print(f"   Message timestamp: {approval_response.get('ts')}")
            print(f"   Channel: {approval_response.get('channel')}")
        except Exception as e:
            print(f"   ❌ Failed to send approval request: {e}")
            return
        
        # Step 3: Wait for manual approval
        print(f"\n⏳ STEP 3: Waiting for approval in Slack...")
        print(f"\n   👉 Please go to {self.settings.slack_approvals_channel} and click:")
        print(f"      • '✅ Approve' button to execute remediation")
        print(f"      • '❌ Reject' button to cancel")
        print(f"\n   The approval request will timeout in 30 minutes.")
        print(f"\n   Note: Approval callback will execute remediation automatically")
        print(f"   (You can check this test's execution log after approving)")
        
        print("\n" + "="*80)
        print("Test 1 setup complete. Approval request is live in Slack.")
        print("="*80 + "\n")
    
    async def test_high_confidence_workflow(self):
        """
        Test Scenario 2: High Confidence Incident
        
        Flow:
        1. Create high confidence incident (0.96)
        2. Auto-execute remediation (no approval needed)
        3. Send success notification to #incidents
        """
        print("\n" + "="*80)
        print("TEST 2: HIGH CONFIDENCE INCIDENT → AUTO-FIX")
        print("="*80)
        
        # Create incident
        incident = self.create_high_confidence_incident()
        plan = self.create_remediation_plan(incident)
        
        print(f"\n📋 INCIDENT DETAILS:")
        print(f"   ID: {incident.incident_id}")
        print(f"   Source: {incident.source.value}")
        print(f"   Severity: {incident.severity.value}")
        print(f"   Confidence: {incident.confidence:.1%} (HIGH - auto-fix enabled)")
        print(f"   Repository: {incident.context.get('repository')}")
        print(f"   Workflow: {incident.context.get('workflow')}")
        
        # Step 1: Auto-execute remediation
        print(f"\n🤖 STEP 1: Auto-executing remediation (no approval needed)")
        incident.start_remediation()
        
        try:
            # In production, this would call RemediatorService
            result = await self.execute_remediation(incident.incident_id, "DevFlowFix AI (Auto)")
            
            incident.end_remediation(
                success=result["success"],
                message=result["message"]
            )
            
            print(f"   ✅ Remediation completed successfully")
            print(f"   Resolution time: {incident.resolution_time_seconds}s")
        except Exception as e:
            print(f"   ❌ Remediation failed: {e}")
            incident.end_remediation(success=False, message=str(e))
        
        # Step 2: Send success notification
        print(f"\n📢 STEP 2: Sending success notification to {self.settings.slack_incidents_channel}")
        try:
            notification_response = await self.notifier.notify_remediation_completed(
                incident=incident,
                success=(incident.outcome == Outcome.SUCCESS),
                message=incident.outcome_message,
            )
            print(f"   ✅ Notification sent successfully")
            print(f"   Message timestamp: {notification_response.get('ts')}")
            print(f"   Channel: {notification_response.get('channel')}")
        except Exception as e:
            print(f"   ❌ Failed to send notification: {e}")
        
        print("\n" + "="*80)
        print("Test 2 complete. Check Slack for success notification.")
        print("="*80 + "\n")
    
    async def run_all_tests(self):
        """Run all test scenarios."""
        print("\n" + "="*80)
        print("SLACK INTEGRATION TEST SUITE")
        print("="*80)
        print(f"\nConfiguration:")
        print(f"   Slack Token: {'✓ Configured' if self.settings.slack_token else '✗ Missing'}")
        print(f"   Incidents Channel: {self.settings.slack_incidents_channel}")
        print(f"   Approvals Channel: {self.settings.slack_approvals_channel}")
        
        if not self.settings.slack_token:
            print(f"\n❌ ERROR: SLACK_TOKEN not configured in .env")
            print(f"   Please set your Slack bot token and try again.")
            return
        
        # Test Slack connection
        print(f"\n🔌 Testing Slack connection...")
        try:
            auth_info = await self.client.auth_test()
            print(f"   ✅ Connected as: {auth_info.get('user', 'Unknown')}")
            print(f"   Team: {auth_info.get('team', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ Connection failed: {e}")
            return
        
        # Run tests
        await self.test_low_confidence_workflow()
        
        print(f"\n⏸️  Waiting 5 seconds before next test...")
        await asyncio.sleep(5)
        
        await self.test_high_confidence_workflow()
        
        # Show execution log
        if self.execution_log:
            print("\n" + "="*80)
            print("REMEDIATION EXECUTION LOG")
            print("="*80)
            for i, entry in enumerate(self.execution_log, 1):
                print(f"\n{i}. Incident: {entry['incident_id']}")
                print(f"   Approved by: {entry['approver']}")
                print(f"   Success: {entry['result']['success']}")
                print(f"   Message: {entry['result']['message']}")
        
        print("\n" + "="*80)
        print("ALL TESTS COMPLETED")
        print("="*80)
        print(f"\nNext steps:")
        print(f"   1. Check {self.settings.slack_incidents_channel} for notifications")
        print(f"   2. Check {self.settings.slack_approvals_channel} for approval requests")
        print(f"   3. Click approve/reject buttons to test callback handling")
        print("\n")


async def main():
    """Main entry point."""
    tester = SlackIntegrationTester()
    
    try:
        await tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tester.client.close()


if __name__ == "__main__":
    asyncio.run(main())
