# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional, Annotated, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
import structlog
import time
import uuid

from app.dependencies import get_db
from app.adapters.database.postgres.repositories.incident import IncidentRepository
from app.adapters.database.postgres.repositories.jobs import JobRepository
from app.auth import get_current_active_user, require_admin
from app.core.schemas.incident import (
    IncidentResponse,
    IncidentDetail,
    IncidentListResponse,
    IncidentStats,
)
from app.core.schemas.search import (
    IncidentSearchRequest,
    PaginationMetadata,
    SearchSummary,
)
from app.core.schemas.jobs import JobResponse, JobType, JobStatus
from app.core.schemas.common import SuccessResponse, ErrorResponse
from app.core.enums import IncidentSource, Severity, Outcome, FailureType
from app.services.export import CSVExportService, PDFExportService

logger = structlog.get_logger()

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def get_incident_repository(db: Session = Depends(get_db)) -> IncidentRepository:
    """Get incident repository."""
    return IncidentRepository(db)


# List incidents for current user

@router.get(
    "",
    response_model=IncidentListResponse,
    summary="List user's incidents",
)
async def list_incidents(
    current_user: dict = Depends(get_current_active_user),
    incident_repo: IncidentRepository = Depends(get_incident_repository),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    source: Optional[IncidentSource] = Query(None, description="Filter by source"),
    severity: Optional[Severity] = Query(None, description="Filter by severity"),
    outcome: Optional[Outcome] = Query(None, description="Filter by outcome"),
    failure_type: Optional[FailureType] = Query(None, description="Filter by failure type"),
    start_date: Optional[datetime] = Query(None, description="Filter after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter before this date"),
    search: Optional[str] = Query(None, description="Search in error logs"),
):
    """
    List incidents for the current authenticated user.
    
    - Regular users see only their own incidents
    - Supports filtering by source, severity, outcome, failure type
    - Supports date range filtering
    - Supports search in error logs
    """
    user = current_user["user"]
    
    # Build filters
    filters = {}
    if source:
        filters["source"] = source.value
    if severity:
        filters["severity"] = severity.value
    if outcome:
        filters["outcome"] = outcome.value
    if failure_type:
        filters["failure_type"] = failure_type.value
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date
    if search:
        filters["search"] = search
    
    # Get user's incidents
    incidents, total = incident_repo.list_by_user(
        user_id=user.user_id,
        skip=skip,
        limit=limit,
        filters=filters,
    )
    
    return IncidentListResponse(
        incidents=[IncidentResponse.model_validate(inc) for inc in incidents],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(incidents)) < total,
    )


