# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import uuid4
import secrets
import hashlib
import base64

import bcrypt
from jose import jwt, JWTError
import pyotp
import structlog

from app.core.config import settings
from app.adapters.database.postgres.models import UserTable, UserSessionTable, AuditLogTable
from app.adapters.database.postgres.repositories.users import (
    UserRepository,
    SessionRepository,
    AuditLogRepository,
)
from app.core.schemas.users import (
    UserCreate,
    LoginRequest,
    AccessTokenClaims,
    RefreshTokenClaims,
    MFASetupResponse,
)
from app.exceptions import DevFlowFixException

logger = structlog.get_logger()

# JWT settings - use from config
JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days
MAX_FAILED_LOGIN_ATTEMPTS = settings.max_failed_login_attempts
LOCKOUT_DURATION_MINUTES = settings.account_lockout_duration_minutes
MAX_ACTIVE_SESSIONS = settings.max_active_sessions_per_user


class AuthenticationError(DevFlowFixException):
    """Authentication-related errors."""
    def __init__(self, message: str, error_code: str = "authentication_error"):
        super().__init__(message=message, error_code=error_code)


class AuthorizationError(DevFlowFixException):
    """Authorization-related errors."""
    def __init__(self, message: str, error_code: str = "authorization_error"):
        super().__init__(message=message, error_code=error_code)


