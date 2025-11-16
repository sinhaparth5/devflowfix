# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from app.core.enums import IncidentSource, Severity


class EventType(str, Enum):
    """Event type enumeration."""
    GITHUB_WORKFLOW_FAILED = "github_workflow_failed"
    GITHUB_WORKFLOW_SUCCESS = "github_workflow_success"
    ARGOCD_SYNC_FAILED = "argocd_sync_failed"
    ARGOCD_SYNC_SUCCESS = "argocd_sync_success"
    KUBERNETES_POD_FAILED = "kubernetes_pod_failed"
    KUBERNETES_POD_CRASH = "kubernetes_pod_crash"
    GENERIC = "generic"


@dataclass
class BaseEvent(ABC):
    """
    Abstract base class for all webhook events.
    
    All event types must inherit from this class and implement
    the required abstract methods.
    """
    
    # Core fields (common to all events)
    event_type: EventType
    source: IncidentSource
    timestamp: datetime
    raw_payload: Dict[str, Any]
    
    # Event metadata
    event_id: Optional[str] = None
    delivery_id: Optional[str] = None
    
    # Incident details (to be populated by subclasses)
    severity: Severity = Severity.MEDIUM
    error_message: Optional[str] = None
    failure_type: Optional[str] = None
    
    # Context information
    repository: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    workflow_name: Optional[str] = None
    job_name: Optional[str] = None
    service_name: Optional[str] = None
    namespace: Optional[str] = None
    
    # Parsed at
    parsed_at: datetime = field(default_factory=datetime.utcnow)
    
    @abstractmethod
    def parse(self) -> None:
        """
        Parse the raw payload and populate event fields.
        
        Must be implemented by all subclasses to extract relevant
        information from the raw webhook payload.
        
        Raises:
            ValueError: If payload cannot be parsed
        """
        pass
    
    @abstractmethod
    def is_failure_event(self) -> bool:
        """
        Determine if this event represents a failure.
        
        Returns:
            True if event represents a failure/error condition
        """
        pass
    
    @abstractmethod
    def get_context(self) -> Dict[str, Any]:
        """
        Get event context for incident creation.
        
        Returns:
            Dictionary with context information for the incident
        """
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary representation.
        
        Returns:
            Dictionary representation of the event
        """
        return {
            "event_type": self.event_type.value,
            "source": self.source.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_id": self.event_id,
            "delivery_id": self.delivery_id,
            "severity": self.severity.value,
            "error_message": self.error_message,
            "failure_type": self.failure_type,
            "repository": self.repository,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "workflow_name": self.workflow_name,
            "job_name": self.job_name,
            "service_name": self.service_name,
            "namespace": self.namespace,
            "context": self.get_context(),
            "parsed_at": self.parsed_at.isoformat(),
        }
    
    def get_summary(self) -> str:
        """
        Get a human-readable summary of the event.
        
        Returns:
            Summary string
        """
        parts = [
            f"[{self.source.value.upper()}]",
            f"{self.event_type.value}",
        ]
        
        if self.repository:
            parts.append(f"in {self.repository}")
        if self.workflow_name:
            parts.append(f"workflow: {self.workflow_name}")
        if self.service_name:
            parts.append(f"service: {self.service_name}")
            
        return " ".join(parts)
    
    def __repr__(self) -> str:
        """String representation of event."""
        return (
            f"{self.__class__.__name__}("
            f"type={self.event_type.value}, "
            f"source={self.source.value}, "
            f"event_id={self.event_id})"
        )


@dataclass
class GenericEvent(BaseEvent):
    """
    Generic event for unrecognized or unsupported event types.
    
    Used as a fallback when event cannot be parsed into a specific type.
    """
    
    def parse(self) -> None:
        """Parse generic event (minimal processing)."""
        self.event_id = self.raw_payload.get("id", str(int(datetime.utcnow().timestamp())))
        self.error_message = "Generic event - no specific parser available"
    
    def is_failure_event(self) -> bool:
        """Generic events are not considered failures."""
        return False
    
    def get_context(self) -> Dict[str, Any]:
        """Get context from raw payload."""
        return {
            "payload_keys": list(self.raw_payload.keys()),
            "payload_size": len(str(self.raw_payload)),
        }