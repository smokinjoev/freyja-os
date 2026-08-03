from __future__ import annotations

from datetime import UTC, datetime

import pytest

from freyja.calendar import CalendarEvent, CalendarMember, CalendarService, InMemoryCalendarProvider
from freyja.tools.calendar import register_calendar_tools, set_calendar_service
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


def _dt(hour: int) -> datetime:
    return datetime(2026, 8, 3, hour, tzinfo=UTC)


@pytest.fixture
def registry() -> ToolRegistry:
    registry = ToolRegistry(audit_enabled=False)
    register_calendar_tools(registry)
    yield registry
    set_calendar_service(None)


@pytest.fixture
def service() -> CalendarService:
    provider = InMemoryCalendarProvider(
        [CalendarEvent("event-1", "joe", "Soccer", _dt(9), _dt(10), attendee_ids=("joe",))]
    )
    service = CalendarService(
        providers={"memory": provider},
        members=[CalendarMember(member_id="joe", display_name="Joe", calendar_ids=("joe",))],
    )
    set_calendar_service(service)
    return service


@pytest.mark.asyncio
async def test_calendar_list_events_tool_uses_service(registry: ToolRegistry, service: CalendarService) -> None:
    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="calendar_list_events",
            arguments={
                "start": "2026-08-03T00:00:00+00:00",
                "end": "2026-08-04T00:00:00+00:00",
                "member_ids": ["joe"],
            },
        )
    )

    assert result.success is True
    assert result.output["count"] == 1
    assert result.output["events"][0]["title"] == "Soccer"


@pytest.mark.asyncio
async def test_calendar_find_time_tool_returns_ranked_options(registry: ToolRegistry, service: CalendarService) -> None:
    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="calendar_find_time",
            arguments={
                "start": "2026-08-03T08:00:00+00:00",
                "end": "2026-08-03T12:00:00+00:00",
                "duration_minutes": 60,
                "member_ids": ["joe"],
                "memory_preferences": ["Joe prefers mornings."],
            },
        )
    )

    assert result.success is True
    assert result.output["count"] > 0
    assert result.output["options"][0]["preference_matches"] == ["Joe prefers mornings."]


@pytest.mark.asyncio
async def test_calendar_create_modify_delete_tools(registry: ToolRegistry, service: CalendarService) -> None:
    created = await registry.execute(
        ToolExecutionRequest(
            tool_name="calendar_create_event",
            arguments={
                "title": "Family dinner",
                "start": "2026-08-03T18:00:00+00:00",
                "end": "2026-08-03T19:00:00+00:00",
                "member_ids": ["joe"],
            },
        )
    )

    assert created.success is True
    event_id = created.output["event"]["event_id"]

    modified = await registry.execute(
        ToolExecutionRequest(
            tool_name="calendar_modify_event",
            arguments={"event_id": event_id, "updates": {"title": "Late dinner"}},
        )
    )
    deleted = await registry.execute(
        ToolExecutionRequest(tool_name="calendar_delete_event", arguments={"event_id": event_id})
    )

    assert modified.output["event"]["title"] == "Late dinner"
    assert deleted.output["deleted"] is True
