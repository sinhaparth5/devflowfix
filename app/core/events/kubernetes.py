# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from app.core.events.base import BaseEvent, EventType
from app.core.enums import IncidentSource, Severity, FailureType

logger = structlog.get_logger(__name__)

@dataclass
class KubernetesPodEvent(BaseEvent):
    """
    Kubernetes pod event.
    
    Parses Kubernetes pod failure events.
    """
    # Kubernetes-specific fields
    pod_name: Optional[str] = None
    pod_phase: Optional[str] = None  # Pending, Running, Succeeded, Failed, Unknown
    container_name: Optional[str] = None
    container_state: Optional[str] = None
    restart_count: Optional[int] = None
    
    # Event details
    reason: Optional[str] = None  # BackOff, CrashLoopBackOff, ImagePullBackOff, etc.
    message: Optional[str] = None
    
    # Resource info
    node_name: Optional[str] = None
    
    def __post_init__(self):
        """Initialize and parse after dataclass creation."""
        self.source = IncidentSource.KUBERNETES
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        self.parse()
    
    def parse(self) -> None:
        """
        Parse Kubernetes event payload.
        
        Raises:
            ValueError: If payload is missing required fields
        """
        try:
            # Get involved object (usually a Pod)
            involved_object = self.raw_payload.get("involvedObject", {})
            if not involved_object:
                raise ValueError("Missing 'involvedObject' in payload")
            
            # Pod info
            self.pod_name = involved_object.get("name")
            self.namespace = involved_object.get("namespace", "default")
            
            # Event metadata
            metadata = self.raw_payload.get("metadata", {})
            self.event_id = metadata.get("uid", f"k8s_{self.pod_name}_{int(datetime.utcnow().timestamp())}")
            
            # Event details
            self.reason = self.raw_payload.get("reason")
            self.message = self.raw_payload.get("message")
            
            # Try to get more details from event source
            source = self.raw_payload.get("source", {})
            self.node_name = source.get("host")
            
            # Determine failure type from reason
            self._determine_failure_type()
            
            # Service name (use pod name without generated suffix)
            if self.pod_name:
                # Remove pod hash suffix (e.g., "my-app-abc123-xyz" -> "my-app")
                parts = self.pod_name.rsplit("-", 2)
                self.service_name = parts[0] if len(parts) > 2 else self.pod_name
            
            # Determine event type and severity
            self._determine_event_type()
            self._format_error_message()
            
            logger.debug(
                "kubernetes_event_parsed",
                event_id=self.event_id,
                pod=self.pod_name,
                reason=self.reason,
                namespace=self.namespace,
            )
            
        except Exception as e:
            logger.error(
                "kubernetes_event_parse_failed",
                error=str(e),
                payload_keys=list(self.raw_payload.keys()),
            )
            raise ValueError(f"Failed to parse Kubernetes webhook payload: {e}")
    
    def _determine_failure_type(self) -> None:
        """Determine specific failure type from Kubernetes reason."""
        reason_to_failure_type = {
            "ImagePullBackOff": FailureType.IMAGE_PULL_BACKOFF,
            "ErrImagePull": FailureType.IMAGE_PULL_BACKOFF,
            "CrashLoopBackOff": FailureType.CRASH_LOOP_BACKOFF,
            "BackOff": FailureType.CRASH_LOOP_BACKOFF,
            "OOMKilled": FailureType.OOM_KILLED,
            "Evicted": FailureType.EVICTED,
            "FailedScheduling": FailureType.PENDING_POD,
            "FailedMount": FailureType.CONFIG_ERROR,
        }
        
        if self.reason:
            failure_type = reason_to_failure_type.get(self.reason)
            if failure_type:
                self.failure_type = failure_type.value
    
    def _determine_event_type(self) -> None:
        """Determine event type and severity based on reason."""
        failure_reasons = [
            "ImagePullBackOff",
            "ErrImagePull",
            "CrashLoopBackOff",
            "BackOff",
            "OOMKilled",
            "Evicted",
            "FailedScheduling",
            "FailedMount",
            "Failed",
        ]
        
        if self.reason in failure_reasons:
            if self.reason == "CrashLoopBackOff":
                self.event_type = EventType.KUBERNETES_POD_CRASH
                self.severity = Severity.CRITICAL
            else:
                self.event_type = EventType.KUBERNETES_POD_FAILED
                self.severity = Severity.HIGH
        else:
            self.event_type = EventType.KUBERNETES_POD_FAILED
            self.severity = Severity.MEDIUM
    
    def _format_error_message(self) -> None:
        """Format error message from event details."""
        if self.message:
            self.error_message = (
                f"Pod '{self.pod_name}' in namespace '{self.namespace}': "
                f"{self.reason} - {self.message}"
            )
        else:
            self.error_message = (
                f"Pod '{self.pod_name}' in namespace '{self.namespace}' "
                f"failed with reason: {self.reason}"
            )
    
    def is_failure_event(self) -> bool:
        """
        Check if this is a failure event.
        
        Returns:
            True if event represents a pod failure
        """
        failure_reasons = [
            "ImagePullBackOff",
            "ErrImagePull",
            "CrashLoopBackOff",
            "BackOff",
            "OOMKilled",
            "Evicted",
            "FailedScheduling",
            "FailedMount",
            "Failed",
        ]
        return self.reason in failure_reasons
    
    def get_context(self) -> Dict[str, Any]:
        """
        Get context information for incident creation.
        
        Returns:
            Dictionary with Kubernetes context
        """
        return {
            "source": "kubernetes",
            "pod_name": self.pod_name,
            "service_name": self.service_name,
            "namespace": self.namespace,
            "reason": self.reason,
            "message": self.message,
            "pod_phase": self.pod_phase,
            "container_name": self.container_name,
            "container_state": self.container_state,
            "restart_count": self.restart_count,
            "node_name": self.node_name,
        }
    
    def get_summary(self) -> str:
        """
        Get human-readable summary.
        
        Returns:
            Summary string
        """
        return (
            f"Kubernetes pod '{self.pod_name}' "
            f"in namespace '{self.namespace}': {self.reason}"
        )