@router.post(
    "/search",
    summary="Advanced incident search",
    description="Enhanced search with full-text search, multi-select filters, and pagination",
)
async def advanced_search_incidents(
    search_request: IncidentSearchRequest = Body(...),
    request: Request = None,
    current_user: dict = Depends(get_current_active_user),
    incident_repo: IncidentRepository = Depends(get_incident_repository),
) -> Dict[str, Any]:
    """
    Advanced search for incidents with comprehensive filtering and pagination.

    Features:
    - Full-text search across error messages, logs, and stack traces
    - Multi-select filtering by source, severity, outcome, failure type
    - Tag-based filtering
    - Repository filtering
    - Confidence score range filtering
    - Date range filtering with presets (today, last_7_days, etc.)
    - Flexible sorting by multiple fields
    - Enhanced pagination with metadata and navigation URLs
    - Search performance metrics

    Example request body:
    ```json
    {
        "search_query": "timeout error",
        "sources": ["github_actions", "jenkins"],
        "severities": ["high", "critical"],
        "outcomes": ["success", "pending"],
        "tags": ["backend", "api"],
        "min_confidence": 0.7,
        "date_preset": "last_7_days",
        "sort_by": "created_at",
        "sort_order": "desc",
        "page": 1,
        "page_size": 20
    }
    ```
    """
    start_time = time.time()
    user = current_user["user"]

    # Calculate date range from preset if provided
    start_date = search_request.start_date
    end_date = search_request.end_date

    if search_request.date_preset:
        start_date, end_date = incident_repo.calculate_date_range(
            search_request.date_preset.value
        )

    # Perform advanced search
    incidents, total, next_cursor, previous_cursor = incident_repo.advanced_search(
        user_id=user.user_id,
        search_query=search_request.search_query,
        sources=search_request.sources,
        severities=search_request.severities,
        outcomes=search_request.outcomes,
        failure_types=search_request.failure_types,
        tags=search_request.tags,
        repository=search_request.repository,
        min_confidence=search_request.min_confidence,
        max_confidence=search_request.max_confidence,
        start_date=start_date,
        end_date=end_date,
        sort_by=search_request.sort_by.value,
        sort_order=search_request.sort_order.value,
        page=search_request.page,
        page_size=search_request.page_size,
        cursor=search_request.cursor,
    )

    # Build pagination metadata
    total_pages = (total + search_request.page_size - 1) // search_request.page_size
    has_previous = search_request.page > 1
    has_next = search_request.page < total_pages

    # Build navigation URLs
    base_url = str(request.base_url).rstrip("/") if request else ""
    base_path = f"{base_url}/api/v1/incidents/search"

    previous_url = None
    next_url = None
    first_url = None
    last_url = None

    if has_previous:
        previous_url = f"{base_path}?page={search_request.page - 1}&page_size={search_request.page_size}"
    if has_next:
        next_url = f"{base_path}?page={search_request.page + 1}&page_size={search_request.page_size}"
    if total_pages > 0:
        first_url = f"{base_path}?page=1&page_size={search_request.page_size}"
        last_url = f"{base_path}?page={total_pages}&page_size={search_request.page_size}"

    pagination = PaginationMetadata(
        current_page=search_request.page,
        page_size=search_request.page_size,
        total_items=total,
        total_pages=total_pages,
        has_previous=has_previous,
        has_next=has_next,
        previous_url=previous_url,
        next_url=next_url,
        first_url=first_url,
        last_url=last_url,
        next_cursor=next_cursor,
        previous_cursor=previous_cursor,
    )

    # Calculate search duration
    end_time = time.time()
    duration_ms = int((end_time - start_time) * 1000)

    # Build filters summary
    filters_applied = {}
    if search_request.search_query:
        filters_applied["search_query"] = search_request.search_query
    if search_request.sources:
        filters_applied["sources"] = [s.value for s in search_request.sources]
    if search_request.severities:
        filters_applied["severities"] = [s.value for s in search_request.severities]
    if search_request.outcomes:
        filters_applied["outcomes"] = [o.value for o in search_request.outcomes]
    if search_request.failure_types:
        filters_applied["failure_types"] = [f.value for f in search_request.failure_types]
    if search_request.tags:
        filters_applied["tags"] = search_request.tags
    if search_request.repository:
        filters_applied["repository"] = search_request.repository
    if search_request.min_confidence is not None:
        filters_applied["min_confidence"] = search_request.min_confidence
    if search_request.max_confidence is not None:
        filters_applied["max_confidence"] = search_request.max_confidence

    # Build date range info
    date_range = {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "preset": search_request.date_preset.value if search_request.date_preset else None,
    }

    summary = SearchSummary(
        total_results=total,
        filters_applied=filters_applied,
        search_duration_ms=duration_ms,
        date_range=date_range,
    )

    logger.info(
        "advanced_search_completed",
        user_id=user.user_id,
        total_results=total,
        page=search_request.page,
        duration_ms=duration_ms,
    )

    return {
        "success": True,
        "incidents": [IncidentResponse.model_validate(inc) for inc in incidents],
        "pagination": pagination,
        "summary": summary,
    }


