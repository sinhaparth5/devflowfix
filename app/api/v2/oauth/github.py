# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub OAuth API Endpoints

Handles GitHub OAuth 2.0 authorization flow.
"""

from typing import Optional
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
from app.dependencies import get_db, get_current_active_user
from app.services.oauth.github_oauth import GitHubOAuthProvider
from app.services.oauth.token_manager import get_token_manager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/github", tags=["OAuth - GitHub"])
settings = get_settings()


def get_github_oauth_provider() -> GitHubOAuthProvider:
    """
    Get GitHub OAuth provider instance.

    Returns:
        GitHubOAuthProvider instance

    Raises:
        HTTPException: If GitHub OAuth is not configured
    """
    if not all([
        settings.github_oauth_client_id,
        settings.github_oauth_client_secret,
        settings.github_oauth_redirect_uri,
    ]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth is not configured. Please set GITHUB_OAUTH_CLIENT_ID, "
                   "GITHUB_OAUTH_CLIENT_SECRET, and GITHUB_OAUTH_REDIRECT_URI environment variables."
        )

    scopes = [scope.strip() for scope in settings.github_oauth_scopes.split(",")]

    return GitHubOAuthProvider(
        client_id=settings.github_oauth_client_id,
        client_secret=settings.github_oauth_client_secret,
        redirect_uri=settings.github_oauth_redirect_uri,
        scopes=scopes,
    )


@router.post(
    "/authorize",
    response_model=OAuthAuthorizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate GitHub OAuth Flow",
    description="Generate GitHub OAuth authorization URL and state for CSRF protection.",
)
async def authorize_github(
    request: Request,
    response: Response,
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthAuthorizeResponse:
    """
    Initiate GitHub OAuth authorization flow.

    **Flow:**
    1. Generate CSRF protection state
    2. Build GitHub authorization URL
    3. Store state in session/cookie
    4. Return URL to frontend for redirect

    **Returns:**
    - Authorization URL to redirect user to
    - State parameter to store in session
    """
    try:
        provider = get_github_oauth_provider()

        # Generate CSRF state
        state = provider.generate_state()

        # Store state in session (you'll need to implement session management)
        # For now, we'll return it and expect frontend to pass it back
        response.set_cookie(
            key=f"oauth_state_{current_user_data['user'].user_id}",
            value=state,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=600,  # 10 minutes
        )

        # Build authorization URL
        authorization_url = provider.build_authorization_url(state)

        logger.info(
            "github_oauth_initiated",
            user_id=current_user_data["user"].user_id,
            state_length=len(state),
        )

        return OAuthAuthorizeResponse(
            authorization_url=authorization_url,
            state=state,
            provider="github",
        )

    except Exception as e:
        logger.error(
            "github_oauth_authorize_failed",
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
    summary="GitHub OAuth Callback",
    description="Handle GitHub OAuth callback after user authorization.",
)
async def github_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="CSRF protection state"),
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> RedirectResponse:
    """
    Handle GitHub OAuth callback.

    **Flow:**
    1. Validate state parameter (CSRF protection)
    2. Exchange authorization code for access token
    3. Fetch user info from GitHub
    4. Encrypt and store token in database
    5. Redirect to success page

    **Query Parameters:**
    - code: Authorization code from GitHub
    - state: CSRF protection state

    **Returns:**
    - Redirect to frontend with success status
    """
    try:
        user = current_user_data["user"]
        provider = get_github_oauth_provider()

        # Get stored state from cookie
        stored_state = request.cookies.get(f"oauth_state_{user.user_id}")

        if not stored_state:
            logger.error(
                "github_oauth_state_missing",
                user_id=user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state not found. Please restart the authorization flow."
            )

        # Validate state (CSRF protection)
        if not provider.validate_state(state, stored_state):
            logger.error(
                "github_oauth_state_mismatch",
                user_id=user.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid state parameter. Possible CSRF attack detected."
            )

        logger.info(
            "github_oauth_callback_received",
            user_id=user.user_id,
            has_code=bool(code),
        )

        # Exchange code for token
        token_data = await provider.exchange_code_for_token(code)
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to obtain access token from GitHub"
            )

        # Get user info from GitHub
        github_user = await provider.get_user_info(access_token)

        # Store OAuth connection
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        scopes = token_data.get("scope", "").split(",")

        oauth_connection = await token_manager.store_oauth_connection(
            db=db,
            user_id=user.user_id,
            provider="github",
            provider_user_id=str(github_user["id"]),
            provider_username=github_user["login"],
            access_token=access_token,
            refresh_token=None,  # GitHub OAuth tokens don't expire
            scopes=scopes,
            expires_at=None,  # GitHub tokens don't expire
        )

        db.commit()

        logger.info(
            "github_oauth_success",
            user_id=user.user_id,
            github_username=github_user["login"],
            connection_id=oauth_connection.id,
        )

        # Redirect to frontend success page
        frontend_url = settings.cors_origins.split(",")[0] if settings.cors_origins != "*" else "http://localhost:3000"
        redirect_url = f"{frontend_url}/settings/integrations?oauth=success&provider=github&username={github_user['login']}"

        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "github_oauth_callback_failed",
            error=str(e),
            exc_info=True,
        )

        # Redirect to error page
        frontend_url = settings.cors_origins.split(",")[0] if settings.cors_origins != "*" else "http://localhost:3000"
        redirect_url = f"{frontend_url}/settings/integrations?oauth=error&provider=github&message={str(e)}"

        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/connection",
    response_model=OAuthConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get GitHub OAuth Connection",
    description="Get current user's GitHub OAuth connection details.",
)
async def get_github_connection(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthConnectionResponse:
    """
    Get GitHub OAuth connection for current user.

    **Returns:**
    - OAuth connection details if exists
    - 404 if no connection found
    """
    user = current_user_data["user"]
    token_manager = get_token_manager(settings.oauth_token_encryption_key)

    connection = await token_manager.get_oauth_connection(
        db=db,
        user_id=user.user_id,
        provider="github",
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub OAuth connection found for this user"
        )

    return OAuthConnectionResponse.from_orm(connection)


@router.delete(
    "/disconnect",
    response_model=OAuthDisconnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect GitHub OAuth",
    description="Revoke and delete GitHub OAuth connection.",
)
async def disconnect_github(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthDisconnectResponse:
    """
    Disconnect GitHub OAuth.

    **Actions:**
    1. Revoke token with GitHub
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
        provider="github",
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub OAuth connection found for this user"
        )

    try:
        provider = get_github_oauth_provider()

        # Get decrypted token
        access_token = token_manager.get_decrypted_token(connection)

        # Revoke token with GitHub
        await provider.revoke_token(access_token)

        logger.info(
            "github_token_revoked",
            user_id=user.user_id,
            connection_id=connection.id,
        )

    except Exception as e:
        logger.warning(
            "github_token_revoke_failed",
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
        "github_oauth_disconnected",
        user_id=user.user_id,
        connection_id=connection.id,
    )

    return OAuthDisconnectResponse(
        success=True,
        connection_id=connection.id,
        provider="github",
        message="GitHub OAuth connection successfully disconnected"
    )
