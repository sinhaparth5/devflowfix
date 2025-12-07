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

# Classification prompt template
CLASSIFICATION_PROMPT = """Analyze the following CI/CD incident and provide a structured classification.

## Incident Details

**Source:** {source}
**Error Log:**
```
{error_log}
```

**Context:**
{context}

{similar_incidents_section}

## Your Task

Classify this incident and provide a JSON response with the following structure:

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

## Guidelines

1. **failure_type**: Choose the most specific failure type based on the error log
2. **root_cause**: Provide a clear, actionable description (max 200 chars)
3. **fixability**: 
   - "auto" if can be fixed automatically (restart, rollback, cache clear, etc.)
   - "manual" if requires human intervention (code fix, config change, etc.)
   - "unknown" if insufficient information
4. **confidence**: Your confidence in the classification (0.0 - 1.0)
   - Consider: error message clarity, context completeness, similar incidents
   - Be conservative: if uncertain, lower the confidence
5. **recommended_action**: Best remediation action based on the failure type
6. **reasoning**: Explain why you chose this classification (2-3 sentences)
7. **key_indicators**: List 2-5 key indicators that led to your classification
8. **suggested_parameters**: Parameters needed for the remediation action

## Examples

### Example 1: ImagePullBackOff
```json
{{
  "failure_type": "imagepullbackoff",
  "root_cause": "Container image not found in registry",
  "fixability": "manual",
  "confidence": 0.95,
  "recommended_action": "k8s_update_image",
  "reasoning": "Error message clearly indicates 'ErrImagePull' and 'ImagePullBackOff'. The image tag may be incorrect or the image doesn't exist in the registry. Requires verification and correction of image reference.",
  "key_indicators": ["ErrImagePull", "ImagePullBackOff", "failed to pull image", "not found"],
  "suggested_parameters": {{
    "namespace": "production",
    "deployment": "my-app",
    "verify_image_exists": true
  }}
}}
```

### Example 2: CrashLoopBackOff
```json
{{
  "failure_type": "crashloopbackoff",
  "root_cause": "Application crashing on startup due to configuration error",
  "fixability": "auto",
  "confidence": 0.85,
  "recommended_action": "k8s_restart_pod",
  "reasoning": "Pod is repeatedly crashing after startup. Error indicates missing configuration. A restart may resolve transient issues, but if it persists, manual config fix is needed.",
  "key_indicators": ["CrashLoopBackOff", "Back-off restarting failed container", "Exit code 1"],
  "suggested_parameters": {{
    "namespace": "production",
    "pod_name": "my-app-abc123",
    "wait_time_seconds": 30
  }}
}}
```

### Example 3: GitHub Workflow Build Failure
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

### Example 4: ArgoCD Sync Failed
```json
{{
  "failure_type": "syncfailed",
  "root_cause": "Kubernetes manifest validation failed - invalid resource definition",
  "fixability": "manual",
  "confidence": 0.92,
  "recommended_action": "notify_only",
  "reasoning": "ArgoCD sync failed due to invalid Kubernetes manifest. The error indicates a validation issue that requires manual review and fix of the manifest file. Cannot be auto-remediated.",
  "key_indicators": ["sync failed", "invalid manifest", "ValidationError", "unknown field"],
  "suggested_parameters": {{
    "application": "my-app",
    "notify_channel": "#devops-alerts"
  }}
}}
```

## Important Notes

- **Be conservative with confidence**: If uncertain, use lower confidence (0.5-0.7)
- **Consider context**: Use all available information (similar incidents, context, etc.)
- **Auto-fixability**: Only mark as "auto" if remediation is safe and reliable
- **Transient vs Persistent**: Distinguish between transient issues (network, rate limits) and persistent ones (code bugs, config errors)
- **Output valid JSON**: Ensure your response is valid, parseable JSON

Now analyze the incident above and provide your classification."""

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
    # Format context
    context_str = "\n".join([f"- {k}: {v}" for k, v in context.items() if v])
    
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
        error_log=error_log[:4000],  # Truncate to avoid token limits
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
    context_lines = "\n".join([f"- {k}: {v}" for k, v in context.items() if v])
    
    code_section = ""
    if repository_code:
        code_section = f"\n## Relevant Repository Code\n```\n{repository_code[:2000]}\n```\n"
    
    prompt = f"""You are a CI/CD expert. Analyze the following incident and provide ONLY a valid JSON solution with NO other text.

## INCIDENT DETAILS

**Failure Type:** {failure_type}
**Root Cause:** {root_cause}

**Error Log:**
```
{error_log[:2000]}
```

**Context:**
{context_lines}
{code_section}

## INSTRUCTIONS

Generate ONLY valid JSON (no markdown, no explanations, just JSON) with the following structure:

{{
  "immediate_fix": {{
    "description": "First action to resolve this issue",
    "steps": ["Step 1", "Step 2", "Step 3"],
    "estimated_time_minutes": 15,
    "risk_level": "low"
  }},
  "code_changes": [
    {{
      "file_path": "path/to/file.js",
      "description": "What to change",
      "current_code": "problematic code snippet",
      "fixed_code": "corrected code snippet",
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

IMPORTANT: 
- Return ONLY valid JSON with NO markdown code blocks
- Do NOT include explanations outside the JSON
- All fields should be strings except arrays
- If a section doesn't apply, use empty array [] or null
- Ensure all JSON is valid and properly escaped

Now generate the solution:"""
    
    return prompt