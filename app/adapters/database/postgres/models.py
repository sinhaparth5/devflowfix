# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON, Relationship
from sqlalchemy import Text, Index, desc, ForeignKey, ARRAY, String
from pgvector.sqlalchemy import Vector
import enum

class PRStatus(str, enum.Enum):
    """Status of an automated PR."""
    CREATED = "created"
    OPEN = "open"
    DRAFT = "draft"
    REVIEW_REQUESTED = "review_requested"
    APPROVED = "approved"
    MERGED = "merged"
    CLOSED = "closed"
    FAILED = "failed"

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
    hashed_password: Optional[str] = Field(default=None, sa_column=Column(Text))

    # OAuth Authentication
    oauth_provider: Optional[str] = Field(default=None, max_length=50, index=True)  # 'google', 'github', or None
    oauth_id: Optional[str] = Field(default=None, max_length=255, index=True)  # Unique ID from OAuth provider

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

    # GitHub Webhook Secret (dynamically generated, unique per user)
    github_webhook_secret: Optional[str] = Field(default=None, sa_column=Column(Text))
    github_username: Optional[str] = Field(default=None, max_length=50)

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
        Index('idx_users_oauth', 'oauth_provider', 'oauth_id'),
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


class LogLevel(str, enum.Enum):
    """Log severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(str, enum.Enum):
    """Application log categories."""
    WEBHOOK = "webhook"
    LLM = "llm"
    ANALYSIS = "analysis"
    REMEDIATION = "remediation"
    GITHUB = "github"
    DATABASE = "database"
    SYSTEM = "system"


class ApplicationLogTable(SQLModel, table=True):
    """
    Application/Workflow log table.
    Tracks the entire CI/CD failure detection and remediation workflow.
    """
    __tablename__ = "application_logs"

    # Primary Key
    log_id: str = Field(primary_key=True, max_length=50)

    # Association
    incident_id: Optional[str] = Field(default=None, foreign_key="incidents.incident_id", index=True, max_length=50)
    user_id: Optional[str] = Field(default=None, foreign_key="users.user_id", index=True, max_length=50)
    session_id: Optional[str] = Field(default=None, max_length=50)

    # Log Classification
    level: LogLevel = Field(default=LogLevel.INFO, index=True)
    category: LogCategory = Field(default=LogCategory.SYSTEM, index=True)

    # Message
    message: str = Field(sa_column=Column(Text))

    # Workflow Stage (e.g., "webhook_received", "llm_analyzing", "remediation_executing")
    stage: Optional[str] = Field(default=None, max_length=100, index=True)

    # Details (JSON for flexible data storage)
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Error Information (if applicable)
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    stack_trace: Optional[str] = Field(default=None, sa_column=Column(Text))

    # LLM Specific (if applicable)
    llm_model: Optional[str] = Field(default=None, max_length=100)
    llm_tokens_used: Optional[int] = Field(default=None)
    llm_response_time_ms: Optional[int] = Field(default=None)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    duration_ms: Optional[int] = Field(default=None)  # For operations with measurable duration

    __table_args__ = (
        Index('idx_app_logs_incident', 'incident_id'),
        Index('idx_app_logs_user', 'user_id'),
        Index('idx_app_logs_level_created', 'level', desc('created_at')),
        Index('idx_app_logs_category_created', 'category', desc('created_at')),
        Index('idx_app_logs_stage', 'stage'),
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

    # Vector Embedding for RAG (4096 dimensions for nvidia/nv-embed-v1)
    embedding: Optional[list] = Field(
        default=None,
        sa_column=Column(Vector(4096))
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

class PullRequestTable(SQLModel, table=True):
    """
    Stores metadata for automatically created pull requests.
    
    Tracks:
    - PR creation details
    - Incident association
    - Status and lifecycle
    - Review/merge progress
    """
    __tablename__ = "pull_requests"

    id: str = Field(primary_key=True, max_length=36)
    incident_id: str = Field(index=True, max_length=36)
    
    # Repository info
    repository_owner: str = Field(index=True, max_length=255)
    repository_name: str = Field(index=True, max_length=255)
    repository_full: str = Field(max_length=512)  # "owner/repo"
    
    # PR details from GitHub
    pr_number: int
    pr_url: str = Field(max_length=512)
    branch_name: str = Field(max_length=255)
    base_branch: str = Field(default="main", max_length=255)
    
    # PR metadata
    title: str = Field(max_length=512)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Status and lifecycle
    status: PRStatus = Field(default=PRStatus.CREATED)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    merged_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(default=None)
    
    # Files and changes
    files_changed: Optional[int] = Field(default=None)
    additions: Optional[int] = Field(default=None)
    deletions: Optional[int] = Field(default=None)
    commits_count: Optional[int] = Field(default=None)
    
    # Review status
    approved_by: Optional[str] = Field(default=None, max_length=255)  # GitHub username(s)
    review_comments_count: int = Field(default=0)
    has_conflicts: bool = Field(default=False)
    
    # Failure analysis
    failure_type: str = Field(max_length=100)
    root_cause: Optional[str] = Field(default=None, max_length=512)
    confidence_score: Optional[float] = Field(default=None)
    
    # Additional metadata
    extra_metadata: Optional[dict] = Field(default=None, sa_column=Column(Text))  # Extra data as JSON
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))  # If PR creation failed
    
    def __repr__(self):
        return (
            f"<PullRequest("
            f"id={self.id}, "
            f"incident={self.incident_id}, "
            f"pr=#{self.pr_number}, "
            f"repo={self.repository_full}, "
            f"status={self.status.value}, "
            f"branch={self.branch_name}"
            f")>"
        )


class GitHubTokenTable(SQLModel, table=True):
    """
    Stores GitHub access tokens for external repositories.

    Allows DevFlowFix to create PRs in different repos using their own tokens.
    Supports both:
    - Repository-specific tokens (more secure)
    - Organization-level tokens (simpler but broader)

    Each user has their own set of tokens for security.
    """
    __tablename__ = "github_tokens"

    id: str = Field(primary_key=True, max_length=255)

    # User association - CRITICAL for security
    user_id: str = Field(foreign_key="users.user_id", index=True, max_length=50)

    # Repository identification
    repository_owner: str = Field(index=True, max_length=255)
    repository_name: Optional[str] = Field(default=None, index=True, max_length=255)  # NULL = org-level token
    repository_full: str = Field(index=True, max_length=512)  # "owner/repo" or "owner/*" - not unique anymore
    
    # Token details
    token: str = Field(max_length=1024)  # Encrypted token value
    is_encrypted: bool = Field(default=True)
    
    # Token metadata
    token_type: str = Field(default="pat", max_length=50)  # "pat" = Personal Access Token, "app" = GitHub App
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = Field(default=None)
    
    # Permissions
    scopes: Optional[str] = Field(default=None, max_length=512)  # Comma-separated: repo,workflow,contents
    permissions_json: Optional[dict] = Field(default=None, sa_column=Column(Text))
    
    # Status
    is_active: bool = Field(default=True)
    is_valid: bool = Field(default=True)
    
    # Metadata
    description: Optional[str] = Field(default=None, max_length=512)
    created_by: Optional[str] = Field(default=None, max_length=255)  # User who added this token
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    def __repr__(self):
        masked_token = self.token[:10] + "..." if self.token else "***"
        return (
            f"<GitHubToken("
            f"id={self.id}, "
            f"repo={self.repository_full}, "
            f"token={masked_token}, "
            f"active={self.is_active}, "
            f"valid={self.is_valid}"
            f")>"
        )


class PRCreationLogTable(SQLModel, table=True):
    """
    Detailed logs of PR creation attempts.
    
    Useful for debugging and auditing PR creation workflows.
    """
    __tablename__ = "pr_creation_logs"

    id: str = Field(primary_key=True, max_length=36)
    
    # Association
    incident_id: str = Field(index=True, max_length=36)
    pr_id: Optional[str] = Field(default=None, max_length=36)  # NULL if creation failed
    
    # Request details
    repository_full: str = Field(max_length=512)
    branch_name: str = Field(max_length=255)
    
    # Solution details
    failure_type: str = Field(max_length=100)
    root_cause: Optional[str] = Field(default=None, max_length=512)
    files_to_change: int = Field(default=0)
    
    # Attempt details
    attempt_number: int = Field(default=1)
    status: str = Field(max_length=50)  # "success", "failed", "partial"
    duration_ms: Optional[int] = Field(default=None)
    
    # Results
    created_at: datetime = Field(default_factory=datetime.utcnow)
    pr_url: Optional[str] = Field(default=None, max_length=512)
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_type: Optional[str] = Field(default=None, max_length=100)
    
    # Additional metadata
    extra_metadata: Optional[dict] = Field(default=None, sa_column=Column(Text))
    
    def __repr__(self):
        return (
            f"<PRCreationLog("
            f"id={self.id}, "
            f"incident={self.incident_id}, "
            f"pr={self.pr_id}, "
            f"status={self.status}, "
            f"repo={self.repository_full}"
            f")>"
        )

class UserDetailsTable(SQLModel, table=True):
    """
    User details table.

    Stores additional user profile information and social links.
    """

    __tablename__ = "user_details"

    # Primary Key
    user_id: str = Field(
        foreign_key="users.user_id",
        primary_key=True,
        max_length=50
    )

    # Location Information
    country: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    postal_code: Optional[str] = Field(default=None, max_length=20)

    # Social Media Links
    facebook_link: Optional[str] = Field(default=None, max_length=500)
    twitter_link: Optional[str] = Field(default=None, max_length=500)
    linkedin_link: Optional[str] = Field(default=None, max_length=500)
    instagram_link: Optional[str] = Field(default=None, max_length=500)
    github_link: Optional[str] = Field(default=None, max_length=500)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index('idx_user_details_country_city', 'country', 'city'),
    )


class JobStatus(str, enum.Enum):
    """Background job status."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, enum.Enum):
    """Types of background jobs."""
    INCIDENT_ANALYSIS = "incident_analysis"
    INCIDENT_REANALYSIS = "incident_reanalysis"
    EXPORT_CSV = "export_csv"
    EXPORT_PDF = "export_pdf"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
    PR_CREATION = "pr_creation"


