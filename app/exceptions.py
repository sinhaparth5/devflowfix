# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Any

class DevFlowFixException(Exception):
    """
    Base exception for all DevFlowFix errors.
    
    All custom exceptions should inherit from this.
    """
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize exception.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            details: Additional error details
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }

class IncidentNotFoundError(DevFlowFixException):
    """Raised when an incident cannot be found."""
    def __init__(self, incident_id: str):
        super().__init__(
            message=f"Incident not found: {incident_id}",
            error_code="incident_not_found",
            details={"incident_id": incident_id},
        )


class IncidentAlreadyResolvedError(DevFlowFixException):
    """Raised when attempting to remediate an already resolved incident."""
    def __init__(self, incident_id: str):
        super().__init__(
            message=f"Incident already resolved: {incident_id}",
            error_code="incident_already_resolved",
            details={"incident_id": incident_id},
        )

class InvalidIncidentStateError(DevFlowFixException):
    """Raised when incident is in an invalid state for the requested operation."""
    def __init__(self, incident_id: str, current_state: str, expected_state: str):
        super().__init__(
            message=f"Incident {incident_id} is in state '{current_state}', expected '{expected_state}'",
            error_code="invalid_incident_state",
            details={
                "incident_id": incident_id,
                "current_state": current_state,
                "expected_state": expected_state,
            },
        )

class AnalysisFailedError(DevFlowFixException):
    """Raised when incident analysis fails."""
    def __init__(self, incident_id: str, reason: str):
        super().__init__(
            message=f"Analysis failed for incident {incident_id}: {reason}",
            error_code="analysis_failed",
            details={"incident_id": incident_id, "reason": reason},
        )

class ConfidenceTooLowError(DevFlowFixException):
    """Raised when confidence score is below threshold for auto-fix."""
    def __init__(self, incident_id: str, confidence: float, threshold: float):
        super().__init__(
            message=f"Confidence {confidence:.2f} below threshold {threshold:.2f} for incident {incident_id}",
            error_code="confidence_too_low",
            details={
                "incident_id": incident_id,
                "confidence": confidence,
                "threshold": threshold,
            },
        )

class NoSimilarIncidentsFoundError(DevFlowFixException):
    """Raised when no similar incidents found for RAG."""
    def __init__(self, incident_id: str):
        super().__init__(
            message=f"No similar incidents found for: {incident_id}",
            error_code="no_similar_incidents",
            details={"incident_id": incident_id},
        )

class RemediationFailedError(DevFlowFixException):
    """Raised when remediation execution fails."""
    def __init__(
        self,
        incident_id: str,
        action_type: str,
        reason: str,
        recoverable: bool = True,
    ):
        super().__init__(
            message=f"Remediation failed for incident {incident_id}: {reason}",
            error_code="remediation_failed",
            details={
                "incident_id": incident_id,
                "action_type": action_type,
                "reason": reason,
                "recoverable": recoverable,
            },
        )

class RemediationTimeoutError(DevFlowFixException):
    """Raised when remediation exceeds timeout."""
    def __init__(self, incident_id: str, timeout_seconds: int):
        super().__init__(
            message=f"Remediation timed out after {timeout_seconds}s for incident {incident_id}",
            error_code="remediation_timeout",
            details={
                "incident_id": incident_id,
                "timeout_seconds": timeout_seconds,
            },
        )

class ValidationFailedError(DevFlowFixException):
    """Raised when pre/post validation fails."""
    def __init__(
        self,
        incident_id: str,
        validation_type: str,
        failures: list[str],
    ):
        super().__init__(
            message=f"{validation_type} validation failed for incident {incident_id}",
            error_code="validation_failed",
            details={
                "incident_id": incident_id,
                "validation_type": validation_type,
                "failures": failures,
            },
        )

class RollbackFailedError(DevFlowFixException):
    """Raised when rollback operation fails."""
    def __init__(self, incident_id: str, snapshot_id: str, reason: str):
        super().__init__(
            message=f"Rollback failed for incident {incident_id}: {reason}",
            error_code="rollback_failed",
            details={
                "incident_id": incident_id,
                "snapshot_id": snapshot_id,
                "reason": reason,
            },
        )

class NoRemediationPlanError(DevFlowFixException):
    """Raised when no remediation plan can be generated."""
    def __init__(self, incident_id: str, reason: str):
        super().__init__(
            message=f"Cannot generate remediation plan for incident {incident_id}: {reason}",
            error_code="no_remediation_plan",
            details={
                "incident_id": incident_id,
                "reason": reason,
            },
        )

