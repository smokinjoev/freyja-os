# Freyja-OS Handoff

## Current Milestone

Communications: Signal production integration, native iMessage integration,
multi-user messaging support, Director integration, and certification coverage.

## Completed Work

- Signal gateway forwards authorized senders to the Director `/route` endpoint
  with connector auth, memory-principal headers, duplicate suppression, group
  rejection, safe outbound errors, and mocked transport coverage.
- Native iMessage gateway forwards authorized macOS bridge events to the
  Director with the same memory-principal pattern, duplicate/self/group
  suppression, safe outbound errors, and mocked transport coverage.
- Shared messaging identity resolution supports both legacy plain allowlists
  and multi-user aliases such as `joe=+15551234567` or
  `beth=beth@example.com`.
- Aliased Signal and iMessage senders resolve to the same
  `family-member:<hash>` memory subject, while conversations remain
  platform-scoped.
- Connector certification now includes Signal, iMessage, multi-user messaging,
  API connector behavior, and boundary expectations.
- Family Calendar remains implemented as the first Personal Intelligence
  Service and is ready to use communications as a user-facing access path.

## Remaining Work

- Configure production allowlists per family member on the deployed Signal and
  iMessage hosts.
- Run live delivery checks on the actual Signal REST wrapper and macOS iMessage
  bridge before declaring external delivery fully operational.
- Add future platforms by reusing the shared identity resolver and
  connector-gateway-to-Director pattern.

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

Communications certification suites live under
`certification/suites/connectors/` and cover Signal, iMessage, multi-user
identity, and connector boundary behavior.

## Architectural Decisions

- Messaging connectors stay outside the Director and act as adapters into the
  existing `/route` API.
- Authorization stays in each gateway, not in transports or model prompts.
- Raw phone numbers and email addresses are never sent as Director memory
  subjects.
- Family member aliases provide cross-platform identity continuity without
  forcing all members onto the same messaging provider.
- Connector tests use mocked HTTP/subprocess transports; no live accounts are
  required in CI.

## Next Work

Next milestone: prepare Family Calendar for real household use through the
communications layer. Add production family-member configuration, then run live
Signal and iMessage smoke tests before connecting calendar scheduling prompts to
real user conversations.
