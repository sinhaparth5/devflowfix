# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Email Service - Integration with the .NET Email Microservice.

This module provides functions to send various email notifications through
the DevFlowFix email microservice (Azure-hosted .NET service).
"""

from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass
import hmac
import hashlib
import time
import json
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()


@dataclass
class EmailResponse:
    """Response from the email service."""
    success: bool
    message_id: Optional[str] = None
    error_message: Optional[str] = None


class EmailServiceError(Exception):
    """Exception raised when email service call fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class EmailService:
    """
    Service for sending emails via the .NET email microservice.

    Base URL: https://devflowfix-mail-service.azurewebsites.net
    Authentication: HMAC-SHA256
    """

    def __init__(self):
        self.base_url = settings.email_service_url
        self.timeout = settings.email_service_timeout
        self.frontend_url = settings.frontend_url
        self.api_key = settings.email_service_api_key
        self.secret = settings.email_service_secret

    def _generate_signature(self, timestamp: int, method: str, path: str, body: str) -> str:
        """
        Generate HMAC-SHA256 signature for request authentication.

        Signature is computed as: HMAC-SHA256("{timestamp}:{method}:{path}:{body}", secret)
        """
        message = f"{timestamp}:{method}:{path}:{body}"
        signature = hmac.new(
            self.secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_auth_headers(self, path: str, body: str) -> dict:
        """Generate authentication headers for email service request."""
        timestamp = int(time.time())
        signature = self._generate_signature(timestamp, "POST", path, body)
        return {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
            "X-Timestamp": str(timestamp),
            "X-Signature": signature
        }

    async def _send_request(self, endpoint: str, payload: dict) -> EmailResponse:
        """
        Send an authenticated request to the email service.

        Args:
            endpoint: API endpoint path (e.g., "/api/email/welcome")
            payload: Request body as dictionary

        Returns:
            EmailResponse with success status and message ID or error
        """
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{self.base_url}{path}"

        # Serialize body with consistent formatting for signature
        body = json.dumps(payload, separators=(",", ":"))
        headers = self._get_auth_headers(path, body)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    content=body,
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    return EmailResponse(
                        success=data.get("success", True),
                        message_id=data.get("messageId"),
                        error_message=data.get("errorMessage")
                    )
                else:
                    logger.error(
                        "email_service_error",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        response_text=response.text
                    )
                    return EmailResponse(
                        success=False,
                        error_message=f"Email service returned status {response.status_code}"
                    )

        except httpx.TimeoutException:
            logger.error("email_service_timeout", endpoint=endpoint)
            return EmailResponse(
                success=False,
                error_message="Email service request timed out"
            )
        except httpx.RequestError as e:
            logger.error(
                "email_service_request_error",
                endpoint=endpoint,
                error=str(e)
            )
            return EmailResponse(
                success=False,
                error_message=f"Email service request failed: {str(e)}"
            )

    async def send_welcome_email(
        self,
        email: str,
        full_name: str,
        username: str,
        login_url: Optional[str] = None
    ) -> EmailResponse:
        """
        Send a welcome email to a newly registered user.

        Args:
            email: User's email address
            full_name: User's full name
            username: User's username
            login_url: Login URL (defaults to frontend_url/login)

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "username": username,
            "createdAt": datetime.now(timezone.utc).isoformat() + "Z",
            "loginUrl": login_url or f"{self.frontend_url}/login"
        }

        result = await self._send_request("/api/email/welcome", payload)

        logger.info(
            "welcome_email_sent" if result.success else "welcome_email_failed",
            email=email,
            success=result.success,
            message_id=result.message_id
        )

        return result

    async def send_verification_email(
        self,
        email: str,
        full_name: str,
        verification_token: str,
        expires_in_hours: int = 24
    ) -> EmailResponse:
        """
        Send an email verification link.

        Args:
            email: User's email address
            full_name: User's full name
            verification_token: JWT verification token
            expires_in_hours: Token expiration in hours

        Returns:
            EmailResponse with result
        """
        verification_url = f"{self.frontend_url}/verify-email?token={verification_token}"

        payload = {
            "email": email,
            "fullName": full_name,
            "verificationToken": verification_token,
            "verificationUrl": verification_url,
            "expiresInHours": expires_in_hours
        }

        result = await self._send_request("/api/email/verification", payload)

        logger.info(
            "verification_email_sent" if result.success else "verification_email_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_password_reset_link(
        self,
        email: str,
        full_name: str,
        reset_token: str,
        request_ip: str,
        expires_in_minutes: int = 60
    ) -> EmailResponse:
        """
        Send a password reset link email.

        Args:
            email: User's email address
            full_name: User's full name
            reset_token: JWT reset token
            request_ip: IP address that requested the reset
            expires_in_minutes: Token expiration in minutes

        Returns:
            EmailResponse with result
        """
        reset_url = f"{self.frontend_url}/reset-password?token={reset_token}"

        payload = {
            "email": email,
            "fullName": full_name,
            "resetToken": reset_token,
            "resetUrl": reset_url,
            "expiresInMinutes": expires_in_minutes,
            "requestIp": request_ip,
            "requestTimestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }

        result = await self._send_request("/api/email/password-reset-link", payload)

        logger.info(
            "password_reset_link_sent" if result.success else "password_reset_link_failed",
            email=email,
            success=result.success,
            request_ip=request_ip
        )

        return result

    async def send_password_reset_confirmation(
        self,
        email: str,
        full_name: str,
        reset_ip: str
    ) -> EmailResponse:
        """
        Send a confirmation that password was reset.

        Args:
            email: User's email address
            full_name: User's full name
            reset_ip: IP address where reset was completed

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "resetTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "resetIp": reset_ip,
            "loginUrl": f"{self.frontend_url}/login"
        }

        result = await self._send_request("/api/email/password-reset-confirmation", payload)

        logger.info(
            "password_reset_confirmation_sent" if result.success else "password_reset_confirmation_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_password_change_confirmation(
        self,
        email: str,
        full_name: str,
        change_ip: str,
        user_agent: str,
        sessions_revoked: bool = True
    ) -> EmailResponse:
        """
        Send a confirmation that password was changed.

        Args:
            email: User's email address
            full_name: User's full name
            change_ip: IP address where change was made
            user_agent: Browser/client user agent
            sessions_revoked: Whether other sessions were logged out

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "changeTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "changeIp": change_ip,
            "userAgent": user_agent,
            "sessionsRevoked": sessions_revoked
        }

        result = await self._send_request("/api/email/password-change-confirmation", payload)

        logger.info(
            "password_change_confirmation_sent" if result.success else "password_change_confirmation_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_mfa_setup_email(
        self,
        email: str,
        full_name: str,
        secret_key: str,
        backup_codes: List[str]
    ) -> EmailResponse:
        """
        Send MFA setup instructions with secret and backup codes.

        Args:
            email: User's email address
            full_name: User's full name
            secret_key: TOTP secret key
            backup_codes: List of backup recovery codes

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "secretKey": secret_key,
            "backupCodes": backup_codes,
            "setupTimestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }

        result = await self._send_request("/api/email/mfa-setup", payload)

        logger.info(
            "mfa_setup_email_sent" if result.success else "mfa_setup_email_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_mfa_enabled_notification(
        self,
        email: str,
        full_name: str,
        enabled_ip: str
    ) -> EmailResponse:
        """
        Send notification that MFA has been enabled.

        Args:
            email: User's email address
            full_name: User's full name
            enabled_ip: IP address where MFA was enabled

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "enabledTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "enabledIp": enabled_ip
        }

        result = await self._send_request("/api/email/mfa-enabled", payload)

        logger.info(
            "mfa_enabled_email_sent" if result.success else "mfa_enabled_email_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_mfa_disabled_warning(
        self,
        email: str,
        full_name: str,
        disabled_ip: str,
        user_agent: str
    ) -> EmailResponse:
        """
        Send warning that MFA has been disabled.

        Args:
            email: User's email address
            full_name: User's full name
            disabled_ip: IP address where MFA was disabled
            user_agent: Browser/client user agent

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "disabledTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "disabledIp": disabled_ip,
            "userAgent": user_agent
        }

        result = await self._send_request("/api/email/mfa-disabled", payload)

        logger.info(
            "mfa_disabled_email_sent" if result.success else "mfa_disabled_email_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_new_login_alert(
        self,
        email: str,
        full_name: str,
        login_ip: str,
        user_agent: str,
        device_fingerprint: Optional[str] = None,
        approximate_location: Optional[str] = None,
        is_new_device: bool = False
    ) -> EmailResponse:
        """
        Send alert about a new login to the account.

        Args:
            email: User's email address
            full_name: User's full name
            login_ip: IP address of the login
            user_agent: Browser/client user agent
            device_fingerprint: Device fingerprint if available
            approximate_location: Approximate location (e.g., "New York, US")
            is_new_device: Whether this is a new/unrecognized device

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "loginTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "loginIp": login_ip,
            "userAgent": user_agent,
            "deviceFingerprint": device_fingerprint or "",
            "approximateLocation": approximate_location or "Unknown",
            "isNewDevice": is_new_device
        }

        result = await self._send_request("/api/email/new-login-alert", payload)

        logger.info(
            "new_login_alert_sent" if result.success else "new_login_alert_failed",
            email=email,
            success=result.success,
            is_new_device=is_new_device
        )

        return result

    async def send_account_locked_warning(
        self,
        email: str,
        full_name: str,
        failed_attempts: int,
        lockout_duration_minutes: int,
        last_attempt_ip: str
    ) -> EmailResponse:
        """
        Send warning that account has been locked due to failed login attempts.

        Args:
            email: User's email address
            full_name: User's full name
            failed_attempts: Number of failed login attempts
            lockout_duration_minutes: How long the account is locked
            last_attempt_ip: IP of the last failed attempt

        Returns:
            EmailResponse with result
        """
        locked_timestamp = datetime.now(timezone.utc)
        unlock_timestamp = locked_timestamp.replace(
            minute=locked_timestamp.minute + lockout_duration_minutes
        )

        payload = {
            "email": email,
            "fullName": full_name,
            "failedAttempts": failed_attempts,
            "lockedTimestamp": locked_timestamp.isoformat() + "Z",
            "lockoutDurationMinutes": lockout_duration_minutes,
            "unlockTimestamp": unlock_timestamp.isoformat() + "Z",
            "lastAttemptIp": last_attempt_ip
        }

        result = await self._send_request("/api/email/account-locked", payload)

        logger.info(
            "account_locked_email_sent" if result.success else "account_locked_email_failed",
            email=email,
            success=result.success,
            failed_attempts=failed_attempts
        )

        return result

    async def send_session_revoked_notification(
        self,
        email: str,
        full_name: str,
        revoked_session_id: str,
        revoked_device_info: str,
        revoked_ip: str,
        revoked_by_ip: str
    ) -> EmailResponse:
        """
        Send notification that a session has been revoked.

        Args:
            email: User's email address
            full_name: User's full name
            revoked_session_id: ID of the revoked session
            revoked_device_info: Device info of revoked session
            revoked_ip: IP of the revoked session
            revoked_by_ip: IP that initiated the revocation

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "revokedSessionId": revoked_session_id,
            "revokedDeviceInfo": revoked_device_info,
            "revokedIp": revoked_ip,
            "revocationTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "revokedByIp": revoked_by_ip
        }

        result = await self._send_request("/api/email/session-revoked", payload)

        logger.info(
            "session_revoked_email_sent" if result.success else "session_revoked_email_failed",
            email=email,
            success=result.success
        )

        return result

    async def send_oauth_account_created(
        self,
        email: str,
        full_name: str,
        oauth_provider: str,
        oauth_email: str
    ) -> EmailResponse:
        """
        Send welcome email for account created via OAuth.

        Args:
            email: User's email address
            full_name: User's full name
            oauth_provider: OAuth provider name (google, github, etc.)
            oauth_email: Email from the OAuth provider

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "oAuthProvider": oauth_provider,
            "oAuthEmail": oauth_email,
            "createdTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "loginUrl": f"{self.frontend_url}/login"
        }

        result = await self._send_request("/api/email/oauth-account-created", payload)

        logger.info(
            "oauth_account_email_sent" if result.success else "oauth_account_email_failed",
            email=email,
            success=result.success,
            provider=oauth_provider
        )

        return result

    async def send_api_key_created_notification(
        self,
        email: str,
        full_name: str,
        key_prefix: str,
        key_name: str,
        created_ip: str
    ) -> EmailResponse:
        """
        Send notification that an API key was created.

        Args:
            email: User's email address
            full_name: User's full name
            key_prefix: Prefix of the API key (e.g., "dff_abc")
            key_name: Name/description of the API key
            created_ip: IP address where key was created

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "keyPrefix": key_prefix,
            "keyName": key_name,
            "createdTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "createdIp": created_ip
        }

        result = await self._send_request("/api/email/api-key-created", payload)

        logger.info(
            "api_key_created_email_sent" if result.success else "api_key_created_email_failed",
            email=email,
            success=result.success,
            key_prefix=key_prefix
        )

        return result

    async def send_api_key_revoked_notification(
        self,
        email: str,
        full_name: str,
        key_prefix: str,
        key_name: str,
        revoked_ip: str
    ) -> EmailResponse:
        """
        Send notification that an API key was revoked.

        Args:
            email: User's email address
            full_name: User's full name
            key_prefix: Prefix of the revoked API key
            key_name: Name/description of the API key
            revoked_ip: IP address where key was revoked

        Returns:
            EmailResponse with result
        """
        payload = {
            "email": email,
            "fullName": full_name,
            "keyPrefix": key_prefix,
            "keyName": key_name,
            "revokedTimestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "revokedIp": revoked_ip
        }

        result = await self._send_request("/api/email/api-key-revoked", payload)

        logger.info(
            "api_key_revoked_email_sent" if result.success else "api_key_revoked_email_failed",
            email=email,
            success=result.success,
            key_prefix=key_prefix
        )

        return result


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """
    Get the email service singleton instance.

    Returns:
        EmailService instance
    """
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