class ApprovalRequiredError(DevFlowFixException):
    """Raised when human approval is required but not provided."""
    def __init__(self, incident_id: str, reason: str):
        super().__init__(
            message=f"Approval required for incident {incident_id}: {reason}",
            error_code="approval_required",
            details={
                "incident_id": incident_id,
                "reason": reason,
            },
        )

class ApprovalTimeoutError(DevFlowFixException):
    """Raised when approval request times out."""
    
    def __init__(self, incident_id: str, timeout_minutes: int):
        super().__init__(
            message=f"Approval timed out after {timeout_minutes} minutes for incident {incident_id}",
            error_code="approval_timeout",
            details={
                "incident_id": incident_id,
                "timeout_minutes": timeout_minutes,
            },
        )

class ApprovalRejectedError(DevFlowFixException):
    """Raised when remediation is rejected by approver."""
    def __init__(self, incident_id: str, approver: str, reason: Optional[str] = None):
        super().__init__(
            message=f"Remediation rejected by {approver} for incident {incident_id}",
            error_code="approval_rejected",
            details={
                "incident_id": incident_id,
                "approver": approver,
                "reason": reason,
            },
        )
class RateLimitExceededError(DevFlowFixException):
    """ Raised when rate limit is exceeded. """
    def __init__(
        self,
        resource: str,
        limit: int,
        window_seconds: int,
        retry_after: int,
    ):
        super().__init__(
            message=f"Rate limit exceeded for {resource}: {limit} requests per {window_seconds}s",
            error_code="rate_limit_exceeded",
            details={
                "resource": resource,
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after": retry_after,
            },
        )

class BlastRadiusExceededError(DevFlowFixException):
    """Raised when blast radius limit is exceeded."""
    def __init__(
        self,
        service: str,
        current_count: int,
        limit: int,
        time_window: str,
    ):
        super().__init__(
            message=f"Blast radius exceeded for {service}: {current_count}/{limit} in {time_window}",
            error_code="blast_radius_exceeded",
            details={
                "service": service,
                "current_count": current_count,
                "limit": limit,
                "time_window": time_window,
            },
        )

class ExternalServiceError(DevFlowFixException):
    """Base exception for external service errors."""
    def __init__(self, service: str, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=f"{service} error: {message}",
            error_code=f"{service.lower()}_error",
            details={
                "service": service,
                "status_code": status_code,
            },
        )

class GitHubAPIError(ExternalServiceError):
    """Raised when GitHub API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__("GitHub", message, status_code)

class ArgoCDAPIError(ExternalServiceError):
    """Raised when ArgoCD API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__("ArgoCD", message, status_code)

class KubernetesAPIError(ExternalServiceError):
    """Raised when Kubernetes API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__("Kubernetes", message, status_code)

class SlackAPIError(ExternalServiceError):
    """Raised when Slack API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__("Slack", message, status_code)

class NVIDIAAPIError(ExternalServiceError):
    """Raised when NVIDIA API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__("NVIDIA", message, status_code)

class PagerDutyAPIError(ExternalServiceError):
    """Raised when PagerDuty API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__("PagerDuty", message, status_code)

class DatabaseError(DevFlowFixException):
    """Raised when database operation fails."""
    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Database {operation} failed: {reason}",
            error_code="database_error",
            details={
                "operation": operation,
                "reason": reason,
            },
        )

class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    def __init__(self, reason: str):
        super().__init__("connection", reason)

class ConfigurationError(DevFlowFixException):
    """Raised when configuration is invalid or missing."""
    def __init__(self, setting: str, reason: str):
        super().__init__(
            message=f"Configuration error for '{setting}': {reason}",
            error_code="configuration_error",
            details={
                "setting": setting,
                "reason": reason,
            },
        )

class MissingCredentialsError(ConfigurationError):
    """Raised when required credentials are missing."""
    def __init__(self, credential: str):
        super().__init__(
            credential,
            f"Required credential '{credential}' is not configured",
        )

class WebhookValidationError(DevFlowFixException):
    """Raised when webhook signature validation fails."""
    def __init__(self, source: str, reason: str):
        super().__init__(
            message=f"Webhook validation failed for {source}: {reason}",
            error_code="webhook_validation_failed",
            details={
                "source": source,
                "reason": reason,
            },
        )

class UnsupportedWebhookEventError(DevFlowFixException):
    """Raised when webhook event type is not supported."""
    def __init__(self, source: str, event_type: str):
        super().__init__(
            message=f"Unsupported webhook event from {source}: {event_type}",
            error_code="unsupported_webhook_event",
            details={
                "source": source,
                "event_type": event_type,
            },
        )