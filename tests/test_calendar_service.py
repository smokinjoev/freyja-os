from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from freyja.calendar import (
    AvailabilityRule,
    CalendarEvent,
    CalendarMember,
    CalendarPreference,
    CalendarService,
    GoogleCalendarProvider,
    InMemoryCalendarProvider,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 3, hour, minute, tzinfo=UTC)


@pytest.fixture
def family() -> list[CalendarMember]:
    return [
        CalendarMember(
            member_id="joe",
            display_name="Joe",
            calendar_ids=("joe-cal",),
            availability_rules=(AvailabilityRule(days=(0,), start_time=time(8), end_time=time(17)),),
            preferred_meeting_windows=(AvailabilityRule(days=(0,), start_time=time(8), end_time=time(12), label="mornings"),),
            preferences=(CalendarPreference("prefers mornings", 2),),
        ),
        CalendarMember(
            member_id="beth",
            display_name="Beth",
            calendar_ids=("beth-cal",),
            availability_rules=(AvailabilityRule(days=(0,), start_time=time(9), end_time=time(17)),),
            travel_buffer_minutes=15,
        ),
    ]


@pytest.mark.asyncio
async def test_find_time_ranks_conflict_free_family_windows(family: list[CalendarMember]) -> None:
    provider = InMemoryCalendarProvider(
        [
            CalendarEvent("soccer", "joe-cal", "Soccer", _dt(9), _dt(10), attendee_ids=("joe",)),
            CalendarEvent("dentist", "beth-cal", "Dentist", _dt(13), _dt(14), attendee_ids=("beth",)),
        ]
    )
    service = CalendarService(providers={"memory": provider}, members=family)

    options = await service.find_time(
        start=_dt(8),
        end=_dt(17),
        duration_minutes=60,
        member_ids=["joe", "beth"],
        memory_preferences=["Joe prefers mornings."],
        limit=3,
    )

    assert options
    assert all(option.window.start.hour != 9 for option in options)
    assert options[0].window.start.hour < 12
    assert "Joe prefers mornings." in options[0].preference_matches


@pytest.mark.asyncio
async def test_free_busy_groups_busy_events_by_family_member(family: list[CalendarMember]) -> None:
    provider = InMemoryCalendarProvider(
        [CalendarEvent("school", "joe-cal", "School pickup", _dt(15), _dt(16), attendee_ids=("joe",))]
    )
    service = CalendarService(providers={"memory": provider}, members=family)

    result = await service.free_busy(start=_dt(14), end=_dt(17), member_ids=["joe", "beth"])

    assert len(result["busy"]["joe"]) == 1
    assert result["busy"]["beth"] == []


@pytest.mark.asyncio
async def test_move_event_if_conflict_uses_ranked_option(family: list[CalendarMember]) -> None:
    provider = InMemoryCalendarProvider(
        [CalendarEvent("dinner", "joe-cal", "Dinner", _dt(18), _dt(19), attendee_ids=("joe", "beth"))]
    )
    service = CalendarService(providers={"memory": provider}, members=family)

    result = await service.move_event_if_conflict(
        event_id="dinner",
        search_start=_dt(17),
        search_end=_dt(21),
        duration_minutes=60,
        member_ids=["joe", "beth"],
        memory_preferences=["Family dinners after 6 PM."],
    )

    assert result["moved"] is True
    assert result["event"]["event_id"] == "dinner"
    assert result["selected_option"]["window"]["start"].startswith("2026-08-03T19:30")


@pytest.mark.asyncio
async def test_google_provider_plugs_into_service_without_live_api(family: list[CalendarMember]) -> None:
    provider = GoogleCalendarProvider(
        [CalendarEvent("google-1", "joe-cal", "Google event", _dt(11), _dt(12), attendee_ids=("joe",))]
    )
    service = CalendarService(providers={"google": provider}, members=family)

    events = await service.search_events(query="google", start=_dt(10), end=_dt(13), member_ids=["joe"])

    assert len(events) == 1
    assert events[0].provider == "google"
