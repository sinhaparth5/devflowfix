# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import List, Dict, Any, Optional
from app.core.enums import FailureType, RemediationActionType

# System prompt for incident classification
SYSTEM_PROMPT = """You are an expert DevOps engineer specializing in CI/CD pipeline failures and cloud infrastructure issues. 
Your task is to analyze error logs and classify incidents to enable automatic remediation.

You have deep knowledge of:
- GitHub Actions, GitLab CI, Jenkins pipelines
- Kubernetes and container orchestration
- ArgoCD and GitOps workflows
- Common failure patterns and their solutions
- Docker, dependencies, and build systems

Analyze incidents carefully and provide structured responses in JSON format."""

SOLUTION_SYSTEM_PROMPT = """You are a senior CI/CD remediation assistant.
Return only valid JSON.
Prefer the smallest correct fix.
Do not invent file paths, line numbers, code, settings, or commands.
Use only evidence from the supplied incident data.
If evidence is insufficient, leave uncertain fields empty instead of guessing."""


def _truncate_text(value: Optional[str], limit: int) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "...[truncated]"


def _summarize_context(context: Dict[str, Any]) -> str:
    priority_keys = [
        "repository",
        "branch",
        "workflow",
        "event_type",
        "run_id",
        "check_run_id",
        "commit_sha",
        "details_url",
        "logs_url",
    ]
    lines: List[str] = []

    for key in priority_keys:
        value = context.get(key)
        if value:
            lines.append(f"- {key}: {_truncate_text(str(value), 160)}")

    changed_files = context.get("changed_files") or []
    if changed_files:
        lines.append("- changed_files:")
        for path in changed_files[:10]:
            lines.append(f"  - {_truncate_text(str(path), 160)}")
        if len(changed_files) > 10:
            lines.append(f"  - ... and {len(changed_files) - 10} more")

    error_files = context.get("error_files") or {}
    if error_files:
        lines.append("- structured_error_files:")
        for file_path, file_errors in list(error_files.items())[:5]:
            lines.append(f"  - file: {_truncate_text(str(file_path), 160)}")
            for error in file_errors[:3]:
                message = _truncate_text(str(error.get('message') or ""), 180)
                line = error.get("line")
                error_type = error.get("error_type") or "error"
                detail = f"{error_type}: {message}"
                if line:
                    detail += f" (line {line})"
                lines.append(f"    - {detail}")
        if len(error_files) > 5:
            lines.append(f"  - ... and {len(error_files) - 5} more files")

    extras = []
    for key, value in context.items():
        if key in priority_keys or key in {"changed_files", "error_files"}:
            continue
        if value in (None, "", [], {}, ()):
            continue
        extras.append((key, value))

    for key, value in extras[:6]:
        lines.append(f"- {key}: {_truncate_text(str(value), 160)}")

    return "\n".join(lines) if lines else "- none"

# Classification prompt template
CLASSIFICATION_PROMPT = """Analyze the following CI/CD incident and return valid JSON only.

## Incident Details

**Source:** {source}
**Error Log:**
```
{error_log}
```

**Context:**
{context}

{similar_incidents_section}

## Return this JSON shape

{{
  "failure_type": "<one of: {failure_types}>",
  "root_cause": "<concise description of the root cause>",
  "fixability": "<one of: auto, manual, unknown>",
  "confidence": <float between 0.0 and 1.0>,
  "recommended_action": "<one of: {action_types}>",
  "reasoning": "<explanation of your analysis>",
  "key_indicators": ["<indicator1>", "<indicator2>", ...],
  "suggested_parameters": {{
    "<param_name>": "<param_value>"
  }}
}}

## Rules

- Choose the most specific failure_type supported by the evidence.
- root_cause must be concise and actionable, max 200 chars.
- fixability is "auto", "manual", or "unknown".
- Be conservative with confidence. Lower it if evidence is incomplete.
- reasoning should be 1-2 short sentences.
- key_indicators should contain 2-5 concrete signals from the incident.
- suggested_parameters should contain only clearly supported values.
- Return valid JSON only. No markdown.

## Example
```json
{{
  "failure_type": "buildfailure",
  "root_cause": "Npm dependency resolution failed due to network timeout",
  "fixability": "auto",
  "confidence": 0.90,
  "recommended_action": "github_rerun_workflow",
  "reasoning": "Build failed during 'npm install' with ETIMEDOUT error. This is a transient network issue that typically resolves on retry. High confidence because error pattern is clear and common.",
  "key_indicators": ["ETIMEDOUT", "npm install failed", "network timeout", "registry.npmjs.org"],
  "suggested_parameters": {{
    "run_id": "123456789",
    "wait_before_retry_seconds": 60
  }}
}}
```

Now analyze the incident and return the JSON."""