class BackgroundJobTable(SQLModel, table=True):
    """
    Background jobs table.

    Tracks long-running asynchronous operations like exports, bulk updates, and PR creation.
    Provides status tracking and progress monitoring for users.
    """
    __tablename__ = "background_jobs"

    # Primary Key
    job_id: str = Field(primary_key=True, max_length=50)

    # Foreign Key to User (owner)
    user_id: str = Field(
        foreign_key="users.user_id",
        index=True,
        max_length=50
    )

    # Job Classification
    job_type: JobType = Field(index=True)
    status: JobStatus = Field(default=JobStatus.QUEUED, index=True)

    # Progress Tracking
    progress: int = Field(default=0, ge=0, le=100)
    current_step: Optional[str] = Field(default=None, max_length=255)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None, index=True)
    estimated_completion: Optional[datetime] = Field(default=None)

    # Results
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Parameters (input data for the job)
    parameters: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Result File (for exports)
    result_file_path: Optional[str] = Field(default=None, max_length=512)
    result_file_size: Optional[int] = Field(default=None)
    result_file_type: Optional[str] = Field(default=None, max_length=50)

    # Job Metadata
    job_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    __table_args__ = (
        Index('idx_jobs_user_created', 'user_id', desc('created_at')),
        Index('idx_jobs_status_created', 'status', desc('created_at')),
        Index('idx_jobs_type_status', 'job_type', 'status'),
    )

