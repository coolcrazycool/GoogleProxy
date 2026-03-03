from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from app.services.calendar import CalendarService, _build_rrule, _format_event
from app.models.schemas import RecurrenceRule
from tests.conftest import auth_headers, FAKE_INTERNAL_TOKEN


# ---------------------------------------------------------------------------
# Helpers / shared data
# ---------------------------------------------------------------------------

NOW = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

FAKE_EVENT_RAW = {
    "id": "event-id-123",
    "summary": "Team Standup",
    "description": "Daily sync",
    "location": "Zoom",
    "start": {"dateTime": "2024-06-15T10:00:00+00:00"},
    "end": {"dateTime": "2024-06-15T10:30:00+00:00"},
    "status": "confirmed",
    "htmlLink": "https://calendar.google.com/event?id=event-id-123",
    "attendees": [{"email": "alice@example.com"}],
    "recurrence": None,
    "creator": {"email": "me@example.com"},
}

FAKE_EVENT_FORMATTED = {
    "id": "event-id-123",
    "summary": "Team Standup",
    "description": "Daily sync",
    "location": "Zoom",
    "start": "2024-06-15T10:00:00+00:00",
    "end": "2024-06-15T10:30:00+00:00",
    "status": "confirmed",
    "html_link": "https://calendar.google.com/event?id=event-id-123",
    "attendees": [{"email": "alice@example.com"}],
    "recurrence": None,
    "creator": {"email": "me@example.com"},
}


def make_calendar_service() -> tuple[CalendarService, MagicMock]:
    """Return a CalendarService with a mocked internal _service."""
    creds = MagicMock()
    with patch("app.services.calendar.build") as mock_build:
        svc = CalendarService(creds)
        return svc, mock_build.return_value


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


class TestBuildRrule:
    def test_basic_weekly(self):
        rule = RecurrenceRule(frequency="WEEKLY", interval=1)
        assert _build_rrule(rule) == "FREQ=WEEKLY"

    def test_with_interval(self):
        rule = RecurrenceRule(frequency="DAILY", interval=2)
        assert _build_rrule(rule) == "FREQ=DAILY;INTERVAL=2"

    def test_with_count(self):
        rule = RecurrenceRule(frequency="MONTHLY", interval=1, count=6)
        assert _build_rrule(rule) == "FREQ=MONTHLY;COUNT=6"

    def test_with_until(self):
        rule = RecurrenceRule(frequency="YEARLY", interval=1, until="20251231T235959Z")
        assert _build_rrule(rule) == "FREQ=YEARLY;UNTIL=20251231T235959Z"

    def test_with_by_day(self):
        rule = RecurrenceRule(frequency="WEEKLY", interval=1, by_day=["MO", "WE", "FR"])
        assert _build_rrule(rule) == "FREQ=WEEKLY;BYDAY=MO,WE,FR"

    def test_full(self):
        rule = RecurrenceRule(
            frequency="WEEKLY", interval=2, count=10, by_day=["TU", "TH"]
        )
        assert _build_rrule(rule) == "FREQ=WEEKLY;INTERVAL=2;COUNT=10;BYDAY=TU,TH"


class TestFormatEvent:
    def test_formats_correctly(self):
        result = _format_event(FAKE_EVENT_RAW)
        assert result == FAKE_EVENT_FORMATTED

    def test_missing_optional_fields(self):
        minimal = {
            "id": "xyz",
            "start": {"dateTime": "2024-01-01T09:00:00+00:00"},
            "end": {"dateTime": "2024-01-01T10:00:00+00:00"},
        }
        result = _format_event(minimal)
        assert result["id"] == "xyz"
        assert result["summary"] is None
        assert result["attendees"] is None

    def test_all_day_event(self):
        raw = {
            "id": "allday",
            "start": {"date": "2024-06-15"},
            "end": {"date": "2024-06-16"},
        }
        result = _format_event(raw)
        assert result["start"] == "2024-06-15"
        assert result["end"] == "2024-06-16"


# ---------------------------------------------------------------------------
# Unit tests: CalendarService
# ---------------------------------------------------------------------------


class TestGetEventsToday:
    def test_returns_formatted_events(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": [FAKE_EVENT_RAW]
        }
        events = svc.get_events_today()
        assert len(events) == 1
        assert events[0]["id"] == "event-id-123"

    def test_empty_calendar(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": []
        }
        assert svc.get_events_today() == []

    def test_passes_correct_calendar_id(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": []
        }
        svc.get_events_today("work@example.com")
        call_kwargs = mock_google.events.return_value.list.call_args.kwargs
        assert call_kwargs["calendarId"] == "work@example.com"


class TestGetEventsWeek:
    def test_returns_events(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": [FAKE_EVENT_RAW, FAKE_EVENT_RAW]
        }
        events = svc.get_events_week()
        assert len(events) == 2

    def test_time_range_spans_7_days(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": []
        }
        svc.get_events_week()
        call_kwargs = mock_google.events.return_value.list.call_args.kwargs
        time_min = datetime.fromisoformat(call_kwargs["timeMin"].replace("Z", "+00:00"))
        time_max = datetime.fromisoformat(call_kwargs["timeMax"].replace("Z", "+00:00"))
        assert (time_max - time_min).days >= 7


