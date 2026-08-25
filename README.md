# Freyja-OS

Freyja-OS is a locally controlled personal-agent platform.

## Current architecture

- Atlas: Freyja Director, control plane, policy authority, memory/identity state, and always-on connector services
- Iris: Apple-native MacAgent host and always-hot 7B routing/reflex tier
- Vulcan or another heavy inference node: optional complex `local_reasoning` provider through the private tailnet
- Hera: household voice/avatar presence and development/experimental node
- Mars: utility, fallback, monitoring, or test node; not the authoritative Director host
- Raspberry Pi: future edge automation node
- Additional computers: optional worker nodes

## Current phase

Current phase: Identity Service on top of the Director, Router, Memory,
Certification, Benchmark, Communications, and Family Calendar foundation.

Every pull request runs the full test suite on Python 3.11-3.13 plus repository
hygiene checks that reject common credential signatures and tracked runtime
state.

## Identity Service

`freyja.identity` is the canonical source of people known to Freyja. It models
`Person`, `Identity`, `Alias`, and `Relationship`, then resolves raw platform
identifiers into people before downstream services act on them.

Identity data can remain on the deterministic development seed or load from a
versioned local SQLite store. Native Apple Contacts, private vCard, and JSON
imports support validation, duplicate detection, dry runs, and transactional
replacement. The native Mac bridge is deliberately small and reusable; it does
not require a separate MacAgent service. See
[`docs/IDENTITY_STORAGE.md`](docs/IDENTITY_STORAGE.md).
Legacy platform memory can be consolidated safely using the dry-run-first
[`identity-to-memory migration`](docs/IDENTITY_MEMORY_MIGRATION.md).
Private identity databases support checksummed backup, verification, and safe
restore workflows documented in [`docs/IDENTITY_BACKUP.md`](docs/IDENTITY_BACKUP.md).

- Signal and iMessage senders can resolve to a `Person` while preserving legacy
  allowlist syntax.
- Calendar members can be selected by person ID or alias; events attach to
  canonical person IDs while providers keep their own calendar IDs.
- Memory principals for known people use the stable family-member subject so
  preferences attach to a person instead of a raw phone number, email address,
  or account ID.
- Read-only Director tools expose identity resolution and relationship queries
  for certification and future router use.

## Personal Intelligence Services

Freyja services should integrate with the existing Director tool path instead
of becoming standalone apps. The first reference service is Family Calendar:

- `CalendarService` owns schedule reasoning.
- `CalendarProvider` adapters isolate calendar backends.
- `GoogleCalendarProvider` and `AppleCalendarProvider` preserve provider
  boundaries without requiring live accounts in tests. On Iris, the Apple
  provider can use EventKit through local Swift execution when
  `CALENDAR_DEFAULT_PROVIDER=apple` and `APPLE_CALENDAR_ENABLED=true`.
- Director tools expose schedules, free/busy, event search, CRUD operations,
  ranked time finding, and conflict-aware event movement.
- Calendar writes require a household principal, Director authorization, and
  explicit approval before execution.
- Long-term preferences from memory can influence scheduling, but explicit user
  instructions remain higher priority.

## Communications

Signal is the preferred protected remote connector. Native iMessage remains an
Apple-native connector path. Both adapters enforce sender policy in their
gateways, map approved senders to memory principals, forward requests to
`/route`, and return sanitized responses.

Allowed senders may be plain platform addresses for backward compatibility or
family aliases for multi-user support:

```text
SIGNAL_ALLOWED_SENDERS=joe=+15551234567,beth=+15557654321
IMESSAGE_ALLOWED_SENDERS=joe=joe@example.com,beth=+15557654321
```

For Signal, aliases also select the protected agent context: `joe` routes as
Cloyd Gibbler with `person:joe`, `beth` routes as Benedict with `person:beth`,
and `family` routes as Freyja with `person:family`. Signal-originated requests
are marked private before they reach Atlas so cloud routing is blocked by
default. Conversation IDs remain platform-specific and raw phone numbers are
not forwarded in Director headers.

## Certification CLI

Run the default smoke certification gauntlet with the default Ollama provider:

```bash
freyja-certify
```

The CLI writes timestamped Markdown and JSON reports to
`certification/reports/` by default, including per-category scores for core,
tools, routing, memory, vision, planning, and connector behavior. Use
`freyja-certify --help` for provider, model, router-mode, suite, difficulty,
benchmark, compare, and output directory options. See
[`certification/README.md`](certification/README.md) for suite details.

## Current host roles

Atlas is the Freyja Director and control-plane host. Atlas also runs always-on
infrastructure services and the Signal connector. Iris owns Apple-native
MacAgent capability, including native iMessage access, and keeps the fast local
7B inference tier hot for low-latency local work. Optional heavy inference nodes
sit behind Director policy; Director routing must tolerate those nodes being
unavailable and use configured fallback paths instead of fabricating an answer.
OpenRouter fallback requires a configured API key and approved model allowlist.

The Signal connector deployment uses
[`bbernhard/signal-cli-rest-api`](https://github.com/bbernhard/signal-cli-rest-api)
in `native` mode on Atlas: a transport adapter polls its receive endpoint,
normalizes supported messages, passes them to `SignalGateway`, forwards
authorized requests to the Atlas Director, and sends the resulting responses
through the REST wrapper. Transport code does not make authorization or
group-policy decisions. The gateway continues to enforce sender allowlists,
reject groups, and suppress duplicates.

Copy the repository `.env.example` to `.env` for local execution, fill in only
local values, and restrict it to the owner:

```bash
cp .env.example .env
chmod 600 .env
source .venv/bin/activate
python scripts/run-signal-connector.py
```

The Signal account must already be registered or linked in the REST wrapper.
First-time registration or linking is a deliberate operator action; follow the
wrapper's upstream instructions from a trusted Atlas session and never commit
the resulting account data or phone numbers.

For the Atlas Signal connector Compose layout, environment-file instructions,
private networking, and validation, see
[`deploy/compose/signal/README.md`](deploy/compose/signal/README.md). The Signal
REST API has no public port in that deployment and is reachable only on its
private Docker network.
