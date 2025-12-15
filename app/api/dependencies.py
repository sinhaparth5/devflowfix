# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Generator, Optional
from functools import lru_cache
import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import Settings, get_settings as _get_settings
from app.services.event_processor import EventProcessor
from app.services.decision import DecisionService
from app.services.analyzer import AnalyzerService
from app.services.remediator import RemediatorService
from app.services.retriever import RetrieverService
from app.domain.strategies.factory import StrategyFactory
from app.adapters.database.postgres.repositories.incident import IncidentRepository
from app.adapters.database.postgres.repositories.vector import VectorRepository
from app.adapters.external.slack.notifications import SlackNotificationAdapter
from app.adapters.ai.nvidia import EmbeddingAdapter, LLMAdapter
from app.core.enums import Environment

logger = structlog.get_logger(__name__)


@lru_cache()
def get_settings() -> Settings:
    return _get_settings()


@lru_cache()
def get_engine():
    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def get_session_factory():
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class ServiceContainer:
    
    _instance: Optional["ServiceContainer"] = None
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._event_processor: Optional[EventProcessor] = None
        self._decision_service: Optional[DecisionService] = None
        self._analyzer_service: Optional[AnalyzerService] = None
        self._remediator_service: Optional[RemediatorService] = None
        self._retriever_service: Optional[RetrieverService] = None
        self._notification_service: Optional[SlackNotificationAdapter] = None
        self._embedding_adapter: Optional[EmbeddingAdapter] = None
        self._llm_adapter: Optional[LLMAdapter] = None
    
    @classmethod
    def get_instance(cls) -> "ServiceContainer":
        if cls._instance is None:
            cls._instance = cls(get_settings())
        return cls._instance
    
    @property
    def embedding_adapter(self) -> EmbeddingAdapter:
        if self._embedding_adapter is None:
            self._embedding_adapter = EmbeddingAdapter(
                api_key=self.settings.NVIDIA_API_KEY,
            )
        return self._embedding_adapter
    
    @property
    def llm_adapter(self) -> LLMAdapter:
        if self._llm_adapter is None:
            self._llm_adapter = LLMAdapter(
                api_key=self.settings.NVIDIA_API_KEY,
            )
        return self._llm_adapter
    
    @property
    def notification_service(self) -> Optional[SlackNotificationAdapter]:
        if self._notification_service is None and self.settings.SLACK_BOT_TOKEN:
            self._notification_service = SlackNotificationAdapter(
                token=self.settings.SLACK_BOT_TOKEN,
                default_channel=self.settings.SLACK_DEFAULT_CHANNEL,
            )
        return self._notification_service
    
    def get_decision_service(self) -> DecisionService:
        if self._decision_service is None:
            environment = Environment(self.settings.ENVIRONMENT)
            strategy = StrategyFactory.create(environment=environment)
            self._decision_service = DecisionService(strategy=strategy)
        return self._decision_service
    
    def get_analyzer_service(self) -> AnalyzerService:
        if self._analyzer_service is None:
            self._analyzer_service = AnalyzerService(
                llm_adapter=self.llm_adapter,
            )
        return self._analyzer_service
    
    def get_remediator_service(self) -> RemediatorService:
        if self._remediator_service is None:
            self._remediator_service = RemediatorService(
                settings=self.settings,
            )
        return self._remediator_service
    
    def get_retriever_service(self) -> RetrieverService:
        if self._retriever_service is None:
            self._retriever_service = RetrieverService(
                embedding_adapter=self.embedding_adapter,
            )
        return self._retriever_service
    
    def get_event_processor(self, session: Session) -> EventProcessor:
        incident_repo = IncidentRepository(session)
        vector_repo = VectorRepository(session)
        
        return EventProcessor(
            incident_repository=incident_repo,
            vector_repository=vector_repo,
            analyzer_service=self.get_analyzer_service(),
            decision_service=self.get_decision_service(),
            remediator_service=self.get_remediator_service(),
            retriever_service=self.get_retriever_service(),
            notification_service=self.notification_service,
            embedding_adapter=self.embedding_adapter,
            default_environment=Environment(self.settings.ENVIRONMENT),
            enable_notifications=self.settings.ENABLE_NOTIFICATIONS,
            enable_auto_remediation=self.settings.ENABLE_AUTO_REMEDIATION,
        )


def get_event_processor(session: Session = Depends(get_db)) -> EventProcessor:
    container = ServiceContainer.get_instance()
    return container.get_event_processor(session)


def get_decision_service() -> DecisionService:
    container = ServiceContainer.get_instance()
    return container.get_decision_service()


def get_analyzer_service() -> AnalyzerService:
    container = ServiceContainer.get_instance()
    return container.get_analyzer_service()


def get_remediator_service() -> RemediatorService:
    container = ServiceContainer.get_instance()
    return container.get_remediator_service()


def get_retriever_service() -> RetrieverService:
    container = ServiceContainer.get_instance()
    return container.get_retriever_service()


def get_incident_repository(session: Session = Depends(get_db)) -> IncidentRepository:
    return IncidentRepository(session)


def get_vector_repository(session: Session = Depends(get_db)) -> VectorRepository:
    return VectorRepository(session)