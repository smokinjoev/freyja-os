from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from freyja.calendar.models import AvailabilityRule, CalendarEvent, CalendarMember, CalendarPreference, RankedTimeOption, TimeWindow
from freyja.calendar.providers import CalendarProvider, InMemoryCalendarProvider
from freyja.identity import IdentityService, default_identity_service


class CalendarService:
    def __init__(
        self,
        *,
        providers: dict[str, CalendarProvider] | None = None,
        members: list[CalendarMember] | None = None,
        identity_service: IdentityService | None = None,
    ) -> None:
        self._providers = providers or {"memory": InMemoryCalendarProvider()}
        self._identity_service = identity_service or default_identity_service()
        self._members = {member.canonical_person_id: member for member in members or _default_family()}

    @property
    def members(self) -> dict[str, CalendarMember]:
        return dict(self._members)

    async def schedule_for_day(
        self,
        target_date: date,
        *,
        member_ids: list[str] | None = None,
    ) -> dict:
        start = datetime.combine(target_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        events = await self.list_events(start=start, end=end, member_ids=member_ids)
        return {
            "date": target_date.isoformat(),
            "events": [event.to_dict() for event in events],
            "count": len(events),
        }

    async def list_events(
        self,
        *,
        start: datetime,
        end: datetime,
        member_ids: list[str] | None = None,
        calendar_ids: list[str] | None = None,
    ) -> list[CalendarEvent]:
        calendars = calendar_ids or self._calendar_ids(member_ids)
        events: list[CalendarEvent] = []
        for provider in self._providers.values():
            events.extend(await provider.list_events(calendar_ids=calendars, start=start, end=end))
        return sorted(events, key=lambda event: (event.start, event.end, event.title))

    async def search_events(
        self,
        *,
        query: str,
        start: datetime,
        end: datetime,
        member_ids: list[str] | None = None,
    ) -> list[CalendarEvent]:
        lowered = query.lower()
        events = await self.list_events(start=start, end=end, member_ids=member_ids)
        return [
            event
            for event in events
            if lowered in event.title.lower()
            or (event.description and lowered in event.description.lower())
            or (event.location and lowered in event.location.lower())
        ]

    async def free_busy(
        self,
        *,
        start: datetime,
        end: datetime,
        member_ids: list[str] | None = None,
    ) -> dict:
        members = self._selected_members(member_ids)
        events = await self.list_events(start=start, end=end, member_ids=[member.canonical_person_id for member in members])
        busy = {
            member.canonical_person_id: [
                event.to_dict()
                for event in events
                if event.calendar_id in member.all_calendar_ids()
                or set(event.attendee_ids) & {member.canonical_person_id, member.member_id}
            ]
            for member in members
        }
        return {"window": TimeWindow(start, end).to_dict(), "busy": busy}

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        member_ids: list[str] | None = None,
        calendar_id: str | None = None,
        provider_name: str = "memory",
        location: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        members = self._selected_members(member_ids)
        target_calendar = calendar_id or ("" if provider_name == "apple" else members[0].all_calendar_ids()[0])
        provider = self._providers[provider_name]
        return await provider.create_event(
            CalendarEvent(
                event_id="",
                calendar_id=target_calendar,
                title=title,
                start=start,
                end=end,
                attendee_ids=tuple(member.canonical_person_id for member in members),
                location=location,
                description=description,
                provider=provider_name,
            )
        )

    async def modify_event(
        self,
        *,
        event_id: str,
        updates: dict,
        provider_name: str = "memory",
    ) -> CalendarEvent | None:
        updates = dict(updates)
        for key in ("start", "end"):
            if isinstance(updates.get(key), str):
                updates[key] = parse_datetime(updates[key])
        return await self._providers[provider_name].modify_event(event_id, updates)

    async def delete_event(self, *, event_id: str, provider_name: str = "memory") -> bool:
        return await self._providers[provider_name].delete_event(event_id)

    async def find_time(
        self,
        *,
        start: datetime,
        end: datetime,
        duration_minutes: int,
        member_ids: list[str] | None = None,
        memory_preferences: list[str] | None = None,
        step_minutes: int = 30,
        limit: int = 5,
        after_work: bool = False,
        least_disruptive: bool = True,
    ) -> list[RankedTimeOption]:
        members = self._selected_members(member_ids)
        busy_events = await self.list_events(start=start, end=end, member_ids=[member.canonical_person_id for member in members])
        options: list[RankedTimeOption] = []
        cursor = _ceil_to_step(start, step_minutes)
        duration = timedelta(minutes=max(1, duration_minutes))
        while cursor + duration <= end:
            window = TimeWindow(cursor, cursor + duration)
            conflicts = tuple(event for event in busy_events if event.window.overlaps(_buffered_window(window, members)))
            if not conflicts:
                score, reasons, matches = self._score_window(
                    window,
                    members,
                    memory_preferences or [],
                    after_work=after_work,
                    least_disruptive=least_disruptive,
                )
                options.append(
                    RankedTimeOption(
                        window=window,
                        score=score,
                        attendee_ids=tuple(member.canonical_person_id for member in members),
                        reasons=tuple(reasons),
                        preference_matches=tuple(matches),
                    )
                )
            cursor += timedelta(minutes=max(5, step_minutes))
        return sorted(options, key=lambda option: (-option.score, option.window.start))[: max(1, limit)]

    async def move_event_if_conflict(
        self,
        *,
        event_id: str,
        search_start: datetime,
        search_end: datetime,
        duration_minutes: int,
        member_ids: list[str] | None = None,
        memory_preferences: list[str] | None = None,
        provider_name: str = "memory",
    ) -> dict:
        events = await self.list_events(start=search_start - timedelta(days=7), end=search_end + timedelta(days=7))
        current = next((event for event in events if event.event_id == event_id), None)
        if current is None:
            return {"moved": False, "reason": "event_not_found", "options": []}
        options = await self.find_time(
            start=search_start,
            end=search_end,
            duration_minutes=duration_minutes,
            member_ids=member_ids or list(current.attendee_ids),
            memory_preferences=memory_preferences,
        )
        if not options:
            return {"moved": False, "reason": "no_free_option", "options": []}
        best = options[0]
        updated = await self.modify_event(
            event_id=event_id,
            provider_name=provider_name,
            updates={"start": best.window.start, "end": best.window.end},
        )
        return {
            "moved": updated is not None,
            "event": updated.to_dict() if updated else None,
            "selected_option": best.to_dict(),
            "options": [option.to_dict() for option in options],
        }

    def _calendar_ids(self, member_ids: list[str] | None) -> list[str]:
        return [
            calendar_id
            for member in self._selected_members(member_ids)
            for calendar_id in member.all_calendar_ids()
        ]

    def _selected_members(self, member_ids: list[str] | None) -> list[CalendarMember]:
        if not member_ids:
            return list(self._members.values())
        selected = [
            self._members[resolved_id]
            for member_id in member_ids
            if (resolved_id := self._resolve_member_id(member_id)) in self._members
        ]
        return selected or list(self._members.values())

    def _resolve_member_id(self, member_id: str) -> str:
        if member_id in self._members:
            return member_id
        person = self._identity_service.resolve(member_id)
        if person is not None:
            return person.person_id
        return member_id

    def _score_window(
        self,
        window: TimeWindow,
        members: list[CalendarMember],
        memory_preferences: list[str],
        *,
        after_work: bool,
        least_disruptive: bool,
    ) -> tuple[float, list[str], list[str]]:
        score = 100.0
        reasons = ["all requested members are free"]
        matches: list[str] = []
        if least_disruptive:
            score += 5
            reasons.append("no existing event needs to move")
        if after_work:
            if window.start.hour >= 17:
                score += 15
                reasons.append("matches after-work request")
            else:
                score -= 30
                reasons.append("before preferred after-work window")
        for member in members:
            member_score, member_reasons = _member_preference_score(member, window)
            score += member_score
            reasons.extend(member_reasons)
        memory_score, matches = _memory_preference_score(memory_preferences, window)
        score += memory_score
        return score, reasons, matches


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _default_family() -> list[CalendarMember]:
    default_rule = AvailabilityRule(days=(0, 1, 2, 3, 4), start_time=time(9), end_time=time(17))
    return [
        CalendarMember(
            member_id="joe",
            display_name="Joe",
            calendar_ids=("joe",),
            timezone="America/New_York",
            availability_rules=(default_rule,),
            preferred_meeting_windows=(AvailabilityRule(days=(0, 1, 2, 3, 4), start_time=time(9), end_time=time(12), label="mornings"),),
            preferences=(CalendarPreference("prefers mornings", 2),),
        ),
        CalendarMember(
            member_id="beth",
            display_name="Beth",
            calendar_ids=("beth",),
            timezone="America/New_York",
            availability_rules=(default_rule,),
        ),
    ]


def _ceil_to_step(value: datetime, step_minutes: int) -> datetime:
    step = max(5, step_minutes)
    minute = ((value.minute + step - 1) // step) * step
    rounded = value.replace(second=0, microsecond=0)
    if minute >= 60:
        rounded = rounded.replace(minute=0) + timedelta(hours=1)
    else:
        rounded = rounded.replace(minute=minute)
    return rounded


def _buffered_window(window: TimeWindow, members: list[CalendarMember]) -> TimeWindow:
    buffer = max((member.travel_buffer_minutes for member in members), default=0)
    return TimeWindow(window.start - timedelta(minutes=buffer), window.end + timedelta(minutes=buffer))


def _member_preference_score(member: CalendarMember, window: TimeWindow) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    local_start = window.start.astimezone(ZoneInfo(member.timezone))
    for rule in member.availability_rules:
        if local_start.weekday() in rule.days and rule.start_time <= local_start.time() <= rule.end_time:
            score += 5
            reasons.append(f"{member.display_name} is inside {rule.label}")
    for rule in member.preferred_meeting_windows:
        if local_start.weekday() in rule.days and rule.start_time <= local_start.time() <= rule.end_time:
            score += 10
            reasons.append(f"{member.display_name} preference: {rule.label}")
    for preference in member.preferences:
        lowered = preference.description.lower()
        if "morning" in lowered and local_start.hour < 12:
            score += 3 * preference.weight
            reasons.append(f"{member.display_name}: {preference.description}")
    return score, reasons


def _memory_preference_score(preferences: list[str], window: TimeWindow) -> tuple[float, list[str]]:
    score = 0.0
    matches: list[str] = []
    weekday = window.start.weekday()
    hour = window.start.hour
    for preference in preferences:
        lowered = preference.lower()
        if "morning" in lowered and hour < 12:
            score += 8
            matches.append(preference)
        if "after 6" in lowered and hour >= 18:
            score += 8
            matches.append(preference)
        if "avoid monday evening" in lowered and weekday == 0 and hour >= 17:
            score -= 25
            matches.append(preference)
        if "cannot miss school" in lowered and weekday < 5 and 8 <= hour < 15:
            score -= 20
            matches.append(preference)
    return score, matches
