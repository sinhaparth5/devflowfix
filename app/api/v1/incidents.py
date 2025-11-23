# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog

from app.dependencies import get_db
from app.adapters.database.postgres.repositories.incident import IncidentRepository
from app.api.v1.auth import get_current_active_user, require_admin
from app.core.schemas.incident import (
    IncidentResponse,
    IncidentDetail,
    IncidentListResponse,
    IncidentStats,
)
from app.core.schemas.common import SuccessResponse, ErrorResponse
from app.core.enums import IncidentSource, Severity, Outcome, FailureType

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