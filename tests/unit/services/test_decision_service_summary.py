# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from app.domain.strategies.base import DecisionResult
from app.services.decision import DecisionService


def test_decision_summary_uses_requires_approval_key() -> None:
    service = DecisionService(enable_rules=False)
    summary = service.get_decision_summary(
        DecisionResult(
            should_auto_fix=False,
            confidence=0.75,
            reason="manual review",
            strategy_name="test",
            factors={},
            requires_approval=True,
        )
    )

    assert "requires_approval" in summary
    assert summary["requires_approval"] is True
    assert "requiers_approval" not in summary
