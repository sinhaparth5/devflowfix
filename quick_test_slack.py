#!/usr/bin/env python3
# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Quick Slack Integration Test

Run this script for a quick test of the Slack integration.
Tests both low confidence (approval) and high confidence (auto-fix) flows.

Usage:
    python quick_test_slack.py
"""

import asyncio
import sys
from datetime import datetime

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import (
    IncidentSource,
    Severity,
    FailureType,
    Fixability,
    RemediationActionType,
    RiskLevel,
)
from app.core.config import Settings
from app.adapters.external.slack.notifications import SlackNotificationAdapter
from app.adapters.external.slack.approvals import SlackApprovalAdapter


async def quick_test():
    """Run a quick Slack integration test."""
    
    print("\n" + "="*70)
    print("QUICK SLACK INTEGRATION TEST")
    print("="*70)
    
    # Check configuration
    settings = Settings()
    
    if not settings.slack_token:
        print("\n❌ ERROR: SLACK_TOKEN not configured")
        print("   Please add SLACK_TOKEN=xoxb-... to your .env file")
        return False
    
    print(f"\n✅ Configuration OK")
    print(f"   Incidents Channel: {settings.slack_incidents_channel}")
    print(f"   Approvals Channel: {settings.slack_approvals_channel}")
    
    # Initialize adapters
    notifier = SlackNotificationAdapter(settings=settings)
    
    async def mock_remediation(incident_id: str, approver: str):
        """Mock remediation execution."""
        print(f"      🔧 Executing remediation (approved by {approver})...")
        await asyncio.sleep(1)
        return {"success": True, "message": "Remediation completed"}
    
    approval_adapter = SlackApprovalAdapter(
        settings=settings,
        remediation_callback=mock_remediation,
    )
    
    # Test 1: Low Confidence Incident
    print("\n" + "-"*70)
    print("TEST 1: Low Confidence Incident (72%) - Requires Approval")
    print("-"*70)
    
    low_incident = Incident(
        incident_id=f"inc_test_low_{datetime.utcnow().strftime('%H%M%S')}",
        timestamp=datetime.utcnow(),
        source=IncidentSource.GITHUB,
        severity=Severity.MEDIUM,
        failure_type=FailureType.BUILD_FAILURE,
        error_log="npm ERR! ERESOLVE could not resolve",
        error_message="npm peer dependency conflict",
        root_cause="Conflicting webpack peer dependencies",
        fixability=Fixability.AUTO,
        confidence=0.72,
        context={
            "repository": "example/repo",
            "workflow": "CI Build",
            "branch": "main",
        },
    )
    
    print(f"\n   1. Sending notification to {settings.slack_incidents_channel}...")
    try:
        response = await notifier.notify_incident(
            incident=low_incident,
            similar_incidents=[
                {
                    "incident_id": "inc_similar_001",
                    "similarity": 0.89,
                    "outcome": "success",
                    "root_cause": "Similar issue resolved",
                }
            ],
        )
        print(f"      ✅ Notification sent (ts: {response.get('ts')})")
    except Exception as e:
        print(f"      ❌ Failed: {e}")
        return False
    
    print(f"\n   2. Sending approval request to {settings.slack_approvals_channel}...")
    try:
        plan = RemediationPlan(
            action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW,
            reason="Rerun failed workflow",
            risk_level=RiskLevel.LOW,
            requires_approval=True,
            parameters={"owner": "example", "repo": "repo", "run_id": 123},
        )
        
        response = await approval_adapter.request_approval(
            incident=low_incident,
            plan=plan,
            timeout_minutes=30,
        )
        print(f"      ✅ Approval request sent (ts: {response.get('ts')})")
        print(f"\n      👉 Go to {settings.slack_approvals_channel} and click Approve/Reject")
    except Exception as e:
        print(f"      ❌ Failed: {e}")
        return False
    
    # Test 2: High Confidence Incident
    print("\n" + "-"*70)
    print("TEST 2: High Confidence Incident (96%) - Auto-Fix")
    print("-"*70)
    
    await asyncio.sleep(2)  # Small delay
    
    high_incident = Incident(
        incident_id=f"inc_test_high_{datetime.utcnow().strftime('%H%M%S')}",
        timestamp=datetime.utcnow(),
        source=IncidentSource.GITHUB,
        severity=Severity.LOW,
        failure_type=FailureType.TEST_FAILURE,
        error_log="Test timeout",
        error_message="Flaky test failed",
        root_cause="Transient network timeout",
        fixability=Fixability.AUTO,
        confidence=0.96,
        context={
            "repository": "example/repo",
            "workflow": "Tests",
            "branch": "main",
        },
    )
    
    print(f"\n   1. Auto-executing remediation (high confidence)...")
    high_incident.start_remediation()
    await asyncio.sleep(1)
    high_incident.end_remediation(success=True, message="Auto-fixed successfully")
    print(f"      ✅ Remediation completed")
    
    print(f"\n   2. Sending success notification to {settings.slack_incidents_channel}...")
    try:
        response = await notifier.notify_remediation_completed(
            incident=high_incident,
            success=True,
            message="Workflow rerun completed successfully",
        )
        print(f"      ✅ Notification sent (ts: {response.get('ts')})")
    except Exception as e:
        print(f"      ❌ Failed: {e}")
        return False
    
    # Summary
    print("\n" + "="*70)
    print("TEST COMPLETE!")
    print("="*70)
    print(f"\n✅ Check your Slack channels:")
    print(f"   • {settings.slack_incidents_channel} - for notifications")
    print(f"   • {settings.slack_approvals_channel} - for approval request")
    print(f"\n💡 Click the Approve/Reject button to test the callback flow")
    print(f"   (Note: Webhook must be configured for callbacks to work)")
    print()
    
    # Cleanup
    await notifier.close()
    await approval_adapter.close()
    
    return True


def main():
    """Main entry point."""
    try:
        success = asyncio.run(quick_test())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
