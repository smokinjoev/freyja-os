from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Awaitable, Callable, Protocol

from freyja.calendar.models import CalendarEvent

CommandRunner = Callable[[list[str], float], Awaitable[str]]


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
    """Local Apple Calendar provider backed by EventKit.

    This provider is intended for Iris/MacAgent. It shells out to Swift so the
    Director can keep using the normal calendar service/tool boundary while
    macOS owns Apple account access and permission prompts.
    """

    name = "apple"

    def __init__(
        self,
        *,
        default_calendar_name: str = "iCloud::Family",
        calendar_aliases: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
        command: tuple[str, ...] = ("swift",),
        runner: CommandRunner | None = None,
    ) -> None:
        self.default_calendar_name = default_calendar_name
        self.calendar_aliases = calendar_aliases or {}
        self.timeout_seconds = timeout_seconds
        self.command = command
        self._runner = runner or _run_command

    async def list_events(
        self,
        *,
        calendar_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        payload = {
            "calendar_selectors": self._calendar_names(calendar_ids),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        data = await self._call("list", payload)
        return [self._event_from_payload(item) for item in data.get("events", [])]

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        payload = {
            "calendar_selector": self._calendar_name(event.calendar_id),
            "title": event.title,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "attendee_ids": list(event.attendee_ids),
            "location": event.location,
            "description": event.description,
        }
        data = await self._call("create", payload)
        return self._event_from_payload(data["event"])

    async def modify_event(self, event_id: str, updates: dict) -> CalendarEvent | None:
        payload = {"event_id": event_id, "updates": _serialize_updates(updates)}
        data = await self._call("modify", payload)
        event = data.get("event")
        return self._event_from_payload(event) if event else None

    async def delete_event(self, event_id: str) -> bool:
        data = await self._call("delete", {"event_id": event_id})
        return bool(data.get("deleted"))

    async def _call(self, operation: str, payload: dict) -> dict:
        args = [
            *self.command,
            "-e",
            _SWIFT_SCRIPT,
            operation,
            json.dumps(payload, separators=(",", ":")),
        ]
        output = await self._runner(args, self.timeout_seconds)
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Apple Calendar bridge returned invalid JSON") from exc
        if data.get("ok") is not True:
            message = str(data.get("error") or "Apple Calendar bridge failed")
            raise RuntimeError(message)
        return data

    def _calendar_names(self, calendar_ids: list[str]) -> list[str]:
        names = [self._calendar_name(calendar_id) for calendar_id in calendar_ids]
        if not names:
            names = [self.default_calendar_name]
        return list(dict.fromkeys(names))

    def _calendar_name(self, calendar_id: str | None) -> str:
        if not calendar_id:
            return self.default_calendar_name
        return self.calendar_aliases.get(calendar_id, calendar_id)

    def _event_from_payload(self, payload: dict) -> CalendarEvent:
        return CalendarEvent(
            event_id=str(payload.get("event_id") or ""),
            calendar_id=str(payload.get("calendar_id") or self.default_calendar_name),
            title=str(payload.get("title") or ""),
            start=datetime.fromisoformat(str(payload["start"]).replace("Z", "+00:00")),
            end=datetime.fromisoformat(str(payload["end"]).replace("Z", "+00:00")),
            attendee_ids=tuple(str(item) for item in payload.get("attendee_ids", [])),
            location=payload.get("location"),
            description=payload.get("description"),
            provider=self.name,
            metadata=dict(payload.get("metadata") or {}),
        )


async def _run_command(args: list[str], timeout_seconds: float) -> str:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError("Apple Calendar bridge timed out")
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "Apple Calendar bridge command failed")
    return stdout.decode("utf-8", errors="replace").strip()


def _serialize_updates(updates: dict) -> dict:
    serialized = dict(updates)
    for key in ("start", "end"):
        value = serialized.get(key)
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
    return serialized


_SWIFT_SCRIPT = r"""
import EventKit
import Foundation

func emit(_ value: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

func fail(_ message: String) -> Never {
    emit(["ok": false, "error": message])
    exit(0)
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    fail("Missing operation or payload")
}

let operation = args[1]
guard
    let payloadData = args[2].data(using: .utf8),
    let payload = try JSONSerialization.jsonObject(with: payloadData) as? [String: Any]
else {
    fail("Invalid payload JSON")
}

let store = EKEventStore()
let status = EKEventStore.authorizationStatus(for: .event)
guard status == .fullAccess || status == .writeOnly || status == .authorized else {
    fail("Calendar access is not authorized")
}

func parseDate(_ value: Any?) -> Date {
    guard let text = value as? String else {
        fail("Missing date")
    }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: text) {
        return date
    }
    formatter.formatOptions = [.withInternetDateTime]
    if let date = formatter.date(from: text) {
        return date
    }
    fail("Invalid date: \(text)")
}

func selectorMatches(_ selector: String, calendar: EKCalendar) -> Bool {
    if selector == calendar.title || selector == calendar.calendarIdentifier {
        return true
    }
    let sourceQualified = "\(calendar.source.title)::\(calendar.title)"
    return selector == sourceQualified
}

func calendarForSelector(_ selector: String) -> EKCalendar {
    let matches = store.calendars(for: .event).filter { selectorMatches(selector, calendar: $0) }
    guard let calendar = matches.first else {
        fail("Calendar not found: \(selector)")
    }
    if matches.count > 1 && !selector.contains("::") {
        fail("Calendar selector is ambiguous: \(selector)")
    }
    return calendar
}

func eventObject(_ event: EKEvent, calendar: EKCalendar) -> [String: Any] {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return [
        "event_id": event.eventIdentifier ?? "",
        "calendar_id": "\(calendar.source.title)::\(calendar.title)",
        "title": event.title ?? "",
        "start": formatter.string(from: event.startDate),
        "end": formatter.string(from: event.endDate),
        "location": event.location as Any,
        "description": event.notes as Any,
        "attendee_ids": [],
        "metadata": [
            "apple_calendar_id": calendar.calendarIdentifier,
            "apple_calendar_title": calendar.title,
            "apple_calendar_source": calendar.source.title
        ]
    ]
}

func findEvent(_ eventId: String) -> EKEvent? {
    if let event = store.event(withIdentifier: eventId) {
        return event
    }
    let start = Calendar.current.date(byAdding: .year, value: -1, to: Date())!
    let end = Calendar.current.date(byAdding: .year, value: 2, to: Date())!
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: nil)
    return store.events(matching: predicate).first { $0.eventIdentifier == eventId }
}

switch operation {
case "list":
    let selectors = payload["calendar_selectors"] as? [String] ?? []
    let calendars = selectors.map { calendarForSelector($0) }
    let start = parseDate(payload["start"])
    let end = parseDate(payload["end"])
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
    let events = store.events(matching: predicate)
        .sorted { $0.startDate < $1.startDate }
        .map { eventObject($0, calendar: $0.calendar) }
    emit(["ok": true, "events": events])

case "create":
    guard let selector = payload["calendar_selector"] as? String else {
        fail("Missing calendar selector")
    }
    let calendar = calendarForSelector(selector)
    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = payload["title"] as? String ?? "Untitled"
    event.startDate = parseDate(payload["start"])
    event.endDate = parseDate(payload["end"])
    event.location = payload["location"] as? String
    event.notes = payload["description"] as? String
    do {
        try store.save(event, span: .thisEvent, commit: true)
    } catch {
        fail("Failed to save event: \(error)")
    }
    emit(["ok": true, "event": eventObject(event, calendar: calendar)])

case "modify":
    guard
        let eventId = payload["event_id"] as? String,
        let updates = payload["updates"] as? [String: Any]
    else {
        fail("Missing event id or updates")
    }
    guard let event = findEvent(eventId) else {
        emit(["ok": true, "event": NSNull()])
        exit(0)
    }
    if let title = updates["title"] as? String {
        event.title = title
    }
    if updates.keys.contains("start") {
        event.startDate = parseDate(updates["start"])
    }
    if updates.keys.contains("end") {
        event.endDate = parseDate(updates["end"])
    }
    if updates.keys.contains("location") {
        event.location = updates["location"] as? String
    }
    if updates.keys.contains("description") {
        event.notes = updates["description"] as? String
    }
    do {
        try store.save(event, span: .thisEvent, commit: true)
    } catch {
        fail("Failed to modify event: \(error)")
    }
    emit(["ok": true, "event": eventObject(event, calendar: event.calendar)])

case "delete":
    guard let eventId = payload["event_id"] as? String else {
        fail("Missing event id")
    }
    guard let event = findEvent(eventId) else {
        emit(["ok": true, "deleted": false])
        exit(0)
    }
    do {
        try store.remove(event, span: .thisEvent, commit: true)
    } catch {
        fail("Failed to delete event: \(error)")
    }
    emit(["ok": true, "deleted": true])

default:
    fail("Unsupported operation: \(operation)")
}
"""