class TestGetFreeSlots:
    def test_no_busy_time(self):
        svc, mock_google = make_calendar_service()
        mock_google.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {"primary": {"busy": []}}
        }
        slots = svc.get_free_slots(
            "2024-06-15T09:00:00+00:00",
            "2024-06-15T18:00:00+00:00",
            min_duration=30,
        )
        assert len(slots) == 1
        assert slots[0]["duration_minutes"] == 540  # 9 hours

    def test_with_busy_block_in_middle(self):
        svc, mock_google = make_calendar_service()
        mock_google.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2024-06-15T12:00:00+00:00",
                            "end": "2024-06-15T13:00:00+00:00",
                        }
                    ]
                }
            }
        }
        slots = svc.get_free_slots(
            "2024-06-15T09:00:00+00:00",
            "2024-06-15T18:00:00+00:00",
            min_duration=30,
        )
        assert len(slots) == 2
        assert slots[0]["duration_minutes"] == 180  # 09:00-12:00
        assert slots[1]["duration_minutes"] == 300  # 13:00-18:00

    def test_min_duration_filters_short_slots(self):
        svc, mock_google = make_calendar_service()
        mock_google.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2024-06-15T09:20:00+00:00",
                            "end": "2024-06-15T18:00:00+00:00",
                        }
                    ]
                }
            }
        }
        # Only 20-minute gap at start — should be filtered when min_duration=30
        slots = svc.get_free_slots(
            "2024-06-15T09:00:00+00:00",
            "2024-06-15T18:00:00+00:00",
            min_duration=30,
        )
        assert slots == []

    def test_overlapping_busy_blocks_are_merged(self):
        svc, mock_google = make_calendar_service()
        mock_google.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2024-06-15T10:00:00+00:00",
                            "end": "2024-06-15T11:30:00+00:00",
                        },
                        {
                            "start": "2024-06-15T11:00:00+00:00",
                            "end": "2024-06-15T12:00:00+00:00",
                        },
                    ]
                }
            }
        }
        slots = svc.get_free_slots(
            "2024-06-15T09:00:00+00:00",
            "2024-06-15T18:00:00+00:00",
            min_duration=30,
        )
        assert len(slots) == 2


