# Freyja-OS Handoff

## Current Milestone

Personal Intelligence Services started with Family Calendar as the reference
service architecture.

## Family Calendar

Implemented components:

- `freyja.calendar.models` for family members, availability rules, events,
  preferences, time windows, and ranked options.
- `freyja.calendar.providers` for `CalendarProvider`,
  `InMemoryCalendarProvider`, `GoogleCalendarProvider`, and
  `AppleCalendarProvider`.
- `freyja.calendar.service.CalendarService` for schedule views, free/busy,
  event search, CRUD forwarding, ranked free-time search, conflict detection,
  travel buffers, and memory-preference scoring.
- `freyja.tools.calendar` for Director tools:
  - `calendar_today_schedule`
  - `calendar_tomorrow_schedule`
  - `calendar_free_busy`
  - `calendar_list_events`
  - `calendar_search_events`
  - `calendar_create_event`
  - `calendar_modify_event`
  - `calendar_delete_event`
  - `calendar_find_time`
  - `calendar_move_event_if_conflict`

The implementation uses mocked/in-memory providers only. No live Google or
Apple calendar account access is required.

## Certification

Calendar certification suites were added under `certification/suites/calendar/`
for schedule reasoning, conflict detection, preference handling, and provider
abstraction.

## Next Work

- Add live Google Calendar OAuth/storage only after the provider contract is
  stable and operator approval requirements are documented.
- Add richer natural-language calendar planning prompts once benchmark data
  shows which model handles tool planning best.
- Extend memory integration with a structured `domain=calendar` preference
  convention rather than relying only on free-text preference strings.
