# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
GitLab OAuth API Endpoints

Handles GitLab OAuth via Zitadel IdP integration.
Users authenticate via GitLab through Zitadel, and we fetch their
GitLab access token from Zitadel's stored IdP tokens.
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
router = APIRouter(prefix="/gitlab", tags=["OAuth - GitLab"])
settings = get_settings()


@router.post(
    "/sync",
    response_model=OAuthConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync GitLab Connection from Zitadel",
    description="Fetch GitLab access token from Zitadel IdP and store it for API access.",
)
async def sync_gitlab_connection(
    request: Request,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthConnectionResponse:
    """
    Sync GitLab OAuth connection from Zitadel.

    If the user logged in via GitLab through Zitadel, this endpoint
    retrieves their GitLab access token from Zitadel and stores it
    for use with GitLab API operations (project listing, webhooks, etc.).

    **Prerequisites:**
    - User must have logged in via GitLab through Zitadel at least once
    - GitLab must be configured as an IdP in Zitadel
    - ZITADEL_GITLAB_IDP_ID must be set

    **Flow:**
    1. Get user's access token from request
    2. Query Zitadel for GitLab IdP link
    3. Fetch GitLab access token from Zitadel
    4. Store encrypted token in oauth_connections table

    **Returns:**
    - OAuth connection details with GitLab username
    """
    user = current_user_data["user"]
    zitadel_settings = get_zitadel_settings()

    # Check if GitLab IdP is configured
    if not zitadel_settings.gitlab_idp_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitLab IdP is not configured in Zitadel. "
                   "Please set ZITADEL_GITLAB_IDP_ID environment variable."
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
        # Get GitLab token from Zitadel IdP
        idp_service = get_zitadel_idp_service()
        gitlab_token = await idp_service.get_gitlab_token(
            user_access_token=user_access_token,
            user_id=user.user_id,
        )

        if not gitlab_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="GitLab is not linked to your account. "
                       "Please login via GitLab through Zitadel first."
            )

        if not gitlab_token.access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab access token not available. "
                       "Please re-authenticate via GitLab."
            )

        # Store the token in oauth_connections table
        token_manager = get_token_manager(settings.oauth_token_encryption_key)

        oauth_connection = await token_manager.store_oauth_connection(
            db=db,
            user_id=user.user_id,
            provider="gitlab",
            provider_user_id=gitlab_token.provider_user_id,
            provider_username=gitlab_token.provider_username,
            access_token=gitlab_token.access_token,
            refresh_token=None,  # GitLab tokens via Zitadel may not have refresh tokens
            scopes=gitlab_token.scopes,
            expires_at=gitlab_token.expires_at,
        )

        db.commit()

        logger.info(
            "gitlab_connection_synced",
            user_id=user.user_id,
            gitlab_username=gitlab_token.provider_username,
            connection_id=oauth_connection.id,
        )

        return OAuthConnectionResponse.from_orm(oauth_connection)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "gitlab_sync_failed",
            error=str(e),
            user_id=user.user_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync GitLab connection: {str(e)}"
        )


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
            detail="No GitLab OAuth connection found. "
                   "Use POST /sync to sync your GitLab connection from Zitadel."
        )

    return OAuthConnectionResponse.from_orm(connection)


@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    summary="Check GitLab Connection Status",
    description="Check if user has GitLab linked via Zitadel and if token is synced.",
)
async def get_gitlab_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    """
    Check GitLab connection status.

    Returns information about:
    - Whether GitLab is linked in Zitadel
    - Whether token is synced to DevFlowFix
    - Token validity

    **Returns:**
    - Status information dict
    """
    user = current_user_data["user"]
    zitadel_settings = get_zitadel_settings()

    result = {
        "gitlab_idp_configured": bool(zitadel_settings.gitlab_idp_id),
        "linked_in_zitadel": False,
        "synced_to_devflowfix": False,
        "gitlab_username": None,
        "needs_sync": False,
    }

    if not zitadel_settings.gitlab_idp_id:
        return result

    # Check if linked in Zitadel
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        user_access_token = auth_header.replace("Bearer ", "")
        idp_service = get_zitadel_idp_service()

        try:
            gitlab_token = await idp_service.get_gitlab_token(
                user_access_token=user_access_token,
                user_id=user.user_id,
            )

            if gitlab_token:
                result["linked_in_zitadel"] = True
                result["gitlab_username"] = gitlab_token.provider_username
        except Exception as e:
            logger.warning(
                "gitlab_status_check_failed",
                error=str(e),
            )

    # Check if synced in DevFlowFix
    token_manager = get_token_manager(settings.oauth_token_encryption_key)
    connection = await token_manager.get_oauth_connection(
        db=db,
        user_id=user.user_id,
        provider="gitlab",
    )

    if connection:
        result["synced_to_devflowfix"] = True
        result["gitlab_username"] = connection.provider_username

    # Determine if sync is needed
    result["needs_sync"] = result["linked_in_zitadel"] and not result["synced_to_devflowfix"]

    return result


@router.delete(
    "/disconnect",
    response_model=OAuthDisconnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Disconnect GitLab OAuth",
    description="Remove GitLab OAuth connection from DevFlowFix (does not unlink from Zitadel).",
)
async def disconnect_gitlab(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthDisconnectResponse:
    """
    Disconnect GitLab OAuth.

    This removes the GitLab token from DevFlowFix but does NOT unlink
    GitLab from your Zitadel account. To fully unlink, you must also
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
        provider="gitlab",
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitLab OAuth connection found for this user"
        )

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
        message="GitLab OAuth connection removed from DevFlowFix. "
                "To fully unlink, also remove the connection in Zitadel Console."
    )
