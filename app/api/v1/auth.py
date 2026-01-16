# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from typing import Optional, Annotated, AsyncIterator
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, File, UploadFile, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import structlog
import base64
import httpx
import asyncio
import json

from app.dependencies import get_db
from app.adapters.database.postgres.repositories.users import (
    UserRepository,
    SessionRepository,
    AuditLogRepository,
)
from app.services.auth import AuthService, AuthenticationError
from app.services.storage import get_storage_service
from app.services.email import get_email_service
from app.core.config import settings
from app.core.schemas.users import (
    UserCreate,
    UserUpdate,
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
    OAuthLoginRequest,
    OAuthCallbackRequest,
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

    Avatar upload:
    - Provide avatar_data as base64 encoded image data
    - Supported formats: PNG, JPEG, GIF, WebP
    - Image will be uploaded to Backblaze B2 bucket
    """
    client_info = get_client_info(request)

    try:
        # First create the user
        user = auth_service.register_user(
            user_data,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
        )

        # Handle avatar upload if provided
        if user_data.avatar_data:
            try:
                # Decode base64 avatar data
                avatar_bytes = base64.b64decode(user_data.avatar_data)

                # Upload to Backblaze
                storage_service = get_storage_service()
                avatar_url = storage_service.upload_avatar(
                    file_content=avatar_bytes,
                    user_id=user.user_id,
                    content_type=user_data.avatar_content_type or "image/png"
                )

                # Update user with avatar URL
                user.avatar_url = avatar_url
                auth_service.user_repo.db.commit()
                auth_service.user_repo.db.refresh(user)

                logger.info(
                    "user_avatar_uploaded",
                    user_id=user.user_id,
                    avatar_url=avatar_url,
                )
            except Exception as avatar_error:
                # Log the error but don't fail registration
                logger.warning(
                    "avatar_upload_failed_during_registration",
                    user_id=user.user_id,
                    error=str(avatar_error),
                )

        logger.info(
            "user_registered",
            user_id=user.user_id,
            email=user.email,
        )

        # Send welcome email
        email_service = get_email_service()
        await email_service.send_welcome_email(
            email=user.email,
            full_name=user.full_name or user.email.split("@")[0],
            username=user.email.split("@")[0],
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


@router.post(
    "/register/with-avatar",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user with avatar file upload",
    responses={
        400: {"model": ErrorResponse, "description": "Email already exists or validation error"},
    },
)
async def register_with_avatar_file(
    email: str = Form(..., description="User email address"),
    password: str = Form(..., description="User password"),
    full_name: Optional[str] = Form(None, description="Full name"),
    avatar_file: Optional[UploadFile] = File(None, description="Avatar image file"),
    request: Request = None,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Register a new user account with direct avatar file upload.

    Password requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Avatar upload:
    - Upload an image file directly (optional)
    - Supported formats: PNG, JPEG, GIF, WebP
    - Max file size: 5MB
    - Image will be uploaded to Backblaze B2 bucket
    """
    client_info = get_client_info(request)

    try:
        # Create UserCreate object for validation
        user_data = UserCreate(
            email=email,
            password=password,
            full_name=full_name
        )

        # First create the user
        user = auth_service.register_user(
            user_data,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
        )

        # Handle avatar upload if provided
        if avatar_file:
            try:
                # Validate content type
                allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
                if avatar_file.content_type not in allowed_types:
                    logger.warning(
                        "invalid_avatar_content_type",
                        user_id=user.user_id,
                        content_type=avatar_file.content_type,
                    )
                    raise ValueError(f"Invalid file type. Allowed: {', '.join(allowed_types)}")

                # Read file content
                avatar_bytes = await avatar_file.read()

                # Validate file size (5MB max)
                max_size = 5 * 1024 * 1024  # 5MB
                if len(avatar_bytes) > max_size:
                    logger.warning(
                        "avatar_file_too_large",
                        user_id=user.user_id,
                        size=len(avatar_bytes),
                    )
                    raise ValueError(f"File too large. Maximum size: {max_size / 1024 / 1024}MB")

                # Upload to Backblaze
                storage_service = get_storage_service()
                avatar_url = storage_service.upload_avatar(
                    file_content=avatar_bytes,
                    user_id=user.user_id,
                    content_type=avatar_file.content_type
                )

                # Update user with avatar URL
                user.avatar_url = avatar_url
                auth_service.user_repo.db.commit()
                auth_service.user_repo.db.refresh(user)

                logger.info(
                    "user_avatar_uploaded",
                    user_id=user.user_id,
                    avatar_url=avatar_url,
                    file_size=len(avatar_bytes),
                )
            except Exception as avatar_error:
                # Log the error but don't fail registration
                logger.warning(
                    "avatar_upload_failed_during_registration",
                    user_id=user.user_id,
                    error=str(avatar_error),
                )

        logger.info(
            "user_registered",
            user_id=user.user_id,
            email=user.email,
        )

        # Send welcome email
        email_service = get_email_service()
        await email_service.send_welcome_email(
            email=user.email,
            full_name=user.full_name or user.email.split("@")[0],
            username=user.email.split("@")[0],
        )

        return UserResponse.model_validate(user)
    except AuthenticationError as e:
        logger.info(
            "registration_failed",
            email=email,
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
    - access_token: Short-lived JWT (1 hour)
    - refresh_token: Long-lived JWT for token refresh (30 days)

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

        # Send new login alert email
        email_service = get_email_service()
        await email_service.send_new_login_alert(
            email=user.email,
            full_name=user.full_name or user.email.split("@")[0],
            login_ip=client_info["ip_address"] or "Unknown",
            user_agent=client_info["user_agent"] or "Unknown",
            device_fingerprint=login_data.device_fingerprint if hasattr(login_data, 'device_fingerprint') else None,
            is_new_device=True,  # Could be enhanced with device tracking
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
            # Send account locked warning email
            email_service = get_email_service()
            # Get user to send email
            user = auth_service.user_repo.get_by_email(login_data.email)
            if user:
                await email_service.send_account_locked_warning(
                    email=user.email,
                    full_name=user.full_name or user.email.split("@")[0],
                    failed_attempts=settings.max_failed_login_attempts,
                    lockout_duration_minutes=settings.account_lockout_duration_minutes,
                    last_attempt_ip=client_info["ip_address"] or "Unknown",
                )
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


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_current_user_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Update the current authenticated user's profile.

    Only fields provided in the request will be updated.
    Fields that are not provided or are null will keep their existing values.

    Updatable fields:
    - full_name: User's full name
    - avatar_data: Base64 encoded avatar image (optional)
    - avatar_content_type: MIME type for avatar (default: image/png)
    - github_username: GitHub username
    - organization_id: Organization ID
    - team_id: Team ID
    - preferences: User preferences as a JSON object
    """
    try:
        user = current_user["user"]
        update_dict = update_data.model_dump(exclude_unset=True, exclude_none=True)

        # Handle avatar upload if provided
        if "avatar_data" in update_dict:
            try:
                # Decode base64 avatar data
                avatar_bytes = base64.b64decode(update_dict["avatar_data"])

                # Delete old avatar if exists
                if user.avatar_url:
                    try:
                        storage_service = get_storage_service()
                        storage_service.delete_avatar(user.avatar_url)
                    except Exception as delete_error:
                        logger.warning(
                            "old_avatar_delete_failed",
                            user_id=user.user_id,
                            error=str(delete_error),
                        )

                # Upload new avatar to Backblaze
                storage_service = get_storage_service()
                avatar_url = storage_service.upload_avatar(
                    file_content=avatar_bytes,
                    user_id=user.user_id,
                    content_type=update_dict.get("avatar_content_type", "image/png")
                )

                user.avatar_url = avatar_url

                logger.info(
                    "user_avatar_updated_via_profile",
                    user_id=user.user_id,
                    avatar_url=avatar_url,
                )
            except Exception as avatar_error:
                logger.error(
                    "avatar_upload_failed_in_profile_update",
                    user_id=user.user_id,
                    error=str(avatar_error),
                    error_type=type(avatar_error).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to upload avatar: {str(avatar_error)}",
                )

            # Remove avatar_data and avatar_content_type from update_dict
            # as they're not direct model fields
            update_dict.pop("avatar_data", None)
            update_dict.pop("avatar_content_type", None)

        # Update user fields that were provided
        for field, value in update_dict.items():
            if hasattr(user, field):
                setattr(user, field, value)

        # Update timestamp
        user.updated_at = datetime.now(timezone.utc)

        # Save to database
        auth_service.user_repo.db.commit()
        auth_service.user_repo.db.refresh(user)

        logger.info(
            "user_profile_updated",
            user_id=user.user_id,
            updated_fields=list(update_dict.keys()),
        )

        return UserResponse.model_validate(user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "profile_update_failed",
            user_id=current_user["user"].user_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile",
        )


@router.post(
    "/me/avatar",
    response_model=UserResponse,
    summary="Update user avatar (file upload)",
)
async def update_user_avatar_file(
    avatar_file: UploadFile = File(..., description="Avatar image file"),
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Update the current user's avatar using direct file upload.

    Upload an image file directly.
    Supported formats: PNG, JPEG, GIF, WebP.
    Max file size: 5MB (recommended).
    The image will be uploaded to Backblaze B2 bucket.
    """
    try:
        # Validate content type
        allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
        if avatar_file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type: {avatar_file.content_type}. Allowed: {', '.join(allowed_types)}",
            )

        # Read file content
        avatar_bytes = await avatar_file.read()

        # Validate file size (5MB max)
        max_size = 5 * 1024 * 1024  # 5MB
        if len(avatar_bytes) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size: {max_size / 1024 / 1024}MB",
            )

        # Delete old avatar if exists
        user = current_user["user"]
        if user.avatar_url:
            try:
                storage_service = get_storage_service()
                storage_service.delete_avatar(user.avatar_url)
            except Exception as delete_error:
                # Log but don't fail the update
                logger.warning(
                    "old_avatar_delete_failed",
                    user_id=user.user_id,
                    error=str(delete_error),
                )

        # Upload new avatar to Backblaze
        storage_service = get_storage_service()
        avatar_url = storage_service.upload_avatar(
            file_content=avatar_bytes,
            user_id=user.user_id,
            content_type=avatar_file.content_type
        )

        # Update user with new avatar URL
        user.avatar_url = avatar_url
        user.updated_at = datetime.now(timezone.utc)
        auth_service.user_repo.db.commit()
        auth_service.user_repo.db.refresh(user)

        logger.info(
            "user_avatar_updated",
            user_id=user.user_id,
            avatar_url=avatar_url,
            file_size=len(avatar_bytes),
        )

        return UserResponse.model_validate(user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "avatar_update_failed",
            user_id=current_user["user"].user_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update avatar",
        )


# Password Management

@router.post(
    "/password/change",
    response_model=SuccessResponse,
    summary="Change password",
)
async def change_password(
    password_data: PasswordChangeRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Change password for current user.

    All sessions will be revoked after password change.
    """
    client_info = get_client_info(request)

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

        # Send password change confirmation email
        user = current_user["user"]
        email_service = get_email_service()
        await email_service.send_password_change_confirmation(
            email=user.email,
            full_name=user.full_name or user.email.split("@")[0],
            change_ip=client_info["ip_address"] or "Unknown",
            user_agent=client_info["user_agent"] or "Unknown",
            sessions_revoked=True,
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
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Request a password reset email.

    Note: For security, always returns success even if email doesn't exist.
    """
    client_info = get_client_info(request)
    token = auth_service.create_password_reset_token(reset_data.email)

    if token:
        # Get user to get full name for email
        user = auth_service.user_repo.get_by_email(reset_data.email)
        if user:
            # Send password reset link email
            email_service = get_email_service()
            await email_service.send_password_reset_link(
                email=user.email,
                full_name=user.full_name or user.email.split("@")[0],
                reset_token=token,
                request_ip=client_info["ip_address"] or "Unknown",
                expires_in_minutes=60,
            )
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
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Reset password using the reset token."""
    client_info = get_client_info(request)

    try:
        # Get user info from token before reset (for email notification)
        user_email = auth_service.get_email_from_reset_token(reset_data.token)
        user = auth_service.user_repo.get_by_email(user_email) if user_email else None

        auth_service.reset_password(reset_data.token, reset_data.new_password)

        logger.info("password_reset_completed")

        # Send password reset confirmation email
        if user:
            email_service = get_email_service()
            await email_service.send_password_reset_confirmation(
                email=user.email,
                full_name=user.full_name or user.email.split("@")[0],
                reset_ip=client_info["ip_address"] or "Unknown",
            )

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

    mfa_response = auth_service.setup_mfa(current_user["user"].user_id)

    # Send MFA setup email with secret and backup codes
    user = current_user["user"]
    email_service = get_email_service()
    await email_service.send_mfa_setup_email(
        email=user.email,
        full_name=user.full_name or user.email.split("@")[0],
        secret_key=mfa_response.secret,
        backup_codes=mfa_response.backup_codes,
    )

    return mfa_response


@router.post(
    "/mfa/enable",
    response_model=SuccessResponse,
    summary="Enable MFA",
)
async def enable_mfa(
    mfa_data: MFAVerifyRequest,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Enable MFA by verifying the setup code.

    Provide a code from your authenticator app to confirm setup.
    """
    client_info = get_client_info(request)

    try:
        auth_service.enable_mfa(current_user["user"].user_id, mfa_data.code)

        logger.info(
            "mfa_enabled",
            user_id=current_user["user"].user_id,
        )

        # Send MFA enabled notification email
        user = current_user["user"]
        email_service = get_email_service()
        await email_service.send_mfa_enabled_notification(
            email=user.email,
            full_name=user.full_name or user.email.split("@")[0],
            enabled_ip=client_info["ip_address"] or "Unknown",
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
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Disable MFA for current user.

    Requires current password and MFA code for verification.
    """
    client_info = get_client_info(request)

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

        # Send MFA disabled warning email
        user = current_user["user"]
        email_service = get_email_service()
        await email_service.send_mfa_disabled_warning(
            email=user.email,
            full_name=user.full_name or user.email.split("@")[0],
            disabled_ip=client_info["ip_address"] or "Unknown",
            user_agent=client_info["user_agent"] or "Unknown",
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
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Revoke a specific session."""
    client_info = get_client_info(request)

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

    # Capture session info before revoking for email notification
    revoked_device_info = session.user_agent or "Unknown device"
    revoked_ip = session.ip_address or "Unknown"

    auth_service.session_repo.revoke_session(
        revoke_data.session_id,
        reason=revoke_data.reason or "User revoked",
    )

    logger.info(
        "session_revoked",
        user_id=current_user["user"].user_id,
        session_id=revoke_data.session_id,
    )

    # Send session revoked notification email
    user = current_user["user"]
    email_service = get_email_service()
    await email_service.send_session_revoked_notification(
        email=user.email,
        full_name=user.full_name or user.email.split("@")[0],
        revoked_session_id=revoke_data.session_id,
        revoked_device_info=revoked_device_info,
        revoked_ip=revoked_ip,
        revoked_by_ip=client_info["ip_address"] or "Unknown",
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
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Create an API key for service authentication.

    WARNING: The full API key is shown only once. Save it securely!
    """
    client_info = get_client_info(request)
    api_key, prefix = auth_service.create_api_key(current_user["user"].user_id)

    logger.info(
        "api_key_created",
        user_id=current_user["user"].user_id,
        prefix=prefix,
    )

    # Send API key created notification email
    user = current_user["user"]
    email_service = get_email_service()
    await email_service.send_api_key_created_notification(
        email=user.email,
        full_name=user.full_name or user.email.split("@")[0],
        key_prefix=prefix,
        key_name="API Key",  # Could be enhanced to accept a name parameter
        created_ip=client_info["ip_address"] or "Unknown",
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
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Revoke the current API key."""
    client_info = get_client_info(request)

    # Get API key prefix before revoking for email notification
    user = current_user["user"]
    api_key_prefix = user.api_key_prefix if hasattr(user, 'api_key_prefix') else "dff_***"

    auth_service.revoke_api_key(current_user["user"].user_id)

    logger.info(
        "api_key_revoked",
        user_id=current_user["user"].user_id,
    )

    # Send API key revoked notification email
    email_service = get_email_service()
    await email_service.send_api_key_revoked_notification(
        email=user.email,
        full_name=user.full_name or user.email.split("@")[0],
        key_prefix=api_key_prefix,
        key_name="API Key",
        revoked_ip=client_info["ip_address"] or "Unknown",
    )

    return SuccessResponse(
        success=True,
        message="API key revoked successfully",
    )


# OAuth Authentication

@router.post(
    "/oauth/google",
    response_model=LoginResponse,
    summary="Login with Google OAuth",
    responses={
        401: {"model": ErrorResponse, "description": "OAuth authentication failed"},
    },
)
async def oauth_google_login(
    oauth_data: OAuthLoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user with Google OAuth.

    Flow:
    1. Frontend redirects user to Google OAuth
    2. User authorizes app
    3. Google redirects back with authorization code
    4. Frontend sends code to this endpoint
    5. Backend exchanges code for access token
    6. Backend fetches user info from Google
    7. Backend creates or updates user account
    8. Returns JWT tokens

    Required settings:
    - GOOGLE_OAUTH_CLIENT_ID
    - GOOGLE_OAUTH_CLIENT_SECRET
    - GOOGLE_OAUTH_REDIRECT_URI
    """
    if oauth_data.provider != "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider. Expected 'google'",
        )

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured on the server",
        )

    client_info = get_client_info(request)

    try:
        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": oauth_data.code,
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "redirect_uri": oauth_data.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                logger.warning(
                    "google_oauth_token_exchange_failed",
                    status_code=token_response.status_code,
                    response=token_response.text,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to exchange authorization code",
                )

            token_data = token_response.json()
            google_access_token = token_data.get("access_token")

            # Fetch user info from Google
            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {google_access_token}"},
            )

            if user_info_response.status_code != 200:
                logger.warning(
                    "google_oauth_userinfo_failed",
                    status_code=user_info_response.status_code,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to fetch user information from Google",
                )

            user_info = user_info_response.json()

        # Check if user already exists (for determining if this is a new account)
        existing_user = auth_service.user_repo.get_by_email(user_info["email"])
        is_new_user = existing_user is None

        # Authenticate or create user
        user, access_token, refresh_token, session_id = auth_service.authenticate_oauth(
            provider="google",
            provider_user_id=user_info["id"],
            email=user_info["email"],
            name=user_info.get("name"),
            avatar_url=user_info.get("picture"),
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
            device_fingerprint=oauth_data.device_fingerprint,
        )

        logger.info(
            "google_oauth_login_success",
            user_id=user.user_id,
            session_id=session_id,
            is_new_user=is_new_user,
        )

        # Send email notification
        email_service = get_email_service()
        if is_new_user:
            # Send OAuth account created email for new users
            await email_service.send_oauth_account_created(
                email=user.email,
                full_name=user.full_name or user.email.split("@")[0],
                oauth_provider="google",
                oauth_email=user_info["email"],
            )
        else:
            # Send new login alert for existing users
            await email_service.send_new_login_alert(
                email=user.email,
                full_name=user.full_name or user.email.split("@")[0],
                login_ip=client_info["ip_address"] or "Unknown",
                user_agent=client_info["user_agent"] or "Unknown",
                is_new_device=True,
            )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "google_oauth_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed",
        )


@router.post(
    "/oauth/github",
    response_model=LoginResponse,
    summary="Login with GitHub OAuth",
    responses={
        401: {"model": ErrorResponse, "description": "OAuth authentication failed"},
    },
)
async def oauth_github_login(
    oauth_data: OAuthLoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user with GitHub OAuth.

    Flow:
    1. Frontend redirects user to GitHub OAuth
    2. User authorizes app
    3. GitHub redirects back with authorization code
    4. Frontend sends code to this endpoint
    5. Backend exchanges code for access token
    6. Backend fetches user info from GitHub
    7. Backend creates or updates user account
    8. Returns JWT tokens

    Required settings:
    - GITHUB_OAUTH_CLIENT_ID
    - GITHUB_OAUTH_CLIENT_SECRET
    - GITHUB_OAUTH_REDIRECT_URI
    """
    if oauth_data.provider != "github":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider. Expected 'github'",
        )

    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth is not configured on the server",
        )

    client_info = get_client_info(request)

    try:
        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "code": oauth_data.code,
                    "client_id": settings.github_oauth_client_id,
                    "client_secret": settings.github_oauth_client_secret,
                    "redirect_uri": oauth_data.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )

            if token_response.status_code != 200:
                logger.warning(
                    "github_oauth_token_exchange_failed",
                    status_code=token_response.status_code,
                    response=token_response.text,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to exchange authorization code",
                )

            token_data = token_response.json()
            github_access_token = token_data.get("access_token")

            if not github_access_token:
                logger.warning(
                    "github_oauth_no_access_token",
                    response=token_data,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to obtain access token from GitHub",
                )

            # Fetch user info from GitHub
            user_info_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {github_access_token}",
                    "Accept": "application/json",
                },
            )

            if user_info_response.status_code != 200:
                logger.warning(
                    "github_oauth_userinfo_failed",
                    status_code=user_info_response.status_code,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to fetch user information from GitHub",
                )

            user_info = user_info_response.json()

            # GitHub doesn't always provide email in the main user endpoint
            # Fetch emails separately if needed
            email = user_info.get("email")
            if not email:
                emails_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {github_access_token}",
                        "Accept": "application/json",
                    },
                )
                if emails_response.status_code == 200:
                    emails = emails_response.json()
                    # Get primary verified email
                    for email_data in emails:
                        if email_data.get("primary") and email_data.get("verified"):
                            email = email_data.get("email")
                            break

            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GitHub account must have a verified email address",
                )

        # Check if user already exists (for determining if this is a new account)
        existing_user = auth_service.user_repo.get_by_email(email)
        is_new_user = existing_user is None

        # Authenticate or create user
        user, access_token, refresh_token, session_id = auth_service.authenticate_oauth(
            provider="github",
            provider_user_id=str(user_info["id"]),
            email=email,
            name=user_info.get("name") or user_info.get("login"),
            avatar_url=user_info.get("avatar_url"),
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
            device_fingerprint=oauth_data.device_fingerprint,
        )

        logger.info(
            "github_oauth_login_success",
            user_id=user.user_id,
            session_id=session_id,
            is_new_user=is_new_user,
        )

        # Send email notification
        email_service = get_email_service()
        if is_new_user:
            # Send OAuth account created email for new users
            await email_service.send_oauth_account_created(
                email=user.email,
                full_name=user.full_name or user.email.split("@")[0],
                oauth_provider="github",
                oauth_email=email,
            )
        else:
            # Send new login alert for existing users
            await email_service.send_new_login_alert(
                email=user.email,
                full_name=user.full_name or user.email.split("@")[0],
                login_ip=client_info["ip_address"] or "Unknown",
                user_agent=client_info["user_agent"] or "Unknown",
                is_new_device=True,
            )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "github_oauth_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed",
        )

