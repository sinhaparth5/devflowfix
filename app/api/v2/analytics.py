# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Analytics API Endpoints

Provides metrics, trends, and dashboard data.
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog

from app.core.schemas.analytics import (
    WorkflowTrendResponse,
    RepositoryHealthMetrics,
    RepositoryHealthListResponse,
    IncidentTrendResponse,
    SystemHealthResponse,
    DashboardSummaryResponse,
)
from app.dependencies import get_db
from app.auth import get_current_active_user
from app.services.analytics.analytics_service import AnalyticsService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_analytics_service() -> AnalyticsService:
    """
    Get analytics service instance.

    Returns:
        AnalyticsService instance
    """
    return AnalyticsService()


@router.get(
    "/workflows/trends",
    response_model=WorkflowTrendResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Workflow Trends",
    description="Get workflow success/failure trends over time.",
)
async def get_workflow_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    period: str = Query("day", description="Aggregation period (hour, day, week, month)"),
    repository_connection_id: Optional[str] = Query(None, description="Filter by repository"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> WorkflowTrendResponse:
    """
    Get workflow trends over time.

    **Query Parameters:**
    - days: Number of days to analyze (default: 30, max: 365)
    - period: Aggregation period - hour, day, week, month (default: day)
    - repository_connection_id: Optional repository filter

    **Returns:**
    - Time series data for total runs, successful runs, failed runs
    - Failure rate and average duration over time
    - Summary statistics
    """
    try:
        user = current_user_data["user"]
        service = get_analytics_service()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        trends = await service.get_workflow_trends(
            db=db,
            user_id=user.user_id,
            start_date=start_date,
            end_date=end_date,
            period=period,
            repository_connection_id=repository_connection_id,
        )

        return WorkflowTrendResponse(**trends)

    except Exception as e:
        logger.error(
            "get_workflow_trends_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workflow trends: {str(e)}"
        )


@router.get(
    "/repositories/health",
    response_model=RepositoryHealthListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Repository Health Metrics",
    description="Get health metrics for all monitored repositories.",
)
async def get_repository_health(
    repository_connection_id: Optional[str] = Query(None, description="Filter by repository"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RepositoryHealthListResponse:
    """
    Get repository health metrics.

    **Query Parameters:**
    - repository_connection_id: Optional filter for specific repository

    **Returns:**
    - Health metrics for each repository
    - Workflow statistics, incident counts, PR metrics
    - Overall health score (0-100)
    - Average health score across all repositories
    """
    try:
        user = current_user_data["user"]
        service = get_analytics_service()

        health_metrics = await service.get_repository_health_metrics(
            db=db,
            user_id=user.user_id,
            repository_connection_id=repository_connection_id,
        )

        # Convert to Pydantic models
        repositories = [RepositoryHealthMetrics(**metrics) for metrics in health_metrics]

        # Calculate average health score
        avg_health_score = (
            sum(r.health_score for r in repositories) / len(repositories)
            if repositories else 0.0
        )

        return RepositoryHealthListResponse(
            repositories=repositories,
            total_repositories=len(repositories),
            avg_health_score=avg_health_score,
        )

    except Exception as e:
        logger.error(
            "get_repository_health_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch repository health: {str(e)}"
        )


@router.get(
    "/incidents/trends",
    response_model=IncidentTrendResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Incident Trends",
    description="Get incident creation and resolution trends over time.",
)
async def get_incident_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    period: str = Query("day", description="Aggregation period"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> IncidentTrendResponse:
    """
    Get incident trends over time.

    **Query Parameters:**
    - days: Number of days to analyze (default: 30, max: 365)
    - period: Aggregation period (default: day)

    **Returns:**
    - Incidents created/resolved over time
    - Open incidents trend
    - Distribution by severity and source
    - Resolution statistics
    """
    try:
        user = current_user_data["user"]
        service = get_analytics_service()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        trends = await service.get_incident_trends(
            db=db,
            user_id=user.user_id,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )

        return IncidentTrendResponse(**trends)

    except Exception as e:
        logger.error(
            "get_incident_trends_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch incident trends: {str(e)}"
        )


@router.get(
    "/system/health",
    response_model=SystemHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get System Health",
    description="Get overall system health and status.",
)
async def get_system_health(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> SystemHealthResponse:
    """
    Get overall system health.

    **Returns:**
    - System status (healthy, degraded, unhealthy)
    - Overall health score
    - Resource counts (repositories, workflows, incidents, PRs)
    - OAuth connection status
    - Webhook health
    - Last 24h activity
    - System alerts
    """
    try:
        user = current_user_data["user"]
        service = get_analytics_service()

        health = await service.get_system_health(
            db=db,
            user_id=user.user_id,
        )

        return SystemHealthResponse(**health)

    except Exception as e:
        logger.error(
            "get_system_health_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch system health: {str(e)}"
        )


@router.get(
    "/dashboard",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Dashboard Summary",
    description="Get comprehensive dashboard summary with all key metrics.",
)
async def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> DashboardSummaryResponse:
    """
    Get dashboard summary with all key metrics.

    **Returns:**
    - System health overview
    - Workflow statistics
    - Incident statistics
    - PR statistics
    - Top repositories by activity
    - Recent failures and fixes
    """
    try:
        user = current_user_data["user"]
        service = get_analytics_service()

        # Get system health
        system_health = await service.get_system_health(
            db=db,
            user_id=user.user_id,
        )

        # Get workflow trends for last 7 days
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)

        workflow_trends = await service.get_workflow_trends(
            db=db,
            user_id=user.user_id,
            start_date=start_date,
            end_date=end_date,
            period="day",
        )

        # Get incident trends
        incident_trends = await service.get_incident_trends(
            db=db,
            user_id=user.user_id,
            start_date=start_date,
            end_date=end_date,
            period="day",
        )

        # Get repository health
        repo_health = await service.get_repository_health_metrics(
            db=db,
            user_id=user.user_id,
        )

        # Sort by health score to get top repositories
        top_repositories = sorted(
            repo_health,
            key=lambda x: x["health_score"],
            reverse=True,
        )[:5]

        return DashboardSummaryResponse(
            system_health=SystemHealthResponse(**system_health),
            workflow_stats=workflow_trends["summary"],
            incident_stats=incident_trends["summary"],
            pr_stats={
                "total_prs": 0,
                "merged_prs": 0,
                "merge_rate": 0.0,
            },
            top_repositories=[RepositoryHealthMetrics(**r) for r in top_repositories],
            recent_failures=[],
            recent_fixes=[],
            generated_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(
            "get_dashboard_summary_error",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dashboard summary: {str(e)}"
        )
