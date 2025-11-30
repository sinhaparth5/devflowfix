# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub API Client

Provides HTTP client for interacting with GitHub API with:
- Authentication (token-based and GitHub App)
- Automatic retries with exponential backoff
- Circuit breaker for fault tolerance
- Rate limit handling
- Comprehensive error handling
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx

from app.core.config import Settings
from app.exceptions import GitHubAPIError
from app.utils.logging import get_logger
from app.utils.retry import retry
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


class GitHubClient:
    """
    HTTP client for GitHub API.
    
    Features:
    - Token authentication
    - Automatic retries with exponential backoff
    - Circuit breaker pattern for fault tolerance
    - Rate limit tracking and handling
    - Comprehensive error handling
    
    Example:
        ```python
        client = GitHubClient(token="ghp_...")
        
        # Get workflow run
        run = await client.get_workflow_run(
            owner="myorg",
            repo="myrepo",
            run_id=123456
        )
        
        # Rerun failed jobs
        await client.rerun_failed_jobs(
            owner="myorg",
            repo="myrepo",
            run_id=123456
        )
        ```
    """
    
    BASE_URL = "https://api.github.com"
    API_VERSION = "2022-11-28"
    
    def __init__(
        self,
        token: Optional[str] = None,
        settings: Optional[Settings] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize GitHub client.
        
        Args:
            token: GitHub personal access token or app token
            settings: Application settings
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.settings = settings or Settings()
        self.token = token or self.settings.github.token
        self.timeout = timeout
        self.max_retries = max_retries
        
        if not self.token:
            logger.warning("github_client_no_token", message="GitHub token not configured")
        
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            headers=self._get_default_headers(),
            follow_redirects=True,
        )
        
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            timeout=60.0,
            expected_exception=GitHubAPIError,
            name="github_api",
        )
        
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset: Optional[datetime] = None
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.API_VERSION,
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    def _update_rate_limit(self, headers: httpx.Headers) -> None:
        """Update rate limit information from response headers."""
        if "x-ratelimit-remaining" in headers:
            self._rate_limit_remaining = int(headers["x-ratelimit-remaining"])
        
        if "x-ratelimit-reset" in headers:
            reset_timestamp = int(headers["x-ratelimit-reset"])
            self._rate_limit_reset = datetime.fromtimestamp(reset_timestamp)
            
            logger.debug(
                "github_rate_limit_updated",
                remaining=self._rate_limit_remaining,
                reset_at=self._rate_limit_reset.isoformat() if self._rate_limit_reset else None,
            )
    
    def _check_rate_limit(self) -> None:
        """Check if we're about to hit rate limit."""
        if self._rate_limit_remaining is not None and self._rate_limit_remaining < 10:
            logger.warning(
                "github_rate_limit_low",
                remaining=self._rate_limit_remaining,
                reset_at=self._rate_limit_reset.isoformat() if self._rate_limit_reset else None,
            )
            
            if self._rate_limit_remaining == 0:
                wait_seconds = 0
                if self._rate_limit_reset:
                    wait_seconds = (self._rate_limit_reset - datetime.now()).total_seconds()
                
                raise GitHubAPIError(
                    f"GitHub API rate limit exceeded. Resets in {wait_seconds:.0f} seconds.",
                    status_code=429,
                )
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to GitHub API with error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for httpx request
            
        Returns:
            Response JSON data
            
        Raises:
            GitHubAPIError: On API errors
        """
        self._check_rate_limit()
        
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            
            self._update_rate_limit(response.headers)
            
            if response.status_code >= 400:
                error_data = {}
                try:
                    error_data = response.json()
                except Exception:
                    pass
                
                error_message = error_data.get("message", response.text)
                
                logger.error(
                    "github_api_error",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                    message=error_message,
                )
                
                raise GitHubAPIError(
                    f"GitHub API error: {error_message}",
                    status_code=response.status_code,
                    response=error_data,
                )
            
            if response.status_code == 204: 
                return {}
            
            return response.json()
        
        except httpx.HTTPError as e:
            logger.error(
                "github_http_error",
                method=method,
                endpoint=endpoint,
                error=str(e),
            )
            raise GitHubAPIError(f"HTTP error calling GitHub API: {e}") from e
    
    @retry(
        max_attempts=3,
        base_delay=1.0,
        exponential_backoff=True,
        exceptions=(GitHubAPIError,),
    )
    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make GET request to GitHub API.
        
        Args:
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        return await self.circuit_breaker._call_async(
            self._request,
            "GET",
            endpoint,
            **kwargs,
        )
    
    @retry(
        max_attempts=3,
        base_delay=1.0,
        exponential_backoff=True,
        exceptions=(GitHubAPIError,),
    )
    async def post(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make POST request to GitHub API.
        
        Args:
            endpoint: API endpoint
            json: JSON body data
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        return await self.circuit_breaker._call_async(
            self._request,
            "POST",
            endpoint,
            json=json,
            **kwargs,
        )
    
    @retry(
        max_attempts=3,
        base_delay=1.0,
        exponential_backoff=True,
        exceptions=(GitHubAPIError,),
    )
    async def patch(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make PATCH request to GitHub API.
        
        Args:
            endpoint: API endpoint
            json: JSON body data
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        return await self.circuit_breaker._call_async(
            self._request,
            "PATCH",
            endpoint,
            json=json,
            **kwargs,
        )
    
    @retry(
        max_attempts=3,
        base_delay=1.0,
        exponential_backoff=True,
        exceptions=(GitHubAPIError,),
    )
    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make DELETE request to GitHub API.
        
        Args:
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        return await self.circuit_breaker._call_async(
            self._request,
            "DELETE",
            endpoint,
            **kwargs,
        )
    
    
    async def get_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Get workflow run details.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Workflow run data
        """
        endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}"
        
        logger.info(
            "github_get_workflow_run",
            owner=owner,
            repo=repo,
            run_id=run_id,
        )
        
        return await self.get(endpoint)
    
    async def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        List workflow runs for a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            workflow_id: Optional workflow ID to filter
            status: Optional status filter (completed, in_progress, etc.)
            per_page: Results per page
            
        Returns:
            List of workflow runs
        """
        if workflow_id:
            endpoint = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        else:
            endpoint = f"/repos/{owner}/{repo}/actions/runs"
        
        params = {"per_page": per_page}
        if status:
            params["status"] = status
        
        response = await self.get(endpoint, params=params)
        return response.get("workflow_runs", [])
    
    async def rerun_workflow(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Rerun entire workflow.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Response data
        """
        endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun"
        
        logger.info(
            "github_rerun_workflow",
            owner=owner,
            repo=repo,
            run_id=run_id,
        )
        
        return await self.post(endpoint)
    
    async def rerun_failed_jobs(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Rerun only failed jobs in a workflow.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Response data
        """
        endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs"
        
        logger.info(
            "github_rerun_failed_jobs",
            owner=owner,
            repo=repo,
            run_id=run_id,
        )
        
        return await self.post(endpoint)
    
    async def cancel_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Cancel a workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            Response data
        """
        endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel"
        
        logger.info(
            "github_cancel_workflow",
            owner=owner,
            repo=repo,
            run_id=run_id,
        )
        
        return await self.post(endpoint)
    
    
    async def list_jobs_for_workflow_run(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> List[Dict[str, Any]]:
        """
        List jobs for a workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            List of jobs
        """
        endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        response = await self.get(endpoint)
        return response.get("jobs", [])
    
    async def get_job(
        self,
        owner: str,
        repo: str,
        job_id: int,
    ) -> Dict[str, Any]:
        """
        Get job details.
        
        Args:
            owner: Repository owner
            repo: Repository name
            job_id: Job ID
            
        Returns:
            Job data
        """
        endpoint = f"/repos/{owner}/{repo}/actions/jobs/{job_id}"
        return await self.get(endpoint)
    
    async def download_job_logs(
        self,
        owner: str,
        repo: str,
        job_id: int,
    ) -> str:
        """
        Download job logs.
        
        Args:
            owner: Repository owner
            repo: Repository name
            job_id: Job ID
            
        Returns:
            Log text
        """
        endpoint = f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
        
        try:
            response = await self.client.get(endpoint)
            response.raise_for_status()
            return response.text
        
        except httpx.HTTPError as e:
            logger.error(
                "github_download_logs_error",
                owner=owner,
                repo=repo,
                job_id=job_id,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to download job logs: {e}") from e
    
    
    async def get_repository(
        self,
        owner: str,
        repo: str,
    ) -> Dict[str, Any]:
        """
        Get repository information.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Repository data
        """
        endpoint = f"/repos/{owner}/{repo}"
        return await self.get(endpoint)
    
    async def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> Dict[str, Any]:
        """
        Create a comment on an issue or pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue or PR number
            body: Comment body
            
        Returns:
            Comment data
        """
        endpoint = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        
        logger.info(
            "github_create_comment",
            owner=owner,
            repo=repo,
            issue_number=issue_number,
        )
        
        return await self.post(endpoint, json={"body": body})
    
    
    async def get_rate_limit(self) -> Dict[str, Any]:
        """
        Get current rate limit status.
        
        Returns:
            Rate limit information
        """
        return await self.get("/rate_limit")
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get circuit breaker status.
        
        Returns:
            Circuit breaker statistics
        """
        return self.circuit_breaker.get_stats()
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
