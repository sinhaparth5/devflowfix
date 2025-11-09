# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Text, Index, desc
from pgvector.sqlalchemy import Vector

class IncidentTable(SQLModel, table=True):
    """
    Incident database table.
    Stores all incident information including embedding 
    """

    __tablename__ = "incidents"
    
    # Primary Key
    incident_id: str = Field(primary_key=True, max_length=50)

    # Timestamps 
    timestamp: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(default=None, index=True)

    # Source Information
    source: str = Field(max_length=50, index=True)
    severity: str = Field(max_length=20, index=True)

    # Failure Details
    failure_type: Optional[str] = Field(default=None, max_length=50, index=True)
    error_log: str = Field(sa_column=Column(Text))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    stack_trace: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Context (stored as JSON)
    context: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Analysis Results
    root_cause: Optional[str] = Field(default=None, sa_column=Column(Text))
    fixability: Optional[str] = Field(default=None, max_length=20)
    confidence: Optional[float] = Field(default=None, index=True)

    # Vector Embedding for RAG (768 dimensions for typical embedding models)
    embedding: Optional[list] = Field(
        default=None,
        sa_column=Column(Vector(768))
    )

    # Similar Incidents (stored as JSON)
    similar_incidents: Optional[list] = Field(default=None, sa_column=Column(JSON))

    # Remediation
    remediation_plan: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    remediation_executed: bool = Field(default=False)
    remediation_start_time: Optional[datetime] = Field(default=None)
    remediation_end_time: Optional[datetime] = Field(default=None)

    # Outcome
    outcome: Optional[str] = Field(default=None, max_length=20, index=True)
    outcome_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    resolution_time_seconds: Optional[int] = Field(default=None)

    # Human Feedback
    human_feedback: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    approved_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    approval_timestamp: Optional[datetime] = Field(default=None)

    # Metadata
    raw_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    tags: list = Field(default_factory=list, sa_column=Column(JSON))

    # Indexes are defined in the migration files
    # But we can specify them here for documentation
    __table_args__ = (
        Index('idx_incidents_timestamp_desc', desc('timestamp')),
        Index('idx_incidents_source_severity', 'source', 'severity'),
        Index('idx_incidents_outcome_created', 'outcome', 'created_at'),
        Index('idx_incidents_confidence_desc', desc('confidence')),
    )

class FeedbackTable(SQLModel, table=True):
    """
    Human feedback table.

    Stores feedback on incident remediations for learning 
    """
    __tablename__ = "feedback"
    
    # Primary Key
    feedback_id: str = Field(primary_key=True, max_length=50)

    # Foreign Key to Incident
    incident_id: str = Field(foreign_key="incidents.incident_id", index=True, max_length=50)
    
    # Feedback
    helpful: bool = Field(index=True)
    comment: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # User Information
    user: Optional[str] = Field(default=None, max_length=100)
    user_email: Optional[str] = Field(default=None, max_length=200)
    
    # Additional Feedback
    rating: Optional[int] = Field(default=None, ge=1, le=5)  # 1-5 star rating
    categories: Optional[list] = Field(default=None, sa_column=Column(JSON))
    
    # Timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_feedback_incident_created', 'incident_id', 'created_at'),
        Index('idx_feedback_helpful', 'helpful'),
    )

class RemediationHistoryTable(SQLModel, table=True):
    """
    Remediation history table.
    
    Stores all remediation attempts for auditing and analysis.
    """
    
    __tablename__ = "remediation_history"
    
    # Primary Key
    history_id: str = Field(primary_key=True, max_length=50)
    
    # Foreign Key to Incident
    incident_id: str = Field(foreign_key="incidents.incident_id", index=True, max_length=50)
    
    # Attempt Information
    attempt_number: int = Field(index=True)
    action_type: str = Field(max_length=100)
    
    # Execution Details
    executed_at: datetime = Field(index=True)
    duration_seconds: Optional[int] = Field(default=None)
    
    # Result
    success: bool = Field(index=True)
    outcome: str = Field(max_length=20)
    message: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Execution Context
    executed_by: Optional[str] = Field(default=None, max_length=100)  # "system" or username
    environment: str = Field(default="dev", max_length=20)
    dry_run: bool = Field(default=False)
    
    # Actions and Validation
    actions_performed: Optional[list] = Field(default=None, sa_column=Column(JSON))
    pre_validation_passed: bool = Field(default=True)
    post_validation_passed: bool = Field(default=True)
    validation_details: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Rollback Information
    rollback_required: bool = Field(default=False)
    rollback_performed: bool = Field(default=False)
    rollback_snapshot_id: Optional[str] = Field(default=None, max_length=50)
    
    # Metadata
    execution_logs: Optional[list] = Field(default=None, sa_column=Column(JSON))
    remediation_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    __table_args__ = (
        Index('idx_remediation_incident_attempt', 'incident_id', 'attempt_number'),
        Index('idx_remediation_success_executed', 'success', 'executed_at'),
    )

class MetricTable(SQLModel, table=True):
    """
    Metrics table.
    
    Stores system metrics for monitoring and analytics.
    """
    
    __tablename__ = "metrics"
    
    # Primary Key
    metric_id: str = Field(primary_key=True, max_length=50)
    
    # Metric Information
    metric_name: str = Field(max_length=100, index=True)
    metric_type: str = Field(max_length=50)  # "counter", "gauge", "histogram"
    value: float = Field()
    unit: Optional[str] = Field(default=None, max_length=50)
    
    # Labels (for grouping/filtering)
    labels: dict = Field(default_factory=dict, sa_column=Column(JSON))
    
    # Timestamp
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_metrics_name_timestamp', 'metric_name', 'timestamp'),
    )

class ConfigTable(SQLModel, table=True):
    """
    Configuration table.
    
    Stores system configuration and settings.
    """
    
    __tablename__ = "config"
    
    # Primary Key
    config_key: str = Field(primary_key=True, max_length=100)
    
    # Value
    config_value: str = Field(sa_column=Column(Text))
    value_type: str = Field(max_length=20)  # "string", "int", "float", "bool", "json"
    
    # Metadata
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    category: Optional[str] = Field(default=None, max_length=50, index=True)
    
    # Versioning
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[str] = Field(default=None, max_length=100)
    
    # Flags
    is_secret: bool = Field(default=False)  # Should be encrypted
    is_system: bool = Field(default=False)  # System config, not user-editable
