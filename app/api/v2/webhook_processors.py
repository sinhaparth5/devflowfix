# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Any, Dict

import structlog
from sqlalchemy.orm import Session

from app.adapters.database.postgres.models import (
    ApplicationLogTable,
    IncidentTable,
    LogCategory,
    LogLevel,
    PRStatus,
    PullRequestTable,
    RepositoryConnectionTable,
    WorkflowRunTable,
)
from app.core.config import get_settings
from app.dependencies import get_service_container

logger = structlog.get_logger(__name__)


async def _fetch_error_file_contents(
    access_token: str,
    owner: str,
    repo: str,
    branch: str,
    error_summary: str,
) -> str:
    """Extract file paths from error logs and fetch their contents from GitHub."""
    import base64
    import re

    from app.adapters.external.github.client import GitHubClient

    file_patterns = [
        r'[\w\-_/\.]+\.(py|js|ts|jsx|tsx|java|go|rb|php|cs|cpp|c|h|rs|kt|swift|yaml|yml|json|xml):(\d+)',
        r'File "([^"]+\.(?:py|js|ts|jsx|tsx|java|go|rb|php))", line (\d+)',
        r'at ([^\s:]+\.(?:py|js|ts|jsx|tsx|java|go|rb|php)):(\d+)',
    ]

    file_paths = set()
    for pattern in file_patterns:
        matches = re.findall(pattern, error_summary)
        for match in matches:
            file_path = match[0] if isinstance(match, tuple) else match
            file_path = file_path.strip()
            if file_path and not file_path.startswith("http"):
                file_paths.add(file_path)

    logger.info(
        "extracted_file_paths_from_errors",
        file_count=len(file_paths),
        files=list(file_paths)[:5],
    )

    if not file_paths:
        return None

    github_client = GitHubClient(token=access_token)
    repository_code_parts = []
    for file_path in list(file_paths)[:5]:
        try:
            file_data = await github_client.get_file_contents(
                owner=owner,
                repo=repo,
                path=file_path,
                ref=branch,
            )
            content = base64.b64decode(file_data["content"]).decode("utf-8")
            repository_code_parts.append(f"### File: {file_path}\n```\n{content[:1500]}\n```\n")
            logger.info("fetched_error_file", file_path=file_path, content_length=len(content))
        except Exception as exc:
            logger.warning("failed_to_fetch_error_file", file_path=file_path, error=str(exc))

    if not repository_code_parts:
        return None

    return "\n\n".join(repository_code_parts)


