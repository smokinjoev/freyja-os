from __future__ import annotations

import json
from datetime import UTC, datetime, time

import pytest

from freyja.calendar import (
    AvailabilityRule,
    CalendarEvent,
    CalendarMember,
    CalendarPreference,
    CalendarService,
    AppleCalendarProvider,
    GoogleCalendarProvider,
    InMemoryCalendarProvider,
)
from freyja.identity import Alias, IdentityService, Person


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
async def test_calendar_resolves_person_aliases(family: list[CalendarMember]) -> None:
    provider = InMemoryCalendarProvider(
        [CalendarEvent("work", "joe-cal", "Work block", _dt(10), _dt(11), attendee_ids=("joe",))]
    )
    identity_service = IdentityService(
        people=[
            Person(person_id="joe", display_name="Joe", aliases=(Alias("Dad"),)),
            Person(person_id="beth", display_name="Beth"),
        ]
    )
    service = CalendarService(providers={"memory": provider}, members=family, identity_service=identity_service)

    result = await service.free_busy(start=_dt(9), end=_dt(12), member_ids=["Dad"])

    assert list(result["busy"]) == ["joe"]
    assert len(result["busy"]["joe"]) == 1


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


@pytest.mark.asyncio
async def test_apple_provider_lists_events_through_local_bridge() -> None:
    calls: list[tuple[str, dict]] = []

    async def runner(args: list[str], timeout: float) -> str:
        calls.append((args[-2], json.loads(args[-1])))
        return (
            '{"ok":true,"events":[{'
            '"event_id":"apple-1",'
            '"calendar_id":"Family",'
            '"title":"Dinner",'
            '"start":"2026-08-03T22:00:00.000Z",'
            '"end":"2026-08-03T23:00:00.000Z",'
            '"location":"Home",'
            '"description":null,'
            '"attendee_ids":[],'
            '"metadata":{"apple_calendar_id":"cal-1"}'
            "}]}"
        )

    provider = AppleCalendarProvider(
        default_calendar_name="iCloud::Family",
        calendar_aliases={"joe": "iCloud::Family", "beth": "iCloud::Family"},
        runner=runner,
    )

    events = await provider.list_events(calendar_ids=["joe", "beth"], start=_dt(17), end=_dt(20))

    assert calls == [
        (
            "list",
            {
                "calendar_selectors": ["iCloud::Family"],
                "start": _dt(17).isoformat(),
                "end": _dt(20).isoformat(),
            },
        )
    ]
    assert len(events) == 1
    assert events[0].event_id == "apple-1"
    assert events[0].calendar_id == "Family"
    assert events[0].provider == "apple"


@pytest.mark.asyncio
async def test_apple_provider_creates_events_on_mapped_family_calendar() -> None:
    calls: list[tuple[str, dict]] = []

    async def runner(args: list[str], timeout: float) -> str:
        payload = json.loads(args[-1])
        calls.append((args[-2], payload))
        return (
            '{"ok":true,"event":{'
            '"event_id":"created-1",'
            '"calendar_id":"Family",'
            '"title":"Family dinner",'
            '"start":"2026-08-03T22:00:00.000Z",'
            '"end":"2026-08-03T23:00:00.000Z",'
            '"location":null,'
            '"description":"approved by Director",'
            '"attendee_ids":["joe"],'
            '"metadata":{}'
            "}}"
        )

    provider = AppleCalendarProvider(
        default_calendar_name="iCloud::Family",
        calendar_aliases={"joe": "iCloud::Family"},
        runner=runner,
    )
    event = CalendarEvent(
        "pending",
        "joe",
        "Family dinner",
        _dt(18),
        _dt(19),
        attendee_ids=("joe",),
        description="approved by Director",
    )

    created = await provider.create_event(event)

    assert calls[0][0] == "create"
    assert calls[0][1]["calendar_selector"] == "iCloud::Family"
    assert calls[0][1]["title"] == "Family dinner"
    assert calls[0][1]["attendee_ids"] == ["joe"]
    assert created.event_id == "created-1"
    assert created.provider == "apple"
