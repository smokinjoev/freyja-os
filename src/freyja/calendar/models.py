from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: "TimeWindow") -> bool:
        return self.start <= other.start and other.end <= self.end

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "minutes": self.minutes}


@dataclass(frozen=True)
class AvailabilityRule:
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    start_time: time = time(9, 0)
    end_time: time = time(17, 0)
    label: str = "working_hours"


@dataclass(frozen=True)
class CalendarPreference:
    description: str
    weight: int = 1


@dataclass(frozen=True)
class CalendarMember:
    member_id: str
    display_name: str
    calendar_ids: tuple[str, ...] = ()
    person_id: str | None = None
    timezone: str = "UTC"
    availability_rules: tuple[AvailabilityRule, ...] = field(default_factory=tuple)
    preferred_working_hours: tuple[AvailabilityRule, ...] = field(default_factory=tuple)
    preferred_meeting_windows: tuple[AvailabilityRule, ...] = field(default_factory=tuple)
    travel_buffer_minutes: int = 0
    preferences: tuple[CalendarPreference, ...] = field(default_factory=tuple)

    def all_calendar_ids(self) -> tuple[str, ...]:
        return self.calendar_ids or (self.member_id,)

    @property
    def canonical_person_id(self) -> str:
        return self.person_id or self.member_id


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    calendar_id: str
    title: str
    start: datetime
    end: datetime
    attendee_ids: tuple[str, ...] = ()
    location: str | None = None
    description: str | None = None
    provider: str = "memory"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def window(self) -> TimeWindow:
        return TimeWindow(self.start, self.end)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "calendar_id": self.calendar_id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "attendee_ids": list(self.attendee_ids),
            "location": self.location,
            "description": self.description,
            "provider": self.provider,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RankedTimeOption:
    window: TimeWindow
    score: float
    attendee_ids: tuple[str, ...]
    conflicts: tuple[CalendarEvent, ...] = ()
    reasons: tuple[str, ...] = ()
    preference_matches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window.to_dict(),
            "score": self.score,
            "attendee_ids": list(self.attendee_ids),
            "conflicts": [event.to_dict() for event in self.conflicts],
            "reasons": list(self.reasons),
            "preference_matches": list(self.preference_matches),
        }
