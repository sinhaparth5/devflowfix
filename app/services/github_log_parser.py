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
        """Generate a short hash for error deduplication.

        Using MD5 is safe here - this is for deduplication only, not security.
        No cryptographic properties are required for grouping similar errors.
        """
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
    # Regex patterns use bounded quantifiers to prevent ReDoS attacks
    # [^\n]+ matches any char except newline, preventing catastrophic backtracking
    ERROR_PATTERNS = [
        (r'##\[error\]([^\n]+)', 'github_error', 'high'),
        (r'Error: Process completed with exit code (\d+)', 'exit_code', 'high'),
        # Lint error: more specific pattern with bounded quantifiers
        (r'(\d{1,6}:\d{1,6})\s+error\s+([^\n]{1,500}?)\s+(@[\w/-]{1,100})', 'lint_error', 'medium'),
        (r'(?i)fatal[:\s]([^\n]+)', 'fatal', 'critical'),
        (r'(?i)panic:', 'panic', 'critical'),
        (r'(?i)traceback \(most recent call last\)', 'python_exception', 'high'),
        (r'FAIL[:\s]([^\n]+)', 'test_failure', 'medium'),
        (r'npm ERR!([^\n]+)', 'npm_error', 'medium'),
        (r'Error:\s*([^\n]+)', 'error', 'medium'),
    ]

    FILE_PATH_PATTERN = r'([/\w.-]+\.(tsx?|jsx?|py|go|java|rb|php|cs|cpp|c|h))'
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    MAX_LINE_LENGTH = 10000  # Prevent processing of extremely long lines
    
    def __init__(self, max_errors_per_type: int = 5, max_total_length: int = 2000):
        self.max_errors_per_type = max_errors_per_type
        self.max_total_length = max_total_length
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), error_type, severity)
            for pattern, error_type, severity in self.ERROR_PATTERNS
        ]
    
    def clean_line(self, line: str) -> str:
        """Clean and validate log line to prevent ReDoS attacks."""
        # Truncate extremely long lines to prevent ReDoS
        if len(line) > self.MAX_LINE_LENGTH:
            line = line[:self.MAX_LINE_LENGTH]

        line = self.ANSI_ESCAPE.sub('', line)
        line = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+', '', line)
        return line.strip()
    
    def extract_file_path(self, line: str) -> Optional[str]:
        match = re.search(self.FILE_PATH_PATTERN, line)
        return match.group(1) if match else None
    
    def parse_lint_error(self, line: str, step_name: str) -> Optional[ErrorBlock]:
        """Parse lint errors with ReDoS-safe regex patterns."""
        match = re.search(r'(\d{1,6}:\d{1,6})\s+error\s+([^\n]{1,500}?)\s+(@[\w/-]{1,100})', line)
        if match:
            location, message, rule = match.groups()
            file_path = self.extract_file_path(line)
            
            return ErrorBlock(
                step_name=step_name,
                error_type='lint_error',
                error_message=f"{message} ({rule})",
                file_path=file_path,
                line_number=None,
                severity='medium'
            )
        return None
    
    def extract_errors(self, log_content: str) -> List[ErrorBlock]:
        lines = log_content.split('\n')
        errors = []
        current_step = "Unknown Step"
        seen_hashes: Set[str] = set()
        current_file = None
        
        for i, line in enumerate(lines):
            cleaned = self.clean_line(line)
            if not cleaned:
                continue
            
            step_match = re.search(r'##\[group\]([^\n]+)', line)
            if step_match:
                current_step = step_match.group(1).strip()
                continue

            file_path = self.extract_file_path(cleaned)
            if file_path and not re.search(r'\d+:\d+\s+error', cleaned):
                current_file = file_path

            # Use bounded quantifiers to prevent ReDoS
            lint_match = re.search(r'(\d{1,6}):(\d{1,6})\s+error\s+([^\n]{1,500}?)\s+(@[\w/-]{1,100})', cleaned)
            if lint_match and current_file:
                line_num, col_num, message, rule = lint_match.groups()
                
                error = ErrorBlock(
                    step_name=current_step,
                    error_type='lint_error',
                    error_message=f"{message} ({rule})",
                    file_path=current_file,
                    line_number=int(line_num) if line_num else None,
                    severity='medium'
                )
                
                error_hash = error.get_hash()
                if error_hash not in seen_hashes:
                    seen_hashes.add(error_hash)
                    errors.append(error)
                continue
            
            for pattern, error_type, severity in self._compiled_patterns:
                if error_type == 'lint_error':
                    continue
                    
                match = pattern.search(cleaned)
                if match:
                    error_msg = match.group(1) if match.lastindex else cleaned
                    
                    # Try to extract line number from error message
                    line_num = None
                    line_match = re.search(r':line\s+(\d+)|:(\d+):', error_msg)
                    if line_match:
                        line_num = int(line_match.group(1) or line_match.group(2))
                    
                    error = ErrorBlock(
                        step_name=current_step,
                        error_type=error_type,
                        error_message=error_msg.strip(),
                        file_path=current_file,
                        line_number=line_num,
                        severity=severity
                    )
                    
                    error_hash = error.get_hash()
                    if error_hash not in seen_hashes:
                        seen_hashes.add(error_hash)
                        errors.append(error)
                    break
        
        return errors
    
    def group_errors(self, errors: List[ErrorBlock]) -> List[ErrorGroup]:
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
                group.files[error.file_path].append(error.error_message)
            else:
                group.files["_general"].append(error.error_message)
        
        return list(groups.values())
    
    def format_compact_summary(self, error_groups: List[ErrorGroup]) -> str:
        if not error_groups:
            return "No errors detected"
        
        lines = []
        total_errors = sum(g.count for g in error_groups)
        
        lines.append(f"Found {total_errors} unique error(s) across {len(error_groups)} type(s)")
        lines.append("")
        
        for idx, group in enumerate(error_groups, 1):
            if idx > 3:
                remaining = len(error_groups) - 3
                lines.append(f"\n... and {remaining} more error type(s)")
                break
            
            lines.append(f"{idx}. {group.error_type.upper()} [{group.severity}]")
            lines.append(f"   Step: {group.step_name}")
            
            # Show files affected
            if group.files and '_general' not in group.files:
                files_list = [f for f in group.files.keys() if f != '_general']
                if files_list:
                    lines.append(f"   Files: {', '.join(files_list[:3])}")
            
            file_count = 0
            for file_path, messages in sorted(group.files.items()):
                if file_count >= self.max_errors_per_type:
                    lines.append(f"   ... and {len(group.files) - file_count} more file(s)")
                    break
                
                if file_path != "_general":
                    # Extract just the filename from full path
                    filename = file_path.split('/')[-1]
                    lines.append(f"   📄 {filename}")
                
                # Deduplicate messages within the file
                unique_messages = list(dict.fromkeys(messages))
                
                for msg in unique_messages[:3]:
                    lines.append(f"      • {msg}")
                
                if len(unique_messages) > 3:
                    lines.append(f"      ... and {len(unique_messages) - 3} more error(s)")
                
                file_count += 1
            
            lines.append("")
        
        summary = "\n".join(lines)
        
        if len(summary) > self.max_total_length:
            summary = summary[:self.max_total_length] + "\n... [output truncated]"
        
        return summary
    
    def extract_critical_logs(self, log_content: str) -> str:
        errors = self.extract_errors(log_content)
        
        if not errors:
            return "No specific errors detected"
        
        groups = self.group_errors(errors)
        return self.format_compact_summary(groups)

class GitHubLogExtractor:
    def __init__(self, github_token: Optional[str] = None):
        from app.core.config import settings
        self.parser = GitHubLogParser()
        self.github_token = github_token or settings.github_token
    
    async def fetch_and_parse_logs(self, owner: str, repo: str, run_id: int) -> str:
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
                        print(f"\n{'='*80}\nGitHub Logs for Job: {job_name} (ID: {job_id})\n{'='*80}\n{logs}\n{'='*80}\n")
                        
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
        return self.parser.extract_critical_logs(log_content)