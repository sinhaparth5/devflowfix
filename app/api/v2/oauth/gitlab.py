# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitLab OAuth API Endpoints

Handles GitLab OAuth 2.0 authorization flow.
"""

import json
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import structlog

from app.core.config import get_settings
from app.core.schemas.oauth import (
    OAuthAuthorizeResponse,
    OAuthCallbackResponse,
    OAuthConnectionResponse,
    OAuthConnectionListResponse,
    OAuthDisconnectResponse,
    OAuthErrorResponse,
)
from app.dependencies import get_db
from app.auth import get_current_active_user
from app.services.oauth.gitlab_oauth import GitLabOAuthProvider
from app.services.oauth.token_manager import get_token_manager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/gitlab", tags=["OAuth - GitLab"])
settings = get_settings()


def get_gitlab_oauth_provider() -> GitLabOAuthProvider:
    """
    Get GitLab OAuth provider instance.

    Returns:
        GitLabOAuthProvider instance

    Raises:
        HTTPException: If GitLab OAuth is not configured
    """
    if not all([
        settings.gitlab_oauth_client_id,
        settings.gitlab_oauth_client_secret,
        settings.gitlab_oauth_redirect_uri,
    ]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitLab OAuth is not configured. Please set GITLAB_OAUTH_CLIENT_ID, "
                   "GITLAB_OAUTH_CLIENT_SECRET, and GITLAB_OAUTH_REDIRECT_URI environment variables."
        )

    scopes = [scope.strip() for scope in settings.gitlab_oauth_scopes.split(",")]

    # Get GitLab instance URL (default to gitlab.com)
    gitlab_url = getattr(settings, 'gitlab_instance_url', 'https://gitlab.com')

    return GitLabOAuthProvider(
        client_id=settings.gitlab_oauth_client_id,
        client_secret=settings.gitlab_oauth_client_secret,
        redirect_uri=settings.gitlab_oauth_redirect_uri,
        scopes=scopes,
        gitlab_url=gitlab_url,
    )


@router.post(
    "/authorize",
    response_model=OAuthAuthorizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate GitLab OAuth Flow",
    description="Generate GitLab OAuth authorization URL and state for CSRF protection.",
)
async def authorize_gitlab(
    request: Request,
    response: Response,
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthAuthorizeResponse:
    """
    Initiate GitLab OAuth authorization flow.

    **Flow:**
    1. Generate CSRF protection state
    2. Build GitLab authorization URL
    3. Store state in session/cookie
    4. Return URL to frontend for redirect

    **Returns:**
    - Authorization URL to redirect user to
    - State parameter to store in session
    """
    try:
        provider = get_gitlab_oauth_provider()

        # Generate CSRF state
        state = provider.generate_state()

        # Store state and user_id together in cookie for callback
        # Callback endpoint doesn't have JWT auth, so we need user_id in the cookie
        cookie_data = json.dumps({
            "state": state,
            "user_id": current_user_data['user'].user_id
        })
        response.set_cookie(
            key="oauth_state_data",
            value=cookie_data,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=600,  # 10 minutes
        )

        # Build authorization URL
        authorization_url = provider.build_authorization_url(state)

        logger.info(
            "gitlab_oauth_initiated",
            user_id=current_user_data["user"].user_id,
            state_length=len(state),
        )

        return OAuthAuthorizeResponse(
            authorization_url=authorization_url,
            state=state,
            provider="gitlab",
        )

    except Exception as e:
        logger.error(
            "gitlab_oauth_authorize_failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate OAuth flow: {str(e)}"
        )


@router.get(
    "/callback",
    response_model=OAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
    summary="GitLab OAuth Callback",
    description="Handle GitLab OAuth callback after user authorization.",
)
async def gitlab_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from GitLab"),
    state: str = Query(..., description="CSRF protection state"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Handle GitLab OAuth callback.

    **Flow:**
    1. Validate state parameter (CSRF protection)
    2. Exchange authorization code for access token
    3. Fetch user info from GitLab
    4. Encrypt and store token in database
    5. Redirect to success page

    **Query Parameters:**
    - code: Authorization code from GitLab
    - state: CSRF protection state

    **Returns:**
    - Redirect to frontend with success status

    **Note:**
    This endpoint does NOT require authentication because it's called by GitLab
    during the OAuth redirect. User identity is retrieved from the OAuth state cookie.
    """
    try:
        provider = get_gitlab_oauth_provider()

        # Get stored state and user_id from cookie
        cookie_data_str = request.cookies.get("oauth_state_data")

        if not cookie_data_str:
            logger.error("gitlab_oauth_state_missing")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state not found. Please restart the authorization flow."
            )

        # Parse cookie data
        try:
            cookie_data = json.loads(cookie_data_str)
            stored_state = cookie_data.get("state")
            user_id = cookie_data.get("user_id")
        except (json.JSONDecodeError, AttributeError):
            logger.error("gitlab_oauth_state_invalid_format")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth state format. Please restart the authorization flow."
            )

        if not stored_state or not user_id:
            logger.error("gitlab_oauth_state_incomplete")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incomplete OAuth state. Please restart the authorization flow."
            )

        # Validate state (CSRF protection)
        if not provider.validate_state(state, stored_state):
            logger.error(
                "gitlab_oauth_state_mismatch",
                user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid state parameter. Possible CSRF attack detected."
            )

        logger.info(
            "gitlab_oauth_callback_received",
            user_id=user_id,
            has_code=bool(code),
        )

        # Exchange code for token
        token_data = await provider.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to obtain access token from GitLab"
            )

        # Get user info from GitLab
        gitlab_user = await provider.get_user_info(access_token)

        # Store OAuth connection
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        # Calculate expiration time
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        scopes = token_data.get("scope", "").split(" ")

        oauth_connection = await token_manager.store_oauth_connection(
            db=db,
            user_id=user_id,
            provider="gitlab",
            provider_user_id=str(gitlab_user["id"]),
            provider_username=gitlab_user["username"],
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            expires_at=expires_at,
        )

        db.commit()

        logger.info(
            "gitlab_oauth_success",
            user_id=user_id,
            gitlab_username=gitlab_user["username"],
            connection_id=oauth_connection.id,
        )

        # Redirect to frontend success page
        frontend_url = settings.cors_origins.split(",")[0] if settings.cors_origins != "*" else "http://localhost:3000"
        redirect_url = f"{frontend_url}/settings/integrations?oauth=success&provider=gitlab&username={gitlab_user['username']}"

        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "gitlab_oauth_callback_failed",
            error=str(e),
            exc_info=True,
        )

        # Redirect to error page
        frontend_url = settings.cors_origins.split(",")[0] if settings.cors_origins != "*" else "http://localhost:3000"
        redirect_url = f"{frontend_url}/settings/integrations?oauth=error&provider=gitlab&message={str(e)}"

        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/connection",
    response_model=OAuthConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get GitLab OAuth Connection",
    description="Get current user's GitLab OAuth connection details.",
)
async def get_gitlab_connection(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthConnectionResponse:
    """
    Get GitLab OAuth connection for current user.

    **Returns:**
    - OAuth connection details if exists
    - 404 if no connection found
    """
    user = current_user_data["user"]
    token_manager = get_token_manager(settings.oauth_token_encryption_key)

    connection = await token_manager.get_oauth_connection(
        db=db,
        user_id=user.user_id,
        provider="gitlab",
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitLab OAuth connection found for this user"
        )

    return OAuthConnectionResponse.from_orm(connection)


@router.delete(
    "/disconnect",
    response_model=OAuthDisconnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect GitLab OAuth",
    description="Revoke and delete GitLab OAuth connection.",
)
async def disconnect_gitlab(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthDisconnectResponse:
    """
    Disconnect GitLab OAuth.

    **Actions:**
    1. Revoke token with GitLab
    2. Delete connection from database
    3. Delete all associated repository connections

    **Returns:**
    - Success message with disconnected connection details
    """
    user = current_user_data["user"]
    token_manager = get_token_manager(settings.oauth_token_encryption_key)

    # Get connection
    connection = await token_manager.get_oauth_connection(
        db=db,
        user_id=user.user_id,
        provider="gitlab",
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitLab OAuth connection found for this user"
        )

    try:
        provider = get_gitlab_oauth_provider()

        # Get decrypted token
        access_token = token_manager.get_decrypted_token(connection)

        # Revoke token with GitLab
        await provider.revoke_token(access_token)

        logger.info(
            "gitlab_token_revoked",
            user_id=user.user_id,
            connection_id=connection.id,
        )

    except Exception as e:
        logger.warning(
            "gitlab_token_revoke_failed",
            error=str(e),
            user_id=user.user_id,
        )
        # Continue with deletion even if revocation fails

    # Deactivate connection
    await token_manager.revoke_oauth_connection(
        db=db,
        connection_id=connection.id,
        user_id=user.user_id,
    )

    db.commit()

    logger.info(
        "gitlab_oauth_disconnected",
        user_id=user.user_id,
        connection_id=connection.id,
    )

    return OAuthDisconnectResponse(
        success=True,
        connection_id=connection.id,
        provider="gitlab",
        message="GitLab OAuth connection successfully disconnected"
    )


@router.post(
    "/refresh",
    response_model=OAuthConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh GitLab Access Token",
    description="Refresh GitLab OAuth access token using refresh token.",
)
async def refresh_gitlab_token(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthConnectionResponse:
    """
    Refresh GitLab OAuth access token.

    **Actions:**
    1. Get current connection
    2. Use refresh token to get new access token
    3. Update connection with new tokens
    4. Return updated connection

    **Note:**
    GitLab access tokens expire, so this endpoint should be called
    when the token is close to expiration.

    **Returns:**
    - Updated OAuth connection with new tokens
    """
    user = current_user_data["user"]
    token_manager = get_token_manager(settings.oauth_token_encryption_key)

    # Get connection
    connection = await token_manager.get_oauth_connection(
        db=db,
        user_id=user.user_id,
        provider="gitlab",
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitLab OAuth connection found for this user"
        )

    if not connection.refresh_token_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh token available for this connection"
        )

    try:
        provider = get_gitlab_oauth_provider()

        # Get decrypted refresh token
        refresh_token = token_manager.decrypt_token(connection.refresh_token_encrypted)

        # Refresh the token
        token_data = await provider.refresh_access_token(refresh_token)

        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token", refresh_token)  # Use old if not provided
        expires_in = token_data.get("expires_in")

        if not new_access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to refresh access token from GitLab"
            )

        # Calculate new expiration
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Update connection with new tokens
        updated_connection = await token_manager.update_oauth_tokens(
            db=db,
            connection_id=connection.id,
            user_id=user.user_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_at=expires_at,
        )

        db.commit()

        logger.info(
            "gitlab_token_refreshed",
            user_id=user.user_id,
            connection_id=connection.id,
        )

        return OAuthConnectionResponse.from_orm(updated_connection)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "gitlab_token_refresh_failed",
            error=str(e),
            user_id=user.user_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh GitLab token: {str(e)}"
        )
