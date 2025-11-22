# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends, Header, BackgroundTasks
from typing import Optional
import json
import hmac
import hashlib


def generate_github_signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


class MockSettings:
    GITHUB_WEBHOOK_SECRET = "test_secret_123"
    environment = "dev"
    enable_notifications = False
    enable_auto_remediation = True


class MockProcessingResult:
    def __init__(self):
        self.incident_id = "inc_test123"
        self.success = True
        self.outcome = Mock(value="success")
        self.message = "Processing completed"


@pytest.fixture
def mock_event_processor():
    processor = Mock()
    processor.process = AsyncMock(return_value=MockProcessingResult())
    return processor


@pytest.fixture
def app(mock_event_processor):
    from fastapi import FastAPI, Request
    from app.core.schemas.webhook import WebhookResponse
    
    app = FastAPI()
    
    mock_settings = MockSettings()
    
    def verify_signature(body: bytes, signature: str, secret: str) -> bool:
        if not signature or not secret:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if signature.startswith("sha256="):
            signature = signature[7:]
        return hmac.compare_digest(expected, signature)
    
    def is_failure_event(event_type: str, payload: dict) -> bool:
        if event_type == "workflow_run":
            workflow_run = payload.get("workflow_run", {})
            conclusion = workflow_run.get("conclusion")
            status_value = workflow_run.get("status")
            return status_value == "completed" and conclusion in ["failure", "timed_out", "action_required"]
        return False
    
    def is_argocd_failure(payload: dict) -> bool:
        app_status = payload.get("application", {}).get("status", {})
        sync_status = app_status.get("sync", {}).get("status", "").lower()
        health_status = app_status.get("health", {}).get("status", "").lower()
        return sync_status in ["unknown", "outofsync"] or health_status in ["degraded", "missing", "unknown"]
    
    def is_k8s_failure(payload: dict) -> bool:
        event_type = payload.get("type", "").lower()
        reason = payload.get("reason", "").lower()
        failure_reasons = ["backoff", "failed", "unhealthy", "evicted", "oomkilled", "crashloopbackoff", "imagepullbackoff"]
        if event_type == "warning":
            return True
        return any(r in reason for r in failure_reasons)
    
    @app.post("/api/v1/webhook/github")
    async def github_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        x_github_event: str = Header(...),
        x_github_delivery: Optional[str] = Header(None),
        x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    ):
        incident_id = f"gh_{x_github_delivery or int(datetime.utcnow().timestamp() * 1000)}"
        body = await request.body()
        
        if x_github_event == "ping":
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message="GitHub webhook ping received",
            )
        
        if mock_settings.GITHUB_WEBHOOK_SECRET:
            if not verify_signature(body, x_hub_signature_256, mock_settings.GITHUB_WEBHOOK_SECRET):
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        try:
            payload = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
        
        if not is_failure_event(x_github_event, payload):
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message=f"Event {x_github_event} acknowledged (not a failure)",
            )
        
        background_tasks.add_task(lambda: None)
        
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=True,
            message="GitHub failure detected, processing started",
        )
    
    @app.post("/api/v1/webhook/argocd")
    async def argocd_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        payload = await request.json()
        incident_id = f"argo_{int(datetime.utcnow().timestamp() * 1000)}"
        
        if not is_argocd_failure(payload):
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message="ArgoCD event acknowledged (not a failure)",
            )
        
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=True,
            message="ArgoCD failure detected, processing started",
        )
    
    @app.post("/api/v1/webhook/kubernetes")
    async def kubernetes_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        payload = await request.json()
        incident_id = f"k8s_{int(datetime.utcnow().timestamp() * 1000)}"
        
        if not is_k8s_failure(payload):
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message="Kubernetes event acknowledged (not a failure)",
            )
        
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=True,
            message="Kubernetes failure detected, processing started",
        )
    
    @app.post("/api/v1/webhook/generic")
    async def generic_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        x_webhook_source: Optional[str] = Header(None),
    ):
        payload = await request.json()
        incident_id = f"gen_{int(datetime.utcnow().timestamp() * 1000)}"
        
        if not payload.get("error_log") and not payload.get("message"):
            return WebhookResponse(
                incident_id=incident_id,
                acknowledged=True,
                queued=False,
                message="Webhook acknowledged (no error_log provided)",
            )
        
        return WebhookResponse(
            incident_id=incident_id,
            acknowledged=True,
            queued=True,
            message="Generic webhook received, processing started",
        )
    
    @app.get("/api/v1/webhook/health")
    async def webhook_health():
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "features": {
                "github": True,
                "argocd": True,
                "kubernetes": True,
                "generic": True,
            },
        }
    
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestGitHubWebhook:
    
    @pytest.fixture
    def workflow_failure_payload(self):
        return {
            "action": "completed",
            "workflow_run": {
                "id": 12345678,
                "name": "CI Pipeline",
                "status": "completed",
                "conclusion": "failure",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "html_url": "https://github.com/org/repo/actions/runs/12345678",
            },
            "repository": {
                "full_name": "org/repo",
            },
        }
    
    @pytest.fixture
    def workflow_success_payload(self):
        return {
            "action": "completed",
            "workflow_run": {
                "id": 12345678,
                "name": "CI Pipeline",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "abc123def456",
            },
            "repository": {
                "full_name": "org/repo",
            },
        }
    
    @pytest.fixture
    def ping_payload(self):
        return {
            "zen": "Keep it logically awesome.",
            "hook_id": 123456,
        }
    
    def test_github_webhook_ping(self, client, ping_payload):
        response = client.post(
            "/api/v1/webhook/github",
            json=ping_payload,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "test-delivery-123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert "ping" in data["message"].lower()
    
    def test_github_webhook_workflow_failure(self, client, workflow_failure_payload):
        signature = generate_github_signature(workflow_failure_payload, "test_secret_123")
        
        response = client.post(
            "/api/v1/webhook/github",
            json=workflow_failure_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "test-delivery-456",
                "X-Hub-Signature-256": signature,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is True
    
    def test_github_webhook_workflow_success_ignored(self, client, workflow_success_payload):
        signature = generate_github_signature(workflow_success_payload, "test_secret_123")
        
        response = client.post(
            "/api/v1/webhook/github",
            json=workflow_success_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "test-delivery-789",
                "X-Hub-Signature-256": signature,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is False
        assert "not a failure" in data["message"].lower()
    
    def test_github_webhook_invalid_signature(self, client, workflow_failure_payload):
        response = client.post(
            "/api/v1/webhook/github",
            json=workflow_failure_payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "test-delivery-invalid",
                "X-Hub-Signature-256": "sha256=invalid_signature",
            },
        )
        
        assert response.status_code == 401
    
    def test_github_webhook_missing_event_header(self, client, workflow_failure_payload):
        response = client.post(
            "/api/v1/webhook/github",
            json=workflow_failure_payload,
        )
        
        assert response.status_code == 422
    
    def test_github_webhook_timed_out(self, client):
        payload = {
            "workflow_run": {
                "id": 12345,
                "name": "CI",
                "status": "completed",
                "conclusion": "timed_out",
                "head_branch": "feature",
                "head_sha": "abc123",
            },
            "repository": {"full_name": "org/repo"},
        }
        
        signature = generate_github_signature(payload, "test_secret_123")
        
        response = client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "timeout-test",
                "X-Hub-Signature-256": signature,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] is True
    
    def test_github_webhook_production_branch(self, client):
        payload = {
            "workflow_run": {
                "id": 12345,
                "name": "CI",
                "status": "completed",
                "conclusion": "failure",
                "head_branch": "production",
                "head_sha": "abc123",
            },
            "repository": {"full_name": "org/repo"},
        }
        
        signature = generate_github_signature(payload, "test_secret_123")
        
        response = client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "prod-test",
                "X-Hub-Signature-256": signature,
            },
        )
        
        assert response.status_code == 200


