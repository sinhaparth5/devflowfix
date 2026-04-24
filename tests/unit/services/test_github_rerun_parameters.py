# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from app.core.enums import IncidentSource, RemediationActionType
from app.core.models.incident import Incident
from app.core.models.remediation import RemediationPlan
from app.domain.remediators.github_rerun import GitHubRerunRemediator


def test_extract_parameters_splits_repository_full_name() -> None:
    remediator = GitHubRerunRemediator()
    incident = Incident(
        source=IncidentSource.GITHUB,
        context={
            "repository": "owner/repo",
            "run_id": 123,
        },
    )
    plan = RemediationPlan(action_type=RemediationActionType.GITHUB_RERUN_WORKFLOW)

    params = remediator._extract_parameters(incident, plan)

    assert params["owner"] == "owner"
    assert params["repo"] == "repo"
    assert params["run_id"] == 123