class AuthService:
    """
    Zero Trust Authentication Service.
    
    Implements:
    - Strong password hashing (bcrypt)
    - JWT with short-lived access tokens
    - Refresh token rotation
    - Session management with device tracking
    - MFA support (TOTP)
    - Brute force protection
    - Audit logging
    """

    def __init__(
        self,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        audit_repo: AuditLogRepository,
    ):
        self.user_repo = user_repo
        self.session_repo = session_repo
        self.audit_repo = audit_repo

    # Password Management

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        # Truncate to 72 bytes (bcrypt limitation)
        password_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            # Truncate to 72 bytes (bcrypt limitation)
            password_bytes = plain_password.encode('utf-8')[:72]
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception:
            return False

    # Token Management

    def create_access_token(
        self,
        user: UserTable,
        session_id: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a short-lived JWT access token."""
        if expires_delta is None:
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        now = datetime.now(timezone.utc)
        expire = now + expires_delta

        claims = {
            "sub": user.user_id,
            "email": user.email,
            "role": user.role,
            "token_version": user.token_version,
            "session_id": session_id,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": str(uuid4()),
            "type": "access",
        }

        return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)

    def create_refresh_token(
        self,
        user: UserTable,
        session_id: str,
        expires_delta: Optional[timedelta] = None,
    ) -> Tuple[str, str]:
        """
        Create a refresh token.
        Returns (token, token_hash) for storage.
        """
        if expires_delta is None:
            expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        now = datetime.now(timezone.utc)
        expire = now + expires_delta

        claims = {
            "sub": user.user_id,
            "token_version": user.token_version,
            "session_id": session_id,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": str(uuid4()),
            "type": "refresh",
        }

        token = jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)
        token_hash = self._hash_token(token)

        return token, token_hash

    def _hash_token(self, token: str) -> str:
        """Hash a token for secure storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    def verify_access_token(self, token: str) -> AccessTokenClaims:
        """Verify and decode an access token."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])

            if payload.get("type") != "access":
                raise AuthenticationError("Invalid token type. Expected access token.", "invalid_token")

            # Validate with AccessTokenClaims (includes email and role)
            try:
                claims = AccessTokenClaims(**payload)
            except ValueError as e:
                logger.warning("access_token_validation_failed", error=str(e))
                raise AuthenticationError("Invalid access token format", "invalid_token")

            # Verify user still exists and is active
            user = self.user_repo.get_by_id(claims.sub)
            if not user:
                raise AuthenticationError("User not found", "user_not_found")

            if not user.is_active:
                raise AuthenticationError("User account is disabled", "account_disabled")

            # Verify token version (for token invalidation)
            if claims.token_version != user.token_version:
                raise AuthenticationError("Token has been revoked", "token_revoked")

            # Verify session is still valid
            session_id = claims.session_id
            if session_id:
                session = self.session_repo.get_active_session(session_id)
                if not session:
                    raise AuthenticationError("Session expired or revoked", "session_invalid")

                # Update session last used time
                self.session_repo.update_last_used(session_id)

            return claims

        except JWTError as e:
            logger.warning("jwt_verification_failed", error=str(e))
            raise AuthenticationError("Invalid or expired token", "invalid_token")

    def verify_refresh_token(self, token: str) -> Tuple[RefreshTokenClaims, UserTable]:
        """Verify a refresh token and return claims with user."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])

            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type. Expected refresh token.", "invalid_token")

            # Validate with RefreshTokenClaims (no email/role required)
            try:
                claims = RefreshTokenClaims(**payload)
            except ValueError as e:
                logger.warning("refresh_token_validation_failed", error=str(e))
                raise AuthenticationError("Invalid refresh token format", "invalid_token")

            user = self.user_repo.get_by_id(claims.sub)
            if not user:
                raise AuthenticationError("User not found", "user_not_found")

            if not user.is_active:
                raise AuthenticationError("User account is disabled", "account_disabled")

            if claims.token_version != user.token_version:
                raise AuthenticationError("Token has been revoked", "token_revoked")

            # Verify session
            session_id = claims.session_id
            if session_id:
                session = self.session_repo.get_active_session(session_id)
                if not session:
                    raise AuthenticationError("Session expired or revoked", "session_invalid")

                # Verify token hash matches
                token_hash = self._hash_token(token)
                if session.refresh_token_hash != token_hash:
                    # Possible token reuse attack - revoke all sessions
                    logger.warning(
                        "refresh_token_reuse_detected",
                        user_id=user.user_id,
                        session_id=session_id,
                    )
                    self.session_repo.revoke_all_user_sessions(
                        user.user_id,
                        reason="Refresh token reuse detected"
                    )
                    self._log_audit(
                        user_id=user.user_id,
                        action="token_reuse_detected",
                        success=False,
                        details={"session_id": session_id},
                    )
                    raise AuthenticationError(
                        "Security violation detected. All sessions revoked.",
                        "token_reuse"
                    )

            return claims, user

        except JWTError as e:
            logger.warning("refresh_token_verification_failed", error=str(e))
            raise AuthenticationError("Invalid or expired refresh token", "invalid_token")

    # User Registration

    def register_user(
        self,
        user_data: UserCreate,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserTable:
        """Register a new user."""
        # Check if email already exists
        existing = self.user_repo.get_by_email(user_data.email)
        if existing:
            self._log_audit(
                action="register",
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"email": user_data.email, "reason": "email_exists"},
            )
            raise AuthenticationError("Email already registered", "email_exists")

        # Create user
        user = UserTable(
            user_id=f"dev_{uuid4().hex[:12]}",
            email=user_data.email.lower(),
            hashed_password=self.hash_password(user_data.password),
            full_name=user_data.full_name,
            role="user",
            is_active=True,
            is_verified=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        user = self.user_repo.create(user)

        self._log_audit(
            user_id=user.user_id,
            action="register",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info("user_registered", user_id=user.user_id, email=user.email)
        return user

    # Authentication

    def authenticate(
        self,
        login_data: LoginRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[UserTable, str, str, str]:
        """
        Authenticate user and create session.
        
        Returns:
            Tuple of (user, access_token, refresh_token, session_id)
        """
        # Check for IP-based brute force
        self._check_ip_lockout(ip_address)

        # Get user
        user = self.user_repo.get_active_by_email(login_data.email)

        if not user:
            self._log_audit(
                action="login",
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"email": login_data.email, "reason": "user_not_found"},
            )
            raise AuthenticationError("Invalid email or password", "invalid_credentials")

        # Check account lockout
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            remaining = (user.locked_until - datetime.now(timezone.utc)).seconds // 60
            self._log_audit(
                user_id=user.user_id,
                action="login",
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "account_locked", "remaining_minutes": remaining},
            )
            raise AuthenticationError(
                f"Account locked. Try again in {remaining} minutes.",
                "account_locked"
            )

        # Verify password
        if not self.verify_password(login_data.password, user.hashed_password):
            failed_attempts = self.user_repo.increment_failed_login(user.user_id)

            if failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
                lockout_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                self.user_repo.lock_user(user.user_id, lockout_until)
                logger.warning("account_locked", user_id=user.user_id)

            self._log_audit(
                user_id=user.user_id,
                action="login",
                success=False,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_password", "failed_attempts": failed_attempts},
            )
            raise AuthenticationError("Invalid email or password", "invalid_credentials")

        # Check MFA if enabled
        if user.is_mfa_enabled:
            if not login_data.mfa_code:
                raise AuthenticationError("MFA code required", "mfa_required")

            if not self._verify_mfa(user, login_data.mfa_code):
                self._log_audit(
                    user_id=user.user_id,
                    action="login",
                    success=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "invalid_mfa_code"},
                )
                raise AuthenticationError("Invalid MFA code", "invalid_mfa_code")

        # Check session limit
        active_sessions = self.session_repo.count_active_sessions(user.user_id)
        if active_sessions >= MAX_ACTIVE_SESSIONS:
            # Revoke oldest session
            sessions = self.session_repo.get_user_sessions(user.user_id)
            if sessions:
                oldest = sessions[-1]
                self.session_repo.revoke_session(oldest.session_id, "Session limit reached")

        # Create session
        session = self._create_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=login_data.device_fingerprint,
        )

        # Create tokens
        access_token = self.create_access_token(user, session.session_id)
        refresh_token, refresh_hash = self.create_refresh_token(user, session.session_id)

        # Update session with refresh token hash
        session.refresh_token_hash = refresh_hash
        self.session_repo.db.commit()

        # Update last login
        self.user_repo.update_last_login(user.user_id, ip_address, user_agent)

        self._log_audit(
            user_id=user.user_id,
            session_id=session.session_id,
            action="login",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info("user_logged_in", user_id=user.user_id, session_id=session.session_id)
        return user, access_token, refresh_token, session.session_id

    def _create_session(
        self,
        user: UserTable,
        ip_address: Optional[str],
        user_agent: Optional[str],
        device_fingerprint: Optional[str],
    ) -> UserSessionTable:
        """Create a new session."""
        session = UserSessionTable(
            session_id=f"ses_{uuid4().hex[:12]}",
            user_id=user.user_id,
            refresh_token_hash="",  # Will be set after token creation
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True,
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

        return self.session_repo.create(session)

    def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Refresh access and refresh tokens (token rotation).
        
        Returns:
            Tuple of (new_access_token, new_refresh_token)
        """
        claims, user = self.verify_refresh_token(refresh_token)
        session_id = claims.session_id

        # Create new tokens
        new_access_token = self.create_access_token(user, session_id)
        new_refresh_token, new_refresh_hash = self.create_refresh_token(user, session_id)

        # Update session with new refresh token hash and extend expiration
        session = self.session_repo.get_by_id(session_id)
        if session:
            session.refresh_token_hash = new_refresh_hash
            session.last_used_at = datetime.now(timezone.utc)
            # Extend session expiration when tokens are refreshed
            session.expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
            self.session_repo.db.commit()

        self._log_audit(
            user_id=user.user_id,
            session_id=session_id,
            action="token_refresh",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return new_access_token, new_refresh_token

    def logout(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        all_sessions: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> int:
        """
        Logout user (revoke session(s)).
        
        Returns:
            Number of sessions revoked
        """
        if all_sessions:
            count = self.session_repo.revoke_all_user_sessions(user_id, "User logout")
            # Also increment token version to invalidate all tokens
            self.user_repo.update_token_version(user_id)
        elif session_id:
            self.session_repo.revoke_session(session_id, "User logout")
            count = 1
        else:
            count = 0

        self._log_audit(
            user_id=user_id,
            session_id=session_id,
            action="logout",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"all_sessions": all_sessions, "sessions_revoked": count},
        )

        return count

    # MFA

    def setup_mfa(self, user_id: str) -> MFASetupResponse:
        """Setup MFA for a user."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found", "user_not_found")

        # Generate secret
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]

        # Store secret (not enabled yet)
        user.mfa_secret = secret
        self.user_repo.update(user)

        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="DevFlowFix"
        )

        return MFASetupResponse(
            secret=secret,
            qr_code_uri=provisioning_uri,
            backup_codes=backup_codes,
        )

    def enable_mfa(self, user_id: str, code: str) -> bool:
        """Enable MFA after verifying setup code."""
        user = self.user_repo.get_by_id(user_id)
        if not user or not user.mfa_secret:
            raise AuthenticationError("MFA not setup", "mfa_not_setup")

        if not self._verify_mfa(user, code):
            raise AuthenticationError("Invalid MFA code", "invalid_mfa_code")

        self.user_repo.enable_mfa(user_id, user.mfa_secret)

        self._log_audit(
            user_id=user_id,
            action="mfa_enabled",
            success=True,
        )

        return True

    def disable_mfa(self, user_id: str, password: str, code: str) -> bool:
        """Disable MFA for a user."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found", "user_not_found")

        if not self.verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid password", "invalid_password")

        if not self._verify_mfa(user, code):
            raise AuthenticationError("Invalid MFA code", "invalid_mfa_code")

        self.user_repo.disable_mfa(user_id)

        self._log_audit(
            user_id=user_id,
            action="mfa_disabled",
            success=True,
        )

        return True

    def _verify_mfa(self, user: UserTable, code: str) -> bool:
        """Verify MFA code."""
        if not user.mfa_secret:
            return False

        totp = pyotp.TOTP(user.mfa_secret)
        return totp.verify(code, valid_window=1)

    # API Keys

    def create_api_key(self, user_id: str) -> Tuple[str, str]:
        """
        Create an API key for service authentication.
        
        Returns:
            Tuple of (full_api_key, prefix)
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found", "user_not_found")

        # Generate API key
        key = f"dff_{secrets.token_urlsafe(32)}"
        prefix = key[:10]
        key_hash = self._hash_token(key)

        self.user_repo.set_api_key(user_id, key_hash, prefix)

        self._log_audit(
            user_id=user_id,
            action="api_key_created",
            success=True,
        )

        return key, prefix

    def verify_api_key(self, api_key: str) -> UserTable:
        """Verify an API key and return the user."""
        key_hash = self._hash_token(api_key)
        prefix = api_key[:10]

        # Find user with matching prefix (for efficiency)
        users = self.user_repo.db.query(UserTable).filter(
            UserTable.api_key_prefix == prefix
        ).all()

        for user in users:
            if user.api_key_hash == key_hash:
                if not user.is_active:
                    raise AuthenticationError("User account is disabled", "account_disabled")
                return user

        raise AuthenticationError("Invalid API key", "invalid_api_key")

    def revoke_api_key(self, user_id: str) -> bool:
        """Revoke a user's API key."""
        self.user_repo.set_api_key(user_id, None, None)

        self._log_audit(
            user_id=user_id,
            action="api_key_revoked",
            success=True,
        )

        return True

    # Security Helpers

    def _check_ip_lockout(self, ip_address: Optional[str]) -> None:
        """Check if IP is temporarily blocked due to brute force."""
        if not ip_address:
            return

        since = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        failed_count = self.audit_repo.count_failed_logins(ip_address, since)

        if failed_count >= MAX_FAILED_LOGIN_ATTEMPTS * 3:  # 3x user limit
            raise AuthenticationError(
                "Too many failed login attempts. Try again later.",
                "ip_blocked"
            )

    def _log_audit(
        self,
        action: str,
        success: bool = True,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Create an audit log entry."""
        try:
            log = AuditLogTable(
                log_id=f"log_{uuid4().hex[:12]}",
                user_id=user_id,
                session_id=session_id,
                action=action,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                error_message=error_message,
                details=details or {},
                created_at=datetime.now(timezone.utc),
            )
            self.audit_repo.create(log)
        except Exception as e:
            logger.error("audit_log_failed", error=str(e))

    # Password Reset

    def create_password_reset_token(self, email: str) -> Optional[str]:
        """Create a password reset token."""
        user = self.user_repo.get_active_by_email(email)
        if not user:
            # Don't reveal if user exists
            return None

        # Create token (valid for 1 hour)
        claims = {
            "sub": user.user_id,
            "email": user.email,
            "type": "password_reset",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "jti": str(uuid4()),
        }

        token = jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)

        self._log_audit(
            user_id=user.user_id,
            action="password_reset_requested",
            success=True,
        )

        return token

    def reset_password(self, token: str, new_password: str) -> bool:
        """Reset password using reset token."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])

            if payload.get("type") != "password_reset":
                raise AuthenticationError("Invalid token type", "invalid_token")

            user = self.user_repo.get_by_id(payload["sub"])
            if not user:
                raise AuthenticationError("User not found", "user_not_found")

            # Update password
            user.hashed_password = self.hash_password(new_password)
            user.token_version += 1  # Invalidate all existing tokens
            self.user_repo.update(user)

            # Revoke all sessions
            self.session_repo.revoke_all_user_sessions(
                user.user_id,
                reason="Password reset"
            )

            self._log_audit(
                user_id=user.user_id,
                action="password_reset",
                success=True,
            )

            return True

        except JWTError:
            raise AuthenticationError("Invalid or expired token", "invalid_token")

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change password for authenticated user."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found", "user_not_found")

        if not self.verify_password(current_password, user.hashed_password):
            self._log_audit(
                user_id=user_id,
                action="password_change",
                success=False,
                details={"reason": "invalid_current_password"},
            )
            raise AuthenticationError("Current password is incorrect", "invalid_password")

        user.hashed_password = self.hash_password(new_password)
        user.token_version += 1
        self.user_repo.update(user)

        # Revoke all other sessions
        self.session_repo.revoke_all_user_sessions(
            user_id,
            reason="Password changed"
        )

        self._log_audit(
            user_id=user_id,
            action="password_change",
            success=True,
        )

        return True
