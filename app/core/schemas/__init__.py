# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

# Webhook schemas
from app.core.schemas.webhook import (
    WebhookPayload,
    WebhookResponse,
    GitHubWebhookPayload,
    ArgoCDWebhookPayload,
    KubernetesWebhookPayload,
)

# Incident schemas
from app.core.schemas.incident import (
    IncidentBase,
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    IncidentDetail,
    IncidentListResponse,
    IncidentStats,
)

# Analysis schemas
from app.core.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisDetailResponse,
    ConfidenceBreakdown,
    SimilarIncident,
)

# Approval schemas
from app.core.schemas.approval import (
    ApprovalRequest,
    ApprovalResponse,
    PendingApproval,
    PendingApprovalsList,
    ApprovalDecision,
    BulkApprovalRequest,
    BulkApprovalResponse,
)

# Remediation schemas
from app.core.schemas.remediation import (
    RemediationRequest,
    RemediationPlanResponse,
    RemediationResponse,
    RemediationStatusResponse,
    RollbackRequest,
    RollbackResponse,
    ValidationResult,
    RemediationHistoryItem,
    RemediationHistoryResponse,
)

# Common schemas
from app.core.schemas.common import (
    PaginationParams,
    SortParams,
    FilterParams,
    PaginatedResponse,
    ErrorResponse,
    SuccessResponse,
    HealthResponse,
    MetricsResponse,
    TimeSeriesDataPoint,
    TimeSeriesResponse,
    BulkOperationResponse,
    ValidationError,
    ValidationErrorResponse,
    RateLimitResponse,
    NotFoundResponse,
    SearchRequest,
    SearchResponse,
)

__all__ = [
    # Webhook
    "WebhookPayload",
    "WebhookResponse",
    "GitHubWebhookPayload",
    "ArgoCDWebhookPayload",
    "KubernetesWebhookPayload",
    
    # Incident
    "IncidentBase",
    "IncidentCreate",
    "IncidentUpdate",
    "IncidentResponse",
    "IncidentDetail",
    "IncidentListResponse",
    "IncidentStats",
    
    # Analysis
    "AnalysisRequest",
    "AnalysisResponse",
    "AnalysisDetailResponse",
    "ConfidenceBreakdown",
    "SimilarIncident",
    
    # Approval
    "ApprovalRequest",
    "ApprovalResponse",
    "PendingApproval",
    "PendingApprovalsList",
    "ApprovalDecision",
    "BulkApprovalRequest",
    "BulkApprovalResponse",
    
    # Remediation
    "RemediationRequest",
    "RemediationPlanResponse",
    "RemediationResponse",
    "RemediationStatusResponse",
    "RollbackRequest",
    "RollbackResponse",
    "ValidationResult",
    "RemediationHistoryItem",
    "RemediationHistoryResponse",
    
    # Common
    "PaginationParams",
    "SortParams",
    "FilterParams",
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
    "HealthResponse",
    "MetricsResponse",
    "TimeSeriesDataPoint",
    "TimeSeriesResponse",
    "BulkOperationResponse",
    "ValidationError",
    "ValidationErrorResponse",
    "RateLimitResponse",
    "NotFoundResponse",
    "SearchRequest",
    "SearchResponse",
]