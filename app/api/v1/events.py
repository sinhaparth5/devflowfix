# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Events API Endpoints

CRUD operations for user calendar events.
"""

from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog
import uuid

from app.dependencies import get_db
from app.auth import get_current_active_user
from app.adapters.database.postgres.models import EventTable, EventColor as DBEventColor
from app.core.schemas.events import (
    EventCreateRequest,
    EventUpdateRequest,
    EventResponse,
    EventListResponse,
    EventDeleteResponse,
    EventColor,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])


def _db_event_to_response(event: EventTable) -> EventResponse:
    """Convert database event to response schema."""
    return EventResponse(
        id=event.id,
        user_id=event.user_id,
        title=event.title,
        color=EventColor(event.color.value),
        start_date=event.start_date,
        end_date=event.end_date,
        description=event.description,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


@router.get(
    "/",
    response_model=EventListResponse,
    summary="List Events",
    description="Get all events for the current user with optional date filtering.",
)
async def list_events(
    start_date: Optional[datetime] = Query(None, description="Filter events starting from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events ending before this date"),
    color: Optional[EventColor] = Query(None, description="Filter by event color"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EventListResponse:
    """
    List all events for the current user.

    **Query Parameters:**
    - start_date: Filter events that start on or after this date
    - end_date: Filter events that end on or before this date
    - color: Filter by event color (danger, primary, success, warning)

    **Returns:**
    - List of events with total count
    """
    user = current_user["user"]

    try:
        query = db.query(EventTable).filter(EventTable.user_id == user.user_id)

        if start_date:
            query = query.filter(EventTable.start_date >= start_date)
        if end_date:
            query = query.filter(EventTable.end_date <= end_date)
        if color:
            query = query.filter(EventTable.color == DBEventColor(color.value))

        # Order by start_date ascending
        query = query.order_by(EventTable.start_date.asc())

        events = query.all()

        return EventListResponse(
            events=[_db_event_to_response(e) for e in events],
            total=len(events),
        )

    except Exception as e:
        logger.error("list_events_failed", error=str(e), user_id=user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve events",
        )


@router.post(
    "/",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Event",
    description="Create a new calendar event.",
)
async def create_event(
    request: EventCreateRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EventResponse:
    """
    Create a new event for the current user.

    **Request Body:**
    - title: Event title (required)
    - color: Event color - danger, primary, success, warning (default: primary)
    - start_date: Event start date (required)
    - end_date: Event end date (required)
    - description: Optional event description

    **Returns:**
    - Created event details
    """
    user = current_user["user"]
    now = datetime.now(timezone.utc)

    try:
        event = EventTable(
            id=f"evt_{uuid.uuid4().hex}",
            user_id=user.user_id,
            title=request.title,
            color=DBEventColor(request.color.value),
            start_date=request.start_date,
            end_date=request.end_date,
            description=request.description,
            created_at=now,
            updated_at=now,
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(
            "event_created",
            event_id=event.id,
            user_id=user.user_id,
            title=event.title,
        )

        return _db_event_to_response(event)

    except Exception as e:
        db.rollback()
        logger.error("create_event_failed", error=str(e), user_id=user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}",
        )


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Get Event",
    description="Get a specific event by ID.",
)
async def get_event(
    event_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EventResponse:
    """
    Get a specific event by ID.

    **Path Parameters:**
    - event_id: The event ID

    **Returns:**
    - Event details
    """
    user = current_user["user"]

    event = db.query(EventTable).filter(
        EventTable.id == event_id,
        EventTable.user_id == user.user_id,
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    return _db_event_to_response(event)


@router.put(
    "/{event_id}",
    response_model=EventResponse,
    summary="Update Event",
    description="Update an existing event.",
)
async def update_event(
    event_id: str,
    request: EventUpdateRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EventResponse:
    """
    Update an existing event.

    **Path Parameters:**
    - event_id: The event ID

    **Request Body:**
    - title: New event title (optional)
    - color: New event color (optional)
    - start_date: New start date (optional)
    - end_date: New end date (optional)
    - description: New description (optional)

    **Returns:**
    - Updated event details
    """
    user = current_user["user"]

    event = db.query(EventTable).filter(
        EventTable.id == event_id,
        EventTable.user_id == user.user_id,
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    try:
        # Update only provided fields
        if request.title is not None:
            event.title = request.title
        if request.color is not None:
            event.color = DBEventColor(request.color.value)
        if request.start_date is not None:
            event.start_date = request.start_date
        if request.end_date is not None:
            event.end_date = request.end_date
        if request.description is not None:
            event.description = request.description

        # Validate dates after update
        if event.end_date < event.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_date must be after or equal to start_date",
            )

        event.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(event)

        logger.info(
            "event_updated",
            event_id=event.id,
            user_id=user.user_id,
        )

        return _db_event_to_response(event)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("update_event_failed", error=str(e), event_id=event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update event: {str(e)}",
        )


@router.delete(
    "/{event_id}",
    response_model=EventDeleteResponse,
    summary="Delete Event",
    description="Delete an event.",
)
async def delete_event(
    event_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EventDeleteResponse:
    """
    Delete an event.

    **Path Parameters:**
    - event_id: The event ID

    **Returns:**
    - Deletion confirmation
    """
    user = current_user["user"]

    event = db.query(EventTable).filter(
        EventTable.id == event_id,
        EventTable.user_id == user.user_id,
    ).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    try:
        db.delete(event)
        db.commit()

        logger.info(
            "event_deleted",
            event_id=event_id,
            user_id=user.user_id,
        )

        return EventDeleteResponse(
            success=True,
            message="Event successfully deleted",
            event_id=event_id,
        )

    except Exception as e:
        db.rollback()
        logger.error("delete_event_failed", error=str(e), event_id=event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete event: {str(e)}",
        )


@router.get(
    "/month/{year}/{month}",
    response_model=EventListResponse,
    summary="Get Events for Month",
    description="Get all events for a specific month.",
)
async def get_events_for_month(
    year: int,
    month: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EventListResponse:
    """
    Get all events for a specific month.

    **Path Parameters:**
    - year: Year (e.g., 2025)
    - month: Month (1-12)

    **Returns:**
    - List of events in that month
    """
    user = current_user["user"]

    if month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be between 1 and 12",
        )

    try:
        # Calculate month start and end
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
        month_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

        # Get events that overlap with the month
        events = db.query(EventTable).filter(
            EventTable.user_id == user.user_id,
            EventTable.start_date <= month_end,
            EventTable.end_date >= month_start,
        ).order_by(EventTable.start_date.asc()).all()

        return EventListResponse(
            events=[_db_event_to_response(e) for e in events],
            total=len(events),
        )

    except Exception as e:
        logger.error("get_events_for_month_failed", error=str(e), user_id=user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve events",
        )
