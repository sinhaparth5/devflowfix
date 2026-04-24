# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from unittest.mock import AsyncMock, Mock

import pytest

from app.core.enums import Environment, FailureType, Fixability, IncidentSource, Outcome
from app.core.models.analysis import AnalysisResult
from app.core.models.context import ExecutionContext
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationResult
from app.services.remediator import RemediatorService


@pytest.mark.asyncio
async def test_execute_wrapper_builds_plan_and_delegates() -> None:
    service = RemediatorService()
    fake_remediator = Mock()
    service.remediator_factory.create = Mock(return_value=fake_remediator)
    service.execute_remediation = AsyncMock(
        return_value=RemediationResult(
            success=True,
            outcome=Outcome.SUCCESS,
            message="ok",
        )
    )

    incident = Incident(
        incident_id="inc_123",
        source=IncidentSource.GITHUB,
        context={
            "repository": "owner/repo",
            "run_id": 99,
            "branch": "main",
        },
    )
    analysis = AnalysisResult(
        category=FailureType.TEST_FAILURE,
        root_cause="tests failed",
        fixability=Fixability.AUTO,
        confidence=0.91,
    )
    context = ExecutionContext(environment=Environment.DEVELOPMENT, repository="owner/repo")

    result = await service.execute(incident=incident, analysis=analysis, context=context)

    assert result.success is True
    service.remediator_factory.create.assert_called_once()
    service.execute_remediation.assert_awaited_once()
    kwargs = service.execute_remediation.await_args.kwargs
    plan = kwargs["plan"]
    assert plan.parameters["owner"] == "owner"
    assert plan.parameters["repo"] == "repo"
    assert plan.parameters["run_id"] == 99
    assert kwargs["remediator"] is fake_remediator
