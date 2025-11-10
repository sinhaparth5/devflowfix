# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Dict, Any, Optional, Type
from datetime import datetime
import structlog

from app.core.events.base import BaseEvent, GenericEvent, EventType
from app.core.events.github import (
    GitHubWorkflowEvent,
    GitHubWorkflowFailedEvent,
    GitHubWorkflowJobEvent,
)
from app.core.events.argocd import ArgoCDSyncEvent
from app.core.events.kubernetes import KubernetesPodEvent
from app.core.enums import IncidentSource

logger = structlog.get_logger(__name__)

class EventParseError(Exception):
    """Raised when event payload cannot be parsed."""
    pass

class EventFactory:
    """
    Factory for creating event objects from webhook payloads.
    
    Detects the source of the webhook and parses it into
    the appropriate event type.
    """
    @staticmethod
    def create_event(
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> BaseEvent:
        """
        Create event object from webhook payload.
        
        Automatically detects the source and parses accordingly.
        
        Args:
            payload: Webhook payload dictionary
            headers: Optional HTTP headers for source detection
            
        Returns:
            Parsed event object
            
        Raises:
            EventParseError: If payload cannot be parsed
        """
        headers = headers or {}
        
        try:
            # Detect source from headers or payload
            source = EventFactory._detect_source(payload, headers)
            
            logger.debug(
                "event_factory_creating",
                source=source,
                payload_keys=list(payload.keys()),
                headers_keys=list(headers.keys()),
            )
            
            # Create appropriate event based on source
            if source == IncidentSource.GITHUB:
                return EventFactory._create_github_event(payload, headers)
            elif source == IncidentSource.ARGOCD:
                return EventFactory._create_argocd_event(payload, headers)
            elif source == IncidentSource.KUBERNETES:
                return EventFactory._create_kubernetes_event(payload, headers)
            else:
                logger.warning(
                    "event_factory_unknown_source",
                    source=source,
                    payload_keys=list(payload.keys()),
                )
                return EventFactory._create_generic_event(payload, headers)
                
        except Exception as e:
            logger.error(
                "event_factory_failed",
                error=str(e),
                payload_keys=list(payload.keys()),
                exc_info=True,
            )
            
            # Return generic event as fallback
            return EventFactory._create_generic_event(payload, headers)
    
    @staticmethod
    def _detect_source(
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> IncidentSource:
        """
        Detect webhook source from headers or payload.
        
        Args:
            payload: Webhook payload
            headers: HTTP headers
            
        Returns:
            Detected source
        """
        # Check headers first (most reliable)
        # Normalize header keys to lowercase
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        # GitHub
        if "x-github-event" in headers_lower or "x-github-delivery" in headers_lower:
            return IncidentSource.GITHUB
        
        # Check explicit source header
        if "x-webhook-source" in headers_lower:
            source_value = headers_lower["x-webhook-source"].lower()
            if "github" in source_value:
                return IncidentSource.GITHUB
            elif "argocd" in source_value:
                return IncidentSource.ARGOCD
            elif "kubernetes" in source_value or "k8s" in source_value:
                return IncidentSource.KUBERNETES
        
        # Check payload structure
        # GitHub
        if "workflow_run" in payload or "workflow_job" in payload:
            return IncidentSource.GITHUB
        if "repository" in payload and "sender" in payload:
            return IncidentSource.GITHUB
        
        # ArgoCD
        if "application" in payload:
            app = payload.get("application", {})
            if "spec" in app and "status" in app:
                return IncidentSource.ARGOCD
        
        # Kubernetes
        if "involvedObject" in payload and "kind" in payload.get("involvedObject", {}):
            return IncidentSource.KUBERNETES
        if "metadata" in payload and "kind" in payload:
            kind = payload.get("kind", "")
            if kind in ["Event", "Pod", "Deployment", "Service"]:
                return IncidentSource.KUBERNETES
        
        # Default to manual/unknown
        return IncidentSource.MANUAL
    
    @staticmethod
    def _create_github_event(
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> BaseEvent:
        """
        Create GitHub event from payload.
        
        Args:
            payload: GitHub webhook payload
            headers: HTTP headers
            
        Returns:
            GitHub event object
        """
        headers_lower = {k.lower(): v for k, v in headers.items()}
        github_event = headers_lower.get("x-github-event", "")
        delivery_id = headers_lower.get("x-github-delivery")
        
        # Determine event type
        if github_event == "workflow_run" or "workflow_run" in payload:
            # Check conclusion
            workflow_run = payload.get("workflow_run", {})
            conclusion = workflow_run.get("conclusion")
            
            event = GitHubWorkflowEvent(
                event_type=EventType.GITHUB_WORKFLOW_FAILED,
                source=IncidentSource.GITHUB,
                timestamp=datetime.utcnow(),
                raw_payload=payload,
                delivery_id=delivery_id,
            )
            
            # If explicitly failed, use specialized class
            if conclusion in ["failure", "cancelled", "timed_out"]:
                event = GitHubWorkflowFailedEvent(
                    event_type=EventType.GITHUB_WORKFLOW_FAILED,
                    source=IncidentSource.GITHUB,
                    timestamp=datetime.utcnow(),
                    raw_payload=payload,
                    delivery_id=delivery_id,
                )
            
            return event
            
        elif github_event == "workflow_job" or "workflow_job" in payload:
            return GitHubWorkflowJobEvent(
                event_type=EventType.GITHUB_WORKFLOW_FAILED,
                source=IncidentSource.GITHUB,
                timestamp=datetime.utcnow(),
                raw_payload=payload,
                delivery_id=delivery_id,
            )
        
        else:
            # Generic GitHub event
            logger.warning(
                "github_event_type_unknown",
                github_event=github_event,
                payload_keys=list(payload.keys()),
            )
            return GenericEvent(
                event_type=EventType.GENERIC,
                source=IncidentSource.GITHUB,
                timestamp=datetime.utcnow(),
                raw_payload=payload,
                delivery_id=delivery_id,
            )
    
    @staticmethod
    def _create_argocd_event(
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> BaseEvent:
        """
        Create ArgoCD event from payload.
        
        Args:
            payload: ArgoCD webhook payload
            headers: HTTP headers
            
        Returns:
            ArgoCD event object
        """
        return ArgoCDSyncEvent(
            event_type=EventType.ARGOCD_SYNC_FAILED,
            source=IncidentSource.ARGOCD,
            timestamp=datetime.utcnow(),
            raw_payload=payload,
        )
    
    @staticmethod
    def _create_kubernetes_event(
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> BaseEvent:
        """
        Create Kubernetes event from payload.
        
        Args:
            payload: Kubernetes event payload
            headers: HTTP headers
            
        Returns:
            Kubernetes event object
        """
        return KubernetesPodEvent(
            event_type=EventType.KUBERNETES_POD_FAILED,
            source=IncidentSource.KUBERNETES,
            timestamp=datetime.utcnow(),
            raw_payload=payload,
        )
    
    @staticmethod
    def _create_generic_event(
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> BaseEvent:
        """
        Create generic event from payload.
        
        Fallback for unknown or unsupported event types.
        
        Args:
            payload: Webhook payload
            headers: HTTP headers
            
        Returns:
            Generic event object
        """
        return GenericEvent(
            event_type=EventType.GENERIC,
            source=IncidentSource.MANUAL,
            timestamp=datetime.utcnow(),
            raw_payload=payload,
        )
    
    @staticmethod
    def is_failure_event(event: BaseEvent) -> bool:
        """
        Check if event represents a failure.
        
        Args:
            event: Event object
            
        Returns:
            True if event is a failure
        """
        return event.is_failure_event()
    
    @staticmethod
    def get_event_summary(event: BaseEvent) -> str:
        """
        Get human-readable summary of event.
        
        Args:
            event: Event object
            
        Returns:
            Summary string
        """
        return event.get_summary()

# Convenience function for creating events
def create_event_from_webhook(
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> BaseEvent:
    """
    Create event from webhook payload.
    
    Convenience function that wraps EventFactory.create_event().
    
    Args:
        payload: Webhook payload dictionary
        headers: Optional HTTP headers
        
    Returns:
        Parsed event object
    """
    return EventFactory.create_event(payload, headers)