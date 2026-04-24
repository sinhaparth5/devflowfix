import pytest

from app.core.enums import RemediationActionType, StrategyType
from app.core.models.analysis import AnalysisResult
from app.core.models.context import ExecutionContext
from app.core.models.incident import Incident
from app.domain.remediators.factory import RemediatorFactory
from app.domain.strategies.factory import StrategyFactory
from app.domain.strategies.hybrid import HybridStrategy
from app.domain.strategies.vector_db import VectorDBStrategy
from app.core.enums import Fixability


def test_analysis_result_returns_top_similar_incident():
    analysis = AnalysisResult(
        category=None,
        root_cause="test",
        fixability=Fixability.AUTO,
        confidence=0.9,
        similar_incidents=[
            {"incident_id": "a", "similarity": 0.6},
            {"incident_id": "b", "similarity": 0.91},
            {"incident_id": "c", "similarity": 0.8},
        ],
    )

    top = analysis.get_top_similar_incident()

    assert top["incident_id"] == "b"


def test_hybrid_strategy_calculates_confidence_without_key_error():
    strategy = HybridStrategy()
    analysis = AnalysisResult(
        category=None,
        root_cause="test",
        fixability=Fixability.AUTO,
        confidence=0.82,
        llm_confidence=0.88,
        similar_incidents=[{"similarity": 0.9, "outcome": "success", "resolution_time_seconds": 120}],
        slack_threads=[{"resolved": True, "steps": ["did x"]}],
    )
    incident = Incident()
    context = ExecutionContext()

    confidence = strategy.calculate_confidence(analysis, incident, context)

    assert 0 <= confidence <= 0.99


def test_vector_db_strategy_calculates_confidence_without_typo_error():
    strategy = VectorDBStrategy()
    analysis = AnalysisResult(
        category=None,
        root_cause="test",
        fixability=Fixability.AUTO,
        confidence=0.8,
        similar_incidents=[{"similarity": 0.92, "outcome": "success"}],
    )
    incident = Incident()
    context = ExecutionContext()

    confidence = strategy.calculate_confidence(analysis, incident, context)

    assert confidence > 0


@pytest.mark.parametrize(
    ("action_type", "expected_class_name"),
    [
        (RemediationActionType.GITHUB_ROTATE_SECRET, "GitHubSecretRotateRemediator"),
        (RemediationActionType.K8S_SCALE_DEPLOYMENT, "K8sScaleRemediator"),
        (RemediationActionType.K8S_UPDATE_IMAGE, "K8sUpdateImageRemediator"),
        (RemediationActionType.ARGOCD_ROLLBACK, "ArgoCDRollbackRemediator"),
        (RemediationActionType.DOCKER_CLEAR_CACHE, "DockerClearCacheRemediator"),
    ],
)
def test_remediator_factory_registers_supported_action_types(action_type, expected_class_name):
    remediator = RemediatorFactory().create(action_type)

    assert remediator.__class__.__name__ == expected_class_name


def test_strategy_factory_supports_aggressive_strategy_type():
    strategy = StrategyFactory.create(StrategyType.AGGRESSIVE)

    assert strategy.__class__.__name__ == "SlackFirstStrategy"
