from datetime import datetime

from pydantic import BaseModel, Field


class CalendarEvent(BaseModel):
    id: str
    summary: str
    start: datetime
    end: datetime
    description: str | None = None
    attendees: list[str] = Field(default_factory=list)


class CreateEventRequest(BaseModel):
    summary: str
    start: datetime
    end: datetime
    description: str | None = None
    attendees: list[str] = Field(default_factory=list)


class UpdateEventRequest(BaseModel):
    summary: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None


class FreeSlot(BaseModel):
    start: datetime
    end: datetime