# Audit Logs Streaming

async def audit_log_stream(
    user_id: str,
    auth_service: AuthService,
) -> AsyncIterator[str]:
    """
    Stream audit logs for a user in real-time using Server-Sent Events.
    
    Checks for new logs every 2 seconds and sends them to the client.
    """
    last_log_time = datetime.now(timezone.utc)
    
    try:
        while True:
            # Fetch new logs since last check
            logs, _ = auth_service.audit_repo.get_by_user(
                user_id=user_id,
                start_date=last_log_time,
                limit=50
            )
            
            # Send each new log as an SSE event
            for log in reversed(logs):  # Oldest first
                log_data = {
                    "log_id": log.log_id,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "success": log.success,
                    "error_message": log.error_message,
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "details": log.details,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                
                # SSE format: "data: {json}\n\n"
                yield f"data: {json.dumps(log_data)}\n\n"
                
                # Update last log time
                if log.created_at:
                    last_log_time = max(last_log_time, log.created_at)
            
            # Wait before checking for new logs again
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        # Client disconnected
        logger.info("audit_log_stream_closed", user_id=user_id)
        yield f"data: {json.dumps({'event': 'stream_closed'})}\n\n"


@router.get(
    "/logs/stream",
    summary="Stream audit logs in real-time (SSE)",
    responses={
        200: {
            "description": "Event stream of audit logs",
            "content": {"text/event-stream": {}}
        }
    },
)
async def stream_audit_logs(
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Stream audit logs for the current user in real-time using Server-Sent Events (SSE).
    
    This endpoint keeps the connection open and sends new logs as they are created.
    
    Frontend Usage (TypeScript):
    ```typescript
    const eventSource = new EventSource('/api/v1/auth/logs/stream', {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });
    
    eventSource.onmessage = (event) => {
      const log = JSON.parse(event.data);
      console.log('New log:', log);
      // Update UI with new log
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      eventSource.close();
    };
    
    // Close when done
    eventSource.close();
    ```
    
    Returns:
    - Event stream of audit log entries as JSON
    - Each event contains: log_id, action, resource_type, success, timestamp, etc.
    """
    logger.info(
        "audit_log_stream_started",
        user_id=current_user["user"].user_id,
    )
    
    return StreamingResponse(
        audit_log_stream(current_user["user"].user_id, auth_service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        },
    )
