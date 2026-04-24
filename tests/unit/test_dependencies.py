from fastapi import HTTPException

from app.api import dependencies as api_dependencies
from app.dependencies import ServiceContainer, get_analyzer_service, get_retriever_service
from app.core.config import Settings
from app import dependencies as root_dependencies


class Sentinel:
    pass


def test_api_dependencies_reexport_primary_wiring():
    assert api_dependencies.ServiceContainer is ServiceContainer
    assert api_dependencies.get_analyzer_service is get_analyzer_service
    assert api_dependencies.get_retriever_service is get_retriever_service


def test_primary_dependency_wrappers_accept_optional_db(monkeypatch):
    container = ServiceContainer.get_instance()
    analyzer = Sentinel()
    retriever = Sentinel()

    monkeypatch.setattr(container, "get_analyzer_service", lambda db=None: analyzer)
    monkeypatch.setattr(container, "get_retriever_service", lambda db=None: retriever)

    assert get_analyzer_service() is analyzer
    assert get_retriever_service() is retriever


def test_settings_allow_missing_database_url():
    settings = Settings(DATABASE_URL="")

    assert settings.database_url == ""
    assert settings.database_configured is False
    assert settings.get_database_url_safe() == "not_configured"


def test_get_db_returns_503_when_database_not_configured(monkeypatch):
    monkeypatch.setattr(root_dependencies.settings, "database_url", "")

    try:
        next(root_dependencies.get_db())
        raise AssertionError("expected get_db() to reject requests without a database")
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "DATABASE_URL" in exc.detail