async def process_workflow_run_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """Process workflow_run webhook event."""
    from datetime import datetime, timezone
    import uuid

    action = payload.get("action")
    workflow_run_data = payload.get("workflow_run", {})

    logger.info(
        "processing_workflow_run_event",
        repository=repo_conn.repository_full_name,
        action=action,
        run_id=workflow_run_data.get("id"),
        status=workflow_run_data.get("status"),
        conclusion=workflow_run_data.get("conclusion"),
    )

    if action != "completed":
        return {"status": "ok", "message": f"Workflow action '{action}' not processed"}

    run_id = str(workflow_run_data["id"])
    existing_run = db.query(WorkflowRunTable).filter(
        WorkflowRunTable.repository_connection_id == repo_conn.id,
        WorkflowRunTable.run_id == run_id,
    ).first()

    if existing_run:
        existing_run.status = workflow_run_data["status"]
        existing_run.conclusion = workflow_run_data.get("conclusion")
        existing_run.updated_at = datetime.now(timezone.utc)
        workflow_run = existing_run
        logger.info("workflow_run_updated", run_id=run_id)
    else:
        workflow_run = WorkflowRunTable(
            id=str(uuid.uuid4()),
            repository_connection_id=repo_conn.id,
            run_id=run_id,
            run_number=workflow_run_data["run_number"],
            workflow_name=workflow_run_data["name"],
            workflow_id=str(workflow_run_data["workflow_id"]),
            status=workflow_run_data["status"],
            conclusion=workflow_run_data.get("conclusion"),
            branch=workflow_run_data["head_branch"],
            commit_sha=workflow_run_data["head_sha"],
            commit_message=workflow_run_data.get("head_commit", {}).get("message", ""),
            author=workflow_run_data.get("head_commit", {}).get("author", {}).get("name", ""),
            started_at=datetime.fromisoformat(workflow_run_data["run_started_at"].replace("Z", "+00:00")) if workflow_run_data.get("run_started_at") else None,
            run_url=workflow_run_data["html_url"],
            run_metadata={
                "event": workflow_run_data.get("event"),
                "logs_url": workflow_run_data.get("logs_url"),
                "workflow_path": workflow_run_data.get("path"),
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(workflow_run)
        logger.info("workflow_run_created", run_id=run_id)

    if workflow_run_data.get("conclusion") == "failure":
        existing_incidents = db.query(IncidentTable).filter(
            IncidentTable.user_id == repo_conn.user_id,
            IncidentTable.source == "webhook",
        ).all()

        existing_incident = next(
            (inc for inc in existing_incidents if inc.context and inc.context.get("workflow_run_id") == workflow_run.id),
            None,
        )

        if not existing_incident:
            incident_id = f"inc_{uuid.uuid4().hex[:8]}"
            error_log = (
                f"Workflow run #{workflow_run.run_number} failed.\n\n"
                f"Commit: {workflow_run.commit_sha[:7]}\n"
                f"Branch: {workflow_run.branch}\n"
                f"Message: {workflow_run.commit_message}"
            )

            incident = IncidentTable(
                incident_id=incident_id,
                user_id=repo_conn.user_id,
                timestamp=datetime.now(timezone.utc),
                severity="high",
                source="webhook",
                failure_type="workflow_failure",
                error_log=error_log,
                error_message=f"Workflow '{workflow_run.workflow_name}' failed on {workflow_run.branch}",
                context={
                    "workflow_run_id": workflow_run.id,
                    "repository": repo_conn.repository_full_name,
                    "workflow_name": workflow_run.workflow_name,
                    "branch": workflow_run.branch,
                    "commit_sha": workflow_run.commit_sha,
                    "run_number": workflow_run.run_number,
                    "run_id": run_id,
                    "run_url": workflow_run.run_url,
                    "logs_url": workflow_run.run_metadata.get("logs_url") if workflow_run.run_metadata else None,
                    "event": workflow_run.run_metadata.get("event") if workflow_run.run_metadata else None,
                    "author": workflow_run.author,
                },
                raw_payload=payload,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(incident)
            db.flush()

            pr_created = False
            pr_number = None
            pr_url = None

            if repo_conn.auto_pr_enabled:
                try:
                    from app.core.enums import IncidentSource
                    from app.core.models.incident import Incident
                    from app.services.github_log_parser import GitHubLogExtractor
                    from app.services.oauth.token_manager import get_token_manager
                    from app.services.pr_creator import PRCreatorService

                    settings = get_settings()
                    token_manager = get_token_manager(settings.oauth_token_encryption_key)
                    container = get_service_container()

                    oauth_conn = await token_manager.get_oauth_connection(
                        db=db,
                        user_id=repo_conn.user_id,
                        provider="github",
                    )
                    if not oauth_conn:
                        raise ValueError("No GitHub OAuth connection found")

                    access_token = token_manager.get_decrypted_token(oauth_conn)
                    owner, repo = repo_conn.repository_full_name.split("/")

                    log_extractor = GitHubLogExtractor(github_token=access_token)
                    error_summary = await log_extractor.fetch_and_parse_logs(
                        owner=owner,
                        repo=repo,
                        run_id=int(run_id),
                    )
                    if not error_summary:
                        raise ValueError("No errors found in workflow logs")

                    repository_code = await _fetch_error_file_contents(
                        access_token=access_token,
                        owner=owner,
                        repo=repo,
                        branch=workflow_run.branch,
                        error_summary=error_summary,
                    )

                    domain_incident = Incident(
                        incident_id=incident_id,
                        source=IncidentSource.GITHUB,
                        severity=incident.severity,
                        error_log=error_summary,
                        error_message=incident.error_message,
                        context={
                            "repository": repo_conn.repository_full_name,
                            "workflow": workflow_run.workflow_name,
                            "branch": workflow_run.branch,
                            "commit": workflow_run.commit_sha,
                            "run_id": run_id,
                            "user_id": repo_conn.user_id,
                        },
                        timestamp=incident.created_at,
                    )

                    analyzer = container.get_analyzer_service(db)
                    if not analyzer:
                        raise ValueError("Analyzer service not available")

                    analysis = await analyzer.analyze(incident=domain_incident, similar_incidents=[])
                    solution = await analyzer.llm.generate_solution(
                        error_log=error_summary,
                        failure_type=analysis.category.value if analysis.category else "build_failure",
                        root_cause=analysis.root_cause or "Workflow failure",
                        context=domain_incident.context,
                        repository_code=repository_code,
                    ) or {}

                    if solution.get("code_changes"):
                        pr_creator = PRCreatorService()
                        pr_result = await pr_creator.create_fix_pr(
                            incident=domain_incident,
                            analysis=analysis,
                            solution=solution,
                            user_id=repo_conn.user_id,
                        )
                        pr_created = True
                        pr_number = pr_result.get("number")
                        pr_url = pr_result.get("html_url")
                except Exception as exc:
                    logger.error("auto_pr_creation_error", incident_id=incident_id, error=str(exc), exc_info=True)

            return {
                "status": "ok",
                "action": "incident_created",
                "incident_id": incident_id,
                "workflow_run_id": run_id,
                "auto_pr_created": pr_created,
                "pr_number": pr_number,
                "pr_url": pr_url,
            }

    return {"status": "ok", "action": "workflow_run_processed", "workflow_run_id": run_id}


async def process_pull_request_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """Process pull_request webhook event."""
    from datetime import datetime, timezone

    action = payload.get("action")
    pr_data = payload.get("pull_request", {})
    pr_number = pr_data.get("number")

    pr_record = db.query(PullRequestTable).filter(
        PullRequestTable.repository_full == repo_conn.repository_full_name,
        PullRequestTable.pr_number == pr_number,
    ).first()

    if not pr_record:
        return {
            "status": "ok",
            "action": "pull_request_logged",
            "pr_number": pr_number,
            "message": "PR not tracked (not an auto-fix PR)",
        }

    pr_record.updated_at = datetime.now(timezone.utc)
    if action == "closed":
        if pr_data.get("merged"):
            pr_record.status = PRStatus.MERGED
            pr_record.merged_at = datetime.fromisoformat(pr_data["merged_at"].replace("Z", "+00:00")) if pr_data.get("merged_at") else datetime.now(timezone.utc)
            incident = db.query(IncidentTable).filter(IncidentTable.incident_id == pr_record.incident_id).first()
            if incident:
                incident.outcome = "auto_fixed"
                incident.outcome_message = f"Fixed by PR #{pr_number}"
                incident.resolved_at = pr_record.merged_at
                incident.updated_at = datetime.now(timezone.utc)
                if incident.created_at:
                    incident.resolution_time_seconds = int((pr_record.merged_at - incident.created_at).total_seconds())
                if incident.context:
                    incident.context["merged_pr_number"] = pr_number
                    incident.context["merged_at"] = pr_record.merged_at.isoformat()
        else:
            pr_record.status = PRStatus.CLOSED
            pr_record.closed_at = datetime.now(timezone.utc)
    elif action in {"opened", "reopened", "ready_for_review"}:
        pr_record.status = PRStatus.OPEN
    elif action == "converted_to_draft":
        pr_record.status = PRStatus.DRAFT
    elif action == "review_requested":
        pr_record.status = PRStatus.REVIEW_REQUESTED
    elif action == "synchronize":
        pr_record.commits_count = pr_data.get("commits", pr_record.commits_count)

    if pr_data.get("additions") is not None:
        pr_record.additions = pr_data.get("additions")
    if pr_data.get("deletions") is not None:
        pr_record.deletions = pr_data.get("deletions")
    if pr_data.get("changed_files") is not None:
        pr_record.files_changed = pr_data.get("changed_files")
    if pr_data.get("commits") is not None:
        pr_record.commits_count = pr_data.get("commits")
    if pr_data.get("review_comments") is not None:
        pr_record.review_comments_count = pr_data.get("review_comments")
    if pr_data.get("mergeable") is not None:
        pr_record.has_conflicts = not pr_data.get("mergeable", True)

    return {
        "status": "ok",
        "action": "pull_request_tracked",
        "pr_number": pr_number,
        "new_status": pr_record.status.value,
    }


async def process_push_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """Process GitHub push event."""
    from datetime import datetime, timezone
    import uuid

    ref = payload.get("ref", "")
    commits = payload.get("commits", [])
    before = payload.get("before")
    after = payload.get("after")
    pusher = payload.get("pusher", {})
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

    if not repo_conn.is_enabled:
        return {
            "status": "ok",
            "action": "push_logged",
            "branch": branch,
            "commits": len(commits),
            "analysis": "skipped - repository monitoring disabled",
        }

    modified_files = set()
    for commit in commits:
        modified_files.update(commit.get("added", []))
        modified_files.update(commit.get("modified", []))
        modified_files.update(commit.get("removed", []))

    log_entry = ApplicationLogTable(
        log_id=str(uuid.uuid4()),
        level=LogLevel.INFO.value,
        category=LogCategory.WEBHOOK.value,
        message=f"Push to {branch}: {len(commits)} commit(s)",
        details={
            "repository": repo_conn.repository_full_name,
            "branch": branch,
            "commit_count": len(commits),
            "files_changed": len(modified_files),
            "pusher": pusher.get("name"),
            "before_sha": before,
            "after_sha": after,
            "modified_files": list(modified_files)[:20],
        },
        source="github_webhook",
        created_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)

    risky_patterns = [
        ".github/workflows/",
        "Dockerfile",
        "docker-compose",
        ".env",
        "requirements.txt",
        "package.json",
        "Gemfile",
        "go.mod",
        "pom.xml",
        "build.gradle",
    ]
    risky_files = [
        file_path for file_path in modified_files
        if any(pattern in file_path for pattern in risky_patterns)
    ]

    return {
        "status": "ok",
        "action": "push_analyzed",
        "branch": branch,
        "commits": len(commits),
        "files_changed": len(modified_files),
        "risky_files_detected": len(risky_files),
        "risky_files": risky_files[:5] if risky_files else [],
    }


async def process_gitlab_pipeline_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """Process GitLab pipeline event."""
    from datetime import datetime, timezone
    import uuid

    pipeline = payload.get("object_attributes", {})
    pipeline_id = str(pipeline.get("id"))
    pipeline_status = pipeline.get("status")
    if pipeline_status not in ["success", "failed"]:
        return {"status": "ok", "message": f"Pipeline status '{pipeline_status}' not processed"}

    commit = payload.get("commit", {})
    branch = pipeline.get("ref", "")
    existing_run = db.query(WorkflowRunTable).filter(
        WorkflowRunTable.repository_connection_id == repo_conn.id,
        WorkflowRunTable.run_id == pipeline_id,
    ).first()

    if existing_run:
        existing_run.status = "completed"
        existing_run.conclusion = pipeline_status
        existing_run.updated_at = datetime.now(timezone.utc)
        workflow_run = existing_run
    else:
        workflow_run = WorkflowRunTable(
            id=str(uuid.uuid4()),
            repository_connection_id=repo_conn.id,
            run_id=pipeline_id,
            run_number=pipeline.get("iid", 0),
            workflow_name=pipeline.get("source", "pipeline"),
            workflow_id=str(pipeline.get("id")),
            status="completed",
            conclusion=pipeline_status,
            branch=branch,
            commit_sha=commit.get("id", ""),
            commit_message=commit.get("message", ""),
            author=commit.get("author", {}).get("name", ""),
            started_at=datetime.fromisoformat(pipeline["created_at"].replace("Z", "+00:00")) if pipeline.get("created_at") else None,
            run_url=payload.get("project", {}).get("web_url", "") + f"/-/pipelines/{pipeline_id}",
            run_metadata={
                "source": pipeline.get("source"),
                "stages": pipeline.get("stages", []),
                "duration": pipeline.get("duration"),
                "queued_duration": pipeline.get("queued_duration"),
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(workflow_run)

    if pipeline_status == "failed":
        existing_incidents = db.query(IncidentTable).filter(
            IncidentTable.user_id == repo_conn.user_id,
            IncidentTable.source == "gitlab_webhook",
        ).all()
        existing_incident = next(
            (inc for inc in existing_incidents if inc.context and inc.context.get("workflow_run_id") == workflow_run.id),
            None,
        )
        if not existing_incident:
            incident_id = f"inc_{uuid.uuid4().hex[:8]}"
            failed_jobs = [
                {
                    "name": build.get("name"),
                    "stage": build.get("stage"),
                    "failure_reason": build.get("failure_reason"),
                }
                for build in payload.get("builds", [])
                if build.get("status") == "failed"
            ]
            error_log = (
                f"Pipeline #{pipeline.get('iid', pipeline_id)} failed.\n\n"
                f"Commit: {commit.get('id', '')[:7]}\n"
                f"Branch: {branch}\n"
                f"Message: {commit.get('message', '')}\n\n"
            )
            if failed_jobs:
                error_log += "Failed Jobs:\n"
                for job in failed_jobs:
                    error_log += f"- {job['name']} ({job['stage']}): {job.get('failure_reason', 'unknown')}\n"

            incident = IncidentTable(
                incident_id=incident_id,
                user_id=repo_conn.user_id,
                timestamp=datetime.now(timezone.utc),
                severity="high",
                source="gitlab_webhook",
                failure_type="pipeline_failure",
                error_log=error_log,
                error_message=f"Pipeline failed on {branch}",
                context={
                    "workflow_run_id": workflow_run.id,
                    "repository": repo_conn.repository_full_name,
                    "branch": branch,
                    "commit_sha": commit.get("id", ""),
                    "pipeline_id": pipeline_id,
                    "pipeline_iid": pipeline.get("iid"),
                    "run_url": workflow_run.run_url,
                    "failed_jobs": failed_jobs,
                    "author": commit.get("author", {}).get("name", ""),
                },
                raw_payload=payload,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(incident)
            return {
                "status": "ok",
                "action": "incident_created",
                "incident_id": incident_id,
                "pipeline_id": pipeline_id,
            }

    return {"status": "ok", "action": "pipeline_processed", "pipeline_id": pipeline_id}


async def process_gitlab_merge_request_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """Process GitLab merge request event."""
    from datetime import datetime, timezone

    mr = payload.get("object_attributes", {})
    mr_iid = mr.get("iid")
    action = mr.get("action")
    state = mr.get("state")

    pr_record = db.query(PullRequestTable).filter(
        PullRequestTable.repository_full == repo_conn.repository_full_name,
        PullRequestTable.pr_number == mr_iid,
    ).first()
    if not pr_record:
        return {
            "status": "ok",
            "action": "merge_request_logged",
            "mr_iid": mr_iid,
            "message": "MR not tracked (not an auto-fix MR)",
        }

    pr_record.updated_at = datetime.now(timezone.utc)
    if action == "merge" or state == "merged":
        pr_record.status = PRStatus.MERGED
        pr_record.merged_at = datetime.now(timezone.utc)
        incident = db.query(IncidentTable).filter(IncidentTable.incident_id == pr_record.incident_id).first()
        if incident:
            incident.outcome = "auto_fixed"
            incident.outcome_message = f"Fixed by MR !{mr_iid}"
            incident.resolved_at = datetime.now(timezone.utc)
            incident.updated_at = datetime.now(timezone.utc)
            if incident.context:
                incident.context["merged_mr_iid"] = mr_iid
                incident.context["merged_at"] = datetime.now(timezone.utc).isoformat()
    elif action == "close" or state == "closed":
        pr_record.status = PRStatus.CLOSED
        pr_record.closed_at = datetime.now(timezone.utc)
    elif action == "approved":
        pr_record.status = PRStatus.APPROVED
        pr_record.approved_by = payload.get("user", {}).get("username")
    elif action in {"open", "reopen"}:
        pr_record.status = PRStatus.OPEN

    return {
        "status": "ok",
        "action": "merge_request_tracked",
        "mr_iid": mr_iid,
        "new_status": pr_record.status.value,
    }


async def process_gitlab_push_event(
    db: Session,
    payload: Dict[str, Any],
    repo_conn: RepositoryConnectionTable,
) -> Dict[str, Any]:
    """Process GitLab push event."""
    ref = payload.get("ref", "")
    commits = payload.get("commits", [])
    total_commits = payload.get("total_commits_count", len(commits))

    if not repo_conn.is_enabled:
        return {
            "status": "ok",
            "action": "push_logged",
            "ref": ref,
            "commits": total_commits,
            "analysis": "skipped - repository not enabled",
        }

    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
    logger.info(
        "gitlab_push_received",
        project=repo_conn.repository_full_name,
        branch=branch,
        commits=total_commits,
        user=payload.get("user_username"),
    )
    return {
        "status": "ok",
        "action": "push_logged",
        "ref": ref,
        "branch": branch,
        "commits": total_commits,
    }
