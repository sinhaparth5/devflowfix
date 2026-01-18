# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Application logger utility for tracking workflow steps.
Provides easy-to-use functions for logging throughout the CI/CD detection pipeline.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4
from sqlalchemy.orm import Session
import structlog
import traceback

from app.adapters.database.postgres.models import ApplicationLogTable, LogLevel, LogCategory
from app.adapters.database.postgres.repositories.logs import ApplicationLogRepository

logger = structlog.get_logger(__name__)


class AppLogger:
    """
    Helper class for creating application logs throughout the workflow.

    Usage:
        app_logger = AppLogger(db, incident_id="inc_123", user_id="user_456")
        app_logger.webhook_received("GitHub workflow failed", {"pr": 123})
        app_logger.llm_start("Analyzing error logs", model="gpt-4")
        app_logger.error("LLM timeout", error_obj=exception)
    """

    def __init__(
        self,
        db: Session,
        incident_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.db = db
        self.repo = ApplicationLogRepository(db)
        self.incident_id = incident_id
        self.user_id = user_id
        self.session_id = session_id
        self.start_time = datetime.now(timezone.utc)

    def _create_log(
        self,
        level: LogLevel,
        category: LogCategory,
        message: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        stack_trace: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_tokens_used: Optional[int] = None,
        llm_response_time_ms: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> ApplicationLogTable:
        """Internal method to create and save a log entry."""
        try:
            log = ApplicationLogTable(
                log_id=f"log_{uuid4().hex[:12]}",
                incident_id=self.incident_id,
                user_id=self.user_id,
                session_id=self.session_id,
                level=level,
                category=category,
                message=message,
                stage=stage,
                details=details or {},
                error=error,
                stack_trace=stack_trace,
                llm_model=llm_model,
                llm_tokens_used=llm_tokens_used,
                llm_response_time_ms=llm_response_time_ms,
                created_at=datetime.now(timezone.utc),
                duration_ms=duration_ms,
            )
            return self.repo.create(log)
        except Exception as e:
            logger.error("failed_to_create_application_log", error=str(e), message=message)
            # Don't raise - logging failure shouldn't break the main workflow
            return None

    # Webhook logs

    def webhook_received(self, message: str, details: Optional[Dict] = None):
        """Log webhook received event."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.WEBHOOK,
            message=message,
            stage="webhook_received",
            details=details,
        )

    def webhook_parsed(self, message: str, details: Optional[Dict] = None):
        """Log webhook parsing success."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.WEBHOOK,
            message=message,
            stage="webhook_parsed",
            details=details,
        )

    # LLM logs

    def llm_start(self, message: str, model: str, details: Optional[Dict] = None):
        """Log LLM analysis started."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.LLM,
            message=message,
            stage="llm_analyzing",
            llm_model=model,
            details=details,
        )

    def llm_complete(
        self,
        message: str,
        model: str,
        tokens_used: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        details: Optional[Dict] = None,
    ):
        """Log LLM analysis completed."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.LLM,
            message=message,
            stage="llm_complete",
            llm_model=model,
            llm_tokens_used=tokens_used,
            llm_response_time_ms=response_time_ms,
            details=details,
        )

    # Analysis logs

    def analysis_start(self, message: str, details: Optional[Dict] = None):
        """Log analysis started."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.ANALYSIS,
            message=message,
            stage="analysis_started",
            details=details,
        )

    def analysis_complete(self, message: str, details: Optional[Dict] = None):
        """Log analysis completed."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.ANALYSIS,
            message=message,
            stage="analysis_complete",
            details=details,
        )

    # Remediation logs

    def remediation_start(self, message: str, details: Optional[Dict] = None):
        """Log remediation started."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.REMEDIATION,
            message=message,
            stage="remediation_started",
            details=details,
        )

    def remediation_executing(self, message: str, details: Optional[Dict] = None):
        """Log remediation executing."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.REMEDIATION,
            message=message,
            stage="remediation_executing",
            details=details,
        )

    def remediation_complete(self, message: str, duration_ms: Optional[int] = None, details: Optional[Dict] = None):
        """Log remediation completed."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.REMEDIATION,
            message=message,
            stage="remediation_complete",
            duration_ms=duration_ms,
            details=details,
        )

    # GitHub logs

    def github_pr_creating(self, message: str, details: Optional[Dict] = None):
        """Log GitHub PR creation started."""
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.GITHUB,
            message=message,
            stage="github_pr_creating",
            details=details,
        )

    def github_pr_created(self, message: str, pr_url: str, details: Optional[Dict] = None):
        """Log GitHub PR created successfully."""
        if details is None:
            details = {}
        details["pr_url"] = pr_url
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.GITHUB,
            message=message,
            stage="github_pr_created",
            details=details,
        )

    # Error logs

    def error(
        self,
        message: str,
        error_obj: Optional[Exception] = None,
        category: LogCategory = LogCategory.SYSTEM,
        stage: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """Log an error."""
        error_str = str(error_obj) if error_obj else None
        stack = traceback.format_exc() if error_obj else None

        return self._create_log(
            level=LogLevel.ERROR,
            category=category,
            message=message,
            stage=stage or "error",
            error=error_str,
            stack_trace=stack,
            details=details,
        )

    def warning(
        self,
        message: str,
        category: LogCategory = LogCategory.SYSTEM,
        stage: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """Log a warning."""
        return self._create_log(
            level=LogLevel.WARNING,
            category=category,
            message=message,
            stage=stage,
            details=details,
        )

    def info(
        self,
        message: str,
        category: LogCategory = LogCategory.SYSTEM,
        stage: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """Log info message."""
        return self._create_log(
            level=LogLevel.INFO,
            category=category,
            message=message,
            stage=stage,
            details=details,
        )

    def debug(
        self,
        message: str,
        category: LogCategory = LogCategory.SYSTEM,
        stage: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """Log debug message."""
        return self._create_log(
            level=LogLevel.DEBUG,
            category=category,
            message=message,
            stage=stage,
            details=details,
        )

    def workflow_complete(self, message: str = "Workflow completed successfully", details: Optional[Dict] = None):
        """Log workflow completion."""
        duration_ms = int((datetime.now(timezone.utc) - self.start_time).total_seconds() * 1000)
        return self._create_log(
            level=LogLevel.INFO,
            category=LogCategory.SYSTEM,
            message=message,
            stage="workflow_complete",
            duration_ms=duration_ms,
            details=details,
        )


# Standalone utility functions for quick logging

def quick_log(
    db: Session,
    message: str,
    level: str = "info",
    category: str = "system",
    incident_id: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict] = None,
):
    """
    Quick logging function for one-off logs without creating an AppLogger instance.

    Usage:
        quick_log(db, "Something happened", level="error", incident_id="inc_123")
    """
    level_map = {
        "debug": LogLevel.DEBUG,
        "info": LogLevel.INFO,
        "warning": LogLevel.WARNING,
        "error": LogLevel.ERROR,
        "critical": LogLevel.CRITICAL,
    }

    category_map = {
        "webhook": LogCategory.WEBHOOK,
        "llm": LogCategory.LLM,
        "analysis": LogCategory.ANALYSIS,
        "remediation": LogCategory.REMEDIATION,
        "github": LogCategory.GITHUB,
        "database": LogCategory.DATABASE,
        "system": LogCategory.SYSTEM,
    }

    app_logger = AppLogger(db, incident_id=incident_id, user_id=user_id)
    return app_logger._create_log(
        level=level_map.get(level.lower(), LogLevel.INFO),
        category=category_map.get(category.lower(), LogCategory.SYSTEM),
        message=message,
        details=details,
    )
