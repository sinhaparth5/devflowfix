# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import IncidentSource, Severity, Outcome, FailureType

# Generic type for paginated responses
T = TypeVar('T')

class PaginationParams(BaseModel):
    """ Query parameters for pagination. """
    skip: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number or records to return")

    model_config = ConfigDict(extra="forbid")

class SortParams(BaseModel):
    """ Query parameters for sorting. """
    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order")

    model_config = ConfigDict(extra="forbid")

class FilterParams(BaseModel):
    """ Query parameters for filtering incidents """
    source: Optional[IncidentSource] = Field(None, description="Filter by source")
    severity: Optional[Severity] = Field(None, description="Filter by severity")
    outcome: Optional[Outcome] = Field(None, description="Filter by outcome")
    failure_type: Optional[FailureType] = Field(None, description="Filter by failure type")

    start_date: Optional[datetime] = Field(None, description="Filter incidents after this date")
    end_date: Optional[datetime] = Field(None, description="Filter incidents before this date")

    repository: Optional[str] = Field(None, description="Filter by repository")
    service: Optional[str] = Field(None, description="Filter by service name")
    namespace: Optional[str] = Field(None, description="Filter by namespace")

    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum confidence")
    max_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Maximum confidence")

    tags: Optional[list[str]] = Field(None, description="Filter by tags")
    search: Optional[str] = Field(None, description="Search in error logs")

    model_config = ConfigDict(extra="forbid")

class PaginatedResponse(BaseModel, Generic[T]):
    """ Generic paginated response. """
    items: list[T]
    total: int
    skip: int
    limit: int
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

class ErrorResponse(BaseModel):
    """ Standard error response. """
    error: str = Field(..., description="Error type or code")
    detail: str = Field(..., description="Detailed error message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    path: Optional[str] = Field(None, description="Request path that caused error")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")

class SuccessResponse(BaseModel):
    """ Standard success response. """
    success: bool = True
    message: str
    data: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class HealthResponse(BaseModel):
    """ Health check response. """
    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: Optional[str] = Field(None, description="Application version")
    uptime_seconds: Optional[int] = Field(None, description="Service uptime in seconds")
    
    # Component health
    database: Optional[str] = Field(None, description="Database connection status")
    nvidia_api: Optional[str] = Field(None, description="NVIDIA API status")
    cache: Optional[str] = Field(None, description="Cache status")

class MetricsResponse(BaseModel):
    """ Metrics response. """
    metric_name: str
    value: float
    unit: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    labels: dict = Field(default_factory=dict)

class TimeSeriesDataPoint(BaseModel):
    """ Single data point in time series. """    
    timestamp: datetime
    value: float
    labels: dict = Field(default_factory=dict)

class TimeSeriesResponse(BaseModel):
    """ Time series data response. """    
    metric_name: str
    data_points: list[TimeSeriesDataPoint]
    start_time: datetime
    end_time: datetime
    interval_seconds: int

class BulkOperationResponse(BaseModel):
    """ Response for bulk operations. """    
    total_requested: int
    successful: int
    failed: int
    errors: list[dict] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)

class ValidationError(BaseModel):
    """ Validation error details. """    
    field: str
    message: str
    value: Optional[any] = None

class ValidationErrorResponse(BaseModel):
    """ Response for validation errors. """    
    error: str = "validation_error"
    detail: str = "Request validation failed"
    errors: list[ValidationError]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class RateLimitResponse(BaseModel):
    """ Rate limit exceeded response. """    
    error: str = "rate_limit_exceeded"
    detail: str
    retry_after_seconds: int
    limit: int
    window_seconds: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class NotFoundResponse(BaseModel):
    """ Resource not found response. """
    error: str = "not_found"
    detail: str
    resource_type: str
    resource_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class SearchRequest(BaseModel):
    """ Search request parameters. """
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    filters: Optional[FilterParams] = None
    pagination: Optional[PaginationParams] = None
    sort: Optional[SortParams] = None

class SearchResponse(BaseModel, Generic[T]):
    """ Search results response. """    
    query: str
    results: list[T]
    total: int
    search_time_ms: int
    suggestions: list[str] = Field(default_factory=list, description="Search suggestions")
