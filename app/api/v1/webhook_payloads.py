# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)


def _collect_changed_files(payload: Dict[str, Any]) -> List[str]:
    """Collect and deduplicate changed files from GitHub webhook payloads."""
    changed_files: List[str] = []

    workflow_run = payload.get("workflow_run", {})
    workflow_head_commit = workflow_run.get("head_commit", {})
    changed_files.extend(workflow_head_commit.get("modified", []))
    changed_files.extend(workflow_head_commit.get("added", []))
    changed_files.extend(workflow_head_commit.get("removed", []))

    check_run = payload.get("check_run", {})
    check_suite = payload.get("check_suite", {})
    for source in (check_run, check_suite, payload.get("head_commit", {})):
        changed_files.extend(source.get("modified", []))
        changed_files.extend(source.get("added", []))
        changed_files.extend(source.get("removed", []))

    for commit in payload.get("commits", []):
        changed_files.extend(commit.get("modified", []))
        changed_files.extend(commit.get("added", []))
        changed_files.extend(commit.get("removed", []))

    return sorted({file_path for file_path in changed_files if file_path})


def is_github_failure_event(event_type: str, payload: Dict[str, Any]) -> bool:
    """Determine if GitHub webhook event represents a failure."""
    if event_type == "workflow_run":
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")
        status_value = workflow_run.get("status")
        return status_value == "completed" and conclusion in ["failure", "timed_out", "action_required"]

    if event_type == "check_run":
        conclusion = payload.get("check_run", {}).get("conclusion")
        return conclusion in ["failure", "timed_out"]

    return False


def is_argocd_failure_event(payload: Dict[str, Any]) -> bool:
    """Determine if ArgoCD webhook event represents a failure."""
    app_status = payload.get("application", {}).get("status", {})
    sync_status = app_status.get("sync", {}).get("status", "").lower()
    health_status = app_status.get("health", {}).get("status", "").lower()
    return sync_status in ["unknown", "outofsync"] or health_status in ["degraded", "missing", "unknown"]


def is_kubernetes_failure_event(payload: Dict[str, Any]) -> bool:
    """Determine if Kubernetes webhook event represents a failure."""
    event_type = payload.get("type", "").lower()
    reason = payload.get("reason", "").lower()
    failure_reasons = [
        "backoff",
        "failed",
        "unhealthy",
        "evicted",
        "oomkilled",
        "crashloopbackoff",
        "imagepullbackoff",
        "error",
        "killing",
    ]
    if event_type == "warning":
        return True
    return any(r in reason for r in failure_reasons)