class OAuthConnectionTable(SQLModel, table=True):
    """
    OAuth Connection Table

    Stores OAuth connections for GitHub, GitLab, etc.
    Tokens are encrypted at rest for security.
    """
    __tablename__ = "oauth_connections"

    # Primary Key - oac_ prefix + 32 hex chars = 36 total
    id: str = Field(primary_key=True, max_length=36)

    # Foreign Key to User
    user_id: str = Field(
        foreign_key="users.user_id",
        index=True,
        max_length=50
    )

    # Provider Information
    provider: str = Field(max_length=20, index=True)  # 'github' or 'gitlab'
    provider_user_id: str = Field(max_length=100, index=True)
    provider_username: str = Field(max_length=100)

    # OAuth Tokens (encrypted)
    access_token: str = Field(sa_column=Column(Text))  # Encrypted OAuth token
    refresh_token: Optional[str] = Field(default=None, sa_column=Column(Text))
    token_expires_at: Optional[datetime] = Field(default=None)

    # Scopes
    scopes: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))

    # Status
    is_active: bool = Field(default=True, index=True)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index('idx_oauth_user_provider', 'user_id', 'provider', unique=True),
        Index('idx_oauth_provider_user', 'provider', 'provider_user_id'),
    )


class RepositoryConnectionTable(SQLModel, table=True):
    """
    Repository Connection Table

    Tracks which repositories are connected and monitored.
    Links to OAuth connections for API access.
    """
    __tablename__ = "repository_connections"

    # Primary Key - rpc_ prefix + 32 hex chars = 36 total
    id: str = Field(primary_key=True, max_length=36)

    # Foreign Keys
    user_id: str = Field(
        foreign_key="users.user_id",
        index=True,
        max_length=50
    )
    oauth_connection_id: str = Field(
        foreign_key="oauth_connections.id",
        index=True,
        max_length=36
    )

    # Repository Information
    provider: str = Field(max_length=20, index=True)  # 'github' or 'gitlab'
    repository_id: str = Field(max_length=100)  # Provider's repo ID
    repository_full_name: str = Field(max_length=255, index=True)  # owner/repo
    repository_name: str = Field(max_length=255)
    owner_name: str = Field(max_length=255)
    is_private: bool = Field(default=False)

    # Webhook Information
    webhook_id: Optional[str] = Field(default=None, max_length=100)
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    webhook_secret: Optional[str] = Field(default=None, max_length=512)  # Encrypted secret
    webhook_events: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # ['workflow_run', 'pull_request', 'push']
    webhook_status: Optional[str] = Field(default=None, max_length=50)  # 'active', 'inactive', 'failed'
    webhook_created_at: Optional[datetime] = Field(default=None)
    webhook_last_delivery_at: Optional[datetime] = Field(default=None)

    # Configuration
    is_enabled: bool = Field(default=True, index=True)
    auto_pr_enabled: bool = Field(default=True)
    auto_fix_enabled: bool = Field(default=True)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_event_at: Optional[datetime] = Field(default=None)

    # Metadata
    repository_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    __table_args__ = (
        Index('idx_repo_user_full_name', 'user_id', 'repository_full_name', unique=True),
        Index('idx_repo_oauth_enabled', 'oauth_connection_id', 'is_enabled'),
    )


