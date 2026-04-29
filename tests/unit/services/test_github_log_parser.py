# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from unittest.mock import AsyncMock, patch

import pytest

from app.services.github_log_parser import GitHubLogExtractor, GitHubLogParser


def test_extract_check_run_id_from_job() -> None:
    parser = GitHubLogParser()

    check_run_id = parser.extract_check_run_id(
        {
            "check_run_url": "https://api.github.com/repos/owner/repo/check-runs/399444496",
        }
    )

    assert check_run_id == 399444496


def test_extract_annotation_errors_prefers_structured_file_context() -> None:
    parser = GitHubLogParser()

    errors = parser.extract_annotation_errors(
        [
            {
                "path": "src/app.py",
                "start_line": 42,
                "annotation_level": "failure",
                "message": "NameError: variable is not defined",
                "title": "Python exception",
            }
        ],
        job_name="tests",
        failed_steps=[{"name": "Run pytest"}],
    )

    assert len(errors) == 1
    assert errors[0].step_name == "tests / Run pytest"
    assert errors[0].file_path == "src/app.py"
    assert errors[0].line_number == 42
    assert errors[0].severity == "critical"
    assert "Python exception" in errors[0].error_message


def test_extract_errors_normalizes_runner_paths_and_line_numbers() -> None:
    parser = GitHubLogParser()

    errors = parser.extract_errors(
        "##[group]Run pytest\n"
        "src/main.py:42: error expected status code 200 (@pytest/assertion)\n"
        '  File "/home/runner/work/example-repo/example-repo/src/main.py", line 42, in <module>\n'
        "Error: Process completed with exit code 1\n"
    )

    file_paths = {error.file_path for error in errors}
    assert "src/main.py" in file_paths
    assert "/home/runner/work/example-repo/example-repo/src/main.py" not in file_paths
    assert any(error.line_number == 42 for error in errors if error.file_path == "src/main.py")


@pytest.mark.asyncio
async def test_fetch_and_parse_logs_includes_failed_steps_and_annotations() -> None:
    extractor = GitHubLogExtractor(github_token="test-token")

    jobs = [
        {
            "id": 101,
            "name": "build",
            "conclusion": "failure",
            "html_url": "https://github.com/owner/repo/runs/1/jobs/101",
            "check_run_url": "https://api.github.com/repos/owner/repo/check-runs/101",
            "steps": [
                {"name": "Set up job", "conclusion": "success"},
                {"name": "Run tests", "conclusion": "failure"},
            ],
        }
    ]
    annotations = [
        {
            "path": "src/main.py",
            "start_line": 13,
            "annotation_level": "failure",
            "message": "AssertionError: expected 200",
            "title": "Test failure",
        }
    ]

    mock_client = AsyncMock()
    mock_client.list_jobs_for_workflow_run.return_value = jobs
    mock_client.list_check_run_annotations.return_value = annotations
    mock_client.download_job_logs.return_value = (
        "##[group]Run tests\n"
        "src/main.py:13: error expected 200 (@pytest/assertion)\n"
        "Error: Process completed with exit code 1\n"
    )
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("app.adapters.external.github.client.GitHubClient", return_value=mock_client):
        summary = await extractor.fetch_and_parse_logs("owner", "repo", 1)

    assert "GitHub failed jobs:" in summary
    assert "Failed steps: Run tests" in summary
    assert "src/main.py" in summary
    assert "AssertionError: expected 200" in summary
