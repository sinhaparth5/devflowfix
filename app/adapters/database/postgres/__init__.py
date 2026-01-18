from .models import (
    IncidentTable,
    FeedbackTable,
    RemediationHistoryTable,
    MetricTable,
    ConfigTable,
    UserTable,
    AuditLogTable,
    PullRequestTable,
    GitHubTokenTable,
    PRCreationLogTable,
    PRStatus,
    UserDetailsTable,
    BackgroundJobTable,
    JobStatus,
    JobType,
)

from .connection import (
    DatabaseConfig,
    DatabaseConnectionPool,
    get_connection_pool,
    get_db_session,
    get_lambda_session,
    reset_connection_pool,
)

from .repositories import (
    IncidentRepository,
    FeedbackRepository,
    RemediationHistoryRepository,
    MetricRepository,
    ConfigRepository,
)

__all__ = [
    # User (auth handled by Zitadel, sessions removed)
    "UserTable",
    "AuditLogTable",
    "UserDetailsTable",
    # Core tables
    "IncidentTable",
    "FeedbackTable",
    "RemediationHistoryTable",
    "MetricTable",
    "ConfigTable",
    "PullRequestTable",
    "GitHubTokenTable",
    "PRCreationLogTable",
    "PRStatus",
    "BackgroundJobTable",
    "JobStatus",
    "JobType",
    # Connection
    "DatabaseConfig",
    "DatabaseConnectionPool",
    "get_connection_pool",
    "get_db_session",
    "get_lambda_session",
    "reset_connection_pool",
    # Repositories
    "IncidentRepository",
    "FeedbackRepository",
    "RemediationHistoryRepository",
    "MetricRepository",
    "ConfigRepository",
]
