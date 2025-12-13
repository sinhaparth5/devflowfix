# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import structlog

from app.dependencies import get_db
from app.api.v1.auth import get_current_user
from app.adapters.database.postgres.repositories.user_details import UserDetailsRepository
from app.core.schemas.users import (
    UserDetailsUpdate,
    UserDetailsResponse,
)
from app.core.schemas.common import SuccessResponse, ErrorResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/user-details", tags=["User Details"])


def get_user_details_repo(db: Session = Depends(get_db)) -> UserDetailsRepository:
    """Get user details repository."""
    return UserDetailsRepository(db)


@router.get("/me", response_model=UserDetailsResponse)
async def get_current_user_details(
    current_user: dict = Depends(get_current_user),
    user_details_repo: UserDetailsRepository = Depends(get_user_details_repo),
):
    """
    Get current authenticated user's details.

    Returns the user details for the currently authenticated user.
    """
    user_id = current_user["user"].user_id

    user_details = user_details_repo.get_by_user_id(user_id)

    if not user_details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User details not found"
        )

    return user_details


@router.get("/{user_id}", response_model=UserDetailsResponse)
async def get_user_details_by_id(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    user_details_repo: UserDetailsRepository = Depends(get_user_details_repo),
):
    """
    Get user details by user ID.

    Only the user themselves or admins can access user details.
    """
    # Check if user is requesting their own details or is an admin
    if current_user["user"].user_id != user_id and current_user["user"].role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this user's details"
        )

    user_details = user_details_repo.get_by_user_id(user_id)

    if not user_details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User details not found"
        )

    return user_details


@router.put("/me", response_model=UserDetailsResponse)
async def update_current_user_details(
    details: UserDetailsUpdate,
    current_user: dict = Depends(get_current_user),
    user_details_repo: UserDetailsRepository = Depends(get_user_details_repo),
):
    """
    Update current authenticated user's details.

    Creates new user details if they don't exist, or updates existing ones.
    """
    user_id = current_user["user"].user_id

    try:
        # Use upsert to create or update
        user_details = user_details_repo.upsert(
            user_id=user_id,
            country=details.country,
            city=details.city,
            postal_code=details.postal_code,
            facebook_link=details.facebook_link,
            twitter_link=details.twitter_link,
            linkedin_link=details.linkedin_link,
            instagram_link=details.instagram_link,
            github_link=details.github_link,
        )

        logger.info("user_details_updated", user_id=user_id)
        return user_details

    except Exception as e:
        logger.error("user_details_update_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user details"
        )


@router.put("/{user_id}", response_model=UserDetailsResponse)
async def update_user_details_by_id(
    user_id: str,
    details: UserDetailsUpdate,
    current_user: dict = Depends(get_current_user),
    user_details_repo: UserDetailsRepository = Depends(get_user_details_repo),
):
    """
    Update user details by user ID.

    Only the user themselves or admins can update user details.
    """
    # Check if user is updating their own details or is an admin
    if current_user["user"].user_id != user_id and current_user["user"].role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this user's details"
        )

    try:
        # Use upsert to create or update
        user_details = user_details_repo.upsert(
            user_id=user_id,
            country=details.country,
            city=details.city,
            postal_code=details.postal_code,
            facebook_link=details.facebook_link,
            twitter_link=details.twitter_link,
            linkedin_link=details.linkedin_link,
            instagram_link=details.instagram_link,
            github_link=details.github_link,
        )

        logger.info("user_details_updated", user_id=user_id)
        return user_details

    except Exception as e:
        logger.error("user_details_update_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user details"
        )


@router.delete("/me", response_model=SuccessResponse)
async def delete_current_user_details(
    current_user: dict = Depends(get_current_user),
    user_details_repo: UserDetailsRepository = Depends(get_user_details_repo),
):
    """
    Delete current authenticated user's details.
    """
    user_id = current_user["user"].user_id

    success = user_details_repo.delete(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User details not found"
        )

    logger.info("user_details_deleted", user_id=user_id)
    return SuccessResponse(message="User details deleted successfully")


@router.delete("/{user_id}", response_model=SuccessResponse)
async def delete_user_details_by_id(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    user_details_repo: UserDetailsRepository = Depends(get_user_details_repo),
):
    """
    Delete user details by user ID.

    Only the user themselves or admins can delete user details.
    """
    # Check if user is deleting their own details or is an admin
    if current_user["user"].user_id != user_id and current_user["user"].role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this user's details"
        )

    success = user_details_repo.delete(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User details not found"
        )

    logger.info("user_details_deleted", user_id=user_id)
    return SuccessResponse(message="User details deleted successfully")
