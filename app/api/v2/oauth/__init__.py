# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
OAuth API Router

Combines all OAuth provider routers (GitHub, GitLab, etc.)
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.schemas.oauth import OAuthConnectionListResponse
from app.dependencies import get_db
from app.auth import get_current_active_user
from app.services.oauth.token_manager import get_token_manager
from app.core.config import get_settings

from . import github
from . import gitlab

# Create main OAuth router
router = APIRouter(prefix="/oauth", tags=["OAuth"])

# Include provider-specific routers
router.include_router(github.router)
router.include_router(gitlab.router)

settings = get_settings()


@router.get(
    "/connections",
    response_model=OAuthConnectionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List OAuth Connections",
    description="Get all OAuth connections for the current user.",
)
async def list_oauth_connections(
    db: Session = Depends(get_db),
    current_user_data: dict = Depends(get_current_active_user),
) -> OAuthConnectionListResponse:
    """
    List all OAuth connections for current user.

    **Returns:**
    - List of all active OAuth connections (GitHub, GitLab, etc.)
    """
    from app.adapters.database.postgres.models import OAuthConnectionTable
    from app.core.schemas.oauth import OAuthConnectionResponse

    user = current_user_data["user"]

    connections = (
        db.query(OAuthConnectionTable)
        .filter(
            OAuthConnectionTable.user_id == user.user_id,
            OAuthConnectionTable.is_active == True,
        )
        .all()
    )

    connection_responses = [
        OAuthConnectionResponse.from_orm(conn) for conn in connections
    ]

    return OAuthConnectionListResponse(
        connections=connection_responses,
        total=len(connection_responses),
    )