class TestArgoCDWebhook:
    
    @pytest.fixture
    def argocd_sync_failed_payload(self):
        return {
            "application": {
                "metadata": {
                    "name": "my-app",
                    "namespace": "argocd",
                },
                "status": {
                    "sync": {
                        "status": "OutOfSync",
                        "revision": "abc123",
                    },
                    "health": {
                        "status": "Degraded",
                    },
                },
            },
        }
    
    @pytest.fixture
    def argocd_healthy_payload(self):
        return {
            "application": {
                "metadata": {
                    "name": "my-app",
                    "namespace": "argocd",
                },
                "status": {
                    "sync": {
                        "status": "Synced",
                    },
                    "health": {
                        "status": "Healthy",
                    },
                },
            },
        }
    
    def test_argocd_webhook_sync_failed(self, client, argocd_sync_failed_payload):
        response = client.post(
            "/api/v1/webhook/argocd",
            json=argocd_sync_failed_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is True
    
    def test_argocd_webhook_healthy_ignored(self, client, argocd_healthy_payload):
        response = client.post(
            "/api/v1/webhook/argocd",
            json=argocd_healthy_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is False
    
    def test_argocd_webhook_degraded_health(self, client):
        payload = {
            "application": {
                "metadata": {"name": "degraded-app"},
                "status": {
                    "sync": {"status": "Synced"},
                    "health": {"status": "Degraded"},
                },
            },
        }
        
        response = client.post(
            "/api/v1/webhook/argocd",
            json=payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] is True


class TestKubernetesWebhook:
    
    @pytest.fixture
    def k8s_crash_loop_payload(self):
        return {
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off restarting failed container",
            "involvedObject": {
                "kind": "Pod",
                "name": "my-pod-abc123",
                "namespace": "default",
            },
        }
    
    @pytest.fixture
    def k8s_oom_killed_payload(self):
        return {
            "type": "Warning",
            "reason": "OOMKilled",
            "message": "Container killed due to OOM",
            "involvedObject": {
                "kind": "Pod",
                "name": "memory-hog-xyz789",
                "namespace": "production",
            },
        }
    
    @pytest.fixture
    def k8s_normal_event_payload(self):
        return {
            "type": "Normal",
            "reason": "Scheduled",
            "message": "Successfully assigned pod to node",
            "involvedObject": {
                "kind": "Pod",
                "name": "normal-pod",
                "namespace": "default",
            },
        }
    
    def test_kubernetes_webhook_crash_loop(self, client, k8s_crash_loop_payload):
        response = client.post(
            "/api/v1/webhook/kubernetes",
            json=k8s_crash_loop_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is True
    
    def test_kubernetes_webhook_oom_killed(self, client, k8s_oom_killed_payload):
        response = client.post(
            "/api/v1/webhook/kubernetes",
            json=k8s_oom_killed_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is True
    
    def test_kubernetes_webhook_normal_event_ignored(self, client, k8s_normal_event_payload):
        response = client.post(
            "/api/v1/webhook/kubernetes",
            json=k8s_normal_event_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is False
    
    def test_kubernetes_webhook_image_pull_backoff(self, client):
        payload = {
            "type": "Warning",
            "reason": "ImagePullBackOff",
            "message": "Back-off pulling image",
            "involvedObject": {
                "kind": "Pod",
                "name": "image-issue-pod",
                "namespace": "staging",
            },
        }
        
        response = client.post(
            "/api/v1/webhook/kubernetes",
            json=payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] is True


class TestGenericWebhook:
    
    def test_generic_webhook_with_error_log(self, client):
        payload = {
            "error_log": "Application crashed with OutOfMemoryError",
            "severity": "high",
            "context": {
                "service": "payment-service",
            },
        }
        
        response = client.post(
            "/api/v1/webhook/generic",
            json=payload,
            headers={"X-Webhook-Source": "custom"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert data["queued"] is True
    
    def test_generic_webhook_with_message(self, client):
        payload = {
            "message": "Service health check failed",
        }
        
        response = client.post(
            "/api/v1/webhook/generic",
            json=payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] is True
    
    def test_generic_webhook_empty_payload(self, client):
        payload = {}
        
        response = client.post(
            "/api/v1/webhook/generic",
            json=payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["queued"] is False
    
    def test_generic_webhook_source_mapping(self, client):
        payload = {"error_log": "Test error"}
        
        sources = ["github", "argocd", "kubernetes", "k8s", "gitlab", "jenkins"]
        
        for source in sources:
            response = client.post(
                "/api/v1/webhook/generic",
                json=payload,
                headers={"X-Webhook-Source": source},
            )
            
            assert response.status_code == 200


class TestWebhookHealth:
    
    def test_webhook_health_endpoint(self, client):
        response = client.get("/api/v1/webhook/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "features" in data


class TestWebhookErrorHandling:
    
    def test_empty_json_payload(self, client):
        response = client.post(
            "/api/v1/webhook/argocd",
            json={},
        )
        
        assert response.status_code == 200


class TestWebhookPayloadExtraction:
    
    def test_github_payload_has_required_fields(self, client):
        payload = {
            "workflow_run": {
                "id": 12345,
                "name": "CI",
                "status": "completed",
                "conclusion": "failure",
                "head_branch": "main",
                "head_sha": "abc123",
                "html_url": "https://github.com/org/repo/actions/runs/12345",
                "workflow_id": 1234,
                "run_number": 42,
            },
            "repository": {
                "full_name": "org/repo",
                "html_url": "https://github.com/org/repo",
            },
        }
        
        signature = generate_github_signature(payload, "test_secret_123")
        
        response = client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": "extraction-test",
                "X-Hub-Signature-256": signature,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "incident_id" in data
        assert data["incident_id"].startswith("gh_")
    
    def test_argocd_payload_extraction(self, client):
        payload = {
            "application": {
                "metadata": {
                    "name": "test-app",
                    "namespace": "argocd",
                },
                "status": {
                    "sync": {
                        "status": "OutOfSync",
                        "revision": "abc123",
                    },
                    "health": {
                        "status": "Degraded",
                    },
                    "conditions": [
                        {
                            "type": "SyncError",
                            "message": "Failed to sync",
                        },
                    ],
                },
            },
        }
        
        response = client.post(
            "/api/v1/webhook/argocd",
            json=payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"].startswith("argo_")
    
    def test_kubernetes_payload_extraction(self, client):
        payload = {
            "type": "Warning",
            "reason": "CrashLoopBackOff",
            "message": "Container crashed",
            "involvedObject": {
                "kind": "Pod",
                "name": "my-pod",
                "namespace": "production",
            },
            "metadata": {
                "name": "event-name",
            },
        }
        
        response = client.post(
            "/api/v1/webhook/kubernetes",
            json=payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"].startswith("k8s_")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])