# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Generator, Optional, Annotated
from functools import lru_cache
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import structlog

from app.core.config import settings
from app.exceptions import DatabaseConnectionError, ConfigurationError

logger = structlog.get_logger()

# Create SQLAlchemy engine
_engine = None
_SessionLocal = None

def get_engine():
    """
    Get or create database engine.
    
    Singleton pattern for engine creation.
    """
    global _engine
    if _engine is None:
        try:
            _engine = create_engine(
                settings.database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,  # Verify connections before using
                echo=settings.log_level == "DEBUG",
            )
            logger.info("database_engine_created")
        except Exception as e:
            logger.error("database_engine_creation_failed", error=str(e))
            raise DatabaseConnectionError(f"Failed to create database engine: {e}")
    return _engine

def get_session_local():
    """
    Get or create SessionLocal factory.
    
    Singleton pattern for SessionLocal creation.
    """
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
    return _SessionLocal

def get_db() -> Generator[Session, None, None]:
    """
    Get database session.
    
    FastAPI dependency that provides a database session.
    Automatically handles session lifecycle and cleanup.
    
    Yields:
        Database session
        
    Example:
        @app.get("/incidents")
        def list_incidents(db: Session = Depends(get_db)):
            return db.query(IncidentTable).all()
    """
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error("database_session_error", error=str(e))
        db.rollback()
        raise
    finally:
        db.close()

@lru_cache()
def get_settings():
    """
    Get application settings.
    
    Cached to avoid reloading settings on every request.
    
    Returns:
        Application settings
    """
    return settings

# These will be populated as services are implemented
def get_incident_repository(db: Session = Depends(get_db)):
    """
    Get incident repository.
    
    Args:
        db: Database session
        
    Returns:
        IncidentRepository instance
    """
    from app.adapters.database.postgres.repositories.incident import IncidentRepository
    return IncidentRepository(db)

def get_feedback_repository(db: Session = Depends(get_db)):
    """
    Get feedback repository.
    
    Args:
        db: Database session
        
    Returns:
        FeedbackRepository instance
    """
    from app.adapters.database.postgres.repositories.feedback import FeedbackRepository
    return FeedbackRepository(db)

def get_analytics_repository(db: Session = Depends(get_db)):
    """
    Get analytics repository.
    
    Args:
        db: Database session
        
    Returns:
        AnalyticsRepository instance
    """
    from app.adapters.database.postgres.repositories.analytics import AnalyticsRepository
    return AnalyticsRepository(db)

def get_vector_repository(db: Session = Depends(get_db)):
    """
    Get vector repository for RAG operations.
    
    Args:
        db: Database session
        
    Returns:
        VectorRepository instance
    """
    from app.adapters.database.postgres.repositories.vertor import VectorRepository
    return VectorRepository(db)

# Service layer dependencies
def get_analyzer_service():
    """
    Get analyzer service.
    
    Returns:
        AnalyzerService instance
    """
    # TODO: Implement when services are ready
    # from app.services.analyzer import AnalyzerService
    # return AnalyzerService(...)
    pass

def get_classifier_service():
    """
    Get classifier service.
    
    Returns:
        ClassifierService instance
    """
    # TODO: Implement when services are ready
    # from app.services.classifier import ClassifierService
    # return ClassifierService(...)
    pass

def get_remediator_service():
    """
    Get remediator service.
    
    Returns:
        RemediatorService instance
    """
    # TODO: Implement when services are ready
    # from app.services.remediator import RemediatorService
    # return RemediatorService(...)
    pass

def get_retriever_service():
    """
    Get retriever service for RAG.
    
    Returns:
        RetrieverService instance
    """
    # TODO: Implement when services are ready
    # from app.services.retriever import RetrieverService
    # return RetrieverService(...)
    pass

def get_embedder_service():
    """
    Get embedder service.
    
    Returns:
        EmbedderService instance
    """
    # TODO: Implement when services are ready
    # from app.services.embedder import EmbedderService
    # return EmbedderService(...)
    pass

def get_event_processor_service():
    """
    Get event processor service.
    
    Returns:
        EventProcessorService instance
    """
    # TODO: Implement when services are ready
    # from app.services.event_processor import EventProcessorService
    # return EventProcessorService(...)
    pass

# External adapter dependencies
def get_github_client():
    """
    Get GitHub client.
    
    Returns:
        GitHubClient instance
    """
    if not settings.github_token:
        raise ConfigurationError("github_token", "GitHub token not configured")
    
    # TODO: Implement when adapters are ready
    # from app.adapters.external.github.client import GitHubClient
    # return GitHubClient(token=settings.github_token)
    pass