def extract_github_payload(payload: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    """Extract and normalize GitHub webhook payload."""
    repository = payload.get("repository", {})
    repository_full_name = repository.get("full_name")
    changed_files = _collect_changed_files(payload)

    if event_type == "workflow_run":
        logger.info(
            "extract_github_payload_called",
            event_type=event_type,
            payload_keys=list(payload.keys()),
            has_workflow_run="workflow_run" in payload,
            has_repository="repository" in payload,
        )
        workflow_run = payload.get("workflow_run", {})

        branch = workflow_run.get("head_branch", "")
        if branch in ["main", "master", "production"]:
            severity = "critical"
        elif branch in ["staging", "develop"]:
            severity = "high"
        else:
            severity = "medium"

        error_log = (
            f"Workflow '{workflow_run.get('name')}' failed\n"
            f"Conclusion: {workflow_run.get('conclusion')}\n"
            f"Repository: {repository_full_name}\n"
            f"Branch: {branch}\n"
            f"Commit: {workflow_run.get('head_sha', '')[:8]}\n"
            f"URL: {workflow_run.get('html_url')}"
        )

        return {
            "severity": severity,
            "error_log": error_log,
            "error_message": f"Workflow failed: {workflow_run.get('conclusion')}",
            "context": {
                "repository": repository_full_name,
                "repository_name": repository.get("name"),
                "repository_id": repository.get("id"),
                "workflow": workflow_run.get("name"),
                "workflow_id": workflow_run.get("workflow_id"),
                "run_id": workflow_run.get("id"),
                "run_number": workflow_run.get("run_number"),
                "branch": branch,
                "commit_sha": workflow_run.get("head_sha"),
                "commit": workflow_run.get("head_sha"),
                "commit_message": workflow_run.get("head_commit", {}).get("message"),
                "author": workflow_run.get("head_commit", {}).get("author", {}).get("name"),
                "event_type": event_type,
                "trigger_event": workflow_run.get("event"),
                "logs_url": workflow_run.get("logs_url"),
                "html_url": workflow_run.get("html_url"),
                "changed_files": changed_files or None,
            },
        }

    if event_type == "check_run":
        check_run = payload.get("check_run", {})
        branch = (
            check_run.get("check_suite", {}).get("head_branch")
            or payload.get("check_suite", {}).get("head_branch")
            or repository.get("default_branch")
            or ""
        )

        if branch in ["main", "master", "production"]:
            severity = "critical"
        elif branch in ["staging", "develop"]:
            severity = "high"
        else:
            severity = "medium"

        error_log = (
            f"Check run '{check_run.get('name')}' failed\n"
            f"Conclusion: {check_run.get('conclusion')}\n"
            f"Repository: {repository_full_name}\n"
            f"Branch: {branch}\n"
            f"Commit: {check_run.get('head_sha', '')[:8]}\n"
            f"URL: {check_run.get('html_url')}"
        )

        return {
            "severity": severity,
            "error_log": error_log,
            "error_message": f"Check run failed: {check_run.get('conclusion')}",
            "context": {
                "repository": repository_full_name,
                "repository_name": repository.get("name"),
                "repository_id": repository.get("id"),
                "workflow": check_run.get("name"),
                "check_run_id": check_run.get("id"),
                "run_id": check_run.get("check_suite", {}).get("id") or check_run.get("id"),
                "branch": branch,
                "commit_sha": check_run.get("head_sha"),
                "commit": check_run.get("head_sha"),
                "event_type": event_type,
                "trigger_event": payload.get("action"),
                "html_url": check_run.get("html_url"),
                "details_url": check_run.get("details_url"),
                "changed_files": changed_files or None,
            },
        }

    return payload


def extract_argocd_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize ArgoCD webhook payload."""
    app = payload.get("application", {})
    metadata = app.get("metadata", {})
    app_status = app.get("status", {})

    sync_status = app_status.get("sync", {}).get("status", "Unknown")
    health_status = app_status.get("health", {}).get("status", "Unknown")

    error_log = (
        f"ArgoCD Application '{metadata.get('name')}' unhealthy\n"
        f"Sync Status: {sync_status}\n"
        f"Health Status: {health_status}\n"
    )

    conditions = app_status.get("conditions", [])
    for condition in conditions:
        error_log += f"Condition: {condition.get('type')} - {condition.get('message', '')}\n"

    return {
        "severity": "high" if health_status.lower() == "degraded" else "medium",
        "error_log": error_log,
        "error_message": f"ArgoCD sync failed: {sync_status}",
        "context": {
            "application": metadata.get("name"),
            "namespace": metadata.get("namespace"),
            "sync_status": sync_status,
            "health_status": health_status,
            "revision": app_status.get("sync", {}).get("revision"),
        },
    }


def extract_kubernetes_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize Kubernetes webhook payload."""
    involved_object = payload.get("involvedObject", payload.get("involved_object", {}))
    reason = payload.get("reason", "Unknown")
    message = payload.get("message", "")

    if reason.lower() in ["oomkilled", "crashloopbackoff"]:
        severity = "critical"
    elif reason.lower() in ["backoff", "unhealthy", "failed"]:
        severity = "high"
    else:
        severity = "medium"

    error_log = (
        f"Kubernetes Event: {reason}\n"
        f"Message: {message}\n"
        f"Object: {involved_object.get('kind')}/{involved_object.get('name')}\n"
        f"Namespace: {involved_object.get('namespace')}"
    )

    return {
        "severity": severity,
        "error_log": error_log,
        "error_message": message,
        "context": {
            "namespace": involved_object.get("namespace"),
            "pod": involved_object.get("name") if involved_object.get("kind") == "Pod" else None,
            "kind": involved_object.get("kind"),
            "reason": reason,
        },
    }
