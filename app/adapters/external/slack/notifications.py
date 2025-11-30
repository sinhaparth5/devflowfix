# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Slack Notification Adapter

Sends rich formatted notifications to Slack channels for:
- Incident detection
- Analysis completion
- Remediation status
- Approval requests
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.models.incident import Incident
from app.core.enums import (
    Severity,
    Fixability,
    ConfidenceLevel,
    Outcome,
    NotificationType,
)
from app.adapters.external.slack.client import SlackClient
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SlackNotificationAdapter:
    """
    Adapter for sending structured notifications to Slack.
    
    Provides rich message formatting using Slack blocks for:
    - Incident notifications
    - Remediation updates
    - Approval requests
    - Escalations
    
    Example:
        ```python
        notifier = SlackNotificationAdapter()
        
        await notifier.notify_incident(
            incident=incident,
            similar_incidents=[...]
        )
        ```
    """
    
    SEVERITY_EMOJI = {
        Severity.LOW: "ℹ️",
        Severity.MEDIUM: "⚠️",
        Severity.HIGH: "🔥",
        Severity.CRITICAL: "🚨",
    }
    
    FIXABILITY_EMOJI = {
        Fixability.AUTO: "🤖",
        Fixability.MANUAL: "👨‍💻",
        Fixability.UNKNOWN: "❓",
    }
    
    OUTCOME_EMOJI = {
        Outcome.SUCCESS: "✅",
        Outcome.FAILED: "❌",
        Outcome.PENDING: "⏳",
        Outcome.ESCALATED: "🆘",
        Outcome.ROLLED_BACK: "↩️",
        Outcome.TIMEOUT: "⏰",
        Outcome.CANCELLED: "🚫",
    }
    
    CONFIDENCE_COLORS = {
        ConfidenceLevel.VERY_LOW: "#DC143C",
        ConfidenceLevel.LOW: "#FF8C00",     
        ConfidenceLevel.MEDIUM: "#FFD700",    
        ConfidenceLevel.HIGH: "#32CD32",     
        ConfidenceLevel.VERY_HIGH: "#228B22", 
    }
    
    def __init__(
        self,
        client: Optional[SlackClient] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize notification adapter.
        
        Args:
            client: Slack client instance (creates new if not provided)
            settings: Application settings
        """
        self.settings = settings or Settings()
        self.client = client or SlackClient(settings=self.settings)
        self.incidents_channel = self.settings.slack_incidents_channel
        self.approvals_channel = self.settings.slack_approvals_channel
    
    async def notify_incident(
        self,
        incident: Incident,
        similar_incidents: Optional[List[Dict[str, Any]]] = None,
        notification_type: NotificationType = NotificationType.INCIDENT_DETECTED,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Post incident notification to #incidents channel with rich formatting.
        
        Args:
            incident: Incident object to notify about
            similar_incidents: List of similar incidents from RAG
            notification_type: Type of notification
            **kwargs: Additional context (error, remediation_result, decision, etc.)
            
        Returns:
            Slack API response
        """
        # Sanitize kwargs to ensure they are JSON serializable
        # This prevents errors when logging non-serializable objects
        for key, value in kwargs.items():
            if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
                kwargs[key] = str(value)
        
        blocks = self._build_incident_blocks(
            incident=incident,
            similar_incidents=similar_incidents or [],
            notification_type=notification_type,
        )
        
        channel = self.incidents_channel
        if notification_type == NotificationType.APPROVAL_REQUESTED:
            channel = self.approvals_channel
        
        logger.info(
            "slack_notify_incident",
            incident_id=incident.incident_id,
            notification_type=notification_type.value,
            channel=channel,
            severity=incident.severity.value,
        )
        
        try:
            response = await self.client.post_message(
                channel=channel,
                text=self._get_fallback_text(incident, notification_type),
                blocks=blocks,
            )
            
            logger.info(
                "slack_notification_sent",
                incident_id=incident.incident_id,
                channel=channel,
                message_ts=response.get("ts"),
            )
            
            return response
        
        except Exception as e:
            logger.error(
                "slack_notification_failed",
                incident_id=incident.incident_id,
                error=str(e),
                channel=channel,
            )
            raise
    
    def _build_incident_blocks(
        self,
        incident: Incident,
        similar_incidents: List[Dict[str, Any]],
        notification_type: NotificationType,
    ) -> List[Dict[str, Any]]:
        """
        Build Slack blocks for incident notification.
        
        Args:
            incident: Incident object
            similar_incidents: Similar incidents from RAG
            notification_type: Type of notification
            
        Returns:
            List of Slack block elements
        """
        blocks = []
        
        severity_emoji = self.SEVERITY_EMOJI.get(incident.severity, "⚠️")
        header_text = f"{severity_emoji} *{notification_type.value.replace('_', ' ').title()}*"
        
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_emoji} Incident Detected",
                "emoji": True,
            }
        })
        
        blocks.append({"type": "divider"})
        
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
            {
                "type": "mrkdwn",
                "text": f"*Timestamp:*\n<!date^{int(incident.timestamp.timestamp())}^{{date_short_pretty}} {{time}}|{incident.timestamp.isoformat()}>"
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
        
        if incident.error_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error Message:*\n```{self._truncate_text(incident.error_message, 500)}```"
                }
            })
        
        if incident.context:
            context_text = self._format_context(incident.context)
            if context_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Context:*\n{context_text}"
                    }
                })
        
        if incident.root_cause or incident.confidence is not None:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🔍 Analysis Results*"
                }
            })
            
            analysis_fields = []
            
            if incident.root_cause:
                analysis_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Root Cause:*\n{self._truncate_text(incident.root_cause, 300)}"
                })
            
            if incident.fixability:
                fixability_emoji = self.FIXABILITY_EMOJI.get(incident.fixability, "❓")
                analysis_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Fixability:*\n{fixability_emoji} {incident.fixability.value.upper()}"
                })
            
            if incident.confidence is not None:
                confidence_level = ConfidenceLevel.from_score(incident.confidence)
                confidence_color = self._get_confidence_emoji(incident.confidence)
                analysis_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Confidence:*\n{confidence_color} {incident.confidence:.1%} ({confidence_level.value})"
                })
            
            if analysis_fields:
                blocks.append({
                    "type": "section",
                    "fields": analysis_fields
                })
        
        if similar_incidents:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📊 Similar Incidents Found: {len(similar_incidents)}*"
                }
            })
            
            similar_text = self._format_similar_incidents(similar_incidents[:3])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": similar_text
                }
            })
        
        if incident.remediation_executed or incident.outcome:
            blocks.append({"type": "divider"})
            outcome_emoji = self.OUTCOME_EMOJI.get(incident.outcome, "⏳")
            
            remediation_fields = []
            
            if incident.outcome:
                remediation_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Status:*\n{outcome_emoji} {incident.outcome.value.upper()}"
                })
            
            if incident.outcome_message:
                remediation_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Message:*\n{self._truncate_text(incident.outcome_message, 200)}"
                })
            
            if incident.resolution_time_seconds:
                duration = self._format_duration(incident.resolution_time_seconds)
                remediation_fields.append({
                    "type": "mrkdwn",
                    "text": f"*Resolution Time:*\n{duration}"
                })
            
            if remediation_fields:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🔧 Remediation Status*"
                    }
                })
                blocks.append({
                    "type": "section",
                    "fields": remediation_fields
                })
        
        if incident.tags:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": " | ".join([f"`{tag}`" for tag in incident.tags[:5]])
                    }
                ]
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"DevFlowFix AI • <!date^{int(datetime.now(timezone.utc).timestamp())}^{{date_short_pretty}} {{time}}|{datetime.now(timezone.utc).isoformat()}>"
                }
            ]
        })
        
        return blocks
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary as readable text."""
        lines = []
        
        priority_fields = [
            "repository", "workflow", "job", "branch",
            "service", "namespace", "pod", "container",
            "app_name", "environment"
        ]
        
        for field in priority_fields:
            if field in context and context[field]:
                value = context[field]
                lines.append(f"• *{field.replace('_', ' ').title()}:* `{value}`")
        
        return "\n".join(lines[:5])
    
    def _format_similar_incidents(self, incidents: List[Dict[str, Any]]) -> str:
        """Format similar incidents as readable text."""
        lines = []
        
        for i, inc in enumerate(incidents, 1):
            similarity = inc.get("similarity", 0.0)
            incident_id = inc.get("incident_id", "unknown")
            outcome = inc.get("outcome", "unknown")
            
            outcome_emoji = "✅" if outcome == "success" else "❌" if outcome == "failed" else "⏳"
            
            lines.append(
                f"{i}. `{incident_id}` • {similarity:.1%} similar • {outcome_emoji} {outcome}"
            )
            
            if inc.get("root_cause"):
                root_cause = self._truncate_text(inc["root_cause"], 100)
                lines.append(f"   _{root_cause}_")
        
        return "\n".join(lines)
    
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
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds as human-readable text."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
    
    def _get_fallback_text(
        self,
        incident: Incident,
        notification_type: NotificationType,
    ) -> str:
        """
        Get fallback text for notification (used in notifications).
        
        Args:
            incident: Incident object
            notification_type: Type of notification
            
        Returns:
            Plain text summary
        """
        severity_emoji = self.SEVERITY_EMOJI.get(incident.severity, "⚠️")
        
        parts = [
            f"{severity_emoji} {notification_type.value.replace('_', ' ').title()}",
            f"Incident: {incident.incident_id}",
            f"Source: {incident.source.value}",
            f"Severity: {incident.severity.value}",
        ]
        
        if incident.confidence is not None:
            parts.append(f"Confidence: {incident.confidence:.1%}")
        
        if incident.outcome:
            parts.append(f"Status: {incident.outcome.value}")
        
        return " | ".join(parts)
    
    async def notify_remediation_started(
        self,
        incident: Incident,
        action_description: str,
    ) -> Dict[str, Any]:
        """
        Notify that remediation has started.
        
        Args:
            incident: Incident being remediated
            action_description: Description of remediation action
            
        Returns:
            Slack API response
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔧 Remediation Started",
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
                        "text": f"*Action:*\n{action_description}"
                    },
                ]
            }
        ]
        
        logger.info(
            "slack_notify_remediation_started",
            incident_id=incident.incident_id,
        )
        
        return await self.client.post_message(
            channel=self.incidents_channel,
            text=f"🔧 Remediation started for incident {incident.incident_id}",
            blocks=blocks,
        )
    
    async def notify_remediation_completed(
        self,
        incident: Incident,
        success: bool,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Notify that remediation has completed.
        
        Args:
            incident: Incident that was remediated
            success: Whether remediation succeeded
            message: Optional message about the result
            
        Returns:
            Slack API response
        """
        emoji = "✅" if success else "❌"
        status = "Success" if success else "Failed"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Remediation {status}",
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
                        "text": f"*Status:*\n{emoji} {status}"
                    },
                ]
            }
        ]
        
        if message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Details:*\n{message}"
                }
            })
        
        if incident.resolution_time_seconds:
            duration = self._format_duration(incident.resolution_time_seconds)
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⏱️ Resolved in {duration}"
                    }
                ]
            })
        
        logger.info(
            "slack_notify_remediation_completed",
            incident_id=incident.incident_id,
            success=success,
        )
        
        return await self.client.post_message(
            channel=self.incidents_channel,
            text=f"{emoji} Remediation {status.lower()} for incident {incident.incident_id}",
            blocks=blocks,
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
