# Freyja-OS

Freyja-OS is a locally controlled personal-agent platform.

## Current architecture

- Mars: Freyja Director and control plane
- Atlas: always-on infrastructure services and Signal connector
- Hera: primary complex local_reasoning provider through Tailscale; not an always-on control-plane host
- Iris: fast local inference tier; inference-focused
- Raspberry Pi: future edge automation node
- Additional computers: optional worker nodes

## Current phase

Current phase: Identity Service on top of the Director, Router, Memory,
Certification, Benchmark, Communications, and Family Calendar foundation.

## Identity Service

`freyja.identity` is the canonical source of people known to Freyja. It models
`Person`, `Identity`, `Alias`, and `Relationship`, then resolves raw platform
identifiers into people before downstream services act on them.

Identity data can remain on the deterministic development seed or load from a
versioned local SQLite store. Private JSON imports support validation, duplicate
detection, dry runs, and transactional replacement. See
[`docs/IDENTITY_STORAGE.md`](docs/IDENTITY_STORAGE.md).
Legacy platform memory can be consolidated safely using the dry-run-first
[`identity-to-memory migration`](docs/IDENTITY_MEMORY_MIGRATION.md).

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
  boundaries without requiring live accounts in tests.
- Director tools expose schedules, free/busy, event search, CRUD operations,
  ranked time finding, and conflict-aware event movement.
- Long-term preferences from memory can influence scheduling, but explicit user
  instructions remain higher priority.

## Communications

Signal and native iMessage are connector adapters into the existing Director.
They enforce sender policy in their gateways, map approved senders to memory
principals, forward requests to `/route`, and return sanitized responses.

Allowed senders may be plain platform addresses for backward compatibility or
family aliases for multi-user support:

```text
SIGNAL_ALLOWED_SENDERS=joe=+15551234567,beth=+15557654321
IMESSAGE_ALLOWED_SENDERS=joe=joe@example.com,beth=+15557654321
```

Aliases let the same family member keep a stable Person-backed memory identity
across messaging platforms while conversation IDs remain platform-specific.

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

## Rev 1 host roles

Mars is the Freyja Director and control-plane host. Atlas runs always-on
infrastructure services and the Signal connector. Hera currently provides the
strong local `local_reasoning` model for complex coding, debugging, planning,
architecture, and difficult tool-selection requests over Tailscale. Iris remains
the fast local inference tier for low-latency local work. Hera is not a core
always-on host, so Director routing must tolerate Hera being unavailable and use
configured fallback paths instead of fabricating an answer. OpenRouter fallback
requires a configured API key and approved model allowlist.

The Signal connector deployment uses
[`bbernhard/signal-cli-rest-api`](https://github.com/bbernhard/signal-cli-rest-api)
in `native` mode on Atlas: a transport adapter polls its receive endpoint,
normalizes supported messages, passes them to `SignalGateway`, forwards
authorized requests to the Director on Mars, and sends the resulting responses
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
