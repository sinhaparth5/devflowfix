# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitHub OAuth API Endpoints

Handles GitHub OAuth via Zitadel IdP integration.
Users authenticate via GitHub through Zitadel, and we fetch their
GitHub access token from Zitadel's stored IdP tokens.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import structlog

from app.core.config import get_settings
from app.core.schemas.oauth import (
    OAuthConnectionResponse,
    OAuthDisconnectResponse,
)
from app.dependencies import get_db
from app.auth import get_current_active_user
from app.auth.config import get_zitadel_settings
from app.services.oauth.zitadel_idp import get_zitadel_idp_service, IdPToken
from app.services.oauth.token_manager import get_token_manager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/github", tags=["OAuth - GitHub"])
settings = get_settings()

@router.post(
    "/sync",
    response_model=OAuthConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync GitHub Connection from Zitadel",
    description="Fetch GitHub access token from Zitadel IdP and store it for API access.",
)
async def sync_github_connection(
    request: Request,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthConnectionResponse:
    """
    Sync GitHub OAuth connection from Zitadel.

    If the user logged in via GitHub through Zitadel, this endpoint
    retrieves their GitHub access token from Zitadel and stores it
    for use with GitHub API operations (repo listing, webhooks, etc.).

    **Prerequisites:**
    - User must have logged in via GitHub through Zitadel at least once
    - GitHub must be configured as an IdP in Zitadel
    - ZITADEL_GITHUB_IDP_ID must be set

    **Flow:**
    1. Get user's access token from request
    2. Query Zitadel for GitHub IdP link
    3. Fetch GitHub access token from Zitadel
    4. Store encrypted token in oauth_connections table

    **Returns:**
    - OAuth connection details with GitHub username
    """
    user = current_user_data["user"]
    zitadel_settings = get_zitadel_settings()

    # Check if GitHub IdP is configured
    if not zitadel_settings.github_idp_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub IdP is not configured in Zitadel. "
                   "Please set ZITADEL_GITHUB_IDP_ID environment variable."
        )

    # Get user's Zitadel access token from the request
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token"
        )

    user_access_token = auth_header.replace("Bearer ", "")

    try:
        # Get GitHub token from Zitadel IdP
        idp_service = get_zitadel_idp_service()
        github_token = await idp_service.get_github_token(
            user_access_token=user_access_token,
            user_id=user.user_id,
        )

        if not github_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="GitHub is not linked to your account. "
                       "Please login via GitHub through Zitadel first."
            )

        if not github_token.access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub access token not available. "
                       "Please re-authenticate via GitHub."
            )

        # Store the token in oauth_connections table
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        oauth_connection = await token_manager.store_oauth_connection(
            db=db,
            user_id=user.user_id,
            provider="github",
            provider_user_id=github_token.provider_user_id,
            provider_username=github_token.provider_username,
            access_token=github_token.access_token,
            refresh_token=None,  # GitHub tokens via Zitadel don't have refresh tokens
            scopes=github_token.scopes,
            expires_at=github_token.expires_at,
        )

        db.commit()

        logger.info(
            "github_connection_synced",
            user_id=user.user_id,
            github_username=github_token.provider_username,
            connection_id=oauth_connection.id,
        )

        return OAuthConnectionResponse.from_orm(oauth_connection)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "github_sync_failed",
            error=str(e),
            user_id=user.user_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync GitHub connection: {str(e)}"
        )

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
            detail="No GitHub OAuth connection found. "
                   "Use POST /sync to sync your GitHub connection from Zitadel."
        )

    return OAuthConnectionResponse.from_orm(connection)

@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    summary="Check GitHub Connection Status",
    description="Check if user has GitHub linked via Zitadel and if token is synced.",
)
async def get_github_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    """
    Check GitHub connection status.

    Returns information about:
    - Whether GitHub is linked in Zitadel
    - Whether token is synced to DevFlowFix
    - Token validity

    **Returns:**
    - Status information dict
    """
    user = current_user_data["user"]
    zitadel_settings = get_zitadel_settings()

    result = {
        "github_idp_configured": bool(zitadel_settings.github_idp_id),
        "linked_in_zitadel": False,
        "synced_to_devflowfix": False,
        "github_username": None,
        "needs_sync": False,
    }

    if not zitadel_settings.github_idp_id:
        return result

    # Check if linked in Zitadel
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        user_access_token = auth_header.replace("Bearer ", "")
        idp_service = get_zitadel_idp_service()

        try:
            github_token = await idp_service.get_github_token(
                user_access_token=user_access_token,
                user_id=user.user_id,
            )

            if github_token:
                result["linked_in_zitadel"] = True
                result["github_username"] = github_token.provider_username
        except Exception as e:
            logger.warning(
                "github_status_check_failed",
                error=str(e),
            )

    # Check if synced in DevFlowFix
    token_manager = get_token_manager(settings.oauth_token_encryption_key)
    connection = await token_manager.get_oauth_connection(
        db=db,
        user_id=user.user_id,
        provider="github",
    )

    if connection:
        result["synced_to_devflowfix"] = True
        result["github_username"] = connection.provider_username

    # Determine if sync is needed
    result["needs_sync"] = result["linked_in_zitadel"] and not result["synced_to_devflowfix"]

    return result


@router.delete(
    "/disconnect",
    response_model=OAuthDisconnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect GitHub OAuth",
    description="Remove GitHub OAuth connection from DevFlowFix (does not unlink from Zitadel).",
)
async def disconnect_github(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthDisconnectResponse:
    """
    Disconnect GitHub OAuth.

    This removes the GitHub token from DevFlowFix but does NOT unlink
    GitHub from your Zitadel account. To fully unlink, you must also
    remove the connection in Zitadel Console.

    **Actions:**
    1. Deactivate connection in database
    2. Delete all associated repository connections

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
        message="GitHub OAuth connection removed from DevFlowFix. "
                "To fully unlink, also remove the connection in Zitadel Console."
    )
