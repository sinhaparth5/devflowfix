# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.

import pytest

from app.adapters.ai.nvidia.llm import LLMAdapter


@pytest.mark.asyncio
async def test_generate_solution_drops_code_changes_without_repository_code(monkeypatch) -> None:
    adapter = LLMAdapter(enable_cache=False)

    async def fake_complete(**kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"immediate_fix":{"description":"x","steps":["a"],"estimated_time_minutes":5,"risk_level":"low"},'
                            '"code_changes":[{"file_path":"src/main.py","line_number":42,"description":"x","current_code":"bad","fixed_code":"good","explanation":"why"}],'
                            '"configuration_changes":[],"prevention_measures":[]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(adapter.client, "complete", fake_complete)
    monkeypatch.setattr(
        adapter.client,
        "extract_text",
        lambda response: response["choices"][0]["message"]["content"],
    )

    solution = await adapter.generate_solution(
        error_log="AssertionError on src/main.py:42",
        failure_type="testfailure",
        root_cause="Assertion mismatch",
        context={"repository": "owner/repo"},
        repository_code=None,
    )

    assert solution["code_changes"] == []
    await adapter.client.close()
