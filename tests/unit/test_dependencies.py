from app.api import dependencies as api_dependencies
from app.dependencies import ServiceContainer, get_analyzer_service, get_retriever_service


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
