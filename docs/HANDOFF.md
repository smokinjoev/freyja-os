# Freyja-OS Handoff

## Current Milestone

Home Assistant foundation: deploy the private automation hub on Atlas, inventory
devices safely, and add explicit approval before Freyja can open pairing or
control an entity.

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
- Director prompts restore recent conversation context, so follow-up requests
  such as "put it on my calendar" can retain the prior task and date.
- Calendar service and tools now accept person IDs or aliases and default to
  the resolved sender when available.
- Calendar writes require the configured persistent provider and refuse the
  temporary in-memory provider outside explicit test injection.
- Reminders service and tools support reminder lists, active reminder listing,
  creation, completion, deletion, and an authenticated Apple Reminders bridge.
- Persistent SQLite identity storage, JSON import, vCard import, native Apple
  Contacts import, backup, verification, and restore workflows are available.
- Signal and iMessage allowlist parsing can resolve approved raw addresses
  through the configured identity store and attach canonical Person headers
  without inline family aliases.
- Identity certification suites were added under
  `certification/suites/identity/`.

## Remaining Work

- Turn on the persistent identity store in production after importing reviewed
  household contacts, then disable seed fallback when appropriate.
- Add recurring production contact sync for the chosen canonical source.
- Deploy Home Assistant OS on Atlas and create its protected Freyja API user.
- Connect the read-only inventory to the live private endpoint.
- Add a general controlled-write approval boundary before exposing pairing.
- Enroll and classify devices deliberately; begin with a harmless test device.
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
- Family Calendar and Reminders Personal Intelligence Services.

## Next Milestone

Complete the Atlas Home Assistant installation, verify backups and inventory,
then enable time-bounded Zigbee pairing behind explicit approval. In parallel,
finish the production identity rollout by importing reviewed household contacts,
enabling the durable SQLite store for the Director and connectors, and removing
inline messaging aliases where canonical identities exist.
