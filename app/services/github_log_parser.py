# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import re
import hashlib
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class ErrorBlock:
    step_name: str
    error_type: str
    error_message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    severity: str = "medium"

    def get_hash(self) -> str:
        content = f"{self.error_type}:{self.error_message}:{self.file_path or ''}"
        return hashlib.md5(content.encode()).hexdigest()[:8]

@dataclass
class ErrorGroup:
    error_type: str
    step_name: str
    files: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    severity: str = "medium"
    count: int = 0

class GitHubLogParser:
    """
    Language-agnostic log parser that works with ANY programming language.

    Instead of matching specific language patterns, it:
    1. Looks for common error keywords (error, fail, fatal, etc.)
    2. Extracts file paths from ANY extension
    3. Extracts line numbers using common patterns
    4. Groups errors intelligently
    """

    # Universal error indicators (language-agnostic)
    UNIVERSAL_ERROR_PATTERNS = [
        # GitHub Actions specific
        (r'##\[error\]([^\n]+)', 'github_action_error', 'high'),
        (r'Error: Process completed with exit code (\d+)', 'exit_code', 'high'),

        # Build tool failures (Maven, Gradle, npm, etc.)
        (r'\[ERROR\]([^\n]+)', 'build_error', 'high'),
        (r'FAILURE: Build failed([^\n]*)', 'build_failure', 'high'),
        (r'BUILD FAILED', 'build_failed', 'high'),

        # Compiler errors (any language)
        (r'error[:\s]+([^\n]+)', 'compiler_error', 'high'),
        (r'error\[E\d+\]:\s*([^\n]+)', 'rust_error', 'high'),  # Rust: error[E0308]

        # Runtime errors
        (r'(?i)fatal[:\s]([^\n]+)', 'fatal_error', 'critical'),
        (r'(?i)panic[:\s]([^\n]*)', 'panic', 'critical'),
        (r'(?i)exception[:\s]([^\n]+)', 'exception', 'high'),

        # Test failures
        (r'FAIL[:\s]([^\n]+)', 'test_failure', 'medium'),
        (r'(?i)test.*failed', 'test_failed', 'medium'),
        (r'(?i)assertion.*failed', 'assertion_failed', 'high'),

        # Package manager errors
        (r'npm ERR!([^\n]+)', 'npm_error', 'medium'),
        (r'yarn error([^\n]+)', 'yarn_error', 'medium'),
        (r'pip._internal.exceptions.([^\n]+)', 'pip_error', 'medium'),
        (r'cargo error([^\n]+)', 'cargo_error', 'medium'),

        # Linting (universal pattern - works with any linter)
        (r'(\d{1,6}):(\d{1,6})[:\s]+(?:error|warning)[:\s]([^\n]{1,500})', 'lint_error', 'medium'),

        # Generic error (catch-all)
        (r'(?i)error[:\s]([^\n]{10,500})', 'generic_error', 'medium'),
    ]

    # Universal file path pattern - matches ANY file extension
    # Looks for common path structures: /path/to/file.ext or ./relative/path.ext
    FILE_PATH_PATTERN = r'(?:\.{0,2}/)?(?:[\w.-]+/)*?([\w.-]+\.[\w]{1,10})'

    # Line number patterns (appears in most language error messages)
    LINE_NUMBER_PATTERNS = [
        r':line\s+(\d+)',           # :line 42
        r'line\s+(\d+)',            # line 42
        r':(\d+):(\d+)',            # file.py:42:10
        r'\[(\d+),(\d+)\]',         # [42,10]
        r'-->\s+[^\s]+:(\d+)',      # --> src/main.rs:42
        r'at line (\d+)',           # at line 42
    ]

    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    MAX_LINE_LENGTH = 10000

    def __init__(self, max_errors_per_type: int = 10, max_total_length: int = 3000):
        self.max_errors_per_type = max_errors_per_type
        self.max_total_length = max_total_length
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), error_type, severity)
            for pattern, error_type, severity in self.UNIVERSAL_ERROR_PATTERNS
        ]
        self._file_pattern = re.compile(self.FILE_PATH_PATTERN)
        self._line_patterns = [re.compile(p) for p in self.LINE_NUMBER_PATTERNS]

    def clean_line(self, line: str) -> str:
        """Remove ANSI codes, timestamps, and normalize."""
        if len(line) > self.MAX_LINE_LENGTH:
            line = line[:self.MAX_LINE_LENGTH]

        line = self.ANSI_ESCAPE.sub('', line)
        # Remove ISO timestamps
        line = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+', '', line)
        # Remove log level prefixes
        line = re.sub(r'^\[\w+\]\s+', '', line)
        return line.strip()

    def extract_file_path(self, line: str) -> Optional[str]:
        """Extract file path from line - works with ANY file extension."""
        # Try to find file paths with extensions
        matches = self._file_pattern.findall(line)
        if matches:
            # Return the last match (usually the most relevant)
            return matches[-1] if isinstance(matches[-1], str) else matches[-1][0]
        return None

    def extract_line_number(self, line: str) -> Optional[int]:
        """Extract line number using multiple common patterns."""
        for pattern in self._line_patterns:
            match = pattern.search(line)
            if match:
                # Get first capturing group that's a number
                for group in match.groups():
                    if group and group.isdigit():
                        return int(group)
        return None

    def extract_errors(self, log_content: str) -> List[ErrorBlock]:
        """Extract errors using language-agnostic patterns."""
        lines = log_content.split('\n')
        errors = []
        current_step = "Unknown Step"
        seen_hashes: Set[str] = set()
        current_file = None

        for line in lines:
            cleaned = self.clean_line(line)
            if not cleaned or len(cleaned) < 5:  # Skip very short lines
                continue

            # Track current step (GitHub Actions groups)
            step_match = re.search(r'##\[group\]([^\n]+)', line)
            if step_match:
                current_step = step_match.group(1).strip()
                continue

            # Extract file path if present
            file_path = self.extract_file_path(cleaned)
            if file_path:
                current_file = file_path

            # Try to match error patterns
            for pattern, error_type, severity in self._compiled_patterns:
                match = pattern.search(cleaned)
                if match:
                    # Extract error message
                    error_msg = match.group(1) if match.lastindex and match.lastindex > 0 else cleaned

                    # Extract line number
                    line_num = self.extract_line_number(cleaned)

                    error = ErrorBlock(
                        step_name=current_step,
                        error_type=error_type,
                        error_message=error_msg.strip()[:500],  # Limit message length
                        file_path=file_path or current_file,
                        line_number=line_num,
                        severity=severity
                    )

                    # Deduplicate
                    error_hash = error.get_hash()
                    if error_hash not in seen_hashes:
                        seen_hashes.add(error_hash)
                        errors.append(error)
                    break  # Only match first pattern

        logger.info(
            "errors_extracted",
            total_errors=len(errors),
            unique_files=len(set(e.file_path for e in errors if e.file_path))
        )

        return errors

    def group_errors(self, errors: List[ErrorBlock]) -> List[ErrorGroup]:
        """Group errors by type and step."""
        groups: Dict[str, ErrorGroup] = {}

        for error in errors:
            key = f"{error.step_name}:{error.error_type}"

            if key not in groups:
                groups[key] = ErrorGroup(
                    error_type=error.error_type,
                    step_name=error.step_name,
                    severity=error.severity
                )

            group = groups[key]
            group.count += 1

            if error.file_path:
                group.files[error.file_path].append(
                    f"Line {error.line_number}: {error.error_message}" if error.line_number
                    else error.error_message
                )
            else:
                group.files["_general"].append(error.error_message)

        # Sort by severity (critical > high > medium > low)
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        return sorted(
            groups.values(),
            key=lambda g: (severity_order.get(g.severity, 4), -g.count)
        )

    def format_compact_summary(self, error_groups: List[ErrorGroup]) -> str:
        """Format errors into a compact, LLM-friendly summary."""
        if not error_groups:
            return "No errors detected"

        lines = []
        total_errors = sum(g.count for g in error_groups)

        lines.append(f"🔴 Found {total_errors} error(s) across {len(error_groups)} type(s)")
        lines.append("")

        for idx, group in enumerate(error_groups, 1):
            if idx > 5:  # Show top 5 error types
                remaining = len(error_groups) - 5
                lines.append(f"\n... and {remaining} more error type(s)")
                break

            # Error type header with severity emoji
            severity_emoji = {
                'critical': '🔥',
                'high': '🔴',
                'medium': '🟡',
                'low': '🟢'
            }
            emoji = severity_emoji.get(group.severity, '⚠️')

            lines.append(f"{emoji} {idx}. {group.error_type.upper().replace('_', ' ')} ({group.count} occurrence(s))")
            lines.append(f"   Step: {group.step_name}")

            # Show affected files
            if group.files and '_general' not in group.files:
                files_list = [f for f in group.files.keys() if f != '_general']
                if files_list:
                    files_display = ', '.join(files_list[:3])
                    if len(files_list) > 3:
                        files_display += f" +{len(files_list) - 3} more"
                    lines.append(f"   📁 Files: {files_display}")

            # Show sample errors
            file_count = 0
            for file_path, messages in sorted(group.files.items()):
                if file_count >= self.max_errors_per_type:
                    break

                if file_path != "_general":
                    filename = file_path.split('/')[-1]
                    lines.append(f"   📄 {filename}:")

                # Show unique messages
                unique_messages = list(dict.fromkeys(messages))
                for msg in unique_messages[:2]:  # Show 2 examples per file
                    lines.append(f"      • {msg[:200]}")

                if len(unique_messages) > 2:
                    lines.append(f"      • ... and {len(unique_messages) - 2} more")

                file_count += 1

            lines.append("")

        summary = "\n".join(lines)

        # Truncate if too long
        if len(summary) > self.max_total_length:
            summary = summary[:self.max_total_length] + "\n\n... [truncated for brevity]"

        return summary

    def extract_critical_logs(self, log_content: str) -> str:
        """Main entry point - extract and format errors."""
        errors = self.extract_errors(log_content)

        if not errors:
            return "No specific errors detected in logs"

        groups = self.group_errors(errors)
        return self.format_compact_summary(groups)


