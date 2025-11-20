# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid5

from app.core.enums import (
    IncidentSource,
    Severity,
    Outcome,
    Fixability,
    FailureType
)

@dataclass
class Incident:
    """
    Core domain entity represneting a CI/CD failure incident.

    This is a domain model, not a database model. It contains business logic
    and is independent of infrastructure concerns.
    """
    incident_id: str = field(default_factory=lambda: f"inc_{uuid5().hex[:12]}")

    timestamp: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    source: IncidentSource = IncidentSource.MANUAL
    severity: Severity = Severity.MEDIUM

    failure_type: Optional[FailureType] = None
    error_log: str = ""
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None

    context: dict = field(default_factory=dict)

    root_cause: Optional[str] = None
    fixability: Optional[Fixability] = None
    confidence: Optional[float] = None

    similar_incidents: list = field(default_factory=list)

    remediation_plan: Optional[dict] = None
    remediation_executed: bool = False
    remediation_start_time: Optional[datetime] = None
    remediation_end_time: Optional[datetime] = None

    outcome: Optional[Outcome] = None
    outcome_message: Optional[str] = None
    resolution_time_seconds: Optional[int] = None

    human_feedback: Optional[dict] = None
    approved_by: Optional[str] = None
    approved_timestamp: Optional[datetime] = None

    raw_payload: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def is_resolved(self) -> bool:
        """ Check if incident has resolved successfully """
        return self.outcome == Outcome.SUCCESS
    
    def is_failed(self) -> bool:
        """ Check if remediation attempt failed. """
        return self.outcome == Outcome.FAILED
    
    def is_pending(self) -> bool:
        """ Check if incident is still pending processing """
        return self.outcome in [Outcome.PENDING, None]
    
    def is_escalated(self) -> bool:
        """ Check if incident was escalated to humans. """
        return self.outcome == Outcome.ESCALATED
    
    def requires_human_intervention(self) -> bool:
        """ Check if incident needs human review. """
        return (
            self.fixability == Fixability.MANUAL
            or self.is_escalated()
            or (self.confidence is not None and self.confidence < 0.85)
        )
    
    def calculate_duration(self) -> int:
        """
        Calculate incident duration in seconds

        Returns:
            Duration form creation to resolution (or now if unresolved)
        """
        if self.resolution_time_seconds is not None:
            return self.resolution_time_seconds
        
        if self.resolved_at:
            end_time = self.resolved_at
        else:
            end_time = datetime.utcnow()

        duration = int(end_time - self.timestamp).total_seconds()
        return max(0, duration)
    
    def calculate_remediation_duration(self) -> Optional[int]:
        """
        Calculate remediation execution time in seconds

        Returns:
            Duration of remediation execution, or None if not executed
        """
        if not self.remediation_start_time or not self.remediation_end_time:
            return None
        
        duration = int(
            (self.remediation_end_time - self.remediation_start_time).total_seconds()
        )
        return max(0, duration)
    
    def mark_resolved(self, outcome: Outcome, message: Optional[str] = None) -> None:
        """
        Mark incident as resolved with outcome.

        Args:
            outcome: Final outcome of the incident
            message: Optional message explaining the outcome
        """
        self.outcome = outcome
        self.outcome_message = message
        self.resolved_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.resolution_time_seconds = self.calculate_duration()

    def start_remediation(self) -> None:
        """ Mark the start of remediation execution """
        self.remediation_start_time = datetime.utcnow()
        self.remediation_executed = True
        self.updated_at = datetime.utcnow()

    def end_remediation(self, success: bool, message: Optional[str] = None) -> None:
        """
        Mark then end of remediation execution

        Args:
            success: Whether remediaiton succeeded
            message: Optional message about the outcome
        """
        self.remediation_end_time = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        if success:
            self.mark_resolved(Outcome.SUCCESS, message)
        else:
            self.mark_resolved(Outcome.FAILED, message)

    def add_feedback(
            self,
            helpful: bool,
            comment: Optional[str] = None,
            user: Optional[str] = None
    ) -> None:
        """
        Add human feedback about the remediation.

        Args: 
            helpful: Whether the remediation was helpful
            comment: Optional comment from the user
            user: User who provided feedback
        """
        self.human_feedback = {
            "helpful": helpful,
            "comment": comment,
            "user": user,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.updated_at = datetime.utcnow()

    def add_approval(self, approver: str) -> None:
        """
        Record human approval for remediation
        Args:
            approver: Username/email of person who approved
        """
        self.approved_by = approver
        self.approved_timestamp = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def add_tag(self, tag: str) -> None:
        """ Add a tag to the incident """
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.utcnow()

    def remove_tag(self, tag: str) -> None:
        """ Remove a tag from the incident. """
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.utcnow()

    def get_service_name(self) -> Optional[str]:
        """ Extract service name from context """
        return self.context.get("service") or self.context.get("app_name")
    
    def get_namespace(self) -> Optional[str]:
        """ Extract namespace from context (for k8s incidents) """
        return self.context.get("namespace")
    
    def get_repository(self) -> Optional[str]:
        """ Extract repository from context (for GitHub incident) """
        return self.context.get("repository")
    
    def get_branch(self)-> Optional[str]:
        """ Extract branch name from the context """
        return self.context.get("branch")
    
    def to_dict(self) -> dict:
        """ Convert incident to dictoionary """
        return {
            "incident_id": self.incident_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source.value if self.source else None,
            "severity": self.severity.value if self.severity else None,
            "failure_type": self.failure_type.value if self.failure_type else None,
            "error_log": self.error_log,
            "root_cause": self.root_cause,
            "fixability": self.fixability.value if self.fixability else None,
            "confidence": self.confidence,
            "outcome": self.outcome.value if self.outcome else None,
            "resolution_time_seconds": self.resolution_time_seconds,
            "context": self.context,
            "tags": self.tags,
        }
    
    def __repr__(self) -> str:
        """ String representation of incident. """
        return (
            f"Incident(id={self.incident_id}, "
            f"source={self.source.value}, "
            f"severity={self.severity.value}, "
            f"outcome={self.outcome.value if self.outcome else 'pending'}"
        )