#!/usr/bin/env python3
# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Manual LLM debug runner for error-log driven analysis.

This script is intentionally not a pytest test. It is a manual debugging tool
for sending a real error log through the NVIDIA LLM path and inspecting:
1. extracted GitHub-style structured errors
2. classification prompt/context
3. classification result
4. solution prompt/context
5. solution result

Example:
    python scripts/debug_llm_error_log.py \
      --error-log-file /tmp/error.log \
      --context-file /tmp/context.json \
      --debug-breakpoints

Attach debugger first:
    python -m debugpy --listen 5679 --wait-for-client scripts/debug_llm_error_log.py ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.adapters.ai.nvidia.llm import LLMAdapter
from app.adapters.ai.nvidia.prompts import (
    build_classification_prompt,
    build_solution_generation_prompt,
)
from app.services.github_log_parser import GitHubLogParser


def _load_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def _load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_section(title: str, payload: Any) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, default=str))


def _build_structured_error_context(error_log: str, context: dict[str, Any]) -> dict[str, Any]:
    parser = GitHubLogParser()
    changed_files = context.get("changed_files", [])
    error_files: dict[str, list[dict[str, Any]]] = {}

    for error in parser.extract_errors(error_log):
        if not error.file_path:
            continue

        if changed_files:
            include = any(
                error.file_path.endswith(changed_file)
                or changed_file.endswith(error.file_path)
                or error.file_path in changed_file
                or changed_file in error.file_path
                for changed_file in changed_files
            )
            if not include:
                continue

        error_files.setdefault(error.file_path, []).append(
            {
                "error_type": error.error_type,
                "message": error.error_message,
                "line": error.line_number,
                "step_name": error.step_name,
                "severity": error.severity,
            }
        )

    if error_files:
        context = dict(context)
        context["error_files"] = error_files

    return context


async def _run(args: argparse.Namespace) -> int:
    error_log = _load_text(args.error_log_file)
    if not error_log and not args.error_log:
        raise SystemExit("Provide --error-log-file or --error-log")
    if args.error_log:
        error_log = args.error_log

    context = _load_json(args.context_file)
    context.update(_load_json(args.context_json_file))
    context = _build_structured_error_context(error_log, context)

    repository_code = _load_text(args.repository_code_file) if args.repository_code_file else None

    adapter = LLMAdapter(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        enable_cache=not args.no_cache,
    )

    classification_prompt = build_classification_prompt(
        source=args.source,
        error_log=error_log,
        context=context,
        similar_incidents=[],
    )

    _print_section("INPUT CONTEXT", context)
    _print_section(
        "CLASSIFICATION PROMPT PREVIEW",
        classification_prompt if args.show_full_prompt else classification_prompt[:5000],
    )

    if args.debug_breakpoints:
        breakpoint()

    classification = await adapter.classify(
        source=args.source,
        error_log=error_log,
        context=context,
        similar_incidents=[],
    )
    _print_section("CLASSIFICATION RESULT", classification)

    failure_type = args.failure_type or str(
        getattr(classification.get("failure_type"), "value", classification.get("failure_type"))
    )
    root_cause = args.root_cause or classification.get("root_cause", "Unknown root cause")

    solution_prompt = build_solution_generation_prompt(
        error_log=error_log,
        failure_type=failure_type,
        root_cause=root_cause,
        context=context,
        repository_code=repository_code,
    )
    _print_section(
        "SOLUTION PROMPT PREVIEW",
        solution_prompt if args.show_full_prompt else solution_prompt[:5000],
    )

    if args.debug_breakpoints:
        breakpoint()

    solution = await adapter.generate_solution(
        error_log=error_log,
        failure_type=failure_type,
        root_cause=root_cause,
        context=context,
        repository_code=repository_code,
    )
    _print_section("SOLUTION RESULT", solution)

    if args.debug_breakpoints:
        breakpoint()

    await adapter.client.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a manual LLM debug flow for an error log.")
    parser.add_argument("--error-log-file", help="Path to a text file containing the error log.")
    parser.add_argument("--error-log", help="Inline error log string.")
    parser.add_argument("--context-file", help="Path to JSON file with request/incident context.")
    parser.add_argument(
        "--context-json-file",
        help="Optional second JSON file merged into context after --context-file.",
    )
    parser.add_argument("--repository-code-file", help="Optional source/code snippet file.")
    parser.add_argument("--source", default="github", help="Incident source label passed to classification.")
    parser.add_argument("--model", help="Override NVIDIA LLM model.")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--failure-type", help="Override failure type for solution generation.")
    parser.add_argument("--root-cause", help="Override root cause for solution generation.")
    parser.add_argument("--no-cache", action="store_true", help="Disable Redis caching for this run.")
    parser.add_argument(
        "--show-full-prompt",
        action="store_true",
        help="Print the entire prompt instead of a preview.",
    )
    parser.add_argument(
        "--debug-breakpoints",
        action="store_true",
        help="Stop at breakpoint() before classify, before solution, and after result.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
