# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Enhanced search and filtering schemas.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field

from app.core.enums import IncidentSource, Severity, Outcome, FailureType


class DateRangePreset(str, Enum):
    """Predefined date range presets for quick filtering."""
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"


class SortOrder(str, Enum):
    """Sort order for search results."""
    ASC = "asc"
    DESC = "desc"


class IncidentSortField(str, Enum):
    """Fields available for sorting incidents."""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    SEVERITY = "severity"
    CONFIDENCE = "confidence"
    RESOLUTION_TIME = "resolution_time_seconds"


class IncidentSearchRequest(BaseModel):
    """Enhanced search request for incidents."""

    # Full-text search
    search_query: Optional[str] = Field(
        None,
        description="Full-text search across error messages, logs, and stack traces"
    )

    # Date filtering
    date_preset: Optional[DateRangePreset] = Field(
        None,
        description="Predefined date range preset"
    )
    start_date: Optional[datetime] = Field(
        None,
        description="Custom start date (overrides preset)"
    )
    end_date: Optional[datetime] = Field(
        None,
        description="Custom end date (overrides preset)"
    )

    # Multi-select filters (OR condition within same filter)
    sources: Optional[List[IncidentSource]] = Field(
        None,
        description="Filter by multiple sources (OR)"
    )
    severities: Optional[List[Severity]] = Field(
        None,
        description="Filter by multiple severities (OR)"
    )
    outcomes: Optional[List[Outcome]] = Field(
        None,
        description="Filter by multiple outcomes (OR)"
    )
    failure_types: Optional[List[FailureType]] = Field(
        None,
        description="Filter by multiple failure types (OR)"
    )

    # Tags filtering
    tags: Optional[List[str]] = Field(
        None,
        description="Filter by tags (OR)"
    )

    # Repository filtering
    repository: Optional[str] = Field(
        None,
        description="Filter by repository name"
    )

    # Confidence range
    min_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score"
    )
    max_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Maximum confidence score"
    )

    # Sorting
    sort_by: IncidentSortField = Field(
        IncidentSortField.CREATED_AT,
        description="Field to sort by"
    )
    sort_order: SortOrder = Field(
        SortOrder.DESC,
        description="Sort order"
    )

    # Pagination
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")

    # Cursor-based pagination (alternative to page)
    cursor: Optional[str] = Field(
        None,
        description="Cursor for pagination (base64 encoded)"
    )


class PaginationMetadata(BaseModel):
    """Enhanced pagination metadata."""

    current_page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_items: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_previous: bool = Field(..., description="Whether there's a previous page")
    has_next: bool = Field(..., description="Whether there's a next page")

    # URLs for navigation
    previous_url: Optional[str] = Field(None, description="URL for previous page")
    next_url: Optional[str] = Field(None, description="URL for next page")
    first_url: Optional[str] = Field(None, description="URL for first page")
    last_url: Optional[str] = Field(None, description="URL for last page")

    # Cursor-based pagination
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
    previous_cursor: Optional[str] = Field(None, description="Cursor for previous page")


class SearchSummary(BaseModel):
    """Summary of search results."""

    total_results: int = Field(..., description="Total matching results")
    filters_applied: dict = Field(..., description="Filters that were applied")
    search_duration_ms: int = Field(..., description="Search execution time in milliseconds")
    date_range: dict = Field(..., description="Effective date range used")
