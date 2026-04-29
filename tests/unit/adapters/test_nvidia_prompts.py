# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from app.adapters.ai.nvidia.prompts import (
    SOLUTION_SYSTEM_PROMPT,
    build_solution_generation_prompt,
)


def test_solution_system_prompt_is_concise_and_strict() -> None:
    assert "Return only valid JSON" in SOLUTION_SYSTEM_PROMPT
    assert "Do not invent" in SOLUTION_SYSTEM_PROMPT


def test_solution_prompt_prioritizes_compact_context_and_truncation() -> None:
    prompt = build_solution_generation_prompt(
        error_log="E" * 3000,
        failure_type="buildfailure",
        root_cause="R" * 500,
        context={
            "repository": "owner/repo",
            "branch": "main",
            "changed_files": [f"src/file_{idx}.py" for idx in range(12)],
            "error_files": {
                "src/app.py": [
                    {"error_type": "check_annotation", "message": "AssertionError", "line": 42},
                ]
            },
            "irrelevant_blob": "X" * 500,
        },
        repository_code="print('hello')\n" * 500,
    )

    assert "Return only valid JSON" in prompt
    assert "structured_error_files" in prompt
    assert "src/app.py" in prompt
    assert "src/file_0.py" in prompt
    assert "...[truncated]" in prompt
    assert len(prompt) < 7000


def test_classification_prompt_is_compact_without_large_example_block() -> None:
    from app.adapters.ai.nvidia.prompts import build_classification_prompt

    prompt = build_classification_prompt(
        source="github",
        error_log="Error: Process completed with exit code 1\n" * 200,
        context={
            "repository": "owner/repo",
            "branch": "main",
            "workflow": "CI",
            "event_type": "workflow_run",
            "run_id": 123,
            "commit_sha": "a" * 40,
            "changed_files": ["src/main.py"],
            "error_files": {"src/main.py": [{"message": "AssertionError", "line": 42}]},
            "large_blob": "x" * 3000,
        },
        similar_incidents=[],
    )

    assert "### Example 2" not in prompt
    assert "### Example 4" not in prompt
    assert "large_blob" not in prompt
    assert len(prompt) < 5000
