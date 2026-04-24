import pytest

from app.core.models.incident import Incident
from app.core.enums import IncidentSource
from app.services.retriever import RetrieverService


class StubEmbeddingAdapter:
    async def embed_incident(self, error_log: str, context: dict):
        return [0.1, 0.2, 0.3]


async def _fake_retrieve_similar_incidents(*args, **kwargs):
    return [
        {
            "incident_id": "inc_1",
            "similarity": 0.97,
            "root_cause": "Cache eviction issue",
            "remediation_actions": ["restart"],
            "outcome": "success",
            "resolution_time_seconds": 45,
        },
        {
            "incident_id": "inc_2",
            "similarity": 0.83,
            "root_cause": "Bad deployment config",
            "remediation_actions": ["rollback"],
            "outcome": "failed",
            "resolution_time_seconds": 120,
        },
    ]


async def test_retrieve_for_rag_context_aggregates_multiple_results(monkeypatch):
    service = RetrieverService(embedding_adapter=StubEmbeddingAdapter(), vector_repository=None)
    incident = Incident(source=IncidentSource.GITHUB, error_log="build failed")

    monkeypatch.setattr(
        service,
        "retrieve_similar_incidents",
        _fake_retrieve_similar_incidents,
    )

    result = await service.retrieve_for_rag_context(incident, max_context_items=2)

    assert result["total_found"] == 2
    assert len(result["similar_incidents"]) == 2
    assert result["similar_incidents"][0]["incident_id"] == "inc_1"
    assert result["success_rate"] == 0.5
    assert result["average_similarity"] == pytest.approx(0.9)
    assert result["has_high_confidence_match"] is True
