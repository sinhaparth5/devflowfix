# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Repository for metrics CRUD operations."""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from app.adapters.database.postgres.models import MetricTable


class MetricRepository:
    """Repository for managing metrics database operations."""
    
    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def create(
        self,
        metric_id: str,
        metric_name: str,
        metric_type: str,
        value: float,
        unit: Optional[str] = None,
        labels: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> MetricTable:
        """
        Create a new metric entry in the database.
        
        Args:
            metric_id: Unique identifier for the metric
            metric_name: Name of the metric
            metric_type: Type of metric (counter, gauge, histogram)
            value: Metric value
            unit: Unit of measurement (optional)
            labels: Labels for grouping/filtering (optional)
            timestamp: Timestamp (defaults to now)
            
        Returns:
            Created MetricTable object
        """
        metric = MetricTable(
            metric_id=metric_id,
            metric_name=metric_name,
            metric_type=metric_type,
            value=value,
            unit=unit,
            labels=labels or {},
            timestamp=timestamp or datetime.utcnow(),
        )
        
        self.session.add(metric)
        self.session.commit()
        self.session.refresh(metric)
        
        return metric
    
    def get_by_id(self, metric_id: str) -> Optional[MetricTable]:
        """
        Retrieve a metric by its ID.
        
        Args:
            metric_id: The unique identifier of the metric
            
        Returns:
            MetricTable object if found, None otherwise
        """
        stmt = select(MetricTable).where(MetricTable.metric_id == metric_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_name(
        self,
        metric_name: str,
        labels: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[MetricTable]:
        """
        Retrieve metrics by name with optional filtering.
        
        Args:
            metric_name: Name of the metric
            labels: Labels to filter by (optional)
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum number of results (default: 1000)
            
        Returns:
            List of MetricTable objects
        """
        stmt = select(MetricTable).where(MetricTable.metric_name == metric_name)
        
        if start_time:
            stmt = stmt.where(MetricTable.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(MetricTable.timestamp <= end_time)
        
        # TODO: Add label filtering when needed
        # Note: JSON filtering in PostgreSQL requires specific syntax
        
        stmt = stmt.order_by(MetricTable.timestamp.desc()).limit(limit)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def list_metrics(
        self,
        metric_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[MetricTable]:
        """
        List metrics with optional filtering.
        
        Args:
            metric_type: Filter by metric type
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum number of results to return (default: 1000)
            offset: Number of results to skip (default: 0)
            
        Returns:
            List of MetricTable objects
        """
        stmt = select(MetricTable)
        
        # Apply filters
        conditions = []
        if metric_type:
            conditions.append(MetricTable.metric_type == metric_type)
        if start_time:
            conditions.append(MetricTable.timestamp >= start_time)
        if end_time:
            conditions.append(MetricTable.timestamp <= end_time)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Order by timestamp descending (newest first)
        stmt = stmt.order_by(MetricTable.timestamp.desc())
        
        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def delete(self, metric_id: str) -> bool:
        """
        Delete a metric by ID.
        
        Args:
            metric_id: The unique identifier of the metric to delete
            
        Returns:
            True if deleted, False if not found
        """
        metric = self.get_by_id(metric_id)
        if not metric:
            return False
        
        self.session.delete(metric)
        self.session.commit()
        
        return True
    
    def delete_old_metrics(self, days: int = 30) -> int:
        """
        Delete metrics older than N days.
        
        Args:
            days: Number of days to keep (default: 30)
            
        Returns:
            Number of metrics deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(MetricTable).where(MetricTable.timestamp < cutoff_date)
        result = self.session.execute(stmt)
        metrics_to_delete = result.scalars().all()
        
        count = len(metrics_to_delete)
        for metric in metrics_to_delete:
            self.session.delete(metric)
        
        self.session.commit()
        return count
    
    def get_latest_value(self, metric_name: str) -> Optional[float]:
        """
        Get the latest value for a metric.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            Latest metric value or None if not found
        """
        stmt = (
            select(MetricTable.value)
            .where(MetricTable.metric_name == metric_name)
            .order_by(MetricTable.timestamp.desc())
            .limit(1)
        )
        result = self.session.execute(stmt)
        value = result.scalar_one_or_none()
        return value
    
    def get_average(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Get average value for a metric over a time range.
        
        Args:
            metric_name: Name of the metric
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            
        Returns:
            Average value or None if no data
        """
        stmt = select(func.avg(MetricTable.value)).where(MetricTable.metric_name == metric_name)
        
        if start_time:
            stmt = stmt.where(MetricTable.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(MetricTable.timestamp <= end_time)
        
        result = self.session.execute(stmt)
        avg = result.scalar_one()
        return float(avg) if avg is not None else None
    
    def get_sum(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Get sum of values for a metric over a time range.
        
        Args:
            metric_name: Name of the metric
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            
        Returns:
            Sum of values or None if no data
        """
        stmt = select(func.sum(MetricTable.value)).where(MetricTable.metric_name == metric_name)
        
        if start_time:
            stmt = stmt.where(MetricTable.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(MetricTable.timestamp <= end_time)
        
        result = self.session.execute(stmt)
        total = result.scalar_one()
        return float(total) if total is not None else None
    
    def get_min_max(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Optional[float]]:
        """
        Get minimum and maximum values for a metric over a time range.
        
        Args:
            metric_name: Name of the metric
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            
        Returns:
            Dictionary with 'min' and 'max' keys
        """
        stmt = select(
            func.min(MetricTable.value),
            func.max(MetricTable.value)
        ).where(MetricTable.metric_name == metric_name)
        
        if start_time:
            stmt = stmt.where(MetricTable.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(MetricTable.timestamp <= end_time)
        
        result = self.session.execute(stmt)
        min_val, max_val = result.one()
        
        return {
            'min': float(min_val) if min_val is not None else None,
            'max': float(max_val) if max_val is not None else None,
        }
    
    def count_metrics(
        self,
        metric_name: Optional[str] = None,
        metric_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """
        Count metrics with optional filtering.
        
        Args:
            metric_name: Filter by metric name (optional)
            metric_type: Filter by metric type (optional)
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            
        Returns:
            Count of matching metrics
        """
        stmt = select(func.count()).select_from(MetricTable)
        
        conditions = []
        if metric_name:
            conditions.append(MetricTable.metric_name == metric_name)
        if metric_type:
            conditions.append(MetricTable.metric_type == metric_type)
        if start_time:
            conditions.append(MetricTable.timestamp >= start_time)
        if end_time:
            conditions.append(MetricTable.timestamp <= end_time)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        result = self.session.execute(stmt)
        return result.scalar_one()
    
    def get_unique_metric_names(self) -> List[str]:
        """
        Get all unique metric names in the database.
        
        Returns:
            List of unique metric names
        """
        stmt = select(MetricTable.metric_name).distinct()
        result = self.session.execute(stmt)
        return [row[0] for row in result.all()]
    
    def get_recent_metrics(
        self,
        metric_name: Optional[str] = None,
        hours: int = 1,
        limit: int = 100,
    ) -> List[MetricTable]:
        """
        Get recent metrics from the last N hours.
        
        Args:
            metric_name: Filter by metric name (optional)
            hours: Number of hours to look back (default: 1)
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of recent MetricTable objects
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        stmt = select(MetricTable).where(MetricTable.timestamp >= cutoff_time)
        
        if metric_name:
            stmt = stmt.where(MetricTable.metric_name == metric_name)
        
        stmt = stmt.order_by(MetricTable.timestamp.desc()).limit(limit)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
