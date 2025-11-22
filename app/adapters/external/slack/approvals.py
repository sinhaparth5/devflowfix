# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Slack Approval Workflow Adapter

Sends interactive approval requests to Slack with:
- Approve/Reject buttons
- Incident and remediation details
- Callback handling for button clicks
- Automatic remediation execution on approval
"""

from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timedelta
import hashlib
import hmac

from app.core.config import Settings
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.core.enums import (
    Severity,
    ApprovalStatus,
    RiskLevel,
    ConfidenceLevel,
)
from app.core.schemas.approval import ApprovalResponse, ApprovalDecision
from app.adapters.external.slack.client import SlackClient
from app.exceptions import ApprovalTimeoutError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SlackApprovalAdapter:
    """
    Adapter for managing approval workflows in Slack.
    
    Provides interactive approval requests with:
    - Rich message formatting with incident details
    - Approve/Reject action buttons
    - Callback handling for button interactions
    - Integration with remediation execution
    - Timeout management
    
    Example:
        ```python
        adapter = SlackApprovalAdapter(
            remediation_callback=execute_remediation_func
        )
        
        # Send approval request
        response = await adapter.request_approval(
            incident=incident,
            plan=plan,
            timeout_minutes=30
        )
        
        # Handle button click callback
        result = await adapter.handle_callback(payload)
        ```
    """
    
    # Severity to emoji mapping
    SEVERITY_EMOJI = {
        Severity.LOW: "ℹ️",
        Severity.MEDIUM: "⚠️",
        Severity.HIGH: "🔥",
        Severity.CRITICAL: "🚨",
    }
    
    # Risk level to color mapping (for message attachments)
    RISK_COLORS = {
        RiskLevel.LOW: "#36a64f",      # Green
        RiskLevel.MEDIUM: "#FFD700",   # Gold
        RiskLevel.HIGH: "#FF8C00",     # Dark Orange
        RiskLevel.CRITICAL: "#DC143C", # Crimson
    }
    
    def __init__(
        self,
        client: Optional[SlackClient] = None,
        settings: Optional[Settings] = None,
        remediation_callback: Optional[Callable[[str, str], Awaitable[Dict[str, Any]]]] = None,
    ):
        """
        Initialize approval adapter.
        
        Args:
            client: Slack client instance (creates new if not provided)
            settings: Application settings
            remediation_callback: Async function to call on approval (incident_id, approver) -> result
        """
        self.settings = settings or Settings()
        self.client = client or SlackClient(settings=self.settings)
        self.approvals_channel = self.settings.slack_approvals_channel
        self.remediation_callback = remediation_callback
        
        # Store pending approvals (in production, use Redis or database)
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
    
    async def request_approval(
        self,
        incident: Incident,
        plan: RemediationPlan,
        timeout_minutes: int = 30,
        requestor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send approval request to Slack with interactive buttons.
        
        Args:
            incident: Incident requiring approval
            plan: Remediation plan to approve
            timeout_minutes: Approval timeout in minutes
            requestor: User requesting approval
            
        Returns:
            Slack API response with message timestamp
        """
        timeout_at = datetime.utcnow() + timedelta(minutes=timeout_minutes)
        
        # Build interactive message blocks
        blocks = self._build_approval_blocks(
            incident=incident,
            plan=plan,
            timeout_at=timeout_at,
            requestor=requestor,
        )
        
        logger.info(
            "slack_request_approval",
            incident_id=incident.incident_id,
            action_type=plan.action_type.value,
            timeout_minutes=timeout_minutes,
            channel=self.approvals_channel,
        )
        
        try:
            response = await self.client.post_message(
                channel=self.approvals_channel,
                text=self._get_approval_fallback_text(incident, plan),
                blocks=blocks,
            )
            
            message_ts = response.get("ts")
            
            # Store pending approval
            self._pending_approvals[incident.incident_id] = {
                "incident": incident,
                "plan": plan,
                "message_ts": message_ts,
                "channel": self.approvals_channel,
                "requested_at": datetime.utcnow(),
                "timeout_at": timeout_at,
                "requestor": requestor,
            }
            
            logger.info(
                "slack_approval_request_sent",
                incident_id=incident.incident_id,
                message_ts=message_ts,
            )
            
            return response
        
        except Exception as e:
            logger.error(
                "slack_approval_request_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )
            raise
    
    def _build_approval_blocks(
        self,
        incident: Incident,
        plan: RemediationPlan,
        timeout_at: datetime,
        requestor: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """
        Build Slack blocks for approval request.
        
        Args:
            incident: Incident object
            plan: Remediation plan
            timeout_at: Approval timeout timestamp
            requestor: User who requested approval
            
        Returns:
            List of Slack block elements
        """
        blocks = []
        
        # Header
        severity_emoji = self.SEVERITY_EMOJI.get(incident.severity, "⚠️")
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_emoji} Remediation Approval Required",
                "emoji": True,
            }
        })
        
        blocks.append({"type": "divider"})
        
        # Incident details
        incident_fields = [
            {
                "type": "mrkdwn",
                "text": f"*Incident ID:*\n`{incident.incident_id}`"
            },
            {
                "type": "mrkdwn",
                "text": f"*Source:*\n{incident.source.value.upper()}"
            },
            {
                "type": "mrkdwn",
                "text": f"*Severity:*\n{severity_emoji} {incident.severity.value.upper()}"
            },
        ]
        
        if incident.failure_type:
            incident_fields.append({
                "type": "mrkdwn",
                "text": f"*Failure Type:*\n`{incident.failure_type.value}`"
            })
        
        blocks.append({
            "type": "section",
            "fields": incident_fields
        })
        
        # Error message or root cause
        if incident.root_cause:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause:*\n{self._truncate_text(incident.root_cause, 300)}"
                }
            })
        elif incident.error_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{self._truncate_text(incident.error_message, 300)}```"
                }
            })
        
        # Context information
        if incident.context:
            context_lines = []
            context_fields = ["repository", "workflow", "job", "service", "namespace", "branch"]
            
            for field in context_fields:
                if field in incident.context and incident.context[field]:
                    context_lines.append(f"• *{field.title()}:* `{incident.context[field]}`")
            
            if context_lines:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Context:*\n" + "\n".join(context_lines[:4])
                    }
                })
        
        # Confidence score
        if incident.confidence is not None:
            confidence_level = ConfidenceLevel.from_score(incident.confidence)
            confidence_emoji = self._get_confidence_emoji(incident.confidence)
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*AI Confidence:*\n{confidence_emoji} {incident.confidence:.1%} ({confidence_level.value.replace('_', ' ').title()})"
                }
            })
        
        blocks.append({"type": "divider"})
        
        # Remediation plan details
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🔧 Proposed Remediation*"
            }
        })
        
        plan_fields = [
            {
                "type": "mrkdwn",
                "text": f"*Action:*\n`{plan.action_type.value}`"
            },
            {
                "type": "mrkdwn",
                "text": f"*Risk Level:*\n{self._get_risk_emoji(plan.risk_level)} {plan.risk_level.value.upper()}"
            },
        ]
        
        if plan.estimated_duration_seconds:
            duration = self._format_duration(plan.estimated_duration_seconds)
            plan_fields.append({
                "type": "mrkdwn",
                "text": f"*Est. Duration:*\n{duration}"
            })
        
        blocks.append({
            "type": "section",
            "fields": plan_fields
        })
        
        # Action description
        if plan.reason:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{plan.reason}"
                }
            })
        
        # Parameters (if any)
        if plan.parameters:
            param_text = self._format_parameters(plan.parameters)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Parameters:*\n```\n{param_text}\n```"
                }
            })
        
        blocks.append({"type": "divider"})
        
        # Timeout information
        timeout_timestamp = int(timeout_at.timestamp())
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⏰ This request will expire <!date^{timeout_timestamp}^{{date_short_pretty}} at {{time}}|{timeout_at.isoformat()}>"
                }
            ]
        })
        
        # Action buttons
        blocks.append({
            "type": "actions",
            "block_id": f"approval_actions_{incident.incident_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Approve",
                        "emoji": True,
                    },
                    "style": "primary",
                    "value": f"approve_{incident.incident_id}",
                    "action_id": f"approve_{incident.incident_id}",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "❌ Reject",
                        "emoji": True,
                    },
                    "style": "danger",
                    "value": f"reject_{incident.incident_id}",
                    "action_id": f"reject_{incident.incident_id}",
                },
            ]
        })
        
        # Footer
        if requestor:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Requested by {requestor} • DevFlowFix AI"
                    }
                ]
            })
        else:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "DevFlowFix AI • Autonomous CI/CD Remediation"
                    }
                ]
            })
        
        return blocks
    
    async def handle_callback(
        self,
        payload: Dict[str, Any],
    ) -> ApprovalResponse:
        """
        Handle Slack interactive callback from button click.
        
        Args:
            payload: Slack interaction payload
            
        Returns:
            ApprovalResponse with execution result
        """
        # Extract callback data
        user = payload.get("user", {})
        approver = user.get("username") or user.get("name") or user.get("id", "unknown")
        
        actions = payload.get("actions", [])
        if not actions:
            logger.warning("slack_callback_no_actions", payload=payload)
            raise ValueError("No actions in callback payload")
        
        action = actions[0]
        action_id = action.get("action_id", "")
        action_value = action.get("value", "")
        
        # Parse action (approve_{incident_id} or reject_{incident_id})
        if action_id.startswith("approve_"):
            approved = True
            incident_id = action_id.replace("approve_", "")
        elif action_id.startswith("reject_"):
            approved = False
            incident_id = action_id.replace("reject_", "")
        else:
            logger.warning("slack_callback_unknown_action", action_id=action_id)
            raise ValueError(f"Unknown action: {action_id}")
        
        logger.info(
            "slack_approval_callback",
            incident_id=incident_id,
            approved=approved,
            approver=approver,
        )
        
        # Get pending approval
        approval_data = self._pending_approvals.get(incident_id)
        if not approval_data:
            logger.warning(
                "slack_approval_not_found",
                incident_id=incident_id,
            )
            raise ValueError(f"No pending approval found for incident: {incident_id}")
        
        # Check timeout
        if datetime.utcnow() > approval_data["timeout_at"]:
            logger.warning(
                "slack_approval_timeout",
                incident_id=incident_id,
            )
            raise ApprovalTimeoutError(
                incident_id=incident_id,
                timeout_minutes=int((approval_data["timeout_at"] - approval_data["requested_at"]).total_seconds() / 60)
            )
        
        incident = approval_data["incident"]
        plan = approval_data["plan"]
        
        # Update the message to show decision
        await self._update_approval_message(
            channel=approval_data["channel"],
            message_ts=approval_data["message_ts"],
            incident=incident,
            approved=approved,
            approver=approver,
        )
        
        # Remove from pending
        del self._pending_approvals[incident_id]
        
        # Create approval response
        approval_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        
        response = ApprovalResponse(
            incident_id=incident_id,
            approval_status=approval_status,
            approver=approver,
            approved_at=datetime.utcnow(),
            message=f"Remediation {'approved' if approved else 'rejected'} by {approver}",
            executed=False,
        )
        
        # Execute remediation if approved and callback provided
        if approved and self.remediation_callback:
            logger.info(
                "slack_executing_remediation",
                incident_id=incident_id,
                approver=approver,
            )
            
            try:
                execution_result = await self.remediation_callback(incident_id, approver)
                response.executed = True
                response.execution_result = execution_result
                response.message = f"Remediation approved and executed by {approver}"
                
                logger.info(
                    "slack_remediation_executed",
                    incident_id=incident_id,
                    success=execution_result.get("success", False),
                )
            
            except Exception as e:
                logger.error(
                    "slack_remediation_execution_failed",
                    incident_id=incident_id,
                    error=str(e),
                )
                response.execution_result = {
                    "success": False,
                    "error": str(e),
                }
                response.message = f"Approved by {approver} but execution failed: {str(e)}"
        
        logger.info(
            "slack_approval_callback_complete",
            incident_id=incident_id,
            approved=approved,
            executed=response.executed,
        )
        
        return response
    
    async def _update_approval_message(
        self,
        channel: str,
        message_ts: str,
        incident: Incident,
        approved: bool,
        approver: str,
    ) -> None:
        """
        Update approval message to show decision.
        
        Args:
            channel: Channel ID
            message_ts: Message timestamp
            incident: Incident object
            approved: Whether approved or rejected
            approver: User who made the decision
        """
        decision_emoji = "✅" if approved else "❌"
        decision_text = "APPROVED" if approved else "REJECTED"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{decision_emoji} Remediation {decision_text}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident ID:*\n`{incident.incident_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Decision:*\n{decision_emoji} {decision_text}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Decided By:*\n{approver}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Decided At:*\n<!date^{int(datetime.utcnow().timestamp())}^{{date_short_pretty}} {{time}}|{datetime.utcnow().isoformat()}>"
                    },
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"{'✅ Remediation will be executed' if approved else '❌ Remediation cancelled'}"
                    }
                ]
            }
        ]
        
        try:
            await self.client.update_message(
                channel=channel,
                ts=message_ts,
                text=f"{decision_emoji} Remediation {decision_text.lower()} by {approver}",
                blocks=blocks,
            )
            
            logger.info(
                "slack_approval_message_updated",
                incident_id=incident.incident_id,
                approved=approved,
            )
        
        except Exception as e:
            logger.error(
                "slack_update_message_failed",
                incident_id=incident.incident_id,
                error=str(e),
            )
    
    def verify_slack_request(
        self,
        request_body: str,
        timestamp: str,
        signature: str,
    ) -> bool:
        """
        Verify Slack request signature for security.
        
        Args:
            request_body: Raw request body
            timestamp: Request timestamp from headers
            signature: Signature from headers
            
        Returns:
            True if signature is valid
        """
        if not self.settings.slack_signing_secret:
            logger.warning("slack_signing_secret_not_configured")
            return True  # Skip verification if not configured
        
        # Create signature base string
        sig_basestring = f"v0:{timestamp}:{request_body}"
        
        # Compute signature
        computed_signature = 'v0=' + hmac.new(
            self.settings.slack_signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        is_valid = hmac.compare_digest(computed_signature, signature)
        
        if not is_valid:
            logger.warning(
                "slack_signature_verification_failed",
                expected=computed_signature[:20] + "...",
                received=signature[:20] + "...",
            )
        
        return is_valid
    
    def get_pending_approval(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """
        Get pending approval data for an incident.
        
        Args:
            incident_id: Incident ID
            
        Returns:
            Approval data or None if not found
        """
        return self._pending_approvals.get(incident_id)
    
    def get_all_pending_approvals(self) -> list[Dict[str, Any]]:
        """
        Get all pending approvals.
        
        Returns:
            List of pending approval data
        """
        return list(self._pending_approvals.values())
    
    def cancel_approval(self, incident_id: str) -> bool:
        """
        Cancel a pending approval.
        
        Args:
            incident_id: Incident ID
            
        Returns:
            True if approval was cancelled, False if not found
        """
        if incident_id in self._pending_approvals:
            del self._pending_approvals[incident_id]
            logger.info("slack_approval_cancelled", incident_id=incident_id)
            return True
        return False
    
    # Helper methods
    
    def _get_confidence_emoji(self, confidence: float) -> str:
        """Get emoji representing confidence level."""
        if confidence >= 0.95:
            return "🟢"
        elif confidence >= 0.85:
            return "🟡"
        elif confidence >= 0.70:
            return "🟠"
        else:
            return "🔴"
    
    def _get_risk_emoji(self, risk_level: RiskLevel) -> str:
        """Get emoji representing risk level."""
        risk_emoji = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴",
        }
        return risk_emoji.get(risk_level, "⚠️")
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds as human-readable text."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    def _format_parameters(self, parameters: Dict[str, Any]) -> str:
        """Format parameters dictionary as readable text."""
        lines = []
        for key, value in parameters.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"{key}: {value}")
            else:
                lines.append(f"{key}: {str(value)[:50]}")
        return "\n".join(lines[:10])
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
    
    def _get_approval_fallback_text(
        self,
        incident: Incident,
        plan: RemediationPlan,
    ) -> str:
        """
        Get fallback text for approval request.
        
        Args:
            incident: Incident object
            plan: Remediation plan
            
        Returns:
            Plain text summary
        """
        severity_emoji = self.SEVERITY_EMOJI.get(incident.severity, "⚠️")
        
        return (
            f"{severity_emoji} Approval Required | "
            f"Incident: {incident.incident_id} | "
            f"Action: {plan.action_type.value} | "
            f"Risk: {plan.risk_level.value}"
        )
    
    async def close(self) -> None:
        """Close underlying Slack client."""
        await self.client.close()
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
