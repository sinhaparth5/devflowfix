# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, desc, and_, or_, case, text, cast, String
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import (
    IncidentTable,
    FeedbackTable,
    RemediationHistoryTable,
    MetricTable,
)
from app.core.enums import IncidentSource, Severity, Outcome, FailureType

logger = structlog.get_logger(__name__)


class AnalyticsRepository:
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_incident_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        source: Optional[IncidentSource] = None,
    ) -> Dict[str, Any]:
        try:
            query = self.session.query(IncidentTable)
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            if source:
                query = query.filter(IncidentTable.source == source.value)
            
            total = query.count()
            
            resolved = query.filter(IncidentTable.outcome == Outcome.SUCCESS.value).count()
            failed = query.filter(IncidentTable.outcome == Outcome.FAILED.value).count()
            pending = query.filter(
                or_(
                    IncidentTable.outcome == Outcome.PENDING.value,
                    IncidentTable.outcome.is_(None)
                )
            ).count()
            escalated = query.filter(IncidentTable.outcome == Outcome.ESCALATED.value).count()
            rolled_back = query.filter(IncidentTable.outcome == Outcome.ROLLED_BACK.value).count()
            
            success_rate = (resolved / total * 100) if total > 0 else 0.0
            
            avg_resolution = self.session.query(
                func.avg(IncidentTable.resolution_time_seconds)
            ).filter(
                IncidentTable.outcome == Outcome.SUCCESS.value
            )
            if start_date:
                avg_resolution = avg_resolution.filter(IncidentTable.created_at >= start_date)
            if end_date:
                avg_resolution = avg_resolution.filter(IncidentTable.created_at <= end_date)
            avg_resolution_time = avg_resolution.scalar()
            
            return {
                "total_incidents": total,
                "resolved_incidents": resolved,
                "failed_incidents": failed,
                "pending_incidents": pending,
                "escalated_incidents": escalated,
                "rolled_back_incidents": rolled_back,
                "success_rate": round(success_rate, 2),
                "average_resolution_time_seconds": round(avg_resolution_time, 2) if avg_resolution_time else None,
            }
            
        except Exception as e:
            logger.error("get_incident_stats_failed", error=str(e))
            raise
    
    def get_incidents_by_source(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        try:
            query = self.session.query(
                IncidentTable.source,
                func.count(IncidentTable.incident_id)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            results = query.group_by(IncidentTable.source).all()
            
            return {source: count for source, count in results}
            
        except Exception as e:
            logger.error("get_incidents_by_source_failed", error=str(e))
            raise
    
    def get_incidents_by_severity(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        try:
            query = self.session.query(
                IncidentTable.severity,
                func.count(IncidentTable.incident_id)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            results = query.group_by(IncidentTable.severity).all()
            
            return {severity: count for severity, count in results}
            
        except Exception as e:
            logger.error("get_incidents_by_severity_failed", error=str(e))
            raise
    
    def get_incidents_by_failure_type(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        try:
            query = self.session.query(
                IncidentTable.failure_type,
                func.count(IncidentTable.incident_id)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            results = query.group_by(IncidentTable.failure_type).all()
            
            return {failure_type or "unknown": count for failure_type, count in results}
            
        except Exception as e:
            logger.error("get_incidents_by_failure_type_failed", error=str(e))
            raise
    
    def get_incidents_by_outcome(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        try:
            query = self.session.query(
                IncidentTable.outcome,
                func.count(IncidentTable.incident_id)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            results = query.group_by(IncidentTable.outcome).all()
            
            return {outcome or "pending": count for outcome, count in results}
            
        except Exception as e:
            logger.error("get_incidents_by_outcome_failed", error=str(e))
            raise
    
    def get_incident_trends(
        self,
        days: int = 30,
        granularity: str = "day",
    ) -> List[Dict[str, Any]]:
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            if granularity == "hour":
                date_trunc = func.date_trunc('hour', IncidentTable.created_at)
            elif granularity == "day":
                date_trunc = func.date_trunc('day', IncidentTable.created_at)
            elif granularity == "week":
                date_trunc = func.date_trunc('week', IncidentTable.created_at)
            else:
                date_trunc = func.date_trunc('day', IncidentTable.created_at)
            
            query = self.session.query(
                date_trunc.label('period'),
                func.count(IncidentTable.incident_id).label('total'),
                func.count(case((IncidentTable.outcome == Outcome.SUCCESS.value, 1))).label('resolved'),
                func.count(case((IncidentTable.outcome == Outcome.FAILED.value, 1))).label('failed'),
            ).filter(
                IncidentTable.created_at >= start_date
            ).group_by(
                date_trunc
            ).order_by(
                date_trunc
            )
            
            results = query.all()
            
            trends = []
            for period, total, resolved, failed in results:
                trends.append({
                    "period": period.isoformat() if period else None,
                    "total": total,
                    "resolved": resolved,
                    "failed": failed,
                    "success_rate": round((resolved / total * 100), 2) if total > 0 else 0,
                })
            
            return trends
            
        except Exception as e:
            logger.error("get_incident_trends_failed", error=str(e))
            raise
    
    def get_mttr(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        source: Optional[IncidentSource] = None,
    ) -> Dict[str, Any]:
        try:
            query = self.session.query(
                func.avg(IncidentTable.resolution_time_seconds).label('avg'),
                func.min(IncidentTable.resolution_time_seconds).label('min'),
                func.max(IncidentTable.resolution_time_seconds).label('max'),
                func.percentile_cont(0.5).within_group(IncidentTable.resolution_time_seconds).label('median'),
                func.percentile_cont(0.95).within_group(IncidentTable.resolution_time_seconds).label('p95'),
            ).filter(
                IncidentTable.outcome == Outcome.SUCCESS.value,
                IncidentTable.resolution_time_seconds.isnot(None),
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            if source:
                query = query.filter(IncidentTable.source == source.value)
            
            result = query.first()
            
            if not result or not result.avg:
                return {
                    "average_seconds": None,
                    "min_seconds": None,
                    "max_seconds": None,
                    "median_seconds": None,
                    "p95_seconds": None,
                }
            
            return {
                "average_seconds": round(result.avg, 2) if result.avg else None,
                "min_seconds": result.min,
                "max_seconds": result.max,
                "median_seconds": round(result.median, 2) if result.median else None,
                "p95_seconds": round(result.p95, 2) if result.p95 else None,
            }
            
        except Exception as e:
            logger.error("get_mttr_failed", error=str(e))
            return {
                "average_seconds": None,
                "min_seconds": None,
                "max_seconds": None,
                "median_seconds": None,
                "p95_seconds": None,
            }
    
    def get_confidence_distribution(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        try:
            query = self.session.query(IncidentTable.confidence).filter(
                IncidentTable.confidence.isnot(None)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            confidences = [r[0] for r in query.all()]
            
            distribution = {
                "very_low_0_50": 0,
                "low_50_70": 0,
                "medium_70_85": 0,
                "high_85_95": 0,
                "very_high_95_100": 0,
            }
            
            for conf in confidences:
                if conf < 0.5:
                    distribution["very_low_0_50"] += 1
                elif conf < 0.7:
                    distribution["low_50_70"] += 1
                elif conf < 0.85:
                    distribution["medium_70_85"] += 1
                elif conf < 0.95:
                    distribution["high_85_95"] += 1
                else:
                    distribution["very_high_95_100"] += 1
            
            return distribution
            
        except Exception as e:
            logger.error("get_confidence_distribution_failed", error=str(e))
            raise
    
    def get_remediation_success_by_action_type(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        try:
            query = self.session.query(
                RemediationHistoryTable.action_type,
                func.count(RemediationHistoryTable.history_id).label('total'),
                func.count(case((RemediationHistoryTable.success == True, 1))).label('successful'),
            )
            
            if start_date:
                query = query.filter(RemediationHistoryTable.executed_at >= start_date)
            if end_date:
                query = query.filter(RemediationHistoryTable.executed_at <= end_date)
            
            results = query.group_by(RemediationHistoryTable.action_type).all()
            
            data = []
            for action_type, total, successful in results:
                data.append({
                    "action_type": action_type,
                    "total": total,
                    "successful": successful,
                    "failed": total - successful,
                    "success_rate": round((successful / total * 100), 2) if total > 0 else 0,
                })
            
            return sorted(data, key=lambda x: x['total'], reverse=True)
            
        except Exception as e:
            logger.error("get_remediation_success_by_action_type_failed", error=str(e))
            raise
    
    def get_feedback_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        try:
            query = self.session.query(FeedbackTable)
            
            if start_date:
                query = query.filter(FeedbackTable.created_at >= start_date)
            if end_date:
                query = query.filter(FeedbackTable.created_at <= end_date)
            
            total = query.count()
            helpful = query.filter(FeedbackTable.helpful == True).count()
            not_helpful = query.filter(FeedbackTable.helpful == False).count()
            
            avg_rating = self.session.query(
                func.avg(FeedbackTable.rating)
            ).filter(
                FeedbackTable.rating.isnot(None)
            )
            if start_date:
                avg_rating = avg_rating.filter(FeedbackTable.created_at >= start_date)
            if end_date:
                avg_rating = avg_rating.filter(FeedbackTable.created_at <= end_date)
            avg_rating_value = avg_rating.scalar()
            
            return {
                "total_feedback": total,
                "helpful_count": helpful,
                "not_helpful_count": not_helpful,
                "helpfulness_rate": round((helpful / total * 100), 2) if total > 0 else 0,
                "average_rating": round(avg_rating_value, 2) if avg_rating_value else None,
            }
            
        except Exception as e:
            logger.error("get_feedback_summary_failed", error=str(e))
            raise
    
    def get_top_failure_types(
        self,
        limit: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        try:
            query = self.session.query(
                IncidentTable.failure_type,
                func.count(IncidentTable.incident_id).label('count'),
            ).filter(
                IncidentTable.failure_type.isnot(None)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            results = query.group_by(
                IncidentTable.failure_type
            ).order_by(
                desc('count')
            ).limit(limit).all()
            
            return [{"failure_type": ft, "count": count} for ft, count in results]
            
        except Exception as e:
            logger.error("get_top_failure_types_failed", error=str(e))
            raise
    
    def get_top_repositories(
        self,
        limit: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        try:
            query = self.session.query(
                cast(IncidentTable.context['repository'], String).label('repository'),
                func.count(IncidentTable.incident_id).label('count'),
            ).filter(
                IncidentTable.context['repository'].isnot(None)
            )

            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)

            results = query.group_by(
                cast(IncidentTable.context['repository'], String)
            ).order_by(
                desc('count')
            ).limit(limit).all()

            return [{"repository": repo, "count": count} for repo, count in results if repo]

        except Exception as e:
            logger.error("get_top_repositories_failed", error=str(e))
            raise
    
    def get_hourly_distribution(
        self,
        days: int = 30,
    ) -> Dict[int, int]:
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            query = self.session.query(
                func.extract('hour', IncidentTable.created_at).label('hour'),
                func.count(IncidentTable.incident_id).label('count'),
            ).filter(
                IncidentTable.created_at >= start_date
            ).group_by(
                func.extract('hour', IncidentTable.created_at)
            ).order_by('hour')
            
            results = query.all()
            
            distribution = {h: 0 for h in range(24)}
            for hour, count in results:
                distribution[int(hour)] = count
            
            return distribution
            
        except Exception as e:
            logger.error("get_hourly_distribution_failed", error=str(e))
            raise
    
    def get_daily_distribution(
        self,
        days: int = 30,
    ) -> Dict[str, int]:
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            query = self.session.query(
                func.to_char(IncidentTable.created_at, 'Day').label('day'),
                func.count(IncidentTable.incident_id).label('count'),
            ).filter(
                IncidentTable.created_at >= start_date
            ).group_by(
                func.to_char(IncidentTable.created_at, 'Day')
            )
            
            results = query.all()
            
            return {day.strip(): count for day, count in results}
            
        except Exception as e:
            logger.error("get_daily_distribution_failed", error=str(e))
            raise
    
    def get_auto_fix_rate(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        try:
            query = self.session.query(IncidentTable).filter(
                IncidentTable.outcome.isnot(None)
            )
            
            if start_date:
                query = query.filter(IncidentTable.created_at >= start_date)
            if end_date:
                query = query.filter(IncidentTable.created_at <= end_date)
            
            total = query.count()
            auto_fixed = query.filter(
                IncidentTable.outcome == Outcome.SUCCESS.value,
                IncidentTable.remediation_executed == True,
            ).count()
            
            escalated = query.filter(IncidentTable.outcome == Outcome.ESCALATED.value).count()
            
            return {
                "total_completed": total,
                "auto_fixed": auto_fixed,
                "escalated": escalated,
                "auto_fix_rate": round((auto_fixed / total * 100), 2) if total > 0 else 0,
                "escalation_rate": round((escalated / total * 100), 2) if total > 0 else 0,
            }
            
        except Exception as e:
            logger.error("get_auto_fix_rate_failed", error=str(e))
            raise
    
    def record_metric(
        self,
        metric_name: str,
        metric_type: str,
        value: float,
        unit: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> MetricTable:
        try:
            from uuid import uuid4
            
            metric = MetricTable(
                metric_id=f"metric_{uuid4().hex[:12]}",
                metric_name=metric_name,
                metric_type=metric_type,
                value=value,
                unit=unit,
                labels=labels or {},
                timestamp=datetime.now(timezone.utc),
            )
            
            self.session.add(metric)
            self.session.commit()
            
            return metric
            
        except Exception as e:
            self.session.rollback()
            logger.error("record_metric_failed", error=str(e))
            raise
    
    def get_metrics(
        self,
        metric_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[MetricTable]:
        try:
            query = self.session.query(MetricTable).filter(
                MetricTable.metric_name == metric_name
            )
            
            if start_date:
                query = query.filter(MetricTable.timestamp >= start_date)
            if end_date:
                query = query.filter(MetricTable.timestamp <= end_date)
            
            return query.order_by(desc(MetricTable.timestamp)).limit(limit).all()
            
        except Exception as e:
            logger.error("get_metrics_failed", error=str(e))
            raise
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        try:
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = today - timedelta(days=7)
            month_ago = today - timedelta(days=30)
            
            today_stats = self.get_incident_stats(start_date=today)
            week_stats = self.get_incident_stats(start_date=week_ago)
            month_stats = self.get_incident_stats(start_date=month_ago)
            
            mttr = self.get_mttr(start_date=month_ago)
            auto_fix = self.get_auto_fix_rate(start_date=month_ago)
            feedback = self.get_feedback_summary(start_date=month_ago)
            
            return {
                "today": today_stats,
                "this_week": week_stats,
                "this_month": month_stats,
                "mttr": mttr,
                "auto_fix_rate": auto_fix,
                "feedback": feedback,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as e:
            logger.error("get_dashboard_summary_failed", error=str(e))
            raise