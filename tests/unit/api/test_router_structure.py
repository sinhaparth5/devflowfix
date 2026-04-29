from fastapi.testclient import TestClient

from app.api import router as api_router
from app.api.v1 import router as v1_router
from app.api.v2 import router as v2_router
from app.core.config import settings
from app.main import app


def test_api_package_aggregates_versioned_routers():
    assert api_router.prefix == "/api"
    assert v1_router.prefix == "/v1"
    assert v2_router.prefix == "/v2"


def test_main_registers_expected_top_level_api_paths():
    paths = {route.path for route in app.routes}

    assert "/api/v1/incidents" in paths
    assert "/api/v1/analytics/overview" in paths
    assert "/api/v1/jobs" in paths
    assert "/api/v2/oauth/connections" in paths
    assert "/api/v2/repositories/connections" in paths
    assert "/api/v2/workflows/runs" in paths
    assert "/api/v2/prs/create" in paths
    assert "/api/v2/analytics/workflows/trends" in paths
    assert "/api/v2/webhooks/github" in paths


def test_health_and_root_head_requests_succeed():
    client = TestClient(app)

    health_response = client.head("/health")
    root_response = client.head("/")

    assert health_response.status_code == 200
    assert root_response.status_code == 200


def test_docs_are_disabled_in_production_only():
    if settings.is_production:
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None
    else:
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"
