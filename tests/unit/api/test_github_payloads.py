# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from app.api.v1.webhook_payloads import extract_github_payload


def test_extract_github_payload_workflow_run_includes_required_context() -> None:
    payload = {
        "workflow_run": {
            "id": 123,
            "run_number": 9,
            "name": "CI",
            "workflow_id": 456,
            "event": "push",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "main",
            "head_sha": "abc123def456",
            "html_url": "https://github.com/owner/repo/actions/runs/123",
            "logs_url": "https://api.github.com/repos/owner/repo/actions/runs/123/logs",
            "head_commit": {
                "message": "Fix build",
                "author": {"name": "Tabish"},
                "modified": ["app/main.py"],
                "added": ["tests/test_main.py"],
            },
        },
        "repository": {
            "id": 789,
            "name": "repo",
            "full_name": "owner/repo",
        },
    }

    normalized = extract_github_payload(payload, "workflow_run")
    context = normalized["context"]

    assert context["repository"] == "owner/repo"
    assert context["branch"] == "main"
    assert context["run_id"] == 123
    assert context["commit_sha"] == "abc123def456"
    assert context["commit"] == "abc123def456"
    assert context["logs_url"] == "https://api.github.com/repos/owner/repo/actions/runs/123/logs"
    assert context["event_type"] == "workflow_run"
    assert context["changed_files"] == ["app/main.py", "tests/test_main.py"]


def test_extract_github_payload_check_run_includes_repo_branch_and_run_context() -> None:
    payload = {
        "action": "completed",
        "check_run": {
            "id": 321,
            "name": "pytest",
            "conclusion": "failure",
            "head_sha": "def456abc123",
            "html_url": "https://github.com/owner/repo/runs/321",
            "details_url": "https://api.github.com/repos/owner/repo/check-runs/321",
            "check_suite": {"id": 654, "head_branch": "develop"},
            "modified": ["src/app.py"],
        },
        "repository": {
            "id": 111,
            "name": "repo",
            "full_name": "owner/repo",
            "default_branch": "main",
        },
    }

    normalized = extract_github_payload(payload, "check_run")
    context = normalized["context"]

    assert context["repository"] == "owner/repo"
    assert context["branch"] == "develop"
    assert context["check_run_id"] == 321
    assert context["run_id"] == 654
    assert context["commit_sha"] == "def456abc123"
    assert context["event_type"] == "check_run"
    assert context["details_url"] == "https://api.github.com/repos/owner/repo/check-runs/321"
    assert context["changed_files"] == ["src/app.py"]