@router.get(
    "/stats",
    response_model=IncidentStats,
    summary="Get user's incident statistics",
)
async def get_incident_stats(
    current_user: dict = Depends(get_current_active_user),
    incident_repo: IncidentRepository = Depends(get_incident_repository),
    start_date: Optional[datetime] = Query(None, description="Stats after this date"),
    end_date: Optional[datetime] = Query(None, description="Stats before this date"),
):
    """
    Get incident statistics for the current user.
    
    Includes:
    - Total incidents count
    - Breakdown by status (resolved, pending, failed, escalated)
    - Success rate
    - Average resolution time
    - Incidents by source, severity, failure type
    """
    user = current_user["user"]
    
    stats = incident_repo.get_user_stats(
        user_id=user.user_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return IncidentStats(**stats)


@router.get(
    "/export",
    summary="Export incidents",
    description="Export incidents to CSV or PDF format. For large exports, creates a background job.",
)
async def export_incidents(
    format: str = Query(..., description="Export format (csv or pdf)", pattern="^(csv|pdf)$"),
    current_user: dict = Depends(get_current_active_user),
    incident_repo: IncidentRepository = Depends(get_incident_repository),
    db: Session = Depends(get_db),
    source: Optional[IncidentSource] = Query(None),
    severity: Optional[Severity] = Query(None),
    outcome: Optional[Outcome] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000, description="Max incidents to export"),
):
    """
    Export incidents to CSV or PDF.

    - For small exports (<= 100 items): Returns file directly
    - For large exports (> 100 items): Creates background job and returns job ID

    Query parameters:
    - format: csv or pdf (required)
    - source, severity, outcome: Filter criteria
    - start_date, end_date: Date range
    - limit: Maximum incidents to export (1-1000)
    """
    user = current_user["user"]

    try:
        # Build filters
        filters = {}
        if source:
            filters["source"] = source.value
        if severity:
            filters["severity"] = severity.value
        if outcome:
            filters["outcome"] = outcome.value
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date

        # Get incidents
        incidents, total = incident_repo.list_by_user(
            user_id=user.user_id,
            skip=0,
            limit=limit,
            filters=filters,
        )

        if not incidents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No incidents found matching the criteria",
            )

        # For small exports, return file directly
        if len(incidents) <= 100:
            if format == "csv":
                csv_service = CSVExportService()
                csv_content = csv_service.export_to_string(incidents)

                return Response(
                    content=csv_content,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename=incidents_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    },
                )
            else:  # pdf
                pdf_service = PDFExportService()
                file_path, file_size = pdf_service.export_incidents(incidents)

                return FileResponse(
                    path=file_path,
                    media_type="application/pdf",
                    filename=f"incidents_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                )

        # For large exports, create background job
        else:
            job_repo = JobRepository(db)
            job_id = f"job_{uuid.uuid4().hex[:16]}"

            job = job_repo.create(
                job_id=job_id,
                user_id=user.user_id,
                job_type=JobType.EXPORT_CSV if format == "csv" else JobType.EXPORT_PDF,
                parameters={
                    "export_type": "incidents",
                    "format": format,
                    "filters": filters,
                    "limit": limit,
                    "total_incidents": total,
                },
            )

            logger.info(
                "export_job_created",
                job_id=job_id,
                format=format,
                user_id=user.user_id,
                total_incidents=total,
            )

            return {
                "success": True,
                "message": f"Export job created for {total} incidents",
                "job_id": job_id,
                "status_url": f"/api/v1/jobs/{job_id}",
                "estimated_time": "2-5 minutes",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("export_error", error=str(e), format=format)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}",
        )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetail,
    summary="Get incident details",
    responses={
        404: {"model": ErrorResponse, "description": "Incident not found"},
    },
)
async def get_incident(
    incident_id: str,
    current_user: dict = Depends(get_current_active_user),
    incident_repo: IncidentRepository = Depends(get_incident_repository),
):
    """
    Get detailed information about a specific incident.
    
    Users can only access their own incidents.
    Admins can access any incident.
    """
    user = current_user["user"]
    
    incident = incident_repo.get_by_id(incident_id)
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident not found: {incident_id}",
        )
    
    # Check ownership (admins can see all)
    if user.role != "admin" and incident.user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this incident",
        )
    
    return IncidentDetail.model_validate(incident)


# Admin endpoints

@router.get(
    "/admin/all",
    response_model=IncidentListResponse,
    summary="List all incidents (Admin)",
    dependencies=[Depends(require_admin)],
)
async def list_all_incidents(
    incident_repo: IncidentRepository = Depends(get_incident_repository),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    source: Optional[IncidentSource] = Query(None),
    severity: Optional[Severity] = Query(None),
    outcome: Optional[Outcome] = Query(None),
):
    """
    List all incidents across all users (Admin only).
    
    Supports filtering by user, source, severity, and outcome.
    """
    filters = {}
    if user_id:
        filters["user_id"] = user_id
    if source:
        filters["source"] = source.value
    if severity:
        filters["severity"] = severity.value
    if outcome:
        filters["outcome"] = outcome.value
    
    incidents, total = incident_repo.list_all(
        skip=skip,
        limit=limit,
        filters=filters,
    )
    
    return IncidentListResponse(
        incidents=[IncidentResponse.model_validate(inc) for inc in incidents],
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + len(incidents)) < total,
    )


@router.get(
    "/admin/stats",
    response_model=IncidentStats,
    summary="Get global incident statistics (Admin)",
    dependencies=[Depends(require_admin)],
)
async def get_global_stats(
    incident_repo: IncidentRepository = Depends(get_incident_repository),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    """Get incident statistics across all users (Admin only)."""
    stats = incident_repo.get_global_stats(
        start_date=start_date,
        end_date=end_date,
    )
    
    return IncidentStats(**stats)


@router.post(
    "/{incident_id}/assign",
    response_model=SuccessResponse,
    summary="Assign incident to user (Admin)",
    dependencies=[Depends(require_admin)],
)
async def assign_incident(
    incident_id: str,
    user_id: str,
    incident_repo: IncidentRepository = Depends(get_incident_repository),
):
    """Assign an incident to a specific user (Admin only)."""
    incident = incident_repo.get_by_id(incident_id)
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident not found: {incident_id}",
        )
    
    incident_repo.assign_to_user(incident_id, user_id)
    
    return SuccessResponse(
        success=True,
        message=f"Incident {incident_id} assigned to user {user_id}",
    )