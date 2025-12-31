# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Base OAuth Provider Class

Provides common OAuth 2.0 functionality for all providers (GitHub, GitLab, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import secrets
import structlog

logger = structlog.get_logger(__name__)


class OAuthProvider(ABC):
    """
    Abstract base class for OAuth providers.

    Implements OAuth 2.0 authorization code flow with PKCE support.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: List[str],
    ):
        """
        Initialize OAuth provider.

        Args:
            client_id: OAuth application client ID
            client_secret: OAuth application client secret
            redirect_uri: Callback URL after authorization
            scopes: List of permission scopes to request
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'github', 'gitlab')"""
        pass

    @property
    @abstractmethod
    def authorize_url(self) -> str:
        """Return the OAuth authorization URL"""
        pass

    @property
    @abstractmethod
    def token_url(self) -> str:
        """Return the OAuth token exchange URL"""
        pass

    @property
    @abstractmethod
    def user_info_url(self) -> str:
        """Return the user info API endpoint"""
        pass

    def generate_state(self) -> str:
        """
        Generate a secure random state for CSRF protection.

        Returns:
            Random state string
        """
        return secrets.token_urlsafe(32)

    def build_authorization_url(self, state: str) -> str:
        """
        Build the authorization URL to redirect user to.

        Args:
            state: CSRF protection state parameter

        Returns:
            Complete authorization URL with all parameters
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "response_type": "code",
        }

        # Add provider-specific parameters
        extra_params = self._get_extra_auth_params()
        params.update(extra_params)

        # Build query string
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.authorize_url}?{query_string}"

    def _get_extra_auth_params(self) -> Dict[str, str]:
        """
        Get provider-specific authorization parameters.

        Override in subclasses to add custom parameters.

        Returns:
            Dictionary of extra parameters
        """
        return {}

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from callback

        Returns:
            Token response containing access_token, refresh_token, etc.
        """
        pass

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token

        Returns:
            New token response
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from the provider.

        Args:
            access_token: Valid access token

        Returns:
            User information dictionary
        """
        pass

    @abstractmethod
    async def revoke_token(self, access_token: str) -> bool:
        """
        Revoke an access token.

        Args:
            access_token: Token to revoke

        Returns:
            True if successful
        """
        pass

    def calculate_token_expiry(self, expires_in: int) -> datetime:
        """
        Calculate token expiration timestamp.

        Args:
            expires_in: Seconds until token expires

        Returns:
            Expiration datetime
        """
        return datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    def is_token_expired(self, expires_at: datetime, buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired or will expire soon.

        Args:
            expires_at: Token expiration timestamp
            buffer_seconds: Refresh buffer time (default 5 minutes)

        Returns:
            True if token is expired or will expire within buffer
        """
        buffer_time = datetime.now(timezone.utc) + timedelta(seconds=buffer_seconds)
        return expires_at <= buffer_time

    def validate_state(self, received_state: str, stored_state: str) -> bool:
        """
        Validate OAuth state parameter for CSRF protection.

        Args:
            received_state: State from callback
            stored_state: State stored in session

        Returns:
            True if states match
        """
        return secrets.compare_digest(received_state, stored_state)
