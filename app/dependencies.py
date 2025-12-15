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
from app.core.enums import Environment
from app.exceptions import DatabaseConnectionError, ConfigurationError

logger = structlog.get_logger()

_engine = None
_SessionLocal = None
_service_container = None


def get_engine():
    global _engine
    if _engine is None:
        try:
            _engine = create_engine(
                settings.database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections after 1 hour
                pool_timeout=30,  # Wait max 30s for connection from pool
                echo=settings.log_level == "DEBUG",
                connect_args={
                    "connect_timeout": 10,  # Connection timeout
                    "options": "-c statement_timeout=30000",  # 30s query timeout
                },
                execution_options={
                    "isolation_level": "READ COMMITTED"  # Optimal for most workloads
                }
            )
            logger.info("database_engine_created")
        except Exception as e:
            logger.error("database_engine_creation_failed", error=str(e))
            raise DatabaseConnectionError(f"Failed to create database engine: {e}")
    return _engine


def get_session_local():
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
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except HTTPException:
        # Re-raise HTTP exceptions without logging as database errors
        # These are business logic errors, not database errors
        db.close()
        raise
    except Exception as e:
        logger.error("database_session_error", error=str(e))
        db.rollback()
        raise
    finally:
        db.close()


@lru_cache()
def get_settings():
    return settings


class ServiceContainer:
    
    _instance: Optional["ServiceContainer"] = None
    
    def __init__(self):
        self._embedding_adapter = None
        self._llm_adapter = None
        self._notification_service = None
        self._analyzer_service = None
        self._decision_service = None
        self._remediator_service = None
        self._retriever_service = None
    
    @classmethod
    def get_instance(cls) -> "ServiceContainer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @property
    def embedding_adapter(self):
        if self._embedding_adapter is None:
            if settings.nvidia_api_key:
                from app.adapters.ai.nvidia.embeddings import EmbeddingAdapter
                self._embedding_adapter = EmbeddingAdapter(
                    model=settings.nvidia_embedding_model
                )
            else:
                logger.warning("nvidia_api_key_not_configured")
        return self._embedding_adapter
    
    @property
    def llm_adapter(self):
        if self._llm_adapter is None:
            if settings.nvidia_api_key:
                from app.adapters.ai.nvidia.llm import LLMAdapter
                self._llm_adapter = LLMAdapter(
                    model=settings.nvidia_llm_model
                )
            else:
                logger.warning("nvidia_api_key_not_configured")
        return self._llm_adapter
    
    @property
    def notification_service(self):
        if self._notification_service is None:
            if settings.slack_token:
                from app.adapters.external.slack.notifications import SlackNotificationAdapter
                self._notification_service = SlackNotificationAdapter(
                    settings=settings
                )
            else:
                logger.warning("slack_token_not_configured")
        return self._notification_service
    
    def get_analyzer_service(self, db: Session):
        if self._analyzer_service is None:
            if self.llm_adapter:
                from app.services.analyzer import AnalyzerService
                self._analyzer_service = AnalyzerService(
                    settings=settings,
                    llm_client=self.llm_adapter,
                    embedder_service=self.embedding_adapter,
                    retriever_service=self.get_retriever_service(db)
                )
            else:
                logger.warning("analyzer_service_not_available_no_llm")
        return self._analyzer_service
    
    def get_decision_service(self):
        if self._decision_service is None:
            from app.services.decision import DecisionService
            from app.domain.strategies.factory import StrategyFactory
            
            env_str = getattr(settings, 'environment', 'dev')
            try:
                environment = Environment(env_str)
            except ValueError:
                environment = Environment.DEVELOPMENT
            
            strategy = StrategyFactory.create(environment=environment)
            self._decision_service = DecisionService(strategy=strategy)
        return self._decision_service
    
    def get_remediator_service(self):
        if self._remediator_service is None:
            from app.services.remediator import RemediatorService
            self._remediator_service = RemediatorService(settings=settings)
        return self._remediator_service
    
    def get_retriever_service(self, db: Session):
        """
        Get RetriverService with vector repository support
        
        Args:
            db: Database session for vector operations

        Returns:
            RetrieverService with repository configured 
        """
        if not self.embedding_adapter:
            logger.warning("retriever_service_not_available_no_embedding")
            return None

        from app.services.retriever import RetrieverService
        from app.adapters.database.postgres.repositories.vector import VectorRepository

        vector_repo = VectorRepository(db)

        retriever = RetrieverService(
            embedding_adapter=self.embedding_adapter,
            vector_repository=vector_repo,
        )

        logger.info(
            "retriever_service_created_with_vector_repo",
            has_embedding=True,
            has_vector_repo=True,
        )

        return retriever


