# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Unit tests for GitHub webhook client."""

import pytest
import hmac
import hashlib
import json
from typing import Dict, Any

from app.adapters.external.github.webhooks import (
    GitHubWebhookClient,
    GitHubWebhookError,
    WebhookSignatureError,
    WebhookPayloadError,
    verify_github_webhook,
)


class TestGitHubWebhookClient:
    """Test suite for GitHubWebhookClient."""
    
    @pytest.fixture
    def webhook_secret(self) -> str:
        """Fixture for webhook secret."""
        return "test_webhook_secret_12345"
    
    @pytest.fixture
    def client(self, webhook_secret: str) -> GitHubWebhookClient:
        """Fixture for GitHubWebhookClient."""
        return GitHubWebhookClient(webhook_secret=webhook_secret)
    
    @pytest.fixture
    def sample_payload(self) -> Dict[str, Any]:
        """Fixture for sample webhook payload."""
        return {
            "action": "completed",
            "workflow_run": {
                "id": 123456789,
                "name": "CI",
                "workflow_id": 12345,
                "run_number": 42,
                "conclusion": "failure",
                "status": "completed",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "run_started_at": "2025-11-10T10:00:00Z",
                "updated_at": "2025-11-10T10:05:00Z",
                "html_url": "https://github.com/owner/repo/actions/runs/123456789",
                "head_commit": {
                    "message": "Fix bug in authentication",
                    "author": {
                        "name": "John Doe",
                        "email": "john@example.com"
                    }
                }
            },
            "repository": {
                "full_name": "owner/repo"
            }
        }
    
    def compute_signature(self, payload: bytes, secret: str) -> str:
        """Helper to compute HMAC-SHA256 signature."""
        return hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
    
    def test_client_initialization_with_secret(self, webhook_secret: str):
        """Test client initialization with explicit secret."""
        client = GitHubWebhookClient(webhook_secret=webhook_secret)
        assert client.webhook_secret == webhook_secret
    
    def test_client_initialization_from_env(self, monkeypatch):
        """Test client initialization from environment variable."""
        test_secret = "env_secret_12345"
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", test_secret)
        
        client = GitHubWebhookClient()
        assert client.webhook_secret == test_secret
    
    def test_client_initialization_without_secret(self, monkeypatch):
        """Test client initialization fails without secret."""
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        
        with pytest.raises(ValueError, match="GitHub webhook secret not provided"):
            GitHubWebhookClient()
    
    def test_verify_signature_valid(self, client: GitHubWebhookClient, webhook_secret: str):
        """Test signature verification with valid signature."""
        payload = b'{"action": "completed"}'
        signature = self.compute_signature(payload, webhook_secret)
        signature_header = f"sha256={signature}"
        
        assert client.verify_signature(payload, signature_header) is True
    
    def test_verify_signature_invalid(self, client: GitHubWebhookClient):
        """Test signature verification with invalid signature."""
        payload = b'{"action": "completed"}'
        invalid_signature = "sha256=invalid_signature_here"
        
        assert client.verify_signature(payload, invalid_signature) is False
    
    def test_verify_signature_missing_header(self, client: GitHubWebhookClient):
        """Test signature verification with missing header."""
        payload = b'{"action": "completed"}'
        
        assert client.verify_signature(payload, None) is False
        assert client.verify_signature(payload, "") is False
    
    def test_verify_signature_wrong_format(self, client: GitHubWebhookClient):
        """Test signature verification with wrong header format."""
        payload = b'{"action": "completed"}'
        wrong_format = "md5=somehash"  # Should be sha256=
        
        assert client.verify_signature(payload, wrong_format) is False
    
    def test_verify_signature_tampered_payload(
        self,
        client: GitHubWebhookClient,
        webhook_secret: str
    ):
        """Test signature verification detects tampered payload."""
        original_payload = b'{"action": "completed"}'
        tampered_payload = b'{"action": "failed"}'
        
        # Signature computed for original
        signature = self.compute_signature(original_payload, webhook_secret)
        signature_header = f"sha256={signature}"
        
        # Verify with tampered payload should fail
        assert client.verify_signature(tampered_payload, signature_header) is False
    
    def test_verify_and_parse_success(
        self,
        client: GitHubWebhookClient,
        sample_payload: Dict[str, Any],
        webhook_secret: str
    ):
        """Test successful verification and parsing."""
        payload_bytes = json.dumps(sample_payload).encode('utf-8')
        signature = self.compute_signature(payload_bytes, webhook_secret)
        signature_header = f"sha256={signature}"
        
        result = client.verify_and_parse(
            payload_body=payload_bytes,
            signature_header=signature_header,
            event_type="workflow_run"
        )
        
        assert result == sample_payload
    
    def test_verify_and_parse_invalid_signature(
        self,
        client: GitHubWebhookClient,
        sample_payload: Dict[str, Any]
    ):
        """Test verify_and_parse raises on invalid signature."""
        payload_bytes = json.dumps(sample_payload).encode('utf-8')
        invalid_signature = "sha256=invalid"
        
        with pytest.raises(WebhookSignatureError, match="Invalid webhook signature"):
            client.verify_and_parse(
                payload_body=payload_bytes,
                signature_header=invalid_signature
            )
    
    def test_verify_and_parse_invalid_json(
        self,
        client: GitHubWebhookClient,
        webhook_secret: str
    ):
        """Test verify_and_parse raises on invalid JSON."""
        invalid_json = b'{"invalid": json}'
        signature = self.compute_signature(invalid_json, webhook_secret)
        signature_header = f"sha256={signature}"
        
        with pytest.raises(WebhookPayloadError, match="Invalid JSON payload"):
            client.verify_and_parse(
                payload_body=invalid_json,
                signature_header=signature_header
            )
    
    def test_is_workflow_failure_completed_failure(self, sample_payload: Dict[str, Any]):
        """Test workflow failure detection for completed failure."""
        assert GitHubWebhookClient.is_workflow_failure(sample_payload) is True
    
    def test_is_workflow_failure_timeout(self, sample_payload: Dict[str, Any]):
        """Test workflow failure detection for timeout."""
        sample_payload["workflow_run"]["conclusion"] = "timed_out"
        assert GitHubWebhookClient.is_workflow_failure(sample_payload) is True
    
    def test_is_workflow_failure_success(self, sample_payload: Dict[str, Any]):
        """Test workflow failure detection for success."""
        sample_payload["workflow_run"]["conclusion"] = "success"
        assert GitHubWebhookClient.is_workflow_failure(sample_payload) is False
    
    def test_is_workflow_failure_check_run(self):
        """Test workflow failure detection for check_run event."""
        payload = {
            "check_run": {
                "conclusion": "failure"
            }
        }
        assert GitHubWebhookClient.is_workflow_failure(payload) is True
    
    def test_extract_failure_details_workflow_run(self, sample_payload: Dict[str, Any]):
        """Test extracting failure details from workflow_run."""
        details = GitHubWebhookClient.extract_failure_details(sample_payload)
        
        assert details["workflow_name"] == "CI"
        assert details["workflow_id"] == 12345
        assert details["run_id"] == 123456789
        assert details["run_number"] == 42
        assert details["conclusion"] == "failure"
        assert details["repository"] == "owner/repo"
        assert details["branch"] == "main"
        assert details["commit_sha"] == "abc123def456"
        assert details["commit_message"] == "Fix bug in authentication"
        assert details["author"] == "John Doe"
        assert details["html_url"] == "https://github.com/owner/repo/actions/runs/123456789"
    
    def test_extract_failure_details_check_run(self):
        """Test extracting failure details from check_run."""
        payload = {
            "check_run": {
                "name": "Test Suite",
                "id": 98765,
                "conclusion": "failure",
                "status": "completed",
                "started_at": "2025-11-10T10:00:00Z",
                "completed_at": "2025-11-10T10:05:00Z",
                "html_url": "https://github.com/owner/repo/runs/98765",
                "head_sha": "def456abc123"
            },
            "repository": {
                "full_name": "owner/repo"
            }
        }
        
        details = GitHubWebhookClient.extract_failure_details(payload)
        
        assert details["check_name"] == "Test Suite"
        assert details["check_id"] == 98765
        assert details["conclusion"] == "failure"
        assert details["repository"] == "owner/repo"
        assert details["commit_sha"] == "def456abc123"
    
    def test_extract_event_type(self):
        """Test extracting event type from headers."""
        headers = {"X-GitHub-Event": "workflow_run"}
        event_type = GitHubWebhookClient.extract_event_type(headers)
        assert event_type == "workflow_run"
        
        # Test lowercase
        headers_lower = {"x-github-event": "push"}
        event_type_lower = GitHubWebhookClient.extract_event_type(headers_lower)
        assert event_type_lower == "push"
    
    def test_extract_delivery_id(self):
        """Test extracting delivery ID from headers."""
        headers = {"X-GitHub-Delivery": "12345-67890-abcdef"}
        delivery_id = GitHubWebhookClient.extract_delivery_id(headers)
        assert delivery_id == "12345-67890-abcdef"
    
    def test_get_workflow_logs_url(self):
        """Test generating workflow logs URL."""
        url = GitHubWebhookClient.get_workflow_logs_url("owner/repo", 12345)
        assert url == "https://github.com/owner/repo/actions/runs/12345"
        
        # With job ID
        url_with_job = GitHubWebhookClient.get_workflow_logs_url("owner/repo", 12345, 67890)
        assert url_with_job == "https://github.com/owner/repo/actions/runs/12345/jobs/67890"
    
    def test_is_retry_eligible_failed_workflow(self, sample_payload: Dict[str, Any]):
        """Test retry eligibility for failed workflow."""
        sample_payload["workflow_run"]["run_attempt"] = 1
        assert GitHubWebhookClient.is_retry_eligible(sample_payload) is True
    
    def test_is_retry_eligible_max_attempts(self, sample_payload: Dict[str, Any]):
        """Test retry not eligible after max attempts."""
        sample_payload["workflow_run"]["run_attempt"] = 3
        assert GitHubWebhookClient.is_retry_eligible(sample_payload) is False
    
    def test_is_retry_eligible_success(self, sample_payload: Dict[str, Any]):
        """Test retry not eligible for successful workflow."""
        sample_payload["workflow_run"]["conclusion"] = "success"
        assert GitHubWebhookClient.is_retry_eligible(sample_payload) is False
    
    def test_validate_webhook_request_valid(
        self,
        client: GitHubWebhookClient,
        sample_payload: Dict[str, Any],
        webhook_secret: str
    ):
        """Test comprehensive webhook validation with valid request."""
        payload_bytes = json.dumps(sample_payload).encode('utf-8')
        signature = self.compute_signature(payload_bytes, webhook_secret)
        
        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "12345"
        }
        
        is_valid, error, payload = client.validate_webhook_request(
            payload_body=payload_bytes,
            headers=headers
        )
        
        assert is_valid is True
        assert error is None
        assert payload == sample_payload
    
    def test_validate_webhook_request_missing_signature(
        self,
        client: GitHubWebhookClient,
        sample_payload: Dict[str, Any]
    ):
        """Test validation fails with missing signature."""
        payload_bytes = json.dumps(sample_payload).encode('utf-8')
        headers = {"X-GitHub-Event": "workflow_run"}
        
        is_valid, error, payload = client.validate_webhook_request(
            payload_body=payload_bytes,
            headers=headers
        )
        
        assert is_valid is False
        assert "Missing X-Hub-Signature-256" in error
        assert payload is None
    
    def test_validate_webhook_request_invalid_signature(
        self,
        client: GitHubWebhookClient,
        sample_payload: Dict[str, Any]
    ):
        """Test validation fails with invalid signature."""
        payload_bytes = json.dumps(sample_payload).encode('utf-8')
        headers = {
            "X-Hub-Signature-256": "sha256=invalid",
            "X-GitHub-Event": "workflow_run"
        }
        
        is_valid, error, payload = client.validate_webhook_request(
            payload_body=payload_bytes,
            headers=headers
        )
        
        assert is_valid is False
        assert "Invalid webhook signature" in error
        assert payload is None
    
    def test_extract_signature_header(self):
        """Test extracting signature header."""
        headers = {"X-Hub-Signature-256": "sha256=abc123"}
        signature = GitHubWebhookClient.extract_signature_header(headers)
        assert signature == "sha256=abc123"
        
        # Test lowercase
        headers_lower = {"x-hub-signature-256": "sha256=def456"}
        signature_lower = GitHubWebhookClient.extract_signature_header(headers_lower)
        assert signature_lower == "sha256=def456"


class TestConvenienceFunction:
    """Test suite for verify_github_webhook convenience function."""
    
    def test_verify_github_webhook_success(self):
        """Test convenience function with valid signature."""
        secret = "test_secret"
        payload = b'{"action": "completed"}'
        
        signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        assert verify_github_webhook(
            payload_body=payload,
            signature_header=f"sha256={signature}",
            webhook_secret=secret
        ) is True
    
    def test_verify_github_webhook_invalid_signature(self):
        """Test convenience function with invalid signature."""
        payload = b'{"action": "completed"}'
        
        assert verify_github_webhook(
            payload_body=payload,
            signature_header="sha256=invalid",
            webhook_secret="test_secret"
        ) is False
    
    def test_verify_github_webhook_no_secret(self, monkeypatch):
        """Test convenience function without secret."""
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        
        payload = b'{"action": "completed"}'
        
        assert verify_github_webhook(
            payload_body=payload,
            signature_header="sha256=anything"
        ) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
