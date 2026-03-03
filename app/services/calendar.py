from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.models.schemas import RecurrenceRule


def _build_rrule(rule: RecurrenceRule) -> str:
    """Convert a RecurrenceRule model into an RFC 5545 RRULE string."""
    parts = [f"FREQ={rule.frequency.upper()}"]
    if rule.interval > 1:
        parts.append(f"INTERVAL={rule.interval}")
    if rule.count is not None:
        parts.append(f"COUNT={rule.count}")
    elif rule.until is not None:
        parts.append(f"UNTIL={rule.until}")
    if rule.by_day:
        parts.append(f"BYDAY={','.join(d.upper() for d in rule.by_day)}")
    return ";".join(parts)


def _normalize_dt(value: str) -> str:
    """Replace trailing Z with +00:00 so fromisoformat() works on Python < 3.11."""
    return value.replace("Z", "+00:00")


def _extract_event_time(event: dict, key: str) -> str:
    """Return ISO-8601 string from event start/end dict (dateTime or date)."""
    dt_obj = event.get(key, {})
    return dt_obj.get("dateTime") or dt_obj.get("date", "")


def _format_event(raw: dict) -> dict:
    """Flatten a raw Google Calendar event to our CalendarEvent schema dict."""
    return {
        "id": raw.get("id", ""),
        "summary": raw.get("summary"),
        "description": raw.get("description"),
        "location": raw.get("location"),
        "start": _extract_event_time(raw, "start"),
        "end": _extract_event_time(raw, "end"),
        "status": raw.get("status"),
        "html_link": raw.get("htmlLink"),
        "attendees": raw.get("attendees"),
        "recurrence": raw.get("recurrence"),
        "creator": raw.get("creator"),
    }


