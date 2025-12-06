# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import re
from typing import List, Dict, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ErrorBlock:
    step_name: str
    error_type: str
    error_message: str
    context: List[str]
    line_number: int
    severity: str


class GitHubLogParser:
    
    ERROR_PATTERNS = [
        (r'##\[error\](.+)', 'github_error', 'high'),
        (r'Error: Process completed with exit code (\d+)', 'exit_code', 'high'),
        (r'(?i)error[:\s](.+)', 'error', 'medium'),
        (r'(?i)fatal[:\s](.+)', 'fatal', 'critical'),
        (r'(?i)exception[:\s](.+)', 'exception', 'high'),
        (r'(?i)FAIL[:\s](.+)', 'test_failure', 'medium'),
        (r'(?i)failed[:\s](.+)', 'failure', 'medium'),
        (r'(?i)panic:', 'panic', 'critical'),
        (r'(?i)traceback \(most recent call last\)', 'python_exception', 'high'),
        (r'(?i)syntax error', 'syntax_error', 'high'),
        (r'(?i)module not found', 'import_error', 'high'),
        (r'(?i)cannot find module', 'import_error', 'high'),
        (r'npm ERR!', 'npm_error', 'medium'),
        (r'yarn error', 'yarn_error', 'medium'),
        (r'composer error', 'composer_error', 'medium'),
        (r'pip error', 'pip_error', 'medium'),
    ]
    
    STEP_START = r'##\[group\](.+)'
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    SKIP_PATTERNS = [
        r'##\[debug\]',
        r'^\s*$',
        r'##\[command\]',
    ]
    
    def __init__(self, context_lines: int = 5, max_errors: int = 10):
        self.context_lines = context_lines
        self.max_errors = max_errors
        self._compiled_error_patterns = [
            (re.compile(pattern, re.IGNORECASE), error_type, severity)
            for pattern, error_type, severity in self.ERROR_PATTERNS
        ]
        self._compiled_skip_patterns = [re.compile(p) for p in self.SKIP_PATTERNS]
    
    def clean_line(self, line: str) -> str:
        line = self.ANSI_ESCAPE.sub('', line)
        line = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+', '', line)
        return line.strip()
    
    def should_skip(self, line: str) -> bool:
        return any(pattern.search(line) for pattern in self._compiled_skip_patterns)
    
    def extract_errors(self, log_content: str) -> List[ErrorBlock]:
        lines = log_content.split('\n')
        errors = []
        current_step = "Unknown Step"
        
        for i, line in enumerate(lines):
            if self.should_skip(line):
                continue
            
            cleaned = self.clean_line(line)
            if not cleaned:
                continue
            
            step_match = re.search(self.STEP_START, line)
            if step_match:
                current_step = step_match.group(1).strip()
                continue
            
            for pattern, error_type, severity in self._compiled_error_patterns:
                match = pattern.search(cleaned)
                if match:
                    error_msg = match.group(1) if match.lastindex else cleaned
                    
                    context_start = max(0, i - self.context_lines)
                    context_end = min(len(lines), i + self.context_lines + 1)
                    context = [
                        self.clean_line(lines[j]) 
                        for j in range(context_start, context_end)
                        if not self.should_skip(lines[j])
                    ]
                    
                    errors.append(ErrorBlock(
                        step_name=current_step,
                        error_type=error_type,
                        error_message=error_msg.strip(),
                        context=context,
                        line_number=i + 1,
                        severity=severity
                    ))
                    
                    if len(errors) >= self.max_errors:
                        return errors
                    break
        
        return errors
    
    def format_error_summary(self, errors: List[ErrorBlock]) -> str:
        if not errors:
            return "No specific errors detected in logs"
        
        summary_parts = []
        
        for idx, error in enumerate(errors, 1):
            summary_parts.append(f"\n{'='*60}")
            summary_parts.append(f"Error #{idx} - {error.error_type.upper()} [{error.severity}]")
            summary_parts.append(f"Step: {error.step_name}")
            summary_parts.append(f"Line: {error.line_number}")
            summary_parts.append(f"{'='*60}")
            summary_parts.append(f"Message: {error.error_message}")
            
            if error.context:
                summary_parts.append(f"\nContext:")
                for ctx_line in error.context:
                    if ctx_line:
                        summary_parts.append(f"  {ctx_line}")
        
        return '\n'.join(summary_parts)
    
    def extract_critical_logs(self, log_content: str, max_length: int = 3000) -> str:
        errors = self.extract_errors(log_content)
        
        if errors:
            summary = self.format_error_summary(errors)
            
            if len(summary) > max_length:
                lines = summary.split('\n')
                truncated = []
                current_length = 0
                
                for line in lines:
                    if current_length + len(line) > max_length - 100:
                        truncated.append("\n... [truncated - error summary too long] ...")
                        break
                    truncated.append(line)
                    current_length += len(line)
                
                return '\n'.join(truncated)
            
            return summary
        
        lines = log_content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if self.should_skip(line):
                continue
            cleaned = self.clean_line(line)
            if cleaned:
                cleaned_lines.append(cleaned)
        
        log_text = '\n'.join(cleaned_lines)
        
        if len(log_text) > max_length:
            beginning = log_text[:max_length // 2]
            end = log_text[-(max_length // 2):]
            return f"{beginning}\n\n... [log truncated] ...\n\n{end}"
        
        return log_text


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
                    
                    errors = self.parser.extract_errors(logs)
                    
                    for error in errors:
                        error.step_name = f"{job_name} / {error.step_name}"
                        all_errors.append(error)
                    
                except Exception as e:
                    logger.warning("github_job_log_fetch_failed", job_id=job_id, error=str(e))
                    continue
            
                if all_errors:
                    summary = self.parser.format_error_summary(all_errors)
                    
                    if len(summary) > 3500:
                        summary = summary[:3500] + "\n\n... [truncated for embedding]"
                    
                    logger.info(
                        "github_errors_extracted",
                        repo=f"{owner}/{repo}",
                        run_id=run_id,
                        error_count=len(all_errors),
                        summary_length=len(summary)
                    )
                    
                    return summary
                
                return ""
            
        except Exception as e:
            logger.error("github_log_extraction_failed", repo=f"{owner}/{repo}", run_id=run_id, error=str(e))
            return ""
    
    def parse_logs_from_text(self, log_content: str) -> str:
        return self.parser.extract_critical_logs(log_content)