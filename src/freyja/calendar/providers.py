from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Protocol

from freyja.calendar.models import CalendarEvent


class CalendarProvider(Protocol):
    name: str

    async def list_events(
        self,
        *,
        calendar_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        ...

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        ...

    async def modify_event(self, event_id: str, updates: dict) -> CalendarEvent | None:
        ...

    async def delete_event(self, event_id: str) -> bool:
        ...


class InMemoryCalendarProvider:
    name = "memory"

    def __init__(self, events: list[CalendarEvent] | None = None) -> None:
        self._events: dict[str, CalendarEvent] = {
            event.event_id: replace(event, provider=self.name) for event in events or []
        }

    async def list_events(
        self,
        *,
        calendar_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        calendar_set = set(calendar_ids)
        return sorted(
            (
                event
                for event in self._events.values()
                if event.calendar_id in calendar_set and event.start < end and start < event.end
            ),
            key=lambda event: (event.start, event.end, event.title),
        )

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        event_id = event.event_id or str(uuid.uuid4())
        stored = replace(event, event_id=event_id, provider=self.name)
        self._events[event_id] = stored
        return stored

    async def modify_event(self, event_id: str, updates: dict) -> CalendarEvent | None:
        event = self._events.get(event_id)
        if event is None:
            return None
        allowed = {key: value for key, value in updates.items() if key in CalendarEvent.__dataclass_fields__}
        updated = replace(event, **allowed)
        self._events[event_id] = updated
        return updated

    async def delete_event(self, event_id: str) -> bool:
        return self._events.pop(event_id, None) is not None


class GoogleCalendarProvider(InMemoryCalendarProvider):
    """Google Calendar provider shell.

    The first implementation intentionally avoids live Google APIs. It preserves
    the provider boundary while tests and certification use mocked providers.
    """

    name = "google"


class AppleCalendarProvider(InMemoryCalendarProvider):
    """Placeholder provider for a future local Apple Calendar bridge."""

    name = "apple"