class CalendarService:
    """Wraps Google Calendar API v3."""

    def __init__(self, credentials) -> None:
        self._service = build("calendar", "v3", credentials=credentials)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_events_today(self, calendar_id: str = "primary") -> list[dict]:
        """Return all events for the current calendar day (UTC)."""
        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        return self._list_events(calendar_id, time_min, time_max)

    def get_events_week(self, calendar_id: str = "primary") -> list[dict]:
        """Return all events for the next 7 days starting from now."""
        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = (now + timedelta(days=7)).replace(
            hour=23, minute=59, second=59, microsecond=0
        ).isoformat()
        return self._list_events(calendar_id, time_min, time_max)

    def _list_events(
        self, calendar_id: str, time_min: str, time_max: str
    ) -> list[dict]:
        try:
            result = (
                self._service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc

        return [_format_event(e) for e in result.get("items", [])]

    # ------------------------------------------------------------------
    # Free / busy
    # ------------------------------------------------------------------

    def get_free_slots(
        self,
        time_min: str,
        time_max: str,
        min_duration: int = 30,
        calendar_ids: list[str] | None = None,
    ) -> list[dict]:
        """Return free time slots of at least *min_duration* minutes."""
        if calendar_ids is None:
            calendar_ids = ["primary"]

        try:
            result = (
                self._service.freebusy()
                .query(
                    body={
                        "timeMin": time_min,
                        "timeMax": time_max,
                        "items": [{"id": cid} for cid in calendar_ids],
                    }
                )
                .execute()
            )
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc

        # Collect and merge busy intervals
        busy: list[dict] = []
        for cid in calendar_ids:
            busy.extend(result.get("calendars", {}).get(cid, {}).get("busy", []))

        busy.sort(key=lambda x: x["start"])
        merged: list[dict] = []
        for period in busy:
            if merged and period["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], period["end"])
            else:
                merged.append({"start": period["start"], "end": period["end"]})

        # Walk gaps between busy blocks
        free_slots: list[dict] = []
        cursor = time_min
        for busy_block in merged:
            if cursor < busy_block["start"]:
                slot_start = datetime.fromisoformat(_normalize_dt(cursor))
                slot_end = datetime.fromisoformat(_normalize_dt(busy_block["start"]))
                duration = int((slot_end - slot_start).total_seconds() / 60)
                if duration >= min_duration:
                    free_slots.append(
                        {
                            "start": cursor,
                            "end": busy_block["start"],
                            "duration_minutes": duration,
                        }
                    )
            cursor = busy_block["end"]

        # Gap after last busy block
        if cursor < time_max:
            slot_start = datetime.fromisoformat(_normalize_dt(cursor))
            slot_end = datetime.fromisoformat(_normalize_dt(time_max))
            duration = int((slot_end - slot_start).total_seconds() / 60)
            if duration >= min_duration:
                free_slots.append(
                    {"start": cursor, "end": time_max, "duration_minutes": duration}
                )

        return free_slots

    # ------------------------------------------------------------------
    # Next meeting
    # ------------------------------------------------------------------

    def get_time_to_next_meeting(self, calendar_id: str = "primary") -> dict:
        """Return the nearest upcoming event and how many minutes away it is."""
        now = datetime.now(timezone.utc)
        look_ahead = now + timedelta(hours=24)

        try:
            result = (
                self._service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now.isoformat(),
                    timeMax=look_ahead.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=1,
                )
                .execute()
            )
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc

        items = result.get("items", [])
        if not items:
            return {
                "event": None,
                "minutes_until": None,
                "message": "Нет предстоящих встреч в ближайшие 24 часа",
            }

        raw = items[0]
        start_str = _extract_event_time(raw, "start")
        start_dt = datetime.fromisoformat(_normalize_dt(start_str))
        minutes_until = max(0, int((start_dt - now).total_seconds() / 60))

        return {
            "event": _format_event(raw),
            "minutes_until": minutes_until,
            "message": f"Следующая встреча через {minutes_until} мин.",
        }

    # ------------------------------------------------------------------
    # Create / update / delete
    # ------------------------------------------------------------------

    def create_event(self, calendar_id: str, summary: str, start: str, end: str,
                     timezone: str = "UTC", description: str | None = None,
                     location: str | None = None,
                     attendees: list[dict] | None = None,
                     recurrence: RecurrenceRule | None = None) -> dict:
        """Insert a new event into the calendar."""
        body: dict = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": timezone},
            "end": {"dateTime": end, "timeZone": timezone},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = attendees
        if recurrence:
            body["recurrence"] = [f"RRULE:{_build_rrule(recurrence)}"]

        try:
            raw = (
                self._service.events()
                .insert(calendarId=calendar_id, body=body)
                .execute()
            )
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc

        return _format_event(raw)

    def update_event(self, calendar_id: str, event_id: str,
                     summary: str | None = None,
                     description: str | None = None,
                     location: str | None = None,
                     start: str | None = None,
                     end: str | None = None,
                     timezone: str | None = None,
                     attendees: list[dict] | None = None,
                     recurrence: RecurrenceRule | None = None) -> dict:
        """Patch an existing event with provided fields."""
        try:
            existing = (
                self._service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc

        if summary is not None:
            existing["summary"] = summary
        if description is not None:
            existing["description"] = description
        if location is not None:
            existing["location"] = location
        if start is not None:
            tz = timezone or existing.get("start", {}).get("timeZone", "UTC")
            existing["start"] = {"dateTime": start, "timeZone": tz}
        if end is not None:
            tz = timezone or existing.get("end", {}).get("timeZone", "UTC")
            existing["end"] = {"dateTime": end, "timeZone": tz}
        if attendees is not None:
            existing["attendees"] = attendees
        if recurrence is not None:
            existing["recurrence"] = [f"RRULE:{_build_rrule(recurrence)}"]

        try:
            raw = (
                self._service.events()
                .update(calendarId=calendar_id, eventId=event_id, body=existing)
                .execute()
            )
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc

        return _format_event(raw)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Permanently delete a calendar event."""
        try:
            self._service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Calendar API error: {exc.reason}",
            ) from exc
