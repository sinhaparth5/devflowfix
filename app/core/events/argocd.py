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
class ArgoCDSyncEvent(BaseEvent):
    """
    ArgoCD application sync event.
    
    Parses ArgoCD webhook payloads for application sync status.
    """
    # ArgoCD-specific fields
    application_name: Optional[str] = None
    project: Optional[str] = None
    sync_status: Optional[str] = None  # Synced, OutOfSync, Unknown
    health_status: Optional[str] = None  # Healthy, Progressing, Degraded, Suspended, Missing
    operation_state: Optional[str] = None  # Running, Failed, Error, Succeeded
    
    # Sync details
    revision: Optional[str] = None
    sync_started_at: Optional[datetime] = None
    sync_finished_at: Optional[datetime] = None
    
    # Server info
    server_url: Optional[str] = None
    
    def __post_init__(self):
        """Initialize and parse after dataclass creation."""
        self.source = IncidentSource.ARGOCD
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        self.parse()
    
    def parse(self) -> None:
        """
        Parse ArgoCD webhook payload.
        
        Raises:
            ValueError: If payload is missing required fields
        """
        try:
            # Get application object
            application = self.raw_payload.get("application", {})
            if not application:
                raise ValueError("Missing 'application' in payload")
            
            # Application metadata
            metadata = application.get("metadata", {})
            self.application_name = metadata.get("name")
            self.namespace = metadata.get("namespace")
            self.event_id = f"argocd_{self.application_name}_{int(datetime.utcnow().timestamp())}"
            
            # Spec
            spec = application.get("spec", {})
            self.project = spec.get("project")
            destination = spec.get("destination", {})
            self.server_url = destination.get("server")
            
            # Status
            status = application.get("status", {})
            
            # Sync status
            sync = status.get("sync", {})
            self.sync_status = sync.get("status")
            self.revision = sync.get("revision")
            
            # Health status
            health = status.get("health", {})
            self.health_status = health.get("status")
            
            # Operation state
            operation_state = status.get("operationState", {})
            self.operation_state = operation_state.get("phase")
            
            # Timing
            if operation_state.get("startedAt"):
                self.sync_started_at = self._parse_argocd_timestamp(
                    operation_state.get("startedAt")
                )
            if operation_state.get("finishedAt"):
                self.sync_finished_at = self._parse_argocd_timestamp(
                    operation_state.get("finishedAt")
                )
            
            # Service name (use application name)
            self.service_name = self.application_name
            
            # Determine event type and severity
            self._determine_event_type()
            self._extract_error_message(status)
            
            logger.debug(
                "argocd_event_parsed",
                event_id=self.event_id,
                application=self.application_name,
                sync_status=self.sync_status,
                health_status=self.health_status,
            )
            
        except Exception as e:
            logger.error(
                "argocd_event_parse_failed",
                error=str(e),
                payload_keys=list(self.raw_payload.keys()),
            )
            raise ValueError(f"Failed to parse ArgoCD webhook payload: {e}")
    
    def _determine_event_type(self) -> None:
        """Determine specific event type based on status."""
        is_failed = (
            self.sync_status == "OutOfSync" or
            self.health_status in ["Degraded", "Missing"] or
            self.operation_state in ["Failed", "Error"]
        )
        
        if is_failed:
            self.event_type = EventType.ARGOCD_SYNC_FAILED
            self.severity = Severity.HIGH
            self.failure_type = FailureType.SYNC_FAILED.value
        else:
            self.event_type = EventType.ARGOCD_SYNC_SUCCESS
            self.severity = Severity.LOW
    
    def _extract_error_message(self, status: Dict[str, Any]) -> None:
        """Extract error message from status."""
        if self.is_failure_event():
            # Try to get operation message
            operation_state = status.get("operationState", {})
            message = operation_state.get("message", "")
            
            if message:
                self.error_message = (
                    f"ArgoCD sync failed for '{self.application_name}': {message}"
                )
            else:
                self.error_message = (
                    f"ArgoCD application '{self.application_name}' is "
                    f"{self.sync_status}/{self.health_status}"
                )
        else:
            self.error_message = (
                f"ArgoCD application '{self.application_name}' synced successfully"
            )
    
    def _parse_argocd_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse ArgoCD timestamp string to datetime.
        
        Args:
            timestamp_str: ISO format timestamp from ArgoCD
            
        Returns:
            Parsed datetime object
        """
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.utcnow()
    
    def is_failure_event(self) -> bool:
        """
        Check if sync failed.
        
        Returns:
            True if sync failed or application is unhealthy
        """
        return (
            self.sync_status == "OutOfSync" or
            self.health_status in ["Degraded", "Missing"] or
            self.operation_state in ["Failed", "Error"]
        )
    
    def get_context(self) -> Dict[str, Any]:
        """
        Get context information for incident creation.
        
        Returns:
            Dictionary with ArgoCD context
        """
        return {
            "source": "argocd",
            "application": self.application_name,
            "service_name": self.service_name,
            "namespace": self.namespace,
            "project": self.project,
            "sync_status": self.sync_status,
            "health_status": self.health_status,
            "operation_state": self.operation_state,
            "revision": self.revision,
            "server_url": self.server_url,
            "sync_started_at": self.sync_started_at.isoformat() if self.sync_started_at else None,
            "sync_finished_at": self.sync_finished_at.isoformat() if self.sync_finished_at else None,
        }
    
    def get_summary(self) -> str:
        """
        Get human-readable summary.
        
        Returns:
            Summary string
        """
        status = "Success" if not self.is_failure_event() else "Failed"
        return (
            f"{status} ArgoCD app '{self.application_name}' "
            f"sync: {self.sync_status}, health: {self.health_status}"
        )
    