class GitHubLogExtractor:
    """
    Fetches logs from GitHub Actions and extracts errors.

    Uses the GitHubLogParser to parse and format errors from workflow run logs.
    """

    def __init__(self, github_token: Optional[str] = None):
        from app.core.config import settings
        self.parser = GitHubLogParser()
        self.github_token = github_token or settings.github_token

    async def fetch_and_parse_logs(self, owner: str, repo: str, run_id: int) -> str:
        """
        Fetch logs from GitHub Actions workflow run and extract errors.

        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID

        Returns:
            Formatted error summary
        """
        from app.adapters.external.github.client import GitHubClient

        try:
            async with GitHubClient(token=self.github_token) as client:
                jobs = await client.list_jobs_for_workflow_run(owner=owner, repo=repo, run_id=run_id)

                failed_jobs = [job for job in jobs if job.get("conclusion") == "failure"]

                if not failed_jobs:
                    logger.warning("github_no_failed_jobs", repo=f"{owner}/{repo}", run_id=run_id)
                    return ""

                all_errors = []

                for job in failed_jobs:
                    job_id = job.get("id")
                    job_name = job.get("name", "unknown")

                    try:
                        logs = await client.download_job_logs(owner=owner, repo=repo, job_id=job_id)

                        logger.debug(
                            "github_logs_fetched",
                            job_name=job_name,
                            job_id=job_id,
                            log_length=len(logs)
                        )

                        errors = self.parser.extract_errors(logs)

                        for error in errors:
                            error.step_name = f"{job_name} / {error.step_name}"
                            all_errors.append(error)

                    except Exception as e:
                        logger.warning("github_job_log_fetch_failed", job_id=job_id, error=str(e))
                        continue

                if all_errors:
                    groups = self.parser.group_errors(all_errors)
                    summary = self.parser.format_compact_summary(groups)

                    logger.info(
                        "github_errors_extracted",
                        repo=f"{owner}/{repo}",
                        run_id=run_id,
                        unique_errors=len(all_errors),
                        error_groups=len(groups),
                        summary_length=len(summary)
                    )

                    return summary

                return ""

        except Exception as e:
            logger.error("github_log_extraction_failed", repo=f"{owner}/{repo}", run_id=run_id, error=str(e))
            return ""

    def parse_logs_from_text(self, log_content: str) -> str:
        """
        Parse logs from raw text content.

        Args:
            log_content: Raw log text

        Returns:
            Formatted error summary
        """
        return self.parser.extract_critical_logs(log_content)
