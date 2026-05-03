# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import base64

import pytest

from app.core.enums import Environment, FailureType, Fixability, IncidentSource, Outcome, Severity
from app.core.models.analysis import AnalysisResult
from app.core.models.context import ExecutionContext
from app.core.models.incident import Incident
from app.domain.strategies.base import DecisionResult
from app.services.event_processor import EventProcessor


class StubIncidentRepository:
    def __init__(self) -> None:
        self.table = SimpleNamespace(
            incident_id="inc_123",
            context={},
            root_cause=None,
            failure_type=None,
            fixability=None,
            confidence=None,
            remediation_plan=None,
            remediation_executed=False,
            remediation_start_time=None,
            remediation_end_time=None,
            outcome=None,
            outcome_message=None,
            resolved_at=None,
            resolution_time_seconds=None,
        )

    def get_by_id(self, incident_id: str):
        return self.table if incident_id == self.table.incident_id else None

    def update(self, incident):
        self.table = incident
        return incident


@pytest.fixture
def processor() -> EventProcessor:
    incident_repo = StubIncidentRepository()
    return EventProcessor(
        incident_repository=incident_repo,
        vector_repository=Mock(),
        analyzer_service=Mock(),
        decision_service=Mock(),
        remediator_service=Mock(),
        retriever_service=Mock(),
        notification_service=None,
        embedding_adapter=None,
        default_environment=Environment.DEVELOPMENT,
        enable_notifications=False,
        enable_auto_remediation=True,
        pr_creator=None,
        enable_auto_pr=True,
    )


@pytest.fixture
def incident(processor: EventProcessor) -> Incident:
    inc = Incident(
        incident_id="inc_123",
        source=IncidentSource.GITHUB,
        severity=Severity.HIGH,
        error_log="tests failing",
        context={
            "repository": "owner/repo",
            "branch": "main",
            "user_id": "user_123",
        },
    )
    processor.incident_repo.table.incident_id = inc.incident_id
    return inc


@pytest.fixture
def analysis() -> AnalysisResult:
    return AnalysisResult(
        category=FailureType.TEST_FAILURE,
        root_cause="unit tests failed",
        fixability=Fixability.MANUAL,
        confidence=0.82,
    )


@pytest.mark.asyncio
async def test_process_background_marks_pending_when_not_auto_fix_and_not_escalated(
    processor: EventProcessor,
    incident: Incident,
    analysis: AnalysisResult,
) -> None:
    processor._generate_and_store_embedding = AsyncMock()
    processor._retrieve_similar = AsyncMock(return_value=[])
    processor._analyze = AsyncMock(return_value=analysis)
    processor._update_incident_analysis = AsyncMock()
    processor._generate_and_log_solutions = AsyncMock(return_value=None)
    processor._decide = AsyncMock(
        return_value=DecisionResult(
            should_auto_fix=False,
            confidence=0.82,
            reason="manual review required",
            strategy_name="test",
            factors={},
            escalate=False,
            requires_approval=False,
        )
    )
    processor._escalate = AsyncMock()
    processor._request_approval = AsyncMock()
    processor._remediate = AsyncMock()
    processor._finalize = AsyncMock()

    await processor._process_background(
        incident,
        ExecutionContext(environment=Environment.DEVELOPMENT, repository="owner/repo"),
    )

    assert incident.outcome == Outcome.PENDING
    assert incident.outcome_message == "manual review required"
    assert processor._escalate.await_count == 0
    assert processor.incident_repo.table.outcome == Outcome.PENDING.value


@pytest.mark.asyncio
async def test_attempt_post_analysis_pr_records_skip_for_non_github_provider(
    processor: EventProcessor,
    analysis: AnalysisResult,
) -> None:
    incident = Incident(
        incident_id="inc_123",
        source=IncidentSource.ARGOCD,
        severity=Severity.HIGH,
        error_log="deploy failed",
        context={"repository": "owner/repo", "user_id": "user_123"},
    )
    processor.incident_repo.table.incident_id = incident.incident_id

    result = await processor._attempt_post_analysis_pr(
        incident=incident,
        analysis=analysis,
        solution={"code_changes": [{"file_path": "app.py", "fixed_code": "pass"}]},
    )

    assert result is None
    assert incident.context["post_analysis"]["status"] == "skipped"
    assert incident.context["post_analysis"]["reason"] == "provider_argocd_pr_not_supported"


@pytest.mark.asyncio
async def test_attempt_post_analysis_pr_records_created_pr(
    processor: EventProcessor,
    incident: Incident,
    analysis: AnalysisResult,
) -> None:
    processor._create_fix_pr = AsyncMock(
        return_value={
            "number": 42,
            "html_url": "https://github.com/owner/repo/pull/42",
            "head": {"ref": "devflowfix/auto-fix-test"},
        }
    )

    result = await processor._attempt_post_analysis_pr(
        incident=incident,
        analysis=analysis,
        solution={"code_changes": [{"file_path": "app.py", "fixed_code": "print(1)"}]},
    )

    assert result is not None
    assert incident.context["automated_pr"]["number"] == 42
    assert incident.context["post_analysis"]["status"] == "pr_created"


@pytest.mark.asyncio
async def test_fetch_repository_code_context_fetches_candidate_files(
    processor: EventProcessor,
    incident: Incident,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGitHubClient:
        def __init__(self, token=None):
            self.token = token

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def get_file_contents(self, owner, repo, path, ref=None):
            assert owner == "owner"
            assert repo == "repo"
            assert path == "src/hooks/useProducts.ts"
            assert ref == "main"
            return {
                "content": base64.b64encode(b"const invalidTypeAssignment = true;\n").decode()
            }

    monkeypatch.setattr("app.adapters.external.github.client.GitHubClient", FakeGitHubClient)

    repository_code = await processor._fetch_repository_code_context(
        incident=incident,
        context={
            "repository": "owner/repo",
            "branch": "main",
            "error_files": {"src/hooks/useProducts.ts": [{"line": 12}]},
        },
    )

    assert repository_code is not None
    assert "## File: src/hooks/useProducts.ts" in repository_code
    assert "invalidTypeAssignment" in repository_code
