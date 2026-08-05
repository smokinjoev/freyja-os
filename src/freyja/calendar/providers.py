from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Protocol

import httpx

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


class AppleCalendarProvider:
    """Authenticated client for the narrow EventKit bridge hosted on Iris."""

    name = "apple"

    def __init__(self, *, base_url: str, token: str, timeout_seconds: float = 15.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not base_url or not token:
            raise ValueError("Apple Calendar bridge URL and token are required")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs: object) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
            response = await client.request(method, f"{self._base_url}{path}", headers=headers, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Apple Calendar bridge returned an invalid response")
        return payload

    async def list_events(self, *, calendar_ids: list[str], start: datetime, end: datetime) -> list[CalendarEvent]:
        params: list[tuple[str, str]] = [("start", start.isoformat()), ("end", end.isoformat())]
        params.extend(("calendar_id", value) for value in calendar_ids)
        payload = await self._request("GET", "/events", params=params)
        return [_event_from_bridge(item) for item in payload.get("events", [])]

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        payload = await self._request("POST", "/events", json=_event_to_bridge(event))
        created = _event_from_bridge(payload.get("event"))
        if not created.event_id:
            raise RuntimeError("Apple Calendar did not return a confirmed event ID")
        return created

    async def modify_event(self, event_id: str, updates: dict) -> CalendarEvent | None:
        normalized = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in updates.items()}
        payload = await self._request("PATCH", "/events", json={"event_id": event_id, "updates": normalized})
        return _event_from_bridge(payload["event"]) if payload.get("event") else None

    async def delete_event(self, event_id: str) -> bool:
        payload = await self._request("DELETE", f"/events/{event_id}")
        return payload.get("deleted") is True


def _event_to_bridge(event: CalendarEvent) -> dict:
    return {
        "title": event.title,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "calendar_id": event.calendar_id or None,
        "location": event.location,
        "description": event.description,
    }


def _event_from_bridge(value: object) -> CalendarEvent:
    if not isinstance(value, dict):
        raise RuntimeError("Apple Calendar bridge returned an invalid event")
    required = ("event_id", "calendar_id", "title", "start", "end")
    if any(not isinstance(value.get(key), str) for key in required):
        raise RuntimeError("Apple Calendar bridge event is incomplete")
    return CalendarEvent(
        event_id=value["event_id"],
        calendar_id=value["calendar_id"],
        title=value["title"],
        start=datetime.fromisoformat(value["start"].replace("Z", "+00:00")),
        end=datetime.fromisoformat(value["end"].replace("Z", "+00:00")),
        location=value.get("location") if isinstance(value.get("location"), str) else None,
        description=value.get("description") if isinstance(value.get("description"), str) else None,
        provider="apple",
        metadata={"calendar_title": value.get("calendar_title"), "all_day": bool(value.get("all_day", False))},
    )
