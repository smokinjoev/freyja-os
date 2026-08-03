# Freyja-OS Handoff

## Current Milestone

Identity Service: make `Person` the canonical representation for people across
memory, messaging, calendar, Director tools, and future voice/avatar work.

## Completed Work

- Added `freyja.identity` with `Person`, `Identity`, `Alias`,
  `Relationship`, and `IdentityService`.
- Implemented alias, phone, email, Signal, iMessage, and calendar-owner
  resolution.
- Added queryable directed relationships such as spouse and child.
- Added read-only Director tools:
  - `identity_resolution`
  - `identity_relationships`
- Signal and iMessage allowlists now attach canonical Person headers when a
  sender maps to a known person, while preserving legacy allowlist behavior.
- Router tool execution now receives sanitized person metadata from trusted
  connector headers.
- Calendar service and tools now accept person IDs or aliases and default to
  the resolved sender when available.
- Identity certification suites were added under
  `certification/suites/identity/`.

## Remaining Work

- Replace the in-code default family seed with a persistent contact source.
- Add production contact import/sync for Google Contacts, Apple Contacts, or a
  local encrypted contacts file.
- Expand relationship coverage beyond the current directed edges.
- Add future voice/avatar identity adapters when those subsystems are built.
- Use identity benchmark history for router policy only after benchmark data is
  collected; no automatic routing changes are implemented yet.

## Architectural Decisions

- Identity is a shared service, not a parallel Director or messaging path.
- Connectors perform platform authorization first, then pass sanitized identity
  headers to the Director.
- Raw phone numbers, emails, account IDs, and device IDs are not used as memory
  subjects for known people.
- Memory remains scoped through `MemoryPrincipal`; known people keep the stable
  `family-member:<hash>` subject for backward compatibility.
- Calendar provider account IDs remain provider data. Scheduling logic works in
  terms of canonical person IDs where practical.
- Tests use mocked contacts, mocked connectors, and in-memory calendar
  providers. No live services are required.

## Completed Foundation

- Director, Router, and tool execution path.
- Memory framework and shared memory APIs.
- Certification CLI, Gauntlet, runtime behavioral verification, benchmark, and
  comparison framework.
- Multi-user Communications through Signal and native iMessage connectors.
- Family Calendar Personal Intelligence Service.

## Next Milestone

Prepare Identity for persistent household use: configure a durable contact
store, add import/sync adapters, and migrate production messaging/calendar
configuration from inline aliases to canonical Person records.
