# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import base64
from unittest.mock import AsyncMock

import pytest

from app.services.pr_creator import PRCreatorService


@pytest.mark.asyncio
async def test_apply_code_changes_updates_existing_file_using_exact_match() -> None:
    github_client = AsyncMock()
    github_client.get_file_contents.return_value = {
        "sha": "abc123",
        "content": base64.b64encode(b"before\nbad_line()\nafter\n").decode("utf-8"),
    }
    github_client.create_or_update_file.return_value = {"commit": {"sha": "def456"}}

    service = PRCreatorService(github_client=github_client)

    changed_files = await service._apply_code_changes(
        github_client=github_client,
        owner="owner",
        repo="repo",
        branch="devflowfix/auto-fix-test",
        code_changes=[
            {
                "file_path": "app.py",
                "current_code": "bad_line()",
                "fixed_code": "good_line()",
                "explanation": "Replace failing call",
            }
        ],
    )

    assert changed_files == ["app.py"]
    github_client.create_or_update_file.assert_awaited_once()
    kwargs = github_client.create_or_update_file.await_args.kwargs
    assert kwargs["path"] == "app.py"
    assert "good_line()" in kwargs["content"]
    assert "bad_line()" not in kwargs["content"]


@pytest.mark.asyncio
async def test_apply_code_changes_skips_invalid_entries() -> None:
    github_client = AsyncMock()
    service = PRCreatorService(github_client=github_client)

    changed_files = await service._apply_code_changes(
        github_client=github_client,
        owner="owner",
        repo="repo",
        branch="devflowfix/auto-fix-test",
        code_changes=[
            {"fixed_code": "missing_path"},
            {"file_path": "app.py", "fixed_code": None},
        ],
    )

    assert changed_files == []
    github_client.create_or_update_file.assert_not_called()
