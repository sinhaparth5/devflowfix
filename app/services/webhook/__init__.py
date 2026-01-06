# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Webhook Services

Handles webhook management and processing for GitHub/GitLab repositories.
"""

from .webhook_manager import WebhookManager

__all__ = ["WebhookManager"]
