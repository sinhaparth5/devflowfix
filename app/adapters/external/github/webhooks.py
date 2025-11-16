# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""GitHub webhook client with signature verification."""

import os
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class GitHubWebhookError(Exception):
    """Base exception for GitHub webhook errors."""
    pass


class WebhookSignatureError(GitHubWebhookError):
    """Exception raised when webhook signature verification fails."""
    pass


class WebhookPayloadError(GitHubWebhookError):
    """Exception raised when webhook payload is invalid."""
    pass


class GitHubWebhookClient:
    """
    GitHub webhook client with HMAC-SHA256 signature verification.
    
    This client verifies that incoming webhook requests are authentic
    by validating the HMAC-SHA256 signature sent by GitHub.
    """
    
    def __init__(self, webhook_secret: Optional[str] = None):
        """
        Initialize the GitHub webhook client.
        
        Args:
            webhook_secret: GitHub webhook secret for signature verification.
                          Falls back to GITHUB_WEBHOOK_SECRET env var if not provided.
                          
        Raises:
            ValueError: If webhook secret is not provided and not found in env vars.
        """
        self.webhook_secret = webhook_secret or os.getenv("GITHUB_WEBHOOK_SECRET")
        
        if not self.webhook_secret:
            raise ValueError(
                "GitHub webhook secret not provided. Set GITHUB_WEBHOOK_SECRET "
                "environment variable or pass webhook_secret parameter."
            )
        
        logger.info("GitHub webhook client initialized")
    
    def verify_signature(
        self,
        payload_body: bytes,
        signature_header: str,
    ) -> bool:
        """
        Verify the GitHub webhook signature using HMAC-SHA256.
        
        Args:
            payload_body: Raw request body as bytes
            signature_header: Value of X-Hub-Signature-256 header from GitHub
            
        Returns:
            True if signature is valid, False otherwise
            
        Example:
            ```python
            client = GitHubWebhookClient()
            is_valid = client.verify_signature(
                payload_body=request.body,
                signature_header=request.headers.get("X-Hub-Signature-256")
            )
            ```
        """
        if not signature_header:
            logger.warning("Missing X-Hub-Signature-256 header")
            return False
        
        if not signature_header.startswith("sha256="):
            logger.warning(f"Invalid signature format: {signature_header}")
            return False
        
        github_signature = signature_header.split("=", 1)[1]
        
        expected_signature = self._compute_signature(payload_body)
        
        is_valid = hmac.compare_digest(github_signature, expected_signature)
        
        if not is_valid:
            logger.warning("Webhook signature verification failed")
        else:
            logger.debug("Webhook signature verified successfully")
        
        return is_valid
    
    def _compute_signature(self, payload_body: bytes) -> str:
        """
        Compute HMAC-SHA256 signature for the payload.
        
        Args:
            payload_body: Raw request body as bytes
            
        Returns:
            Hexadecimal signature string
        """
        secret_bytes = self.webhook_secret.encode('utf-8')
        signature = hmac.new(
            key=secret_bytes,
            msg=payload_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def verify_and_parse(
        self,
        payload_body: bytes,
        signature_header: str,
        event_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify signature and parse webhook payload.
        
        Args:
            payload_body: Raw request body as bytes
            signature_header: Value of X-Hub-Signature-256 header
            event_type: Value of X-GitHub-Event header (optional)
            
        Returns:
            Parsed webhook payload as dictionary
            
        Raises:
            WebhookSignatureError: If signature verification fails
            WebhookPayloadError: If payload parsing fails
            
        Example:
            ```python
            try:
                payload = client.verify_and_parse(
                    payload_body=request.body,
                    signature_header=request.headers.get("X-Hub-Signature-256"),
                    event_type=request.headers.get("X-GitHub-Event")
                )
                # Process payload
            except WebhookSignatureError:
                # Handle invalid signature
            ```
        """
        # Verify signature
        if not self.verify_signature(payload_body, signature_header):
            raise WebhookSignatureError(
                "Invalid webhook signature. Request may not be from GitHub."
            )
        
        # Parse JSON payload
        try:
            import json
            payload = json.loads(payload_body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            raise WebhookPayloadError(f"Invalid JSON payload: {e}")
        
        if event_type:
            logger.info(f"Received GitHub webhook event: {event_type}")
        
        return payload
    
    @staticmethod
    def extract_event_type(headers: Dict[str, str]) -> Optional[str]:
        """
        Extract GitHub event type from webhook headers.
        
        Args:
            headers: Request headers dictionary
            
        Returns:
            Event type string (e.g., "push", "pull_request", "workflow_run")
            or None if header not found
            
        Example:
            Event types include:
            - push
            - pull_request
            - workflow_run
            - check_run
            - deployment
            - issue_comment
        """
        return headers.get("X-GitHub-Event") or headers.get("x-github-event")
    
    @staticmethod
    def extract_delivery_id(headers: Dict[str, str]) -> Optional[str]:
        """
        Extract unique delivery ID from webhook headers.
        
        Args:
            headers: Request headers dictionary
            
        Returns:
            Unique delivery ID (UUID) or None if not found
        """
        return headers.get("X-GitHub-Delivery") or headers.get("x-github-delivery")
    
    @staticmethod
    def is_workflow_failure(payload: Dict[str, Any]) -> bool:
        """
        Check if webhook payload represents a workflow failure.
        
        Args:
            payload: Parsed webhook payload
            
        Returns:
            True if workflow failed, False otherwise
        """
        if payload.get("action") == "completed":
            workflow_run = payload.get("workflow_run", {})
            conclusion = workflow_run.get("conclusion")
            return conclusion in ["failure", "timed_out", "action_required"]
        
        if payload.get("check_run"):
            check_run = payload.get("check_run", {})
            conclusion = check_run.get("conclusion")
            return conclusion in ["failure", "timed_out", "action_required"]
        
        return False
    
    @staticmethod
    def extract_failure_details(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract failure details from webhook payload.
        
        Args:
            payload: Parsed webhook payload
            
        Returns:
            Dictionary containing failure details
            
        Example return value:
            {
                "workflow_name": "CI",
                "workflow_id": 12345,
                "run_id": 67890,
                "run_number": 42,
                "conclusion": "failure",
                "repository": "owner/repo",
                "branch": "main",
                "commit_sha": "abc123",
                "commit_message": "Fix bug",
                "author": "username",
                "started_at": "2025-11-10T10:00:00Z",
                "completed_at": "2025-11-10T10:05:00Z",
                "html_url": "https://github.com/owner/repo/actions/runs/67890"
            }
        """
        details = {}
        
        if "workflow_run" in payload:
            workflow_run = payload["workflow_run"]
            
            details["workflow_name"] = workflow_run.get("name")
            details["workflow_id"] = workflow_run.get("workflow_id")
            details["run_id"] = workflow_run.get("id")
            details["run_number"] = workflow_run.get("run_number")
            details["conclusion"] = workflow_run.get("conclusion")
            details["status"] = workflow_run.get("status")
            details["started_at"] = workflow_run.get("run_started_at")
            details["completed_at"] = workflow_run.get("updated_at")
            details["html_url"] = workflow_run.get("html_url")
            
            repository = payload.get("repository", {})
            details["repository"] = repository.get("full_name")
            
            details["branch"] = workflow_run.get("head_branch")
            details["commit_sha"] = workflow_run.get("head_sha")
            
            head_commit = workflow_run.get("head_commit", {})
            details["commit_message"] = head_commit.get("message")
            
            author = head_commit.get("author", {})
            details["author"] = author.get("name") or author.get("email")
        
        elif "check_run" in payload:
            check_run = payload["check_run"]
            
            details["check_name"] = check_run.get("name")
            details["check_id"] = check_run.get("id")
            details["conclusion"] = check_run.get("conclusion")
            details["status"] = check_run.get("status")
            details["started_at"] = check_run.get("started_at")
            details["completed_at"] = check_run.get("completed_at")
            details["html_url"] = check_run.get("html_url")
            
            repository = payload.get("repository", {})
            details["repository"] = repository.get("full_name")
            
            head_sha = check_run.get("head_sha")
            details["commit_sha"] = head_sha
        
        return details
    
    @staticmethod
    def get_workflow_logs_url(
        repository: str,
        run_id: int,
        job_id: Optional[int] = None
    ) -> str:
        """
        Generate URL for workflow logs.
        
        Args:
            repository: Repository full name (owner/repo)
            run_id: Workflow run ID
            job_id: Specific job ID (optional)
            
        Returns:
            URL string to access logs
        """
        base_url = f"https://github.com/{repository}/actions/runs/{run_id}"
        
        if job_id:
            return f"{base_url}/jobs/{job_id}"
        
        return base_url
    
    @staticmethod
    def is_retry_eligible(payload: Dict[str, Any]) -> bool:
        """
        Determine if a failed workflow is eligible for automatic retry.
        
        Args:
            payload: Parsed webhook payload
            
        Returns:
            True if workflow can be retried, False otherwise
        """
        if "workflow_run" not in payload:
            return False
        
        workflow_run = payload["workflow_run"]
        conclusion = workflow_run.get("conclusion")
        
        if conclusion not in ["failure", "timed_out"]:
            return False
        
        run_attempt = workflow_run.get("run_attempt", 1)
        if run_attempt >= 3:
            logger.info(f"Workflow run {workflow_run.get('id')} already retried {run_attempt} times")
            return False
        
        return True
    
    def validate_webhook_request(
        self,
        payload_body: bytes,
        headers: Dict[str, str],
    ) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Comprehensive webhook request validation.
        
        Args:
            payload_body: Raw request body as bytes
            headers: Request headers dictionary
            
        Returns:
            Tuple of (is_valid, error_message, parsed_payload)
            - is_valid: True if request is valid
            - error_message: Error description if invalid, None otherwise
            - parsed_payload: Parsed payload if valid, None otherwise
            
        Example:
            ```python
            is_valid, error, payload = client.validate_webhook_request(
                payload_body=request.body,
                headers=dict(request.headers)
            )
            
            if not is_valid:
                return {"error": error}, 401
            
            # Process payload
            ```
        """
        signature = self.extract_signature_header(headers)
        if not signature:
            return False, "Missing X-Hub-Signature-256 header", None
        
        event_type = self.extract_event_type(headers)
        
        try:
            payload = self.verify_and_parse(
                payload_body=payload_body,
                signature_header=signature,
                event_type=event_type,
            )
            return True, None, payload
        
        except WebhookSignatureError as e:
            return False, str(e), None
        
        except WebhookPayloadError as e:
            return False, str(e), None
        
        except Exception as e:
            logger.error(f"Unexpected error validating webhook: {e}")
            return False, f"Internal error: {e}", None
    
    @staticmethod
    def extract_signature_header(headers: Dict[str, str]) -> Optional[str]:
        """
        Extract signature header from request headers.
        
        Args:
            headers: Request headers dictionary
            
        Returns:
            Signature header value or None if not found
        """
        return (
            headers.get("X-Hub-Signature-256") or 
            headers.get("x-hub-signature-256")
        )


def verify_github_webhook(
    payload_body: bytes,
    signature_header: str,
    webhook_secret: Optional[str] = None,
) -> bool:
    """
    Quick webhook signature verification function.
    
    Args:
        payload_body: Raw request body as bytes
        signature_header: Value of X-Hub-Signature-256 header
        webhook_secret: GitHub webhook secret (optional, uses env var by default)
        
    Returns:
        True if signature is valid, False otherwise
        
    Example:
        ```python
        from fastapi import Request, HTTPException
        
        @app.post("/webhooks/github")
        async def github_webhook(request: Request):
            body = await request.body()
            signature = request.headers.get("X-Hub-Signature-256")
            
            if not verify_github_webhook(body, signature):
                raise HTTPException(status_code=401, detail="Invalid signature")
            
            # Process webhook
        ```
    """
    try:
        client = GitHubWebhookClient(webhook_secret)
        return client.verify_signature(payload_body, signature_header)
    except ValueError:
        logger.error("GitHub webhook secret not configured")
        return False