class WorkflowRunTable(SQLModel, table=True):
    """
    Workflow Run Tracking Table

    Tracks GitHub/GitLab workflow runs associated with incidents.
    """
    __tablename__ = "workflow_runs"

    # Primary Key - wfr_ prefix + 32 hex chars = 36 total
    id: str = Field(primary_key=True, max_length=36)

    # Foreign Keys
    incident_id: Optional[str] = Field(
        default=None,
        foreign_key="incidents.incident_id",
        index=True,
        max_length=50
    )
    repository_connection_id: str = Field(
        foreign_key="repository_connections.id",
        index=True,
        max_length=36
    )

    # Workflow Run Information
    provider: str = Field(default="github", max_length=20)
    run_id: str = Field(max_length=100, index=True)
    workflow_name: str = Field(max_length=255)
    workflow_id: Optional[str] = Field(default=None, max_length=100)
    workflow_path: Optional[str] = Field(default=None, max_length=512)

    # Status
    status: str = Field(max_length=50)  # queued, in_progress, completed
    conclusion: Optional[str] = Field(default=None, max_length=50)  # success, failure, cancelled

    # Run Metadata
    run_number: Optional[int] = Field(default=None)
    run_attempt: Optional[int] = Field(default=None)
    branch: Optional[str] = Field(default=None, max_length=255)  # head_branch alias
    head_branch: Optional[str] = Field(default=None, max_length=255)
    commit_sha: Optional[str] = Field(default=None, max_length=40)  # head_sha alias
    head_sha: Optional[str] = Field(default=None, max_length=40)
    commit_message: Optional[str] = Field(default=None, max_length=1000)
    author: Optional[str] = Field(default=None, max_length=255)
    run_url: Optional[str] = Field(default=None, max_length=500)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional Data
    event_payload: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    run_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    __table_args__ = (
        Index('idx_wfrun_repo_run_id', 'repository_connection_id', 'run_id', unique=True),
        Index('idx_wfrun_incident', 'incident_id'),
        Index('idx_wfrun_status', 'status', 'conclusion'),
    )
