# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
import re


class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, max_length=255, description="Full name")


class UserCreate(UserBase):
    """Schema for creating a new user (registration)."""
    password: str = Field(..., min_length=8, max_length=128, description="Password")
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    full_name: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = Field(None, max_length=500)
    preferences: Optional[dict] = None

    model_config = ConfigDict(extra="forbid")


class UserResponse(UserBase):
    """Schema for user in API responses."""
    user_id: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    is_mfa_enabled: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserDetailResponse(UserResponse):
    """Detailed user response with additional fields."""
    preferences: dict = Field(default_factory=dict)
    allowed_repositories: list = Field(default_factory=list)
    allowed_namespaces: list = Field(default_factory=list)
    allowed_services: list = Field(default_factory=list)
    updated_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of users."""
    users: list[UserResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


# Authentication Schemas

class LoginRequest(BaseModel):
    """Schema for login request."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")
    device_fingerprint: Optional[str] = Field(None, description="Device fingerprint for session tracking")
    mfa_code: Optional[str] = Field(None, min_length=6, max_length=6, description="MFA code if enabled")


class LoginResponse(BaseModel):
    """Schema for successful login response."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Schema for token refresh request."""
    refresh_token: str = Field(..., description="Refresh token")


class RefreshTokenResponse(BaseModel):
    """Schema for token refresh response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutRequest(BaseModel):
    """Schema for logout request."""
    refresh_token: Optional[str] = Field(None, description="Refresh token to revoke")
    all_sessions: bool = Field(False, description="Revoke all sessions")


class LogoutResponse(BaseModel):
    """Schema for logout response."""
    success: bool
    message: str
    sessions_revoked: int = 0


class PasswordChangeRequest(BaseModel):
    """Schema for password change request."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    email: EmailStr = Field(..., description="Email for password reset")


class PasswordResetConfirm(BaseModel):
    """Schema for confirming password reset."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v


class EmailVerificationRequest(BaseModel):
    """Schema for email verification."""
    token: str = Field(..., description="Email verification token")


# MFA Schemas

class MFASetupResponse(BaseModel):
    """Schema for MFA setup response."""
    secret: str = Field(..., description="MFA secret (for QR code)")
    qr_code_uri: str = Field(..., description="OTP Auth URI for QR code")
    backup_codes: list[str] = Field(..., description="Backup codes")


class MFAVerifyRequest(BaseModel):
    """Schema for MFA verification."""
    code: str = Field(..., min_length=6, max_length=6, description="MFA code")


class MFADisableRequest(BaseModel):
    """Schema for disabling MFA."""
    password: str = Field(..., description="Current password for confirmation")
    code: str = Field(..., min_length=6, max_length=6, description="MFA code")


# Session Schemas

class SessionResponse(BaseModel):
    """Schema for session in API responses."""
    session_id: str
    device_fingerprint: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    is_current: bool = False
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """List of active sessions."""
    sessions: list[SessionResponse]
    total: int


class RevokeSessionRequest(BaseModel):
    """Schema for revoking a session."""
    session_id: str = Field(..., description="Session ID to revoke")
    reason: Optional[str] = Field(None, description="Reason for revocation")


# API Key Schemas

class APIKeyCreateResponse(BaseModel):
    """Schema for API key creation response."""
    api_key: str = Field(..., description="Full API key (shown only once)")
    prefix: str = Field(..., description="API key prefix for identification")
    created_at: datetime


class APIKeyResponse(BaseModel):
    """Schema for API key in responses (without full key)."""
    prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


# Token Claims

class TokenClaims(BaseModel):
    """Schema for JWT token claims."""
    sub: str  # user_id
    email: str
    role: str
    token_version: int
    session_id: Optional[str] = None
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    jti: str  # unique token ID
    type: str  # "access" or "refresh"


# Audit Log Schemas

class AuditLogResponse(BaseModel):
    """Schema for audit log in API responses."""
    log_id: str
    user_id: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated list of audit logs."""
    logs: list[AuditLogResponse]
    total: int
    skip: int
    limit: int
    has_more: bool