def get_service_container() -> ServiceContainer:
    return ServiceContainer.get_instance()


def get_incident_repository(db: Session = Depends(get_db)):
    from app.adapters.database.postgres.repositories.incident import IncidentRepository
    return IncidentRepository(db)


def get_feedback_repository(db: Session = Depends(get_db)):
    from app.adapters.database.postgres.repositories.feedback import FeedbackRepository
    return FeedbackRepository(db)


def get_analytics_repository(db: Session = Depends(get_db)):
    from app.adapters.database.postgres.repositories.analytics import AnalyticsRepository
    return AnalyticsRepository(db)


def get_vector_repository(db: Session = Depends(get_db)):
    from app.adapters.database.postgres.repositories.vector import VectorRepository
    return VectorRepository(db)


def get_event_processor(db: Session = Depends(get_db)):
    from app.services.event_processor import EventProcessor
    from app.adapters.database.postgres.repositories.incident import IncidentRepository
    from app.adapters.database.postgres.repositories.vector import VectorRepository
    
    container = get_service_container()
    
    incident_repo = IncidentRepository(db)
    vector_repo = VectorRepository(db)
    
    env_str = getattr(settings, 'environment', 'dev')
    try:
        environment = Environment(env_str)
    except ValueError:
        environment = Environment.DEVELOPMENT
    
    return EventProcessor(
        incident_repository=incident_repo,
        vector_repository=vector_repo,
        analyzer_service=container.get_analyzer_service(db),
        decision_service=container.get_decision_service(),
        remediator_service=container.get_remediator_service(),
        retriever_service=container.get_retriever_service(db),
        notification_service=container.notification_service,
        embedding_adapter=container.embedding_adapter,
        default_environment=environment,
        enable_notifications=getattr(settings, 'enable_notifications', True),
        enable_auto_remediation=getattr(settings, 'enable_auto_remediation', True),
    )


def get_analyzer_service():
    container = get_service_container()
    return container.get_analyzer_service()


def get_classifier_service():
    pass


def get_remediator_service():
    container = get_service_container()
    return container.get_remediator_service()


def get_retriever_service():
    container = get_service_container()
    return container.get_retriever_service()


def get_decision_service():
    container = get_service_container()
    return container.get_decision_service()


def get_embedder_service():
    container = get_service_container()
    return container.embedding_adapter


def get_event_processor_service():
    pass


def get_github_client():
    if not settings.github_token:
        raise ConfigurationError("github_token", "GitHub token not configured")
    pass


def get_argocd_client():
    if not settings.argocd_server or not settings.argocd_token:
        raise ConfigurationError("argocd", "ArgoCD credentials not configured")
    pass


def get_kubernetes_client():
    pass


def get_slack_client():
    if not settings.slack_token:
        raise ConfigurationError("slack_token", "Slack token not configured")
    pass


def get_pagerduty_client():
    if not settings.pagerduty_api_key:
        logger.warning("pagerduty_not_configured")
        return None
    pass


async def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return "system"
    return None


async def require_authentication(
    current_user: Annotated[Optional[str], Depends(get_current_user)]
) -> str:
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
    return x_request_id


async def get_pagination_params(
    skip: int = 0,
    limit: int = 100,
) -> dict:
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
    if not settings.github_webhook_secret:
        logger.warning("github_webhook_secret_not_configured")
        return {"validated": False, "event": x_github_event}
    
    if not x_hub_signature_256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing GitHub signature",
        )
    
    return {"validated": True, "event": x_github_event}


async def validate_slack_request(
    x_slack_signature: Annotated[Optional[str], Header()] = None,
    x_slack_request_timestamp: Annotated[Optional[str], Header()] = None,
) -> dict:
    if not settings.slack_signing_secret:
        logger.warning("slack_signing_secret_not_configured")
        return {"validated": False}
    
    if not x_slack_signature or not x_slack_request_timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature or timestamp",
        )
    
    return {"validated": True}