def get_argocd_client():
    """
    Get ArgoCD client.
    
    Returns:
        ArgoCDClient instance
    """
    if not settings.argocd_server or not settings.argocd_token:
        raise ConfigurationError("argocd", "ArgoCD credentials not configured")
    
    # TODO: Implement when adapters are ready
    # from app.adapters.external.argocd.client import ArgoCDClient
    # return ArgoCDClient(server=settings.argocd_server, token=settings.argocd_token)
    pass

def get_kubernetes_client():
    """
    Get Kubernetes client.
    
    Returns:
        KubernetesClient instance
    """
    # TODO: Implement when adapters are ready
    # from app.adapters.external.kubernetes.client import KubernetesClient
    # return KubernetesClient(kubeconfig_path=settings.kubeconfig_path)
    pass

def get_slack_client():
    """
    Get Slack client.
    
    Returns:
        SlackClient instance
    """
    if not settings.slack_token:
        raise ConfigurationError("slack_token", "Slack token not configured")
    
    # TODO: Implement when adapters are ready
    # from app.adapters.external.slack.client import SlackClient
    # return SlackClient(token=settings.slack_token)
    pass

def get_pagerduty_client():
    """
    Get PagerDuty client.
    
    Returns:
        PagerDutyClient instance
    """
    if not settings.pagerduty_api_key:
        logger.warning("pagerduty_not_configured")
        return None
    
    # TODO: Implement when adapters are ready
    # from app.adapters.external.pagerduty.client import PagerDutyClient
    # return PagerDutyClient(api_key=settings.pagerduty_api_key)
    pass

async def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
) -> Optional[str]:
    """
    Get current authenticated user.
    
    For now, this is a placeholder. In production, implement proper auth.
    
    Args:
        authorization: Authorization header
        
    Returns:
        Username or None if not authenticated
    """
    # TODO: Implement proper authentication
    # For now, just return a placeholder or parse from header
    if authorization and authorization.startswith("Bearer "):
        # Extract user from token (implement JWT validation here)
        return "system"  # Placeholder
    return None

async def require_authentication(
    current_user: Annotated[Optional[str], Depends(get_current_user)]
) -> str:
    """
    Require authentication for endpoint.
    
    Args:
        current_user: Current user from auth dependency
        
    Returns:
        Username
        
    Raises:
        HTTPException: If not authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user

async def get_request_id(
    x_request_id: Annotated[Optional[str], Header()] = None,
) -> Optional[str]:
    """
    Get request ID from header or state.
    
    Args:
        x_request_id: Request ID from header
        
    Returns:
        Request ID
    """
    return x_request_id

async def get_pagination_params(
    skip: int = 0,
    limit: int = 100,
) -> dict:
    """
    Get pagination parameters.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        Dictionary with skip and limit
    """
    # Validate and cap limit
    if limit > 1000:
        limit = 1000
    if skip < 0:
        skip = 0
        
    return {"skip": skip, "limit": limit}

async def get_common_filters(
    source: Optional[str] = None,
    severity: Optional[str] = None,
    outcome: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Get common filter parameters.
    
    Args:
        source: Filter by source
        severity: Filter by severity
        outcome: Filter by outcome
        start_date: Filter by start date
        end_date: Filter by end date
        
    Returns:
        Dictionary with filters
    """
    filters = {}
    
    if source:
        filters["source"] = source
    if severity:
        filters["severity"] = severity
    if outcome:
        filters["outcome"] = outcome
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date
        
    return filters

async def validate_github_webhook(
    x_hub_signature_256: Annotated[Optional[str], Header()] = None,
    x_github_event: Annotated[Optional[str], Header()] = None,
) -> dict:
    """
    Validate GitHub webhook signature.
    
    Args:
        x_hub_signature_256: GitHub webhook signature
        x_github_event: GitHub event type
        
    Returns:
        Dictionary with validation results
        
    Raises:
        HTTPException: If validation fails
    """
    if not settings.github_webhook_secret:
        logger.warning("github_webhook_secret_not_configured")
        return {"validated": False, "event": x_github_event}
    
    if not x_hub_signature_256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing GitHub signature",
        )
    
    # TODO: Implement actual signature validation
    # For now, just return the event type
    return {"validated": True, "event": x_github_event}

async def validate_slack_request(
    x_slack_signature: Annotated[Optional[str], Header()] = None,
    x_slack_request_timestamp: Annotated[Optional[str], Header()] = None,
) -> dict:
    """
    Validate Slack request signature.
    
    Args:
        x_slack_signature: Slack signature
        x_slack_request_timestamp: Request timestamp
        
    Returns:
        Dictionary with validation results
        
    Raises:
        HTTPException: If validation fails
    """
    if not settings.slack_signing_secret:
        logger.warning("slack_signing_secret_not_configured")
        return {"validated": False}
    
    if not x_slack_signature or not x_slack_request_timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature or timestamp",
        )
    
    # TODO: Implement actual signature validation
    return {"validated": True}