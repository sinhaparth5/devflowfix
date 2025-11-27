# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
import structlog

from app.dependencies import get_db, get_analytics_repository
from app.adapters.database.postgres.repositories.analytics import AnalyticsRepository
from app.core.enums import IncidentSource, Severity, Outcome

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/dashboard",
    summary="Get dashboard summary",
    description="Get comprehensive dashboard data including today, week, and month stats",
)
async def get_dashboard(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_dashboard_summary()
    except Exception as e:
        logger.error("get_dashboard_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard data",
        )


@router.get(
    "/stats",
    summary="Get incident statistics",
    description="Get incident counts and success rates with optional date filtering",
)
async def get_stats(
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    source: Optional[str] = Query(None, description="Filter by source"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    analytics_repo = AnalyticsRepository(db)
    
    source_enum = None
    if source:
        try:
            source_enum = IncidentSource(source)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source: {source}",
            )
    
    try:
        return analytics_repo.get_incident_stats(
            start_date=start_date,
            end_date=end_date,
            source=source_enum,
        )
    except Exception as e:
        logger.error("get_stats_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics",
        )


@router.get(
    "/breakdown/source",
    summary="Get incidents by source",
    description="Get incident count breakdown by source platform",
)
async def get_breakdown_by_source(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_incidents_by_source(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_breakdown_by_source_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve source breakdown",
        )


@router.get(
    "/breakdown/severity",
    summary="Get incidents by severity",
    description="Get incident count breakdown by severity level",
)
async def get_breakdown_by_severity(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_incidents_by_severity(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_breakdown_by_severity_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve severity breakdown",
        )


@router.get(
    "/breakdown/failure-type",
    summary="Get incidents by failure type",
    description="Get incident count breakdown by failure type",
)
async def get_breakdown_by_failure_type(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_incidents_by_failure_type(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_breakdown_by_failure_type_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve failure type breakdown",
        )


@router.get(
    "/breakdown/outcome",
    summary="Get incidents by outcome",
    description="Get incident count breakdown by outcome status",
)
async def get_breakdown_by_outcome(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_incidents_by_outcome(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_breakdown_by_outcome_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve outcome breakdown",
        )


@router.get(
    "/trends",
    summary="Get incident trends",
    description="Get incident trends over time with configurable granularity",
)
async def get_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    granularity: str = Query("day", regex="^(hour|day|week)$", description="Time granularity"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_incident_trends(
            days=days,
            granularity=granularity,
        )
    except Exception as e:
        logger.error("get_trends_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trends",
        )


@router.get(
    "/mttr",
    summary="Get Mean Time To Repair",
    description="Get MTTR statistics including average, min, max, median, and p95",
)
async def get_mttr(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    analytics_repo = AnalyticsRepository(db)
    
    source_enum = None
    if source:
        try:
            source_enum = IncidentSource(source)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source: {source}",
            )
    
    try:
        return analytics_repo.get_mttr(
            start_date=start_date,
            end_date=end_date,
            source=source_enum,
        )
    except Exception as e:
        logger.error("get_mttr_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve MTTR",
        )


@router.get(
    "/auto-fix-rate",
    summary="Get auto-fix rate",
    description="Get auto-fix vs escalation rate statistics",
)
async def get_auto_fix_rate(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_auto_fix_rate(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_auto_fix_rate_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve auto-fix rate",
        )


@router.get(
    "/confidence-distribution",
    summary="Get confidence score distribution",
    description="Get distribution of AI confidence scores across incidents",
)
async def get_confidence_distribution(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_confidence_distribution(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_confidence_distribution_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve confidence distribution",
        )


@router.get(
    "/remediation-success",
    summary="Get remediation success by action type",
    description="Get success rates for each remediation action type",
)
async def get_remediation_success(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_remediation_success_by_action_type(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_remediation_success_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve remediation success rates",
        )


@router.get(
    "/feedback",
    summary="Get feedback summary",
    description="Get summary of user feedback on remediations",
)
async def get_feedback_summary(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_feedback_summary(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_feedback_summary_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feedback summary",
        )


@router.get(
    "/top/failure-types",
    summary="Get top failure types",
    description="Get most common failure types",
)
async def get_top_failure_types(
    limit: int = Query(10, ge=1, le=50),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_top_failure_types(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_top_failure_types_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve top failure types",
        )


@router.get(
    "/top/repositories",
    summary="Get top repositories",
    description="Get repositories with most incidents",
)
async def get_top_repositories(
    limit: int = Query(10, ge=1, le=50),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_top_repositories(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("get_top_repositories_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve top repositories",
        )


@router.get(
    "/distribution/hourly",
    summary="Get hourly distribution",
    description="Get incident count by hour of day",
)
async def get_hourly_distribution(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[int, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_hourly_distribution(days=days)
    except Exception as e:
        logger.error("get_hourly_distribution_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve hourly distribution",
        )


@router.get(
    "/distribution/daily",
    summary="Get daily distribution",
    description="Get incident count by day of week",
)
async def get_daily_distribution(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    analytics_repo = AnalyticsRepository(db)
    
    try:
        return analytics_repo.get_daily_distribution(days=days)
    except Exception as e:
        logger.error("get_daily_distribution_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve daily distribution",
        )


@router.get(
    "/overview",
    summary="Get analytics overview",
    description="Get a comprehensive overview for the frontend dashboard",
)
async def get_analytics_overview(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    analytics_repo = AnalyticsRepository(db)
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    try:
        stats = analytics_repo.get_incident_stats(start_date=start_date)
        by_source = analytics_repo.get_incidents_by_source(start_date=start_date)
        by_severity = analytics_repo.get_incidents_by_severity(start_date=start_date)
        by_outcome = analytics_repo.get_incidents_by_outcome(start_date=start_date)
        trends = analytics_repo.get_incident_trends(days=days, granularity="day")
        mttr = analytics_repo.get_mttr(start_date=start_date)
        auto_fix = analytics_repo.get_auto_fix_rate(start_date=start_date)
        top_failures = analytics_repo.get_top_failure_types(limit=5, start_date=start_date)
        hourly = analytics_repo.get_hourly_distribution(days=days)
        
        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": datetime.now(timezone.utc).isoformat(),
                "days": days,
            },
            "summary": stats,
            "breakdown": {
                "by_source": by_source,
                "by_severity": by_severity,
                "by_outcome": by_outcome,
            },
            "trends": trends,
            "performance": {
                "mttr": mttr,
                "auto_fix_rate": auto_fix,
            },
            "top_failure_types": top_failures,
            "hourly_distribution": hourly,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error("get_analytics_overview_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics overview",
        )