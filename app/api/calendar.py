from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_credentials
from app.models.schemas import (
    CalendarEvent,
    CreateEventRequest,
    DeleteEventResponse,
    FreeBusyResponse,
    FreeSlot,
    NextMeetingResponse,
    UpdateEventRequest,
)
from app.services.calendar import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


@router.get("/events/today", response_model=list[CalendarEvent])
def get_events_today(
    calendar_id: str = Query("primary", description="Calendar ID"),
    credentials=Depends(get_current_credentials),
) -> list[CalendarEvent]:
    """Return all events for today (calendar day, UTC)."""
    svc = CalendarService(credentials)
    return [CalendarEvent(**e) for e in svc.get_events_today(calendar_id)]


@router.get("/events/week", response_model=list[CalendarEvent])
def get_events_week(
    calendar_id: str = Query("primary", description="Calendar ID"),
    credentials=Depends(get_current_credentials),
) -> list[CalendarEvent]:
    """Return all events for the next 7 days."""
    svc = CalendarService(credentials)
    return [CalendarEvent(**e) for e in svc.get_events_week(calendar_id)]


@router.get("/events/next", response_model=NextMeetingResponse)
def get_next_meeting(
    calendar_id: str = Query("primary", description="Calendar ID"),
    credentials=Depends(get_current_credentials),
) -> NextMeetingResponse:
    """Return the next upcoming event and how many minutes away it is."""
    svc = CalendarService(credentials)
    data = svc.get_time_to_next_meeting(calendar_id)
    event = CalendarEvent(**data["event"]) if data["event"] else None
    return NextMeetingResponse(
        event=event,
        minutes_until=data["minutes_until"],
        message=data["message"],
    )


# ---------------------------------------------------------------------------
# Free / busy
# ---------------------------------------------------------------------------


@router.get("/freebusy", response_model=FreeBusyResponse)
def get_free_slots(
    time_min: str = Query(..., description="Start of interval, ISO-8601 with timezone"),
    time_max: str = Query(..., description="End of interval, ISO-8601 with timezone"),
    calendar_id: str = Query("primary", description="Calendar ID"),
    min_duration: int = Query(30, ge=1, description="Minimum free-slot duration in minutes"),
    credentials=Depends(get_current_credentials),
) -> FreeBusyResponse:
    """Return free time slots of at least *min_duration* minutes in the given interval."""
    svc = CalendarService(credentials)
    slots = svc.get_free_slots(time_min, time_max, min_duration, [calendar_id])
    return FreeBusyResponse(
        time_min=time_min,
        time_max=time_max,
        free_slots=[FreeSlot(**s) for s in slots],
    )


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


@router.post("/events", response_model=CalendarEvent, status_code=201)
def create_event(
    body: CreateEventRequest,
    credentials=Depends(get_current_credentials),
) -> CalendarEvent:
    """Create a new calendar event. Add *recurrence* field to make it recurring."""
    svc = CalendarService(credentials)
    attendees_raw = (
        [{"email": a.email, "optional": a.optional} for a in body.attendees]
        if body.attendees
        else None
    )
    event = svc.create_event(
        calendar_id=body.calendar_id,
        summary=body.summary,
        start=body.start,
        end=body.end,
        timezone=body.timezone,
        description=body.description,
        location=body.location,
        attendees=attendees_raw,
        recurrence=body.recurrence,
    )
    return CalendarEvent(**event)


@router.put("/events/{event_id}", response_model=CalendarEvent)
def update_event(
    event_id: str,
    body: UpdateEventRequest,
    calendar_id: str = Query("primary", description="Calendar ID"),
    credentials=Depends(get_current_credentials),
) -> CalendarEvent:
    """Update an existing event. Only provided fields are changed."""
    svc = CalendarService(credentials)
    attendees_raw = (
        [{"email": a.email, "optional": a.optional} for a in body.attendees]
        if body.attendees is not None
        else None
    )
    event = svc.update_event(
        calendar_id=calendar_id,
        event_id=event_id,
        summary=body.summary,
        description=body.description,
        location=body.location,
        start=body.start,
        end=body.end,
        timezone=body.timezone,
        attendees=attendees_raw,
        recurrence=body.recurrence,
    )
    return CalendarEvent(**event)


@router.delete("/events/{event_id}", response_model=DeleteEventResponse)
def delete_event(
    event_id: str,
    calendar_id: str = Query("primary", description="Calendar ID"),
    credentials=Depends(get_current_credentials),
) -> DeleteEventResponse:
    """Delete a calendar event permanently."""
    svc = CalendarService(credentials)
    svc.delete_event(calendar_id, event_id)
    return DeleteEventResponse(message=f"Event '{event_id}' deleted")
