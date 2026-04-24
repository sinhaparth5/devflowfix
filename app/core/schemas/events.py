# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Event Schemas

Pydantic models for calendar event API requests and responses.
"""

from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventColor(str, Enum):
    """Event color options for calendar display."""
    DANGER = "danger"
    PRIMARY = "primary"
    SUCCESS = "success"
    WARNING = "warning"


class EventCreateRequest(BaseModel):
    """Request schema for creating a new event."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Team Meeting",
                "color": "primary",
                "start_date": "2025-01-24T09:00:00Z",
                "end_date": "2025-01-24T10:00:00Z",
                "description": "Weekly team sync",
            }
        }
    )

    title: str = Field(..., min_length=1, max_length=255, description="Event title")
    color: EventColor = Field(default=EventColor.PRIMARY, description="Event color for calendar display")
    start_date: datetime = Field(..., description="Event start date")
    end_date: datetime = Field(..., description="Event end date")
    description: Optional[str] = Field(default=None, max_length=2000, description="Optional event description")

    @field_validator('end_date')
    @classmethod
    def end_date_must_be_after_start(cls, v, info):
        """Validate that end_date is after or equal to start_date."""
        if 'start_date' in info.data and v < info.data['start_date']:
            raise ValueError('end_date must be after or equal to start_date')
        return v

class EventUpdateRequest(BaseModel):
    """Request schema for updating an event."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Updated Meeting Title",
                "color": "success",
            }
        }
    )

    title: Optional[str] = Field(default=None, min_length=1, max_length=255, description="Event title")
    color: Optional[EventColor] = Field(default=None, description="Event color")
    start_date: Optional[datetime] = Field(default=None, description="Event start date")
    end_date: Optional[datetime] = Field(default=None, description="Event end date")
    description: Optional[str] = Field(default=None, max_length=2000, description="Event description")

class EventResponse(BaseModel):
    """Response schema for a single event."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "evt_abc123",
                "user_id": "user_xyz",
                "title": "Team Meeting",
                "color": "primary",
                "start_date": "2025-01-24T09:00:00Z",
                "end_date": "2025-01-24T10:00:00Z",
                "description": "Weekly team sync",
                "created_at": "2025-01-23T12:00:00Z",
                "updated_at": "2025-01-23T12:00:00Z",
            }
        },
    )

    id: str = Field(..., description="Event ID")
    user_id: str = Field(..., description="Owner user ID")
    title: str = Field(..., description="Event title")
    color: EventColor = Field(..., description="Event color")
    start_date: datetime = Field(..., description="Event start date")
    end_date: datetime = Field(..., description="Event end date")
    description: Optional[str] = Field(default=None, description="Event description")
    created_at: datetime = Field(..., description="When the event was created")
    updated_at: datetime = Field(..., description="When the event was last updated")

class EventListResponse(BaseModel):
    """Response schema for a list of events."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "events": [
                    {
                        "id": "evt_abc123",
                        "user_id": "user_xyz",
                        "title": "Team Meeting",
                        "color": "primary",
                        "start_date": "2025-01-24T09:00:00Z",
                        "end_date": "2025-01-24T10:00:00Z",
                        "description": "Weekly team sync",
                        "created_at": "2025-01-23T12:00:00Z",
                        "updated_at": "2025-01-23T12:00:00Z",
                    }
                ],
                "total": 1,
            }
        }
    )

    events: List[EventResponse] = Field(..., description="List of events")
    total: int = Field(..., description="Total number of events")

class EventDeleteResponse(BaseModel):
    """Response schema for event deletion."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Event successfully deleted",
                "event_id": "evt_abc123",
            }
        }
    )

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Status message")
    event_id: str = Field(..., description="Deleted event ID")

