# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Automated PR Creator Service

Creates and tracks automated fix pull requests in source repositories.
Uses per-repository GitHub tokens for secure access.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import structlog

from app.core.models.incident import Incident
from app.core.models.analysis import AnalysisResult
from app.adapters.external.github.client import GitHubClient
from app.adapters.database.postgres.models import (
    PullRequestTable,
    PRCreationLogTable,
    PRStatus,
)
from app.services.github_token_manager import GitHubTokenManager
from app.core.enums import FailureType

logger = structlog.get_logger(__name__)

class PRCreatorService:
    """
    Service for creating automated fix pull requests.

    Creates PRs in source repositories with:
    - Code changes from NVIDIA AI analysis
    - Configuration updates
    - Detailed explanations
    - Prevention measures

    Features:
    - Per-repository GitHub token support
    - PR metadata tracking in database
    - Creation audit logging
    - Automatic branch management

    Example:
        ```python
        service = PRCreatorService()
        
        pr_result = await service.create_fix_pr(
            incident=incident,
            analysis=analysis,
            solution=solution,
        )
        
        print(f"PR created: {pr_result['pr_url']}")
        ```
    """
    def __init__(self, github_client: Optional[GitHubClient] = None):
        """
        Initialize PR creator service.
        
        Args:
            github_client: GitHub API client (optional, uses token manager)
        """
        self.github = github_client
        self.token_manager = GitHubTokenManager()
        self._db_session = None

    async def create_fix_pr(
            self,
            incident: Incident,
            analysis: AnalysisResult,
            solution: Dict[str, Any],
            user_id: Optional[str] = None,
            db_session=None,
    ) -> Dict[str, Any]:
        """
        Create an automated fix PR in the source repository.

        Args:
            incident: Incident details with repo information
            analysis: AI analysis result with root cause and fixability
            solution: NVIDIA AI-generated solution with code changes
            user_id: User ID for token retrieval (required)
            db_session: Database session for tracking

        Returns:
            PR result with metadata

        Raises:
            ValueError: If repository information or user_id not found
        """
        from app.dependencies import get_db

        # Get user_id from incident context if not provided
        if not user_id:
            user_id = incident.context.get("user_id")

        if not user_id:
            raise ValueError(
                "Cannot create PR: user_id required. "
                "Ensure the webhook includes user_id in the incident context."
            )

        repo_info = self._extract_repo_info(incident)
        if not repo_info:
            raise ValueError("Cannot create PR: repository info not found")

        owner = repo_info["owner"]
        repo = repo_info["repo"]
        base_branch = repo_info.get("branch", "main")

        # Get repo-specific GitHub token for THIS USER
        token = self.token_manager.get_token(user_id, owner, repo)
        if not token:
            raise ValueError(
                f"No GitHub token found for user {user_id} and repository {owner}/{repo}. "
                "Please register your token via /api/v1/pr-management/tokens/register"
            )
        
        # Create authenticated GitHub client for this repo
        github_client = GitHubClient(token=token)

        logger.info(
            "pr_creation_start",
            incident_id=incident.incident_id,
            owner=owner,
            repo=repo,
            failure_type=analysis.category.value,
            confidence=analysis.confidence,
        )

        creation_log_id = f"log_{uuid4()}"
        start_time = datetime.now(timezone.utc)
        
        try:
            branch_name = self._generate_branch_name(incident, analysis)
            await self._create_branch(
                github_client, owner, repo, base_branch, branch_name
            )

            changed_files = await self._apply_code_changes(
                github_client=github_client,
                owner=owner,
                repo=repo,
                branch=branch_name,
                code_changes=solution.get("code_changes", []),
            )

            config_files = await self._apply_config_changes(
                github_client=github_client,
                owner=owner,
                repo=repo,
                branch=branch_name,
                config_changes=solution.get("configuration_changes", []),
            )

            pr_title = self._generate_pr_title(analysis)
            pr_body = self._generate_pr_body(
                incident=incident,
                analysis=analysis,
                solution=solution,
                changed_files=changed_files + config_files,
            )

            logger.info(
                "pr_creation_payload",
                title_length=len(pr_title),
                body_length=len(pr_body),
                head=branch_name,
                base=base_branch,
            )

            pr_result = await github_client.create_pull_request(
                owner=owner,
                repo=repo,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch,
            )

            # Store PR metadata in database
            db_gen = None
            if db_session:
                db = db_session
            else:
                db_gen = get_db()
                db = next(db_gen)

            try:
                pr_id = f"pr_{uuid4()}"

                pr_record = PullRequestTable(
                    id=pr_id,
                    incident_id=incident.incident_id,
                    repository_owner=owner,
                    repository_name=repo,
                    repository_full=f"{owner}/{repo}",
                    pr_number=pr_result["number"],
                    pr_url=pr_result["html_url"],
                    branch_name=branch_name,
                    base_branch=base_branch,
                    title=pr_title,
                    description=pr_body,
                    status=PRStatus.CREATED,
                    files_changed=len(changed_files + config_files),
                    failure_type=analysis.category.value if analysis.category else "unknown",
                    root_cause=analysis.root_cause,
                    confidence_score=analysis.confidence,
                    metadata={
                        "incident_id": incident.incident_id,
                        "created_by": "devflowfix",
                        "version": "1.0",
                    },
                )

                db.add(pr_record)

                # Log creation attempt
                creation_log = PRCreationLogTable(
                    id=creation_log_id,
                    incident_id=incident.incident_id,
                    pr_id=pr_id,
                    repository_full=f"{owner}/{repo}",
                    branch_name=branch_name,
                    failure_type=analysis.category.value if analysis.category else "unknown",
                    root_cause=analysis.root_cause,
                    files_to_change=len(changed_files + config_files),
                    status="success",
                    duration_ms=int(
                        (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    ),
                    pr_url=pr_result["html_url"],
                )

                db.add(creation_log)
                db.commit()
            finally:
                if db_gen:
                    db.close()

            logger.info(
                "pr_created_success",
                incident_id=incident.incident_id,
                pr_id=pr_id,
                pr_number=pr_result["number"],
                pr_url=pr_result["html_url"],
                files_changed=len(changed_files + config_files),
            )

            return {
                **pr_result,
                "pr_id": pr_id,
                "files_changed": changed_files + config_files,
                "timestamp": start_time.isoformat(),
            }
            
        except Exception as e:
            logger.error(
                "pr_creation_failed",
                incident_id=incident.incident_id,
                owner=owner,
                repo=repo,
                error=str(e),
                exc_info=True,
            )

            # Log failed attempt
            db_gen_err = None
            try:
                if db_session:
                    db = db_session
                else:
                    db_gen_err = get_db()
                    db = next(db_gen_err)
                
                creation_log = PRCreationLogTable(
                    id=creation_log_id,
                    incident_id=incident.incident_id,
                    pr_id=None,
                    repository_full=f"{owner}/{repo}",
                    branch_name=self._generate_branch_name(incident, analysis),
                    failure_type=analysis.category.value if analysis.category else "unknown",
                    root_cause=analysis.root_cause,
                    files_to_change=len(solution.get("code_changes", [])),
                    status="failed",
                    duration_ms=int(
                        (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    ),
                    error_message=str(e),
                    error_type=type(e).__name__[:36],  # Truncate to fit DB constraint
                )

                db.add(creation_log)
                db.commit()
            except Exception as log_error:
                logger.error("failed_to_log_pr_creation_error", error=str(log_error))
            finally:
                if db_gen_err:
                    db.close()

            raise
    
    def _extract_repo_info(self, incident: Incident) -> Optional[Dict[str, str]]:
        """Extract owner/repo from incident context."""
        repo_full = incident.context.get("repository")
        if not repo_full:
            return None
        
        parts = repo_full.split("/")
        if len(parts) != 2:
            return None
        
        return {
            "owner": parts[0],
            "repo": parts[1],
            "branch": incident.context.get("branch", "main"),
        }
    
    def _generate_branch_name(
            self,
            incident: Incident,
            analysis: AnalysisResult,
    ) -> str:
        """Generate branch name for the fix."""
        failure_type = analysis.category.value.replace("_", "-")
        incident_id = incident.incident_id[:8]
        return f"devflowfix/auto-fix-{failure_type}-{incident_id}"
    
    async def _create_branch(
            self,
            github_client: GitHubClient,
            owner: str,
            repo: str,
            base_branch: str,
            new_branch: str,
    ):
        """Create new branch from base."""
        base_ref = await github_client.get_ref(owner, repo, f"heads/{base_branch}")
        base_sha = base_ref["object"]["sha"]

        await github_client.create_ref(
            owner=owner,
            repo=repo,
            ref=f"refs/heads/{new_branch}",
            sha=base_sha,
        )

        logger.info(
            "branch_created",
            owner=owner,
            repo=repo,
            branch=new_branch
        )

    async def _apply_code_changes(
            self,
            github_client: GitHubClient,
            owner: str,
            repo: str,
            branch: str,
            code_changes: List[Dict[str, Any]],
    ) -> List[str]:
        """Apply code changes to files."""
        changed_files = []

        for change in code_changes:
            file_path = change.get("file_path")
            fixed_code = change.get("fixed_code")
            current_code = change.get("current_code")
            line_number = change.get("line_number")
            
            if not file_path or not fixed_code:
                continue

            try:
                # Fetch the current file content from the repository
                try:
                    current_file = await github_client.get_file_contents(
                        owner=owner,
                        repo=repo,
                        path=file_path,
                        ref=branch,
                    )
                    sha = current_file["sha"]
                    
                    # Decode the file content (GitHub returns base64-encoded content)
                    import base64
                    file_content = base64.b64decode(current_file["content"]).decode('utf-8')
                    
                    # Strategy 1: If current_code is provided, try exact match and replace
                    if current_code and current_code.strip() in file_content:
                        # Replace the specific problematic code
                        updated_content = file_content.replace(current_code, fixed_code)
                        logger.info(
                            "code_replaced_using_exact_match",
                            file=file_path,
                            current_code_length=len(current_code),
                            fixed_code_length=len(fixed_code),
                        )
                    # Strategy 2: Try fuzzy matching (ignoring whitespace differences)
                    elif current_code:
                        import re
                        # Normalize whitespace in both current and file content
                        normalized_current = re.sub(r'\\s+', ' ', current_code.strip())
                        lines = file_content.split('\\n')
                        
                        replaced = False
                        for i, line in enumerate(lines):
                            normalized_line = re.sub(r'\\s+', ' ', line.strip())
                            if normalized_current in normalized_line or normalized_line in normalized_current:
                                # Found a fuzzy match, replace this line
                                lines[i] = fixed_code if not fixed_code.endswith('\\n') else fixed_code.rstrip('\\n')
                                replaced = True
                                logger.info(
                                    "code_replaced_using_fuzzy_match",
                                    file=file_path,
                                    line_number=i+1,
                                )
                                break
                        
                        if replaced:
                            updated_content = '\\n'.join(lines)
                        elif line_number is not None:
                            # Fall back to line number
                            if 0 < line_number <= len(lines):
                                lines[line_number - 1] = fixed_code if not fixed_code.endswith('\\n') else fixed_code.rstrip('\\n')
                                updated_content = '\\n'.join(lines)
                                logger.info(
                                    "code_replaced_at_line_fallback",
                                    file=file_path,
                                    line_number=line_number,
                                )
                            else:
                                # Line number out of range
                                updated_content = file_content + '\\n' + fixed_code
                                logger.warning(
                                    "line_number_out_of_range_appending",
                                    file=file_path,
                                    line_number=line_number,
                                    total_lines=len(lines),
                                )
                        else:
                            # No match found, use fixed_code as entire content
                            updated_content = fixed_code
                            logger.warning(
                                "no_match_found_using_fixed_code",
                                file=file_path,
                            )
                    # Strategy 3: Use line number if provided
                    elif line_number is not None:
                        # Use line number to apply the fix
                        lines = file_content.split('\\n')
                        if 0 < line_number <= len(lines):
                            # Replace the line at the specified line number
                            lines[line_number - 1] = fixed_code if not fixed_code.endswith('\\n') else fixed_code.rstrip('\\n')
                            updated_content = '\\n'.join(lines)
                            logger.info(
                                "code_replaced_at_line",
                                file=file_path,
                                line_number=line_number,
                            )
                        else:
                            # Line number out of range, append at the end
                            updated_content = file_content + '\\n' + fixed_code
                            logger.warning(
                                "line_number_out_of_range_appending",
                                file=file_path,
                                line_number=line_number,
                                total_lines=len(lines),
                            )
                    else:
                        # No current_code or line_number, use fixed_code as entire file content
                        updated_content = fixed_code
                        logger.info(
                            "using_fixed_code_as_entire_file",
                            file=file_path,
                        )
                    
                except Exception as fetch_error:
                    # File doesn't exist, create new file with fixed_code
                    logger.warning(
                        "file_not_found_creating_new",
                        file=file_path,
                        error=str(fetch_error),
                    )
                    sha = None
                    updated_content = fixed_code

                # Update the file in the repository
                await github_client.create_or_update_file(
                    owner=owner,
                    repo=repo,
                    path=file_path,
                    message=f"fix: {change.get('explanation', 'Auto-fix code issue')}",
                    content=updated_content,
                    branch=branch,
                    sha=sha,
                )

                changed_files.append(file_path)

                logger.info(
                    "code_change_applied",
                    owner=owner,
                    repo=repo,
                    file=file_path,
                )

            except Exception as e:
                logger.error(
                    "code_change_failed",
                    file=file_path,
                    error=str(e),
                    exc_info=True,
                )
        return changed_files
    
    async def _apply_config_changes(
            self,
            github_client: GitHubClient,
            owner: str,
            repo: str,
            branch: str,
            config_changes: List[Dict[str, Any]],       
    ) -> List[str]:
        """Apply configuration changes."""
        changed_files = []
        
        # Handle None or empty config_changes
        if not config_changes:
            return changed_files

        for change in config_changes:
            file_path = change.get("file")
            
            if not file_path:
                continue
            
            try:
                try:
                    current_file = await github_client.get_file_contents(
                        owner=owner,
                        repo=repo,
                        path=file_path,
                        ref=branch,
                    )
                    sha = current_file["sha"]
                except:
                    sha = None
                
                # Use recommended value for config
                new_value = change.get("recommended_value", change.get("value", ""))
                
                config_content = f"{change.get('setting', 'config')}: {new_value}\n"
                
                await github_client.create_or_update_file(
                    owner=owner,
                    repo=repo,
                    path=file_path,
                    message=f"config: {change.get('reason', 'Update configuration')}",
                    content=config_content,
                    branch=branch,
                    sha=sha,
                )
                
                changed_files.append(file_path)
                
                logger.info(
                    "config_change_applied",
                    owner=owner,
                    repo=repo,
                    file=file_path,
                    setting=change.get('setting'),
                )
                
            except Exception as e:
                logger.error(
                    "config_change_failed",
                    file=file_path,
                    error=str(e),
                )
        
        return changed_files


    def _generate_pr_title(self, analysis: AnalysisResult) -> str:
        """Generate PR title."""
        failure_type = analysis.category.value.replace("_", " ").title()
        return f"DevFlowFix: {failure_type}"
    
    def _generate_pr_body(
        self,
        incident: Incident,
        analysis: AnalysisResult,
        solution: Dict[str, Any],
        changed_files: List[str],
    ) -> str:
        """Generate detailed PR description."""
        immediate_fix = solution.get("immediate_fix", {})
        code_changes = solution.get("code_changes", [])
        prevention = solution.get("prevention_measures", [])
        
        body = f"""## 🤖 Automated Fix by DevFlowFix

### Problem Detected
- **Failure Type**: {analysis.category.value.replace("_", " ").title()}
- **Root Cause**: {analysis.root_cause}
- **Confidence**: {analysis.confidence:.0%}
- **Incident ID**: `{incident.incident_id}`

### Changes Made

"""
        
        # List changed files
        if changed_files:
            body += "**Modified Files:**\n"
            for file in changed_files:
                body += f"- `{file}`\n"
            body += "\n"
        
        # Immediate fix description
        if immediate_fix:
            body += f"""### Fix Description

{immediate_fix.get('description', '')}

**Estimated Time**: {immediate_fix.get('estimated_time_minutes', 0)} minutes
**Risk Level**: {immediate_fix.get('risk_level', 'Unknown').upper()}

**Steps Taken**:
"""
            for i, step in enumerate(immediate_fix.get('steps', []), 1):
                body += f"{i}. {step}\n"
            body += "\n"
        
        # Code changes detail
        if code_changes:
            body += "### Code Changes\n\n"
            for idx, change in enumerate(code_changes, 1):
                body += f"**{idx}. {change.get('file_path', 'N/A')}**\n"
                body += f"- Line(s): {change.get('line_numbers', 'N/A')}\n"
                body += f"- Explanation: {change.get('explanation', 'N/A')}\n\n"
        
        # Prevention measures
        if prevention:
            body += "### Prevention Measures\n\n"
            body += "To prevent similar issues in the future:\n\n"
            for measure in prevention[:3]:
                body += f"- **{measure.get('measure', '')}**: "
                body += f"{measure.get('description', '')}\n"
            body += "\n"
        
        # Footer
        body += """---

*This PR was automatically generated by DevFlowFix AI. Please review the changes before merging.*

**Review Checklist**:
- [ ] Changes address the root cause
- [ ] No unintended side effects
- [ ] Tests pass
- [ ] Documentation updated (if needed)
"""
        
        return body
    
    def should_create_pr(
        self,
        analysis: AnalysisResult,
        incident: Incident,
        min_confidence: float = 0.85,
    ) -> bool:
        """
        Determine if PR should be created.
        
        Args:
            analysis: Analysis result
            incident: Incident details
            min_confidence: Minimum confidence threshold
            
        Returns:
            True if PR should be created
        """
        # Check confidence
        if analysis.confidence < min_confidence:
            logger.info(
                "pr_skipped_low_confidence",
                incident_id=incident.incident_id,
                confidence=analysis.confidence,
            )
            return False
        
        # Only create PRs for certain failure types
        auto_fix_types = [
            FailureType.LINT_FAILURE,
            FailureType.TEST_FAILURE,
            FailureType.DEPENDENCY_ERROR,
            FailureType.CONFIG_ERROR,
        ]
        
        if analysis.category not in auto_fix_types:
            logger.info(
                "pr_skipped_failure_type",
                incident_id=incident.incident_id,
                failure_type=analysis.category.value,
            )
            return False
        
        # Check if repo info available
        if not incident.context.get("repository"):
            logger.info(
                "pr_skipped_no_repo",
                incident_id=incident.incident_id,
            )
            return False
        
        return True 