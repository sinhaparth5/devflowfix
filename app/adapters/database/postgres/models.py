# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON, Relationship
from sqlalchemy import Text, Index, desc, ForeignKey
from pgvector.sqlalchemy import Vector

class UserTable(SQLModel, table=True):
    """
    User database table.
    Stores user information for Zero Trust authentication.
    """
    __tablename__ = "users"
    # Primary Key
    user_id: str = Field(primary_key=True, max_length=50)

    # Authentication
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(sa_column=Column(Text))

    # Profile Information
    full_name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None, max_length=500)

    # Organization/Team
    organization_id: Optional[str] = Field(default=None, max_length=50, index=True)
    team_id: Optional[str] = Field(default=None, max_length=50, index=True)
    role: str = Field(default="user", max_length=50, index=True)

    # Zero Trust Fields
    is_active: bool = Field(default=True, index=True)
    is_verified: bool = Field(default=False)
    is_mfa_enabled: bool = Field(default=False)
    mfa_secret: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Session Management
    last_login_at: Optional[datetime] = Field(default=None)
    last_login_ip: Optional[str] = Field(default=None, max_length=45)
    last_login_user_agent: Optional[str] = Field(default=None, sa_column=Column(Text))
    failed_login_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = Field(default=None)
       
    # Token Management
    refresh_token_hash: Optional[str] = Field(default=None, sa_column=Column(Text))
    token_version: int = Field(default=0)

    # API Keys for service accounts
    api_key_hash: Optional[str] = Field(default=None, sa_column=Column(Text))
    api_key_prefix: Optional[str] = Field(default=None, max_length=10)

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = Field(default=None, max_length=50)

    # Settings/Preferences (strored as JSON)
    preferences: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Allowed resources (Zero Trust - explicit permissions)
    allowed_repositories: list = Field(default_factory=list, sa_column=Column(JSON))
    allowed_namespaces: list = Field(default_factory=list, sa_column=Column(JSON))
    allowed_services: list = Field(default_factory=list, sa_column=Column(JSON))

    __table_args__ = (
        Index('idx_users_email_active', 'email', 'is_active'),
        Index('idx_users_org_team', 'organization_id', 'team_id'),
        Index('idx_users_role', 'role'),
    )

class UserSessionTable(SQLModel, table=True):
    """
    User session table for Zero Trust session management.
    Each session is tracked individually for security
    """
    __tablename__ = "user_sessions"

    # Primary Key
    session_id: str = Field(primary_key=True, max_length=50)

    # Foregin Key to User
    user_id: str = Field(foreign_key="users.user_id", index=True, max_length=50)

    # Session Details
    refresh_token_hash: str = Field(sa_column=Column(Text))
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Location (for anomaly detection)
    country: Optional[str] = Field(default=None, max_length=2)
    city: Optional[str] = Field(default=None, max_length=100)
    
    # Session state
    is_active: bool = Field(default=True, index=True)
    is_revoked: bool = Field(default=False)
    revoked_reason: Optional[str] = Field(default=None, max_length=255)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_used_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(index=True)

    __table_args__ = (
        Index('idx_sessions_user_active', 'user_id', 'is_active'),
        Index('idx_sessions_expires', 'expires_at'),
    )

class AuditLogTable(SQLModel, table=True):
    """
    Audit log table for Zero Trust compliance.
    Tracks all security-relevant actions
    """
    __tablename__ = "audit_logs"

    # Primary Key
    log_id: str = Field(primary_key=True, max_length=50)

    # Who
    user_id: Optional[str] = Field(default=None, foreign_key="users.user_id", index=True, max_length=50)
    session_id: Optional[str] = Field(default=None, max_length=50)

    # What
    action: str = Field(max_length=100, index=True)
    resource_type: Optional[str] = Field(default=None, max_length=50)
    resource_id: Optional[str] = Field(default=None, max_length=50)

    # Details
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Where
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Result
    success: bool = Field(default=True, index=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))

    # When
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_created_desc', desc('created_at')),
    )

class IncidentTable(SQLModel, table=True):
    """
    Incident database table.
    Stores all incident information including embedding 
    """

    __tablename__ = "incidents"
    
    # Primary Key
    incident_id: str = Field(primary_key=True, max_length=50)

    # Foreign Key to User (owner)
    user_id: Optional[str] = Field(
        default=None,
        foreign_key="users.user_id",
        index=True,
        max_length=50
    )

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
        Index('idx_incidents_embeddings_ivfflat',
              'embedding',
              postgresql_using='ivfflat',
              postgresql_with={'lists': 100},
              postgresql_ops={'embedding': 'vector_cosine_ops'}
              ),
        Index('idx_incidents_user_id', 'user_id'),
        Index('idx_incidents_user_created', 'user_id', 'created_at'),
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

    # Foreign Key to User
    user_id: Optional[str] = Field(default=None, foreign_key="users.user_id", index=True, max_length=50)
    
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