def build_classification_prompt(
    source: str,
    error_log: str,
    context: Dict[str, Any],
    similar_incidents: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build classification prompt with incident details.
    
    Args:
        source: Incident source (github, argocd, kubernetes)
        error_log: Error log or message
        context: Additional context information
        similar_incidents: Optional list of similar incidents
        
    Returns:
        Formatted prompt string
    """
    priority_keys = [
        "repository",
        "branch",
        "workflow",
        "event_type",
        "run_id",
        "commit_sha",
        "changed_files",
        "error_files",
    ]
    context_lines = []
    for key in priority_keys:
        value = context.get(key)
        if value in (None, "", [], {}, ()):
            continue
        rendered = str(value)
        if len(rendered) > 800:
            rendered = rendered[:800] + "...[truncated]"
        context_lines.append(f"- {key}: {rendered}")
    context_str = "\n".join(context_lines) if context_lines else "- none"
    
    # Format similar incidents section
    similar_section = ""
    if similar_incidents and len(similar_incidents) > 0:
        similar_section = "\n**Similar Past Incidents:**\n"
        for i, incident in enumerate(similar_incidents[:3], 1):
            similar_section += f"\n{i}. "
            similar_section += f"Failure Type: {incident.get('failure_type', 'unknown')}, "
            similar_section += f"Action: {incident.get('action_taken', 'none')}, "
            similar_section += f"Outcome: {incident.get('outcome', 'unknown')}, "
            similar_section += f"Similarity: {incident.get('similarity', 0):.2f}\n"
            if incident.get('root_cause'):
                similar_section += f"   Root Cause: {incident['root_cause']}\n"
    
    # Get available failure types and actions
    failure_types = ", ".join([ft.value for ft in FailureType])
    action_types = ", ".join([at.value for at in RemediationActionType])
    
    # Build final prompt
    prompt = CLASSIFICATION_PROMPT.format(
        source=source,
        error_log=error_log[:1600],
        context=context_str,
        similar_incidents_section=similar_section,
        failure_types=failure_types,
        action_types=action_types,
    )
    
    return prompt

def build_root_cause_analysis_prompt(
    error_log: str,
    context: Dict[str, Any],
    stack_trace: Optional[str] = None,
) -> str:
    """
    Build prompt for detailed root cause analysis.
    
    Used when deeper analysis is needed beyond classification.
    
    Args:
        error_log: Error log or message
        context: Additional context
        stack_trace: Optional stack trace
        
    Returns:
        Formatted prompt string
    """
    # Build stack trace section separately to avoid f-string backslash issues
    stack_trace_section = ""
    if stack_trace:
        stack_trace_section = f"## Stack Trace\n```\n{stack_trace[:2000]}\n```\n"
    
    # Build context lines separately
    context_lines = "\n".join([f"- {k}: {v}" for k, v in context.items() if v])
    
    prompt = f"""Perform a detailed root cause analysis of the following incident.

## Error Log
```
{error_log[:3000]}
```

{stack_trace_section}
## Context
{context_lines}

## Analysis Required

Provide a detailed root cause analysis in JSON format:

{{
  "primary_cause": "<main reason for the failure>",
  "contributing_factors": ["<factor1>", "<factor2>", ...],
  "error_chain": ["<step1>", "<step2>", "<step3>"],
  "affected_components": ["<component1>", "<component2>", ...],
  "severity_justification": "<why this severity level>",
  "prevention_recommendations": ["<recommendation1>", "<recommendation2>", ...]
}}

Focus on:
1. What specifically caused this failure
2. What sequence of events led to it
3. Which components are affected
4. How to prevent similar failures

Provide your analysis:"""
    
    return prompt

def build_remediation_validation_prompt(
    failure_type: str,
    proposed_action: str,
    context: Dict[str, Any],
) -> str:
    """
    Build prompt to validate proposed remediation action.
    
    Args:
        failure_type: Classified failure type
        proposed_action: Proposed remediation action
        context: Incident context
        
    Returns:
        Formatted prompt string
    """
    # Build context lines separately to avoid f-string backslash issues
    context_lines = "\n".join([f"- {k}: {v}" for k, v in context.items() if v])
    
    prompt = f"""Validate the proposed remediation action for this incident.

## Incident Classification
- Failure Type: {failure_type}
- Proposed Action: {proposed_action}

## Context
{context_lines}

## Validation Required

Evaluate the proposed remediation and provide a JSON response:

{{
  "is_safe": <true/false>,
  "is_appropriate": <true/false>,
  "risk_level": "<low/medium/high/critical>",
  "confidence": <0.0-1.0>,
  "concerns": ["<concern1>", "<concern2>", ...],
  "preconditions": ["<precondition1>", "<precondition2>", ...],
  "alternative_actions": ["<action1>", "<action2>", ...],
  "recommendation": "<proceed/modify/escalate>"
}}

Consider:
1. Will this action safely resolve the issue?
2. Are there any risks or side effects?
3. Are preconditions met?
4. Is there a better action?

Provide your validation:"""
    
    return prompt

# Few-shot examples for improving classification accuracy
FEW_SHOT_EXAMPLES = [
    {
        "error": "ImagePullBackOff: Failed to pull image 'myapp:v1.2.3': rpc error: code = NotFound",
        "classification": {
            "failure_type": "imagepullbackoff",
            "fixability": "manual",
            "confidence": 0.95,
            "action": "k8s_update_image",
        }
    },
    {
        "error": "CrashLoopBackOff: container 'app' in pod 'myapp-xyz' is crash looping",
        "classification": {
            "failure_type": "crashloopbackoff",
            "fixability": "auto",
            "confidence": 0.80,
            "action": "k8s_restart_pod",
        }
    },
    {
        "error": "npm ERR! code ETIMEDOUT\nnpm ERR! network request to https://registry.npmjs.org failed",
        "classification": {
            "failure_type": "buildfailure",
            "fixability": "auto",
            "confidence": 0.90,
            "action": "github_rerun_workflow",
        }
    },
]


def build_solution_generation_prompt(
    error_log: str,
    failure_type: str,
    root_cause: str,
    context: Dict[str, Any],
    repository_code: Optional[str] = None,
) -> str:
    """
    Build prompt to generate detailed solutions based on error analysis.
    
    Args:
        error_log: Error log or message
        failure_type: Classified failure type
        root_cause: Root cause analysis
        context: Incident context
        repository_code: Optional relevant code from repository
        
    Returns:
        Formatted prompt string for solution generation
    """
    context_lines = _summarize_context(context)
    
    code_section = ""
    if repository_code:
        code_section = f"\n## Relevant Repository Code\n```\n{_truncate_text(repository_code, 1200)}\n```\n"

    trimmed_error_log = _truncate_text(error_log, 1400)
    trimmed_root_cause = _truncate_text(root_cause, 220)
    
    prompt = f"""Task: propose the smallest reliable fix for this CI/CD failure.

Return only valid JSON. No prose. No markdown.

## Incident
- failure_type: {failure_type}
- root_cause: {trimmed_root_cause}

## Error Summary
```
{trimmed_error_log}
```

## Context
{context_lines}
{code_section}

## Required JSON schema

{{
  "immediate_fix": {{
    "description": "First action to resolve this issue",
    "steps": ["Step 1", "Step 2", "Step 3"],
    "estimated_time_minutes": 15,
    "risk_level": "low"
  }},
  "code_changes": [
    {{
      "file_path": "EXTRACT from error log (e.g. src/hooks/useProducts.ts)",
      "line_number": "EXTRACT from error log as INTEGER (e.g. 15, 23, 156)",
      "description": "What to change",
      "current_code": "problematic code snippet from error",
      "fixed_code": "corrected code snippet (use EMPTY STRING to delete line)",
      "explanation": "Why this fixes the issue"
    }}
  ],
  "configuration_changes": [
    {{
      "file": "config file path",
      "setting": "config key or parameter",
      "current_value": "current value",
      "recommended_value": "new value",
      "reason": "Why this helps"
    }}
  ],
  "prevention_measures": [
    {{
      "measure": "Action to prevent future failures",
      "description": "How this prevents the issue",
      "implementation_effort": "low"
    }}
  ]
}}

## Rules
- Be concise and deterministic.
- Prefer one good fix over many speculative fixes.
- If the evidence points to a config issue, leave code_changes as [].
- If the evidence points to a code issue, only include files supported by the error summary or structured_error_files.
- If changed_files is present, prioritize those files and avoid unrelated files.
- Do not invent line numbers. If unknown, use null.
- Use current_code only when it is directly supported by the provided input.
- For delete-only fixes, use an empty string for fixed_code.
- If a section does not apply, use [] or null.
- Keep each text field short and actionable.
- If no repository code is provided, prefer code_changes: [] unless the exact current_code is present in the supplied incident data.
"""
    
    return prompt
