# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
PR Creator Service

Handles automated pull request creation for incident fixes.
"""

import uuid
import base64
import httpx
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import (
    IncidentTable,
    RepositoryConnectionTable,
    WorkflowRunTable,
)
from app.services.oauth.token_manager import TokenManager
from app.core.schemas.pr import PRFileChange, AIFixSuggestion

logger = structlog.get_logger(__name__)


class PRCreator:
    """
    Creates pull requests for incident fixes.

    Responsibilities:
    - Analyze incidents and workflow failures
    - Generate code fixes (with AI assistance)
    - Create branches and commits
    - Create pull requests on GitHub
    - Track PR status and outcomes
    """

    def __init__(self, token_manager: TokenManager):
        """
        Initialize PR creator.

        Args:
            token_manager: Token manager for OAuth token access
        """
        self.token_manager = token_manager

    def generate_branch_name(self, incident_id: str, prefix: str = "devflowfix") -> str:
        """
        Generate unique branch name for a fix.

        Args:
            incident_id: Incident ID
            prefix: Branch name prefix

        Returns:
            Branch name like: devflowfix/fix-inc_abc123
        """
        # Extract short ID from incident_id
        short_id = incident_id.split("_")[-1][:8] if "_" in incident_id else incident_id[:8]
        return f"{prefix}/fix-{short_id}"

    async def get_repository_default_branch(
        self,
        access_token: str,
        owner: str,
        repo: str,
    ) -> str:
        """
        Get repository's default branch.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name

        Returns:
            Default branch name (e.g., "main" or "master")
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            repo_data = response.json()
            return repo_data.get("default_branch", "main")

    async def get_file_content(
        self,
        access_token: str,
        owner: str,
        repo: str,
        file_path: str,
        ref: str = "main",
    ) -> Tuple[str, str]:
        """
        Get file content from GitHub.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            file_path: Path to file
            ref: Branch/commit reference

        Returns:
            Tuple of (content, sha)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                params={"ref": ref},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            if response.status_code == 404:
                # File doesn't exist
                return "", ""

            response.raise_for_status()
            file_data = response.json()

            # Decode base64 content
            content = base64.b64decode(file_data["content"]).decode("utf-8")
            sha = file_data["sha"]

            return content, sha

    async def create_or_update_file(
        self,
        access_token: str,
        owner: str,
        repo: str,
        file_path: str,
        content: str,
        message: str,
        branch: str,
        sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create or update a file in GitHub repository.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            file_path: Path to file
            content: File content
            message: Commit message
            branch: Branch name
            sha: File SHA (required for updates)

        Returns:
            Commit information
        """
        # Encode content to base64
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }

        if sha:
            payload["sha"] = sha

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

            response.raise_for_status()
            return response.json()

    async def create_branch(
        self,
        access_token: str,
        owner: str,
        repo: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Create a new branch in GitHub repository.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            branch_name: New branch name
            from_branch: Source branch to branch from

        Returns:
            Branch reference information
        """
        # Get the SHA of the source branch
        async with httpx.AsyncClient() as client:
            # Get source branch ref
            ref_response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{from_branch}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            ref_response.raise_for_status()
            source_sha = ref_response.json()["object"]["sha"]

            # Create new branch
            create_response = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/git/refs",
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": source_sha,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            create_response.raise_for_status()
            return create_response.json()

    async def create_pull_request(
        self,
        access_token: str,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a pull request in GitHub repository.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            title: PR title
            body: PR description
            head_branch: Source branch
            base_branch: Target branch
            draft: Create as draft PR

        Returns:
            Pull request information
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                json={
                    "title": title,
                    "body": body,
                    "head": head_branch,
                    "base": base_branch,
                    "draft": draft,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_pull_request(
        self,
        access_token: str,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> Dict[str, Any]:
        """
        Get pull request details from GitHub.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Pull request details
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    async def list_pull_requests(
        self,
        access_token: str,
        owner: str,
        repo: str,
        state: str = "all",
        head: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List pull requests in repository.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            state: PR state (open, closed, all)
            head: Filter by head branch

        Returns:
            List of pull requests
        """
        params = {"state": state}
        if head:
            params["head"] = f"{owner}:{head}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    async def update_pull_request(
        self,
        access_token: str,
        owner: str,
        repo: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update pull request.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            title: New title
            body: New description
            state: New state (open, closed)

        Returns:
            Updated PR information
        """
        payload = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        if state:
            payload["state"] = state

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    async def merge_pull_request(
        self,
        access_token: str,
        owner: str,
        repo: str,
        pr_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "squash",
    ) -> Dict[str, Any]:
        """
        Merge a pull request.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            commit_title: Merge commit title
            commit_message: Merge commit message
            merge_method: Merge method (merge, squash, rebase)

        Returns:
            Merge result
        """
        payload = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    async def add_pr_comment(
        self,
        access_token: str,
        owner: str,
        repo: str,
        pr_number: int,
        comment: str,
    ) -> Dict[str, Any]:
        """
        Add a comment to a pull request.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            comment: Comment text

        Returns:
            Comment information
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
                json={"body": comment},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    def generate_pr_title(self, incident: IncidentTable) -> str:
        """
        Generate PR title from incident.

        Args:
            incident: Incident record

        Returns:
            PR title
        """
        if incident.workflow_name:
            return f"Fix: {incident.workflow_name} failure in {incident.repository}"
        return f"Fix: CI/CD failure in {incident.repository}"

    def generate_pr_body(
        self,
        incident: IncidentTable,
        file_changes: List[PRFileChange],
        ai_analysis: Optional[str] = None,
    ) -> str:
        """
        Generate PR description from incident and changes.

        Args:
            incident: Incident record
            file_changes: List of file changes
            ai_analysis: Optional AI analysis summary

        Returns:
            PR body markdown
        """
        body_parts = [
            "## 🤖 Automated Fix by DevFlowFix",
            "",
            "### Incident Details",
            f"- **Incident ID:** `{incident.incident_id}`",
            f"- **Repository:** {incident.repository}",
        ]

        if incident.branch:
            body_parts.append(f"- **Branch:** `{incident.branch}`")

        if incident.workflow_name:
            body_parts.append(f"- **Workflow:** {incident.workflow_name}")

        if incident.commit_sha:
            body_parts.append(f"- **Commit:** `{incident.commit_sha[:7]}`")

        body_parts.extend([
            "",
            "### Description",
            incident.description or "Automated fix for CI/CD failure.",
            "",
        ])

        if ai_analysis:
            body_parts.extend([
                "### AI Analysis",
                ai_analysis,
                "",
            ])

        body_parts.extend([
            "### Changes Made",
            f"This PR modifies {len(file_changes)} file(s):",
            "",
        ])

        for change in file_changes:
            body_parts.append(f"- `{change.file_path}` - {change.explanation}")

        body_parts.extend([
            "",
            "### Testing",
            "- [ ] Verify that the workflow runs successfully",
            "- [ ] Check that the fix addresses the root cause",
            "- [ ] Review code changes for correctness",
            "",
            "---",
            "",
            "🔗 [View Incident Details](link-to-incident)",
            "",
            "_This PR was automatically generated by DevFlowFix._",
        ])

        return "\n".join(body_parts)

    async def create_pr_for_incident(
        self,
        db: Session,
        incident_id: str,
        user_id: str,
        file_changes: List[PRFileChange],
        branch_name: Optional[str] = None,
        draft: bool = False,
        ai_analysis: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a pull request for an incident.

        Args:
            db: Database session
            incident_id: Incident ID
            user_id: User ID
            file_changes: List of file changes to apply
            branch_name: Custom branch name
            draft: Create as draft PR
            ai_analysis: AI analysis summary

        Returns:
            PR creation result with details

        Raises:
            ValueError: If incident not found or no repository connection
        """
        # Get incident
        incident = db.query(IncidentTable).filter(
            IncidentTable.incident_id == incident_id,
            IncidentTable.user_id == user_id,
        ).first()

        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        if not incident.repository:
            raise ValueError(f"Incident {incident_id} has no repository information")

        # Get repository connection for OAuth token
        repo_conn = db.query(RepositoryConnectionTable).filter(
            RepositoryConnectionTable.user_id == user_id,
            RepositoryConnectionTable.repository_full_name == incident.repository,
            RepositoryConnectionTable.is_enabled == True,
        ).first()

        if not repo_conn:
            raise ValueError(f"No active repository connection found for {incident.repository}")

        # Get OAuth token
        oauth_conn = await self.token_manager.get_oauth_connection(
            db=db,
            user_id=user_id,
            provider="github",
        )

        if not oauth_conn:
            raise ValueError("No GitHub OAuth connection found")

        access_token = self.token_manager.get_decrypted_token(oauth_conn)

        # Parse repository owner/name
        owner, repo = incident.repository.split("/")

        # Generate branch name if not provided
        if not branch_name:
            branch_name = self.generate_branch_name(incident_id)

        # Get default branch
        default_branch = await self.get_repository_default_branch(
            access_token=access_token,
            owner=owner,
            repo=repo,
        )

        # Create new branch
        try:
            await self.create_branch(
                access_token=access_token,
                owner=owner,
                repo=repo,
                branch_name=branch_name,
                from_branch=default_branch,
            )
            logger.info(
                "branch_created",
                branch=branch_name,
                repository=incident.repository,
            )
        except Exception as e:
            logger.error(
                "branch_creation_failed",
                error=str(e),
                branch=branch_name,
            )
            raise ValueError(f"Failed to create branch: {str(e)}")

        # Apply file changes
        commit_shas = []
        for change in file_changes:
            try:
                # Get current file content and SHA if it exists
                _, file_sha = await self.get_file_content(
                    access_token=access_token,
                    owner=owner,
                    repo=repo,
                    file_path=change.file_path,
                    ref=branch_name,
                )

                # Create/update file
                commit_result = await self.create_or_update_file(
                    access_token=access_token,
                    owner=owner,
                    repo=repo,
                    file_path=change.file_path,
                    content=change.new_content,
                    message=f"Fix: {change.explanation}",
                    branch=branch_name,
                    sha=file_sha if file_sha else None,
                )

                commit_shas.append(commit_result["commit"]["sha"])

                logger.info(
                    "file_updated",
                    file=change.file_path,
                    branch=branch_name,
                )
            except Exception as e:
                logger.error(
                    "file_update_failed",
                    file=change.file_path,
                    error=str(e),
                )
                raise ValueError(f"Failed to update {change.file_path}: {str(e)}")

        # Generate PR title and body
        pr_title = self.generate_pr_title(incident)
        pr_body = self.generate_pr_body(incident, file_changes, ai_analysis)

        # Create pull request
        try:
            pr_result = await self.create_pull_request(
                access_token=access_token,
                owner=owner,
                repo=repo,
                title=pr_title,
                body=pr_body,
                head_branch=branch_name,
                base_branch=default_branch,
                draft=draft,
            )

            logger.info(
                "pr_created",
                pr_number=pr_result["number"],
                pr_url=pr_result["html_url"],
                incident_id=incident_id,
            )

            # Update incident metadata with PR info
            if not incident.metadata:
                incident.metadata = {}

            if "prs" not in incident.metadata:
                incident.metadata["prs"] = []

            incident.metadata["prs"].append({
                "pr_number": pr_result["number"],
                "pr_url": pr_result["html_url"],
                "branch_name": branch_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files_changed": len(file_changes),
            })

            db.flush()

            return {
                "success": True,
                "pr_number": pr_result["number"],
                "pr_url": pr_result["html_url"],
                "branch_name": branch_name,
                "commit_sha": commit_shas[-1] if commit_shas else None,
                "files_changed": len(file_changes),
                "incident_id": incident_id,
                "ai_analysis_used": bool(ai_analysis),
                "error_message": None,
                "created_at": datetime.now(timezone.utc),
            }

        except Exception as e:
            logger.error(
                "pr_creation_failed",
                error=str(e),
                incident_id=incident_id,
            )
            return {
                "success": False,
                "pr_number": None,
                "pr_url": None,
                "branch_name": branch_name,
                "commit_sha": None,
                "files_changed": len(file_changes),
                "incident_id": incident_id,
                "ai_analysis_used": bool(ai_analysis),
                "error_message": str(e),
                "created_at": datetime.now(timezone.utc),
            }
