from __future__ import annotations

from dataclasses import dataclass

from freyja import core


@dataclass
class FakeCalendarEvent:
    event_id: str
    title: str

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "title": self.title}


class FakeCalendarService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def list_events(self, **kwargs) -> list[FakeCalendarEvent]:
        self.calls.append(kwargs)
        return [FakeCalendarEvent("event-1", "Basement cleanup")]


async def test_freyja6_core_calendar_list_events_dispatches_to_calendar_service(monkeypatch) -> None:
    service = FakeCalendarService()
    monkeypatch.setattr(core, "get_calendar_service", lambda: service)

    result = await core.call_tool(
        "calendar.list_events",
        {
            "start": "2026-09-19T00:00:00+00:00",
            "end": "2026-09-20T00:00:00+00:00",
            "calendar_ids": ["family-redacted"],
        },
    )

    assert result == {"ok": True, "count": 1, "events": [{"event_id": "event-1", "title": "Basement cleanup"}]}
    assert service.calls[0]["calendar_ids"] == ["family-redacted"]


async def test_freyja6_core_home_assistant_read_tools_are_read_only_wrappers(monkeypatch) -> None:
    calls = []

    async def fake_read_state(request):
        calls.append((request.tool_name, request.arguments, request.actor))
        return {"entity_id": "sensor.redacted", "state": "72", "source": "fixture"}

    async def fake_list_states(request):
        calls.append((request.tool_name, request.arguments, request.actor))
        return {"count": 1, "entities": [{"entity_id": "sensor.redacted"}], "source": "fixture"}

    monkeypatch.setattr(core, "_home_assistant_read_state", fake_read_state)
    monkeypatch.setattr(core, "_home_assistant_list_states", fake_list_states)

    read = await core.call_tool("home_assistant.read_state", {"entity_id": "sensor.redacted"})
    listed = await core.call_tool("home_assistant.list_states", {"domain": "sensor"})

    assert read["ok"] is True
    assert listed["ok"] is True
    assert calls == [
        ("home_assistant_read_state", {"entity_id": "sensor.redacted"}, "freyja-core"),
        ("home_assistant_list_states", {"domain": "sensor"}, "freyja-core"),
    ]
