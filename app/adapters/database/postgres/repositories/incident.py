# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, func, desc, cast, String
import structlog
import base64
import json

from app.adapters.database.postgres.models import IncidentTable
from app.exceptions import DatabaseError
from app.core.enums import IncidentSource, Severity, Outcome, FailureType

logger = structlog.get_logger()


class IncidentRepository:
    """Repository for incident database operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, incident: IncidentTable) -> IncidentTable:
        """Create a new incident."""
        try:
            self.db.add(incident)
            self.db.commit()
            self.db.refresh(incident)
            logger.info("incident_created", incident_id=incident.incident_id)
            return incident
        except Exception as e:
            self.db.rollback()
            logger.error("incident_creation_failed", error=str(e))
            raise DatabaseError("create", str(e))

    def get_by_id(self, incident_id: str) -> Optional[IncidentTable]:
        """Get incident by ID."""
        return self.db.query(IncidentTable).filter(
            IncidentTable.incident_id == incident_id
        ).first()

    def update(self, incident: IncidentTable) -> IncidentTable:
        """Update an existing incident."""
        try:
            incident.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(incident)
            return incident
        except Exception as e:
            self.db.rollback()
            logger.error("incident_update_failed", incident_id=incident.incident_id, error=str(e))
            raise DatabaseError("update", str(e))

    def delete(self, incident_id: str) -> bool:
        """Delete an incident."""
        incident = self.get_by_id(incident_id)
        if incident:
            self.db.delete(incident)
            self.db.commit()
            return True
        return False

    # User-scoped queries

    def list_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None,
    ) -> tuple[list[IncidentTable], int]:
        """
        List incidents for a specific user.
        
        Args:
            user_id: User ID to filter by
            skip: Number of records to skip
            limit: Maximum records to return
            filters: Optional filters dict
            
        Returns:
            Tuple of (incidents, total_count)
        """
        query = self.db.query(IncidentTable).filter(IncidentTable.user_id == user_id)
        query = self._apply_filters(query, filters or {})

        total = query.count()
        incidents = query.order_by(desc(IncidentTable.created_at)).offset(skip).limit(limit).all()

        return incidents, total

    def get_user_stats(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get incident statistics for a specific user.
        
        Args:
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Statistics dictionary
        """
        query = self.db.query(IncidentTable).filter(IncidentTable.user_id == user_id)

        if start_date:
            query = query.filter(IncidentTable.created_at >= start_date)
        if end_date:
            query = query.filter(IncidentTable.created_at <= end_date)

        return self._compute_stats(query)

    def assign_to_user(self, incident_id: str, user_id: str) -> bool:
        """Assign an incident to a user."""
        incident = self.get_by_id(incident_id)
        if incident:
            incident.user_id = user_id
            incident.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info("incident_assigned", incident_id=incident_id, user_id=user_id)
            return True
        return False

    # Admin/global queries

    def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None,
    ) -> tuple[list[IncidentTable], int]:
        """
        List all incidents (admin use).
        
        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            filters: Optional filters dict
            
        Returns:
            Tuple of (incidents, total_count)
        """
        query = self.db.query(IncidentTable)
        query = self._apply_filters(query, filters or {})

        total = query.count()
        incidents = query.order_by(desc(IncidentTable.created_at)).offset(skip).limit(limit).all()

        return incidents, total

    def get_global_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get global incident statistics.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Statistics dictionary
        """
        query = self.db.query(IncidentTable)

        if start_date:
            query = query.filter(IncidentTable.created_at >= start_date)
        if end_date:
            query = query.filter(IncidentTable.created_at <= end_date)

        return self._compute_stats(query)

    # Helper methods

    def _apply_filters(self, query, filters: dict):
        """Apply filters to query."""
        if filters.get("user_id"):
            query = query.filter(IncidentTable.user_id == filters["user_id"])
        if filters.get("source"):
            query = query.filter(IncidentTable.source == filters["source"])
        if filters.get("severity"):
            query = query.filter(IncidentTable.severity == filters["severity"])
        if filters.get("outcome"):
            query = query.filter(IncidentTable.outcome == filters["outcome"])
        if filters.get("failure_type"):
            query = query.filter(IncidentTable.failure_type == filters["failure_type"])
        if filters.get("start_date"):
            query = query.filter(IncidentTable.created_at >= filters["start_date"])
        if filters.get("end_date"):
            query = query.filter(IncidentTable.created_at <= filters["end_date"])
        if filters.get("search"):
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    IncidentTable.error_log.ilike(search_term),
                    IncidentTable.error_message.ilike(search_term),
                    IncidentTable.root_cause.ilike(search_term),
                )
            )
        if filters.get("min_confidence"):
            query = query.filter(IncidentTable.confidence >= filters["min_confidence"])
        if filters.get("max_confidence"):
            query = query.filter(IncidentTable.confidence <= filters["max_confidence"])
        if filters.get("repository"):
            query = query.filter(
                cast(IncidentTable.context["repository"], String) == filters["repository"]
            )
        if filters.get("namespace"):
            query = query.filter(
                cast(IncidentTable.context["namespace"], String) == filters["namespace"]
            )
        if filters.get("service"):
            query = query.filter(
                cast(IncidentTable.context["service"], String) == filters["service"]
            )

        return query

    def _compute_stats(self, query) -> dict:
        """Compute statistics from a query."""
        total = query.count()

        # Count by outcome
        resolved = query.filter(IncidentTable.outcome == "success").count()
        pending = query.filter(
            or_(IncidentTable.outcome == "pending", IncidentTable.outcome == None)
        ).count()
        failed = query.filter(IncidentTable.outcome == "failed").count()
        escalated = query.filter(IncidentTable.outcome == "escalated").count()

        # Success rate
        success_rate = (resolved / total * 100) if total > 0 else 0.0

        # Average resolution time
        resolved_incidents = query.filter(
            and_(
                IncidentTable.outcome == "success",
                IncidentTable.resolution_time_seconds != None
            )
        ).all()

        avg_resolution_time = None
        if resolved_incidents:
            total_time = sum(inc.resolution_time_seconds for inc in resolved_incidents)
            avg_resolution_time = total_time / len(resolved_incidents)

        # By source
        by_source = {}
        for row in self.db.query(
            IncidentTable.source,
            func.count(IncidentTable.incident_id)
        ).group_by(IncidentTable.source).all():
            by_source[row[0]] = row[1]

        # By severity
        by_severity = {}
        for row in self.db.query(
            IncidentTable.severity,
            func.count(IncidentTable.incident_id)
        ).group_by(IncidentTable.severity).all():
            by_severity[row[0]] = row[1]

        # By failure type
        by_failure_type = {}
        for row in self.db.query(
            IncidentTable.failure_type,
            func.count(IncidentTable.incident_id)
        ).filter(IncidentTable.failure_type != None).group_by(IncidentTable.failure_type).all():
            by_failure_type[row[0]] = row[1]

        return {
            "total_incidents": total,
            "resolved_incidents": resolved,
            "pending_incidents": pending,
            "failed_incidents": failed,
            "escalated_incidents": escalated,
            "success_rate": round(success_rate, 2),
            "average_resolution_time_seconds": avg_resolution_time,
            "incidents_by_source": by_source,
            "incidents_by_severity": by_severity,
            "incidents_by_failure_type": by_failure_type,
        }

    # Vector/similarity queries

    def get_similar_incidents(
        self,
        embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.7,
        exclude_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[tuple[IncidentTable, float]]:
        """
        Find similar incidents using vector similarity.
        
        Args:
            embedding: Query embedding vector
            limit: Maximum results
            min_similarity: Minimum cosine similarity threshold
            exclude_id: Incident ID to exclude from results
            user_id: Optional user ID to scope results
            
        Returns:
            List of (incident, similarity_score) tuples
        """
        from pgvector.sqlalchemy import Vector

        # Build base query
        query = self.db.query(
            IncidentTable,
            IncidentTable.embedding.cosine_distance(embedding).label("distance")
        ).filter(
            IncidentTable.embedding != None,
            IncidentTable.outcome == "success",  # Only resolved incidents
        )

        if exclude_id:
            query = query.filter(IncidentTable.incident_id != exclude_id)

        if user_id:
            query = query.filter(IncidentTable.user_id == user_id)

        # Order by similarity (lower distance = higher similarity)
        query = query.order_by("distance").limit(limit * 2)  # Get extra for filtering

        results = query.all()

        # Convert distance to similarity and filter
        similar = []
        for incident, distance in results:
            similarity = 1 - distance
            if similarity >= min_similarity:
                similar.append((incident, similarity))
            if len(similar) >= limit:
                break

        return similar

    def update_embedding(self, incident_id: str, embedding: list[float]) -> bool:
        """Update incident embedding."""
        incident = self.get_by_id(incident_id)
        if incident:
            incident.embedding = embedding
            incident.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            return True
        return False

    # Recent incidents

    def get_recent(
        self,
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> list[IncidentTable]:
        """Get recent incidents."""
        query = self.db.query(IncidentTable)

        if user_id:
            query = query.filter(IncidentTable.user_id == user_id)

        return query.order_by(desc(IncidentTable.created_at)).limit(limit).all()

    def get_pending(
        self,
        user_id: Optional[str] = None,
    ) -> list[IncidentTable]:
        """Get pending incidents awaiting remediation."""
        query = self.db.query(IncidentTable).filter(
            or_(
                IncidentTable.outcome == "pending",
                IncidentTable.outcome == None
            )
        )

        if user_id:
            query = query.filter(IncidentTable.user_id == user_id)

        return query.order_by(IncidentTable.created_at).all()

    # Enhanced Search

    def advanced_search(
        self,
        user_id: str,
        search_query: Optional[str] = None,
        sources: Optional[List[IncidentSource]] = None,
        severities: Optional[List[Severity]] = None,
        outcomes: Optional[List[Outcome]] = None,
        failure_types: Optional[List[FailureType]] = None,
        tags: Optional[List[str]] = None,
        repository: Optional[str] = None,
        min_confidence: Optional[float] = None,
        max_confidence: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[List[IncidentTable], int, Optional[str], Optional[str]]:
        """
        Advanced search with full-text search, multi-select filters, and pagination.

        Args:
            user_id: User ID to filter by (required for security)
            search_query: Full-text search across error messages, logs, and stack traces
            sources: List of sources to filter by (OR condition)
            severities: List of severities to filter by (OR condition)
            outcomes: List of outcomes to filter by (OR condition)
            failure_types: List of failure types to filter by (OR condition)
            tags: List of tags to filter by (OR condition)
            repository: Filter by repository name
            min_confidence: Minimum confidence score
            max_confidence: Maximum confidence score
            start_date: Start date for filtering
            end_date: End date for filtering
            sort_by: Field to sort by
            sort_order: Sort order (asc or desc)
            page: Page number (1-indexed)
            page_size: Items per page
            cursor: Optional cursor for cursor-based pagination

        Returns:
            Tuple of (incidents, total_count, next_cursor, previous_cursor)
        """
        import time
        start_time = time.time()

        # Build base query with user filter
        query = self.db.query(IncidentTable).filter(IncidentTable.user_id == user_id)

        # Full-text search
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    IncidentTable.error_log.ilike(search_term),
                    IncidentTable.error_message.ilike(search_term),
                    IncidentTable.stack_trace.ilike(search_term),
                    IncidentTable.root_cause.ilike(search_term),
                )
            )

        # Multi-select filters (OR condition within each filter)
        if sources:
            source_values = [s.value if isinstance(s, IncidentSource) else s for s in sources]
            query = query.filter(IncidentTable.source.in_(source_values))

        if severities:
            severity_values = [s.value if isinstance(s, Severity) else s for s in severities]
            query = query.filter(IncidentTable.severity.in_(severity_values))

        if outcomes:
            outcome_values = [o.value if isinstance(o, Outcome) else o for o in outcomes]
            query = query.filter(IncidentTable.outcome.in_(outcome_values))

        if failure_types:
            failure_type_values = [f.value if isinstance(f, FailureType) else f for f in failure_types]
            query = query.filter(IncidentTable.failure_type.in_(failure_type_values))

        # Tags filtering (OR condition)
        if tags:
            tag_filters = [
                func.json_array_length(IncidentTable.tags) > 0,
                or_(*[
                    cast(IncidentTable.tags, String).ilike(f'%"{tag}"%')
                    for tag in tags
                ])
            ]
            query = query.filter(and_(*tag_filters))

        # Repository filtering
        if repository:
            query = query.filter(
                cast(IncidentTable.context["repository"], String) == repository
            )

        # Confidence range
        if min_confidence is not None:
            query = query.filter(IncidentTable.confidence >= min_confidence)
        if max_confidence is not None:
            query = query.filter(IncidentTable.confidence <= max_confidence)

        # Date filtering
        if start_date:
            query = query.filter(IncidentTable.created_at >= start_date)
        if end_date:
            query = query.filter(IncidentTable.created_at <= end_date)

        # Get total count before pagination
        total = query.count()

        # Sorting
        sort_column = getattr(IncidentTable, sort_by, IncidentTable.created_at)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)

        # Pagination
        offset = (page - 1) * page_size
        incidents = query.offset(offset).limit(page_size).all()

        # Calculate cursors (simple base64 encoding of page number for now)
        next_cursor = None
        previous_cursor = None

        if page * page_size < total:
            next_cursor = base64.b64encode(str(page + 1).encode()).decode()
        if page > 1:
            previous_cursor = base64.b64encode(str(page - 1).encode()).decode()

        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)

        logger.info(
            "advanced_search_completed",
            user_id=user_id,
            total_results=total,
            page=page,
            duration_ms=duration_ms,
        )

        return incidents, total, next_cursor, previous_cursor

    def calculate_date_range(
        self,
        preset: str,
    ) -> Tuple[datetime, datetime]:
        """
        Calculate start and end dates from a preset.

        Args:
            preset: Date range preset (e.g., "today", "last_7_days")

        Returns:
            Tuple of (start_date, end_date)
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if preset == "today":
            return today_start, now
        elif preset == "yesterday":
            yesterday = today_start - timedelta(days=1)
            return yesterday, today_start
        elif preset == "this_week":
            week_start = today_start - timedelta(days=now.weekday())
            return week_start, now
        elif preset == "last_week":
            week_start = today_start - timedelta(days=now.weekday() + 7)
            week_end = week_start + timedelta(days=7)
            return week_start, week_end
        elif preset == "this_month":
            month_start = today_start.replace(day=1)
            return month_start, now
        elif preset == "last_month":
            month_start = (today_start.replace(day=1) - timedelta(days=1)).replace(day=1)
            month_end = today_start.replace(day=1)
            return month_start, month_end
        elif preset == "last_7_days":
            return today_start - timedelta(days=7), now
        elif preset == "last_30_days":
            return today_start - timedelta(days=30), now
        elif preset == "last_90_days":
            return today_start - timedelta(days=90), now
        else:
            # Default to last 30 days
            return today_start - timedelta(days=30), now

    # Bulk operations

    def bulk_assign_to_user(
        self,
        incident_ids: list[str],
        user_id: str,
    ) -> int:
        """Bulk assign incidents to a user."""
        result = self.db.query(IncidentTable).filter(
            IncidentTable.incident_id.in_(incident_ids)
        ).update(
            {
                "user_id": user_id,
                "updated_at": datetime.now(timezone.utc),
            },
            synchronize_session=False
        )
        self.db.commit()
        return result

    def bulk_update_outcome(
        self,
        incident_ids: list[str],
        outcome: str,
        outcome_message: Optional[str] = None,
    ) -> int:
        """Bulk update incident outcomes."""
        update_data = {
            "outcome": outcome,
            "updated_at": datetime.now(timezone.utc),
        }
        if outcome_message:
            update_data["outcome_message"] = outcome_message
        if outcome == "success":
            update_data["resolved_at"] = datetime.now(timezone.utc)

        result = self.db.query(IncidentTable).filter(
            IncidentTable.incident_id.in_(incident_ids)
        ).update(update_data, synchronize_session=False)
        self.db.commit()
        return result