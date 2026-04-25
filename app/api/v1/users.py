# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import structlog

from app.adapters.database.postgres.models import UserDetailsTable, UserTable
from app.core.schemas.users import ManualUserCreateRequest, ManualUserCreateResponse
from app.dependencies import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "",
    response_model=ManualUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create local user and user details",
    description="Creates a user row and matching user_details row in a single database transaction.",
)
async def create_local_user(
    payload: ManualUserCreateRequest,
    db: Session = Depends(get_db),
):
    user_id = payload.user_id or uuid4().hex[:32]

    existing_user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with id '{user_id}' already exists",
        )

    existing_email = db.query(UserTable).filter(UserTable.email == payload.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{payload.email}' already exists",
        )

    now = datetime.now(timezone.utc)

    db_user = UserTable(
        user_id=user_id,
        email=payload.email,
        full_name=payload.full_name,
        avatar_url=payload.avatar_url,
        oauth_provider=payload.oauth_provider,
        oauth_id=payload.oauth_id or user_id,
        organization_id=payload.organization_id,
        team_id=payload.team_id,
        role=payload.role,
        is_active=payload.is_active,
        is_verified=payload.is_verified,
        github_username=payload.github_username,
        created_at=now,
        updated_at=now,
    )

    user_details = UserDetailsTable(
        user_id=user_id,
        country=payload.country,
        city=payload.city,
        postal_code=payload.postal_code,
        facebook_link=payload.facebook_link,
        twitter_link=payload.twitter_link,
        linkedin_link=payload.linkedin_link,
        instagram_link=payload.instagram_link,
        github_link=payload.github_link,
        created_at=now,
        updated_at=now,
    )

    try:
        db.add(db_user)
        db.flush()
        db.add(user_details)
        db.commit()
        db.refresh(db_user)
        db.refresh(user_details)
    except IntegrityError as exc:
        db.rollback()
        logger.error("manual_user_create_failed", error=str(exc), user_id=user_id, email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User creation failed because of a database uniqueness or foreign key constraint",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("manual_user_create_failed", error=str(exc), user_id=user_id, email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create local user",
        ) from exc

    return ManualUserCreateResponse(
        user_id=db_user.user_id,
        email=db_user.email,
        full_name=db_user.full_name,
        role=db_user.role,
        is_active=db_user.is_active,
        is_verified=db_user.is_verified,
        oauth_provider=db_user.oauth_provider,
        oauth_id=db_user.oauth_id,
        organization_id=db_user.organization_id,
        team_id=db_user.team_id,
        github_username=db_user.github_username,
        created_at=db_user.created_at,
        updated_at=db_user.updated_at,
        user_details=user_details,
    )
