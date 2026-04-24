# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

import structlog

logger = structlog.get_logger(__name__)


def generate_webhook_secret() -> str:
    """Generate a cryptographically secure random webhook secret."""
    random_bytes = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(random_bytes).decode("utf-8").rstrip("=")


def verify_github_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature_header or not secret:
        logger.warning(
            "signature_verification_missing_data",
            has_signature=bool(signature_header),
            has_secret=bool(secret),
        )
        return False

    expected_signature = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    received_signature = signature_header[7:] if signature_header.startswith("sha256=") else signature_header
    is_valid = hmac.compare_digest(expected_signature, received_signature)

    logger.debug(
        "signature_verification_result",
        signature_match=is_valid,
        expected_prefix=expected_signature[:16] + "...",
        received_prefix=received_signature[:16] + "...",
    )
    return is_valid


def verify_gitlab_token(token_header: str, expected_token: str) -> bool:
    """Verify GitLab webhook token."""
    if not token_header or not expected_token:
        logger.warning(
            "gitlab_token_verification_missing_data",
            has_token=bool(token_header),
            has_expected=bool(expected_token),
        )
        return False

    is_valid = hmac.compare_digest(token_header, expected_token)
    logger.debug("gitlab_token_verification_result", token_match=is_valid)
    return is_valid
