# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums import IncidentSource

class WebhookPayload(BaseModel):
    """ Generic webhook payload schema. """
    event_type: str = Field(..., description="Type of event")
    data: dict = Field(default_factory=dict, description="Event data")
    timestamp: Optional[datetime] = Field(None, description="Event timestamp")
    source: Optional[str] = Field(None, description="Source system")

class WebhookResponse(BaseModel):
    """ Response from webhook endpoint """
    incident_id: str = Field(..., description="Created incident ID.")
    acknowledged: bool = Field(True, description="Whether webhook was acknowledged")
    queued: bool = Field(False, description="Whether event was queued for processing")
    message: Optional[str] = Field(None, description="Response message")

class GitHubWebhookPayload(BaseModel):
    """ GitHub webhook specific payload """
    action: str = Field(..., description="GitHub actions")
    workflow_run: Optional[dict] = Field(None, description="Workflow run details")
    repository: dict = Field(..., description="Repository information")
    sender: Optional[dict] = Field(None, description="User who triggered the event")

class ArgoCDWebhookPayload(BaseModel):
    """ ArgoCD webhook specific payload """
    application: str = Field(..., description="Application name")
    status: str = Field(..., description="Sync status")
    health: Optional[str] = Field(None, description="Health status")
    message: Optional[str] = Field(None, description="Status message")
    revision: Optional[str] = Field(None, description="Git revision")

class KubernetesWebhookPayload(BaseModel):
    """ Kubernetes event webhook payload """
    type: str = Field(..., description="Event type")
    reason: str = Field(..., description="Event reason")
    message: str = Field(..., description="Event message")
    involved_object: dict = Field(..., description="Involved object")
    metadata: dict = Field(..., description="Event metadata")