class TestGetTimeToNextMeeting:
    def test_next_meeting_found(self):
        svc, mock_google = make_calendar_service()
        future_start = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
        future_end = (datetime.now(timezone.utc) + timedelta(minutes=75)).isoformat()
        raw = {
            **FAKE_EVENT_RAW,
            "start": {"dateTime": future_start},
            "end": {"dateTime": future_end},
        }
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": [raw]
        }
        result = svc.get_time_to_next_meeting()
        assert result["event"] is not None
        assert 40 <= result["minutes_until"] <= 50
        assert "мин." in result["message"]

    def test_no_upcoming_meeting(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.list.return_value.execute.return_value = {
            "items": []
        }
        result = svc.get_time_to_next_meeting()
        assert result["event"] is None
        assert result["minutes_until"] is None


class TestCreateEvent:
    def test_basic_create(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.insert.return_value.execute.return_value = (
            FAKE_EVENT_RAW
        )
        result = svc.create_event(
            calendar_id="primary",
            summary="Meeting",
            start="2024-06-15T10:00:00+00:00",
            end="2024-06-15T11:00:00+00:00",
        )
        assert result["id"] == "event-id-123"
        mock_google.events.return_value.insert.assert_called_once()

    def test_create_with_recurrence(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.insert.return_value.execute.return_value = (
            FAKE_EVENT_RAW
        )
        rule = RecurrenceRule(frequency="WEEKLY", interval=1, by_day=["MO"])
        svc.create_event(
            calendar_id="primary",
            summary="Weekly",
            start="2024-06-15T10:00:00+00:00",
            end="2024-06-15T11:00:00+00:00",
            recurrence=rule,
        )
        body = mock_google.events.return_value.insert.call_args.kwargs["body"]
        assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]

    def test_create_with_attendees(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.insert.return_value.execute.return_value = (
            FAKE_EVENT_RAW
        )
        svc.create_event(
            calendar_id="primary",
            summary="Meeting",
            start="2024-06-15T10:00:00+00:00",
            end="2024-06-15T11:00:00+00:00",
            attendees=[{"email": "alice@example.com", "optional": False}],
        )
        body = mock_google.events.return_value.insert.call_args.kwargs["body"]
        assert body["attendees"] == [{"email": "alice@example.com", "optional": False}]


class TestUpdateEvent:
    def test_update_summary(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.get.return_value.execute.return_value = dict(
            FAKE_EVENT_RAW
        )
        mock_google.events.return_value.update.return_value.execute.return_value = (
            FAKE_EVENT_RAW
        )
        result = svc.update_event(
            calendar_id="primary",
            event_id="event-id-123",
            summary="New Title",
        )
        update_body = mock_google.events.return_value.update.call_args.kwargs["body"]
        assert update_body["summary"] == "New Title"

    def test_update_with_recurrence(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.get.return_value.execute.return_value = dict(
            FAKE_EVENT_RAW
        )
        mock_google.events.return_value.update.return_value.execute.return_value = (
            FAKE_EVENT_RAW
        )
        rule = RecurrenceRule(frequency="DAILY", interval=1, count=5)
        svc.update_event(
            calendar_id="primary",
            event_id="event-id-123",
            recurrence=rule,
        )
        update_body = mock_google.events.return_value.update.call_args.kwargs["body"]
        assert update_body["recurrence"] == ["RRULE:FREQ=DAILY;COUNT=5"]


class TestDeleteEvent:
    def test_delete_called(self):
        svc, mock_google = make_calendar_service()
        mock_google.events.return_value.delete.return_value.execute.return_value = None
        svc.delete_event("primary", "event-id-123")
        mock_google.events.return_value.delete.assert_called_once_with(
            calendarId="primary", eventId="event-id-123"
        )


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCalendarEndpoints:
    async def test_get_events_today(self, client):
        with patch(
            "app.api.calendar.CalendarService.get_events_today",
            return_value=[FAKE_EVENT_FORMATTED],
        ):
            resp = await client.get(
                "/calendar/events/today", headers=auth_headers()
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["id"] == "event-id-123"

    async def test_get_events_week(self, client):
        with patch(
            "app.api.calendar.CalendarService.get_events_week",
            return_value=[FAKE_EVENT_FORMATTED],
        ):
            resp = await client.get(
                "/calendar/events/week", headers=auth_headers()
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_next_meeting(self, client):
        with patch(
            "app.api.calendar.CalendarService.get_time_to_next_meeting",
            return_value={
                "event": FAKE_EVENT_FORMATTED,
                "minutes_until": 30,
                "message": "Следующая встреча через 30 мин.",
            },
        ):
            resp = await client.get(
                "/calendar/events/next", headers=auth_headers()
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["minutes_until"] == 30
        assert "встреча" in body["message"]

    async def test_get_next_meeting_no_events(self, client):
        with patch(
            "app.api.calendar.CalendarService.get_time_to_next_meeting",
            return_value={
                "event": None,
                "minutes_until": None,
                "message": "Нет предстоящих встреч в ближайшие 24 часа",
            },
        ):
            resp = await client.get(
                "/calendar/events/next", headers=auth_headers()
            )
        assert resp.status_code == 200
        assert resp.json()["event"] is None

    async def test_get_free_slots(self, client):
        with patch(
            "app.api.calendar.CalendarService.get_free_slots",
            return_value=[
                {
                    "start": "2024-06-15T09:00:00+00:00",
                    "end": "2024-06-15T12:00:00+00:00",
                    "duration_minutes": 180,
                }
            ],
        ):
            resp = await client.get(
                "/calendar/freebusy",
                params={
                    "time_min": "2024-06-15T09:00:00+00:00",
                    "time_max": "2024-06-15T18:00:00+00:00",
                },
                headers=auth_headers(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["free_slots"]) == 1
        assert body["free_slots"][0]["duration_minutes"] == 180

    async def test_create_event(self, client):
        with patch(
            "app.api.calendar.CalendarService.create_event",
            return_value=FAKE_EVENT_FORMATTED,
        ):
            resp = await client.post(
                "/calendar/events",
                json={
                    "summary": "Team Standup",
                    "start": "2024-06-15T10:00:00+00:00",
                    "end": "2024-06-15T10:30:00+00:00",
                },
                headers=auth_headers(),
            )
        assert resp.status_code == 201
        assert resp.json()["id"] == "event-id-123"

    async def test_create_recurring_event(self, client):
        with patch(
            "app.api.calendar.CalendarService.create_event",
            return_value=FAKE_EVENT_FORMATTED,
        ) as mock_create:
            resp = await client.post(
                "/calendar/events",
                json={
                    "summary": "Weekly Sync",
                    "start": "2024-06-15T10:00:00+00:00",
                    "end": "2024-06-15T11:00:00+00:00",
                    "recurrence": {
                        "frequency": "WEEKLY",
                        "interval": 1,
                        "by_day": ["MO", "WE"],
                        "count": 8,
                    },
                },
                headers=auth_headers(),
            )
        assert resp.status_code == 201
        # Verify the recurrence rule was passed
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["recurrence"] is not None
        assert call_kwargs["recurrence"].frequency == "WEEKLY"

    async def test_update_event(self, client):
        with patch(
            "app.api.calendar.CalendarService.update_event",
            return_value=FAKE_EVENT_FORMATTED,
        ):
            resp = await client.put(
                "/calendar/events/event-id-123",
                json={"summary": "Updated Title"},
                headers=auth_headers(),
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "event-id-123"

    async def test_delete_event(self, client):
        with patch(
            "app.api.calendar.CalendarService.delete_event",
            return_value=None,
        ):
            resp = await client.delete(
                "/calendar/events/event-id-123",
                headers=auth_headers(),
            )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"]

    async def test_unauthorized_without_token(self, client):
        resp = await client.get("/calendar/events/today")
        assert resp.status_code == 401
