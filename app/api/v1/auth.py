# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import structlog

from app.dependencies import get_db
from app.adapters.database.postgres.repositories.users import (
    UserRepository,
    SessionRepository,
    AuditLogRepository,
)
from app.services.auth import AuthService, AuthenticationError
from app.core.config import settings
from app.core.schemas.users import (
    UserCreate,
    UserResponse,
    UserDetailResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    LogoutRequest,
    LogoutResponse,
    PasswordChangeRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    MFASetupResponse,
    MFAVerifyRequest,
    MFADisableRequest,
    SessionResponse,
    SessionListResponse,
    RevokeSessionRequest,
    APIKeyCreateResponse,
    AccessTokenClaims,
)
from app.core.schemas.common import SuccessResponse, ErrorResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Security
security = HTTPBearer(auto_error=False)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Get authentication service with repositories."""
    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)
    audit_repo = AuditLogRepository(db)
    return AuthService(user_repo, session_repo, audit_repo)


def get_client_info(request: Request) -> dict:
    """Extract client information from request."""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent"),
    }


async def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """
    Dependency to get current authenticated user.
    
    Returns dict with user info and claims.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Verify this is an access token (not refresh token)
        claims = auth_service.verify_access_token(credentials.credentials)
        
        # Get user from database
        user = auth_service.user_repo.get_by_id(claims.sub)
        
        if not user:
            logger.warning(
                "user_not_found_for_valid_token",
                user_id=claims.sub,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return {
            "user": user,
            "claims": claims,
            "session_id": claims.session_id,
        }
    except AuthenticationError as e:
        logger.info(
            "authentication_failed",
            error=e.message,
            error_code=e.error_code,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError as e:
        # Handle Pydantic validation errors
        logger.warning(
            "token_validation_failed",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed token. Please use an access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(
            "unexpected_auth_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dependency to get current active user."""
    if not current_user["user"].is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_active_user),
) -> dict:
    """Dependency to require admin role."""
    if current_user["user"].role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# Registration

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={
        400: {"model": ErrorResponse, "description": "Email already exists"},
    },
)
async def register(
    user_data: UserCreate,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Register a new user account.
    
    Password requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    client_info = get_client_info(request)
    
    try:
        user = auth_service.register_user(
            user_data,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
        )
        
        logger.info(
            "user_registered",
            user_id=user.user_id,
            email=user.email,
        )
        
        return UserResponse.model_validate(user)
    except AuthenticationError as e:
        logger.info(
            "registration_failed",
            email=user_data.email,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


# Login/Logout

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login with email and password",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        423: {"model": ErrorResponse, "description": "Account locked"},
    },
)
async def login(
    login_data: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user and receive tokens.
    
    Returns:
    - access_token: Short-lived JWT (15 minutes)
    - refresh_token: Long-lived JWT for token refresh (7 days)
    
    If MFA is enabled, provide the mfa_code field.
    """
    client_info = get_client_info(request)
    
    try:
        user, access_token, refresh_token, session_id = auth_service.authenticate(
            login_data,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
        )
        
        logger.info(
            "user_login_success",
            user_id=user.user_id,
            session_id=session_id,
        )
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        )
    except AuthenticationError as e:
        logger.info(
            "login_failed",
            email=login_data.email,
            error=e.message,
            error_code=e.error_code,
        )
        if e.error_code == "account_locked":
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=e.message,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid refresh token"},
    },
)
async def refresh_token(
    token_data: RefreshTokenRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Refresh access token using refresh token.
    
    Implements token rotation - returns new access AND refresh tokens.
    The old refresh token is invalidated.
    """
    client_info = get_client_info(request)
    
    try:
        new_access, new_refresh = auth_service.refresh_tokens(
            token_data.refresh_token,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
        )
        
        logger.info(
            "tokens_refreshed",
            ip_address=client_info["ip_address"],
        )
        
        return RefreshTokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )
    except AuthenticationError as e:
        logger.info(
            "token_refresh_failed",
            error=e.message,
            error_code=e.error_code,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )
    except ValueError as e:
        logger.warning(
            "invalid_refresh_token_format",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token format",
        )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Logout user",
)
async def logout(
    logout_data: LogoutRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Logout user and revoke session(s).
    
    - Set all_sessions=true to logout from all devices
    - Provide refresh_token to revoke specific session
    """
    client_info = get_client_info(request)
    
    sessions_revoked = auth_service.logout(
        user_id=current_user["user"].user_id,
        session_id=current_user["session_id"],
        all_sessions=logout_data.all_sessions,
        ip_address=client_info["ip_address"],
        user_agent=client_info["user_agent"],
    )
    
    logger.info(
        "user_logout",
        user_id=current_user["user"].user_id,
        sessions_revoked=sessions_revoked,
        all_sessions=logout_data.all_sessions,
    )
    
    return LogoutResponse(
        success=True,
        message="Logged out successfully",
        sessions_revoked=sessions_revoked,
    )


# User Profile

@router.get(
    "/me",
    response_model=UserDetailResponse,
    summary="Get current user profile",
)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_active_user),
):
    """Get the current authenticated user's profile."""
    return UserDetailResponse.model_validate(current_user["user"])


# Password Management

@router.post(
    "/password/change",
    response_model=SuccessResponse,
    summary="Change password",
)
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Change password for current user.
    
    All sessions will be revoked after password change.
    """
    try:
        auth_service.change_password(
            user_id=current_user["user"].user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
        )
        
        logger.info(
            "password_changed",
            user_id=current_user["user"].user_id,
        )
        
        return SuccessResponse(
            success=True,
            message="Password changed successfully. Please login again.",
        )
    except AuthenticationError as e:
        logger.info(
            "password_change_failed",
            user_id=current_user["user"].user_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.post(
    "/password/reset/request",
    response_model=SuccessResponse,
    summary="Request password reset",
)
async def request_password_reset(
    reset_data: PasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Request a password reset email.
    
    Note: For security, always returns success even if email doesn't exist.
    """
    token = auth_service.create_password_reset_token(reset_data.email)
    
    if token:
        # TODO: Send email with reset link containing token
        logger.info("password_reset_token_created", email=reset_data.email)
    
    return SuccessResponse(
        success=True,
        message="If the email exists, a password reset link has been sent.",
    )


@router.post(
    "/password/reset/confirm",
    response_model=SuccessResponse,
    summary="Confirm password reset",
)
async def confirm_password_reset(
    reset_data: PasswordResetConfirm,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Reset password using the reset token."""
    try:
        auth_service.reset_password(reset_data.token, reset_data.new_password)
        
        logger.info("password_reset_completed")
        
        return SuccessResponse(
            success=True,
            message="Password reset successfully. Please login with your new password.",
        )
    except AuthenticationError as e:
        logger.info(
            "password_reset_failed",
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


# MFA

@router.post(
    "/mfa/setup",
    response_model=MFASetupResponse,
    summary="Setup MFA",
)
async def setup_mfa(
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Setup MFA for current user.
    
    Returns:
    - secret: For manual entry in authenticator app
    - qr_code_uri: For QR code generation
    - backup_codes: Save these securely!
    
    After setup, call /mfa/enable with a code to enable MFA.
    """
    if current_user["user"].is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled",
        )
    
    logger.info(
        "mfa_setup_initiated",
        user_id=current_user["user"].user_id,
    )
    
    return auth_service.setup_mfa(current_user["user"].user_id)


@router.post(
    "/mfa/enable",
    response_model=SuccessResponse,
    summary="Enable MFA",
)
async def enable_mfa(
    mfa_data: MFAVerifyRequest,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Enable MFA by verifying the setup code.
    
    Provide a code from your authenticator app to confirm setup.
    """
    try:
        auth_service.enable_mfa(current_user["user"].user_id, mfa_data.code)
        
        logger.info(
            "mfa_enabled",
            user_id=current_user["user"].user_id,
        )
        
        return SuccessResponse(
            success=True,
            message="MFA enabled successfully",
        )
    except AuthenticationError as e:
        logger.info(
            "mfa_enable_failed",
            user_id=current_user["user"].user_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.post(
    "/mfa/disable",
    response_model=SuccessResponse,
    summary="Disable MFA",
)
async def disable_mfa(
    mfa_data: MFADisableRequest,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Disable MFA for current user.
    
    Requires current password and MFA code for verification.
    """
    if not current_user["user"].is_mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )
    
    try:
        auth_service.disable_mfa(
            current_user["user"].user_id,
            mfa_data.password,
            mfa_data.code,
        )
        
        logger.info(
            "mfa_disabled",
            user_id=current_user["user"].user_id,
        )
        
        return SuccessResponse(
            success=True,
            message="MFA disabled successfully",
        )
    except AuthenticationError as e:
        logger.info(
            "mfa_disable_failed",
            user_id=current_user["user"].user_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


# Sessions

@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List active sessions",
)
async def list_sessions(
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """List all active sessions for current user."""
    sessions = auth_service.session_repo.get_user_sessions(
        current_user["user"].user_id,
        active_only=True,
    )
    
    session_responses = []
    for session in sessions:
        response = SessionResponse.model_validate(session)
        response.is_current = (session.session_id == current_user["session_id"])
        session_responses.append(response)
    
    return SessionListResponse(
        sessions=session_responses,
        total=len(session_responses),
    )


@router.post(
    "/sessions/revoke",
    response_model=SuccessResponse,
    summary="Revoke a session",
)
async def revoke_session(
    revoke_data: RevokeSessionRequest,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Revoke a specific session."""
    # Verify session belongs to user
    session = auth_service.session_repo.get_by_id(revoke_data.session_id)
    if not session or session.user_id != current_user["user"].user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    if revoke_data.session_id == current_user["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke current session. Use logout instead.",
        )
    
    auth_service.session_repo.revoke_session(
        revoke_data.session_id,
        reason=revoke_data.reason or "User revoked",
    )
    
    logger.info(
        "session_revoked",
        user_id=current_user["user"].user_id,
        session_id=revoke_data.session_id,
    )
    
    return SuccessResponse(
        success=True,
        message="Session revoked successfully",
    )


# API Keys

@router.post(
    "/api-key",
    response_model=APIKeyCreateResponse,
    summary="Create API key",
)
async def create_api_key(
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Create an API key for service authentication.
    
    WARNING: The full API key is shown only once. Save it securely!
    """
    api_key, prefix = auth_service.create_api_key(current_user["user"].user_id)
    
    logger.info(
        "api_key_created",
        user_id=current_user["user"].user_id,
        prefix=prefix,
    )
    
    return APIKeyCreateResponse(
        api_key=api_key,
        prefix=prefix,
        created_at=datetime.now(timezone.utc),
    )


@router.delete(
    "/api-key",
    response_model=SuccessResponse,
    summary="Revoke API key",
)
async def revoke_api_key(
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Revoke the current API key."""
    auth_service.revoke_api_key(current_user["user"].user_id)
    
    logger.info(
        "api_key_revoked",
        user_id=current_user["user"].user_id,
    )
    
    return SuccessResponse(
        success=True,
        message="API key revoked successfully",
    )
